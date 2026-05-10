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
import { useShallow } from "zustand/react/shallow";
import IncomingCallScreen from "@/components/training/phone/IncomingCallScreen";
import CallDialingOverlay from "@/components/training/phone/CallDialingOverlay";
// Phase E (2026-05-08): unified loader — same component as the chat
// route, mode='call' adds phone-themed icon + 300Hz click + reason/stats.
import SessionEndingOverlay from "@/components/training/SessionEndingOverlay";
import ScriptDrawer from "@/components/training/ScriptDrawer";
import { LinkClientButton } from "@/components/training/LinkClientButton";
// NEW-6/7 (2026-05-04): same kebab pattern as the chat view — paperclip
// moved into a dropdown so the input field is the main focus.
import { SessionAttachmentButton } from "@/components/training/SessionAttachmentButton";
import { telemetry } from "@/lib/telemetry";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useTTS } from "@/hooks/useTTS";
import { useSpeechRecognition } from "@/hooks/useSpeechRecognition";
import { useMicrophone } from "@/hooks/useMicrophone";
import { MicStatusBanner, pickBannerKind } from "@/components/training/MicStatusBanner";
import { TTSUnlockOverlay } from "@/components/training/TTSUnlockOverlay";
import { toast } from "sonner";
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

// PR-H (B5 defensive): module-level fallback for "this session was
// already accepted in this tab". sessionStorage normally carries this
// across remounts, but on Brave/Safari private mode setItem can throw
// or silently fail (no quota / disabled), and useState reads then
// return false on the second render → IncomingCallScreen renders again.
// The Set lives for the page life of the tab; it is the in-memory
// fallback that survives the brief remount without depending on the
// browser storage facility being writable.
const _ACCEPTED_SESSIONS_RUNTIME = new Set<string>();

export default function TrainingCallPage() {
  const router = useRouter();
  const params = useParams();
  const searchParams = useSearchParams();
  const id = (Array.isArray(params?.id) ? params?.id[0] : params?.id) as string;

  const s = useSessionStore();

  // TZ-4 §13.4.1 — per-session audit state for the badge strip near
  // the top of the call view. The store is fed by NotificationWS-
  // Provider; this read subscribes to changes for *this* session id
  // only. Audit-2026-04-28: project to a flat object via ``useShallow``
  // so the call page only re-renders when THIS session's counters
  // actually change. The naive ``state.bySession[id]`` selector
  // returned the same reference across calls but didn't help when
  // ``recordPolicyViolation`` rebuilt the bucket via spread —
  // ``useShallow`` compares by primitive fields instead.
  const policySession = usePolicyStore(
    useShallow((st) => {
      if (!id) return null;
      const bucket = st.bySession[id];
      if (!bucket) return null;
      return {
        total: bucket.total,
        bySeverity: bucket.bySeverity,
        personaConflicts: bucket.personaConflicts,
        lastPersonaAttemptedField: bucket.lastPersonaAttemptedField,
        enforceActive: bucket.enforceActive,
      };
    }),
  );

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
    // PR-H (B5 defensive): check the module-level runtime Set first —
    // if Accept was clicked earlier in this tab, the user shouldn't see
    // IncomingCallScreen again on a remount even when sessionStorage
    // is disabled (Brave Shields / Safari private). Falls back to the
    // sessionStorage probe so a real F5 reload still rehydrates from
    // disk on a normal browser.
    if (_ACCEPTED_SESSIONS_RUNTIME.has(id)) return true;
    try {
      return window.sessionStorage.getItem(`call-accepted-${id}`) === "1";
    } catch {
      return false;
    }
  });
  // Transient state flags for the IncomingCallScreen buttons.
  const [accepting, setAccepting] = useState(false);
  const [declining, setDeclining] = useState(false);
  // Phase 1 of call-flow lifecycle redesign (2026-05-01): brief
  // "Соединение..." overlay between Accept-click and PhoneCallMode taking
  // over. Sells the "real phone call" feel — without it, click → instant
  // active call felt AI-y. Cleared after ~1200ms by the Accept handler.
  const [dialingOverlay, setDialingOverlay] = useState(false);
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

  // Sprint 0 §7 (Bug A) — first-audio gate.
  //
  // Problem: when handleAccept runs, it tells the ringback loop to play
  // a final ~60ms pickup click via Web Audio (line 314+, scheduled at
  // ctx.currentTime + 0.02). Right after that, the WS connects, the
  // backend (with CALL_HUMANIZED_V2 + auto_opener flag) sends the
  // "Алло?" tts.audio almost immediately, and the HTMLAudioElement
  // playback starts before the pickup click finishes — user hears them
  // overlap as "странный звук".
  //
  // Fix: hold a wall-clock timestamp that means "first TTS allowed at".
  // Set it 350ms after the Accept click (covers 20ms schedule + 60ms
  // click + 250ms ctx-close + 20ms safety margin). Each tts.audio /
  // tts.audio_chunk handler runs through scheduleAudioPlayback() which
  // either plays immediately (gate already open) or defers via
  // setTimeout (one-shot, queue order preserved because all pending
  // calls share the same target wake-up).
  //
  // Default value Date.now() means "open" — a stale-state refresh
  // (callAccepted=true on mount) bypasses the gate entirely, which is
  // correct: there is no fresh pickup click on rehydration.
  const audioGateUntilRef = useRef<number>(Date.now());
  // Phase D (2026-05-08, Bug 2 fix): track every deferred audio play so
  // we can cancel them all on hangup. Without this set, a tts.audio_chunk
  // arriving inside the gate window (now 1500ms post-Accept per Phase A)
  // would defer via setTimeout — and that setTimeout had no cancel handle.
  // After the user hangs up and tts.stop() is called, the deferred
  // queueAudioChunk callback would still fire, repopulate the chunk queue,
  // and play. The pilot's "voice continues after hangup" complaint traces
  // to exactly this leak.
  const pendingAudioTimeoutsRef = useRef<Set<number>>(new Set());
  const scheduleAudioPlayback = useCallback((play: () => void) => {
    const now = Date.now();
    const gate = audioGateUntilRef.current;
    if (now >= gate) {
      play();
      return;
    }
    const id = window.setTimeout(() => {
      pendingAudioTimeoutsRef.current.delete(id);
      play();
    }, gate - now);
    pendingAudioTimeoutsRef.current.add(id);
  }, []);

  // Phase D (2026-05-08): single redirect helper. Previously THREE
  // independent code paths (completeHangup, session.ended handler,
  // client.hangup handler) each scheduled their own router.replace
  // with their own setTimeout — so a manual hangup followed by a
  // backend-initiated client.hangup race could fire two redirects,
  // and a user saw a /results flash + reload. redirectFiredRef makes
  // this idempotent: only the FIRST caller wins.
  // (stopAllAudio is defined AFTER tts below since it captures it.)
  const redirectFiredRef = useRef(false);
  const goToResults = useCallback((delayMs: number = 0) => {
    if (redirectFiredRef.current) return;
    redirectFiredRef.current = true;
    const sid = currentSessionIdRef.current || id;
    if (delayMs > 0) {
      window.setTimeout(() => router.replace(`/results/${sid}`), delayMs);
    } else {
      router.replace(`/results/${sid}`);
    }
  }, [id, router]);

  // --- TTS (plays backend mp3, exposes real audioLevel) -------------------
  // 2026-05-01 — phoneBandFilter ON for call page only. Routes every TTS
  // playback through highpass(300Hz)→lowpass(3400Hz)→compressor (PSTN
  // narrowband) so the AI client sounds unmistakably "по телефону" instead
  // of studio-clean. Chat / arena pages don't pass this prop, default false.
  const tts = useTTS({ lang: "ru-RU", rate: 0.95, pitch: 1.0, phoneBandFilter: true });

  // Phase D (2026-05-08): single-source helper for "stop all audio NOW".
  // Cancels every pending scheduleAudioPlayback timeout, then asks
  // useTTS to tear down the active audio element + chunk queue +
  // pendingPlaybackRef. Use this from EVERY hangup path so the user
  // never hears audio after the visual call has ended.
  const stopAllAudio = useCallback(() => {
    pendingAudioTimeoutsRef.current.forEach((id) => clearTimeout(id));
    pendingAudioTimeoutsRef.current.clear();
    try { tts.stop(); } catch { /* noop */ }
  }, [tts]);

  // Surface terminal TTS playback errors as toasts. Without this, decode
  // failures, media-element errors, and tts.fallback transitions were
  // silent and the user just heard nothing / a different voice with no
  // explanation. Audit Pattern 3 #9 + #15.
  // PR-H (B7 defensive): track first TTS audio after session.started.
  // Pilot users report: «у некоторых пользователей не слышать ии клиента».
  // The 3-vector unlock sequence runs on Accept, but on a subset of
  // browsers (Brave with autoplay tightened, mobile Safari with strict
  // gesture coupling, audio device race) the AudioContext stays
  // suspended and the first tts.audio decode fires into the void —
  // there's no error, just silence. The recovery flag below flips ON
  // when the WS receives session.started and OFF the moment any
  // tts.audio / tts.audio_chunk arrives. A useEffect below watches the
  // delta and, if no audio after 6 seconds, surfaces a "tap to enable
  // sound" toast that re-runs tts.unlock(). Without this the user sits
  // there waiting for a phantom AI that the backend already streamed
  // but the browser never played.
  const [sessionStartedAt, setSessionStartedAt] = useState<number | null>(null);
  const firstTtsAudioReceivedRef = useRef(false);
  const ttsRecoveryFiredRef = useRef(false);

  const lastTtsErrorMsgRef = useRef<string | null>(null);
  useEffect(() => {
    if (!tts.playbackError) {
      lastTtsErrorMsgRef.current = null;
      return;
    }
    if (tts.playbackError.message === lastTtsErrorMsgRef.current) return;
    lastTtsErrorMsgRef.current = tts.playbackError.message;
    if (tts.playbackError.kind === "fallback_active") {
      toast.info("Резервный голос", { description: tts.playbackError.message });
    } else {
      toast.error("Озвучка прервана", { description: tts.playbackError.message });
    }
  }, [tts.playbackError]);

  // Phase B (2026-05-08) — authoritative "first audio actually played"
  // signal. Watches `tts.speaking` and sets the watchdog-disarm flag
  // ONLY when an Audio element actually started playback (useTTS sets
  // speaking=true after the .play() promise resolves). Previously the
  // flag was set on WS message RECEIPT, which made the watchdog
  // self-disarm even when Brave/mobile Safari refused autoplay — so
  // the recovery toast never appeared and pilot users sat in silence.
  useEffect(() => {
    if (tts.speaking && !firstTtsAudioReceivedRef.current) {
      firstTtsAudioReceivedRef.current = true;
      logger.log("[CALL] B7 watchdog disarmed — tts.speaking=true (audio actually playing)");
    }
  }, [tts.speaking]);

  // PR-H (B7) — no-audio watchdog. If session.started fires but no
  // tts.audio / tts.audio_chunk arrives in 6 seconds, surface a
  // recovery toast that re-runs tts.unlock(). The 3-vector unlock on
  // Accept covers most cases, but on Brave (autoplay tightened),
  // mobile Safari (strict gesture coupling), or after an audio device
  // race the AudioContext can stay suspended and decode results land
  // in the void with no error event. Without this the user just sits
  // in silence wondering if the AI is even there. Watchdog runs once
  // per session — ttsRecoveryFiredRef makes sure a flaky network
  // delaying the first audio doesn't spawn 5 toasts in a row.
  useEffect(() => {
    if (!sessionStartedAt) return;
    const tid = window.setTimeout(() => {
      if (firstTtsAudioReceivedRef.current) return;
      if (ttsRecoveryFiredRef.current) return;
      ttsRecoveryFiredRef.current = true;
      logger.warn("[CALL] B7 watchdog: no tts.audio in 6s after session.started");
      // Phase B (2026-05-08): proactively re-run tts.unlock() BEFORE
      // showing the toast. On Brave / mobile Safari the AudioContext
      // sometimes goes suspended between Accept-click and the first
      // tts.audio decode (background tab, audio device race). A
      // second unlock can recover silently — only show the toast if
      // it didn't help, judged by another 600ms grace check.
      try { tts.unlock(); } catch { /* best-effort */ }
      window.setTimeout(() => {
        if (firstTtsAudioReceivedRef.current) {
          logger.log("[CALL] B7 watchdog: silent re-unlock recovered — no toast needed");
          return;
        }
        try {
          // Toast with a tap-to-fix action. Sonner's `action` renders
          // a button alongside the message that runs the callback —
          // gives the user a one-tap recovery instead of hunting for
          // the speaker icon as the previous copy suggested.
          toast.warning("Не слышно ИИ-клиента?", {
            description:
              "Звук мог быть заблокирован браузером. Нажмите «Включить звук» чтобы восстановить.",
            duration: 12000,
            action: {
              label: "Включить звук",
              onClick: () => {
                try { tts.unlock(); } catch { /* */ }
                logger.log("[CALL] user tapped manual TTS unlock");
              },
            },
          });
        } catch {
          /* sonner not available — non-fatal */
        }
      }, 600);
    }, 6000);
    return () => window.clearTimeout(tid);
  }, [sessionStartedAt, tts]);

  // --- STT (continuous, forwards recognized text to WS) -------------------
  const sttSendRef = useRef<((text: string) => void) | null>(null);
  // PR-C (barge-in feedback): when STT detects the user starting to
  // speak while TTS is mid-reply, send audio.interrupted to the backend
  // so it can rewrite history with what the manager actually heard.
  // ``audioRef.current.currentTime`` × ~14 chars/sec (Russian TTS avg)
  // gives a rough char count that's good enough for the prompt cue —
  // the LLM only needs to know "got cut early" vs "got most of it".
  const interruptSendRef = useRef<((playedChars: number) => void) | null>(null);
  const stt = useSpeechRecognition({
    lang: "ru-RU",
    onResult: (text) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      // Barge-in detection: TTS still speaking when user-speech text arrives.
      if (tts.speaking) {
        const ct = tts.audioRef?.current?.currentTime ?? 0;
        const playedChars = Math.max(0, Math.round(ct * 14));
        try {
          interruptSendRef.current?.(playedChars);
        } catch {
          /* non-blocking */
        }
        try { tts.stop(); } catch { /* noop */ }
      }
      sttSendRef.current?.(trimmed);
    },
  });

  // PR-F (Whisper fallback for call mode): Web Speech API depends on
  // Google's cloud, which Brave blocks by default and Safari/Firefox
  // don't expose at all. When that path errors out we still want voice
  // to work, so we fall back to MediaRecorder + backend Whisper — the
  // same pipeline chat already uses (audio.end with full processing).
  //
  // Trigger conditions: SpeechRecognition reported a network error or
  // the API isn't supported in the current browser. The fallback is
  // push-to-talk (hold the button while speaking) — continuous-mode
  // streaming with VAD belongs to a future PR; push-to-talk is shipped
  // now because it gets call-mode actually working everywhere TODAY.
  const sttBlocked =
    !stt.isSupported ||
    stt.errorCode === "network" ||
    stt.errorCode === "service-not-allowed" ||
    stt.errorCode === "language-not-supported";
  const microphoneFallback = useMicrophone({});
  const [pushTalkActive, setPushTalkActive] = useState(false);
  const sendAudioBlobRef = useRef<((blob: Blob) => void) | null>(null);

  // --- Mount guard: verify session_mode, hydrate store --------------------
  /*
   * 2026-05-10 FIND-010 fix: устранён eslint-disable.
   * Раньше effect зависел только от `[id]`, остальные ссылки
   * (router, store actions, useState setters) попадали под disable
   * как «stable references».
   *
   * Теперь явно destructure'им actions из zustand-store перед
   * useEffect — они стабильны (zustand actions создаются один раз).
   * useState-setters стабильны по Reactовому контракту. router и
   * api-helpers тоже стабильны. Кладём всё в deps честно — линтер
   * не жалуется, future refactor увидит реальные зависимости.
   */
  const setCharacterName = s.setCharacterName;
  const setScenarioTitle = s.setScenarioTitle;
  useEffect(() => {
    if (!id) return;
    logger.log("[CALL] mount — id=", id);
    let cancelled = false;
    (async () => {
      try {
        const meta = await api.get<SessionMeta>(`/training/sessions/${id}`);
        logger.log("[CALL] meta fetched", meta);
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
        if (meta?.character_name) setCharacterName(meta.character_name);
        if (meta?.scenario_title) setScenarioTitle(meta.scenario_title);
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
  }, [id, router, setCharacterName, setScenarioTitle, setSessionMode, setSceneBg, setRealClientId, setModeOk]);

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
  //
  // 2026-05-10 FIND-010 fix: устранён eslint-disable. tts.setVolume —
  // useCallback из useTTS, ссылка стабильна, можно положить в deps без
  // риска повторных запусков на каждом рендере.
  const ttsSetVolume = tts.setVolume;
  useEffect(() => {
    ttsSetVolume(0.85);
  }, [ttsSetVolume]);

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

    // Phase A (2026-05-08): only schedule audio when the context is
    // actually running. Scheduling tones into a `suspended` timeline
    // queues them in real-time-future; when the context unsuspends on
    // the user's first gesture the queue flushes compressed into a few
    // ms — that flush manifested as a brief screech/click bundle right
    // at the Accept-click moment. By gating on `ctx.state === "running"`
    // we either play immediately (already unlocked) or wait for the
    // statechange event to fire, after which the queue is in sync with
    // wall-clock again.
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
      // Schedule next cycle — 3s silence after this cycle's tone.
      // Phase A (2026-05-08): the 40ms «trying-to-pick-up» random-PCM
      // burst was removed. It had no DC blocking and no attack envelope
      // (only release), so the very first sample was a hard step from
      // 0 to ±0.024 — perceptible as an impulse click at low volumes
      // and a hiss at higher ones. The 425 Hz pulsed gudok already
      // conveys "phone ringing" — the noise burst was decorative
      // overhead that contributed to the pre-pickup screech reports.
      timerId = setTimeout(playOneCycle, 3500);
    };

    let stateHandler: (() => void) | null = null;
    const startPlayback = () => {
      if (stopped) return;
      playOneCycle();
    };
    if (ctx.state === "running") {
      startPlayback();
    } else {
      // Suspended: wait for unlock instead of scheduling into a frozen
      // timeline. resume() is best-effort (returns rejected promise on
      // some browsers without a gesture); the statechange handler is
      // the authoritative trigger.
      stateHandler = () => {
        if (ctx.state === "running") startPlayback();
      };
      ctx.addEventListener("statechange", stateHandler);
      ctx.resume().catch(() => { /* will retry via statechange */ });
    }

    // Phase A (2026-05-08): the loud pickup-click variant of stop()
    // was removed. It produced a 60ms random-PCM burst at amplitude
    // 0.14 with no attack envelope — the impulse at sample 0 was the
    // single most likely source of the user-reported screech, especially
    // when stacked with the second AudioContext that the dialing
    // overlay creates ~50ms later. The dialing overlay's ringback
    // (1.0s pulsed 425 Hz) is now the sole audio cue for "receiver
    // picked up", which matches a real-phone soundscape better than
    // a noise click anyway.
    const stop = () => {
      if (stopped) return;
      stopped = true;
      if (timerId) {
        clearTimeout(timerId);
        timerId = null;
      }
      if (stateHandler) {
        try { ctx.removeEventListener("statechange", stateHandler); } catch { /* */ }
        stateHandler = null;
      }
      setTimeout(() => {
        try { ctx.close(); } catch { /* ignore */ }
      }, 50);
    };
    ringbackStopRef.current = stop;

    return () => {
      stop();
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
      logger.log("[CALL]", data.type, data.data);
      switch (data.type) {
        case "auth.success":
        case "session.ready":
          break;

        case "session.started": {
          if (data.data.session_id) {
            currentSessionIdRef.current = data.data.session_id as string;
          }
          // PR-H (B7): start the no-audio watchdog. firstTtsAudioReceived
          // resets to false on every fresh session.started, so a Story
          // Mode call #2 still gets its 6-second grace.
          setSessionStartedAt(Date.now());
          firstTtsAudioReceivedRef.current = false;
          ttsRecoveryFiredRef.current = false;
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
          // Phase B (2026-05-08): the watchdog flag is no longer set
          // here. Previously `firstTtsAudioReceivedRef.current = true`
          // fired on RECEIPT of the WS message, before play() actually
          // succeeded — so if the browser refused autoplay (Brave,
          // mobile Safari) the watchdog disarmed itself anyway and the
          // recovery toast never appeared. Now the flag is set by a
          // useEffect that watches `tts.speaking` (which flips true
          // only when an Audio element actually started playback —
          // see useTTS.ts:592, 828, 1073). Recovery toast will fire
          // when no audio actually plays in 6s.
          const audioB64 = data.data.audio_b64 as string | undefined;
          if (audioB64 && typeof audioB64 === "string" && audioB64.length > 0) {
            // Sprint 0 §7 (Bug A): defer the first audio behind the
            // pickup-click gate so it does not overlap with the
            // ringback's farewell tone.
            const emotion = data.data.emotion as EmotionState | undefined;
            const voiceParams = data.data.voice_params as
              | { stability: number; similarity_boost: number; style: number; speed: number }
              | undefined;
            const durationMs = data.data.duration_ms as number | undefined;
            // Phase F (2026-05-08): backend-flagged barge reactions
            // (emit from _handle_audio_interrupted) bypass both the
            // audio gate AND the playAudioMessage queue — the
            // surprise/anger response must land within the perceptual
            // window of the user's interrupt, not after a queued chunk.
            const isBargeReaction = Boolean(data.data.interruption_reaction);
            if (isBargeReaction) {
              tts.playAudioMessage(
                {
                  audio: audioB64,
                  emotion,
                  voice_params: voiceParams,
                  duration_ms: durationMs,
                },
                { interrupt: true },
              );
            } else {
              scheduleAudioPlayback(() => {
                tts.playAudioMessage({
                  audio: audioB64,
                  emotion,
                  voice_params: voiceParams,
                  duration_ms: durationMs,
                });
              });
            }
          } else {
            logger.warn("[CALL] tts.audio received but audio_b64 missing/empty", {
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
          // Phase B (2026-05-08): same as tts.audio above — the
          // watchdog flag is no longer set on chunk receipt. The
          // tts.speaking effect below is the authoritative signal.
          const chunkAudio = data.data.audio_b64 as string | undefined;
          if (chunkAudio) {
            // Sprint 0 §7 (Bug A): same gate. queueAudioChunk only adds
            // to the internal sentence queue — useTTS plays them in
            // index order regardless of when they were queued, so the
            // setTimeout indirection does not reorder anything.
            const idx = (data.data.sentence_index as number) ?? 0;
            const last = Boolean(data.data.is_last);
            scheduleAudioPlayback(() => {
              tts.queueAudioChunk({
                audio: chunkAudio,
                index: idx,
                isLast: last,
              });
            });
          }
          break;
        }

        case "tts.couple_audio":
          // Sprint 0 §7 (Bug A): also gate the couple-audio path.
          {
            const couple = data.data as unknown as Parameters<typeof tts.playCoupleAudio>[0];
            scheduleAudioPlayback(() => {
              tts.playCoupleAudio(couple);
            });
          }
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

        // P2 (2026-04-29) — coaching mistake detector toasts.
        // Backend rule-based detector emits this on every detected mistake
        // (monologue, no_open_question, early_pricing, repeated_argument,
        // talk_ratio_high). Routed through addWhisper so the existing
        // PhoneCallMode coachingHint UI renders it (priority dot + text).
        case "coaching.mistake": {
          const d = data.data as Record<string, unknown>;
          const hint = String(d.hint ?? "");
          if (!hint) break;
          const severity = String(d.severity ?? "warn");
          const priority: "low" | "medium" | "high" =
            severity === "alert" ? "high" : severity === "info" ? "low" : "medium";
          const mistakeType = String(d.type ?? "stage");
          const iconMap: Record<string, string> = {
            monologue: "mic-off",
            no_open_question: "help-circle",
            early_pricing: "alert-triangle",
            repeated_argument: "rotate-cw",
            talk_ratio_high: "volume-2",
            mode_switch_to_on_task: "compass",
          };
          s.addWhisper({
            type: "stage",
            message: hint,
            stage: mistakeType,
            priority,
            icon: iconMap[mistakeType] ?? "zap",
            timestamp: Date.now(),
          });
          telemetry.track("coaching_mistake", {
            mistake_type: mistakeType,
            severity,
          });
          break;
        }

        case "score.hint":
          // 2026-05-03: dropped `s.setRealtimeScores(...)` write —
          // the <RealtimeScores> consumer was removed in the
          // sidebar redesign and nothing else reads the slice.
          // Call mode shows score live via the in-call UI; if a
          // breakdown panel reappears it should subscribe directly
          // here.
          break;

        case "session.ended":
          // Phase D (2026-05-08): unified hangup path. stopAllAudio()
          // clears pending scheduleAudioPlayback timeouts AND tears
          // down useTTS — guarantees no audio plays after this point,
          // closing the "voice continues after hangup" leak. goToResults
          // is idempotent so a concurrent client.hangup that fires the
          // same path doesn't trigger a second redirect.
          if (hangupInProgress || endInFlightRef.current) {
            break;
          }
          stopAllAudio();
          stt.stopListening();
          endInFlightRef.current = true;
          setHangupReason("Звонок завершён");
          setHangupInProgress(true);
          // Phase 5+6 (2026-05-01): give CallEndingTransition its 2.2s
          // animated transition before the route swap so the user sees
          // "Анализирую → Считаю баллы → Готовлю отчёт".
          goToResults(2200);
          break;

        case "client.hangup": {
          const canContinue = Boolean(data.data.call_can_continue);
          logger.log("[CALL] client.hangup received", {
            reason: data.data.reason,
            canContinue,
          });
          if (!canContinue) {
            // Phase D (2026-05-08, Bug 2 fix): respect hangupInProgress.
            // Without this guard, a manual hangup that already started
            // the redirect timer would be re-armed by the backend's
            // client.hangup arriving in parallel — TWO redirects
            // (page flash) + TWO tts.stop calls (cuts farewell audio
            // mid-stream).
            if (hangupInProgress || endInFlightRef.current) {
              break;
            }
            endInFlightRef.current = true;
            // Phase D (2026-05-08, Bug 2 fix): stopAllAudio runs
            // IMMEDIATELY now, not deferred 3500ms. The previous design
            // ("let farewell TTS play") backfired: pilot users perceived
            // post-hangup audio as a glitch — real phones go silent the
            // moment they disconnect. The 3500ms delay only governs the
            // navigation (so the CallEndingTransition gets its full
            // animated arc); audio is silenced at t=0.
            stopAllAudio();
            stt.stopListening();
            setHangupReason((data.data.reason as string) || "Звонок завершён");
            setHangupInProgress(true);
            goToResults(3500);
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
            // Phase D (2026-05-08): also stop audio on this path; if a
            // tts chunk is still in the gate window, it would otherwise
            // play after we land on /results.
            stopAllAudio();
            try { stt.stopListening(); } catch { /* */ }
            goToResults(0);
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
    // PR-C: barge-in feedback channel. The STT handler computes
    // played_chars from the still-running audio element and pushes the
    // event through this ref so the backend can rewrite history before
    // the next text.message arrives. Order matters — interrupt FIRST,
    // text.message SECOND, so the LLM sees the truncated assistant
    // turn when generating the response.
    interruptSendRef.current = (playedChars: number) => {
      if (connectionState !== "connected") return;
      sendMessage({ type: "audio.interrupted", data: { played_chars: playedChars } });
    };
    // PR-F: Whisper-fallback sender. Reads the recorded blob into base64
    // and ships it as audio.end (NOT transcribe_only=true — we want the
    // backend to STT it AND generate the next reply atomically, the
    // same end-to-end behaviour Web Speech gives us). Defensive about
    // empty / tiny blobs that mean «mic was held for half a second».
    sendAudioBlobRef.current = async (blob: Blob) => {
      if (connectionState !== "connected") return;
      if (!blob || blob.size < 2_048) return;
      try {
        const buf = await blob.arrayBuffer();
        let binary = "";
        const bytes = new Uint8Array(buf);
        const chunkSize = 0x8000; // avoid stack overflow on large blobs
        for (let i = 0; i < bytes.length; i += chunkSize) {
          binary += String.fromCharCode(
            ...bytes.subarray(i, i + chunkSize),
          );
        }
        const audio = btoa(binary);
        sendMessage({
          type: "audio.end",
          data: {
            audio,
            mime_type: blob.type || "audio/webm",
          },
        });
      } catch (err) {
        logger.warn("[call] audio.end serialise failed", err);
      }
    };
  }, [sendMessage, connectionState]);

  // PR-F: push-to-talk handlers. ``onPointerDown`` starts MediaRecorder;
  // ``onPointerUp``/``onPointerLeave`` stops + fires the audio.end ref.
  // Holding < 0.4s is treated as a misclick — we just bail without
  // sending anything (size guard in the ref also catches it server-
  // side). Pointer events instead of mouse/touch separately so phones
  // and trackpads behave identically.
  const pushTalkStart = useCallback(async () => {
    if (!microphoneFallback.isSupported) return;
    setPushTalkActive(true);
    const ok = await microphoneFallback.startRecording();
    if (!ok) setPushTalkActive(false);
  }, [microphoneFallback]);

  const pushTalkStop = useCallback(async () => {
    if (!pushTalkActive) return;
    setPushTalkActive(false);
    const blob = await microphoneFallback.stopRecording();
    if (blob) sendAudioBlobRef.current?.(blob);
  }, [microphoneFallback, pushTalkActive]);

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
    logger.log("[CALL] sending session.start");
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
  /*
   * 2026-05-10 FIND-010 fix: stt.startListening / stt.stopListening —
   * useCallback в useSpeechRecognition (stable refs). Раньше они шли
   * в effect через `stt`-объект, deps содержали только триггеры
   * (modeOk/connectionState/muted), а disable перекрывал ESLint.
   * Теперь явно destructure stable methods + isSupported, deps честные.
   */
  const sttStartListening = stt.startListening;
  const sttStopListening = stt.stopListening;
  const sttIsSupported = stt.isSupported;
  useEffect(() => {
    if (modeOk !== true) return;
    if (connectionState !== "connected") return;
    if (muted) {
      sttStopListening();
      return;
    }
    if (!sttIsSupported) return;
    sttStartListening();
  }, [modeOk, connectionState, muted, sttStartListening, sttStopListening, sttIsSupported]);

  // Watchdog: if STT remains idle for ~3s after we asked to listen, retry.
  // Covers transient SpeechRecognition.start() races (Chrome will sometimes
  // silently no-op if a previous instance hadn't fully torn down).
  //
  // Phase D (2026-05-08): exponential backoff instead of fixed 3000ms. The
  // previous fixed retry hammered the SpeechRecognition API every 3 seconds
  // when it was permanently denied (Brave with Shields, denied microphone
  // permission, language not supported) — the user saw the red mic banner
  // blink on/off as start→error→idle→start cycled. Backoff caps at 24s and
  // resets to 3s the moment STT successfully transitions out of idle.
  /*
   * 2026-05-10 FIND-010 fix: те же destructured stable methods.
   * Watchdog effect зависит от sttStatus как триггера, методы из
   * destructure'а выше — стабильны.
   */
  const sttRetryAttemptRef = useRef(0);
  const sttStatus = stt.status;
  useEffect(() => {
    if (modeOk !== true) return;
    if (connectionState !== "connected") return;
    if (muted) return;
    if (!sttIsSupported) return;
    if (sttStatus !== "idle") {
      // Successful start (or any non-idle transition) resets the backoff.
      sttRetryAttemptRef.current = 0;
      return;
    }
    const attempt = sttRetryAttemptRef.current;
    // 3s, 6s, 12s, 24s (cap). After 4 attempts on a permanently-denied
    // browser the cycle settles to one retry every 24s — quiet enough not
    // to thrash, frequent enough to recover if permission is later granted.
    const delay = Math.min(3000 * 2 ** attempt, 24000);
    const t = setTimeout(() => {
      sttRetryAttemptRef.current = attempt + 1;
      sttStartListening();
    }, delay);
    return () => clearTimeout(t);
  }, [modeOk, connectionState, muted, sttStatus, sttIsSupported, sttStartListening]);

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
    // the button react. Now the click visibly commits → 2.2s transition.
    setHangupReason("Звонок завершён");
    setHangupInProgress(true);
    // Phase D (2026-05-08): stopAllAudio cancels deferred audio timeouts
    // BEFORE useTTS.stop runs — so no chunk that's mid-flight in
    // scheduleAudioPlayback can resurrect playback after the user
    // clicked the red button.
    stopAllAudio();
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
    // Phase 5+6 (2026-05-01): give CallEndingTransition its 2.2s window
    // (was 250ms — too quick to register as a transition; user perceived
    // the result page as "appearing instantly"). Replace not push so
    // back-button doesn't return to a dead call.
    goToResults(2200);
  }, [id, stopAllAudio, stt, goToResults]);

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
      // 2026-05-04 (call-mode text fix): user reports "I type, AI doesn't
      // respond" — root cause was a silent WS-not-connected return that
      // cleared neither the input nor surfaced any feedback. Now we show
      // a toast so the user knows WHY the message didn't go through.
      logger.warn("[call] cannot send text — WS not connected", { connectionState });
      try {
        const { toast } = require("sonner") as { toast: { error: (msg: string, opts?: unknown) => void } };
        toast.error("Звонок не подключён", {
          description: "Проверьте интернет и нажмите «Принять» снова.",
        });
      } catch {
        // If toast lib unavailable, the warn() above is the only signal.
      }
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
          logger.log("[CALL] accept-click: running unlock sequence");
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
              logger.log("[CALL] unlock: AudioContext state =", ctx.state);
              setTimeout(() => { try { ctx.close(); } catch { /* */ } }, 500);
            }
            // Vector 2: HTMLAudioElement via blob URL (CSP-safe).
            // Phase B (2026-05-08): RIFF size byte fixed 0x25 → 0x25 wait
            // — file is 45 bytes total, minus 8 (RIFF + size fields) = 37
            // payload bytes, so 0x25 IS correct for the RIFF size field
            // (size of everything after the 8-byte RIFF header). The
            // previous bytes ARE valid; the empirical Safari/iOS
            // rejection observed in pilots was likely the data-chunk
            // size mismatch — `data` chunk declares 0x01 bytes but
            // browsers expect even alignment for 8-bit PCM. Pad to 2
            // bytes (still inaudible) by extending data to 0x02 bytes.
            // Net effect: file size 46, RIFF size 0x26, data size 0x02.
            const silentWav = new Uint8Array([
              0x52, 0x49, 0x46, 0x46, 0x26, 0, 0, 0, 0x57, 0x41, 0x56, 0x45,
              0x66, 0x6d, 0x74, 0x20, 0x10, 0, 0, 0, 1, 0, 1, 0,
              0x40, 0x1f, 0, 0, 0x40, 0x1f, 0, 0, 1, 0, 8, 0,
              0x64, 0x61, 0x74, 0x61, 0x02, 0, 0, 0, 0x80, 0x80,
            ]);
            const blob = new Blob([silentWav], { type: "audio/wav" });
            const url = URL.createObjectURL(blob);
            const a = new Audio(url);
            a.volume = 0.001;
            try {
              await a.play();
              logger.log("[CALL] unlock: HTMLAudio play() succeeded");
            } catch (e) {
              logger.warn("[CALL] unlock: HTMLAudio play() failed:", e);
            }
            URL.revokeObjectURL(url);
            // Vector 3: also poke tts.unlock() if pending.
            try { tts.unlock(); } catch { /* */ }
          } catch (e) {
            logger.warn("[CALL] unlock sequence error:", e);
          }
          // Persist across refresh so F5 doesn't bounce back to incoming.
          // PR-H (B5 defensive): also write to the module-level Set so
          // a remount survives even when sessionStorage is disabled.
          if (id) _ACCEPTED_SESSIONS_RUNTIME.add(id);
          try {
            window.sessionStorage.setItem(`call-accepted-${id}`, "1");
          } catch {
            /* storage quota / private mode — non-fatal, runtime Set covers it */
          }
          // Phase A (2026-05-08): audio gate raised from 350ms to 1500ms.
          // The previous 350ms only covered the pickup-click bundle but
          // let the AI's "Алло?" land WHILE the dialing overlay (1200ms)
          // was still showing — user heard speech under "Соединение..."
          // text. 1500ms holds TTS until the dialing overlay has fully
          // unmounted (220ms fade-out delay below + 1200ms overlay
          // = 1420ms; +80ms safety margin = 1500ms).
          audioGateUntilRef.current = Date.now() + 1500;
          // Phase 1 (2026-05-01): show "Соединение..." dialing overlay
          // for 1200ms over the active call so the transition feels like
          // a real phone connecting, not a teleport into an active call.
          //
          // Phase A (2026-05-08): defer setCallAccepted by 220ms so the
          // IncomingCallScreen has time to fade out (animate via the
          // `accepting` prop) instead of jump-cutting. The dialing
          // overlay's dismiss timer is started AFTER callAccepted flips,
          // so the overlay shows for the full 1200ms from when it
          // actually paints.
          //
          // Phase B (2026-05-08, Bug 1 fix): setDialingOverlay(true) is
          // also DEFERRED into the 220ms timeout. Previously it fired
          // synchronously on click, which painted the dialing overlay's
          // emerald Phone-icon circle UNDER the still-fading
          // IncomingCallScreen Accept button (both at z-50). When the
          // Accept screen faded out, the dialing circle was exposed
          // exactly where the user just clicked — and the pilot read
          // it as "another green Accept button appeared". By deferring
          // both setters into the same timeout, the overlay only
          // mounts AFTER the IncomingCallScreen has unmounted, so the
          // user sees a clean transition instead of a button-shaped
          // crossfade.
          setTimeout(() => {
            setDialingOverlay(true);
            setCallAccepted(true);
            setTimeout(() => setDialingOverlay(false), 1200);
          }, 220);
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
  const wsDead = connectionState === "disconnected" || connectionState === "error";
  const rawBannerKind = pickBannerKind({
    wsDead,
    sttSupported,
    sttErrorCode: stt.errorCode,
    micErrorReason: null,
  });
  // 2026-05-07 (B6): when STT is blocked/unsupported but the Whisper
  // push-to-talk fallback is ready, suppress the loud orange "Голосовое
  // распознавание заблокировано" banner — the Whisper PTT pill below
  // the call view IS the auto-fallback. The banner used to scare users
  // (especially on Brave) into thinking voice was broken when in fact
  // it was already working through the server-side Whisper pipeline.
  // ws_dead always wins — the user must know connectivity is gone.
  const whisperReady = sttBlocked && microphoneFallback.isSupported;
  const bannerKind =
    rawBannerKind === "ws_dead"
      ? rawBannerKind
      : whisperReady &&
          (rawBannerKind === "stt_network" ||
            rawBannerKind === "stt_unsupported")
        ? null
        : rawBannerKind;

  // 2026-04-22: hang-up transition overlay. Shown for the 3.5s between
  // client.hangup/session.ended and the redirect to /results. Covers the
  // entire viewport at z-[100] so any UI flash (chat page, empty call,
  // loading spinner on /results) is invisible to the user. The farewell
  // TTS still plays because it was queued before this render.
  if (hangupInProgress) {
    // Phase E (2026-05-08): unified loader. Was a separate
    // CallEndingTransition (2.2s phone-themed anim) — now uses the
    // same SessionEndingOverlay as the chat route with mode='call'.
    // mode='call' brings back the phone-flavor (PhoneOff icon flash,
    // 300Hz hangup click on mount, reason + stats display) on top of
    // the unified 4-phase backend timeline. The redirect timing is
    // still governed by goToResults(2200|3500) at each hangup call
    // site — the overlay paints continuously until the route changes.
    const callStats: Array<{ label: string; value: string }> = [];
    if (s.elapsed && s.elapsed > 0) {
      const m = Math.floor(s.elapsed / 60);
      const sec = s.elapsed % 60;
      callStats.push({ label: "Длительность", value: `${m}:${sec.toString().padStart(2, "0")}` });
    }
    if (s.stagesCompleted && s.stagesCompleted.length > 0) {
      callStats.push({ label: "Этапов пройдено", value: String(s.stagesCompleted.length) });
    }
    return (
      <SessionEndingOverlay
        visible
        mode="call"
        reason={hangupReason}
        stats={callStats}
      />
    );
  }

  return (
    <>
      {/* Phase 1 of call-flow lifecycle redesign (2026-05-01): "Соединение..."
          overlay covers PhoneCallMode for ~1200ms after Accept-click so the
          transition feels like a real phone connecting. Auto-dismisses via
          setTimeout in the Accept handler. */}
      <CallDialingOverlay visible={dialingOverlay} calleeName={s.characterName} />
      {/* 2026-04-23 Sprint 3: ScriptDrawer floats over PhoneCallMode on
          mobile + narrow windows (it's lg:hidden by default). On desktop
          the plan's merge into PhoneCallMode teleprompter happens
          in-component; here we just guarantee the mobile drawer exists. */}
      <ScriptDrawer
        onCopyExample={(text) => {
          // On call page the main input is the voice mic, but we do
          // have a fallback text field — pre-fill it with the example.
          // B6 (2026-05-03): APPEND to existing text instead of REPLACE.
          setTextInput((cur) => (cur.trim() ? cur + (cur.endsWith(" ") ? "" : " ") + text : text));
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
        onCopyExample={(text) => {
          // User-first §A.2 (2026-04-29): "тап = вставить" on the desktop
          // ScriptPanel example phrases. Pre-A.2 this prop wasn't passed
          // so handleCopy fell through to navigator.clipboard (silent).
          // Now a tap pre-fills the fallback text input — same UX as the
          // mobile ScriptDrawer that already had this wiring.
          // B6 (2026-05-03): APPEND to existing text instead of REPLACE.
          setTextInput((cur) => (cur.trim() ? cur + (cur.endsWith(" ") ? "" : " ") + text : text));
        }}
        micSlot={
          /*
            2026-05-10 (pixel redesign): mic button был rounded-full +
            blur, теперь square pixel 2px solid, font-pixel-лейбл 14px.
            Audio-level glow сохранён для feedback'а (живой пульс при
            активном слушании). Логика TTS-pause + STT не тронута.
          */
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
            className="flex flex-col items-center gap-2"
          >
            <span
              className="flex h-16 w-16 items-center justify-center rounded-sm transition-all duration-150 active:scale-95"
              style={{
                background:
                  stt.status === "listening"
                    ? "rgba(239,68,68,0.95)"
                    : "rgba(167,139,250,0.18)",
                color: stt.status === "listening" ? "#fff" : "var(--accent)",
                border: stt.status === "listening"
                  ? "3px solid #f87171"
                  : "3px solid var(--accent)",
                boxShadow:
                  stt.status === "listening"
                    ? `0 0 ${18 + stt.audioLevel * 38}px rgba(239,68,68,${0.55 + stt.audioLevel * 0.45})`
                    : "0 0 12px var(--accent-glow)",
              }}
            >
              {stt.status === "listening" ? (
                <MicOff size={28} strokeWidth={2.4} />
              ) : (
                <Mic size={28} strokeWidth={2.4} />
              )}
            </span>
            <span
              className="font-pixel uppercase tracking-widest"
              style={{
                color: stt.status === "listening" ? "#f87171" : "var(--text-muted)",
                fontSize: 14,
                letterSpacing: "0.22em",
              }}
            >
              {stt.status === "listening" ? "СЛУШАЮ…" : "ГОВОРИТЬ"}
            </span>
          </button>
        }
      />

      {/*
        2026-05-10 (pixel redesign): Outcome modal был в plain Tailwind
        стиле (rounded-md + bg-emerald-500/red-500/sky-500). Теперь —
        пиксельный стиль: square 2px borders, font-pixel uppercase 14px,
        gradient-фон по цвету исхода, neon glow при ховере. Логика
        completeHangup НЕ ТРОГАЕТСЯ.
      */}
      {showCenterOutcome && !hangupInProgress && (
        <div
          className="fixed inset-0 z-[160] flex items-end justify-center p-4 sm:items-center"
          style={{
            background: "rgba(0,0,0,0.72)",
            backdropFilter: "blur(6px)",
          }}
        >
          <div
            className="w-full max-w-md rounded-sm p-5"
            style={{
              background: "linear-gradient(135deg, rgba(8,5,18,0.95), rgba(16,12,28,0.98))",
              border: "3px solid var(--accent)",
              boxShadow: "0 0 22px var(--accent-glow), inset 0 0 12px rgba(0,0,0,0.4)",
            }}
          >
            <div className="mb-4">
              <div
                className="font-pixel uppercase tracking-widest"
                style={{
                  color: "var(--accent)",
                  fontSize: 18,
                  letterSpacing: "0.18em",
                  textShadow: "0 0 8px var(--accent-glow)",
                }}
              >
                ▰ ИСХОД ЗВОНКА ▰
              </div>
              <div
                className="mt-2 font-pixel uppercase tracking-widest"
                style={{ color: "var(--text-muted)", fontSize: 14, letterSpacing: "0.18em" }}
              >
                Зафиксируем результат — карточка клиента обновится
              </div>
            </div>
            <div className="grid gap-2">
              <button
                type="button"
                className="rounded-sm px-4 py-3 text-left font-pixel uppercase tracking-widest transition-all hover:scale-[1.02]"
                style={{
                  background: "linear-gradient(90deg, rgba(74,222,128,0.22), rgba(74,222,128,0.08))",
                  border: "2px solid #4ade80",
                  color: "#4ade80",
                  fontSize: 14,
                  letterSpacing: "0.18em",
                  boxShadow: "0 0 8px rgba(74,222,128,0.25)",
                }}
                onClick={() => completeHangup("agreed")}
              >
                ✓ ДОГОВОР СОГЛАСОВАН
              </button>
              <button
                type="button"
                className="rounded-sm px-4 py-3 text-left font-pixel uppercase tracking-widest transition-all hover:scale-[1.02]"
                style={{
                  background: "linear-gradient(90deg, rgba(248,113,113,0.22), rgba(248,113,113,0.08))",
                  border: "2px solid #f87171",
                  color: "#f87171",
                  fontSize: 14,
                  letterSpacing: "0.18em",
                  boxShadow: "0 0 8px rgba(248,113,113,0.25)",
                }}
                onClick={() => completeHangup("not_agreed")}
              >
                ✗ ДОГОВОР НЕ СОГЛАСОВАН
              </button>
              <button
                type="button"
                className="rounded-sm px-4 py-3 text-left font-pixel uppercase tracking-widest transition-all hover:scale-[1.02]"
                style={{
                  background: "linear-gradient(90deg, rgba(56,189,248,0.22), rgba(56,189,248,0.08))",
                  border: "2px solid #38bdf8",
                  color: "#38bdf8",
                  fontSize: 14,
                  letterSpacing: "0.18em",
                  boxShadow: "0 0 8px rgba(56,189,248,0.25)",
                }}
                onClick={() => completeHangup("continue")}
              >
                ↻ ПРОДОЛЖИТЬ В ДРУГОМ ЗВОНКЕ
              </button>
              <button
                type="button"
                className="rounded-sm px-4 py-3 font-pixel uppercase tracking-widest transition-colors"
                style={{
                  background: "transparent",
                  border: "2px dashed rgba(255,255,255,0.18)",
                  color: "var(--text-muted)",
                  fontSize: 14,
                  letterSpacing: "0.18em",
                }}
                onClick={() => setShowCenterOutcome(false)}
              >
                ← ВЕРНУТЬСЯ К ЗВОНКУ
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

      {bannerKind && (
        <MicStatusBanner
          kind={bannerKind}
          onRetry={() => stt.startListening()}
        />
      )}

      {/* PR-F (Whisper fallback for call): when Web Speech API is
          blocked by the browser (Brave Shields) or unsupported (Safari
          old / Firefox), expose a push-to-talk button that records a
          blob and POSTs it to the backend Whisper pipeline. The button
          sits above the text input so the user can choose: voice (PTT)
          or keyboard. The pre-existing text input below still works
          regardless. */}
      {sttBlocked && microphoneFallback.isSupported && callAccepted && (
        <div
          className="fixed bottom-[88px] left-1/2 z-30 -translate-x-1/2 flex flex-col items-center gap-2"
          aria-live="polite"
        >
          <button
            type="button"
            onPointerDown={pushTalkStart}
            onPointerUp={pushTalkStop}
            onPointerLeave={() => { if (pushTalkActive) pushTalkStop(); }}
            onPointerCancel={pushTalkStop}
            disabled={connectionState !== "connected"}
            className="flex items-center gap-2 rounded-full px-5 py-3 text-sm font-bold text-white transition-all"
            style={{
              background: pushTalkActive
                ? "linear-gradient(135deg, #ff5f57 0%, #c01f1f 100%)"
                : "linear-gradient(135deg, #7c3aed 0%, #5b21b6 100%)",
              boxShadow: pushTalkActive
                ? "0 0 0 6px rgba(255,95,87,0.25), 0 0 24px rgba(255,95,87,0.6)"
                : "0 4px 16px -4px rgba(124,58,237,0.6)",
              transform: pushTalkActive ? "scale(1.05)" : "scale(1)",
              transition: "transform 0.1s, box-shadow 0.15s, background 0.15s",
              opacity: connectionState === "connected" ? 1 : 0.5,
              touchAction: "none",
            }}
            title="Удерживайте для записи. Whisper-fallback активен."
          >
            {pushTalkActive ? <MicOff size={18} /> : <Mic size={18} />}
            <span>{pushTalkActive ? "Говорите…" : "Удерживайте чтобы говорить"}</span>
          </button>
          <div
            className="rounded-full px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider"
            style={{
              background: "rgba(124,58,237,0.18)",
              color: "#c4b5fd",
              border: "1px solid rgba(124,58,237,0.4)",
            }}
            title="Голос работает через сервер (Whisper). В Brave/Safari/Firefox это рабочий вариант — настраивать ничего не нужно."
          >
            🎤 Голос работает · Whisper
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
      <div className="fixed bottom-0 left-0 right-0 z-20 flex flex-col items-center bg-gradient-to-t from-black/70 to-transparent px-4 pb-3 pt-10">
        {/* 2026-05-04 (radical redesign): chip + paperclip + WS-status dot
            in a tiny secondary bar ABOVE the input. The text input itself
            then takes the full max-w-lg width. User feedback: «панель
            ввода главная — остальное куда хочешь убирай». */}
        <div className="mb-1.5 flex w-full max-w-lg items-center gap-2 px-2">
          <span
            className="flex h-2 w-2 shrink-0 rounded-full"
            style={{
              background: connectionState === "connected" ? "#22c55e" : "#ef4444",
              boxShadow: connectionState === "connected"
                ? "0 0 6px #22c55e"
                : "0 0 6px #ef4444",
              animation: connectionState === "connected" ? undefined : "pulse 1s infinite",
            }}
            title={
              connectionState === "connected"
                ? "Звонок подключён"
                : `WS: ${connectionState} — нажмите «Принять» снова если не восстановится`
            }
            aria-label={`WS status: ${connectionState}`}
          />
          <LinkClientButton
            sessionId={id}
            variant="call"
            disabled={connectionState !== "connected"}
          />
          <SessionAttachmentButton
            sessionId={id}
            variant="call"
            disabled={connectionState !== "connected"}
          />
        </div>
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
            placeholder={
              connectionState === "connected"
                ? "Введите сообщение клиенту…"
                : "Подключаемся… (или нажмите «Принять» заново)"
            }
            aria-label="Сообщение клиенту текстом"
            className="flex-1 bg-transparent px-2 text-base text-white placeholder:text-white/40 outline-none"
            disabled={connectionState !== "connected"}
          />
          <button
            type="submit"
            disabled={!textInput.trim() || connectionState !== "connected"}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white/15 text-white transition-opacity hover:bg-white/25 disabled:cursor-not-allowed disabled:opacity-30"
            aria-label="Отправить сообщение"
          >
            ▶
          </button>
        </form>
      </div>

      <TTSUnlockOverlay visible={tts.needsAudioUnlock} onUnlock={tts.unlock} />
    </>
  );
}
