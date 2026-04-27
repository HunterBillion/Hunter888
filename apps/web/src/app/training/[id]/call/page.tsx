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
import { PersonaConflictBadge } from "@/components/persona/PersonaConflictBadge";
import { PolicyViolationCounter } from "@/components/policy/PolicyViolationCounter";
import { usePolicyStore } from "@/stores/usePolicyStore";
import IncomingCallScreen from "@/components/training/phone/IncomingCallScreen";
import ScriptDrawer from "@/components/training/ScriptDrawer";
import { SessionAttachmentButton } from "@/components/training/SessionAttachmentButton";
import { telemetry } from "@/lib/telemetry";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useTTS } from "@/hooks/useTTS";
import { useSpeechRecognition } from "@/hooks/useSpeechRecognition";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";
import type { EmotionState, WSMessage } from "@/types";
import type { ClientCardData } from "@/components/training/ClientCard";

interface SessionMetaInner {
  // TZ-2 §6.2/6.3 canonical runtime fields. The backend stamps these on
  // every session (api/training.py start path) so the FE no longer has to
  // peek at custom_params.session_mode to decide between call/chat/center.
  // The legacy `custom_params.session_mode` stays in the type for fallback
  // — pilot data created before the canonical fields landed only carries
  // the legacy shape.
  mode?: "chat" | "call" | "center" | string | null;
  runtime_type?: string | null;
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
  // TZ-2 §6.2 — accept canonical mode at top level too (some legacy
  // callers flattened the session record before the wrapper landed).
  mode?: "chat" | "call" | "center" | string | null;
  runtime_type?: string | null;
  custom_params?: { bg_noise?: string | null; session_mode?: string } | null;
}

export default function TrainingCallPage() {
  const router = useRouter();
  const params = useParams();
  const searchParams = useSearchParams();
  const id = (Array.isArray(params?.id) ? params?.id[0] : params?.id) as string;

  const s = useSessionStore();

  // TZ-4 §13.4.1 — per-session audit state for the badge strip near
  // the top of the call view. The store is fed by NotificationWS-
  // Provider; this read subscribes to changes for *this* session id
  // only (Zustand selector returns the same reference until the
  // bucket actually changes), so other sessions in other tabs don't
  // re-render this component.
  const policySession = usePolicyStore((st) => (id ? st.bySession[id] : undefined));

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
  // 2026-04-23 Sprint 5 (Zone 2): callAccepted persisted across refresh
  // via sessionStorage. Scoped to session id so switching sessions resets.
  const [callAccepted, setCallAccepted] = useState<boolean>(() => {
    if (typeof window === "undefined" || !id) return false;
    try {
      return window.sessionStorage.getItem(`call-accepted-${id}`) === "1";
    } catch {
      return false;
    }
  });
  // Transient state flags for the IncomingCallScreen buttons.
  const [accepting, setAccepting] = useState(false);
  const [declining, setDeclining] = useState(false);
  // real_client_id pulled from GET /training/sessions/{id} — used as
  // redirect target when user clicks Decline (back to the CRM card).
  const [realClientId, setRealClientId] = useState<string | null>(null);
  // 2026-04-22: mask routing flash after hangup. When backend sends
  // client.hangup, several handlers race (explicit client.hangup path,
  // session.ended on WS close, modeOk re-check on remount). Without a
  // mask the user briefly saw the call page reset / chat page flash
  // before landing on /results. Now: any hangup trigger flips
  // hangupInProgress which renders a full-screen "call ending" overlay
  // that covers all intermediate states until the redirect lands.
  const [hangupInProgress, setHangupInProgress] = useState(false);
  const [hangupReason, setHangupReason] = useState<string>("");
  const [sessionMode, setSessionMode] = useState<"chat" | "call" | "center">("call");
  const [showCenterOutcome, setShowCenterOutcome] = useState(false);
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
        // TZ-2 §6.2 — read the canonical `mode` field first. The backend
        // schema (SessionResponse) now exposes it directly; legacy
        // `custom_params.session_mode` stays as a fallback so any pilot
        // session created before the canonical column was surfaced still
        // routes correctly. Accept both top-level (legacy flat shape) and
        // nested-under-session (canonical SessionResultResponse wrapper).
        const canonicalMode =
          meta?.session?.mode || meta?.mode || null;
        const cp =
          meta?.session?.custom_params || meta?.custom_params || null;
        const legacyMode = cp?.session_mode;
        const resolvedMode = canonicalMode || legacyMode;
        // Fail-OPEN on missing data (new sessions whose response is in
        // flight) but FAIL-CLOSED on an explicit "chat" / "center" signal
        // so the user lands on the right surface. The previous logic only
        // reacted to "chat"; with the canonical field we can also pivot
        // to /center when the runtime says so.
        if (resolvedMode === "chat") {
          logger.warn(
            `[call] session ${id} is mode="chat", redirecting to chat view`,
          );
          if (!cancelled) router.replace(`/training/${id}`);
          return;
        }
        if (resolvedMode === "center") {
          setSessionMode("center");
        } else {
          setSessionMode("call");
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
        // 2026-04-23 Zone 2: pick up real_client_id so Decline knows where
        // to redirect (CRM card vs /training). Fields may live at top
        // level or nested under session — tolerate either shape.
        const rcid =
          (meta as unknown as { real_client_id?: string | null })?.real_client_id
          ?? (meta as unknown as { session?: { real_client_id?: string | null } })?.session?.real_client_id
          ?? null;
        if (rcid) setRealClientId(String(rcid));
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

  // 2026-04-23 Sprint 5 (Zone 2): looped ringback. Plays 425Hz RU dial
  // tone on a 3.5s cycle until user clicks Accept or component unmounts.
  // Replaces the previous one-shot ring that played exactly once on
  // mount. Looping sells the «real incoming call» feel — user can walk
  // over to accept and still hear ringing.
  //
  // Audio is unlocked by the user's first Accept/Decline click (both are
  // gesture handlers). Before that click, AudioContext sits in "suspended"
  // state in modern Chrome; resume() is called at the top of handleAccept.
  // On most browsers the ringback won't actually emit sound until unlock,
  // but that's fine — the visual animation carries the UX.
  const ringbackStopRef = useRef<(() => void) | null>(null);
  useEffect(() => {
    if (modeOk !== true || callAccepted) return;
    if (typeof window === "undefined") return;
    const AC = (window.AudioContext ||
      (window as unknown as { webkitAudioContext?: typeof AudioContext })
        .webkitAudioContext) as typeof AudioContext | undefined;
    if (!AC) return;
    let ctx: AudioContext;
    try { ctx = new AC(); } catch { return; }
    let stopped = false;
    let timerId: ReturnType<typeof setTimeout> | null = null;

    const playOneCycle = () => {
      if (stopped) return;
      const t0 = ctx.currentTime + 0.02;
      const ring = ctx.createOscillator();
      ring.type = "sine";
      ring.frequency.value = 425;
      const ringGain = ctx.createGain();
      ringGain.gain.setValueAtTime(0, t0);
      ringGain.gain.linearRampToValueAtTime(0.18, t0 + 0.04);  // 40ms fade-in
      ringGain.gain.setValueAtTime(0.18, t0 + 0.6);
      ringGain.gain.linearRampToValueAtTime(0, t0 + 0.65);     // 50ms fade-out
      ring.connect(ringGain).connect(ctx.destination);
      ring.start(t0);
      ring.stop(t0 + 0.7);
      // 40ms «trying-to-pick-up» noise burst right after the tone.
      const t1 = t0 + 0.78;
      const clickBuf = ctx.createBuffer(1, ctx.sampleRate * 0.04, ctx.sampleRate);
      const cd = clickBuf.getChannelData(0);
      for (let i = 0; i < cd.length; i++) cd[i] = (Math.random() * 2 - 1) * (1 - i / cd.length) * 0.3;
      const click = ctx.createBufferSource();
      click.buffer = clickBuf;
      const clickGain = ctx.createGain();
      clickGain.gain.value = 0.08;
      click.connect(clickGain).connect(ctx.destination);
      click.start(t1);
      // Schedule next cycle — 3s silence after this cycle's click.
      timerId = setTimeout(playOneCycle, 3500);
    };

    if (ctx.state === "suspended") ctx.resume().catch(() => {});
    playOneCycle();

    const stop = (playPickupClick = false) => {
      if (stopped) return;
      stopped = true;
      if (timerId) {
        clearTimeout(timerId);
        timerId = null;
      }
      if (playPickupClick) {
        // Final louder pickup click — as if the receiver lifts off hook.
        try {
          const t = ctx.currentTime + 0.02;
          const buf = ctx.createBuffer(1, ctx.sampleRate * 0.06, ctx.sampleRate);
          const d = buf.getChannelData(0);
          for (let i = 0; i < d.length; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / d.length);
          const src = ctx.createBufferSource();
          src.buffer = buf;
          const g = ctx.createGain();
          g.gain.value = 0.14;
          src.connect(g).connect(ctx.destination);
          src.start(t);
        } catch {
          /* ignore */
        }
      }
      setTimeout(() => {
        try { ctx.close(); } catch { /* ignore */ }
      }, playPickupClick ? 250 : 50);
    };
    ringbackStopRef.current = () => stop(true);

    return () => {
      stop(false);
      ringbackStopRef.current = null;
    };
  }, [modeOk, callAccepted]);

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
    // 2026-04-23 Sprint 5 (Zone 2): WS connects as soon as modeOk, even
    // before user clicks Accept. The ONLY thing gated on callAccepted is
    // the session.start message (see sessionStartSentRef effect). This
    // lets the WebSocket handshake + auth.success complete while user
    // looks at IncomingCallScreen — so when they Accept, session.started
    // + client_card arrive in ~400ms instead of 1-2s cold-start.
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

        case "stage.skipped": {
          // 2026-04-23 Sprint 3: skipped stage notification (mirror of
          // chat handler). ScriptDrawer auto-opens with yellow alert.
          const sd = data.data as {
            missed_stage_number?: number;
            missed_stage_label?: string;
            current_stage_number?: number;
            current_stage_label?: string;
            hint?: string;
          };
          if (sd.missed_stage_number && sd.missed_stage_label) {
            s.setSkippedHint({
              missedStageNumber: sd.missed_stage_number,
              missedStageLabel: sd.missed_stage_label,
              currentStageNumber: sd.current_stage_number ?? s.currentStage,
              currentStageLabel: sd.current_stage_label ?? s.stageLabel,
              hint: sd.hint ?? "Вернитесь и закройте этот этап.",
              setAt: Date.now(),
            });
            telemetry.track("stage_skipped", {
              missed: sd.missed_stage_number,
              current: sd.current_stage_number ?? s.currentStage,
            });
          }
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
          // 2026-04-22: dedupe with client.hangup. If client.hangup fired
          // first, it scheduled a 3.5s timer to let farewell TTS play out
          // THEN router.replace. session.ended arriving concurrently would
          // cut the TTS short. Let the hangup path finish.
          if (hangupInProgress) {
            break;
          }
          tts.stop();
          stt.stopListening();
          endInFlightRef.current = true;
          setHangupReason("Звонок завершён");
          setHangupInProgress(true);
          router.replace(`/results/${currentSessionIdRef.current || id}`);
          break;

        case "client.hangup": {
          const canContinue = Boolean(data.data.call_can_continue);
          console.log("[CALL] client.hangup received", {
            reason: data.data.reason,
            canContinue,
          });
          if (!canContinue) {
            endInFlightRef.current = true;
            // 2026-04-22 (v2): set hangup overlay immediately so the user
            // doesn't see a flash of chat UI / empty call state while the
            // WS closes and /results loads. Previously: client.hangup →
            // setTimeout redirect → in those 3.5s, session.ended fires AND
            // WS disconnect re-triggers modeOk check → briefly rendered
            // chat page → then /results. Now the overlay masks ALL of it.
            setHangupReason((data.data.reason as string) || "Звонок завершён");
            setHangupInProgress(true);
            // router.replace so back-button doesn't return to dead call.
            setTimeout(() => {
              tts.stop();
              stt.stopListening();
              router.replace(`/results/${currentSessionIdRef.current || id}`);
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
    // 2026-04-23 Zone 2: don't send session.start until user clicks Accept.
    // Backend only emits TTS audio AFTER session.start, so holding it
    // until Accept prevents audio from being silently dropped by the
    // autoplay policy. Auth handshake already completed in parallel, so
    // as soon as user clicks Accept this effect runs and session.started
    // lands in ~400ms.
    if (!callAccepted) return;
    if (sessionStartSentRef.current) return;
    if (!id) return;
    sessionStartSentRef.current = true;
    // eslint-disable-next-line no-console
    console.log("[CALL] sending session.start");
    sendMessage({ type: "session.start", data: { session_id: id } });
  }, [connectionState, id, sendMessage, callAccepted]);

  // --- STT start/stop bound to mute state + mode readiness ---------------
  // 2026-04-26: removed the `!tts.speaking` gate. Previously, if TTS got
  // stuck (audio queue jammed, autoplay deferred, late chunk), `tts.speaking`
  // never went false → STT never started → user thought microphone was
  // dead even though the device was perfectly working. Web Speech API
  // ships its own VAD + the audio path uses echoCancellation, so leaving
  // STT live during TTS playback doesn't actually create a feedback loop
  // in practice. Mute remains the user's explicit pause.
  useEffect(() => {
    if (modeOk !== true) return;
    if (connectionState !== "connected") return;
    if (muted) {
      stt.stopListening();
      return;
    }
    if (!stt.isSupported) return;
    stt.startListening();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modeOk, connectionState, muted]);

  // Watchdog: if STT remains idle for ~3s after we asked to listen, retry
  // once. Covers transient SpeechRecognition.start() races (Chrome will
  // sometimes silently no-op if a previous instance hadn't fully torn down).
  useEffect(() => {
    if (modeOk !== true) return;
    if (connectionState !== "connected") return;
    if (muted) return;
    if (!stt.isSupported) return;
    if (stt.status !== "idle") return;
    const t = setTimeout(() => stt.startListening(), 3000);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modeOk, connectionState, muted, stt.status]);

  // --- Speaker toggle — pauses/resumes TTS playback ----------------------
  useEffect(() => {
    tts.setEnabled(speakerOn);
  }, [speakerOn, tts]);

  // --- Hangup: navigate IMMEDIATELY, cleanup in background ---------------
  // Navigate first so the button always responds even if TTS/STT/backend
  // throw. Cleanup runs as fire-and-forget — the results page reloads
  // session state from the server anyway, so late-arriving errors are safe.
  const completeHangup = useCallback((outcome?: "agreed" | "not_agreed" | "continue") => {
    if (endInFlightRef.current) return;
    endInFlightRef.current = true;
    setShowCenterOutcome(false);
    const sid = currentSessionIdRef.current || id;
    // 2026-04-23 UX: show the hangup overlay IMMEDIATELY so the user sees
    // responsive feedback (red spinner in button + "Завершаем…" label +
    // full-screen "Сохраняем результаты" overlay). Previously router.push
    // happened in the same tick — user got an abrupt jump without seeing
    // the button react. Now the click visibly commits → 250ms tick → /results.
    setHangupReason("Звонок завершён");
    setHangupInProgress(true);
    try { tts.stop(); } catch { /* noop */ }
    try { stt.stopListening(); } catch { /* noop */ }
    // Fire-and-forget end POST in parallel so backend scoring starts NOW,
    // not after we land on /results.
    (async () => {
      try {
        await api.post(`/training/sessions/${sid}/end`, outcome ? { outcome } : {});
      } catch (err) {
        logger.warn("[call] end POST failed (may already be ended)", err);
      }
    })();
    // Replace (not push) so back-button doesn't return to dead call.
    window.setTimeout(() => {
      router.replace(`/results/${sid}`);
    }, 250);
  }, [id, router, tts, stt]);

  const onHangup = useCallback(() => {
    if (sessionMode === "center") {
      setShowCenterOutcome(true);
      return;
    }
    completeHangup();
  }, [completeHangup, sessionMode]);

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

  // 2026-04-23 Sprint 5 (Zone 2): the old inline JSX accept-gate is
  // replaced by the full IncomingCallScreen component with avatar, age,
  // city, profession, lead-source badge, debt chip and a pair of
  // Accept+Decline buttons. Accept runs the 3-vector audio unlock,
  // Decline posts to /training/sessions/{id}/decline and redirects to
  // the CRM card (or /training if no real_client).
  if (!callAccepted) {
    return (
      <IncomingCallScreen
        characterName={s.characterName || "Клиент"}
        emotion={s.emotion as EmotionState | undefined}
        sceneId={sceneBg}
        clientCard={s.clientCard}
        accepting={accepting}
        declining={declining}
        onAccept={async () => {
          if (accepting || declining) return;
          setAccepting(true);
          console.log("[CALL] accept-click: running unlock sequence");
          // Stop looping ringback + play one final pickup click.
          try { ringbackStopRef.current?.(); } catch { /* */ }
          // Re-run the 3-vector unlock — proven gesture-handler sequence.
          try {
            // Vector 1: Web Audio API unlock.
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
              setTimeout(() => { try { ctx.close(); } catch { /* */ } }, 500);
            }
            // Vector 2: HTMLAudioElement via blob URL (CSP-safe).
            const silentWav = new Uint8Array([
              0x52, 0x49, 0x46, 0x46, 0x25, 0, 0, 0, 0x57, 0x41, 0x56, 0x45,
              0x66, 0x6d, 0x74, 0x20, 0x10, 0, 0, 0, 1, 0, 1, 0,
              0x40, 0x1f, 0, 0, 0x40, 0x1f, 0, 0, 1, 0, 8, 0,
              0x64, 0x61, 0x74, 0x61, 0x01, 0, 0, 0, 0x80,
            ]);
            const blob = new Blob([silentWav], { type: "audio/wav" });
            const url = URL.createObjectURL(blob);
            const a = new Audio(url);
            a.volume = 0.001;
            try {
              await a.play();
              console.log("[CALL] unlock: HTMLAudio play() succeeded");
            } catch (e) {
              console.warn("[CALL] unlock: HTMLAudio play() failed:", e);
            }
            URL.revokeObjectURL(url);
            // Vector 3: also poke tts.unlock() if pending.
            try { tts.unlock(); } catch { /* */ }
          } catch (e) {
            console.warn("[CALL] unlock sequence error:", e);
          }
          // Persist across refresh so F5 doesn't bounce back to incoming.
          try {
            window.sessionStorage.setItem(`call-accepted-${id}`, "1");
          } catch {
            /* storage quota / private mode — non-fatal */
          }
          setCallAccepted(true);
        }}
        onDecline={async () => {
          if (accepting || declining) return;
          setDeclining(true);
          try { ringbackStopRef.current?.(); } catch { /* */ }
          // Persist decline so refresh doesn't re-show incoming screen.
          try {
            window.sessionStorage.setItem(`call-declined-${id}`, "1");
          } catch {
            /* */
          }
          // Fire-and-forget POST /decline. We redirect regardless of the
          // response — backend idempotency handles double-clicks and 429
          // rate limits shouldn't block the UX.
          (async () => {
            try {
              await api.post(`/training/sessions/${id}/decline`, {});
            } catch (err) {
              logger.warn("[call] decline POST failed (non-fatal)", err);
            }
          })();
          // Route to CRM card if we know the real client, else back to
          // /training catalog. router.replace prevents the user from
          // back-button'ing into the same incoming screen.
          const target = realClientId ? `/clients/${realClientId}` : "/training";
          router.replace(target);
        }}
      />
    );
  }

  // 2026-04-22 diagnostics banner: show on-screen warnings so user sees
  // the state of critical call-mode dependencies without opening DevTools.
  // Plain derived values (not hooks) — safe after the early-return.
  const sttSupported = stt.isSupported;
  const sttError = stt.status === "unsupported" || stt.status === "error";
  const wsDead = connectionState === "disconnected" || connectionState === "error";

  // 2026-04-22: hang-up transition overlay. Shown for the 3.5s between
  // client.hangup/session.ended and the redirect to /results. Covers the
  // entire viewport at z-[100] so any UI flash (chat page, empty call,
  // loading spinner on /results) is invisible to the user. The farewell
  // TTS still plays because it was queued before this render.
  if (hangupInProgress) {
    return (
      <div
        className="fixed inset-0 z-[100] flex flex-col items-center justify-center gap-5 text-white"
        style={{
          background:
            "radial-gradient(ellipse at center, #2a1a4a 0%, #14091e 55%, #06030c 100%)",
        }}
      >
        <div className="text-6xl animate-pulse">📞</div>
        <div className="text-xl font-semibold tracking-tight">Звонок завершён</div>
        {hangupReason && (
          <div className="text-sm text-white/60 max-w-sm text-center px-8">
            {hangupReason}
          </div>
        )}
        <div className="flex items-center gap-2 text-xs text-white/50 mt-3">
          <div className="h-1 w-1 rounded-full bg-white/60 animate-pulse" />
          <span>Сохраняем результаты…</span>
        </div>
      </div>
    );
  }

  return (
    <>
      {/* 2026-04-23 Sprint 3: ScriptDrawer floats over PhoneCallMode on
          mobile + narrow windows (it's lg:hidden by default). On desktop
          the plan's merge into PhoneCallMode teleprompter happens
          in-component; here we just guarantee the mobile drawer exists. */}
      <ScriptDrawer
        onCopyExample={(text) => {
          // On call page the main input is the voice mic, but we do
          // have a fallback text field — pre-fill it with the example.
          setTextInput(text);
        }}
      />
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
        endInFlight={hangupInProgress}
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

      {showCenterOutcome && !hangupInProgress && (
        <div className="fixed inset-0 z-[160] flex items-end justify-center bg-black/60 p-4 backdrop-blur-sm sm:items-center">
          <div className="w-full max-w-md rounded-lg border border-white/10 bg-neutral-950 p-4 shadow-2xl">
            <div className="mb-4">
              <div className="text-sm font-semibold text-white">Выберите исход звонка</div>
              <div className="mt-1 text-xs text-white/60">Зафиксируем результат, чтобы карточка клиента обновилась корректно.</div>
            </div>
            <div className="grid gap-2">
              <button type="button" className="rounded-md bg-emerald-500 px-4 py-3 text-left text-sm font-semibold text-white" onClick={() => completeHangup("agreed")}>
                Договор согласован
              </button>
              <button type="button" className="rounded-md bg-red-500 px-4 py-3 text-left text-sm font-semibold text-white" onClick={() => completeHangup("not_agreed")}>
                Договор не согласован
              </button>
              <button type="button" className="rounded-md bg-sky-500 px-4 py-3 text-left text-sm font-semibold text-white" onClick={() => completeHangup("continue")}>
                Продолжить в другом звонке
              </button>
              <button type="button" className="rounded-md border border-white/10 px-4 py-3 text-sm text-white/70" onClick={() => setShowCenterOutcome(false)}>
                Вернуться к звонку
              </button>
            </div>
          </div>
        </div>
      )}

      {/*
        Diagnostics banner (2026-04-22). Shows on-screen why the call
        might feel silent without user having to open DevTools:
          - WS down: "Нет связи с сервером…"
          - STT unsupported/error: "Микрофон недоступен, пишите текстом"
          - tts still speaking: "Клиент говорит…" (info)
        Positioned below the teleprompter so it doesn't fight the avatar.
      */}
      {/* TZ-4 §13.4.1 — audit signal badges. The PolicyViolationCounter
          and PersonaConflictBadge components self-hide at zero, so
          warn-only sessions with no violations look identical to the
          legacy UI. The policy session state is hoisted into a
          top-level hook (``policySession`` const above) to satisfy
          the React Rules-of-Hooks. */}
      {policySession && (
        <div className="fixed top-[78px] left-0 right-0 z-30 flex justify-center gap-2 px-4 pointer-events-none">
          <div className="pointer-events-auto">
            <PolicyViolationCounter
              severityCounts={policySession.bySeverity}
              enforceActive={policySession.enforceActive}
            />
          </div>
          <div className="pointer-events-auto">
            <PersonaConflictBadge
              count={policySession.personaConflicts}
              lastAttemptedField={policySession.lastPersonaAttemptedField}
            />
          </div>
        </div>
      )}

      {(wsDead || sttError || !sttSupported) && (
        <div className="fixed top-[130px] left-0 right-0 z-30 flex justify-center px-4">
          {sttError && sttSupported && !wsDead ? (
            // 2026-04-26: actionable retry button on stt error. Earlier
            // this banner was pointer-events-none → user with denied mic
            // had no obvious recovery path beyond the small mic icon.
            <button
              type="button"
              onClick={() => stt.startListening()}
              className="rounded-full bg-amber-500/90 px-4 py-1.5 text-xs font-medium text-black shadow-lg transition hover:bg-amber-400"
            >
              Микрофон недоступен — нажмите чтобы включить
            </button>
          ) : (
            <div className="pointer-events-none rounded-full bg-amber-500/90 px-4 py-1.5 text-xs font-medium text-black shadow-lg">
              {wsDead
                ? "Нет связи с сервером — переподключаемся…"
                : "Этот браузер не поддерживает голос. Пишите текстом ниже."}
            </div>
          )}
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
          <SessionAttachmentButton
            sessionId={id}
            variant="call"
            disabled={connectionState !== "connected"}
          />
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
