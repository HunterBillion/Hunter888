"use client";

/**
 * `/training/[id]/call` — full-screen "live call" view.
 *
 * 2026-04-21 REWRITE: Call page is now architecturally self-sufficient.
 * Previously it was a decorative shell that simulated audioLevel with
 * random noise and relied on the sibling chat page being mounted to
 * actually run WebSocket/TTS/STT. That architecture meant landing on
 * /call directly (e.g. from a scenario card) produced a call UI with
 * no audio, no interaction, and a hangup that routed back to chat.
 *
 * This implementation:
 *   - Verifies session_mode == "call" on mount; redirects to /training/[id]
 *     chat view if the session is not a call session.
 *   - Owns its own useWebSocket, useTTS, useSpeechRecognition pipeline.
 *   - Handles the call-relevant subset of WS events:
 *       session.started | tts.audio | character.response | session.ended.
 *   - Sends user speech transcripts as message events to the backend.
 *   - Real audioLevel from useTTS (no more fake pulse).
 *   - Hangup posts /training/sessions/{id}/end and navigates directly to
 *     /results/{id} (no intermediate chat-page redirect hop).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useSessionStore } from "@/stores/useSessionStore";
import { PhoneCallMode } from "@/components/training/phone/PhoneCallMode";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useTTS } from "@/hooks/useTTS";
import { useSpeechRecognition } from "@/hooks/useSpeechRecognition";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";
import type { EmotionState, WSMessage } from "@/types";
import type { ClientCardData } from "@/components/training/ClientCard";

interface SessionMeta {
  character_name?: string;
  scenario_title?: string;
  custom_bg_noise?: string | null;
  custom_params?: { bg_noise?: string | null; session_mode?: string } | null;
}

export default function TrainingCallPage() {
  const router = useRouter();
  const params = useParams();
  const searchParams = useSearchParams();
  const id = (Array.isArray(params?.id) ? params?.id[0] : params?.id) as string;

  const s = useSessionStore();

  const [sceneBg, setSceneBg] = useState<string | null>(
    searchParams?.get("bg") || null,
  );
  const [muted, setMuted] = useState(false);
  const [speakerOn, setSpeakerOn] = useState(true);
  const [modeOk, setModeOk] = useState<boolean | null>(null); // null = checking
  const elapsedTickerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const endInFlightRef = useRef(false);
  const currentSessionIdRef = useRef<string>(id);

  // --- TTS (plays backend mp3, exposes real audioLevel) -------------------
  const tts = useTTS({ lang: "ru-RU", rate: 0.95, pitch: 1.0 });

  // --- STT (continuous, forwards recognized text to WS) -------------------
  const sttSendRef = useRef<((text: string) => void) | null>(null);
  const stt = useSpeechRecognition({
    lang: "ru-RU",
    onResult: (text) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      sttSendRef.current?.(trimmed);
    },
  });

  // --- Mount guard: verify session_mode, hydrate store --------------------
  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    (async () => {
      try {
        const meta = await api.get<SessionMeta>(`/training/sessions/${id}`);
        const sessionMode =
          meta?.custom_params?.session_mode || "chat";
        if (sessionMode !== "call") {
          // Session created as chat — call UI would be broken. Redirect.
          logger.warn(
            `[call] session ${id} is mode="${sessionMode}", redirecting to chat view`,
          );
          if (!cancelled) router.replace(`/training/${id}`);
          return;
        }
        if (cancelled) return;
        if (meta?.character_name) s.setCharacterName(meta.character_name);
        if (meta?.scenario_title) s.setScenarioTitle(meta.scenario_title);
        const bg =
          meta?.custom_bg_noise || meta?.custom_params?.bg_noise || null;
        if (bg) setSceneBg(bg);
        setModeOk(true);
      } catch (err) {
        logger.error("[call] failed to verify session mode", err);
        // Fail-open: render call UI anyway; backend 404/forbidden will close WS.
        if (!cancelled) setModeOk(true);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // --- Elapsed ticker -----------------------------------------------------
  useEffect(() => {
    if (elapsedTickerRef.current) clearInterval(elapsedTickerRef.current);
    elapsedTickerRef.current = setInterval(() => {
      useSessionStore.getState().tickElapsed();
    }, 1000);
    return () => {
      if (elapsedTickerRef.current) clearInterval(elapsedTickerRef.current);
    };
  }, [id]);

  // --- WebSocket ----------------------------------------------------------
  const lastSeqNum = s.messages.length > 0
    ? s.messages.reduce((max, m) => Math.max(max, m.sequenceNumber ?? 0), 0) || null
    : null;

  const { sendMessage, connectionState } = useWebSocket({
    sessionId: s.sessionId || id || null,
    lastSequenceNumber: lastSeqNum,
    autoConnect: modeOk === true,
    onMessage: (data: WSMessage) => {
      if (!data.data || typeof data.data !== "object") data.data = {};
      switch (data.type) {
        case "auth.success":
        case "session.ready":
          break;

        case "session.started": {
          if (data.data.session_id) {
            currentSessionIdRef.current = data.data.session_id as string;
          }
          if (data.data.character_name)
            s.setCharacterName(data.data.character_name as string);
          if (data.data.initial_emotion)
            s.setEmotion(data.data.initial_emotion as EmotionState);
          if (data.data.scenario_title)
            s.setScenarioTitle(data.data.scenario_title as string);
          if (data.data.client_card) {
            s.setClientCard(data.data.client_card as ClientCardData);
            s.setSessionState("briefing");
          } else {
            s.setSessionState("ready");
          }
          break;
        }

        case "tts.audio":
          // Real audio from backend (navy TTS or ElevenLabs). useTTS plays
          // it and updates audioLevel for the avatar animation.
          tts.playAudioMessage(
            data.data as unknown as Parameters<typeof tts.playAudioMessage>[0],
          );
          break;

        case "tts.couple_audio":
          tts.playCoupleAudio(
            data.data as unknown as Parameters<typeof tts.playCoupleAudio>[0],
          );
          break;

        case "character.response": {
          const text = (data.data.text as string) || "";
          if (text) tts.scheduleFallback(text, 2500);
          if (data.data.emotion) s.setEmotion(data.data.emotion as EmotionState);
          break;
        }

        case "emotion.changed":
          if (data.data.emotion)
            s.setEmotion(data.data.emotion as EmotionState);
          break;

        case "session.ended":
          // Navigate to results on clean backend close.
          tts.stop();
          stt.stopListening();
          endInFlightRef.current = true;
          router.push(`/results/${currentSessionIdRef.current || id}`);
          break;

        case "error": {
          const code = (data.data.code as string) || "";
          if (code === "session_hijacked" || code === "session_conflict") {
            logger.warn("[call] session error", data.data);
            router.replace(`/training/${id}`);
          }
          break;
        }

        default:
          break;
      }
    },
  });

  // Wire up STT.onResult → WS sendMessage
  useEffect(() => {
    sttSendRef.current = (text: string) => {
      if (!text || connectionState !== "connected") return;
      sendMessage({ type: "user.message", data: { content: text } });
    };
  }, [sendMessage, connectionState]);

  // --- STT start/stop bound to mute state + mode readiness ---------------
  useEffect(() => {
    if (modeOk !== true) return;
    if (connectionState !== "connected") return;
    if (muted) {
      stt.stopListening();
      return;
    }
    if (!stt.isSupported) return;
    // Start listening when TTS is idle — prevents feedback loop where mic
    // picks up the character's own voice from the speaker.
    if (!tts.speaking) stt.startListening();
    else stt.stopListening();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modeOk, connectionState, muted, tts.speaking]);

  // --- Speaker toggle — pauses/resumes TTS playback ----------------------
  useEffect(() => {
    tts.setEnabled(speakerOn);
  }, [speakerOn, tts]);

  // --- Hangup: end session + navigate directly to results ---------------
  const onHangup = useCallback(async () => {
    if (endInFlightRef.current) return;
    endInFlightRef.current = true;
    tts.stop();
    stt.stopListening();
    const sid = currentSessionIdRef.current || id;
    try {
      await api.post(`/training/sessions/${sid}/end`, {});
    } catch (err) {
      logger.warn("[call] end POST failed (may already be ended)", err);
    }
    router.push(`/results/${sid}`);
  }, [id, router, tts, stt]);

  // Still loading mode guard
  if (modeOk === null) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-black text-white/60 text-sm">
        Подключаемся к звонку…
      </div>
    );
  }

  return (
    <PhoneCallMode
      characterName={s.characterName || "Клиент"}
      emotion={s.emotion as EmotionState}
      sessionState={s.sessionState}
      audioLevel={tts.audioLevel}
      elapsed={s.elapsed}
      muted={muted}
      speakerOn={speakerOn}
      sceneId={sceneBg}
      clientCard={s.clientCard}
      onToggleMute={() => setMuted((m) => !m)}
      onToggleSpeaker={() => setSpeakerOn((v) => !v)}
      onHangup={onHangup}
    />
  );
}
