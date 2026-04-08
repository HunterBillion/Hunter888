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
} from "lucide-react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useMicrophone } from "@/hooks/useMicrophone";
import { useSpeechRecognition } from "@/hooks/useSpeechRecognition";
import { useTTS } from "@/hooks/useTTS";
import { MicCheck } from "@/components/training/MicCheck";
import ChatMessage from "@/components/training/ChatMessage";
import { CrystalMic } from "@/components/training/CrystalMic";
import TranscriptionIndicator from "@/components/training/TranscriptionIndicator";
import VibeMeter from "@/components/training/VibeMeter";
import { type CheckpointInfo } from "@/components/training/ScriptAdherence";
import StageProgressBar from "@/components/training/StageProgress";
import WhisperPanel from "@/components/training/WhisperPanel";
import { HangupModal } from "@/components/training/HangupModal";
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
import { TrainingToasts } from "@/components/training/TrainingToasts";
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

const Avatar3D = dynamic(
  () => import("@/components/training/Avatar3D").then((m) => m.Avatar3D),
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
  const storyCustomParams = useMemo(() => ({
    archetype: storyArchetype,
    profession: storyProfession,
    lead_source: storyLeadSource,
    difficulty: storyDifficulty,
  }), [storyArchetype, storyProfession, storyLeadSource, storyDifficulty]);

  // ── Zustand store (replaces 30+ useState) ──
  // Full subscription for render — but NEVER put `s` in useEffect deps!
  // Use useSessionStore.getState() for actions inside effects/callbacks.
  const s = useSessionStore();

  // Initialize store on mount
  useEffect(() => {
    useSessionStore.getState().init(routeId);
    return () => {
      useSessionStore.getState().reset();
      wsTimersRef.current.forEach(clearTimeout);
      wsTimersRef.current = [];
    };
  }, [routeId]);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const wsTimersRef = useRef<ReturnType<typeof setTimeout>[]>([]);
  const sessionEndedRef = useRef<{ score: number | null; xp: number | null; levelUp: boolean }>({ score: null, xp: null, levelUp: false });
  const storyBootstrappedRef = useRef(false);
  const [storyTransitionText, setStoryTransitionText] = useState(
    isStoryMode ? "ИНИЦИАЛИЗАЦИЯ AI-ИСТОРИИ..." : "ПОДКЛЮЧЕНИЕ К СЕССИИ..."
  );
  const [storyCallReport, setStoryCallReport] = useState<{
    callNumber: number;
    score: number;
    keyMoments: string[];
    consequences: Array<{ call: number; type: string; severity: number; detail: string }>;
    memoriesCreated: number;
  } | null>(null);
  const [activeConsequence, setActiveConsequence] = useState<import("@/types/story").ConsequenceEvent | null>(null);
  const [scoreHint, setScoreHint] = useState<{
    objection_handling: number;
    communication: number;
    human_factor: number;
    realtime_estimate: number;
    max_possible_realtime: number;
  } | null>(null);
  const [preferBrowserSpeech, setPreferBrowserSpeech] = useState(false);
  const [sttWarningDismissed, setSttWarningDismissed] = useState(false);

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
      logger.log(`[WS] ${data.type}`, data.type === "tts.audio" ? `(audio ${(data.data?.audio_b64 as string)?.length || 0} chars)` : data.data);
      switch (data.type) {
        case "auth.success":
        case "session.ready":
          break;

        case "session.started":
          setStoryTransitionText("ЗВОНОК АКТИВЕН");
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

        case "character.response": {
          s.setIsTyping(false);
          const content = stripStageDirections(data.data.content as string);
          s.addMessage({
            id: s.nextMsgId(),
            role: "assistant",
            content,
            emotion: data.data.emotion as EmotionState | undefined,
            timestamp: new Date().toISOString(),
            sequenceNumber: data.data.sequence_number as number | undefined,
          });
          if (data.data.emotion) s.setEmotion(data.data.emotion as EmotionState);
          if (data.data.script_score !== undefined) s.setScriptScore(data.data.script_score as number);
          s.setListenTime(s.listenTime + 1);
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

        case "tts.fallback":
          logger.warn("[TTS] ElevenLabs fallback received:", data.data.reason);
          break;

        case "session.ended":
          tts.stop();
          if (timerRef.current) clearInterval(timerRef.current);
          if (isStoryMode) {
            setStoryTransitionText("ФОРМИРУЕМ ОТЧЁТ ЗВОНКА...");
            s.setSessionState("connecting");
          } else {
            s.setSessionState("completed");
            // Show celebration overlay with score before redirecting
            const ended = data.data as Record<string, unknown> | undefined;
            const endedScores = ended?.scores as Record<string, number> | undefined;
            const endedXp = ended?.xp_breakdown as Record<string, number> | undefined;
            sessionEndedRef.current = {
              score: (endedScores?.total as number) ?? null,
              xp: (endedXp?.grand_total as number) ?? null,
              levelUp: Boolean(ended?.level_up),
            };
            setTimeout(() => router.push(`/results/${routeId}`), 3500);
          }
          break;

        case "transcription.result": {
          const text = data.data.text as string;
          const isEmpty = data.data.is_empty as boolean;
          if (isEmpty || !text) {
            s.setTranscription({ status: "idle", partial: "", final: "" });
          } else {
            s.setTranscription({ status: "done", partial: "", final: text });
            s.addMessage({ id: s.nextMsgId(), role: "user", content: text, timestamp: new Date().toISOString() });
            s.setTalkTime(s.talkTime + 1);
          }
          break;
        }

        case "stt.unavailable":
        case "stt.error":
          if (speech.isSupported) {
            setPreferBrowserSpeech(true);
            s.setSttAvailable(true);
            s.setTextMode(false);
          } else {
            s.setSttAvailable(false);
            s.setTextMode(true);
          }
          break;

        case "emotion.update":
          if (data.data.current) {
            s.setEmotion(data.data.current as EmotionState);
            s.addEmotionToHistory(data.data.current as EmotionState);
          }
          break;

        case "stage.update":
          s.setStageUpdate(wsPayload<import("@/types").StageUpdate>(data.data));
          break;

        case "score.update":
          if (data.data.script_score !== undefined) s.setScriptScore(data.data.script_score as number);
          if (data.data.checkpoints_hit !== undefined) s.setCheckpointsHit(data.data.checkpoints_hit as number);
          if (data.data.checkpoints_total !== undefined) s.setCheckpointsTotal(data.data.checkpoints_total as number);
          if (Array.isArray(data.data.checkpoints)) s.setCheckpoints(data.data.checkpoints as CheckpointInfo[]);
          // new_checkpoint: set if present, clear if not (only flash once per match)
          s.setNewCheckpoint(data.data.new_checkpoint ? (data.data.new_checkpoint as string) : null);
          if (data.data.is_preliminary !== undefined) s.setIsPreliminaryScore(data.data.is_preliminary as boolean);
          break;

        case "score.hint":
          setScoreHint({
            objection_handling: Number(data.data.objection_handling || 0),
            communication: Number(data.data.communication || 0),
            human_factor: Number(data.data.human_factor || 0),
            realtime_estimate: Number(data.data.realtime_estimate || 0),
            max_possible_realtime: Number(data.data.max_possible_realtime || 0),
          });
          // Also store in Zustand for RealtimeScores panel
          s.setRealtimeScores({
            objection_handling: Number(data.data.objection_handling || 0),
            communication: Number(data.data.communication || 0),
            human_factor: Number(data.data.human_factor || 0),
            realtime_estimate: Number(data.data.realtime_estimate || 0),
            max_possible: Number(data.data.max_possible_realtime || 0),
          });
          break;

        case "silence.warning":
          s.setSilenceWarning(true);
          wsTimersRef.current.push(setTimeout(() => s.setSilenceWarning(false), 5000));
          break;

        case "silence.timeout":
          s.setShowSilenceModal(true);
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

        case "client.hangup":
          s.setHangupData({
            reason: (data.data.reason as string) || "",
            hangupPhrase: (data.data.hangup_phrase as string) || "",
            canContinue: Boolean(data.data.call_can_continue),
            triggers: (data.data.triggers as string[]) || [],
          });
          s.setShowHangupModal(true);
          break;

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
          tts.playCoupleAudio({
            utterances: (data.data.utterances as Array<{ speaker: string; audio_b64: string; text: string }>).map((u) => ({
              speaker: u.speaker as "A" | "B" | "AB",
              audio: u.audio_b64,
            })),
          });
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

        case "story.call_report":
          setStoryCallReport({
            callNumber: Number(data.data.call_number || 1),
            score: Number(data.data.score || 0),
            keyMoments: Array.isArray(data.data.key_moments) ? (data.data.key_moments as string[]) : [],
            consequences: Array.isArray(data.data.consequences)
              ? (data.data.consequences as Array<{ call: number; type: string; severity: number; detail: string }>)
              : [],
            memoriesCreated: Number(data.data.memories_created || 0),
          });
          break;

        case "story.progress":
          s.setCallNumber(data.data.call_number as number);
          setStoryTransitionText("ГОТОВИМ СЛЕДУЮЩИЙ ЗВОНОК...");
          break;

        case "story.completed":
          s.setSessionState("completed");
          tts.stop();
          if (timerRef.current) clearInterval(timerRef.current);
          setTimeout(() => router.push(`/training/crm/${data.data.story_id}`), 1500);
          break;

        // ── v6: Session resume messages ──
        case "session.resumed":
          s.setEmotion(data.data.emotion as EmotionState);
          s.setElapsed(Math.floor(data.data.elapsed_seconds as number));
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
          logger.error("Training error:", errMsg);
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

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [s.messages, s.transcription, s.isTyping]);

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
    if (!text || s.sessionState !== "ready") return;
    // Block sending when WS is not connected — messages would be buffered silently
    if (connectionState !== "connected") {
      logger.warn("[Training] Send blocked: WS not connected (state=%s)", connectionState);
      return;
    }
    s.addMessage({ id: s.nextMsgId(), role: "user", content: text, timestamp: new Date().toISOString() });
    sendMessage({ type: "text.message", data: { content: text } });
    s.setInput("");
    s.setTalkTime(s.talkTime + 1);
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  const handleEnd = () => sendMessage({ type: "session.end", data: {} });

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

      s.setTextMode(true);
      s.setSttAvailable(false);
    }
  };

  const handleMicRelease = async () => {
    if (microphone.recordingState === "recording" && !preferBrowserSpeech) {
      const blob = await microphone.stopRecording();
      s.setMicActive(false);
      if (blob && blob.size > 0) {
        try {
          s.setTranscription({ status: "transcribing", partial: "", final: "" });
          const audio = await blobToBase64(blob);
          sendMessage({
            type: "audio.end",
            data: {
              audio,
              mime_type: blob.type || "audio/webm",
            },
          });
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

  // ── Connecting gate ──
  if (s.sessionState === "connecting" && !s.showPreCallBrief && !storyCallReport) {
    return (
      <div className="flex h-screen flex-col items-center justify-center" style={{ background: "var(--bg-primary)" }}>
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-transparent" style={{ borderTopColor: "var(--accent)" }} />
        <span className="mt-4 text-sm tracking-wide" style={{ color: "var(--text-muted)" }}>
          {storyTransitionText}
        </span>
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

  // ── MicCheck gate ──
  if (!s.micChecked && s.sessionState === "ready") {
    return (
      <div className="flex h-screen items-center justify-center" style={{ background: "var(--bg-primary)" }}>
        <div className="fixed inset-0 scanlines z-[100] opacity-10 mix-blend-overlay pointer-events-none" />
        <MicCheck
          onComplete={(micAvailable) => {
            if (!micAvailable) {
              s.setTextMode(true);
              s.setSttAvailable(false);
            }
            s.setMicChecked(true);
          }}
          onSkip={() => {
            s.setTextMode(true);
            s.setSttAvailable(false);
            s.setMicChecked(true);
          }}
        />
      </div>
    );
  }

  return (
    <TrainingErrorBoundary sessionId={routeId}>
    <div className="flex h-screen flex-col overflow-hidden" style={{ background: "var(--bg-primary)" }}>
      {/* ── Scanlines overlay ──────────────────────────────── */}
      <div className="fixed inset-0 scanlines z-[100] opacity-15 mix-blend-overlay pointer-events-none" />

      {/* Global mic glow */}
      <div className={`fixed inset-0 global-mic-glow z-50 ${s.micActive ? "active" : ""}`} />

      {/* ── Top HUD Header ─────────────────────────────────── */}
      <header
        className="shrink-0 flex justify-between items-center px-5 lg:px-8 z-20"
        style={{ height: 60, background: "rgba(3,3,6,0.85)", backdropFilter: "blur(20px)", borderBottom: "1px solid rgba(255,255,255,0.06)" }}
      >
        {/* Left: scenario info */}
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <div className="min-w-0">
            <div className="text-sm font-semibold truncate" style={{ color: "var(--text-primary)" }}>
              {s.scenarioTitle || "Тренировка"}
            </div>
            <div className="text-xs truncate" style={{ color: "var(--text-muted)" }}>
              {s.characterName || "Клиент"}
              {s.storyMode && ` · Звонок ${s.callNumber}/${s.totalCalls}`}
            </div>
          </div>
        </div>

        {/* Center: timer — big and clear */}
        <div className="flex items-center gap-2">
          <div
            className={`font-mono text-xl font-bold tabular-nums ${s.elapsed >= 1500 ? "animate-pulse" : ""}`}
            style={{ color: s.elapsed >= 1500 ? "var(--warning)" : "var(--text-primary)" }}
          >
            {formatTime(s.elapsed)}
          </div>
        </div>

        {/* Right: controls */}
        <div className="flex items-center gap-3 flex-1 justify-end">
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
            style={{ background: "rgba(239,68,68,0.12)", color: "#F87171", border: "1px solid rgba(239,68,68,0.25)" }}
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
              background: connectionState === "reconnecting" ? "rgba(245,158,11,0.15)" : "rgba(239,68,68,0.15)",
              border: `1px solid ${connectionState === "reconnecting" ? "rgba(245,158,11,0.3)" : "rgba(239,68,68,0.3)"}`,
              color: connectionState === "reconnecting" ? "#F59E0B" : "#F87171",
              backdropFilter: "blur(12px)",
            }}
          >
            <div className="w-2 h-2 rounded-full animate-pulse" style={{ background: connectionState === "reconnecting" ? "#F59E0B" : "#F87171" }} />
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
          isFinal={storyCallReport.callNumber >= s.totalCalls}
          onContinue={() => {
            const isFinal = storyCallReport.callNumber >= s.totalCalls;
            setStoryCallReport(null);
            if (isFinal) {
              s.setSessionState("completed");
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

      {/* ── 3-Column Layout ─────────────────────────────────── */}
      <main className="flex-1 min-h-0 z-20 px-3 py-2 lg:px-4 lg:py-3" style={{ width: "min(100%, var(--app-shell-max))", marginInline: "auto" }}>
        <div className="training-session-grid">
        {/* LEFT: Chat Panel */}
        <aside className="training-session-panel hidden lg:flex flex-col rounded-2xl overflow-hidden"
          style={{
            background: "linear-gradient(180deg, rgba(99,102,241,0.04) 0%, rgba(255,255,255,0.02) 100%)",
          }}
        >
          {/* Accent strip */}
          <div className="h-[3px] shrink-0" style={{ background: "linear-gradient(90deg, transparent, var(--accent), transparent)" }} />

          {/* Messages area */}
          <div className="flex-1 px-5 py-4 overflow-y-auto space-y-3 flex flex-col min-h-0">
            <div className="flex-1 min-h-0" />

            {s.messages.length === 0 && s.sessionState === "ready" && (
              <div className="py-20 flex flex-col items-center gap-4">
                <div className="w-14 h-14 rounded-2xl flex items-center justify-center"
                  style={{ background: "rgba(99,102,241,0.08)" }}
                >
                  <MessageSquare size={24} style={{ color: "var(--accent)", opacity: 0.5 }} />
                </div>
                <p className="text-lg text-center leading-relaxed" style={{ color: "var(--text-muted)" }}>
                  Начните диалог
                </p>
                <p className="text-sm text-center" style={{ color: "var(--text-muted)", opacity: 0.6 }}>
                  Говорите в микрофон или пишите здесь
                </p>
              </div>
            )}

            {s.messages.map((msg) => (
              <ChatMessage key={msg.id} message={msg} />
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

            {s.transcription.status !== "idle" && <TranscriptionIndicator state={s.transcription} />}
            <div ref={messagesEndRef} />
          </div>

          {/* Text input — always visible at bottom */}
          {s.sessionState === "ready" && (
            <div className="shrink-0 px-4 py-3" style={{ borderTop: "1px solid rgba(255,255,255,0.06)", background: "rgba(0,0,0,0.2)" }}>
              <div className="flex items-end gap-2">
                <textarea
                  ref={textareaRef}
                  value={s.input}
                  onChange={(e) => s.setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Введите сообщение..."
                  disabled={s.sessionState !== "ready"}
                  rows={1}
                  aria-label="Введите сообщение"
                  className="vh-input max-h-28 min-h-[40px] flex-1 resize-none text-sm"
                  onInput={(e) => {
                    const t = e.target as HTMLTextAreaElement;
                    t.style.height = "auto";
                    t.style.height = Math.min(t.scrollHeight, 112) + "px";
                  }}
                />
                <motion.button
                  onClick={handleSend}
                  disabled={!s.input.trim() || s.sessionState !== "ready" || connectionState !== "connected"}
                  aria-label="Отправить"
                  className="flex h-[40px] w-[40px] shrink-0 items-center justify-center rounded-xl text-white"
                  style={{ background: "var(--accent)", opacity: !s.input.trim() || s.sessionState !== "ready" ? 0.4 : 1 }}
                  whileTap={{ scale: 0.95 }}
                >
                  <Send size={16} />
                </motion.button>
              </div>
            </div>
          )}
        </aside>

        {/* CENTER: Avatar + Mic */}
        <section className="training-session-panel training-session-center rounded-2xl relative flex flex-col items-center justify-center overflow-hidden"
          style={{ background: "radial-gradient(ellipse at center, rgba(99,102,241,0.06) 0%, transparent 70%)" }}
        >
          {/* Client name + emotion — top center */}
          <div className="absolute top-5 left-0 right-0 flex flex-col items-center gap-1.5 z-30">
            <div className="text-base font-semibold" style={{ color: "var(--text-primary)" }}>
              {s.characterName || "Клиент"}
            </div>
            <div className="flex items-center gap-2">
              <motion.div
                className="w-2 h-2 rounded-full"
                style={{ background: EMOTION_MAP[s.emotion]?.color || "#6D28D9" }}
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
                  style={{ color: EMOTION_MAP[s.emotion]?.color || "#6D28D9" }}
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
              style={{ background: EMOTION_MAP[s.emotion]?.color || "#6D28D9" }}
            />
            <Avatar3D
              emotion={s.emotion}
              isSpeaking={tts.speaking || s.micActive}
              audioLevel={tts.speaking ? tts.audioLevel : microphone.audioLevel || speech.audioLevel}
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

        {/* RIGHT: Stats Panel — hierarchy via background intensity */}
        <aside className="training-session-panel flex flex-col gap-2.5 overflow-y-auto">

          {/* ── PRIMARY: Mood + Acceptance ── */}
          <div className="rounded-2xl p-5" style={{ background: "rgba(255,255,255,0.04)" }}>
            <VibeMeter emotion={s.emotion} />
            {/* Acceptance bar inline */}
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
                    background: acceptanceScore >= 60 ? "linear-gradient(90deg, #22c55e, #00FF94)" : "linear-gradient(90deg, #F59E0B, #6366F1)",
                  }}
                />
              </div>
              <div className="mt-1.5 text-xs font-medium" style={{ color: acceptanceScore >= 60 ? "#00FF94" : "var(--text-muted)" }}>
                {acceptanceLabel}
              </div>
            </div>
          </div>

          {/* ── SECONDARY: Talk/Listen ratio ── */}
          <div className="rounded-xl p-4" style={{ background: "rgba(255,255,255,0.025)" }}>
            <TalkListenRatio talkPercent={s.talkTime + s.listenTime > 0 ? Math.round((s.talkTime / (s.talkTime + s.listenTime)) * 100) : 50} />
          </div>

          {/* ── Stage progress ── */}
          <div className="rounded-xl p-4" style={{ background: "rgba(255,255,255,0.02)" }}>
            <StageProgressBar
              currentStage={s.currentStage}
              stagesCompleted={s.stagesCompleted}
              totalStages={s.totalStages}
            />
          </div>

          {/* ── Emotion timeline sparkline ── */}
          {s.emotionHistory.length >= 2 && (
            <div className="rounded-xl p-4" style={{ background: "rgba(255,255,255,0.015)" }}>
              <LiveEmotionTimeline />
            </div>
          )}

          {/* ── Coaching whisper ── */}
          <div className="rounded-xl p-4" style={{ background: "rgba(255,255,255,0.015)" }}>
            <WhisperPanel onToggle={(enabled) => sendMessage({ type: "whisper.toggle", data: { enabled } })} />
          </div>

          {/* ── Difficulty indicator ── */}
          <div className="rounded-xl p-4" style={{ background: "rgba(255,255,255,0.01)" }}>
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

          {/* ── Human factors + Consequences — only when present ── */}
          {(s.humanFactors.length > 0 || s.consequences.length > 0) && (
            <div className="rounded-xl p-3 space-y-2">
              {s.humanFactors.length > 0 && (
                <div>
                  <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>Факторы</div>
                  <HumanFactorIcons factors={s.humanFactors} />
                </div>
              )}
              {s.consequences.length > 0 && (
                <div className="space-y-1.5">
                  {s.consequences.slice(-2).reverse().map((consequence, index) => (
                    <div key={`${consequence.call}-${consequence.type}-${index}`} className="rounded-lg px-3 py-2.5 text-sm" style={{ background: "rgba(239,68,68,0.06)", color: "var(--text-secondary)" }}>
                      <span className="font-semibold" style={{ color: "#F87171" }}>{consequence.type.replace(/_/g, " ")}</span>
                      <span className="ml-2 line-clamp-1">{consequence.detail}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ── Trap log (collapsible) ── */}
          {s.trapHistory.length > 0 && (
            <div className="rounded-xl p-3">
              <TrapLog />
            </div>
          )}

          {/* ── Score — compact with breakdown ── */}
          <div className="rounded-xl p-4 relative overflow-hidden" style={{ background: "rgba(255,255,255,0.02)" }}>
            <AnimatePresence>
              {checkpointFlash && (
                <motion.div
                  className="absolute inset-0 rounded-xl pointer-events-none"
                  initial={{ opacity: 0.4 }}
                  animate={{ opacity: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.8 }}
                  style={{ background: "radial-gradient(circle at center, rgba(0,255,148,0.15) 0%, transparent 70%)" }}
                />
              )}
            </AnimatePresence>
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold" style={{ color: "var(--text-secondary)" }}>Баллы</span>
              <motion.div
                className="text-xl font-bold tabular-nums"
                style={{ color: "var(--accent)" }}
                key={Math.round(s.scriptScore)}
                initial={{ scale: 1.2, opacity: 0.7 }}
                animate={{ scale: 1, opacity: 1 }}
                transition={{ type: "spring", stiffness: 500, damping: 25 }}
              >
                {s.messages.length === 0 ? "—" : <>{Math.round(s.scriptScore)}<span className="text-sm font-normal ml-0.5" style={{ color: "var(--text-muted)" }}>/100</span></>}
              </motion.div>
            </div>
            {scoreHint && (
              <div className="mt-3 space-y-2.5">
                {[
                  ["Возражения", scoreHint.objection_handling, "#F59E0B"],
                  ["Коммуникация", scoreHint.communication, "#3B82F6"],
                  ["Человеческий фактор", scoreHint.human_factor, "#EC4899"],
                ].map(([label, value, color]) => (
                  <div key={label as string}>
                    <div className="mb-1 flex items-center justify-between text-sm" style={{ color: "var(--text-muted)" }}>
                      <span>{label as string}</span>
                      <span className="font-semibold tabular-nums" style={{ color: color as string }}>{Math.round(value as number)}</span>
                    </div>
                    <div className="h-1.5 w-full rounded-full" style={{ background: "rgba(255,255,255,0.06)" }}>
                      <motion.div
                        className="h-full rounded-full"
                        animate={{ width: `${Math.min(100, ((value as number) / 18.75) * 100)}%` }}
                        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
                        style={{ background: color as string }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
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

      {/* ── Modals ──────────────────────────────────────────── */}
      <AnimatePresence>
        {s.sessionState === "completed" && (
          <motion.div key="modal-completed" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-[150] flex items-center justify-center" style={{ background: "rgba(0,0,0,0.8)", backdropFilter: "blur(8px)" }}>
            <motion.div initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ type: "spring", stiffness: 300, damping: 20 }} className="glass-panel px-8 sm:px-12 py-8 text-center max-w-md rounded-3xl">
              <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full" style={{ background: "rgba(0,255,102,0.1)", boxShadow: "0 0 40px rgba(0,255,102,0.15)" }}>
                <CheckCircle2 size={32} style={{ color: "#00FF66" }} />
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
                  <div className="font-display text-5xl font-black" style={{ color: sessionEndedRef.current.score >= 70 ? "#00FF66" : sessionEndedRef.current.score >= 40 ? "#FFB400" : "#FF3333" }}>
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
                  <span className="font-display font-bold text-lg" style={{ color: "#FFB400" }}>+{sessionEndedRef.current.xp} XP</span>
                </motion.div>
              )}
              {sessionEndedRef.current.levelUp && (
                <motion.div
                  initial={{ opacity: 0, scale: 0.8 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ delay: 0.9, type: "spring" }}
                  className="mt-3 inline-flex items-center gap-2 rounded-xl px-4 py-2"
                  style={{ background: "rgba(0,255,102,0.1)", border: "1px solid rgba(0,255,102,0.3)" }}
                >
                  <span className="font-display font-bold text-lg" style={{ color: "#00FF66" }}>УРОВЕНЬ ПОВЫШЕН!</span>
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
          <motion.div key="modal-abort" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-[150] flex items-center justify-center p-4" style={{ background: "rgba(0,0,0,0.7)", backdropFilter: "blur(8px)" }}>
            <motion.div initial={{ scale: 0.9 }} animate={{ scale: 1 }} className="glass-panel w-full max-w-md px-6 sm:px-8 py-7 text-center rounded-2xl">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full" style={{ background: "rgba(255,51,51,0.1)", border: "1px solid rgba(255,51,51,0.2)" }}>
                <XCircle size={26} style={{ color: "#FF3333" }} />
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
          <motion.div key="modal-silence" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-[150] flex items-center justify-center p-4" style={{ background: "rgba(0,0,0,0.7)", backdropFilter: "blur(8px)" }}>
            <motion.div initial={{ scale: 0.9 }} animate={{ scale: 1 }} className="glass-panel w-full max-w-md px-6 sm:px-8 py-7 text-center rounded-2xl">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full" style={{ background: "rgba(245,158,11,0.1)", border: "1px solid rgba(245,158,11,0.2)" }}>
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

      <HangupModal
        open={s.showHangupModal}
        data={s.hangupData}
        onRedial={() => {
          s.setShowHangupModal(false);
          s.setHangupData(null);
          if (s.storyMode && s.storyId) {
            sendMessage({ type: "story.next_call", data: { story_id: s.storyId } });
          }
        }}
        onResults={() => {
          s.setShowHangupModal(false);
          s.setHangupData(null);
          if (s.storyMode) {
            sendMessage({ type: "story.end", data: { story_id: s.storyId } });
          } else {
            sendMessage({ type: "session.end", data: {} });
          }
        }}
      />
    </div>
    </TrainingErrorBoundary>
  );
}
