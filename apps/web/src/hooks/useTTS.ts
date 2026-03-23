"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { logger } from "@/lib/logger";

/**
 * TTS hook with dual mode + voice modulation support (ТЗ-04):
 * - "elevenlabs" — plays mp3 audio from backend (via WS tts.audio message)
 * - "browser" — fallback to window.speechSynthesis (Russian voice)
 *
 * New in ТЗ-04:
 *   - Accepts emotion + voice_params from backend tts.audio message
 *   - Exposes currentEmotion for Avatar3D color/animation binding
 *   - Uses duration_ms for animation synchronization
 *   - Handles couple mode (sequential playback of utterances array)
 *
 * Flow (single voice):
 *   1. Backend sends character.response (text) → shown in chat immediately
 *   2. Backend sends tts.audio { audio, format, emotion, voice_params, duration_ms }
 *   3. playAudioMessage() → decode → play → expose emotion for Avatar3D
 *   4. If tts.audio doesn't arrive within 3s → auto-fallback to speak()
 *
 * Flow (couple mode):
 *   1. Backend sends tts.couple_audio { utterances: [{ speaker, audio, emotion, ... }] }
 *   2. playCoupleAudio() → sequential playback of each utterance
 *   3. currentSpeaker / currentEmotion update with each segment
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type TTSMode = "elevenlabs" | "browser";

/** Re-export canonical EmotionState (10 states + legacy aliases) from types. */
import type { EmotionState } from "@/types";
export type { EmotionState };

/** Human factor types from Factor Activation Engine. */
export type HumanFactor = "anger" | "fatigue" | "anxiety" | "sarcasm";

/** Voice synthesis parameters (mirrors backend VoiceParams). */
export interface VoiceParams {
  stability: number;
  similarity_boost: number;
  style: number;
  speed: number;
}

/** Single-voice TTS message from backend (tts.audio). */
export interface TTSAudioMessage {
  audio: string;            // base64 mp3
  format?: string;          // "mp3" (default)
  emotion?: EmotionState;
  voice_params?: VoiceParams;
  duration_ms?: number;
  active_factors?: HumanFactor[];
}

/** One utterance in couple mode. */
export interface CoupleUtterance {
  speaker: "A" | "B" | "AB";
  audio: string;            // base64 mp3
  emotion?: EmotionState;
  voice_params?: VoiceParams;
  duration_ms?: number;
  is_whisper?: boolean;
  active_factors?: HumanFactor[];
}

/** Couple-mode TTS message from backend (tts.couple_audio). */
export interface TTSCoupleMessage {
  utterances: CoupleUtterance[];
  total_duration_ms?: number;
}

interface UseTTSOptions {
  lang?: string;
  rate?: number;
  pitch?: number;
  /** Callback fired when emotion changes (for Avatar3D binding). */
  onEmotionChange?: (emotion: EmotionState | null) => void;
  /** Callback fired when voice params change. */
  onVoiceParamsChange?: (params: VoiceParams | null) => void;
  /** Callback fired when couple-mode speaker changes. */
  onSpeakerChange?: (speaker: "A" | "B" | "AB" | null) => void;
  /** Callback fired when active human factors change (for Avatar3D effects). */
  onActiveFactorsChange?: (factors: HumanFactor[]) => void;
}

interface UseTTSReturn {
  /** Play mp3 audio from base64 (legacy — still works). */
  playAudio: (audioB64: string) => void;

  /** Play full TTS message with emotion/params (preferred for ТЗ-04). */
  playAudioMessage: (msg: TTSAudioMessage) => void;

  /** Play couple-mode utterances sequentially. */
  playCoupleAudio: (msg: TTSCoupleMessage) => void;

  /** Speak text via browser speechSynthesis (fallback). */
  speak: (text: string) => void;

  /** Schedule fallback: if playAudio isn't called within timeout, auto-speak. */
  scheduleFallback: (text: string, timeoutMs?: number) => void;

  /** Cancel scheduled fallback (call when tts.audio arrives). */
  cancelFallback: () => void;

  /** Switch permanently to browser TTS (call on tts.fallback WS message). */
  enableFallbackMode: () => void;

  /** Stop all audio playback (barge-in). */
  stop: () => void;

  /** Is audio currently playing. */
  speaking: boolean;

  /** Is TTS enabled by user. */
  enabled: boolean;
  setEnabled: (v: boolean) => void;

  /** Current TTS mode. */
  mode: TTSMode;

  /** Simulated audio level for Avatar3D animation (0-1). */
  audioLevel: number;

  /** Current emotion state from last TTS message (null when idle). */
  currentEmotion: EmotionState | null;

  /** Current voice params from last TTS message. */
  currentVoiceParams: VoiceParams | null;

  /** Current speaker in couple mode (null if single voice). */
  currentSpeaker: "A" | "B" | "AB" | null;

  /** Remaining duration of current audio in ms (for animation sync). */
  remainingDurationMs: number;

  /** Active human factors from last TTS message (for Avatar3D visual effects). */
  activeFactors: HumanFactor[];
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useTTS(options: UseTTSOptions = {}): UseTTSReturn {
  const {
    lang = "ru-RU",
    rate = 0.95,
    pitch = 1.0,
    onEmotionChange,
    onVoiceParamsChange,
    onSpeakerChange,
    onActiveFactorsChange,
  } = options;

  // --- Core state ---
  const [speaking, setSpeaking] = useState(false);
  const [enabled, setEnabled] = useState(true);
  const [mode, setMode] = useState<TTSMode>("elevenlabs");
  const [audioLevel, setAudioLevel] = useState(0);

  // --- ТЗ-04 state ---
  const [currentEmotion, setCurrentEmotion] = useState<EmotionState | null>(null);
  const [currentVoiceParams, setCurrentVoiceParams] = useState<VoiceParams | null>(null);
  const [currentSpeaker, setCurrentSpeaker] = useState<"A" | "B" | "AB" | null>(null);
  const [remainingDurationMs, setRemainingDurationMs] = useState(0);
  const [activeFactors, setActiveFactors] = useState<HumanFactor[]>([]);

  // --- Refs ---
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const objectUrlRef = useRef<string | null>(null);
  const voiceRef = useRef<SpeechSynthesisVoice | null>(null);
  const fallbackTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const durationTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const coupleQueueRef = useRef<CoupleUtterance[]>([]);
  const couplePlayingRef = useRef(false);

  // Stable callback refs (avoid stale closures)
  const onEmotionChangeRef = useRef(onEmotionChange);
  const onVoiceParamsChangeRef = useRef(onVoiceParamsChange);
  const onSpeakerChangeRef = useRef(onSpeakerChange);
  const onActiveFactorsChangeRef = useRef(onActiveFactorsChange);
  useEffect(() => { onEmotionChangeRef.current = onEmotionChange; }, [onEmotionChange]);
  useEffect(() => { onVoiceParamsChangeRef.current = onVoiceParamsChange; }, [onVoiceParamsChange]);
  useEffect(() => { onSpeakerChangeRef.current = onSpeakerChange; }, [onSpeakerChange]);
  useEffect(() => { onActiveFactorsChangeRef.current = onActiveFactorsChange; }, [onActiveFactorsChange]);

  // ---------------------------------------------------------------------------
  // Pick Russian voice for browser fallback
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (typeof window === "undefined" || !window.speechSynthesis) return;

    const pickVoice = () => {
      const voices = window.speechSynthesis.getVoices();
      voiceRef.current =
        voices.find((v) => v.lang.startsWith("ru") && v.localService) ||
        voices.find((v) => v.lang.startsWith("ru")) ||
        voices[0] || null;
    };

    pickVoice();
    window.speechSynthesis.onvoiceschanged = pickVoice;

    return () => {
      window.speechSynthesis.cancel();
    };
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current = null;
      }
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
        objectUrlRef.current = null;
      }
      if (fallbackTimerRef.current) {
        clearTimeout(fallbackTimerRef.current);
      }
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
      if (durationTimerRef.current) {
        clearInterval(durationTimerRef.current);
      }
      coupleQueueRef.current = [];
      couplePlayingRef.current = false;
      window.speechSynthesis?.cancel();
    };
  }, []);

  // ---------------------------------------------------------------------------
  // Audio level simulation for Avatar3D
  // ---------------------------------------------------------------------------
  const startAudioLevelSimulation = useCallback(() => {
    let phase = 0;
    const animate = () => {
      phase += 0.15;
      const level =
        0.3 +
        Math.sin(phase) * 0.2 +
        Math.sin(phase * 2.7) * 0.15 +
        Math.sin(phase * 0.5) * 0.1 +
        Math.random() * 0.1;
      setAudioLevel(Math.max(0, Math.min(1, level)));
      animationFrameRef.current = requestAnimationFrame(animate);
    };
    animationFrameRef.current = requestAnimationFrame(animate);
  }, []);

  const stopAudioLevelSimulation = useCallback(() => {
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }
    setAudioLevel(0);
  }, []);

  // ---------------------------------------------------------------------------
  // Duration countdown (for animation sync)
  // ---------------------------------------------------------------------------
  const startDurationCountdown = useCallback((durationMs: number) => {
    if (durationTimerRef.current) {
      clearInterval(durationTimerRef.current);
    }
    setRemainingDurationMs(durationMs);
    const startTime = Date.now();
    durationTimerRef.current = setInterval(() => {
      const elapsed = Date.now() - startTime;
      const remaining = Math.max(0, durationMs - elapsed);
      setRemainingDurationMs(remaining);
      if (remaining <= 0 && durationTimerRef.current) {
        clearInterval(durationTimerRef.current);
        durationTimerRef.current = null;
      }
    }, 100); // Update every 100ms for smooth animation
  }, []);

  const stopDurationCountdown = useCallback(() => {
    if (durationTimerRef.current) {
      clearInterval(durationTimerRef.current);
      durationTimerRef.current = null;
    }
    setRemainingDurationMs(0);
  }, []);

  // ---------------------------------------------------------------------------
  // Update emotion/params state + fire callbacks
  // ---------------------------------------------------------------------------
  const updateEmotion = useCallback((emotion: EmotionState | null) => {
    setCurrentEmotion(emotion);
    onEmotionChangeRef.current?.(emotion);
  }, []);

  const updateVoiceParams = useCallback((params: VoiceParams | null) => {
    setCurrentVoiceParams(params);
    onVoiceParamsChangeRef.current?.(params);
  }, []);

  const updateSpeaker = useCallback((speaker: "A" | "B" | "AB" | null) => {
    setCurrentSpeaker(speaker);
    onSpeakerChangeRef.current?.(speaker);
  }, []);

  const updateFactors = useCallback((factors: HumanFactor[]) => {
    setActiveFactors(factors);
    onActiveFactorsChangeRef.current?.(factors);
  }, []);

  const clearModulationState = useCallback(() => {
    updateEmotion(null);
    updateVoiceParams(null);
    updateSpeaker(null);
    updateFactors([]);
    stopDurationCountdown();
  }, [updateEmotion, updateVoiceParams, updateSpeaker, updateFactors, stopDurationCountdown]);

  // ---------------------------------------------------------------------------
  // Stop everything
  // ---------------------------------------------------------------------------
  const stop = useCallback(() => {
    // Stop mp3
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
      audioRef.current = null;
    }
    // Revoke ObjectURL to prevent memory leak
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
    // Stop browser TTS
    if (typeof window !== "undefined" && window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }
    // Stop couple queue
    coupleQueueRef.current = [];
    couplePlayingRef.current = false;
    // Stop animation + modulation
    stopAudioLevelSimulation();
    clearModulationState();
    setSpeaking(false);
  }, [stopAudioLevelSimulation, clearModulationState]);

  // ---------------------------------------------------------------------------
  // Core: decode base64 → Audio element → play with callbacks
  // ---------------------------------------------------------------------------
  const decodeAndPlay = useCallback(
    (
      audioB64: string,
      opts?: {
        emotion?: EmotionState;
        voiceParams?: VoiceParams;
        durationMs?: number;
        speaker?: "A" | "B" | "AB";
        activeFactors?: HumanFactor[];
        onEnded?: () => void;
      }
    ): HTMLAudioElement | null => {
      try {
        const binaryString = atob(audioB64);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
          bytes[i] = binaryString.charCodeAt(i);
        }
        const blob = new Blob([bytes], { type: "audio/mpeg" });
        const url = URL.createObjectURL(blob);
        objectUrlRef.current = url;

        const audio = new Audio(url);
        audioRef.current = audio;

        // Set modulation state
        if (opts?.emotion) updateEmotion(opts.emotion);
        if (opts?.voiceParams) updateVoiceParams(opts.voiceParams);
        if (opts?.speaker !== undefined) updateSpeaker(opts.speaker);
        if (opts?.activeFactors) updateFactors(opts.activeFactors);

        audio.onplay = () => {
          setSpeaking(true);
          startAudioLevelSimulation();
          if (opts?.durationMs && opts.durationMs > 0) {
            startDurationCountdown(opts.durationMs);
          }
        };

        audio.onended = () => {
          setSpeaking(false);
          stopAudioLevelSimulation();
          stopDurationCountdown();
          URL.revokeObjectURL(url);
          objectUrlRef.current = null;
          audioRef.current = null;
          opts?.onEnded?.();
        };

        audio.onerror = () => {
          setSpeaking(false);
          stopAudioLevelSimulation();
          stopDurationCountdown();
          URL.revokeObjectURL(url);
          objectUrlRef.current = null;
          audioRef.current = null;
          opts?.onEnded?.();
        };

        audio.play().then(() => {
          logger.log(
            `[TTS] Audio playback started | emotion=${opts?.emotion ?? "none"} | speaker=${opts?.speaker ?? "single"}`
          );
        }).catch((err) => {
          logger.warn("[TTS] Audio play FAILED:", err.name, err.message);
          setSpeaking(false);
          stopAudioLevelSimulation();
          stopDurationCountdown();
          URL.revokeObjectURL(url);
          objectUrlRef.current = null;
          audioRef.current = null;
          opts?.onEnded?.();
        });

        return audio;
      } catch (err) {
        logger.warn("[TTS] Audio decode failed:", err);
        opts?.onEnded?.();
        return null;
      }
    },
    [
      updateEmotion,
      updateVoiceParams,
      updateSpeaker,
      updateFactors,
      startAudioLevelSimulation,
      stopAudioLevelSimulation,
      startDurationCountdown,
      stopDurationCountdown,
    ]
  );

  // ---------------------------------------------------------------------------
  // Play mp3 from base64 (legacy API — backward compatible)
  // ---------------------------------------------------------------------------
  const playAudio = useCallback(
    (audioB64: string) => {
      logger.log(
        `[TTS] playAudio called | enabled=${enabled} | mode=${mode} | b64_len=${audioB64?.length || 0}`
      );
      if (!enabled) {
        logger.warn("[TTS] playAudio skipped — TTS disabled by user");
        return;
      }
      stop();
      decodeAndPlay(audioB64);
    },
    [enabled, mode, stop, decodeAndPlay]
  );

  // ---------------------------------------------------------------------------
  // Play full TTS message with emotion + params (ТЗ-04 API)
  // ---------------------------------------------------------------------------
  const playAudioMessage = useCallback(
    (msg: TTSAudioMessage) => {
      logger.log(
        `[TTS] playAudioMessage | enabled=${enabled} | emotion=${msg.emotion} | duration=${msg.duration_ms}ms`
      );
      if (!enabled) {
        logger.warn("[TTS] playAudioMessage skipped — TTS disabled");
        return;
      }
      stop();
      decodeAndPlay(msg.audio, {
        emotion: msg.emotion,
        voiceParams: msg.voice_params,
        durationMs: msg.duration_ms,
        activeFactors: msg.active_factors,
        onEnded: () => {
          // Keep emotion visible briefly after audio ends (for smooth Avatar3D transition)
          setTimeout(() => {
            if (!couplePlayingRef.current) {
              clearModulationState();
            }
          }, 500);
        },
      });
    },
    [enabled, stop, decodeAndPlay, clearModulationState]
  );

  // ---------------------------------------------------------------------------
  // Couple mode: sequential playback of utterances
  // ---------------------------------------------------------------------------
  const playCoupleAudio = useCallback(
    (msg: TTSCoupleMessage) => {
      logger.log(
        `[TTS] playCoupleAudio | utterances=${msg.utterances.length} | total=${msg.total_duration_ms}ms`
      );
      if (!enabled) {
        logger.warn("[TTS] playCoupleAudio skipped — TTS disabled");
        return;
      }
      stop();

      coupleQueueRef.current = [...msg.utterances];
      couplePlayingRef.current = true;

      // Total duration countdown
      if (msg.total_duration_ms && msg.total_duration_ms > 0) {
        startDurationCountdown(msg.total_duration_ms);
      }

      const playNext = () => {
        const next = coupleQueueRef.current.shift();
        if (!next) {
          // Queue exhausted
          couplePlayingRef.current = false;
          setSpeaking(false);
          stopAudioLevelSimulation();
          clearModulationState();
          return;
        }

        decodeAndPlay(next.audio, {
          emotion: next.emotion,
          voiceParams: next.voice_params,
          durationMs: next.duration_ms,
          speaker: next.speaker,
          activeFactors: next.active_factors,
          onEnded: () => {
            // Small gap between couple utterances (natural turn-taking)
            if (coupleQueueRef.current.length > 0) {
              setTimeout(playNext, 120);
            } else {
              couplePlayingRef.current = false;
              setTimeout(clearModulationState, 500);
            }
          },
        });
      };

      playNext();
    },
    [
      enabled,
      stop,
      decodeAndPlay,
      startDurationCountdown,
      stopAudioLevelSimulation,
      clearModulationState,
    ]
  );

  // ---------------------------------------------------------------------------
  // Browser speech synthesis (fallback)
  // ---------------------------------------------------------------------------
  const speak = useCallback(
    (text: string) => {
      if (!enabled || typeof window === "undefined" || !window.speechSynthesis) return;
      if (!text.trim()) return;

      stop();

      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = lang;
      utterance.rate = rate;
      utterance.pitch = pitch;
      if (voiceRef.current) {
        utterance.voice = voiceRef.current;
      }

      utterance.onstart = () => {
        setSpeaking(true);
        startAudioLevelSimulation();
      };
      utterance.onend = () => {
        setSpeaking(false);
        stopAudioLevelSimulation();
      };
      utterance.onerror = () => {
        setSpeaking(false);
        stopAudioLevelSimulation();
      };

      window.speechSynthesis.speak(utterance);
    },
    [enabled, lang, rate, pitch, stop, startAudioLevelSimulation, stopAudioLevelSimulation]
  );

  // ---------------------------------------------------------------------------
  // Schedule / cancel fallback
  // ---------------------------------------------------------------------------
  const scheduleFallback = useCallback(
    (text: string, timeoutMs: number = 3000) => {
      logger.log(`[TTS] scheduleFallback | mode=${mode} | timeout=${timeoutMs}ms`);
      if (fallbackTimerRef.current) {
        clearTimeout(fallbackTimerRef.current);
      }

      if (mode === "browser") {
        logger.log("[TTS] Already in browser mode — speaking immediately");
        speak(text);
        return;
      }

      fallbackTimerRef.current = setTimeout(() => {
        if (!audioRef.current) {
          logger.warn(
            "[TTS] Fallback timer fired — ElevenLabs audio didn't arrive, using browser TTS"
          );
          speak(text);
        } else {
          logger.log(
            "[TTS] Fallback timer fired but ElevenLabs audio already playing — skipping"
          );
        }
        fallbackTimerRef.current = null;
      }, timeoutMs);
    },
    [mode, speak]
  );

  const cancelFallback = useCallback(() => {
    if (fallbackTimerRef.current) {
      clearTimeout(fallbackTimerRef.current);
      fallbackTimerRef.current = null;
    }
  }, []);

  // ---------------------------------------------------------------------------
  // Mode switching
  // ---------------------------------------------------------------------------
  const enableFallbackMode = useCallback(() => {
    setMode("browser");
    logger.warn("[TTS] SWITCHED to browser mode permanently (ElevenLabs fallback triggered)");
  }, []);

  // ---------------------------------------------------------------------------
  // Enable/disable
  // ---------------------------------------------------------------------------
  const handleSetEnabled = useCallback(
    (v: boolean) => {
      setEnabled(v);
      if (!v) {
        stop();
      }
    },
    [stop]
  );

  // ---------------------------------------------------------------------------
  // Return
  // ---------------------------------------------------------------------------
  return {
    // Legacy API (backward compatible)
    playAudio,
    // ТЗ-04 API
    playAudioMessage,
    playCoupleAudio,
    // Fallback
    speak,
    scheduleFallback,
    cancelFallback,
    enableFallbackMode,
    // Controls
    stop,
    speaking,
    enabled,
    setEnabled: handleSetEnabled,
    mode,
    // Avatar3D binding
    audioLevel,
    currentEmotion,
    currentVoiceParams,
    currentSpeaker,
    remainingDurationMs,
    activeFactors,
  };
}
