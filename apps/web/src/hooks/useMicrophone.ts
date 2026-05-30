"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { logger } from "@/lib/logger";
import {
  DEFAULT_VAD_CONFIG,
  vadInit,
  vadStep,
  type VadConfig,
  type VadState,
} from "@/lib/vad";
import type { MicErrorReason, MicrophonePermissionState, RecordingState } from "@/types";

/**
 * Pick the best MediaRecorder mime type the browser actually supports.
 * Safari has no webm/opus → fall back to mp4/aac, then to the browser
 * default. Shared by the push-to-talk recorder and the VAD per-utterance
 * recorder so both behave identically across browsers.
 */
function pickMimeType(): string {
  if (typeof MediaRecorder === "undefined") return "";
  return MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
    ? "audio/webm;codecs=opus"
    : MediaRecorder.isTypeSupported("audio/webm")
      ? "audio/webm"
      : MediaRecorder.isTypeSupported("audio/mp4;codecs=mp4a.40.2")
        ? "audio/mp4;codecs=mp4a.40.2"
        : MediaRecorder.isTypeSupported("audio/mp4")
          ? "audio/mp4"
          : "";
}

// Map a getUserMedia rejection (or pre-flight failure) to a specific
// MicErrorReason. Using the DOMException.name keeps us forward-compatible
// when browsers add new error names.
function classifyMicError(err: unknown): MicErrorReason {
  if (typeof window !== "undefined" && !window.isSecureContext) return "insecure";
  if (!(err instanceof DOMException)) return "unknown";
  switch (err.name) {
    case "NotAllowedError":
    case "PermissionDeniedError":
      return "denied";
    case "NotFoundError":
    case "DevicesNotFoundError":
      return "not_found";
    case "NotReadableError":
    case "TrackStartError":
      return "in_use";
    case "OverconstrainedError":
    case "ConstraintNotSatisfiedError":
      return "constraints";
    case "SecurityError":
      return "insecure";
    case "AbortError":
      return "aborted";
    default:
      return "unknown";
  }
}

const NOISE_GATE_THRESHOLD = 30; // dB threshold
const SILENCE_TIMEOUT_MS = 30_000; // 30 seconds auto-stop
const TIMESLICE_MS = 250; // chunk interval
const ANALYSER_FFT_SIZE = 256;

interface UseMicrophoneOptions {
  onChunk?: (chunk: Blob) => void;
  onSilenceTimeout?: () => void;
  /**
   * Continuous voice-activity mode (Phase 2 — cross-browser barge-in). When
   * you call `startVadListening()` the mic stays open and the hook watches the
   * audio energy: it fires `onSpeechStart` the instant the manager begins
   * talking (used to barge in over the AI) and `onSpeechEnd` with the captured
   * utterance blob once they stop (shipped to backend Whisper for the
   * transcript). This is the always-listening alternative to push-to-talk for
   * browsers without the Web Speech API (Safari/Firefox/Brave).
   */
  vad?: {
    /** Fired on speech onset — wire this to the barge-in interrupt. */
    onSpeechStart?: () => void;
    /** Fired on speech end with the recorded utterance (may be discarded if tiny). */
    onSpeechEnd?: (blob: Blob) => void;
    /** Override the default dB thresholds / timings. */
    config?: Partial<VadConfig>;
  };
}

interface UseMicrophoneReturn {
  recordingState: RecordingState;
  permissionState: MicrophonePermissionState;
  errorReason: MicErrorReason | null;
  audioLevel: number; // 0-100 scale for visual indicator
  isSupported: boolean;
  startRecording: () => Promise<boolean>;
  stopRecording: () => Promise<Blob | null>;
  requestPermission: () => Promise<boolean>;
  /** True while continuous VAD listening is active. */
  vadListening: boolean;
  /** Open the mic and start always-on voice-activity detection. */
  startVadListening: () => Promise<boolean>;
  /** Stop VAD listening and release the mic. */
  stopVadListening: () => void;
}

export function useMicrophone(
  options: UseMicrophoneOptions = {},
): UseMicrophoneReturn {
  const [recordingState, setRecordingState] = useState<RecordingState>("idle");
  const [permissionState, setPermissionState] =
    useState<MicrophonePermissionState>("prompt");
  const [errorReason, setErrorReason] = useState<MicErrorReason | null>(null);
  const [audioLevel, setAudioLevel] = useState(0);
  const [vadListening, setVadListening] = useState(false);
  const isSupported =
    typeof window !== "undefined" &&
    typeof navigator !== "undefined" &&
    !!navigator.mediaDevices?.getUserMedia &&
    typeof MediaRecorder !== "undefined";

  const optionsRef = useRef(options);
  optionsRef.current = options;

  // FIX 20: Guard against setState after unmount
  const mountedRef = useRef(true);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const animFrameRef = useRef<number>(0);
  const silenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSoundTimeRef = useRef<number>(Date.now());

  // ── VAD continuous-listening state (Phase 2) ──────────────────────────────
  // Separate from the push-to-talk recorder above so the two modes never share
  // a half-torn-down MediaRecorder. The stream/analyser stay open for the whole
  // listening session; a *fresh* MediaRecorder is spun up per utterance so each
  // emitted blob is a standalone-decodable file (you can't slice a webm mid
  // stream — only the first chunk carries the header).
  const vadStateRef = useRef<VadState>(vadInit());
  const vadAnimRef = useRef<number>(0);
  const vadRecorderRef = useRef<MediaRecorder | null>(null);
  const vadChunksRef = useRef<Blob[]>([]);
  // The recorder starts the moment any energy appears (so we don't clip the
  // first phoneme), but the utterance is only "committed" once VAD confirms a
  // real onset. An uncommitted recorder that fizzles (a transient) is discarded.
  const vadCommittedRef = useRef(false);
  const vadListeningRef = useRef(false);

  // Check permission state on mount & clean up listener on unmount
  const permStatusRef = useRef<PermissionStatus | null>(null);
  useEffect(() => {
    if (typeof navigator === "undefined" || !navigator.permissions) return;

    navigator.permissions
      .query({ name: "microphone" as PermissionName })
      .then((status) => {
        permStatusRef.current = status;
        setPermissionState(
          status.state === "granted"
            ? "granted"
            : status.state === "denied"
              ? "denied"
              : "prompt",
        );
        status.onchange = () => {
          setPermissionState(
            status.state === "granted"
              ? "granted"
              : status.state === "denied"
                ? "denied"
                : "prompt",
          );
        };
      })
      .catch(() => {
        // permissions API not supported, leave as prompt
      });

    return () => {
      if (permStatusRef.current) {
        permStatusRef.current.onchange = null;
        permStatusRef.current = null;
      }
    };
  }, []);

  // Cleanup on unmount — stop all media resources and prevent stale state updates
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      cancelAnimationFrame(animFrameRef.current);
      cancelAnimationFrame(vadAnimRef.current);
      vadListeningRef.current = false;
      if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
        mediaRecorderRef.current.stop();
        mediaRecorderRef.current = null;
      }
      if (vadRecorderRef.current && vadRecorderRef.current.state !== "inactive") {
        try { vadRecorderRef.current.stop(); } catch { /* noop */ }
        vadRecorderRef.current = null;
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
      }
      if (audioContextRef.current) {
        audioContextRef.current.close().catch(() => {});
        audioContextRef.current = null;
      }
      analyserRef.current = null;
    };
  }, []);

  const computeAudioLevel = useCallback(() => {
    const analyser = analyserRef.current;
    if (!analyser || !mountedRef.current) return undefined;

    const dataArray = new Uint8Array(analyser.frequencyBinCount);
    analyser.getByteFrequencyData(dataArray);

    // Compute RMS-like value from frequency data
    let sum = 0;
    for (let i = 0; i < dataArray.length; i++) {
      sum += dataArray[i];
    }
    const avg = sum / dataArray.length;

    // Convert to 0-100 scale (byte values are 0-255)
    const level = Math.min(100, Math.round((avg / 255) * 100 * 2));
    setAudioLevel(level);

    // Compute dB for noise gate
    const rms =
      Math.sqrt(
        dataArray.reduce((s, v) => s + (v / 255) * (v / 255), 0) /
          dataArray.length,
      ) || 0.0001;
    const dB = 20 * Math.log10(rms);

    return { level, dB };
  }, []);

  const monitorAudio = useCallback(() => {
    const result = computeAudioLevel();
    if (result && result.dB >= -((100 - NOISE_GATE_THRESHOLD) / 100) * 50) {
      lastSoundTimeRef.current = Date.now();
    }

    // Check silence timeout. Defence-in-depth (audit Pattern 2 #7):
    // we both invoke the consumer callback *and* hard-stop the recorder.
    // Earlier the hook only fired the callback and trusted the consumer
    // to call stopRecording() — if they forgot, the mic stayed open and
    // streamed silent chunks indefinitely. Now the recorder always stops
    // on its own, the callback is informational.
    const silenceDuration = Date.now() - lastSoundTimeRef.current;
    if (silenceDuration >= SILENCE_TIMEOUT_MS) {
      optionsRef.current.onSilenceTimeout?.();
      const mr = mediaRecorderRef.current;
      if (mr && mr.state !== "inactive") {
        try { mr.stop(); } catch { /* already stopping */ }
      }
      // Belt: also drop tracks immediately so the OS-level mic indicator
      // (browser tray) goes away even if `mr.stop()` is async.
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
      }
      return; // Stop monitoring
    }

    animFrameRef.current = requestAnimationFrame(monitorAudio);
  }, [computeAudioLevel]);

  const requestPermission = useCallback(async (): Promise<boolean> => {
    if (typeof window !== "undefined" && !window.isSecureContext) {
      setPermissionState("error");
      setErrorReason("insecure");
      return false;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((t) => t.stop());
      setPermissionState("granted");
      setErrorReason(null);
      return true;
    } catch (err) {
      const reason = classifyMicError(err);
      logger.error("[useMicrophone] requestPermission failed:", { reason, err });
      setPermissionState(reason === "denied" ? "denied" : "error");
      setErrorReason(reason);
      return false;
    }
  }, []);

  const startRecording = useCallback(async () => {
    if (!isSupported) {
      setPermissionState("error");
      setErrorReason("unsupported");
      return false;
    }
    if (typeof window !== "undefined" && !window.isSecureContext) {
      setPermissionState("error");
      setErrorReason("insecure");
      return false;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      streamRef.current = stream;
      setPermissionState("granted");
      setErrorReason(null);

      // Detect mid-session permission revoke / device unplug. Without
      // this listener we'd stay in "recording" forever sending empty
      // chunks while the user thought we were listening.
      stream.getTracks().forEach((track) => {
        track.onended = () => {
          logger.warn("[useMicrophone] track ended unexpectedly (unplug/revoke)");
          if (mountedRef.current) {
            setRecordingState("idle");
            setAudioLevel(0);
            setErrorReason("not_found");
          }
        };
      });

      // Set up AnalyserNode for audio level monitoring. Use webkit
      // fallback for older iOS Safari (<14.1).
      const Ctor: typeof AudioContext =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext ||
        AudioContext;
      const audioContext = new Ctor();
      // iOS Safari starts contexts in "suspended" state — must resume
      // explicitly or audioLevel stays at 0.
      if (audioContext.state === "suspended") {
        audioContext.resume().catch(() => {});
      }
      audioContextRef.current = audioContext;
      const source = audioContext.createMediaStreamSource(stream);
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = ANALYSER_FFT_SIZE;
      analyser.smoothingTimeConstant = 0.8;
      source.connect(analyser);
      analyserRef.current = analyser;

      // Set up MediaRecorder. Safari doesn't support webm/opus —
      // fall back to mp4/aac and finally to default (browser-chosen).
      const mimeType = pickMimeType();

      const mediaRecorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          // Check noise gate: only forward chunks above threshold
          const result = computeAudioLevel();
          const aboveGate =
            !result ||
            result.dB >= -((100 - NOISE_GATE_THRESHOLD) / 100) * 50;

          chunksRef.current.push(event.data);

          if (aboveGate) {
            optionsRef.current.onChunk?.(event.data);
          }
        }
      };

      mediaRecorder.onerror = () => {
        setRecordingState("idle");
      };

      chunksRef.current = [];
      mediaRecorder.start(TIMESLICE_MS);
      mediaRecorderRef.current = mediaRecorder;
      lastSoundTimeRef.current = Date.now();
      setRecordingState("recording");

      // Start audio monitoring loop
      animFrameRef.current = requestAnimationFrame(monitorAudio);
      return true;
    } catch (err) {
      const reason = classifyMicError(err);
      logger.error("[useMicrophone] startRecording failed:", { reason, err });
      setPermissionState(reason === "denied" ? "denied" : "error");
      setErrorReason(reason);
      setRecordingState("idle");
      return false;
    }
  }, [computeAudioLevel, isSupported, monitorAudio]);

  const stopRecording = useCallback((): Promise<Blob | null> => {
    return new Promise((resolve) => {
      cancelAnimationFrame(animFrameRef.current);
      if (silenceTimerRef.current) {
        clearTimeout(silenceTimerRef.current);
        silenceTimerRef.current = null;
      }

      const mediaRecorder = mediaRecorderRef.current;
      if (!mediaRecorder || mediaRecorder.state === "inactive") {
        setRecordingState("idle");
        setAudioLevel(0);
        resolve(null);
        return;
      }

      // Listen for the final dataavailable event before building Blob
      mediaRecorder.addEventListener("stop", () => {
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        chunksRef.current = [];

        // Stop all tracks
        if (streamRef.current) {
          streamRef.current.getTracks().forEach((track) => track.stop());
          streamRef.current = null;
        }

        // Close audio context
        if (audioContextRef.current) {
          audioContextRef.current.close().catch(() => {});
          audioContextRef.current = null;
        }
        analyserRef.current = null;

        setRecordingState("processing");
        setAudioLevel(0);

        // Reset to idle after a moment
        setTimeout(() => {
          if (mountedRef.current) setRecordingState("idle");
        }, 100);

        resolve(blob);
      }, { once: true });

      mediaRecorder.stop();
      mediaRecorderRef.current = null;
    });
  }, []);

  // ── VAD continuous listening (Phase 2: cross-browser barge-in) ────────────

  // Tear down any in-flight per-utterance recorder without emitting a blob.
  // Used for transients (energy that never became a real onset) and on stop.
  const discardVadUtterance = useCallback(() => {
    const mr = vadRecorderRef.current;
    vadRecorderRef.current = null;
    vadCommittedRef.current = false;
    vadChunksRef.current = [];
    if (mr && mr.state !== "inactive") {
      try { mr.stop(); } catch { /* already stopping */ }
    }
  }, []);

  // Start a fresh recorder for the current utterance. Begins at first energy so
  // the leading phoneme isn't clipped; the blob is only delivered if the
  // utterance is committed (see monitorVad).
  const startVadUtterance = useCallback(() => {
    const stream = streamRef.current;
    if (!stream || vadRecorderRef.current) return;
    const mimeType = pickMimeType();
    let mr: MediaRecorder;
    try {
      mr = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
    } catch {
      return; // recorder unavailable — VAD onset/end events still fire for barge-in
    }
    vadChunksRef.current = [];
    mr.ondataavailable = (event) => {
      if (event.data.size > 0) vadChunksRef.current.push(event.data);
    };
    try {
      mr.start();
    } catch {
      return;
    }
    vadRecorderRef.current = mr;
  }, []);

  // Stop the current utterance recorder and, if committed, hand the assembled
  // blob to onSpeechEnd. Listening continues for the next utterance.
  const finishVadUtterance = useCallback(() => {
    const mr = vadRecorderRef.current;
    const committed = vadCommittedRef.current;
    vadRecorderRef.current = null;
    vadCommittedRef.current = false;
    if (!mr || mr.state === "inactive") {
      vadChunksRef.current = [];
      return;
    }
    mr.addEventListener(
      "stop",
      () => {
        const blob = new Blob(vadChunksRef.current, {
          type: mr.mimeType || "audio/webm",
        });
        vadChunksRef.current = [];
        if (committed && blob.size > 0) {
          optionsRef.current.vad?.onSpeechEnd?.(blob);
        }
      },
      { once: true },
    );
    try { mr.stop(); } catch { /* already stopping */ }
  }, []);

  const monitorVad = useCallback(() => {
    if (!vadListeningRef.current || !mountedRef.current) return;
    const cfg: VadConfig = { ...DEFAULT_VAD_CONFIG, ...optionsRef.current.vad?.config };
    const result = computeAudioLevel();
    if (result) {
      const now =
        typeof performance !== "undefined" ? performance.now() : Date.now();
      const above = result.dB >= cfg.onsetThresholdDb;

      // Begin capturing at the first hint of energy so the onset isn't clipped.
      if (above && !vadRecorderRef.current) startVadUtterance();

      const { next, event } = vadStep(vadStateRef.current, result.dB, now, cfg);
      vadStateRef.current = next;

      if (event === "onset") {
        vadCommittedRef.current = true;
        optionsRef.current.vad?.onSpeechStart?.();
      } else if (event === "end") {
        finishVadUtterance();
      } else if (
        // A candidate recorder that never reached onset (transient) — drop it.
        vadRecorderRef.current &&
        !vadCommittedRef.current &&
        next.phase === "silence" &&
        next.aboveSinceTs === null
      ) {
        discardVadUtterance();
      }
    }
    vadAnimRef.current = requestAnimationFrame(monitorVad);
  }, [computeAudioLevel, startVadUtterance, finishVadUtterance, discardVadUtterance]);

  const startVadListening = useCallback(async (): Promise<boolean> => {
    if (!isSupported) {
      setErrorReason("unsupported");
      return false;
    }
    if (typeof window !== "undefined" && !window.isSecureContext) {
      setErrorReason("insecure");
      return false;
    }
    if (vadListeningRef.current) return true; // idempotent
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      streamRef.current = stream;
      setPermissionState("granted");
      setErrorReason(null);

      stream.getTracks().forEach((track) => {
        track.onended = () => {
          logger.warn("[useMicrophone] VAD track ended (unplug/revoke)");
          if (mountedRef.current) {
            setErrorReason("not_found");
          }
        };
      });

      const Ctor: typeof AudioContext =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext ||
        AudioContext;
      const audioContext = new Ctor();
      if (audioContext.state === "suspended") {
        audioContext.resume().catch(() => {});
      }
      audioContextRef.current = audioContext;
      const source = audioContext.createMediaStreamSource(stream);
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = ANALYSER_FFT_SIZE;
      analyser.smoothingTimeConstant = 0.8;
      source.connect(analyser);
      analyserRef.current = analyser;

      vadStateRef.current = vadInit();
      vadCommittedRef.current = false;
      vadChunksRef.current = [];
      vadListeningRef.current = true;
      setVadListening(true);
      vadAnimRef.current = requestAnimationFrame(monitorVad);
      return true;
    } catch (err) {
      const reason = classifyMicError(err);
      logger.error("[useMicrophone] startVadListening failed:", { reason, err });
      setPermissionState(reason === "denied" ? "denied" : "error");
      setErrorReason(reason);
      vadListeningRef.current = false;
      setVadListening(false);
      return false;
    }
  }, [isSupported, monitorVad]);

  const stopVadListening = useCallback(() => {
    vadListeningRef.current = false;
    cancelAnimationFrame(vadAnimRef.current);
    discardVadUtterance();
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }
    analyserRef.current = null;
    vadStateRef.current = vadInit();
    setAudioLevel(0);
    setVadListening(false);
  }, [discardVadUtterance]);

  return {
    recordingState,
    permissionState,
    errorReason,
    audioLevel,
    isSupported,
    startRecording,
    stopRecording,
    requestPermission,
    vadListening,
    startVadListening,
    stopVadListening,
  };
}
