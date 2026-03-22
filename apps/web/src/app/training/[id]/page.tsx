"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import dynamic from "next/dynamic";
import {
  Clock,
  XCircle,
  CheckCircle2,
  AlertTriangle,
  Send,
  Volume2,
  VolumeX,
  Radio,
  Lightbulb,
} from "lucide-react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useSpeechRecognition } from "@/hooks/useSpeechRecognition";
import { useTTS } from "@/hooks/useTTS";
import { MicCheck } from "@/components/training/MicCheck";
import ChatMessage from "@/components/training/ChatMessage";
import { CrystalMic } from "@/components/training/CrystalMic";
import TranscriptionIndicator from "@/components/training/TranscriptionIndicator";
import VibeMeter from "@/components/training/VibeMeter";
import ScriptAdherence, { type CheckpointInfo } from "@/components/training/ScriptAdherence";
import TalkListenRatio from "@/components/training/TalkListenRatio";
import { TrapNotification, TrapSummaryBadge, type TrapEvent } from "@/components/training/TrapNotification";
import { ClientCard, type ClientCardData } from "@/components/training/ClientCard";
import { ClientCardMini } from "@/components/training/ClientCardMini";
import { HumanFactorIcons } from "@/components/training/HumanFactorIcons";
import { StoryProgress } from "@/components/training/StoryProgress";
import { ConsequenceToast } from "@/components/training/ConsequenceToast";
import { PreCallBriefOverlay } from "@/components/training/PreCallBriefOverlay";
import { StoryCallReportOverlay } from "@/components/training/StoryCallReportOverlay";
import { BetweenCallsOverlay } from "@/components/training/BetweenCallsOverlay";
import { useSessionStore } from "@/stores/useSessionStore";
import { useHotkeys } from "@/hooks/useHotkeys";
import { LogoSeparator } from "@/components/ui/LogoSeparator";
import {
  type EmotionState,
  type ObjectionHint,
  type CheckpointHint,
  type SoftSkillsUpdate,
  EMOTION_MAP,
} from "@/types";
import { logger } from "@/lib/logger";

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
  const storyCustomParams = {
    archetype: searchParams.get("custom_archetype") || undefined,
    profession: searchParams.get("custom_profession") || undefined,
    lead_source: searchParams.get("custom_lead_source") || undefined,
    difficulty: searchParams.get("custom_difficulty") ? Number(searchParams.get("custom_difficulty")) : undefined,
  };

  // ── Zustand store (replaces 30+ useState) ──
  const s = useSessionStore();

  // Initialize store on mount
  useEffect(() => {
    s.init(routeId);
    return () => { s.reset(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routeId]);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
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

  // TTS — ElevenLabs (primary) + browser speechSynthesis (fallback)
  const tts = useTTS({ lang: "ru-RU", rate: 0.95, pitch: 1.0 });

  const { sendMessage, connectionState } = useWebSocket({
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
            setTimeout(() => router.push(`/results/${routeId}`), 1500);
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
          s.setSttAvailable(false);
          s.setTextMode(true);
          break;

        case "emotion.update":
          if (data.data.current) s.setEmotion(data.data.current as EmotionState);
          break;

        case "score.update":
          if (data.data.script_score !== undefined) s.setScriptScore(data.data.script_score as number);
          if (data.data.checkpoints_hit !== undefined) s.setCheckpointsHit(data.data.checkpoints_hit as number);
          if (data.data.checkpoints_total !== undefined) s.setCheckpointsTotal(data.data.checkpoints_total as number);
          if (Array.isArray(data.data.checkpoints)) s.setCheckpoints(data.data.checkpoints as CheckpointInfo[]);
          break;

        case "score.hint":
          setScoreHint({
            objection_handling: Number(data.data.objection_handling || 0),
            communication: Number(data.data.communication || 0),
            human_factor: Number(data.data.human_factor || 0),
            realtime_estimate: Number(data.data.realtime_estimate || 0),
            max_possible_realtime: Number(data.data.max_possible_realtime || 0),
          });
          break;

        case "silence.warning":
          s.setSilenceWarning(true);
          setTimeout(() => s.setSilenceWarning(false), 5000);
          break;

        case "silence.timeout":
          s.setShowSilenceModal(true);
          break;

        case "session.timeout":
          s.setSessionState("completed");
          if (timerRef.current) clearInterval(timerRef.current);
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
          setTimeout(() => s.setObjectionHint(null), 4000);
          break;
        }

        case "hint.checkpoint": {
          const cpHint: CheckpointHint = {
            checkpoint: data.data.checkpoint as string,
            status: data.data.status as CheckpointHint["status"],
          };
          s.setCheckpointHint(cpHint);
          setTimeout(() => s.setCheckpointHint(null), 3000);
          break;
        }

        case "soft_skills.update": {
          const skills = data.data as unknown as SoftSkillsUpdate;
          if (skills.talk_ratio !== undefined) {
            const serverTalk = Math.round(skills.talk_ratio * 100);
            s.setTalkTime(serverTalk);
            s.setListenTime(100 - serverTalk);
          }
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
          s.setPreCallBrief(data.data as unknown as import("@/types/story").PreCallBrief);
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
            window.setTimeout(() => {
              setActiveConsequence((current) => (
                current && current.call === consequence.call && current.type === consequence.type ? null : current
              ));
            }, 4500);
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

        case "error":
          logger.error("Training error:", data.data.message);
          break;
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
  useEffect(() => {
    if (connectionState === "connected" && s.sessionState === "connecting") {
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
  }, [connectionState, s.sessionState, routeId, sendMessage, isStoryMode, storyScenarioId, storyCalls, storyCustomParams]);

  // Handle WS disconnect
  useEffect(() => {
    if (connectionState === "disconnected" && s.sessionState !== "completed") {
      s.setSessionState("connecting");
    }
  }, [connectionState, s.sessionState, s]);

  // Timer
  useEffect(() => {
    if (s.sessionState === "ready") {
      timerRef.current = setInterval(() => s.tickElapsed(), 1000);
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [s.sessionState, s]);

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

  const handleMicPress = () => {
    if (s.sessionState === "ready" && s.sttAvailable) {
      if (tts.speaking) tts.stop();
      speech.startListening();
      s.setMicActive(true);
    }
  };

  const handleMicRelease = () => {
    if (speech.status === "listening") {
      speech.stopListening();
      s.setMicActive(false);
    }
  };

  const handleContinueSession = () => {
    s.setShowSilenceModal(false);
    sendMessage({ type: "silence.continue", data: {} });
  };

  // Track talk/listen time — 1s interval
  useEffect(() => {
    if (s.sessionState !== "ready") return;
    const iv = setInterval(() => {
      if (s.micActive) {
        s.setTalkTime(s.talkTime + 1);
      } else if (s.isTyping || tts.speaking) {
        s.setListenTime(s.listenTime + 1);
      }
    }, 1000);
    return () => clearInterval(iv);
  }, [s.sessionState, s.micActive, s.isTyping, tts.speaking, s]);

  const talkPercent = s.talkTime + s.listenTime > 0 ? Math.round((s.talkTime / (s.talkTime + s.listenTime)) * 100) : 50;

  // ── Connecting gate ──
  if (s.sessionState === "connecting" && !s.showPreCallBrief && !storyCallReport) {
    return (
      <div className="flex h-screen flex-col items-center justify-center" style={{ background: "var(--bg-primary)" }}>
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-transparent" style={{ borderTopColor: "var(--accent)" }} />
        <span className="mt-4 font-mono text-xs tracking-widest" style={{ color: "var(--text-muted)" }}>
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
    <div className="flex h-screen flex-col overflow-hidden" style={{ background: "var(--bg-primary)" }}>
      {/* ── Scanlines overlay ──────────────────────────────── */}
      <div className="fixed inset-0 scanlines z-[100] opacity-15 mix-blend-overlay pointer-events-none" />

      {/* Global mic glow */}
      <div className={`fixed inset-0 global-mic-glow z-50 ${s.micActive ? "active" : ""}`} />

      {/* ── Top HUD Header ─────────────────────────────────── */}
      <header
        className="h-16 shrink-0 glass-panel rounded-none flex justify-between items-center px-6 z-20"
        style={{ borderTop: "2px solid rgba(139,92,246,0.3)", borderRadius: 0 }}
      >
        <div className="flex items-center gap-4">
          <div
            className="w-2 h-2 rounded-full animate-pulse"
            style={{
              background: connectionState === "connected" ? "#00FF66" : "var(--neon-red)",
              boxShadow: connectionState === "connected" ? "0 0 10px #00FF66" : "0 0 10px #FF3333",
            }}
          />
          <span className="font-mono text-xs tracking-widest" style={{ color: "var(--text-muted)" }}>
            LAYER 4: <span style={{ color: "var(--text-primary)" }}>
              {connectionState === "connected" ? "ONLINE" : "OFFLINE"}
            </span>
          </span>
        </div>

        <div className="font-display font-black text-xl tracking-[0.15em] flex items-center gap-2">
          <span style={{ color: "var(--accent)" }}>X</span><span style={{ color: "var(--text-primary)" }}>HUNTER</span>
          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded ml-2" style={{ background: "var(--accent-muted)", color: "var(--accent)" }}>
            v2.4
          </span>
        </div>

        <div className="flex items-center gap-4">
          <div className="text-right hidden md:block">
            <div className="font-mono text-[10px] tracking-widest" style={{ color: "var(--text-muted)" }}>SESSION TIME</div>
            <div
              className={`font-mono text-sm ${s.elapsed >= 1500 ? "animate-pulse" : ""}`}
              style={{ color: s.elapsed >= 1500 ? "var(--warning)" : "var(--accent)" }}
            >
              {formatTime(s.elapsed)}
            </div>
          </div>

          <motion.button
            onClick={() => tts.setEnabled(!tts.enabled)}
            className="flex items-center justify-center rounded-lg p-1.5"
            style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)" }}
            whileTap={{ scale: 0.95 }}
            title={`Голос AI: ${tts.mode === "elevenlabs" ? "ElevenLabs" : "Браузер"}`}
          >
            {tts.enabled ? <Volume2 size={14} style={{ color: "var(--accent)" }} /> : <VolumeX size={14} style={{ color: "var(--text-muted)" }} />}
          </motion.button>

          <button onClick={() => s.setShowAbortModal(true)} disabled={s.sessionState !== "ready"} className="vh-btn-danger">
            <span>ABORT FLIGHT</span>
          </button>
        </div>
      </header>

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
      <main className="flex-1 grid grid-cols-1 lg:grid-cols-12 gap-4 p-4 md:p-6 min-h-0 z-20">
        {/* LEFT: Live Transcript */}
        <aside className="hidden lg:flex lg:col-span-3 glass-panel rounded-xl flex-col overflow-hidden" style={{ borderLeft: "2px solid rgba(139,92,246,0.3)" }}>
          <div className="p-4 border-b flex justify-between items-center shrink-0" style={{ borderColor: "var(--border-color)", background: "rgba(0,0,0,0.2)" }}>
            <h2 className="font-display tracking-widest text-sm flex items-center gap-2" style={{ color: "var(--text-secondary)" }}>
              <Radio size={14} style={{ color: "var(--accent)" }} /> LIVE TRANSCRIPT
            </h2>
            <span className="flex gap-1 items-center">
              <span className="w-1.5 h-1.5 rounded-full animate-ping" style={{ background: "var(--accent)" }} />
              <span className="text-[10px] font-mono" style={{ color: "var(--accent)" }}>REC</span>
            </span>
          </div>

          <div className="flex-1 p-4 overflow-y-auto space-y-3 flex flex-col justify-end">
            {s.messages.length === 0 && s.sessionState === "ready" && (
              <p className="py-8 text-center text-xs" style={{ color: "var(--text-muted)" }}>Начните диалог</p>
            )}

            {s.messages.map((msg) => (
              <ChatMessage key={msg.id} message={msg} />
            ))}

            {s.isTyping && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex items-center gap-2 py-1 text-xs" style={{ color: "var(--text-muted)" }}>
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
        </aside>

        {/* CENTER: Avatar + Mic */}
        <section className="col-span-1 lg:col-span-6 glass-panel rounded-xl relative flex flex-col items-center justify-center overflow-hidden"
          style={{ border: "1px solid rgba(139,92,246,0.2)", boxShadow: "inset 0 0 50px rgba(0,0,0,0.3)" }}
        >
          {/* Spinning orbit circles */}
          <div className="absolute inset-0 pointer-events-none flex items-center justify-center opacity-10">
            <div className="w-[450px] h-[450px] rounded-full border border-dashed animate-spin-slow" style={{ borderColor: "var(--accent)" }} />
            <div className="absolute w-[350px] h-[350px] rounded-full border animate-spin-slow-reverse" style={{ borderColor: "rgba(139,92,246,0.5)" }} />
          </div>

          {/* Emotion indicator */}
          <div className="absolute top-6 left-6 flex flex-col gap-1 z-30">
            <span className="font-mono text-[10px] tracking-widest uppercase" style={{ color: "var(--text-muted)" }}>
              Target Emotion State
            </span>
            <div className="flex items-center gap-2">
              <motion.div
                className="w-2 h-2 rounded-full"
                style={{ background: EMOTION_MAP[s.emotion]?.color || "#6D28D9" }}
                animate={{ boxShadow: `0 0 8px ${EMOTION_MAP[s.emotion]?.glow || "rgba(109,40,217,0.4)"}` }}
              />
              <span className="font-display font-bold tracking-widest text-lg uppercase"
                style={{ color: EMOTION_MAP[s.emotion]?.color || "#6D28D9" }}
              >
                {EMOTION_MAP[s.emotion]?.label || "UNKNOWN"}
              </span>
            </div>
          </div>

          {/* STT warning */}
          {!s.sttAvailable && s.sessionState === "ready" && (
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              className="absolute top-6 right-6 z-30 flex items-center gap-2 rounded-xl px-3 py-2 text-xs"
              style={{ background: "rgba(245,158,11,0.1)", border: "1px solid rgba(245,158,11,0.2)", color: "var(--warning)" }}
            >
              <AlertTriangle size={14} />
              STT недоступно
            </motion.div>
          )}

          {/* Avatar */}
          <div className="relative w-full aspect-square max-w-[500px] flex items-center justify-center z-10">
            <div className="absolute inset-0 rounded-full opacity-20 blur-[80px] transition-colors duration-1000"
              style={{ background: EMOTION_MAP[s.emotion]?.color || "#6D28D9" }}
            />
            <Avatar3D
              emotion={s.emotion}
              isSpeaking={tts.speaking || speech.status === "listening"}
              audioLevel={tts.speaking ? tts.audioLevel : speech.audioLevel}
              className="absolute inset-0 z-20"
            />
          </div>

          {/* Mic / Text input */}
          <div className="absolute bottom-8 left-1/2 -translate-x-1/2 z-30 w-full max-w-lg px-4">
            {s.textMode ? (
              <div className="flex items-end gap-2">
                <textarea
                  ref={textareaRef}
                  value={s.input}
                  onChange={(e) => s.setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={s.sessionState === "ready" ? "Введите сообщение..." : "Ожидание подключения..."}
                  disabled={s.sessionState !== "ready"}
                  rows={1}
                  className="vh-input max-h-32 min-h-[42px] flex-1 resize-none"
                  onInput={(e) => {
                    const t = e.target as HTMLTextAreaElement;
                    t.style.height = "auto";
                    t.style.height = Math.min(t.scrollHeight, 128) + "px";
                  }}
                />
                <motion.button
                  onClick={handleSend}
                  disabled={!s.input.trim() || s.sessionState !== "ready"}
                  className="flex h-[42px] w-[42px] shrink-0 items-center justify-center rounded-xl text-white"
                  style={{ background: "var(--accent)", opacity: !s.input.trim() || s.sessionState !== "ready" ? 0.4 : 1 }}
                  whileTap={{ scale: 0.95 }}
                >
                  <Send size={18} />
                </motion.button>
              </div>
            ) : (
              <CrystalMic
                isRecording={speech.status === "listening"}
                isProcessing={s.transcription.status === "transcribing"}
                audioLevel={speech.audioLevel}
                onPress={handleMicPress}
                onRelease={handleMicRelease}
                onTextMode={() => s.setTextMode(true)}
                disabled={s.sessionState !== "ready" || !s.sttAvailable}
              />
            )}
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

        {/* RIGHT: Stats Panel — progressive reveal per ТЗ */}
        <aside className="col-span-1 lg:col-span-3 flex flex-col gap-4">
          {/* VibeMeter: appears after 3 minutes */}
          <AnimatePresence>
            {s.elapsed >= 180 && (
              <motion.div initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.5 }}>
                <VibeMeter emotion={s.emotion} />
              </motion.div>
            )}
          </AnimatePresence>

          {/* ScriptAdherence: appears after 5 minutes */}
          <AnimatePresence>
            {s.elapsed >= 300 && (
              <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.5 }}>
                <ScriptAdherence progress={s.scriptScore} checkpointsHit={s.checkpointsHit} checkpointsTotal={s.checkpointsTotal} checkpoints={s.checkpoints} highlightCheckpoint={s.checkpointHint?.checkpoint ?? null} />
              </motion.div>
            )}
          </AnimatePresence>

          {/* TalkListenRatio: appears after 5 minutes */}
          <AnimatePresence>
            {s.elapsed >= 300 && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.5, delay: 0.2 }}>
                <TalkListenRatio talkPercent={talkPercent} />
              </motion.div>
            )}
          </AnimatePresence>

          {/* TrapSummary: always visible (traps can appear any time) */}
          <TrapSummaryBadge fell={s.trapsFell} dodged={s.trapsDodged} netScore={s.trapNetScore} />

          {/* Live Score */}
          <div className="rounded-xl p-5" style={{ background: "var(--glass-bg)", border: "1px solid var(--glass-border)", backdropFilter: "blur(20px)" }}>
            <div className="font-mono text-[10px] uppercase tracking-widest mb-2" style={{ color: "var(--text-muted)" }}>LIVE SCORE</div>
            <div className="text-3xl font-bold glow-text-purple" style={{ color: "var(--accent)" }}>
              {Math.round(s.scriptScore)}
              <span className="text-sm font-normal ml-1" style={{ color: "var(--text-muted)" }}>/100</span>
            </div>
            {scoreHint && (
              <div className="mt-4 space-y-2">
                <div className="flex items-center justify-between text-[11px]" style={{ color: "var(--text-secondary)" }}>
                  <span>RT Estimate</span>
                  <span className="font-mono" style={{ color: "var(--accent)" }}>
                    {scoreHint.realtime_estimate}/{scoreHint.max_possible_realtime}
                  </span>
                </div>
                {[
                  ["Возражения", scoreHint.objection_handling, "#F59E0B"],
                  ["Коммуникация", scoreHint.communication, "#3B82F6"],
                  ["Human Factor", scoreHint.human_factor, "#EC4899"],
                ].map(([label, value, color]) => (
                  <div key={label as string}>
                    <div className="mb-1 flex items-center justify-between text-[10px]" style={{ color: "var(--text-muted)" }}>
                      <span>{label as string}</span>
                      <span>{Math.round(value as number)}</span>
                    </div>
                    <div className="h-1.5 w-full rounded-full" style={{ background: "var(--input-bg)" }}>
                      <div
                        className="h-full rounded-full transition-all duration-500"
                        style={{ width: `${Math.min(100, ((value as number) / 18.75) * 100)}%`, background: color as string }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </aside>
      </main>

      {/* ── Trap Notification ──────────────────────────────── */}
      <TrapNotification event={s.activeTrap} onDismiss={() => s.setActiveTrap(null)} />

      {/* ── Objection Hint Toast ──────────────────────────── */}
      <AnimatePresence>
        {s.objectionHint && (
          <motion.div
            initial={{ opacity: 0, x: 40 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 40 }}
            className="fixed bottom-6 left-6 z-[160] max-w-xs"
          >
            <div
              className="rounded-xl p-3 backdrop-blur-xl flex items-start gap-3"
              style={{
                background: "rgba(139,92,246,0.1)",
                border: "1px solid rgba(139,92,246,0.3)",
                boxShadow: "0 0 20px rgba(139,92,246,0.15)",
              }}
            >
              <Lightbulb size={16} style={{ color: "var(--accent)", flexShrink: 0, marginTop: 2 }} />
              <div>
                <div className="font-mono text-[10px] tracking-widest uppercase" style={{ color: "var(--accent)" }}>
                  ПОДСКАЗКА
                </div>
                <div className="text-xs mt-1" style={{ color: "var(--text-secondary)" }}>
                  {s.objectionHint.message}
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Checkpoint Hint Toast ─────────────────────────── */}
      <AnimatePresence>
        {s.checkpointHint && (
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="fixed top-20 left-1/2 -translate-x-1/2 z-[140]"
          >
            <div
              className="rounded-xl px-4 py-2 backdrop-blur-xl flex items-center gap-2"
              style={{
                background: "rgba(139,92,246,0.1)",
                border: "1px solid rgba(139,92,246,0.3)",
                boxShadow: "0 0 15px rgba(139,92,246,0.1)",
              }}
            >
              <CheckCircle2 size={14} style={{ color: "var(--accent)" }} />
              <span className="font-mono text-[11px]" style={{ color: "var(--text-secondary)" }}>
                Сейчас хорошо бы: <span style={{ color: "var(--accent)" }}>{s.checkpointHint.checkpoint}</span>
              </span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Silence Warning Banner ──────────────────────────── */}
      <AnimatePresence>
        {s.silenceWarning && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
            className="fixed bottom-24 left-1/2 -translate-x-1/2 z-[140] flex items-center gap-3 rounded-xl px-5 py-3"
            style={{
              background: "rgba(245,158,11,0.15)",
              border: "1px solid rgba(245,158,11,0.3)",
              backdropFilter: "blur(12px)",
              boxShadow: "0 0 20px rgba(245,158,11,0.15)",
            }}
          >
            <AlertTriangle size={18} style={{ color: "var(--warning)" }} />
            <span className="font-mono text-sm" style={{ color: "var(--warning)" }}>
              Вы молчите — скоро сессия будет приостановлена
            </span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Timer Warning (25min+) ────────────────────────── */}
      <AnimatePresence>
        {s.elapsed >= 1500 && s.elapsed < 1800 && s.sessionState === "ready" && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed top-20 right-6 z-[130] flex items-center gap-2 rounded-xl px-4 py-2"
            style={{
              background: "rgba(245,158,11,0.1)",
              border: "1px solid rgba(245,158,11,0.2)",
              backdropFilter: "blur(12px)",
            }}
          >
            <Clock size={14} style={{ color: "var(--warning)" }} />
            <span className="font-mono text-xs" style={{ color: "var(--warning)" }}>
              {formatTime(1800 - s.elapsed)} до лимита
            </span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Modals ──────────────────────────────────────────── */}
      <AnimatePresence>
        {s.sessionState === "completed" && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-[150] flex items-center justify-center" style={{ background: "rgba(0,0,0,0.7)" }}>
            <motion.div initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} className="glass-panel px-8 py-6 text-center">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full" style={{ background: "rgba(0,255,102,0.1)" }}>
                <CheckCircle2 size={24} style={{ color: "#00FF66" }} />
              </div>
              <h2 className="mt-3 font-display text-lg font-bold" style={{ color: "var(--text-primary)" }}>
                FLIGHT COMPLETED
              </h2>
              <p className="mt-1 font-mono text-xs" style={{ color: "var(--text-muted)" }}>
                Analyzing data...
              </p>
            </motion.div>
          </motion.div>
        )}

        {s.showAbortModal && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-[150] flex items-center justify-center" style={{ background: "rgba(0,0,0,0.7)" }}>
            <motion.div initial={{ scale: 0.9 }} animate={{ scale: 1 }} className="glass-panel max-w-sm px-8 py-6 text-center">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full" style={{ background: "rgba(255,51,51,0.1)" }}>
                <XCircle size={24} style={{ color: "#FF3333" }} />
              </div>
              <h2 className="mt-3 font-display text-lg font-bold" style={{ color: "var(--text-primary)" }}>
                Прервать тренировку?
              </h2>
              <p className="mt-2 text-sm" style={{ color: "var(--text-secondary)" }}>
                Прогресс будет сохранён, но сессия завершится досрочно.
              </p>
              <div className="mt-4 flex justify-center gap-3">
                <motion.button onClick={() => s.setShowAbortModal(false)} className="vh-btn-outline" whileTap={{ scale: 0.97 }}>
                  Продолжить
                </motion.button>
                <motion.button onClick={() => { s.setShowAbortModal(false); handleEnd(); }} className="vh-btn-danger flex items-center gap-2" whileTap={{ scale: 0.97 }}>
                  <XCircle size={14} /> Завершить
                </motion.button>
              </div>
            </motion.div>
          </motion.div>
        )}

        {s.showSilenceModal && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-[150] flex items-center justify-center" style={{ background: "rgba(0,0,0,0.7)" }}>
            <motion.div initial={{ scale: 0.9 }} animate={{ scale: 1 }} className="glass-panel max-w-sm px-8 py-6 text-center">
              <h2 className="font-display text-lg font-bold" style={{ color: "var(--warning)" }}>
                SIGNAL LOST
              </h2>
              <p className="mt-2 text-sm" style={{ color: "var(--text-secondary)" }}>
                Вы давно молчите. Продолжить тренировку?
              </p>
              <div className="mt-4 flex justify-center gap-3">
                <motion.button onClick={handleContinueSession} className="vh-btn-primary" whileTap={{ scale: 0.97 }}>
                  Продолжить
                </motion.button>
                <motion.button onClick={handleEnd} className="vh-btn-outline" whileTap={{ scale: 0.97 }}>
                  Завершить
                </motion.button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
