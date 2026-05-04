"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import dynamic from "next/dynamic";
import {
  XCircle,
  CheckCircle2,
  AlertTriangle,
  Send,
  Volume2,
  VolumeX,
  Radio,
  MessageSquare,
  Mic,
  Loader2,
  Target,
  ListChecks,
  Activity,
} from "lucide-react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useAuthBootstrap } from "@/hooks/useAuthBootstrap";
import { useMicrophone } from "@/hooks/useMicrophone";
import { useSpeechRecognition } from "@/hooks/useSpeechRecognition";
import { useTTS } from "@/hooks/useTTS";
import { MicCheck } from "@/components/training/MicCheck";
import ChatMessage from "@/components/training/ChatMessage";
import { PinnedMessagesBar } from "@/components/training/PinnedMessagesBar";
import { QuoteReplyBadge } from "@/components/training/QuoteReplyBadge";
import { LinkClientButton } from "@/components/training/LinkClientButton";
// NEW-6/7 (2026-05-04): SessionAttachmentButton moved into a kebab menu
// so the textarea regains ~70%+ of the input row. Direct import kept for
// the call view where we apply the same kebab pattern.
import { InputBarMoreMenu } from "@/components/training/InputBarMoreMenu";
// 2026-04-20: CallButton убран из chat-header. Переключение в голосовой
// режим теперь происходит на CRM-карточке клиента (/clients/[id]),
// через отдельные кнопки «Написать / Позвонить» — до входа в сессию,
// а не в середине чата. См. apps/web/src/app/clients/[id]/page.tsx.
// Компонент CallButton.tsx сохранён в /components/training/ на случай
// возврата к inline-переключению в будущем.
import ScriptHints from "@/components/training/ScriptHints";
import { XHunterLogo } from "@/components/ui/XHunterLogo";

const PixelGridBackground = dynamic(
  () => import("@/components/pixel/PixelGridBackground").then((m) => m.PixelGridBackground),
  { ssr: false },
);
import { CrystalMic } from "@/components/training/CrystalMic";
import VibeMeter from "@/components/training/VibeMeter";
import { type CheckpointInfo } from "@/components/training/ScriptAdherence";
import ScriptPanel from "@/components/training/ScriptPanel";
import ScriptDrawer from "@/components/training/ScriptDrawer";
import WhisperPanel from "@/components/training/WhisperPanel";
import { HangupModal } from "@/components/training/HangupModal";
import SessionEndingOverlay from "@/components/training/SessionEndingOverlay";
import { telemetry } from "@/lib/telemetry";
import {
  createHangupCoordinatorState,
  markEndSent,
  armFallback as armFallbackImpl,
  cancelFallback as cancelFallbackImpl,
  resetForNewSession as resetHangupCoordinator,
  type HangupCoordinatorState,
} from "@/lib/hangupCoordinator";
import { TrapNotification, type TrapEvent } from "@/components/training/TrapNotification";
import { ClientCard, type ClientCardData } from "@/components/training/ClientCard";
import { ClientCardMini } from "@/components/training/ClientCardMini";
import { HumanFactorIcons } from "@/components/training/HumanFactorIcons";
import { StoryProgress } from "@/components/training/StoryProgress";
import { ConsequenceToast } from "@/components/training/ConsequenceToast";
import { PreCallBriefOverlay } from "@/components/training/PreCallBriefOverlay";
import TrapLog from "@/components/training/TrapLog";
import TalkListenRatio from "@/components/training/TalkListenRatio";
import LiveEmotionTimeline from "@/components/training/LiveEmotionTimeline";
import DifficultyIndicator from "@/components/training/DifficultyIndicator";
import { StoryCallReportOverlay } from "@/components/training/StoryCallReportOverlay";
import { BetweenCallsOverlay } from "@/components/training/BetweenCallsOverlay";
import { useSessionStore } from "@/stores/useSessionStore";
import { TrainingErrorBoundary } from "@/components/training/TrainingErrorBoundary";
import { TTSUnlockOverlay } from "@/components/training/TTSUnlockOverlay";
import { toast } from "sonner";
import { TrainingToasts } from "@/components/training/TrainingToasts";
import { BootSequence } from "@/components/training/BootSequence";
import { useHotkeys } from "@/hooks/useHotkeys";
import { useSound } from "@/hooks/useSound";
import {
  type EmotionState,
  type ObjectionHint,
  type CheckpointHint,
  type SoftSkillsUpdate,
  EMOTION_MAP,
} from "@/types";
import { logger } from "@/lib/logger";
import { api } from "@/lib/api";

/** Type-safe accessor for untyped WebSocket message data payloads. */
function wsPayload<T>(data: Record<string, unknown>): T {
  return data as T;
}

/**
 * Strip ALL stage directions / action narration from LLM output.
 * Safety net — backend also strips. Handles:
 * - *Italicized action text* (any text between asterisks)
 * - *Unclosed asterisk actions
 * - (keyword stage directions) in parentheses
 */
function stripStageDirections(text: string): string {
  if (!text) return "";
  return text
    .replace(/\*[^*]+\*/g, '')
    .replace(/(?:^|\n)\*[^*\n]+(?:\n|$)/gm, '')
    .replace(/\((?:[Гг]олос|[Пп]ауз|[Тт]их|[Кк]рич|[Пп]лач|[Шш][её]пот|[Вв]здох|[Сс]мех|[Вв]схлип|[Зз]лоб|[Рр]аздраж|[Нн]ервн|[Сс]покойн|[Уу]верен|[Рр]ешительн|[Гг]ромк|[Бб]ыстр|[Мм]едленн|[Оо]бижен|[Сс]аркастич|[Хх]олодн|[Рр]езк|[Мм]ягк|[Ии]спуган|[Дд]рожащ|[Вв]ешает|[Сс]брос|[Дд]ушит|[Дд]авит|[Зз]амолкает|[Вв]ыдыхает|[Вв]здыхает|[Мм]олчит|[Бб]росает|[Тт]рубк|[Сс]тучит|[Хх]лопает)[^)]*\)/gi, '')
    .replace(/  +/g, ' ')
    .replace(/\n\s*\n/g, '\n')
    .trim();
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

async function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      const result = reader.result;
      if (typeof result !== "string") {
        reject(new Error("Audio conversion failed"));
        return;
      }
      const [, base64 = ""] = result.split(",");
      resolve(base64);
    };
    reader.onerror = () => reject(reader.error ?? new Error("Audio conversion failed"));
    reader.readAsDataURL(blob);
  });
}

const StylizedAvatar = dynamic(
  () => import("@/components/training/StylizedAvatar").then((m) => m.StylizedAvatar).catch(() => {
    // If StylizedAvatar fails to load (WebGL not supported, context lost), render nothing
    return () => null;
  }),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-transparent" style={{ borderTopColor: "var(--accent)" }} />
      </div>
    ),
  },
);

export default function TrainingSessionPage() {
  const { ready: authReady } = useAuthBootstrap();
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const routeId = params.id as string;
  const isStoryMode = searchParams.get("mode") === "story";
  const storyScenarioId = isStoryMode ? routeId : null;
  const storyCalls = Math.min(5, Math.max(2, Number(searchParams.get("calls") || "3") || 3));
  const storyArchetype = searchParams.get("custom_archetype") || undefined;
  const storyProfession = searchParams.get("custom_profession") || undefined;
  const storyLeadSource = searchParams.get("custom_lead_source") || undefined;
  const storyDifficulty = searchParams.get("custom_difficulty") ? Number(searchParams.get("custom_difficulty")) : undefined;
  // 2026-04-21: forward the 7 extended builder fields that the old
  // buildStoryQuery was dropping. Keys match what the backend reads off
  // session.custom_params (see app/api/training.py:~325 and
  // app/services/client_generator.generate_client_profile). "random" is a
  // valid sentinel for the 4 context presets — the server unwraps it.
  const storyFamilyPreset = searchParams.get("custom_family_preset") || undefined;
  const storyCreditorsPreset = searchParams.get("custom_creditors_preset") || undefined;
  const storyDebtStage = searchParams.get("custom_debt_stage") || undefined;
  const storyDebtRange = searchParams.get("custom_debt_range") || undefined;
  const storyEmotionPreset = searchParams.get("custom_emotion_preset") || undefined;
  const storyBgNoise = searchParams.get("custom_bg_noise") || undefined;
  const storyTimeOfDay = searchParams.get("custom_time_of_day") || undefined;
  const storyFatigue = searchParams.get("custom_fatigue") || undefined;
  // Constructor v2 tone (2026-04-21): harsh/neutral/lively/friendly.
  const storyTone = searchParams.get("custom_tone") || undefined;
  const storyCustomParams = useMemo(() => ({
    archetype: storyArchetype,
    profession: storyProfession,
    lead_source: storyLeadSource,
    difficulty: storyDifficulty,
    family_preset: storyFamilyPreset,
    creditors_preset: storyCreditorsPreset,
    debt_stage: storyDebtStage,
    debt_range: storyDebtRange,
    emotion_preset: storyEmotionPreset,
    bg_noise: storyBgNoise,
    time_of_day: storyTimeOfDay,
    client_fatigue: storyFatigue,
    tone: storyTone,
  }), [
    storyArchetype, storyProfession, storyLeadSource, storyDifficulty,
    storyFamilyPreset, storyCreditorsPreset, storyDebtStage, storyDebtRange,
    storyEmotionPreset, storyBgNoise, storyTimeOfDay, storyFatigue, storyTone,
  ]);

  // ── Zustand store (replaces 30+ useState) ──
  // Full subscription for render — but NEVER put `s` in useEffect deps!
  // Use useSessionStore.getState() for actions inside effects/callbacks.
  const s = useSessionStore();

  // Initialize store on mount
  useEffect(() => {
    useSessionStore.getState().init(routeId);
    // 2026-04-18: auto-skip MicCheck gate. Must run inside an effect, NOT
    // during render (caused "Cannot update a component while rendering" error).
    useSessionStore.getState().setMicChecked(true);
    // 2026-05-04 (v2): belt-and-suspenders reset — `session.started` and
    // `session.resumed` handlers also clear these refs, but if the route
    // changes (story-mode pivot, deep link from /results back into another
    // session) the parent may keep the component mounted. Resetting on
    // routeId change guarantees the dedupe slate is clean for the new id.
    resetHangupCoordinator(hangupRef.current);
    return () => {
      useSessionStore.getState().reset();
      wsTimersRef.current.forEach(clearTimeout);
      wsTimersRef.current = [];
      cancelFallbackImpl(hangupRef.current, { reason: "unmount" });
    };
  }, [routeId]);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const wsTimersRef = useRef<ReturnType<typeof setTimeout>[]>([]);
  const sessionEndedRef = useRef<{ score: number | null; xp: number | null; levelUp: boolean }>({ score: null, xp: null, levelUp: false });
  // 2026-05-04 (v2): hangup coordinator — owns the dedupe slate +
  // fallback timer for the post-hangup race. See @/lib/hangupCoordinator
  // for the contract; the page uses it through the four wrappers below.
  // Extracted to a pure module so it can be unit-tested without booting
  // the whole page (see __tests__/hangup-flow.test.tsx).
  const hangupRef = useRef<HangupCoordinatorState>(createHangupCoordinatorState());
  const storyBootstrappedRef = useRef(false);
  // 2026-04-18 audit fix: in story-mode, each new call spawns a NEW
  // TrainingSession backend-side. The URL's `routeId` stays the initial
  // session id forever. We track the LIVE session id here so REST calls
  // (end, results redirect, session_hijacked recovery) hit the right row.
  const currentSessionIdRef = useRef<string>(routeId);
  const [storyTransitionText, setStoryTransitionText] = useState(
    isStoryMode ? "ИНИЦИАЛИЗАЦИЯ AI-ИСТОРИИ..." : "ПОДКЛЮЧЕНИЕ К СЕССИИ..."
  );
  // 2026-04-23: full-screen "Завершаем тренировку" overlay shown between
  // handleEnd() click and router.replace → /results. Prevents the 5-15s
  // dead-air window while backend is scoring.
  const [ending, setEnding] = useState(false);
  const [storyCallReport, setStoryCallReport] = useState<{
    callNumber: number;
    score: number;
    keyMoments: string[];
    consequences: Array<{ call: number; type: string; severity: number; detail: string }>;
    memoriesCreated: number;
    isFinal: boolean;
  } | null>(null);
  const [activeConsequence, setActiveConsequence] = useState<import("@/types/story").ConsequenceEvent | null>(null);
  const [personalChallenge, setPersonalChallenge] = useState<string | null>(null);
  const [scoreHint, setScoreHint] = useState<{
    script_adherence: number;
    objection_handling: number;
    communication: number;
    anti_patterns: number;
    result: number;
    chain_traversal: number;
    trap_handling: number;
    human_factor: number;
    realtime_estimate: number;
    max_possible_realtime: number;
  } | null>(null);
  const [preferBrowserSpeech, setPreferBrowserSpeech] = useState(false);
  const [sttWarningDismissed, setSttWarningDismissed] = useState(false);
  // 2026-05-03 redesign: right-sidebar tab state. Replaces the 9-panel
  // always-on stack that pushed "Баллы" off-screen on most viewports.
  // Mirrors the 3-pill switcher used on /pvp ("arena|knowledge|history").
  type SidebarTab = "score" | "script" | "reactions";
  const [sidebarTab, setSidebarTab] = useState<SidebarTab>("score");

  // Auto-dismiss STT warning after 5 seconds
  useEffect(() => {
    if (!s.sttAvailable && s.sessionState === "ready" && !sttWarningDismissed) {
      const t = setTimeout(() => setSttWarningDismissed(true), 5000);
      return () => clearTimeout(t);
    }
  }, [s.sttAvailable, s.sessionState, sttWarningDismissed]);

  // ── Micro-animation states ──
  const [scorePulse, setScorePulse] = useState(false);
  const [checkpointFlash, setCheckpointFlash] = useState(false);
  const prevScriptScoreRef = useRef(s.scriptScore);
  const prevCheckpointsRef = useRef(s.checkpointsHit);

  // ── Score change pulse animation ──
  useEffect(() => {
    if (s.scriptScore !== prevScriptScoreRef.current && s.scriptScore > 0) {
      setScorePulse(true);
      const t = setTimeout(() => setScorePulse(false), 600);
      prevScriptScoreRef.current = s.scriptScore;
      return () => clearTimeout(t);
    }
  }, [s.scriptScore]);

  // ── Checkpoint hit celebration ──
  useEffect(() => {
    if (s.checkpointsHit > prevCheckpointsRef.current) {
      setCheckpointFlash(true);
      const t = setTimeout(() => setCheckpointFlash(false), 800);
      prevCheckpointsRef.current = s.checkpointsHit;
      return () => clearTimeout(t);
    }
  }, [s.checkpointsHit]);

  // Sound effect for difficulty mode changes (boss/safe)
  const { playSound } = useSound();
  const difficultyMode = useSessionStore((st) => st.difficultyMode);
  const prevDifficultyModeRef = useRef(difficultyMode);
  useEffect(() => {
    if (prevDifficultyModeRef.current !== difficultyMode) {
      if (difficultyMode === "boss") playSound("epic", 0.4);
      else if (difficultyMode === "safe") playSound("fail", 0.3);
      prevDifficultyModeRef.current = difficultyMode;
    }
  }, [difficultyMode, playSound]);

  // TTS — ElevenLabs (primary) + browser speechSynthesis (fallback)
  const tts = useTTS({ lang: "ru-RU", rate: 0.95, pitch: 1.0 });

  // Surface terminal TTS errors / fallback transitions as toasts. Mirror
  // of /call page handler — chat path used the same useTTS pipeline but
  // had no UI surface for any of these failure modes. Audit Pattern 3
  // #9 + #15.
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
  const microphone = useMicrophone({
    onSilenceTimeout: () => useSessionStore.getState().setShowSilenceModal(true),
  });

  // Compute last sequence number for session resume
  const lastSeqNum = s.messages.length > 0
    ? s.messages.reduce((max, m) => Math.max(max, m.sequenceNumber ?? 0), 0) || null
    : null;

  const { sendMessage, connectionState } = useWebSocket({
    sessionId: s.sessionId || null,
    lastSequenceNumber: lastSeqNum,
    onMessage: (data) => {
      // Global guard: ensure data.data is always an object (never undefined)
      if (!data.data || typeof data.data !== "object") data.data = {};
      logger.log(`[WS] ${data.type}`, data.type === "tts.audio" ? `(audio ${(data.data?.audio_b64 as string)?.length || 0} chars)` : data.data);
      switch (data.type) {
        case "auth.success":
        case "session.ready":
          break;

        case "session.started":
          setStoryTransitionText("ЗВОНОК АКТИВЕН");
          // 2026-04-18 audit fix: track the LIVE session_id. In story mode
          // each call creates a new TrainingSession row; without this the
          // URL's routeId would drift and all REST calls (end, results
          // redirect) would target the first call forever.
          if (data.data.session_id) {
            currentSessionIdRef.current = data.data.session_id as string;
          }
          // 2026-05-04 (v2): reset session.end dedupe + clear any stale
          // hangup-fallback timer for the new session. Story-mode reuses
          // the same component instance across multiple calls — without
          // this reset, the second/third call would silently skip
          // session.end (the dedupe ref stays true forever).
          resetHangupCoordinator(hangupRef.current);
          if (data.data.character_name) s.setCharacterName(data.data.character_name as string);
          if (data.data.initial_emotion) s.setEmotion(data.data.initial_emotion as EmotionState);
          if (data.data.scenario_title) s.setScenarioTitle(data.data.scenario_title as string);
          if (data.data.archetype_code) s.setArchetypeCode(data.data.archetype_code as string);
          if (data.data.character_gender) s.setCharacterGender(data.data.character_gender as "M" | "F" | "neutral");
          if (data.data.client_card) {
            s.setClientCard(data.data.client_card as ClientCardData);
            s.setSessionState("briefing");
          } else {
            s.setSessionState("ready");
          }
          break;

        case "avatar.typing":
          s.setIsTyping(data.data.is_typing as boolean);
          break;

        case "character.response_chunk": {
          // SYNC: text chunks are intentionally NOT rendered here.
          // Text is revealed together with audio via `tts.audio_chunk.text`
          // (or all at once via `character.response` if TTS fails).
          // This keeps text and voice 1:1 synchronized instead of text
          // racing ahead of audio by 300-500ms per sentence.
          break;
        }

        case "character.response": {
          s.setIsTyping(false);
          // Deduplicate by sequence_number (may overlap with message.replay)
          const seq = data.data?.sequence_number as number | undefined;
          if (seq != null && s.messages.some(m => m.sequenceNumber === seq)) break;
          const rawContent = (data.data?.content as string) || "";
          const content = stripStageDirections(rawContent);
          // 2026-04-18: dup-fix. Previous logic finalized only if the IMMEDIATELY
          // last message was streaming. If another message (user reply, trap hint,
          // etc.) arrived between streaming chunks and character.response, the
          // check failed and a second duplicate bubble was added.
          // New logic:
          //   1. Find the most recent streaming assistant message (any position).
          //   2. If found — finalize it with the full content.
          //   3. If not found but same content already exists in last 5 — no-op.
          //   4. Otherwise — add as new message.
          const recentMsgs = s.messages.slice(-5);
          const streamingAssistant = [...recentMsgs].reverse()
            .find((m) => m.role === "assistant" && m.isStreaming);
          // Fuzzy match: any recent assistant msg whose content contains or
          // is contained by the incoming content (handles streaming-then-final).
          const trimmedContent = content.trim();
          const fuzzyMatch = recentMsgs.find(
            (m) => m.role === "assistant" && (
              m.content.trim() === trimmedContent ||
              m.content.includes(trimmedContent) ||
              (trimmedContent.length > 20 && trimmedContent.includes(m.content.trim()))
            ),
          );
          if (streamingAssistant) {
            s.finalizeStreamingMessage(content, data.data.emotion as EmotionState | undefined, seq);
          } else if (fuzzyMatch) {
            // Already rendered via streaming path — skip duplicate.
            // (If content slightly differs, we keep the first one that arrived.)
            logger.log("[WS] character.response: content already present (fuzzy match), skipping dup");
          } else {
            s.addMessage({
              id: s.nextMsgId(),
              role: "assistant",
              content,
              emotion: data.data.emotion as EmotionState | undefined,
              timestamp: new Date().toISOString(),
              sequenceNumber: seq,
            });
          }
          if (data.data.emotion) s.setEmotion(data.data.emotion as EmotionState);
          if (data.data.script_score !== undefined) s.setScriptScore(data.data.script_score as number);
          s.setListenTime(s.listenTime + 1);
          // Refresh script hints now that the client has responded — next
          // suggestions should be based on the new conversation state.
          s.refreshScriptHints();
          break;
        }

        case "tts.audio": {
          tts.cancelFallback();
          const audioB64 = data.data.audio_b64 as string;
          if (audioB64 && typeof audioB64 === "string") {
            tts.playAudioMessage({
              audio: audioB64,
              emotion: data.data.emotion as EmotionState | undefined,
              voice_params: data.data.voice_params as { stability: number; similarity_boost: number; style: number; speed: number } | undefined,
              duration_ms: data.data.duration_ms as number | undefined,
            });
          } else {
            logger.warn("[WS] tts.audio received but audio_b64 is not a string:", typeof audioB64);
          }
          break;
        }

        case "tts.audio_chunk": {
          // Sentence-level TTS streaming: audio AND text arrive together.
          // Text is revealed in the chat bubble synchronously with audio playback.
          tts.cancelFallback();
          const chunkAudio = data.data.audio_b64 as string;
          const chunkText = (data.data?.text as string) || "";

          // 1. Append text to current assistant message (creating if missing).
          // 2026-04-18 ROOT-CAUSE fix: ordering is not guaranteed.
          //   Case A: tts.audio_chunk arrives BEFORE character.response
          //           → build up streaming bubble from chunks, finalize later
          //   Case B: character.response arrives FIRST with full content
          //           → final msg exists; chunks' text is SUBSTRING of final
          //           → we must SKIP chunks (don't create dup streaming bubble)
          if (chunkText) {
            const recent = s.messages.slice(-5);
            const trimmedChunk = chunkText.trim();
            // Case B: chunk text already present inside a recent assistant msg → skip
            const alreadyPresent = recent.some(
              (m) => m.role === "assistant" &&
                     !m.isStreaming &&
                     m.content.includes(trimmedChunk),
            );
            if (alreadyPresent) {
              // Chunk text already rendered via character.response — do nothing.
              // (TTS audio still queued below for playback.)
            } else {
              const streamingInRecent = [...recent].reverse()
                .find((m) => m.role === "assistant" && m.isStreaming);
              if (streamingInRecent) {
                s.appendToLastAssistantMessage(chunkText + " ");
              } else {
                s.addMessage({
                  id: s.nextMsgId(),
                  role: "assistant",
                  content: chunkText + " ",
                  timestamp: new Date().toISOString(),
                  isStreaming: true,
                });
              }
            }
          }

          // 2. Queue audio for sequential playback (in sentence order).
          if (chunkAudio && typeof chunkAudio === "string") {
            tts.queueAudioChunk({
              audio: chunkAudio,
              index: data.data.sentence_index as number,
              isLast: Boolean(data.data.is_last),
            });
          }
          break;
        }

        case "tts.fallback":
          logger.warn("[TTS] ElevenLabs fallback received:", data.data.reason);
          // Switch to browser Web Speech API so the user still hears the AI
          tts.enableFallbackMode();
          // Clear any partially-queued chunks from the failed streaming synth
          tts.resetChunkQueue();
          break;

        case "session.ended":
          tts.stop();
          if (timerRef.current) clearInterval(timerRef.current);
          {
            // H2 fix: both story mode and single-call get immediate results
            // NOTE: don't flip sessionState="completed" for story-mode mid-call
            // endings — StoryCallReportOverlay needs to be rendered, which
            // requires sessionState to stay non-terminal until final call.
            const ended = data.data as Record<string, unknown> | undefined;
            const endedScores = ended?.scores as Record<string, number> | undefined;
            sessionEndedRef.current = {
              score: (endedScores?.total as number) ?? null,
              xp: null, // XP arrives later via session.xp_update (C4 fix)
              levelUp: false,
            };
            if (isStoryMode) {
              setStoryTransitionText("ЗВОНОК ЗАВЕРШЁН. ФОРМИРУЕМ ОТЧЁТ...");
              // 2026-04-18 audit fix: use currentSessionIdRef (live id) not
              // routeId (stale URL id). Also: only fallback-redirect if we
              // haven't received story.call_report after 15s — which would
              // indicate a backend hang.
              setTimeout(() => {
                const st = useSessionStore.getState();
                if (st.sessionState === "completed" && !storyCallReport) {
                  // Story fallback: go to story summary if we have story id,
                  // otherwise single-call results.
                  if (st.storyMode && st.storyId) {
                    router.push(`/stories/${st.storyId}`);
                  } else {
                    router.push(`/results/${currentSessionIdRef.current || routeId}`);
                  }
                }
              }, 15000);
            } else {
              // 2026-04-23: instant redirect (0ms). Session-ending overlay
              // (set via handleEnd → ending=true) covered the whole
              // scoring window; session.ended is the signal to land on
              // /results. router.replace so back-button doesn't re-open
              // the dead chat. Also ensure overlay state is set in case
              // backend auto-ended via silence/hangup (user didn't click).
              s.setSessionState("completed");
              setEnding(true);
              // 2026-05-04: success path — cancel the 5s fallback so we
              // don't double-navigate (success replace already lands).
              // 2026-05-04 (v2): emits a console.info so the
              // fallback-fire-rate dashboard has a denominator.
              cancelFallbackImpl(hangupRef.current, {
                reason: "ack",
                sessionId: currentSessionIdRef.current || routeId,
              });
              router.replace(`/results/${currentSessionIdRef.current || routeId}`);
            }
          }
          break;

        case "session.xp_update":
          // C4 fix: XP/level arrives after background processing
          {
            const xpData = data.data as Record<string, unknown> | undefined;
            const xpBreakdown = xpData?.xp_breakdown as Record<string, number> | undefined;
            if (sessionEndedRef.current) {
              sessionEndedRef.current.xp = (xpBreakdown?.grand_total as number) ?? null;
              sessionEndedRef.current.levelUp = Boolean(xpData?.level_up);
            }
          }
          break;

        case "transcription.result": {
          const text = data.data.text as string;
          const isEmpty = data.data.is_empty as boolean;
          if (isEmpty || !text) {
            s.setTranscription({ status: "idle", partial: "", final: "" });
          } else {
            // Show preview — user confirms before sending
            s.setTranscription({ status: "preview", partial: "", final: text });
            // Put text into input for editing
            s.setInput(text);
          }
          break;
        }

        case "stt.unavailable":
        case "stt.error": {
          // 2026-05-03 prod bug fix: when backend rejects short audio
          // ("Audio too short (433 bytes)") it sends stt.unavailable
          // but the previous handler forgot to clear `transcription.status`
          // — left at "transcribing" from when audio.end was sent. The
          // "Распознаю: речь..." indicator stays on screen forever, even
          // though the request already finished. User reports
          // "бесконечное распознавание речи" maps exactly to this.
          // Reset status + surface the backend message via toast so user
          // knows what happened.
          s.setTranscription({ status: "idle", partial: "", final: "" });
          const msg =
            (data.data?.message as string | undefined) ||
            "Не удалось распознать. Попробуйте говорить чуть длиннее.";
          import("@/stores/useNotificationStore").then(({ useNotificationStore }) => {
            useNotificationStore.getState().addToast({
              title: "Распознавание не удалось",
              body: msg,
              type: "warning",
            });
          }).catch(() => {/* notification store unavailable */});

          if (speech.isSupported) {
            setPreferBrowserSpeech(true);
            s.setSttAvailable(true);
            s.setTextMode(false);
          } else {
            s.setSttAvailable(false);
            s.setTextMode(true);
          }
          break;
        }

        case "emotion.update":
          if (data.data.current) {
            s.setEmotion(data.data.current as EmotionState);
            s.addEmotionToHistory(data.data.current as EmotionState);
          }
          break;

        case "stage.update":
          s.setStageUpdate(wsPayload<import("@/types").StageUpdate>(data.data));
          // Bug fix 2026-04-17: ScriptHints должны перечитываться при
          // смене стадии скрипта продаж — иначе 3 карточки-подсказки
          // наверху зависают на старых. Раньше refresh происходил только
          // после character.response, stage.update его не триггерил.
          s.refreshScriptHints();
          break;

        case "stage.skipped": {
          // 2026-04-23 Sprint 3: backend signals user jumped past one or
          // more script stages. ScriptPanel / ScriptDrawer renders a
          // yellow-bordered hint card pointing to the missed stage.
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
              hint: sd.hint ?? "Вернитесь и закройте этот этап — клиент это заметил.",
              setAt: Date.now(),
            });
            // 2026-04-23 gap-fill: fire telemetry so post-demo analytics
            // can see how often users skip ahead (and which stages).
            telemetry.track("stage_skipped", {
              missed: sd.missed_stage_number,
              current: sd.current_stage_number ?? s.currentStage,
            });
          }
          break;
        }

        case "score.update":
          if (data.data.script_score !== undefined) s.setScriptScore(data.data.script_score as number);
          if (data.data.checkpoints_hit !== undefined) s.setCheckpointsHit(data.data.checkpoints_hit as number);
          if (data.data.checkpoints_total !== undefined) s.setCheckpointsTotal(data.data.checkpoints_total as number);
          if (Array.isArray(data.data.checkpoints)) s.setCheckpoints(data.data.checkpoints as CheckpointInfo[]);
          // new_checkpoint: set if present, clear if not (only flash once per match)
          s.setNewCheckpoint(data.data.new_checkpoint ? (data.data.new_checkpoint as string) : null);
          if (data.data.is_preliminary !== undefined) s.setIsPreliminaryScore(data.data.is_preliminary as boolean);
          // Bug fix 2026-04-17: checkpoint hit → подсказки устарели
          if (data.data.new_checkpoint) {
            s.refreshScriptHints();
          }
          break;

        case "score.hint":
          // B9: All 8 real-time layers
          setScoreHint({
            script_adherence: Number(data.data.script_adherence || 0),
            objection_handling: Number(data.data.objection_handling || 0),
            communication: Number(data.data.communication || 0),
            anti_patterns: Number(data.data.anti_patterns || 0),
            result: Number(data.data.result || 0),
            chain_traversal: Number(data.data.chain_traversal || 0),
            trap_handling: Number(data.data.trap_handling || 0),
            human_factor: Number(data.data.human_factor || 0),
            realtime_estimate: Number(data.data.realtime_estimate || 0),
            max_possible_realtime: Number(data.data.max_possible_realtime || 0),
          });
          // 2026-05-03: removed `s.setRealtimeScores(...)` write —
          // the consuming `<RealtimeScores>` panel was removed during
          // the redesign and the slice had no other readers. Keeping
          // a setter that nobody read kept renders alive on every
          // score.hint and added store churn for no reason. Sub-scores
          // now render directly from local `scoreHint` useState.
          break;

        case "silence.warning":
          s.setSilenceWarning(true);
          wsTimersRef.current.push(setTimeout(() => s.setSilenceWarning(false), 5000));
          break;

        case "silence.timeout":
          s.setShowSilenceModal(true);
          break;

        case "session.takeover_by_self":
          // Another tab/remount for the same user took over this session.
          // Close silently — the "new" connection is handling the session now.
          // Do NOT redirect, do NOT call /end, do NOT flip to completed.
          tts.stop();
          if (timerRef.current) clearInterval(timerRef.current);
          break;

        case "session.timeout":
          s.setSessionState("completed");
          if (timerRef.current) clearInterval(timerRef.current);
          break;

        case "client.hangup_warning":
          s.setHangupWarning((data.data.message as string) || "Клиент теряет терпение...");
          // Auto-dismiss after 5 seconds
          wsTimersRef.current.push(setTimeout(() => s.setHangupWarning(null), 5000));
          break;

        case "client.hangup": {
          const canContinue = Boolean(data.data.call_can_continue);
          s.setHangupData({
            reason: (data.data.reason as string) || "",
            hangupPhrase: (data.data.hangup_phrase as string) || "",
            canContinue,
            triggers: (data.data.triggers as string[]) || [],
          });
          s.setShowHangupModal(true);
          // C3 fix: auto-send session.end for single-call hangup after 3s
          // so backend can clean up (no zombie sessions).
          // 2026-05-04: dedupe via sessionEndSentRef — if the user clicks
          // "К результатам" before this 3s timer fires, the click path
          // already sent session.end and we must not double-send (backend
          // replies with error: session_completed and the timing of the
          // redirect drifts by 10–60s).
          if (!canContinue) {
            wsTimersRef.current.push(
              setTimeout(() => {
                // 2026-05-04 (v2): also arm the 5s router-fallback for
                // the silent-user path. Previously, if the user did NOT
                // click "К результатам" and session.ended was delayed
                // by 60s (slow scoring / WS lag), they were stuck on
                // the dead chat behind the modal. armHangupFallback()
                // navigates to /results in 5s if session.ended doesn't
                // arrive first (the success path cancels it).
                armHangupFallback();
                if (markEndSent(hangupRef.current)) {
                  sendMessage({ type: "session.end", data: {} });
                }
              }, 3000),
            );
          }
          break;
        }

        case "trap.triggered": {
          const trapEvent: TrapEvent = {
            trap_name: data.data.trap_name as string,
            category: data.data.category as TrapEvent["category"],
            status: data.data.status as TrapEvent["status"],
            score_delta: data.data.score_delta as number,
            wrong_keywords: (data.data.wrong_keywords as string[]) || [],
            correct_keywords: (data.data.correct_keywords as string[]) || [],
            client_phrase: (data.data.client_phrase as string) || "",
            correct_example: (data.data.correct_example as string) || "",
          };
          s.setActiveTrap(trapEvent);
          s.addTrapToHistory(trapEvent);
          s.adjustTrapNetScore(trapEvent.score_delta);
          if (trapEvent.status === "fell" || trapEvent.status === "partial") {
            s.addTrapFell();
          } else if (trapEvent.status === "dodged") {
            s.addTrapDodged();
          }
          break;
        }

        case "trap.personal_challenge": {
          // Personal Challenge Toast: "Ловушка X победила тебя N раз. Попробуешь ещё?"
          const challengeMsg = (data.data.message as string) || `Ловушка «${data.data.trap_name}» бросает вызов!`;
          setPersonalChallenge(challengeMsg);
          wsTimersRef.current.push(setTimeout(() => setPersonalChallenge(null), 5000));
          break;
        }

        case "hint.objection": {
          const hint: ObjectionHint = {
            category: data.data.category as ObjectionHint["category"],
            message: data.data.message as string,
          };
          s.setObjectionHint(hint);
          wsTimersRef.current.push(setTimeout(() => s.setObjectionHint(null), 4000));
          break;
        }

        case "hint.checkpoint": {
          const cpHint: CheckpointHint = {
            checkpoint: data.data.checkpoint as string,
            status: data.data.status as CheckpointHint["status"],
          };
          s.setCheckpointHint(cpHint);
          wsTimersRef.current.push(setTimeout(() => s.setCheckpointHint(null), 3000));
          break;
        }

        case "whisper.coaching": {
          const whisper: import("@/types").CoachingWhisper = {
            type: data.data.type as import("@/types").WhisperType,
            message: data.data.message as string,
            stage: data.data.stage as string,
            priority: data.data.priority as "high" | "medium" | "low",
            icon: data.data.icon as string,
            timestamp: Date.now(),
          };
          s.addWhisper(whisper);
          break;
        }

        // P2 (2026-04-29) — coaching mistake detector toasts in chat mode.
        // Same payload as call mode (see call/page.tsx for mapping rationale).
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
          break;
        }

        case "whisper.toggle_ack":
          if (data.data.enabled !== undefined) s.setWhispersEnabled(data.data.enabled as boolean);
          break;

        case "soft_skills.update": {
          const skills = wsPayload<SoftSkillsUpdate>(data.data);
          if (skills.talk_ratio !== undefined) {
            const serverTalk = Math.round(skills.talk_ratio * 100);
            s.setTalkTime(serverTalk);
            s.setListenTime(100 - serverTalk);
          }
          break;
        }

        case "difficulty.update": {
          const diffUpdate = wsPayload<import("@/stores/useSessionStore").DifficultyUpdate>(data.data);
          s.setDifficultyUpdate(diffUpdate);
          // Generate difficulty change reason
          const reason = diffUpdate.had_comeback
            ? "Восстановление после серии ошибок"
            : diffUpdate.good_streak >= 3
              ? `Серия верных ответов (${diffUpdate.good_streak}) — сложность растёт`
              : diffUpdate.bad_streak >= 3
                ? `Серия ошибок (${diffUpdate.bad_streak}) — сложность снижается`
                : diffUpdate.mode === "boss"
                  ? "Режим босса: максимальная сложность"
                  : diffUpdate.mode === "safe"
                    ? "Безопасный режим: пониженная сложность"
                    : null;
          s.setDifficultyReason(reason);
          break;
        }

        case "tts.couple_audio":
          tts.cancelFallback();
          if (data.data?.utterances) {
            tts.playCoupleAudio({
              utterances: (data.data.utterances as Array<{ speaker: string; audio_b64: string; text: string }>).map((u) => ({
                speaker: u.speaker as "A" | "B" | "AB",
                audio: u.audio_b64,
              })),
            });
          }
          break;

        // ── Story-mode messages ──
        case "story.started":
          storyBootstrappedRef.current = true;
          setStoryTransitionText("ПОДГОТОВКА ПЕРВОГО ЗВОНКА...");
          s.setStoryMode(data.data.story_id as string, data.data.total_calls as number);
          s.setCharacterName(data.data.client_name as string || "Клиент");
          break;

        case "story.pre_call_brief":
          s.setPreCallBrief(wsPayload<import("@/types/story").PreCallBrief>(data.data));
          s.setHumanFactors(
            ((data.data as { active_factors?: import("@/types/story").HumanFactor[] }).active_factors) || []
          );
          setStoryTransitionText(`БРИФИНГ ЗВОНКА #${String(data.data.call_number || "")}`);
          s.setShowPreCallBrief(true);
          break;

        case "story.between_calls":
          s.setBetweenCallsEvents(data.data.events as Array<{ event_type: string; title: string; content: string; severity: number | null }>);
          s.setShowBetweenCalls(true);
          break;

        case "story.call_ready":
          s.setCallNumber(data.data.call_number as number);
          setStoryTransitionText(`ЗАПУСК ЗВОНКА #${String(data.data.call_number || "")}...`);
          break;

        case "story.state_delta":
          if (Array.isArray(data.data.active_factors)) {
            s.setHumanFactors(data.data.active_factors as import("@/types/story").HumanFactor[]);
          }
          if (data.data.new_consequence) {
            const consequence = data.data.new_consequence as import("@/types/story").ConsequenceEvent;
            s.addConsequence(consequence);
            setActiveConsequence(consequence);
            wsTimersRef.current.push(setTimeout(() => {
              setActiveConsequence((current) => (
                current && current.call === consequence.call && current.type === consequence.type ? null : current
              ));
            }, 4500));
          }
          break;

        case "story.call_report": {
          // 2026-04-18 audit fix: trust the backend's `is_final` flag
          // rather than comparing callNumber >= totalCalls on the client,
          // which could race with the store update from story.call_ready.
          const _cn = Number(data.data.call_number || 1);
          const _tc = Number(data.data.total_calls || s.totalCalls || 3);
          const _isFinal = data.data.is_final === true || _cn >= _tc;
          setStoryCallReport({
            callNumber: _cn,
            score: Number(data.data.score || 0),
            keyMoments: Array.isArray(data.data.key_moments) ? (data.data.key_moments as string[]) : [],
            consequences: Array.isArray(data.data.consequences)
              ? (data.data.consequences as Array<{ call: number; type: string; severity: number; detail: string }>)
              : [],
            memoriesCreated: Number(data.data.memories_created || 0),
            isFinal: _isFinal,
          });
          break;
        }

        case "story.progress":
          s.setCallNumber(data.data.call_number as number);
          setStoryTransitionText("ГОТОВИМ СЛЕДУЮЩИЙ ЗВОНОК...");
          break;

        case "story.completed": {
          // 2026-04-18 audit fix: don't auto-navigate while the user is
          // still reading StoryCallReportOverlay. The backend sends
          // `story.completed` right after the final `story.call_report`
          // (same function) — if we just router.push immediately, the
          // user sees the report overlay for ~900ms and then gets yanked
          // to the story summary without ever clicking "Open final".
          //
          // Instead: stop the TTS + timer so the "completed" state is
          // clean, and let the user press the overlay's own button. The
          // overlay's onContinue handler will then navigate.
          //
          // If for some reason no overlay is showing (e.g. forced end
          // via `story.end`, or a race where the report never arrived),
          // navigate immediately as a fallback.
          tts.stop();
          if (timerRef.current) clearInterval(timerRef.current);
          const _storyId = data.data.story_id as string | undefined;
          // Check if StoryCallReportOverlay will show (or already is).
          // We peek state via getState() since `storyCallReport` closure
          // may be stale in this handler callback.
          if (!storyCallReport) {
            s.setSessionState("completed");
            if (_storyId) {
              setTimeout(() => router.push(`/stories/${_storyId}`), 900);
            }
          }
          // If storyCallReport IS set, do nothing — the overlay's
          // onContinue handler will take care of navigation with its
          // own setTimeout, avoiding a double router.push race.
          break;
        }

        // ── v6: Session resume messages ──
        case "session.resumed":
          // Clear local messages before replay to prevent duplicates —
          // locally-added messages lack sequenceNumber so replay dedup misses them.
          s.clearMessages();
          s.setEmotion(data.data.emotion as EmotionState);
          s.setElapsed(Math.floor(data.data.elapsed_seconds as number));
          // 2026-04-18 audit fix: also update currentSessionIdRef so REST
          // calls hit the resumed session, not the initial routeId.
          if (data.data.session_id) {
            currentSessionIdRef.current = data.data.session_id as string;
          }
          // 2026-05-04 (v2): a resumed session is by definition not yet
          // ended — clear the dedupe ref so a subsequent hangup can
          // actually fire session.end.
          resetHangupCoordinator(hangupRef.current);
          // 2026-04-18 audit fix: restore story HUD state on reconnect.
          // Without this, a reconnect in the middle of a 5-call chain
          // showed "call 0/0" and the story HUD bar disappeared.
          if (data.data.story_id && data.data.total_calls) {
            s.setStoryMode(data.data.story_id as string, data.data.total_calls as number);
            if (data.data.call_number != null) {
              s.setCallNumber(data.data.call_number as number);
            }
            storyBootstrappedRef.current = true;
          }
          // C2 fix: restore full session state on reconnect
          if (data.data.character_name) s.setCharacterName(data.data.character_name as string);
          if (data.data.archetype_code) s.setArchetypeCode(data.data.archetype_code as string);
          if (data.data.scenario_title) s.setScenarioTitle(data.data.scenario_title as string);
          if (data.data.character_gender) s.setCharacterGender(data.data.character_gender as "M" | "F" | "neutral");
          if (data.data.client_card) {
            s.setClientCard(data.data.client_card as ClientCardData);
          }
          // Sort messages by sequence number to ensure correct order after replay
          s.sortMessagesBySequence();
          s.setSessionState("ready");
          // Restart elapsed timer
          if (timerRef.current) clearInterval(timerRef.current);
          timerRef.current = setInterval(() => s.tickElapsed(), 1000);
          logger.log("[WS] Session resumed:", data.data.session_id);
          break;

        case "message.replay": {
          // Add replayed message if not already in store (dedupe by sequence_number)
          const seq = data.data.sequence_number as number | undefined;
          const alreadyExists = seq != null && s.messages.some((m) => m.sequenceNumber === seq);
          if (!alreadyExists) {
            s.addMessage({
              id: s.nextMsgId(),
              role: data.data.role as "user" | "assistant",
              content: data.data.content as string,
              emotion: data.data.emotion as EmotionState | undefined,
              timestamp: data.data.timestamp
                ? new Date((data.data.timestamp as number) * 1000).toISOString()
                : new Date().toISOString(),
              sequenceNumber: seq,
              isReplay: true,
            });
          }
          break;
        }

        case "error": {
          const errMsg = typeof data.data.message === "string" ? data.data.message : "Неизвестная ошибка";
          const errCode = data.data.code as string | undefined;
          // 2026-04-22: log known graceful exits at info level — they're
          // not actual errors. The browser console kept showing scary
          // "Training error: session_completed" right before normal redirect
          // to /results, which made support tickets look like crashes.
          const _gracefulCodes = new Set(["session_completed", "session_locked", "session_hijacked"]);
          if (errCode && _gracefulCodes.has(errCode)) {
            logger.log("[training] graceful event:", errCode);
          } else {
            logger.error("Training error:", errCode || errMsg);
          }

          // 2026-04-18: graceful handling of terminal session states so user
          // doesn't see "Неизвестная ошибка" when trying to continue / rejoin.
          if (errCode === "session_completed") {
            logger.log("[training] Session already completed → navigating to /results");
            s.setSessionState("completed");
            // 2026-04-18 audit fix: for story-mode, redirect to the
            // story summary page instead of the single-call results.
            // For regular sessions, use the live session id (may have
            // drifted from URL routeId if session was resumed).
            const _sid = currentSessionIdRef.current || routeId;
            if (s.storyMode && s.storyId) {
              setTimeout(() => router.push(`/stories/${s.storyId}`), 400);
            } else {
              setTimeout(() => router.push(`/results/${_sid}`), 400);
            }
            break;
          }
          if (errCode === "session_not_found") {
            logger.warn("[training] Session not found → back to /training");
            setTimeout(() => router.push("/training"), 400);
            break;
          }
          if (errCode === "session_locked") {
            logger.warn("[training] Session locked by another connection — waiting for auto-reconnect");
            break;
          }

          // Session was taken over by another tab/connection.
          //
          // 2026-04-21: dropped the auto-end + redirect to /results.
          // In prod this fires spuriously on reconnect / fast-refresh /
          // brief network blips, and every time it happened the user got
          // their session ended and shoved into /results — losing their
          // in-progress dialogue. useWebSocket already auto-reconnects;
          // if a second tab is truly driving the session the user will
          // notice and close one manually.
          //
          // Keep the observability — just no destructive side effect.
          // Dev guard kept in case the chat page is ever re-extended to
          // react to legitimate hijacks.
          if (errCode === "session_hijacked") {
            logger.warn("[training] session_hijacked (non-fatal, letting WS reconnect)", data.data);
          }
          break;
        }
      }
    },
  });

  // Web Speech API STT
  const speech = useSpeechRecognition({
    lang: "ru-RU",
    onResult: (text) => {
      s.addMessage({ id: s.nextMsgId(), role: "user", content: text, timestamp: new Date().toISOString() });
      sendMessage({ type: "text.message", data: { content: text } });
      s.setTalkTime(s.talkTime + 1);
      s.setTranscription({ status: "done", partial: "", final: text });
      // Detect goodbye phrases and show hangup confirmation
      // 2026-04-18: extended list per user feedback — "клади трубку", "клади" were not detected.
    const goodbyePhrases = [
      "досвидания", "до свидания", "прощай", "прощайте", "пока",
      "всего доброго", "до встречи", "счастливо",
      "клади трубку", "клади", "кладу трубку", "кладу",
      "вешай трубку", "вешаю трубку", "положу трубку", "положи трубку",
      "закругляемся", "закругляюсь", "завершаю разговор", "завершаю звонок",
    ];
      const lowerText = text.toLowerCase().trim();
      if (goodbyePhrases.some(p => lowerText.includes(p))) {
        s.setShowHangupModal(true);
      }
    },
    onInterim: (text) => {
      s.setTranscription({ status: "transcribing", partial: text, final: "" });
    },
    onError: (error) => {
      if (error === "not-allowed" || error === "unsupported") {
        s.setSttAvailable(false);
        s.setTextMode(true);
      }
    },
  });

  // Session start on WS connect
  const sessionState = useSessionStore((st) => st.sessionState);
  useEffect(() => {
    if (connectionState === "connected" && sessionState === "connecting") {
        if (isStoryMode) {
          if (!storyBootstrappedRef.current && storyScenarioId) {
            setStoryTransitionText("ЗАПУСК AI-ИСТОРИИ...");
            sendMessage({
              type: "story.start",
              data: {
                scenario_id: storyScenarioId,
                total_calls: storyCalls,
                custom_params: storyCustomParams,
              },
            });
          }
        } else {
          sendMessage({ type: "session.start", data: { session_id: routeId } });
      }
    }
  }, [connectionState, sessionState, routeId, sendMessage, isStoryMode, storyScenarioId, storyCalls, storyCustomParams]);

  // Handle WS disconnect / reconnecting
  useEffect(() => {
    const st = useSessionStore.getState();
    if ((connectionState === "disconnected" || connectionState === "reconnecting") && st.sessionState !== "completed") {
      st.setConnectionState(connectionState);
    }
  }, [connectionState, sessionState]);

  // Timer
  useEffect(() => {
    if (sessionState === "ready") {
      timerRef.current = setInterval(() => useSessionStore.getState().tickElapsed(), 1000);
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [sessionState]);

  // 2026-04-18: MUCH more reliable auto-scroll.
  // Previous impl depended on the ref identity of s.messages (Zustand may not
  // trigger re-render if slice happens inside a reducer). Now we:
  //   1. Listen to messages.length + last-message.content (streaming updates)
  //   2. Directly scrollTop the container instead of scrollIntoView the sentinel
  //   3. Use requestAnimationFrame to run AFTER paint (fixes "scroll before layout")
  const lastContentLen =
    s.messages.length > 0 ? (s.messages[s.messages.length - 1]?.content || "").length : 0;

  // 2026-04-18: auto-resize textarea when input changes programmatically
  // (quote-reply, STT transcription insert). onInput only fires on user typing.
  useEffect(() => {
    const t = textareaRef.current;
    if (!t) return;
    t.style.height = "auto";
    t.style.height = Math.min(t.scrollHeight, 240) + "px";
  }, [s.input]);
  useEffect(() => {
    // Target the training-chat-scroll container by id (reliable even if refs get stale)
    const container = typeof document !== "undefined"
      ? document.getElementById("training-chat-scroll")
      : null;
    const doScroll = () => {
      if (container) {
        container.scrollTop = container.scrollHeight;
      } else {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
      }
    };
    // Multi-shot: RAF immediate, 120ms retry (streaming), 500ms final (layout settle)
    const raf = requestAnimationFrame(doScroll);
    const t1 = setTimeout(doScroll, 120);
    const t2 = setTimeout(doScroll, 500);
    return () => {
      cancelAnimationFrame(raf);
      clearTimeout(t1);
      clearTimeout(t2);
    };
  }, [s.messages.length, lastContentLen, s.transcription.status, s.isTyping]);

  // Typing watchdog: if the AI "typing" indicator is stuck for > 45s without
  // any response arriving, force-clear it so the UI isn't permanently frozen.
  // Protects against backend hangs in LLM or TTS.
  useEffect(() => {
    if (!s.isTyping) return;
    const t = setTimeout(() => {
      logger.warn("[training] isTyping watchdog fired — forcing false after 45s");
      s.setIsTyping(false);
    }, 45_000);
    return () => clearTimeout(t);
  }, [s.isTyping]);  // eslint-disable-line react-hooks/exhaustive-deps

  // P3-30: Global keyboard shortcuts via useHotkeys
  useHotkeys(s.sessionState === "ready" ? "training" : "global", [
    {
      key: "Space",
      action: "startMic",
      scope: "training",
      handler: () => {
        if (!s.textMode && s.sttAvailable && !s.micActive) handleMicPress();
      },
    },
    {
      key: "Space",
      action: "stopMic",
      scope: "training",
      keyup: true,
      handler: () => handleMicRelease(),
    },
    {
      key: "Escape",
      action: "toggleAbort",
      scope: "training",
      handler: () => s.setShowAbortModal(!s.showAbortModal),
    },
  ]);

  const formatTime = (sec: number) =>
    `${Math.floor(sec / 60).toString().padStart(2, "0")}:${(sec % 60).toString().padStart(2, "0")}`;

  const handleSend = () => {
    const text = s.input.trim();
    if (!text || s.sessionState !== "ready" || s.isTyping) return;
    // Block sending when WS is not connected — messages would be buffered silently
    if (connectionState !== "connected") {
      logger.warn("[Training] Send blocked: WS not connected (state=%s)", connectionState);
      return;
    }
    // 2026-04-19 Phase 2.6: attach quote metadata (id + preview) if the
    // user replied to a specific bubble. Both go on the optimistic user
    // bubble (so the quoted block renders immediately) and into the WS
    // payload (so the server can inject a quote section into the prompt).
    const quotedId = s.pendingQuotedId ?? undefined;
    const quotedPreview = s.pendingQuotedPreview ?? undefined;
    s.addMessage({
      id: s.nextMsgId(),
      role: "user",
      content: text,
      timestamp: new Date().toISOString(),
      quotedMessageId: quotedId,
      quotedPreview: quotedPreview,
    });
    sendMessage({
      type: "text.message",
      data: {
        content: text,
        ...(quotedId ? { quoted_message_id: quotedId } : {}),
      },
    });
    s.clearPendingQuote();
    s.setInput("");
    s.setTalkTime(s.talkTime + 1);
    // Detect goodbye phrases and show hangup confirmation
    // 2026-04-18: extended list per user feedback — "клади трубку", "клади" were not detected.
    const goodbyePhrases = [
      "досвидания", "до свидания", "прощай", "прощайте", "пока",
      "всего доброго", "до встречи", "счастливо",
      "клади трубку", "клади", "кладу трубку", "кладу",
      "вешай трубку", "вешаю трубку", "положу трубку", "положи трубку",
      "закругляемся", "закругляюсь", "завершаю разговор", "завершаю звонок",
    ];
    const lowerText = text.toLowerCase().trim();
    if (goodbyePhrases.some(p => lowerText.includes(p))) {
      s.setShowHangupModal(true);
    }
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  // 2026-04-23: instant overlay so user sees feedback right away. Backend
  // takes 5-15s to score + AI-coach + RAG, but the click should never feel
  // unresponsive. Overlay self-renders phase progress while we wait for
  // session.ended WS event to fire the actual redirect.
  // 2026-05-04: dedupe send + arm fallback redirect so the user is never
  // stuck if session.ended is delayed/dropped (5s timeout → /results).
  const handleEnd = () => {
    setEnding(true);
    if (markEndSent(hangupRef.current)) {
      sendMessage({ type: "session.end", data: {} });
    }
    armHangupFallback();
  };

  // 2026-05-04 (v2): thin wrapper around the pure coordinator. Owns the
  // navigation side-effect (router.replace) since the coordinator is
  // intentionally DOM-free. Logs are baked into the coordinator's
  // default loggers (console.warn) so the dashboard sees them.
  const armHangupFallback = () => {
    const sid = currentSessionIdRef.current || routeId;
    armFallbackImpl(hangupRef.current, {
      sessionId: sid,
      onFire: (firedSid) => {
        const st = useSessionStore.getState();
        // Don't fight the success path — if session.ended already
        // moved us to /results, just bail.
        if (st.sessionState === "completed") return;
        // Mark completed so the navigation doesn't trigger a
        // "session active" re-render loop on the dead chat.
        s.setSessionState("completed");
        router.replace(`/results/${firedSid}`);
      },
    });
  };

  const handleMicPress = async () => {
    if (s.sessionState === "ready" && s.sttAvailable) {
      if (tts.speaking) tts.stop();
      if (microphone.isSupported && !preferBrowserSpeech) {
        const started = await microphone.startRecording();
        if (started) {
          s.setMicActive(true);
          return;
        }
      }

      if (speech.isSupported) {
        speech.startListening();
        s.setMicActive(true);
        return;
      }

      // 2026-04-22: explicit feedback when no STT path is available.
      // Most common cause is browsers blocking mic permission silently —
      // user kept tapping the button and "nothing happened". Show toast
      // with actionable hint so they know to allow mic in browser settings.
      try {
        const { useNotificationStore } = await import("@/stores/useNotificationStore");
        useNotificationStore.getState().addToast({
          title: "Микрофон недоступен",
          body: "Разрешите доступ к микрофону в настройках сайта (значок замка слева от адресной строки) или используйте текстовый ввод.",
          type: "warning",
        });
      } catch {
        /* notification store unavailable in this build — silent fallback */
      }

      s.setTextMode(true);
      s.setSttAvailable(false);
    }
  };

  const handleMicRelease = async () => {
    if (microphone.recordingState === "recording" && !preferBrowserSpeech) {
      const blob = await microphone.stopRecording();
      s.setMicActive(false);
      // 2026-05-03 prod bug guard: a tap (vs hold) produces a ~400-byte
      // blob that backend Whisper rejects as "Audio too short", which
      // emits stt.unavailable. We pre-empt that round-trip when the
      // blob is implausibly small for actual speech (~2 KB ≈ 80 ms of
      // opus). User gets immediate feedback instead of waiting for the
      // backend response.
      const TOO_SHORT_BYTES = 2_048;
      if (blob && blob.size > 0 && blob.size < TOO_SHORT_BYTES) {
        s.setTranscription({ status: "idle", partial: "", final: "" });
        try {
          const { useNotificationStore } = await import("@/stores/useNotificationStore");
          useNotificationStore.getState().addToast({
            title: "Слишком короткое нажатие",
            body: "Удерживайте кнопку микрофона и говорите хотя бы секунду.",
            type: "warning",
          });
        } catch { /* notification store unavailable */ }
        return;
      }
      if (blob && blob.size > 0) {
        try {
          s.setTranscription({ status: "transcribing", partial: "", final: "" });
          const audio = await blobToBase64(blob);
          // Send for transcription only — don't process until user confirms
          sendMessage({
            type: "audio.end",
            data: {
              audio,
              mime_type: blob.type || "audio/webm",
              transcribe_only: true,
            },
          });
          // 2026-04-22: watchdog — if backend STT is down (Whisper
          // crashed/loading/network blip) the transcription.result event
          // never arrives and the "Распознаю: речь..." bar sits forever.
          // 45s timeout covers Whisper cold-start (6-10s) + slow backend.
          window.setTimeout(() => {
            const cur = useSessionStore.getState().transcription;
            if (cur.status === "transcribing") {
              logger.warn("[training] STT watchdog: no result in 45s — resetting");
              useSessionStore.getState().setTranscription({ status: "idle", partial: "", final: "" });
              import("@/stores/useNotificationStore").then(({ useNotificationStore }) => {
                useNotificationStore.getState().addToast({
                  title: "Распознавание не удалось",
                  body: "Сервис распознавания не ответил. Попробуйте ещё раз или введите текстом.",
                  type: "warning",
                });
              }).catch(() => {/* ignore */});
            }
          }, 45000);
        } catch {
          s.setTranscription({ status: "idle", partial: "", final: "" });
          if (speech.isSupported) {
            speech.startListening();
            s.setMicActive(true);
            return;
          }
          s.setTextMode(true);
        }
      } else {
        s.setTranscription({ status: "idle", partial: "", final: "" });
      }
      return;
    }

    if (speech.status === "listening") {
      speech.stopListening();
      s.setMicActive(false);
    }
  };

  const handleContinueSession = () => {
    s.setShowSilenceModal(false);
    sendMessage({ type: "silence.continue", data: {} });
  };

  // Track talk/listen time — 1s interval (uses getState() to avoid stale closures)
  const ttsRef = useRef(tts.speaking);
  ttsRef.current = tts.speaking;
  useEffect(() => {
    if (sessionState !== "ready") return;
    const iv = setInterval(() => {
      const state = useSessionStore.getState();
      if (state.micActive) {
        useSessionStore.setState({ talkTime: state.talkTime + 1 });
      } else if (state.isTyping || ttsRef.current) {
        useSessionStore.setState({ listenTime: state.listenTime + 1 });
      }
    }, 1000);
    return () => clearInterval(iv);
  }, [sessionState]);

  const talkPercent = s.talkTime + s.listenTime > 0 ? Math.round((s.talkTime / (s.talkTime + s.listenTime)) * 100) : 50;
  const emotionValue = EMOTION_MAP[s.emotion]?.value ?? 10;
  const emotionLabel = EMOTION_MAP[s.emotion]?.labelRu ?? "Нейтральный";
  const rawTrust = s.clientCard?.trust_level;
  const rawResistance = s.clientCard?.resistance_level;
  const negativeFactorPenalty = s.humanFactors.reduce((sum, factor) => {
    if (["distrust", "fear", "anger", "stress", "fatigue", "sadness"].includes(factor.factor)) {
      return sum + factor.intensity * 9;
    }
    return sum;
  }, 0);
  const positiveFactorBoost = s.humanFactors.reduce((sum, factor) => {
    if (factor.factor === "empathy") {
      return sum + factor.intensity * 8;
    }
    return sum;
  }, 0);
  const trustScore = rawTrust ?? Math.round(emotionValue / 10);
  const resistanceScore = rawResistance ?? clamp(10 - Math.round(emotionValue / 12), 1, 10);
  const consequencePenalty = s.consequences.reduce((sum, consequence) => sum + consequence.severity * 7, 0);
  const acceptanceScore = clamp(
    Math.round(
      emotionValue * 0.45 +
      trustScore * 3.2 +
      (10 - resistanceScore) * 2.4 +
      positiveFactorBoost -
      negativeFactorPenalty -
      consequencePenalty
    ),
    0,
    100
  );
  const acceptanceLabel =
    acceptanceScore >= 80 ? "Готов к сделке" :
    acceptanceScore >= 60 ? "Сильный интерес" :
    acceptanceScore >= 40 ? "Осторожный интерес" :
    acceptanceScore >= 20 ? "Сомневается" :
    "Закрыт";
  const pressureScore = clamp(
    Math.round(
      s.consequences.reduce((sum, consequence) => sum + consequence.severity * 18, 0) +
      s.humanFactors.reduce((sum, factor) => sum + factor.intensity * 12, 0)
    ),
    0,
    100
  );

  // ── Connecting gate — pixel boot sequence ──
  if (s.sessionState === "connecting" && !s.showPreCallBrief && !storyCallReport) {
    // Minimal loader — replaces noisy "terminal boot" animation
    return (
      <div
        className="flex min-h-screen items-center justify-center"
        style={{ background: "var(--bg-primary)" }}
      >
        <div className="flex flex-col items-center gap-3">
          <Loader2 size={28} className="animate-spin" style={{ color: "var(--accent)" }} />
          <span className="font-mono text-xs uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
            Подключение к сессии...
          </span>
        </div>
      </div>
    );
  }

  // ── Briefing gate ──
  if (s.sessionState === "briefing" && s.clientCard) {
    return (
      <ClientCard
        clientCard={s.clientCard}
        scenarioTitle={s.scenarioTitle || "Тренировка"}
        onStart={() => s.setSessionState("ready")}
        onBack={() => {
          sendMessage({ type: "session.end", data: {} });
          router.push("/training");
        }}
      />
    );
  }

  // ── MicCheck gate — 2026-04-18 DISABLED ──
  // Per user feedback: "убери панель выбора, пусть на автомате перенесёт
  // на аудио". Session goes STRAIGHT to chat now.

  // Wait for auth bootstrap (token refresh via cookie if needed) before rendering
  if (!authReady) {
    return (
      <div className="flex h-screen items-center justify-center" style={{ background: "var(--bg-primary)" }}>
        <Loader2 size={28} className="animate-spin" style={{ color: "var(--accent)" }} />
      </div>
    );
  }

  return (
    <TrainingErrorBoundary sessionId={routeId}>
    <div className="flex h-screen flex-col overflow-hidden" style={{ background: "var(--bg-primary)" }}>

      {/* Global mic glow */}
      <div className={`fixed inset-0 global-mic-glow z-50 ${s.micActive ? "active" : ""}`} />

      {/* ── Top HUD Header — pixel game style ────────────── */}
      <header
        className="shrink-0 flex justify-between items-center px-5 lg:px-8 z-20"
        style={{ height: 60, background: "rgba(3,3,6,0.92)", backdropFilter: "blur(20px)", borderBottom: "2px solid var(--accent)" }}
      >
        {/* Left: XHUNTER logo (replaces scenario info which was noisy) */}
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <XHunterLogo size="sm" />
          {s.storyMode && (
            <span className="font-pixel text-[10px] hidden sm:inline" style={{ color: "var(--text-muted)" }}>
              ЗВОНОК {s.callNumber}/{s.totalCalls}
            </span>
          )}
        </div>

        {/* Center: timer — pixel game style */}
        <div className="flex items-center gap-2">
          <div
            className={`font-pixel text-xl font-bold tabular-nums pixel-glow ${s.elapsed >= 1500 ? "animate-pulse" : ""}`}
            style={{ color: s.elapsed >= 1500 ? "var(--warning)" : "var(--accent)" }}
          >
            {formatTime(s.elapsed)}
          </div>
        </div>

        {/* Right: controls */}
        <div className="flex items-center gap-3 flex-1 justify-end">
          {/* 2026-04-20: блок CallButton удалён. Вход в голосовой режим
              теперь строго через CRM-карточку /clients/[id]. Это убирает
              путаницу "зачем живой звонок внутри чата" — выбор chat vs
              voice происходит ДО старта сессии. */}
          <motion.button
            onClick={() => tts.setEnabled(!tts.enabled)}
            className="flex items-center justify-center rounded-xl p-2"
            style={{ background: "rgba(255,255,255,0.04)" }}
            whileTap={{ scale: 0.95 }}
            aria-label={tts.enabled ? "Выключить голос AI" : "Включить голос AI"}
            title={`Голос AI: ${tts.mode === "elevenlabs" ? "ElevenLabs" : "Браузер"}`}
          >
            {tts.enabled ? <Volume2 size={18} style={{ color: "var(--accent)" }} /> : <VolumeX size={18} style={{ color: "var(--text-muted)" }} />}
          </motion.button>

          <button
            onClick={() => s.setShowAbortModal(true)}
            disabled={s.sessionState !== "ready"}
            className="rounded-xl px-4 py-2 text-sm font-semibold transition-all"
            style={{ background: "var(--danger-muted)", color: "var(--danger)", border: "1px solid rgba(239,68,68,0.25)" }}
            aria-label="Прервать тренировку"
          >
            Завершить
          </button>
        </div>
      </header>

      {/* Connection status toast — only when there's a problem */}
      <AnimatePresence>
        {connectionState !== "connected" && (
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="fixed top-2 left-1/2 -translate-x-1/2 z-50 rounded-xl px-4 py-2 text-sm font-medium flex items-center gap-2"
            style={{
              background: connectionState === "reconnecting" ? "var(--warning-muted)" : "var(--danger-muted)",
              border: `1px solid ${connectionState === "reconnecting" ? "rgba(245,158,11,0.3)" : "rgba(239,68,68,0.3)"}`,
              color: connectionState === "reconnecting" ? "var(--warning)" : "var(--danger)",
              backdropFilter: "blur(12px)",
            }}
          >
            <div className="w-2 h-2 rounded-full animate-pulse" style={{ background: connectionState === "reconnecting" ? "var(--warning)" : "var(--danger)" }} />
            {connectionState === "reconnecting" ? "Переподключение..." : "Нет связи"}
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Client Card Mini ──────────────────────────────── */}
      {s.clientCard && s.sessionState === "ready" && (
        <ClientCardMini
          clientCard={s.clientCard}
          isExpanded={s.miniCardExpanded}
          onToggle={() => s.setMiniCardExpanded(!s.miniCardExpanded)}
        />
      )}

      {/* ── Story-mode HUD bar ──────────────────────────────── */}
      {s.storyMode && s.sessionState === "ready" && (
        <div className="flex items-center gap-4 px-6 py-2 z-20" style={{ borderBottom: "1px solid var(--border-color)" }}>
          <StoryProgress callNumber={s.callNumber} totalCalls={s.totalCalls} />
          {s.humanFactors.length > 0 && <HumanFactorIcons factors={s.humanFactors} />}
        </div>
      )}

      {/* ── PreCallBrief overlay (story mode) ────────────── */}
      {s.showBetweenCalls && s.betweenCallsEvents.length > 0 && (
        <BetweenCallsOverlay
          callNumber={s.callNumber || s.preCallBrief?.call_number || 1}
          totalCalls={s.totalCalls}
          events={s.betweenCallsEvents}
          onContinue={() => s.setShowBetweenCalls(false)}
        />
      )}

      {s.showPreCallBrief && s.preCallBrief && !s.showBetweenCalls && (
        <PreCallBriefOverlay
          brief={s.preCallBrief}
          onStart={() => {
            s.setShowPreCallBrief(false);
            setStoryTransitionText(`ЗАПУСК ЗВОНКА #${s.preCallBrief?.call_number || s.callNumber}...`);
            s.setSessionState("connecting");
            sendMessage({ type: "session.start", data: { scenario_id: storyScenarioId, custom_params: storyCustomParams } });
          }}
        />
      )}

      {storyCallReport && (
        <StoryCallReportOverlay
          callNumber={storyCallReport.callNumber}
          totalCalls={s.totalCalls}
          score={storyCallReport.score}
          keyMoments={storyCallReport.keyMoments}
          consequences={storyCallReport.consequences}
          memoriesCreated={storyCallReport.memoriesCreated}
          isFinal={storyCallReport.isFinal}
          onContinue={() => {
            // 2026-04-18 audit fix: final call no longer dead-ends.
            //   - Tell the backend to finalize the story via `story.end`
            //     (the `story.completed` auto-emit will also fire, but
            //     sending `story.end` guarantees DB state even if the
            //     socket was flaky).
            //   - Navigate to /stories/:id for the CRM summary page
            //     (previously we just set sessionState="completed" and
            //     the user stared at a blank screen).
            const isFinal = storyCallReport.isFinal;
            const storyId = s.storyId;
            setStoryCallReport(null);
            if (isFinal) {
              if (storyId) {
                sendMessage({ type: "story.end", data: { story_id: storyId } });
                setStoryTransitionText("ЗАВЕРШАЕМ ИСТОРИЮ...");
                // Stop the in-call timer so the "completed" view is clean
                tts.stop();
                if (timerRef.current) clearInterval(timerRef.current);
                s.setSessionState("completed");
                // Navigate. The backend will ALSO emit story.completed
                // which navigates — whichever fires first wins. Both
                // land on the same route, so it's idempotent.
                setTimeout(() => router.push(`/stories/${storyId}`), 900);
              } else {
                // No story id (shouldn't happen, but fallback safely):
                s.setSessionState("completed");
                setTimeout(() => router.push("/training"), 600);
              }
              return;
            }
            s.resetCallState();
            setStoryTransitionText("ГОТОВИМ СЛЕДУЮЩИЙ ЗВОНОК...");
            sendMessage({ type: "story.next_call", data: { story_id: s.storyId } });
          }}
        />
      )}

      {/* ── Consequence toast (story mode) ────────────────── */}
      {activeConsequence && (
        <ConsequenceToast
          consequence={activeConsequence}
          onDismiss={() => setActiveConsequence(null)}
        />
      )}

      {/* ── Personal Challenge Toast (trap failed 2+ times) ── */}
      {personalChallenge && (
        <div
          style={{
            position: "fixed",
            top: "5rem",
            left: "50%",
            transform: "translateX(-50%)",
            zIndex: 999,
            padding: "1rem 1.5rem",
            borderRadius: 12,
            background: "linear-gradient(135deg, rgba(245,158,11,0.15) 0%, rgba(239,68,68,0.12) 100%)",
            border: "1px solid rgba(245,158,11,0.4)",
            backdropFilter: "blur(12px)",
            maxWidth: 420,
            textAlign: "center",
            animation: "shake 0.5s ease-in-out, fadeIn 0.3s ease-out",
            boxShadow: "0 0 30px rgba(245,158,11,0.2)",
          }}
        >
          <div style={{ fontSize: "1.5rem", marginBottom: "0.25rem" }}>⚔️</div>
          <p style={{
            margin: 0,
            fontSize: "0.9rem",
            fontWeight: 600,
            color: "var(--warning)",
            lineHeight: 1.4,
          }}>
            {personalChallenge}
          </p>
          <button
            onClick={() => setPersonalChallenge(null)}
            style={{
              marginTop: "0.5rem",
              padding: "0.3rem 0.8rem",
              borderRadius: 6,
              background: "rgba(245,158,11,0.2)",
              border: "1px solid rgba(245,158,11,0.3)",
              color: "var(--warning)",
              fontSize: "0.8rem",
              cursor: "pointer",
              fontWeight: 600,
            }}
          >
            Принимаю вызов!
          </button>
        </div>
      )}

      {/* ── 3-Column Layout ─────────────────────────────────── */}
      <main className="flex-1 min-h-0 z-20 px-3 py-2 lg:px-4 lg:py-3" style={{ width: "min(100%, var(--app-shell-max))", marginInline: "auto" }}>
        <div className="training-session-grid">
        {/* LEFT: Chat Panel — 2026-04-18:
            • Stronger pixel-grid bg so panel isn't empty-looking
            • Visible ACCENT border so user sees chat boundary (complained:
              "нет границы, не видно где чат а где центр экрана") */}
        <aside className="training-session-panel training-session-panel--chat hidden lg:flex flex-col rounded-2xl overflow-hidden relative"
          style={{
            background: "var(--bg-primary)",
            backgroundImage: `
              radial-gradient(ellipse at 50% 15%, var(--accent-muted) 0%, transparent 55%),
              repeating-linear-gradient(0deg, transparent 0, transparent 27px, rgba(107,77,199,0.045) 27px, rgba(107,77,199,0.045) 28px),
              repeating-linear-gradient(90deg, transparent 0, transparent 27px, rgba(107,77,199,0.045) 27px, rgba(107,77,199,0.045) 28px)
            `,
            // Clear violet boundary so the panel stands out from the central chat.
            border: "2px solid var(--accent)",
            boxShadow: "0 0 0 1px rgba(107,77,199,0.25), 4px 4px 0 0 rgba(107,77,199,0.15)",
          }}
        >
          {/* Keep decorative pixel grid on top for extra depth */}
          <div className="absolute inset-0 pointer-events-none opacity-30">
            <PixelGridBackground variant="platform" />
          </div>

          {/* Accent strip */}
          <div className="h-[3px] shrink-0 relative z-10" style={{ background: "linear-gradient(90deg, transparent, var(--accent), transparent)" }} />

          {/* Messages area (z-10 keeps messages above the grid background) */}
          {/* 2026-04-18 scroll fix: explicit min-h-0 on flex parent forces proper
              inner scrollbar, padding-bottom gives breathing room above input bar */}
          <div
            id="training-chat-scroll"
            className="flex-1 px-5 py-4 overflow-y-auto space-y-3 flex flex-col min-h-0 relative z-10"
            style={{ paddingBottom: 24, scrollbarWidth: "auto", scrollbarColor: "rgba(107,77,199,0.45) transparent" }}
          >
            {/* 2026-04-18 pinning feature: bar appears when any message is pinned */}
            <PinnedMessagesBar
              messages={s.messages}
              onUnpin={(id) => s.togglePinMessage(id)}
            />
            {s.messages.map((msg) => (
              <ChatMessage
                key={msg.id}
                message={msg}
                onTogglePin={() => s.togglePinMessage(msg.id)}
                onReply={(content) => {
                  // 2026-04-19 Phase 2.6: quote-reply goes through the store
                  // so (a) a QuoteReplyBadge can preview it, (b) the next
                  // text.message WS send carries `quoted_message_id`, and
                  // (c) the server-side llm prompt injects a ## ЦИТАТА
                  // МЕНЕДЖЕРА section to force in-context answers.
                  const preview = content.length > 160 ? content.slice(0, 160) + "…" : content;
                  s.setPendingQuote({ id: msg.id, preview });
                  setTimeout(() => textareaRef.current?.focus(), 30);
                }}
              />
            ))}

            {s.isTyping && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex items-center gap-2 py-1.5 text-sm" style={{ color: "var(--text-muted)" }}>
                <div className="flex gap-0.5">
                  {[0, 1, 2].map((i) => (
                    <motion.span key={i} className="h-1.5 w-1.5 rounded-full" style={{ background: "var(--accent)" }} animate={{ y: [0, -4, 0] }} transition={{ duration: 0.5, repeat: Infinity, delay: i * 0.15 }} />
                  ))}
                </div>
                {s.characterName} печатает...
              </motion.div>
            )}

            {/* 2026-04-22: TranscriptionIndicator REMOVED from inside the
                scroll area — it was floating with the messages, making the
                "Распознавание речи..." panel jump around. Live partial-
                transcript is now shown above the input bar (see below),
                anchored to the input area instead of the scroll content. */}

            {/* 2026-04-20: ScriptHints redesign — replaced the sticky bottom
                banner with a floating FAB+popover (rendered as a sibling of
                the scroll container, not inside it, so it doesn't scroll
                with the messages). The FAB anchors to the chat aside's
                bottom-right, pulses when new hints arrive, and the popover
                auto-closes when the manager starts typing or picks one. */}

            <div ref={messagesEndRef} />
          </div>

          {/* Text input — always visible at bottom */}
          {s.sessionState === "ready" && (
            <div className="shrink-0" style={{ borderTop: "1px solid rgba(255,255,255,0.06)", background: "rgba(0,0,0,0.2)" }}>
              {/* Transcription preview bar */}
              {s.transcription.status === "preview" && s.input.trim() && (
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="px-4 py-2 flex items-center gap-2"
                  style={{ borderBottom: "1px solid rgba(255,255,255,0.06)", background: "rgba(var(--accent-rgb, 107,77,199), 0.08)" }}
                >
                  <Mic size={14} style={{ color: "var(--accent)", flexShrink: 0 }} />
                  <span className="text-xs truncate" style={{ color: "var(--accent)" }}>
                    Распознано — проверьте и отправьте
                  </span>
                  <button
                    onClick={() => { s.setTranscription({ status: "idle", partial: "", final: "" }); s.setInput(""); }}
                    className="ml-auto text-xs px-2 py-0.5 rounded"
                    style={{ color: "var(--text-muted)" }}
                  >
                    <XCircle size={14} />
                  </button>
                </motion.div>
              )}

              {/* Transcribing indicator + live partial transcript.
                  2026-04-22: replaced the floating TranscriptionIndicator
                  (which was rendered inside the message scroll area and
                  jumped around) with this anchored band above the input.
                  Shows partial recognition text live so the user can see
                  what's being captured without it scrolling out of view. */}
              {s.transcription.status === "transcribing" && (
                <div className="px-4 py-2 flex items-center gap-2">
                  <Loader2 size={14} className="animate-spin shrink-0" style={{ color: "var(--accent)" }} />
                  <span className="text-xs shrink-0" style={{ color: "var(--text-muted)" }}>Распознаю:</span>
                  {s.transcription.partial ? (
                    <span
                      className="text-xs truncate flex-1 italic"
                      style={{ color: "var(--text-secondary)" }}
                    >
                      {s.transcription.partial}
                    </span>
                  ) : (
                    <span className="text-xs flex-1" style={{ color: "var(--text-muted)" }}>речь...</span>
                  )}
                </div>
              )}

              <div className="px-4 py-3">
                {/* 2026-04-19 Phase 2.6: quote-reply pending state badge. */}
                <QuoteReplyBadge
                  preview={s.pendingQuotedPreview}
                  onCancel={() => s.clearPendingQuote()}
                />
                <div className="flex items-end gap-2">
                  {/* NEW-6/7: primary chip = LinkClient. Tertiary actions
                      (paperclip) live in the kebab so the textarea is wide. */}
                  <LinkClientButton
                    sessionId={routeId}
                    disabled={s.sessionState !== "ready"}
                  />
                  <InputBarMoreMenu
                    sessionId={routeId}
                    disabled={s.sessionState !== "ready"}
                  />
                  <textarea
                    ref={textareaRef}
                    value={s.input}
                    onChange={(e) => s.setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder={s.transcription.status === "preview" ? "Редактируйте и нажмите Enter..." : "Введите сообщение..."}
                    disabled={s.sessionState !== "ready"}
                    rows={1}
                    aria-label="Введите сообщение"
                    /* 2026-04-18: max-h bumped 112 → 240 px so long STT/reply quotes fit */
                    className="vh-input min-h-[40px] flex-1 resize-none text-sm"
                    style={{
                      maxHeight: 240,
                      ...(s.transcription.status === "preview"
                        ? { borderColor: "var(--accent)", boxShadow: "0 0 0 1px var(--accent-glow)" }
                        : {}),
                    }}
                    onInput={(e) => {
                      const t = e.target as HTMLTextAreaElement;
                      t.style.height = "auto";
                      t.style.height = Math.min(t.scrollHeight, 240) + "px";
                    }}
                  />
                  <motion.button
                    onClick={() => {
                      // Clear preview state on send
                      if (s.transcription.status === "preview") {
                        s.setTranscription({ status: "idle", partial: "", final: "" });
                      }
                      handleSend();
                    }}
                    disabled={!s.input.trim() || s.sessionState !== "ready" || connectionState !== "connected" || s.isTyping}
                    aria-label="Отправить"
                    className="flex h-[40px] w-[40px] shrink-0 items-center justify-center rounded-xl text-white"
                    style={{ background: "var(--accent)", opacity: !s.input.trim() || s.sessionState !== "ready" || s.isTyping ? 0.4 : 1 }}
                    whileTap={{ scale: 0.95 }}
                  >
                    {s.isTyping ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
                  </motion.button>
                </div>
              </div>
            </div>
          )}

          {/* 2026-04-20: floating ScriptHints FAB — renders as absolute
              child of the chat aside, so it sits at the bottom-right of
              the chat column independent of viewport size. The component
              positions itself (absolute right/bottom) and handles its own
              popover, so we just need to mount it here. */}
          {s.scriptHintsEnabled && s.sessionState === "ready" && routeId && (
            <ScriptHints
              sessionId={routeId}
              refreshKey={s.scriptHintsRefreshKey}
              userTyping={s.input.trim().length > 0}
              onSend={(text) => {
                sendMessage({ type: "text.message", data: { content: text } });
                s.addMessage({
                  id: s.nextMsgId(),
                  role: "user",
                  content: text,
                  timestamp: new Date().toISOString(),
                });
                s.setIsTyping(true);
              }}
            />
          )}
        </aside>

        {/* CENTER: Avatar + Mic — same violet border as chat for visual cohesion */}
        <section
          className="training-session-panel training-session-center rounded-2xl relative flex flex-col items-center justify-center overflow-hidden"
          style={{
            background: "radial-gradient(ellipse at center, rgba(107,77,199,0.06) 0%, transparent 70%)",
            border: "2px solid var(--accent)",
            boxShadow: "0 0 0 1px rgba(107,77,199,0.25), 4px 4px 0 0 rgba(107,77,199,0.15)",
          }}
        >
          {/* Client name + emotion — top center */}
          <div className="absolute top-5 left-0 right-0 flex flex-col items-center gap-1.5 z-30">
            <div className="text-base font-semibold" style={{ color: "var(--text-primary)" }}>
              {s.characterName || "Клиент"}
            </div>
            <div className="flex items-center gap-2">
              <motion.div
                className="w-2 h-2 rounded-full"
                style={{ background: EMOTION_MAP[s.emotion]?.color || "var(--brand-deep)" }}
                animate={{
                  boxShadow: [
                    `0 0 4px ${EMOTION_MAP[s.emotion]?.glow || "rgba(109,40,217,0.4)"}`,
                    `0 0 12px ${EMOTION_MAP[s.emotion]?.glow || "rgba(109,40,217,0.4)"}`,
                    `0 0 4px ${EMOTION_MAP[s.emotion]?.glow || "rgba(109,40,217,0.4)"}`,
                  ],
                }}
                transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
              />
              <AnimatePresence mode="wait">
                <motion.span
                  key={s.emotion}
                  className="text-sm font-semibold"
                  style={{ color: EMOTION_MAP[s.emotion]?.color || "var(--brand-deep)" }}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: 8 }}
                  transition={{ duration: 0.3 }}
                >
                  {EMOTION_MAP[s.emotion]?.labelRu || EMOTION_MAP[s.emotion]?.label || "Неизвестно"}
                </motion.span>
              </AnimatePresence>
            </div>
          </div>

          {/* STT warning — dismissible */}
          <AnimatePresence>
          {!s.sttAvailable && s.sessionState === "ready" && !sttWarningDismissed && (
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              className="absolute top-6 right-6 z-30 flex items-center gap-2 rounded-xl px-3 py-2 text-xs"
              style={{ background: "rgba(245,158,11,0.1)", border: "1px solid rgba(245,158,11,0.2)", color: "var(--warning)" }}
            >
              <AlertTriangle size={14} />
              Голосовой режим недоступен. Используйте текстовый чат.
              <button onClick={() => setSttWarningDismissed(true)} className="ml-1 hover:opacity-70" aria-label="Закрыть">
                <XCircle size={14} />
              </button>
            </motion.div>
          )}
          </AnimatePresence>

          {/* Avatar */}
          <div className="relative w-full max-w-[min(65vh,560px)] aspect-square flex items-center justify-center z-10">
            <div className="absolute inset-0 rounded-full opacity-20 blur-[60px] transition-colors duration-1000"
              style={{ background: EMOTION_MAP[s.emotion]?.color || "var(--brand-deep)" }}
            />
            <StylizedAvatar
              emotion={s.emotion}
              isSpeaking={tts.speaking || s.micActive}
              audioLevel={tts.speaking ? tts.audioLevel : microphone.audioLevel || speech.audioLevel}
              seed={`${s.archetypeCode || routeId || "default"}-${s.characterGender}`}
              className="absolute inset-0 z-20"
            />
          </div>

          {/* Mic / Text input */}
          <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-30 w-full max-w-lg px-4">
            {/* Desktop: mic when voice mode, small toggle button when text mode */}
            <div className="hidden lg:flex justify-center">
              {s.textMode ? (
                <motion.button
                  onClick={() => s.setTextMode(false)}
                  className="flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium transition-colors"
                  style={{ background: "rgba(255,255,255,0.05)", color: "var(--text-muted)", border: "1px solid rgba(255,255,255,0.08)" }}
                  whileHover={{ background: "rgba(255,255,255,0.08)" }}
                  whileTap={{ scale: 0.97 }}
                >
                  <Mic size={16} />
                  Голосовой режим
                </motion.button>
              ) : (
                <CrystalMic
                  mode="hold"
                  isRecording={microphone.recordingState === "recording" || speech.status === "listening"}
                  isProcessing={microphone.recordingState === "processing" || s.transcription.status === "transcribing"}
                  audioLevel={microphone.audioLevel || speech.audioLevel}
                  onPress={handleMicPress}
                  onRelease={handleMicRelease}
                  onTextMode={() => {
                    s.setTextMode(true);
                    setTimeout(() => textareaRef.current?.focus(), 100);
                  }}
                  disabled={s.sessionState !== "ready" || (!s.sttAvailable && !speech.isSupported)}
                />
              )}
            </div>
            {/* Mobile: mic or textarea (left panel is hidden) */}
            <div className="lg:hidden">
              {s.textMode ? (
                <div className="flex items-end gap-2">
                  {/* NEW-6/7: same kebab pattern as desktop bar above. */}
                  <LinkClientButton
                    sessionId={routeId}
                    disabled={s.sessionState !== "ready"}
                  />
                  <InputBarMoreMenu
                    sessionId={routeId}
                    disabled={s.sessionState !== "ready"}
                  />
                  <textarea
                    value={s.input}
                    onChange={(e) => s.setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder={s.sessionState === "ready" ? "Введите сообщение..." : "Ожидание подключения..."}
                    disabled={s.sessionState !== "ready"}
                    rows={1}
                    aria-label="Введите сообщение"
                    className="vh-input max-h-32 min-h-[42px] flex-1 resize-none"
                    onInput={(e) => {
                      const t = e.target as HTMLTextAreaElement;
                      t.style.height = "auto";
                      t.style.height = Math.min(t.scrollHeight, 128) + "px";
                    }}
                  />
                  <motion.button
                    onClick={handleSend}
                    disabled={!s.input.trim() || s.sessionState !== "ready" || connectionState !== "connected"}
                    aria-label="Отправить сообщение"
                    className="flex h-[42px] w-[42px] shrink-0 items-center justify-center rounded-xl text-white"
                    style={{ background: "var(--accent)", opacity: !s.input.trim() || s.sessionState !== "ready" ? 0.4 : 1 }}
                    whileTap={{ scale: 0.95 }}
                  >
                    <Send size={18} />
                  </motion.button>
                </div>
              ) : (
                <CrystalMic
                  mode="hold"
                  isRecording={microphone.recordingState === "recording" || speech.status === "listening"}
                  isProcessing={microphone.recordingState === "processing" || s.transcription.status === "transcribing"}
                  audioLevel={microphone.audioLevel || speech.audioLevel}
                  onPress={handleMicPress}
                  onRelease={handleMicRelease}
                  onTextMode={() => s.setTextMode(true)}
                  disabled={s.sessionState !== "ready" || (!s.sttAvailable && !speech.isSupported)}
                />
              )}
            </div>
          </div>

          {/* Mobile transcript */}
          <div className="mt-4 w-full overflow-y-auto px-4 lg:hidden" style={{ maxHeight: "30vh" }}>
            <div className="space-y-2">
              {s.messages.map((msg) => (
                <ChatMessage key={msg.id} message={msg} />
              ))}
              <div ref={messagesEndRef} />
            </div>
          </div>
        </section>

        {/*
          RIGHT: Stats panel — 2026-05-03 redesign.
          Mirrors /pvp's 3-pill switcher pattern. Old version stacked
          9 panels (VibeMeter, TalkListen, Script, Emotion, Whisper,
          Difficulty, HumanFactor, TrapLog, Score) in one always-on
          column that on most viewports pushed "Баллы" off-screen and
          made the page feel like a wall of widgets. Now: compact pill
          switcher → only one tab at a time. WhisperPanel hoisted out
          to a floating dock (bottom of this file) so coaching hints
          aren't gated behind the active tab.

          Hidden below `lg` because mobile gets the chat-only view —
          the same panels are reachable via /history / /results once
          the session ends.
        */}
        <aside
          className="training-session-panel training-session-panel--stats hidden lg:flex flex-col gap-3 overflow-y-auto rounded-2xl"
          style={{
            border: "2px solid var(--accent)",
            boxShadow: "0 0 0 1px rgba(107,77,199,0.25), 4px 4px 0 0 rgba(107,77,199,0.15)",
            padding: "12px",
          }}
        >
          {/*
            Coaching whisper — moved from a floating dock into the
            sidebar header (2026-05-03 fix). The floating version
            overlapped the third tab "Реакции" and visually felt
            like a separate hovering panel. Now it lives at the top
            of the sidebar so coaching hints are visible regardless
            of which tab is active, without occluding anything.
          */}
          <div className="rounded-xl" style={{ background: "rgba(107,77,199,0.08)", border: "1px solid rgba(107,77,199,0.25)", padding: "10px 12px" }}>
            <WhisperPanel onToggle={(enabled) => sendMessage({ type: "whisper.toggle", data: { enabled } })} />
          </div>

          {/* Pill switcher — same layoutId pattern as /pvp:482 */}
          <div className="flex gap-1 rounded-xl p-1" style={{ background: "rgba(255,255,255,0.04)" }}>
            {([
              { key: "score", label: "Балл", Icon: Target },
              { key: "script", label: "Скрипт", Icon: ListChecks },
              { key: "reactions", label: "Реакции", Icon: Activity },
            ] as const).map(({ key, label, Icon }) => {
              const active = sidebarTab === key;
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => setSidebarTab(key)}
                  className="relative flex-1 flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-xs font-semibold transition-colors"
                  style={{
                    color: active ? "white" : "var(--text-muted)",
                  }}
                >
                  {active && (
                    <motion.div
                      layoutId="trainingSidebarTab"
                      className="absolute inset-0 rounded-lg"
                      style={{ background: "var(--accent)" }}
                      transition={{ type: "spring", stiffness: 500, damping: 35 }}
                    />
                  )}
                  <span className="relative flex items-center gap-1.5">
                    <Icon size={13} />
                    {label}
                  </span>
                </button>
              );
            })}
          </div>

          {/* ─────────────────────────────────────────────────────────
              TAB: Балл — VibeMeter + Acceptance + TalkListen + total
              + full 8-field breakdown from score.hint payload.
              Old version showed only 3 of 8 sub-scores (schema drift
              since the backend started emitting all 8 in PR #B9).
              ───────────────────────────────────────────────────── */}
          {sidebarTab === "score" && (
            <div className="flex flex-col gap-3">
              <div className="rounded-2xl p-4" style={{ background: "rgba(255,255,255,0.04)" }}>
                <VibeMeter emotion={s.emotion} />
                <div className="mt-4 pt-4" style={{ borderTop: "1px solid rgba(255,255,255,0.06)" }}>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-semibold" style={{ color: "var(--text-secondary)" }}>Принятие сделки</span>
                    <motion.span
                      key={acceptanceScore}
                      initial={{ scale: 1.2 }}
                      animate={{ scale: 1 }}
                      className="text-sm font-bold tabular-nums"
                      style={{ color: acceptanceScore >= 60 ? "#00FF94" : "var(--accent)" }}
                    >
                      {s.messages.length === 0 ? "—" : `${acceptanceScore}%`}
                    </motion.span>
                  </div>
                  <div className="h-2.5 overflow-hidden rounded-full" style={{ background: "rgba(255,255,255,0.06)" }}>
                    <motion.div
                      className="h-full rounded-full"
                      animate={{ width: `${acceptanceScore}%` }}
                      transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
                      style={{
                        background: acceptanceScore >= 60 ? "linear-gradient(90deg, #22c55e, #00FF94)" : "linear-gradient(90deg, #F59E0B, var(--accent))",
                      }}
                    />
                  </div>
                  <div className="mt-1.5 text-xs font-medium" style={{ color: acceptanceScore >= 60 ? "#00FF94" : "var(--text-muted)" }}>
                    {acceptanceLabel}
                  </div>
                </div>
              </div>

              <div className="rounded-xl p-3" style={{ background: "rgba(255,255,255,0.025)" }}>
                <TalkListenRatio talkPercent={s.talkTime + s.listenTime > 0 ? Math.round((s.talkTime / (s.talkTime + s.listenTime)) * 100) : 50} />
              </div>

              <div className="rounded-xl p-4 relative overflow-hidden" style={{ background: "rgba(255,255,255,0.05)" }}>
                <AnimatePresence>
                  {checkpointFlash && (
                    <motion.div
                      className="absolute inset-0 rounded-xl pointer-events-none"
                      initial={{ opacity: 0.4 }}
                      animate={{ opacity: 0 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: 0.8 }}
                      style={{ background: "radial-gradient(circle at center, rgba(61,220,132,0.15) 0%, transparent 70%)" }}
                    />
                  )}
                </AnimatePresence>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-semibold" style={{ color: "var(--text-secondary)" }}>Общий балл</span>
                  <motion.div
                    className="text-2xl font-bold tabular-nums"
                    style={{ color: "var(--accent)" }}
                    key={Math.round(s.scriptScore)}
                    initial={{ scale: 1.2, opacity: 0.7 }}
                    animate={{ scale: 1, opacity: 1 }}
                    transition={{ type: "spring", stiffness: 500, damping: 25 }}
                  >
                    {s.messages.length === 0 ? "—" : <>{Math.round(s.scriptScore)}<span className="text-sm font-normal ml-0.5" style={{ color: "var(--text-muted)" }}>/100</span></>}
                  </motion.div>
                </div>
                {scoreHint ? (
                  // Render ALL 8 layers from the score.hint payload.
                  // Order matches the backend's logical flow:
                  // script → objection → communication → anti-pattern
                  // → result → chain → trap → human factor.
                  // Each layer caps at 12.5 (=100/8) so width math
                  // is value/12.5 * 100 — pre-fix used /18.75 which
                  // assumed a 6-layer split that's no longer accurate.
                  <div className="mt-3 space-y-2">
                    {([
                      ["Скрипт", scoreHint.script_adherence, "var(--accent)"],
                      ["Возражения", scoreHint.objection_handling, "var(--warning)"],
                      ["Коммуникация", scoreHint.communication, "var(--info)"],
                      ["Анти-паттерны", scoreHint.anti_patterns, "var(--danger)"],
                      ["Результат", scoreHint.result, "#00FF94"],
                      ["Сценарий", scoreHint.chain_traversal, "var(--magenta)"],
                      ["Ловушки", scoreHint.trap_handling, "#F59E0B"],
                      ["Человеч. фактор", scoreHint.human_factor, "#A78BFA"],
                    ] as const).map(([label, value, color]) => (
                      <div key={label}>
                        <div className="mb-0.5 flex items-center justify-between text-[11px]" style={{ color: "var(--text-muted)" }}>
                          <span>{label}</span>
                          <span className="tabular-nums font-mono" style={{ color }}>{Math.round(value)}</span>
                        </div>
                        <div className="h-1.5 w-full rounded-full overflow-hidden" style={{ background: "rgba(255,255,255,0.06)" }}>
                          <motion.div
                            className="h-full rounded-full"
                            animate={{ width: `${Math.min(100, (value / 12.5) * 100)}%` }}
                            transition={{ duration: 0.5, ease: "easeOut" }}
                            style={{ background: color }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="mt-2 text-xs" style={{ color: "var(--text-muted)" }}>
                    Баллы появятся после первого ответа
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ─────────────────────────────────────────────────────────
              TAB: Скрипт — ScriptPanel + DifficultyIndicator
              ───────────────────────────────────────────────────── */}
          {sidebarTab === "script" && (
            <div className="flex flex-col gap-3">
              <div className="rounded-xl p-4" style={{ background: "rgba(255,255,255,0.04)" }}>
                <ScriptPanel
                  compactHeader
                  onCopyExample={(text) => {
                    // B6 (2026-05-03): APPEND to existing input instead of REPLACE
                    // so users don't lose what they've already typed when tapping
                    // an example phrase from the script panel.
                    const cur = useSessionStore.getState().input ?? "";
                    const next = cur.trim() ? cur + (cur.endsWith(" ") ? "" : " ") + text : text;
                    useSessionStore.getState().setInput(next);
                    if (textareaRef.current) {
                      textareaRef.current.focus();
                      setTimeout(() => {
                        if (textareaRef.current) {
                          textareaRef.current.setSelectionRange(next.length, next.length);
                        }
                      }, 0);
                    }
                  }}
                />
              </div>
              <div className="rounded-xl p-4" style={{ background: "rgba(255,255,255,0.025)" }}>
                <DifficultyIndicator
                  effectiveDifficulty={s.effectiveDifficulty}
                  modifier={0}
                  mode={s.difficultyMode}
                  trend={s.difficultyTrend}
                  goodStreak={s.goodStreak}
                  badStreak={s.badStreak}
                  hadComeback={false}
                />
              </div>
            </div>
          )}

          {/* ─────────────────────────────────────────────────────────
              TAB: Реакции — Emotion timeline + HumanFactors + TrapLog
              + Consequences. Empty-state banner so the tab doesn't
              render an empty card on session start.
              ───────────────────────────────────────────────────── */}
          {sidebarTab === "reactions" && (
            <div className="flex flex-col gap-3">
              {s.emotionHistory.length >= 2 ? (
                <div className="rounded-xl p-4" style={{ background: "rgba(255,255,255,0.04)" }}>
                  <LiveEmotionTimeline />
                </div>
              ) : (
                <div className="rounded-xl p-4 text-xs" style={{ background: "rgba(255,255,255,0.02)", color: "var(--text-muted)" }}>
                  Карта эмоций появится после нескольких реплик
                </div>
              )}
              {s.humanFactors.length > 0 && (
                <div className="rounded-xl p-3" style={{ background: "rgba(255,255,255,0.025)" }}>
                  <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>Факторы</div>
                  <HumanFactorIcons factors={s.humanFactors} />
                </div>
              )}
              {s.consequences.length > 0 && (
                <div className="rounded-xl p-3 space-y-1.5">
                  <div className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>Последствия</div>
                  {s.consequences.slice(-3).reverse().map((consequence, index) => (
                    <div
                      key={`${consequence.call}-${consequence.type}-${index}`}
                      className="rounded-lg px-3 py-2.5 text-sm"
                      style={{ background: "var(--danger-muted)", color: "var(--text-secondary)" }}
                    >
                      <span className="font-semibold" style={{ color: "var(--danger)" }}>{(consequence.type || "event").replace(/_/g, " ")}</span>
                      <span className="ml-2 line-clamp-1">{consequence.detail}</span>
                    </div>
                  ))}
                </div>
              )}
              {s.trapHistory.length > 0 && (
                <div className="rounded-xl p-3" style={{ background: "rgba(255,255,255,0.015)" }}>
                  <TrapLog />
                </div>
              )}
            </div>
          )}
        </aside>
        </div>
      </main>

      {/* ── Trap Notification ──────────────────────────────── */}
      <TrapNotification event={s.activeTrap} onDismiss={() => s.setActiveTrap(null)} />

      {/* ── Training Toasts (hangup, hints, silence, timer) ── */}
      <TrainingToasts
        hangupWarning={s.hangupWarning}
        objectionHint={s.objectionHint}
        checkpointHint={s.checkpointHint}
        silenceWarning={s.silenceWarning}
        elapsed={s.elapsed}
        sessionState={s.sessionState}
        formatTime={formatTime}
      />

      {/* 2026-04-23: full-screen ending overlay — shown from handleEnd
          click until router.replace lands on /results. Covers the 5-15s
          scoring window so the user never sees a frozen chat UI. */}
      <SessionEndingOverlay
        visible={ending}
        title="Завершаем тренировку"
        subtitle={s.characterName || undefined}
      />

      {/* 2026-04-23 Sprint 3: ScriptDrawer — mobile-only bottom-sheet for
          the script panel. Sidebar holds it on desktop (lg+); on smaller
          screens this drawer auto-opens on stage.update + stage.skipped. */}
      <ScriptDrawer
        onCopyExample={(text) => {
          // B6 (2026-05-03): APPEND to existing input instead of REPLACE.
          const cur = useSessionStore.getState().input ?? "";
          const next = cur.trim() ? cur + (cur.endsWith(" ") ? "" : " ") + text : text;
          useSessionStore.getState().setInput(next);
          if (textareaRef.current) {
            textareaRef.current.focus();
            setTimeout(() => {
              if (textareaRef.current) {
                textareaRef.current.setSelectionRange(next.length, next.length);
              }
            }, 0);
          }
        }}
      />

      {/* ── Modals ──────────────────────────────────────────── */}
      <AnimatePresence>
        {s.sessionState === "completed" && (
          <motion.div key="modal-completed" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-[150] flex items-center justify-center" style={{ background: "rgba(0,0,0,0.8)", backdropFilter: "blur(8px)" }}>
            <motion.div initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ type: "spring", stiffness: 300, damping: 20 }} className="glass-panel px-8 sm:px-12 py-8 text-center max-w-md rounded-3xl">
              <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full" style={{ background: "rgba(61,220,132,0.1)", boxShadow: "0 0 40px rgba(61,220,132,0.15)" }}>
                <CheckCircle2 size={32} style={{ color: "var(--success)" }} />
              </div>
              <h2 className="mt-4 font-display text-2xl font-bold" style={{ color: "var(--text-primary)" }}>
                ТРЕНИРОВКА ЗАВЕРШЕНА
              </h2>
              {sessionEndedRef.current.score !== null && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.3 }}
                  className="mt-4"
                >
                  <div className="font-display text-5xl font-black" style={{ color: sessionEndedRef.current.score >= 70 ? "var(--success)" : sessionEndedRef.current.score >= 40 ? "var(--warning)" : "var(--danger)" }}>
                    {Math.round(sessionEndedRef.current.score)}
                  </div>
                  <div className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>баллов</div>
                </motion.div>
              )}
              {sessionEndedRef.current.xp !== null && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.6 }}
                  className="mt-3 inline-flex items-center gap-2 rounded-xl px-4 py-2"
                  style={{ background: "rgba(255,180,0,0.1)", border: "1px solid rgba(255,180,0,0.2)" }}
                >
                  <span className="font-display font-bold text-lg" style={{ color: "var(--warning)" }}>+{sessionEndedRef.current.xp} XP</span>
                </motion.div>
              )}
              {sessionEndedRef.current.levelUp && (
                <motion.div
                  initial={{ opacity: 0, scale: 0.8 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ delay: 0.9, type: "spring" }}
                  className="mt-3 inline-flex items-center gap-2 rounded-xl px-4 py-2"
                  style={{ background: "rgba(61,220,132,0.1)", border: "1px solid rgba(61,220,132,0.3)" }}
                >
                  <span className="font-display font-bold text-lg" style={{ color: "var(--success)" }}>УРОВЕНЬ ПОВЫШЕН!</span>
                </motion.div>
              )}
              <motion.p
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 1.2 }}
                className="mt-4 text-sm"
                style={{ color: "var(--text-muted)" }}
              >
                Переход к результатам...
              </motion.p>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {s.showAbortModal && (
          <motion.div key="modal-abort" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-[150] flex items-center justify-center p-4" style={{ background: "var(--overlay-bg)", backdropFilter: "blur(8px)" }}>
            <motion.div initial={{ scale: 0.9 }} animate={{ scale: 1 }} className="glass-panel w-full max-w-md px-6 sm:px-8 py-7 text-center rounded-2xl">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full" style={{ background: "var(--danger-muted)", border: "1px solid rgba(229,72,77,0.2)" }}>
                <XCircle size={26} style={{ color: "var(--danger)" }} />
              </div>
              <h2 className="mt-4 font-display text-xl font-bold" style={{ color: "var(--text-primary)" }}>
                Прервать тренировку?
              </h2>
              <p className="mt-2 text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                Прогресс будет сохранён, но сессия завершится досрочно.
              </p>
              <div className="mt-6 grid grid-cols-2 gap-3">
                <motion.button onClick={() => s.setShowAbortModal(false)} className="btn-neon w-full py-3 text-sm" whileTap={{ scale: 0.97 }}>
                  Продолжить
                </motion.button>
                <motion.button onClick={() => { s.setShowAbortModal(false); handleEnd(); }} className="btn-neon btn-neon--danger w-full py-3 text-sm flex items-center justify-center gap-2" whileTap={{ scale: 0.97 }}>
                  <XCircle size={14} /> Завершить
                </motion.button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {s.showSilenceModal && (
          <motion.div key="modal-silence" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-[150] flex items-center justify-center p-4" style={{ background: "var(--overlay-bg)", backdropFilter: "blur(8px)" }}>
            <motion.div initial={{ scale: 0.9 }} animate={{ scale: 1 }} className="glass-panel w-full max-w-md px-6 sm:px-8 py-7 text-center rounded-2xl">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full" style={{ background: "var(--warning-muted)", border: "1px solid rgba(245,158,11,0.2)" }}>
                <AlertTriangle size={26} style={{ color: "var(--warning)" }} />
              </div>
              <h2 className="mt-4 font-display text-xl font-bold" style={{ color: "var(--warning)" }}>
                Потеря сигнала
              </h2>
              <p className="mt-2 text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                Вы давно молчите. Продолжить тренировку?
              </p>
              <div className="mt-6 grid grid-cols-2 gap-3">
                <motion.button onClick={handleContinueSession} className="btn-neon w-full py-3 text-sm" whileTap={{ scale: 0.97 }}>
                  Продолжить
                </motion.button>
                <motion.button onClick={handleEnd} className="btn-neon w-full py-3 text-sm" whileTap={{ scale: 0.97 }}>
                  Завершить
                </motion.button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/*
        Autoplay-unlock overlay for chat mode. Browsers block
        HTMLAudioElement.play() outside a user gesture, and useTTS
        sets `needsAudioUnlock` whenever play() rejects. Without this
        overlay, chat-mode users heard nothing and reported "ошибка
        ТТС" — there was no surface to unlock the audio context.
        Same component used in /call/page.tsx for parity.
      */}
      <TTSUnlockOverlay visible={tts.needsAudioUnlock} onUnlock={tts.unlock} />

      <HangupModal
        open={s.showHangupModal}
        data={s.hangupData}
        onRedial={() => {
          s.setShowHangupModal(false);
          s.setHangupData(null);
          // 2026-04-18 audit fix: if we're on the last call of the story,
          // "redial" doesn't make sense — story.next_call would error. In
          // that case, finalize the story instead.
          if (s.storyMode && s.storyId) {
            if (s.callNumber >= s.totalCalls) {
              sendMessage({ type: "story.end", data: { story_id: s.storyId } });
              setStoryTransitionText("ЗАВЕРШАЕМ ИСТОРИЮ...");
              s.setSessionState("completed");
              setTimeout(() => router.push(`/stories/${s.storyId}`), 900);
            } else {
              s.resetCallState();
              setStoryTransitionText("ПЕРЕЗВАНИВАЕМ...");
              sendMessage({ type: "story.next_call", data: { story_id: s.storyId } });
            }
          }
        }}
        onResults={() => {
          // 2026-05-04 prod bug fix: previously this handler closed the
          // modal then fire-and-forget'd session.end. The chat UI behind
          // the modal became visible (user reports "вернулся в чат"),
          // and the actual redirect waited 10–60s for session.ended.
          // Now we:
          //   1. show the SessionEndingOverlay immediately so the dead
          //      chat is masked,
          //   2. send session.end exactly once (deduped via ref so the
          //      C3 auto-fire can't double-fire),
          //   3. arm the 5s fallback navigation so the user is never
          //      stuck if session.ended is delayed/dropped.
          // The success path remains: session.ended → router.replace at
          // line ~556 fires <100ms after backend finishes scoring.
          s.setShowHangupModal(false);
          s.setHangupData(null);
          if (s.storyMode && s.storyId) {
            // 2026-04-18 audit fix: explicit navigation after story.end
            // — previously we fired the message and hoped story.completed
            // event would redirect. If the socket was slow, user saw a
            // blank "completed" screen indefinitely.
            sendMessage({ type: "story.end", data: { story_id: s.storyId } });
            s.setSessionState("completed");
            setTimeout(() => router.push(`/stories/${s.storyId}`), 900);
          } else {
            setEnding(true);
            if (markEndSent(hangupRef.current)) {
              sendMessage({ type: "session.end", data: {} });
            }
            armHangupFallback();
          }
        }}
      />
    </div>
    </TrainingErrorBoundary>
  );
}
