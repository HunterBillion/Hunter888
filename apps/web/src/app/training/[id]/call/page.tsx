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
import { Mic, MicOff } from "lucide-react";
import { useSessionStore } from "@/stores/useSessionStore";
import { PhoneCallMode } from "@/components/training/phone/PhoneCallMode";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useTTS } from "@/hooks/useTTS";
import { useSpeechRecognition } from "@/hooks/useSpeechRecognition";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";
import type { EmotionState, WSMessage } from "@/types";
import type { ClientCardData } from "@/components/training/ClientCard";

interface SessionMetaInner {
  custom_params?: { bg_noise?: string | null; session_mode?: string } | null;
  client_story_id?: string | null;
}
interface SessionMeta {
  // Primary shape: wrapped SessionResultResponse
  session?: SessionMetaInner;
  client_card?: { name?: string } | null;
  // Legacy fields that some callers expect at top level — accept either.
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
    // eslint-disable-next-line no-console
    console.log("[CALL] mount — id=", id);
    let cancelled = false;
    (async () => {
      try {
        const meta = await api.get<SessionMeta>(`/training/sessions/${id}`);
        // eslint-disable-next-line no-console
        console.log("[CALL] meta fetched", meta);
        // The endpoint returns SessionResultResponse with the real session
        // nested under `session.custom_params`. Some legacy paths inline
        // the same fields at top level — tolerate both.
        const cp =
          meta?.session?.custom_params || meta?.custom_params || null;
        const sessionMode = cp?.session_mode;
        // Fail-OPEN: only redirect when we have an EXPLICIT "chat" signal.
        // If session_mode is missing/undefined we render the call UI —
        // previous fail-closed logic broke freshly-created call sessions
        // whose response shape didn't include session_mode at top level.
        if (sessionMode === "chat") {
          logger.warn(
            `[call] session ${id} is mode="chat", redirecting to chat view`,
          );
          if (!cancelled) router.replace(`/training/${id}`);
          return;
        }
        if (cancelled) return;
        if (meta?.character_name) s.setCharacterName(meta.character_name);
        if (meta?.scenario_title) s.setScenarioTitle(meta.scenario_title);
        const bg =
          meta?.custom_bg_noise ||
          meta?.custom_params?.bg_noise ||
          meta?.session?.custom_params?.bg_noise ||
          null;
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

  // --- Speaker/volume wiring ----------------------------------------------
  // 2026-04-21: Speaker button now opens a volume slider popover (inside
  // PhoneCallMode). No longer maps speakerOn → presets — user controls
  // volume precisely via the slider. Initialise to a comfortable default
  // on first mount so the user hears TTS without pre-interacting.
  useEffect(() => {
    tts.setVolume(0.85);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // --- WebSocket ----------------------------------------------------------
  const lastSeqNum = s.messages.length > 0
    ? s.messages.reduce((max, m) => Math.max(max, m.sequenceNumber ?? 0), 0) || null
    : null;

  // URL id wins over zustand store. Store can hold a stale id from a
  // previous chat session — using it would connect WS to a dead session
  // and silently produce no TTS/STT.
  const { sendMessage, connectionState } = useWebSocket({
    sessionId: id || s.sessionId || null,
    lastSequenceNumber: lastSeqNum,
    autoConnect: modeOk === true,
    onMessage: (data: WSMessage) => {
      if (!data.data || typeof data.data !== "object") data.data = {};
      // eslint-disable-next-line no-console
      console.log("[CALL]", data.type, data.data);
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

        case "tts.audio_chunk": {
          // Sentence-level TTS streaming. Backend splits multi-sentence
          // replies ("Алло... Кто это? Откуда у вас мой номер?") into one
          // chunk per sentence for faster first-audio (~1.5s vs 5-13s).
          // The chat page at /training/[id] handles this event AND renders
          // subtitles; the call page only needs audio — PhoneCallMode has
          // no chat-bubble UI. Queue chunks in sentence order and let
          // useTTS play them sequentially.
          //
          // Before this handler existed the call-mode heard nothing on
          // any multi-sentence reply — exact symptom of the 2026-04-21
          // incident: character.response came through, tts.audio never
          // did, user saw dead silence (journal #22 recurrence).
          tts.cancelFallback();
          const chunkAudio = data.data.audio_b64 as string | undefined;
          if (chunkAudio) {
            tts.queueAudioChunk({
              audio: chunkAudio,
              index: (data.data.sentence_index as number) ?? 0,
              isLast: Boolean(data.data.is_last),
            });
          }
          break;
        }

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

        // Script / coaching / scoring — previously only chat-view handled
        // these. Call-view was missing this info which is why "скрипт в
        // звонке" was entirely absent. Mirroring chat handlers (feature
        // parity) using the same Zustand store, so the UI renders from
        // the same source of truth.
        case "stage.update": {
          const d = data.data as Record<string, unknown>;
          s.setStageUpdate({
            stage_number: Number(d.stage_number ?? 1),
            stage_name: String(d.stage_name ?? ""),
            stage_label: String(d.stage_label ?? ""),
            total_stages: Number(d.total_stages ?? 7),
            stages_completed: (d.stages_completed as number[]) ?? [],
            stage_scores: (d.stage_scores as Record<string, number>) ?? {},
            confidence: typeof d.confidence === "number" ? d.confidence : 0,
          });
          break;
        }

        case "whisper.coaching": {
          const d = data.data as Record<string, unknown>;
          const msg = String(d.message ?? "");
          if (msg) {
            s.addWhisper({
              type: (d.type as "legal" | "emotion" | "stage" | "objection" | "transition") ?? "stage",
              message: msg,
              stage: d.stage ? String(d.stage) : "",
              priority: (d.priority as "low" | "medium" | "high") ?? "low",
              icon: d.icon ? String(d.icon) : "zap",
              timestamp: Date.now(),
            });
          }
          break;
        }

        case "score.hint": {
          const d = data.data as Record<string, unknown>;
          const num = (k: string) => Number(d[k] ?? 0);
          s.setRealtimeScores({
            script_adherence: num("script_adherence"),
            objection_handling: num("objection_handling"),
            communication: num("communication"),
            anti_patterns: num("anti_patterns"),
            result: num("result"),
            chain_traversal: num("chain_traversal"),
            trap_handling: num("trap_handling"),
            human_factor: num("human_factor"),
            realtime_estimate: num("realtime_estimate"),
            max_possible_realtime: num("max_possible_realtime"),
          });
          break;
        }

        case "session.ended":
          // Navigate to results on clean backend close.
          tts.stop();
          stt.stopListening();
          endInFlightRef.current = true;
          router.push(`/results/${currentSessionIdRef.current || id}`);
          break;

        case "error": {
          const code = (data.data.code as string) || "";
          // Hijack/conflict: do NOT auto-redirect to chat. The WS has
          // reconnect logic, and most hijacks in production are spurious
          // (React remount, fast-refresh, brief network blip). Kicking the
          // user to chat on every such event is how call-mode sessions
          // appeared to "vanish" for users. Log and rely on reconnect; if
          // it truly stays broken, the server closes the socket and the
          // user can leave manually via the hangup button.
          if (code === "session_hijacked" || code === "session_conflict") {
            logger.warn("[call] session takeover event (non-fatal)", data.data);
          } else {
            // Other errors (missing_field, rate_limit, scenario issues):
            // surface to console for diagnostics. Non-fatal; stay on call.
            logger.warn("[call] ws error", data.data);
          }
          break;
        }

        default:
          break;
      }
    },
  });

  // Wire up STT.onResult → WS sendMessage (text.message is the
  // canonical type; user.message is unknown to backend).
  useEffect(() => {
    sttSendRef.current = (text: string) => {
      if (!text || connectionState !== "connected") return;
      sendMessage({ type: "text.message", data: { content: text } });
    };
  }, [sendMessage, connectionState]);

  // Kick-start the session on WS ready. The chat flow sends
  // session.start with the REST-created session_id; backend resumes
  // and emits session.started/character.response/tts.audio. Without
  // this message the backend just idles after auth.success.
  const sessionStartSentRef = useRef(false);
  useEffect(() => {
    if (connectionState !== "connected") {
      sessionStartSentRef.current = false;
      return;
    }
    if (sessionStartSentRef.current) return;
    if (!id) return;
    sessionStartSentRef.current = true;
    // eslint-disable-next-line no-console
    console.log("[CALL] sending session.start");
    sendMessage({ type: "session.start", data: { session_id: id } });
  }, [connectionState, id, sendMessage]);

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

  // --- Hangup: navigate IMMEDIATELY, cleanup in background ---------------
  // Navigate first so the button always responds even if TTS/STT/backend
  // throw. Cleanup runs as fire-and-forget — the results page reloads
  // session state from the server anyway, so late-arriving errors are safe.
  const onHangup = useCallback(() => {
    if (endInFlightRef.current) return;
    endInFlightRef.current = true;
    const sid = currentSessionIdRef.current || id;
    // Immediate navigation — guaranteed response to the click.
    router.push(`/results/${sid}`);
    // Best-effort cleanup in the background.
    (async () => {
      try { tts.stop(); } catch { /* noop */ }
      try { stt.stopListening(); } catch { /* noop */ }
      try {
        await api.post(`/training/sessions/${sid}/end`, {});
      } catch (err) {
        logger.warn("[call] end POST failed (may already be ended)", err);
      }
    })();
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
    <>
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
        volume={tts.volume}
        onVolumeChange={tts.setVolume}
        stage={{
          current: s.currentStage || 1,
          label: s.stageLabel || undefined,
          completed: s.stagesCompleted || [],
          total: s.totalStages || 7,
        }}
        coachingHint={
          s.whispers && s.whispers.length > 0
            ? {
                message: s.whispers[0].message,
                priority: s.whispers[0].priority,
                icon: s.whispers[0].icon,
                type: s.whispers[0].type,
              }
            : null
        }
        micSlot={
          <button
            type="button"
            aria-label={stt.status === "listening" ? "Остановить запись" : "Начать запись"}
            onClick={() => {
              if (stt.status === "listening") {
                stt.stopListening();
              } else {
                // Pause TTS so we don't record our own output into STT.
                try { tts.stop(); } catch { /* noop */ }
                stt.startListening();
              }
            }}
            className={[
              "flex h-16 w-16 items-center justify-center rounded-full transition-all",
              "ring-2 ring-white/10 backdrop-blur-sm",
              stt.status === "listening"
                ? "bg-red-500/90 hover:bg-red-500 scale-110"
                : "bg-white/10 hover:bg-white/20",
            ].join(" ")}
            style={{
              boxShadow:
                stt.status === "listening"
                  ? `0 0 ${20 + stt.audioLevel * 40}px rgba(239, 68, 68, ${0.5 + stt.audioLevel * 0.5})`
                  : "none",
            }}
          >
            {stt.status === "listening" ? (
              <MicOff size={28} className="text-white" />
            ) : (
              <Mic size={28} className="text-white/90" />
            )}
          </button>
        }
      />
      {/*
        Autoplay-unlock overlay. Browsers (Chrome/Safari strict, iOS
        Safari especially) block HTMLAudioElement.play() that isn't
        directly inside a user-gesture callback. The click that routed
        to this page counts, but by the time WS connects and the first
        TTS chunk arrives, activation may have expired.
        useTTS.needsAudioUnlock flips to true whenever audio.play()
        rejects with NotAllowedError/AbortError. We then render a
        full-screen button whose onClick calls tts.unlock() — that call
        stack is a user gesture, so the queued audio replays cleanly.
      */}
      {tts.needsAudioUnlock && (
        <div
          className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/80 backdrop-blur-sm"
          onClick={tts.unlock}
          role="button"
          tabIndex={0}
        >
          <div className="flex max-w-sm flex-col items-center gap-4 rounded-2xl bg-white/10 px-8 py-10 text-center shadow-2xl">
            <div className="text-6xl">🔊</div>
            <div className="text-xl font-semibold text-white">
              Нажмите для включения звука
            </div>
            <div className="text-sm text-white/70">
              Браузер заблокировал автовоспроизведение. Тапните где-угодно —
              голос клиента зазвучит немедленно.
            </div>
          </div>
        </div>
      )}
    </>
  );
}
