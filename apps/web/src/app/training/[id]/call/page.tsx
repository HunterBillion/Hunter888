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
  // 2026-04-22: explicit user-gesture gate before WS connects. Browsers
  // (especially iOS Safari + strict Chrome) refuse audio playback unless
  // a user gesture happened on the page. The previous flow was: open URL
  // → WS auto-connects → TTS arrives → audio.play() rejected silently
  // → user heard nothing for the first 30-60s until they happened to
  // click somewhere on the page. Now: a "Принять звонок" gate plays a
  // silent audio buffer in the click handler, which unlocks both
  // HTMLAudioElement and AudioContext for the rest of the session.
  const [callAccepted, setCallAccepted] = useState(false);
  // 2026-04-22 fallback text input: call mode was voice-only and users
  // with broken mic / denied permission / unsupported browser had NO
  // way to send a message. Chat worked because you can type there.
  // Now call has an always-visible text input as a peer to push-to-talk.
  const [textInput, setTextInput] = useState("");
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

  // 2026-04-22: procedural ringback + pickup-click on call connect.
  // Sells the "real call" feeling — instead of dead silence between
  // session.start and the first TTS, the user hears a single short ring
  // followed by a small click as if the AI just picked up the phone.
  // Pure Web Audio API: no audio files needed.
  const ringbackPlayedRef = useRef(false);
  useEffect(() => {
    if (modeOk !== true || ringbackPlayedRef.current) return;
    ringbackPlayedRef.current = true;
    if (typeof window === "undefined") return;
    const AC = (window.AudioContext ||
      (window as unknown as { webkitAudioContext?: typeof AudioContext })
        .webkitAudioContext) as typeof AudioContext | undefined;
    if (!AC) return;
    let ctx: AudioContext;
    try { ctx = new AC(); } catch { return; }
    // RU/EU dial-tone is 425Hz. Single ~600ms tone, then a 90ms gap, then
    // a soft "click" that simulates the receiver lifting.
    const t0 = ctx.currentTime + 0.05;
    const ring = ctx.createOscillator();
    ring.type = "sine";
    ring.frequency.value = 425;
    const ringGain = ctx.createGain();
    ringGain.gain.setValueAtTime(0, t0);
    ringGain.gain.linearRampToValueAtTime(0.18, t0 + 0.04);
    ringGain.gain.setValueAtTime(0.18, t0 + 0.6);
    ringGain.gain.linearRampToValueAtTime(0, t0 + 0.65);
    ring.connect(ringGain).connect(ctx.destination);
    ring.start(t0); ring.stop(t0 + 0.7);
    // Click: short noise burst with a steep envelope.
    const t1 = t0 + 0.78;
    const clickBuf = ctx.createBuffer(1, ctx.sampleRate * 0.05, ctx.sampleRate);
    const cd = clickBuf.getChannelData(0);
    for (let i = 0; i < cd.length; i++) cd[i] = (Math.random() * 2 - 1) * (1 - i / cd.length);
    const click = ctx.createBufferSource();
    click.buffer = clickBuf;
    const clickGain = ctx.createGain();
    clickGain.gain.value = 0.12;
    click.connect(clickGain).connect(ctx.destination);
    click.start(t1);
    // Browsers suspend until gesture — try resume.
    if (ctx.state === "suspended") ctx.resume().catch(() => {});
    // Cleanup the context after sounds done so we don't leak.
    setTimeout(() => { try { ctx.close(); } catch { /* ignore */ } }, 1500);
  }, [modeOk]);

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
    // 2026-04-22: gate WS connect behind explicit user gesture (callAccepted).
    // The accept button plays a silent audio buffer in its click handler,
    // which unlocks HTMLAudioElement permanently for the page. Without this
    // gate, TTS audio arrived before any gesture and was silently dropped.
    autoConnect: modeOk === true && callAccepted,
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

        case "tts.audio": {
          // 2026-04-22 FIELD-NAME FIX: backend sends `audio_b64` but
          // playAudioMessage expects `audio`. Previously this passed
          // data.data directly, so msg.audio was undefined → atob('')
          // → InvalidCharacterError → silent TTS. Chat page had the
          // correct mapping; call page was missed during refactor.
          tts.cancelFallback();
          const audioB64 = data.data.audio_b64 as string | undefined;
          if (audioB64 && typeof audioB64 === "string" && audioB64.length > 0) {
            tts.playAudioMessage({
              audio: audioB64,
              emotion: data.data.emotion as EmotionState | undefined,
              voice_params: data.data.voice_params as
                | { stability: number; similarity_boost: number; style: number; speed: number }
                | undefined,
              duration_ms: data.data.duration_ms as number | undefined,
            });
          } else {
            console.warn("[CALL] tts.audio received but audio_b64 missing/empty", {
              has_field: "audio_b64" in (data.data as object),
              len: typeof audioB64 === "string" ? audioB64.length : null,
            });
          }
          break;
        }

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

        case "client.hangup": {
          // 2026-04-22: backend signals client hung up the phone (either
          // emotion FSM transitioned to "hangup" OR AI-content farewell
          // detected). Without this handler the call page kept playing the
          // farewell TTS and then sat there forever — backend's auto-end
          // task wouldn't redirect because we missed the session.ended that
          // followed. Now we wait for TTS of the farewell to finish, then
          // navigate to results immediately.
          const canContinue = Boolean(data.data.call_can_continue);
          logger.log("[call] client.hangup received", {
            reason: data.data.reason,
            canContinue,
          });
          if (!canContinue) {
            // Mark in-flight so the WebSocket close handler doesn't fire a
            // duplicate /end POST.
            endInFlightRef.current = true;
            // Wait ~3.5s so the goodbye TTS plays out, then redirect.
            setTimeout(() => {
              tts.stop();
              stt.stopListening();
              router.push(`/results/${currentSessionIdRef.current || id}`);
            }, 3500);
          }
          break;
        }

        case "error": {
          const code = (data.data.code as string) || "";
          // 2026-04-22: session_completed means backend rejected our
          // message because the session is already ended (auto-end after
          // farewell, or competing tab ended it). Redirect to results
          // instead of sitting on a dead call screen indefinitely.
          if (code === "session_completed") {
            logger.log("[call] session already completed → /results");
            endInFlightRef.current = true;
            router.push(`/results/${currentSessionIdRef.current || id}`);
            break;
          }
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

  // 2026-04-22 fallback sender: send current textInput as a plain text.message
  // with correct `content` key (same shape as chat page). Clears the box so
  // Enter-to-send feels responsive.
  //
  // 2026-04-22 (hotfix): this useCallback + the three const diagnostics
  // below were originally placed AFTER the `if (modeOk === null) return …`
  // early-return below. That violated Rules of Hooks — on the first render
  // (modeOk === null) the hooks didn't run, on the second render they did,
  // so React counted different hook totals between renders and threw
  // Minified React error #310 ("Rendered more hooks than during the
  // previous render"). Moving the hook above the early-return restores
  // a stable hook order across every render.
  const sendText = useCallback(() => {
    const trimmed = textInput.trim();
    if (!trimmed) return;
    if (connectionState !== "connected") {
      logger.warn("[call] cannot send text — WS not connected", { connectionState });
      return;
    }
    sendMessage({ type: "text.message", data: { content: trimmed } });
    setTextInput("");
  }, [textInput, connectionState, sendMessage]);

  // Still loading mode guard
  if (modeOk === null) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-black text-white/60 text-sm">
        Подключаемся к звонку…
      </div>
    );
  }

  // 2026-04-22: explicit user-gesture gate. Click "Принять звонок" plays a
  // silent audio buffer in the click handler (counts as gesture for
  // HTMLAudioElement) AND resumes any AudioContext that was created by
  // ambient noise / ringback. This guarantees TTS audio plays from the
  // very first reply instead of being silently dropped by autoplay policy.
  // Without this gate, users heard nothing for the first 30-60s until
  // they happened to click somewhere else on the page.
  if (!callAccepted) {
    return (
      <div
        className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-6 text-white"
        style={{
          background:
            "radial-gradient(ellipse at center, #2a1a4a 0%, #14091e 55%, #06030c 100%)",
        }}
      >
        <div className="text-7xl animate-pulse">📞</div>
        <div className="text-2xl font-semibold tracking-tight">
          Входящий звонок
        </div>
        <div className="text-sm text-white/60 max-w-sm text-center px-8">
          {s.characterName || "Клиент"} ждёт ответа
        </div>
        <button
          onClick={async () => {
            // 2026-04-22 (v3): aggressive multi-vector unlock. Previous
            // versions had Web Audio silent buffer + blob-URL HTMLAudioElement
            // but user still got silent TTS. Chrome's autoplay policy
            // requires MULTIPLE conditions:
            //   1) AudioContext unlocked via resume() in a gesture
            //   2) HTMLAudioElement.play() succeeded within gesture window
            //   3) Media engagement index sufficient
            // We hit all three here. Also: await the play promise so the
            // gesture frame stays alive until Chrome confirms unlock.
            console.log("[CALL] accept-click: running unlock sequence");
            try {
              // --- Vector 1: Web Audio API unlock ---
              const AC = (window.AudioContext ||
                (window as unknown as {
                  webkitAudioContext?: typeof AudioContext;
                }).webkitAudioContext) as typeof AudioContext | undefined;
              if (AC) {
                const ctx = new AC();
                if (ctx.state === "suspended") {
                  await ctx.resume().catch(() => {});
                }
                const buf = ctx.createBuffer(1, 1, 22050);
                const src = ctx.createBufferSource();
                src.buffer = buf;
                src.connect(ctx.destination);
                src.start(0);
                console.log("[CALL] unlock: AudioContext state =", ctx.state);
                // Keep context around for 500ms to satisfy media policy.
                setTimeout(() => { try { ctx.close(); } catch { /* */ } }, 500);
              }
              // --- Vector 2: HTMLAudioElement via blob URL ---
              // CSP allows blob: — data: was blocked. Valid silent 8kHz mono
              // PCM wav, 1 sample of silence. Using proper WAV headers.
              const silentWav = new Uint8Array([
                0x52, 0x49, 0x46, 0x46, 0x25, 0, 0, 0, 0x57, 0x41, 0x56, 0x45,
                0x66, 0x6d, 0x74, 0x20, 0x10, 0, 0, 0, 1, 0, 1, 0,
                0x40, 0x1f, 0, 0, 0x40, 0x1f, 0, 0, 1, 0, 8, 0,
                0x64, 0x61, 0x74, 0x61, 0x01, 0, 0, 0, 0x80,
              ]);
              const blob = new Blob([silentWav], { type: "audio/wav" });
              const url = URL.createObjectURL(blob);
              const a = new Audio(url);
              a.volume = 0.001; // not 0 — some browsers skip 0-volume plays
              try {
                await a.play();
                console.log("[CALL] unlock: HTMLAudio play() succeeded");
              } catch (e) {
                console.warn("[CALL] unlock: HTMLAudio play() failed:", e);
              }
              URL.revokeObjectURL(url);
              // --- Vector 3: also poke tts.unlock() if pending ---
              try { tts.unlock(); } catch { /* */ }
            } catch (e) {
              console.warn("[CALL] unlock sequence error:", e);
            }
            setCallAccepted(true);
          }}
          className="mt-4 flex items-center gap-3 rounded-full px-10 py-4 text-lg font-semibold text-white shadow-2xl transition active:scale-95"
          style={{
            background:
              "linear-gradient(135deg, #4f30b8 0%, #311573 50%, #1f0a52 100%)",
            boxShadow:
              "0 12px 40px rgba(49, 21, 115, 0.55), 0 0 0 1px rgba(255,255,255,0.08) inset",
          }}
        >
          <span className="text-2xl">📲</span>
          Принять звонок
        </button>
        <div className="text-xs text-white/40 px-8 text-center max-w-sm mt-2">
          Нажмите чтобы подключить звук — браузер требует жест пользователя
        </div>
      </div>
    );
  }

  // 2026-04-22 diagnostics banner: show on-screen warnings so user sees
  // the state of critical call-mode dependencies without opening DevTools.
  // Plain derived values (not hooks) — safe after the early-return.
  const sttSupported = stt.isSupported;
  const sttError = stt.status === "unsupported" || stt.status === "error";
  const wsDead = connectionState === "disconnected" || connectionState === "error";

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
            className="flex flex-col items-center gap-1.5"
          >
            <span
              className={[
                "flex h-16 w-16 items-center justify-center rounded-full transition-all duration-150 active:scale-95",
                stt.status === "listening" ? "bg-red-500/90" : "",
              ].join(" ")}
              style={{
                background:
                  stt.status === "listening"
                    ? "rgba(239,68,68,0.9)"
                    : "rgba(255,255,255,0.12)",
                color: "#fff",
                border: "1px solid rgba(255,255,255,0.18)",
                backdropFilter: "blur(8px)",
                boxShadow:
                  stt.status === "listening"
                    ? `0 0 ${20 + stt.audioLevel * 40}px rgba(239, 68, 68, ${0.5 + stt.audioLevel * 0.5})`
                    : "none",
              }}
            >
              {stt.status === "listening" ? (
                <MicOff size={26} />
              ) : (
                <Mic size={26} />
              )}
            </span>
            <span className="text-[10px] uppercase tracking-wider opacity-70">
              {stt.status === "listening" ? "Слушаю" : "Говорить"}
            </span>
          </button>
        }
      />

      {/*
        Diagnostics banner (2026-04-22). Shows on-screen why the call
        might feel silent without user having to open DevTools:
          - WS down: "Нет связи с сервером…"
          - STT unsupported/error: "Микрофон недоступен, пишите текстом"
          - tts still speaking: "Клиент говорит…" (info)
        Positioned below the teleprompter so it doesn't fight the avatar.
      */}
      {(wsDead || sttError || !sttSupported) && (
        <div className="pointer-events-none fixed top-[130px] left-0 right-0 z-30 flex justify-center px-4">
          <div className="rounded-full bg-amber-500/90 px-4 py-1.5 text-xs font-medium text-black shadow-lg">
            {wsDead
              ? "Нет связи с сервером — переподключаемся…"
              : !sttSupported
              ? "Этот браузер не поддерживает голос. Пишите текстом ниже."
              : "Микрофон недоступен. Нажмите значок ниже или печатайте текстом."}
          </div>
        </div>
      )}

      {/*
        Text-input fallback (2026-04-22). Always visible at the bottom of
        the call view. Works exactly like chat: type, Enter / кнопка ▶ —
        sends `text.message` WS event with `content` key (same contract
        as chat page). User gets a reliable way to talk even when
        microphone is broken / denied / browser doesn't support STT.
        Push-to-talk mic remains in the control row for voice users.
      */}
      <div className="fixed bottom-0 left-0 right-0 z-20 flex justify-center bg-gradient-to-t from-black/70 to-transparent px-4 pb-3 pt-10">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            sendText();
          }}
          className="flex w-full max-w-lg items-center gap-2 rounded-full bg-black/50 px-4 py-2 ring-1 ring-white/10 backdrop-blur-md"
        >
          <input
            type="text"
            value={textInput}
            onChange={(e) => setTextInput(e.target.value)}
            placeholder="Или напишите текстом…"
            aria-label="Сообщение клиенту текстом"
            className="flex-1 bg-transparent text-sm text-white placeholder:text-white/40 outline-none"
            disabled={connectionState !== "connected"}
          />
          <button
            type="submit"
            disabled={!textInput.trim() || connectionState !== "connected"}
            className="flex h-8 w-8 items-center justify-center rounded-full bg-white/15 text-white transition-opacity hover:bg-white/25 disabled:cursor-not-allowed disabled:opacity-30"
            aria-label="Отправить сообщение"
          >
            ▶
          </button>
        </form>
      </div>

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
