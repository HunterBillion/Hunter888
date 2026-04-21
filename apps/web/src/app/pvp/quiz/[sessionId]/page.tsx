"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  BookOpen,
  Send,
  ChevronLeft,
  Clock,
  CheckCircle2,
  XCircle,
  Lightbulb,
  SkipForward,
  Trophy,
  Target,
  BarChart3,
  Brain,
  ArrowRight,
  Loader2,
  AlertTriangle,
  Sparkles,
  Flame,
  Star,
  Zap,
  Mic,
  MicOff,
} from "lucide-react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useSpeechRecognition } from "@/hooks/useSpeechRecognition";
import { AppIcon } from "@/components/ui/AppIcon";
import { useSound } from "@/hooks/useSound";
import { QuizThinkingIndicator } from "@/components/pvp/QuizThinkingIndicator";
import { QuizCaseIntro } from "@/components/pvp/QuizCaseIntro";
import { useKnowledgeStore, type QuizMessage } from "@/stores/useKnowledgeStore";
import { ErrorBoundary } from "@/components/errors/ErrorBoundary";
import { PageAuthGate } from "@/components/layout/PageAuthGate";
import { logger } from "@/lib/logger";
import type { WSMessage } from "@/types";

/* ─── Quiz Session Page ──────────────────────────────────────────────────── */

export default function KnowledgeSessionPageWrapper() {
  return (
    <PageAuthGate>
      <ErrorBoundary>
        <KnowledgeSessionPage />
      </ErrorBoundary>
    </PageAuthGate>
  );
}

function KnowledgeSessionPage() {
  const params = useParams();
  const router = useRouter();
  const sessionId = params.sessionId as string;

  const store = useKnowledgeStore();
  const { playSound } = useSound();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [showResults, setShowResults] = useState(false);
  const [hintLoading, setHintLoading] = useState(false);

  // 2026-04-20: голосовой ответ в knowledge quiz. Владельцу было важно
  // чтобы "во всей панели" работал голос — TTS для intro здесь уже есть
  // (QuizCaseIntro), а вот STT для ответа юзера — нет. Добавляем через
  // тот же useSpeechRecognition, что и в /training/[id]. Результат
  // хука дописывается в store.input, а не заменяет его — чтобы юзер мог
  // начать печатать, добавить голосом, поправить руками и отправить.
  const speech = useSpeechRecognition({
    lang: "ru-RU",
    onResult: (text: string) => {
      if (!text) return;
      const current = store.input.trim();
      // пробел-разделитель: если уже есть текст — добавляем с пробелом
      const next = current ? `${current} ${text}` : text;
      store.setInput(next);
    },
  });
  const handleMicToggle = useCallback(() => {
    if (!speech.isSupported) return;
    if (speech.status === "listening") {
      speech.stopListening();
    } else {
      speech.startListening();
    }
  }, [speech]);
  // quiz_v2: narrative case briefing (2026-04-18)
  const [caseIntro, setCaseIntro] = useState<{
    caseId: string;
    complexity: "simple" | "tangled" | "adversarial";
    introText: string;
    totalQuestions: number;
    personality: "professor" | "detective" | "blitz";
    audioUrl?: string | null;
  } | null>(null);

  // #7 fix: Reset store when navigating to a different session to prevent stale state leak
  useEffect(() => {
    if (store.sessionId && store.sessionId !== sessionId) {
      store.reset();
    }
    store.setSessionId(sessionId);
    store.setStatus("connecting");
  }, [sessionId]); // eslint-disable-line react-hooks/exhaustive-deps -- store setters are stable Zustand actions

  // WebSocket message handler
  const handleMessage = useCallback(
    (msg: WSMessage) => {
      const data: Record<string, unknown> = { ...msg, ...(msg.data || {}) };
      const type = msg.type;

      switch (type) {
        case "session_started": {
          store.setStatus("active");
          if (data.mode) {
            store.init(data.mode as typeof store.mode, data.category as string | undefined);
            store.setSessionId(sessionId);
            store.setStatus("active");
          }
          if (typeof data.total_questions === "number") {
            store.updateProgress({
              correct: 0,
              incorrect: 0,
              skipped: 0,
              score: 0,
              current: 0,
              total: data.total_questions as number,
            });
          }
          if (typeof data.time_limit === "number") {
            store.setTimeLeft(data.time_limit as number);
          }
          break;
        }

        // V2: quiz.ready with personality data
        // quiz_v2: narrative case briefing (2026-04-18)
        case "case.intro": {
          const cx = (data.complexity === "simple" || data.complexity === "tangled" || data.complexity === "adversarial")
            ? data.complexity
            : "simple";
          const p = (data.personality === "detective" || data.personality === "professor" || data.personality === "blitz")
            ? data.personality
            : "professor";
          setCaseIntro({
            caseId: String(data.case_id ?? "C-???"),
            complexity: cx as "simple" | "tangled" | "adversarial",
            introText: String(data.intro_text ?? ""),
            totalQuestions: Number(data.total_questions ?? 10),
            personality: p as "professor" | "detective" | "blitz",
            audioUrl: typeof data.audio_url === "string" ? data.audio_url : null,
          });
          break;
        }
        // quiz_v2: TTS audio arrives async AFTER case.intro (backend synth takes 1-3s)
        case "case.intro.audio": {
          const audio = typeof data.audio_url === "string" ? data.audio_url : null;
          if (audio) {
            setCaseIntro((prev) => prev ? { ...prev, audioUrl: audio } : prev);
          }
          break;
        }

        case "quiz.ready": {
          store.setStatus("active");
          store.setSessionId(sessionId);
          if (typeof data.total_questions === "number") {
            store.updateProgress({
              correct: 0, incorrect: 0, skipped: 0, score: 0, current: 0,
              total: data.total_questions as number,
            });
          }
          if (typeof data.time_limit_per_question === "number") {
            store.setTimeLeft(data.time_limit_per_question as number);
          }
          // V2: Set AI personality
          const personality = data.ai_personality as Record<string, string> | undefined;
          if (personality) {
            store.setAiPersonality({
              name: personality.name,
              displayName: personality.display_name,
              avatarEmoji: personality.avatar_emoji,
              greeting: personality.greeting,
            });
            // Show greeting as system message
            store.addMessage({
              type: "system",
              content: personality.greeting,
              avatarEmoji: personality.avatar_emoji,
            });
          }
          break;
        }

        case "question":
        case "quiz.question": {
          const content = (data.content || data.text) as string;
          const currentPersonality = useKnowledgeStore.getState().aiPersonality;
          store.addMessage({
            type: "question",
            content,
            category: data.category as string | undefined,
            avatarEmoji: currentPersonality?.avatarEmoji,
          });
          store.setIsTyping(false);
          // V2: Update difficulty from server
          if (typeof data.current_difficulty === "number") {
            store.setCurrentDifficulty(data.current_difficulty as number);
          }
          // Clear pending follow-up
          store.setPendingFollowUp(null);
          break;
        }

        // 2026-04-18 STREAMING: verdict arrives first (< 1-2s), UI shows ✓/✖ + sets up streaming bubble.
        case "quiz.feedback.verdict": {
          const correctAns = typeof data.correct_answer === "string" ? data.correct_answer : undefined;
          const articleRef = typeof data.article_reference === "string" ? data.article_reference : undefined;
          const isCorrect = Boolean(data.is_correct);
          store.setIsTyping(false);
          store.addMessage({
            type: "feedback",
            content: "",              // will be filled by chunk events
            isCorrect,
            correctAnswer: correctAns,
            articleRef,
            explanation: "",
          });
          if (isCorrect) {
            playSound("correct", 0.4);
          } else {
            playSound("incorrect", 0.3);
          }
          break;
        }
        // Streaming chunks — append to the last feedback message as tokens arrive.
        case "quiz.feedback.chunk": {
          const t = typeof data.text === "string" ? data.text : "";
          if (t) {
            store.appendToLastMessage(t);
          }
          break;
        }
        case "feedback":
        case "quiz.feedback": {
          // V2: Enhanced feedback with personality, streak, speed bonus
          const personalityComment = data.personality_comment as string | undefined;
          const speedBonus = data.speed_bonus as number | undefined;
          const feedbackContent = personalityComment
            ? `${personalityComment}\n\n${data.explanation as string || ""}`
            : (data.explanation as string || "");
          const currentPersonality2 = useKnowledgeStore.getState().aiPersonality;

          // SFX: correct/incorrect + streak milestone
          if (data.is_correct) {
            playSound("correct", 0.4);
            const streakVal = data.streak as number | undefined;
            if (streakVal && [3, 5, 7, 10].includes(streakVal)) {
              setTimeout(() => playSound("streak", 0.5), 300);
            }
          } else {
            playSound("incorrect", 0.3);
          }

          store.addMessage({
            type: "feedback",
            content: feedbackContent,
            isCorrect: data.is_correct as boolean,
            explanation: data.explanation as string | undefined,
            articleRef: (data.article_ref || data.article_reference) as string | undefined,
            // 2026-04-18: surface correct answer prominently in the bubble
            correctAnswer: (data.correct_answer || data.correct_answer_summary) as string | undefined,
            personalityComment,
            speedBonus,
            avatarEmoji: currentPersonality2?.avatarEmoji,
          });
          // V2: Update streak & difficulty
          if (typeof data.streak === "number") {
            store.setStreak(data.streak as number, (data.best_streak as number) ?? store.bestStreak);
          }
          if (typeof data.current_difficulty === "number") {
            store.setCurrentDifficulty(data.current_difficulty as number);
          }
          if (data.progress) {
            const p = data.progress as Record<string, number>;
            store.updateProgress({
              correct: p.correct ?? store.correct,
              incorrect: p.incorrect ?? store.incorrect,
              skipped: p.skipped ?? store.skipped,
              score: p.score ?? store.score,
              current: p.current ?? store.currentQuestion,
              total: p.total ?? store.totalQuestions,
            });
          }
          break;
        }

        // V2: Follow-up question from AI
        case "quiz.follow_up": {
          store.setPendingFollowUp(data.text as string);
          const currentPersonality3 = useKnowledgeStore.getState().aiPersonality;
          store.addMessage({
            type: "follow_up",
            content: data.text as string,
            avatarEmoji: currentPersonality3?.avatarEmoji,
          });
          break;
        }

        // V2: Progress update
        case "quiz.progress": {
          const p = data as Record<string, number>;
          store.updateProgress({
            correct: p.correct ?? store.correct,
            incorrect: p.incorrect ?? store.incorrect,
            skipped: p.skipped ?? store.skipped,
            score: p.score ?? store.score,
            current: p.current ?? store.currentQuestion,
            total: p.total ?? store.totalQuestions,
          });
          break;
        }

        // V2: Soft limit warning
        case "quiz.soft_limit": {
          store.addMessage({
            type: "system",
            content: data.text as string,
          });
          break;
        }

        case "hint":
        case "quiz.hint": {
          store.addMessage({
            type: "hint",
            content: (data.content || data.text) as string,
          });
          setHintLoading(false);
          break;
        }

        case "system":
        case "quiz.system_message": {
          store.addMessage({
            type: "system",
            content: (data.content || data.text) as string,
          });
          break;
        }

        case "typing": {
          store.setIsTyping(true);
          break;
        }

        case "timer_sync":
        case "quiz.timeout": {
          if (typeof data.time_left === "number") {
            store.setTimeLeft(data.time_left as number);
          }
          break;
        }

        case "session_completed":
        case "quiz.completed": {
          store.setResults(data.results as Record<string, unknown>);
          store.setStatus("completed");
          setShowResults(true);
          if (timerRef.current) {
            clearInterval(timerRef.current);
            timerRef.current = null;
          }
          // SFX: victory or defeat based on score
          const resultScore = ((data.results as Record<string, unknown>)?.score as number) ?? 0;
          playSound(resultScore >= 50 ? "victory" : "defeat", 0.5);
          break;
        }

        case "error": {
          store.addMessage({
            type: "system",
            content: `Ошибка: ${data.message || "Неизвестная ошибка"}`,
          });
          break;
        }

        default:
          logger.warn("[Knowledge WS] Unknown message type:", type);
      }
    },
    [sessionId], // eslint-disable-line react-hooks/exhaustive-deps -- store actions are stable Zustand refs
  );

  // WebSocket connection
  const { sendMessage, isConnected, connectionState } = useWebSocket({
    path: `/ws/knowledge`,
    onMessage: handleMessage,
    autoConnect: true,
  });

  // Send quiz.start when WS connects and status is still "connecting"
  useEffect(() => {
    if (isConnected && store.status === "connecting") {
      // Retrieve mode/category from URL search params or store
      const params = new URLSearchParams(window.location.search);
      const mode = params.get("mode") || store.mode || "free_dialog";
      const category = params.get("category") || store.category || undefined;
      const personality = params.get("personality") || undefined;
      sendMessage({
        type: "quiz.start",
        data: { mode, category, ai_personality: personality },
      });
    }
  }, [isConnected, store.status, sendMessage]); // eslint-disable-line react-hooks/exhaustive-deps

  // Timer for blitz mode
  // Extract boolean so we don't put a raw expression in the deps array
  // (which React can't track) and don't use the numeric timeLeft value
  // (which would restart the interval every second).
  const hasTimeLeft = store.timeLeft !== null;
  useEffect(() => {
    if (store.mode === "blitz" && hasTimeLeft && store.status === "active") {
      timerRef.current = setInterval(() => {
        store.tickTimer();
      }, 1000);
      return () => {
        if (timerRef.current) {
          clearInterval(timerRef.current);
          timerRef.current = null;
        }
      };
    }
    // store.tickTimer is a stable Zustand action — safe to omit.
  }, [store.mode, store.status, hasTimeLeft]); // eslint-disable-line react-hooks/exhaustive-deps -- store.tickTimer is a stable Zustand action (documented above)

  // SFX: tick sound for last 10 seconds in blitz
  useEffect(() => {
    if (store.mode === "blitz" && store.timeLeft !== null && store.timeLeft <= 10 && store.timeLeft > 0) {
      playSound("tick", 0.2);
    }
  }, [store.mode, store.timeLeft, playSound]);

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [store.messages.length, store.isTyping]);

  // #6 fix: Sanitize user input — strip control chars, cap length
  const MAX_ANSWER_LENGTH = 2000;
  const sanitizeInput = (raw: string): string => {
    // Remove zero-width and control characters (keep newlines/tabs)
    // eslint-disable-next-line no-control-regex
    return raw.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F\u200B-\u200F\uFEFF]/g, "").slice(0, MAX_ANSWER_LENGTH);
  };

  // Send answer
  const handleSend = useCallback(() => {
    const text = sanitizeInput(store.input.trim());
    if (!text || store.status !== "active") return;

    store.addMessage({ type: "answer", content: text });
    sendMessage({ type: "answer", content: text });
    store.setInput("");
    store.setIsTyping(true);

    // Focus back on input
    setTimeout(() => inputRef.current?.focus(), 50);
  }, [store.input, store.status, sendMessage]); // eslint-disable-line react-hooks/exhaustive-deps -- store setters are stable Zustand actions

  // Skip question
  const handleSkip = useCallback(() => {
    sendMessage({ type: "skip" });
    store.addMessage({ type: "system", content: "Вопрос пропущен" });
  }, [sendMessage]); // eslint-disable-line react-hooks/exhaustive-deps -- store.addMessage is a stable Zustand action

  // Request hint
  const handleHint = useCallback(() => {
    if (hintLoading) return;
    setHintLoading(true);
    sendMessage({ type: "hint_request" });
  }, [hintLoading, sendMessage]);

  // Keyboard submit
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Format time
  const formatTime = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, "0")}`;
  };

  const progressPct =
    store.totalQuestions > 0
      ? Math.round((store.currentQuestion / store.totalQuestions) * 100)
      : 0;

  // ─── Results Screen ────────────────────────────────
  if (showResults || store.status === "completed") {
    const results = store.results || {};
    const accuracy =
      store.correct + store.incorrect > 0
        ? Math.round((store.correct / (store.correct + store.incorrect)) * 100)
        : 0;

    return (
      <div
        className="flex min-h-screen flex-col"
        style={{ background: "var(--bg-primary)" }}
      >
        <div className="flex-1 flex items-center justify-center p-4">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="glass-panel max-w-lg w-full p-8 relative overflow-hidden"
          >
            <div
              className="absolute top-0 left-0 right-0 h-[2px]"
              style={{
                background:
                  "linear-gradient(90deg, transparent, #6366F1, transparent)",
              }}
            />

            <div className="text-center">
              <motion.div
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ delay: 0.2, type: "spring", stiffness: 200 }}
                className="mx-auto flex h-20 w-20 items-center justify-center rounded-full"
                style={{
                  background:
                    accuracy >= 75
                      ? "rgba(61,220,132,0.1)"
                      : accuracy >= 50
                        ? "rgba(245,158,11,0.1)"
                        : "var(--danger-muted)",
                  border: `2px solid ${accuracy >= 75 ? "#00FF6640" : accuracy >= 50 ? "#F59E0B40" : "#FF333340"}`,
                }}
              >
                <Trophy
                  size={36}
                  style={{
                    color:
                      accuracy >= 75
                        ? "var(--success)"
                        : accuracy >= 50
                          ? "var(--warning)"
                          : "var(--danger)",
                  }}
                />
              </motion.div>

              <h2
                className="mt-5 font-display text-2xl font-bold"
                style={{ color: "var(--text-primary)" }}
              >
                Квиз завершён!
              </h2>
              <p
                className="mt-1 text-sm"
                style={{ color: "var(--text-secondary)" }}
              >
                {accuracy >= 75
                  ? "Отличный результат!"
                  : accuracy >= 50
                    ? "Хороший результат, но есть куда расти"
                    : "Стоит повторить материал"}
              </p>
            </div>

            <div className="mt-8 grid grid-cols-2 gap-3">
              <div
                className="rounded-xl p-4 text-center"
                style={{
                  background: "rgba(61,220,132,0.06)",
                  border: "1px solid rgba(61,220,132,0.15)",
                }}
              >
                <div
                  className="font-display text-3xl font-bold"
                  style={{ color: "var(--success)" }}
                >
                  {store.correct}
                </div>
                <div
                  className="mt-1 font-mono text-sm uppercase tracking-widest"
                  style={{ color: "var(--text-muted)" }}
                >
                  Верно
                </div>
              </div>
              <div
                className="rounded-xl p-4 text-center"
                style={{
                  background: "var(--danger-muted)",
                  border: "1px solid var(--danger-muted)",
                }}
              >
                <div
                  className="font-display text-3xl font-bold"
                  style={{ color: "var(--danger)" }}
                >
                  {store.incorrect}
                </div>
                <div
                  className="mt-1 font-mono text-sm uppercase tracking-widest"
                  style={{ color: "var(--text-muted)" }}
                >
                  Неверно
                </div>
              </div>
              <div
                className="rounded-xl p-4 text-center"
                style={{
                  background: "var(--accent-muted)",
                  border: "1px solid var(--accent-muted)",
                }}
              >
                <div
                  className="font-display text-3xl font-bold"
                  style={{ color: "var(--accent)" }}
                >
                  {accuracy}%
                </div>
                <div
                  className="mt-1 font-mono text-sm uppercase tracking-widest"
                  style={{ color: "var(--text-muted)" }}
                >
                  Точность
                </div>
              </div>
              <div
                className="rounded-xl p-4 text-center"
                style={{
                  background: "rgba(245,158,11,0.06)",
                  border: "1px solid rgba(245,158,11,0.15)",
                }}
              >
                <div
                  className="font-display text-3xl font-bold"
                  style={{ color: "var(--warning)" }}
                >
                  {store.score}
                </div>
                <div
                  className="mt-1 font-mono text-sm uppercase tracking-widest"
                  style={{ color: "var(--text-muted)" }}
                >
                  Очки
                </div>
              </div>
            </div>

            {/* V2: Streak counter with animation */}
            <AnimatePresence>
              {store.streak >= 2 && (
                <motion.div
                  key={`streak-${store.streak}`}
                  initial={{ opacity: 0, scale: 0.8 }}
                  animate={{ opacity: 1, scale: [1, 1.15, 1] }}
                  exit={{ opacity: 0, scale: 0.8 }}
                  transition={{ duration: 0.4 }}
                  className="mt-3 flex items-center justify-center gap-1 rounded-lg py-1.5 px-3"
                  style={{
                    background: store.streak >= 5
                      ? "rgba(249,115,22,0.2)"
                      : "rgba(249,115,22,0.1)",
                    border: `1px solid rgba(249,115,22,${store.streak >= 5 ? 0.4 : 0.2})`,
                    boxShadow: store.streak >= 5
                      ? "0 0 12px rgba(249,115,22,0.3)"
                      : "none",
                  }}
                >
                  <motion.span
                    className="text-orange-500 text-sm"
                    animate={store.streak >= 5 ? { scale: [1, 1.3, 1] } : {}}
                    transition={{ repeat: Infinity, duration: 1.5 }}
                  >
                    <Flame size={16} style={{ color: "var(--warning)" }} />
                  </motion.span>
                  <span className="font-mono text-sm font-bold" style={{ color: "var(--warning)" }}>
                    {store.streak}
                  </span>
                  {store.streak >= 5 && (
                    <motion.span
                      className="text-sm font-mono text-orange-400 ml-1"
                      animate={{ opacity: [0.6, 1, 0.6] }}
                      transition={{ repeat: Infinity, duration: 1.2 }}
                    >
                      В УДАРЕ!
                    </motion.span>
                  )}
                </motion.div>
              )}
            </AnimatePresence>

            {/* V2: Difficulty indicator */}
            {store.currentDifficulty > 0 && (
              <div className="mt-2 text-center">
                <span className="font-mono text-sm tracking-wider" style={{ color: "var(--text-muted)" }}>
                  СЛОЖНОСТЬ{" "}
                </span>
                {Array.from({ length: 5 }).map((_, i) => (
                  <span key={i} style={{ color: i < store.currentDifficulty ? "var(--warning)" : "var(--text-muted)", fontSize: "14px" }}>
                    <Star size={12} style={{ color: "var(--rank-gold)" }} />
                  </span>
                ))}
              </div>
            )}

            {store.skipped > 0 && (
              <div
                className="mt-3 text-center font-mono text-sm"
                style={{ color: "var(--text-muted)" }}
              >
                Пропущено: {store.skipped}
              </div>
            )}

            {/* #5 fix: Category progress from server results */}
            {Array.isArray(results.category_progress) && (results.category_progress as Array<{ category: string; correct: number; total: number }>).length > 0 && (
              <div className="mt-6">
                <h3 className="font-mono text-sm uppercase tracking-widest mb-3" style={{ color: "var(--text-muted)" }}>
                  По категориям
                </h3>
                <div className="space-y-2">
                  {(results.category_progress as Array<{ category: string; correct: number; total: number }>).map((cat) => {
                    const pct = cat.total > 0 ? Math.round((cat.correct / cat.total) * 100) : 0;
                    return (
                      <div key={cat.category}>
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-sm" style={{ color: "var(--text-secondary)" }}>{cat.category}</span>
                          <span className="font-mono text-sm" style={{ color: pct >= 75 ? "var(--success)" : pct >= 50 ? "var(--warning)" : "var(--danger)" }}>
                            {cat.correct}/{cat.total} ({pct}%)
                          </span>
                        </div>
                        <div className="h-1.5 rounded-full overflow-hidden" style={{ background: "rgba(255,255,255,0.06)" }}>
                          <div
                            className="h-full rounded-full transition-all"
                            style={{
                              width: `${pct}%`,
                              background: pct >= 75 ? "var(--success)" : pct >= 50 ? "var(--warning)" : "var(--danger)",
                            }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Weak categories — highlight areas needing improvement */}
            {Array.isArray(results.category_progress) && (() => {
              const weak = (results.category_progress as Array<{ category: string; correct: number; total: number }>)
                .filter(c => c.total > 0 && (c.correct / c.total) < 0.6);
              if (weak.length === 0) return null;
              return (
                <div
                  className="mt-4 rounded-xl p-4"
                  style={{
                    background: "color-mix(in srgb, var(--warning) 6%, transparent)",
                    border: "1px solid color-mix(in srgb, var(--warning) 20%, transparent)",
                  }}
                >
                  <div className="flex items-center gap-2 mb-2">
                    <span className="font-mono text-sm uppercase tracking-widest font-bold" style={{ color: "var(--warning)" }}>
                      Слабые категории ФЗ-127
                    </span>
                  </div>
                  <ul className="space-y-1">
                    {weak.map(c => (
                      <li key={c.category} className="flex items-start gap-2 text-sm" style={{ color: "var(--text-secondary)" }}>
                        <span style={{ color: "var(--danger)", flexShrink: 0 }}>→</span>
                        <span><strong>{c.category}</strong> — {c.correct}/{c.total} ({Math.round((c.correct / c.total) * 100)}%). Рекомендуем дополнительную тренировку.</span>
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })()}

            {/* Server summary */}
            {typeof results.summary === "string" && results.summary && (
              <div
                className="mt-4 rounded-xl p-3 text-sm leading-relaxed"
                style={{ background: "var(--accent-muted)", border: "1px solid var(--accent-muted)", color: "var(--text-secondary)" }}
              >
                {results.summary as string}
              </div>
            )}

            <div className="mt-8 flex gap-3">
              <motion.button
                onClick={() => {
                  store.reset();
                  router.push("/pvp");
                }}
                className="flex flex-1 items-center justify-center gap-2 rounded-xl border px-4 py-3 font-mono text-sm tracking-wider transition-all"
                style={{
                  borderColor: "rgba(255,255,255,0.08)",
                  background: "rgba(255,255,255,0.03)",
                  color: "var(--text-secondary)",
                }}
                whileTap={{ scale: 0.98 }}
              >
                <ChevronLeft size={14} />
                К выбору режима
              </motion.button>
              <motion.button
                onClick={() => {
                  store.reset();
                  store.init(store.mode, store.category ?? undefined);
                  // Would create new session
                  router.push("/pvp");
                }}
                className="btn-neon flex flex-1 items-center justify-center gap-2"
                whileTap={{ scale: 0.98 }}
              >
                Ещё раз
                <ArrowRight size={14} />
              </motion.button>
            </div>
          </motion.div>
        </div>
      </div>
    );
  }

  // ─── Chat Interface ────────────────────────────────
  return (
    <div
      className="flex h-screen flex-col relative"
      style={{
        background: "var(--bg-primary)",
        // 2026-04-18 fix: add pixel-arcade background (was blank/empty).
        backgroundImage: `
          radial-gradient(ellipse at top, var(--accent-muted) 0%, transparent 60%),
          repeating-linear-gradient(0deg, transparent 0, transparent 23px, rgba(107,77,199,0.035) 23px, rgba(107,77,199,0.035) 24px),
          repeating-linear-gradient(90deg, transparent 0, transparent 23px, rgba(107,77,199,0.035) 23px, rgba(107,77,199,0.035) 24px)
        `,
      }}
    >
      {/* quiz_v2: case briefing overlay — pops in when backend emits case.intro */}
      {caseIntro && (
        <QuizCaseIntro
          caseId={caseIntro.caseId}
          complexity={caseIntro.complexity}
          introText={caseIntro.introText}
          totalQuestions={caseIntro.totalQuestions}
          personality={caseIntro.personality}
          audioUrl={caseIntro.audioUrl}
          onAccept={() => setCaseIntro(null)}
        />
      )}

      {/* Top Bar — pixel arcade (2026-04-18: enlarged padding + min-height so components breathe) */}
      <div
        className="shrink-0 px-5 sm:px-6"
        style={{
          paddingTop: 14,
          paddingBottom: 14,
          minHeight: 72,
          borderBottom: "2px solid var(--accent)",
          background: "var(--bg-primary)",
          boxShadow: "0 2px 0 0 rgba(0,0,0,0.15), 0 4px 0 0 var(--accent-muted)",
          position: "relative",
          zIndex: 10,
        }}
      >
        <div className="mx-auto flex max-w-3xl items-center justify-between">
          {/* Left: Back + Mode */}
          <div className="flex items-center gap-3">
            <motion.button
              onClick={() => {
                store.reset();
                router.push("/pvp");
              }}
              whileHover={{ y: -1 }}
              whileTap={{ y: 2 }}
              className="flex items-center justify-center"
              style={{
                width: 44, height: 44,
                background: "var(--input-bg)",
                border: "2px solid var(--border-color)",
                borderRadius: 0,
                color: "var(--text-secondary)",
                boxShadow: "2px 2px 0 0 var(--border-color)",
                transition: "box-shadow 140ms ease-out, transform 140ms ease-out",
              }}
            >
              <ChevronLeft size={22} />
            </motion.button>
            <div>
              <div
                className="font-pixel uppercase tracking-wider"
                style={{ color: "var(--accent)", textShadow: "0 0 6px var(--accent-glow)", fontSize: 16 }}
              >
                ▶ {store.mode === "blitz"
                  ? "БЛИЦ"
                  : store.mode === "themed"
                    ? "ПО ТЕМЕ"
                    : store.mode === "pvp"
                      ? "PVP"
                      : "ДИАЛОГ"}
              </div>
              {store.category && (
                <div className="font-pixel uppercase tracking-wider mt-1" style={{ color: "var(--text-muted)", fontSize: 14 }}>
                  ● {store.category}
                </div>
              )}
            </div>
          </div>

          {/* Center: segmented pixel progress bar (arcade healthbar) */}
          <div className="flex items-center gap-3">
            {store.totalQuestions > 0 && (
              <div className="flex items-center gap-2">
                <div className="hidden sm:flex items-center gap-1" aria-label={`Прогресс ${store.currentQuestion}/${store.totalQuestions}`}>
                  {Array.from({ length: Math.min(store.totalQuestions, 12) }).map((_, i) => {
                    const filled = i < Math.round((store.currentQuestion / store.totalQuestions) * Math.min(store.totalQuestions, 12));
                    return (
                      <span
                        key={i}
                        style={{
                          width: 14,
                          height: 18,
                          background: filled ? "var(--accent)" : "var(--input-bg)",
                          border: `2px solid ${filled ? "var(--accent)" : "var(--border-color)"}`,
                          borderRadius: 0,
                          boxShadow: filled ? "0 0 6px var(--accent-glow)" : "none",
                          transition: "background 180ms ease-out, border-color 180ms ease-out",
                        }}
                      />
                    );
                  })}
                </div>
                <span className="font-pixel uppercase tracking-wider tabular-nums" style={{ color: "var(--text-primary)", fontSize: 16 }}>
                  {store.currentQuestion}/{store.totalQuestions}
                </span>
              </div>
            )}
          </div>

          {/* Right: Pixel scoreboard + timer */}
          <div className="flex items-center gap-2">
            {/* Score box — pixel retro (only shown in active quiz) */}
            {(store.correct > 0 || store.incorrect > 0) && (
              <div
                className="flex items-center gap-2 px-3 py-1.5 font-pixel tabular-nums"
                style={{
                  background: "var(--input-bg)",
                  border: "2px solid var(--accent)",
                  borderRadius: 0,
                  boxShadow: "2px 2px 0 0 var(--accent-muted)",
                  fontSize: 16,
                }}
              >
                <span style={{ color: "var(--success)" }}>✓{store.correct}</span>
                <span style={{ color: "var(--text-muted)" }}>│</span>
                <span style={{ color: "var(--danger)" }}>✖{store.incorrect}</span>
              </div>
            )}

            {store.timeLeft !== null && (
              <motion.div
                className="flex items-center gap-2 px-3 py-1.5 font-pixel uppercase tracking-wider"
                animate={store.timeLeft <= 10 ? { scale: [1, 1.08, 1] } : {}}
                transition={{ duration: 0.6, repeat: store.timeLeft <= 10 ? Infinity : 0, ease: "easeInOut" }}
                style={{
                  background: store.timeLeft <= 30 ? "rgba(239,68,68,0.15)" : "rgba(245,158,11,0.1)",
                  color: store.timeLeft <= 30 ? "var(--danger)" : "var(--warning)",
                  border: `2px solid ${store.timeLeft <= 30 ? "var(--danger)" : "var(--warning)"}`,
                  borderRadius: 0,
                  boxShadow: `2px 2px 0 0 ${store.timeLeft <= 30 ? "var(--danger)" : "var(--warning)"}`,
                  fontSize: 15,
                }}
              >
                <Clock size={14} />
                <span className="tabular-nums">{formatTime(store.timeLeft)}</span>
              </motion.div>
            )}
          </div>
        </div>
      </div>

      {/* Chat Messages — pixel-grid arcade background (2026-04-18 UX fix) */}
      <div
        className="flex-1 overflow-y-auto relative"
        style={{
          backgroundImage: `
            radial-gradient(ellipse at 50% 20%, rgba(107,77,199,0.12) 0%, transparent 55%),
            repeating-linear-gradient(0deg, transparent 0, transparent 31px, rgba(107,77,199,0.06) 31px, rgba(107,77,199,0.06) 32px),
            repeating-linear-gradient(90deg, transparent 0, transparent 31px, rgba(107,77,199,0.06) 31px, rgba(107,77,199,0.06) 32px)
          `,
        }}
      >
        <div className="mx-auto max-w-3xl px-4 py-6 space-y-4 relative">
          {/* Connection status */}
          {connectionState !== "connected" && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex items-center justify-center gap-2 py-8"
            >
              <Loader2
                size={20}
                className="animate-spin"
                style={{ color: "var(--accent)" }}
              />
              <span
                className="font-mono text-sm"
                style={{ color: "var(--text-muted)" }}
              >
                {connectionState === "connecting"
                  ? "Подключение..."
                  : "Переподключение..."}
              </span>
            </motion.div>
          )}

          {/* Messages */}
          {store.messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}

          {/* Typing indicator — rotating arcade messages (2026-04-18) */}
          <AnimatePresence>
            {store.isTyping && <QuizThinkingIndicator />}
          </AnimatePresence>

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* V2: Follow-up action bar */}
      {store.pendingFollowUp && (
        <div
          className="shrink-0 border-t px-4 py-3"
          style={{
            borderColor: "var(--accent-muted)",
            background: "var(--accent-muted)",
          }}
        >
          <div className="mx-auto flex max-w-3xl items-center justify-between">
            <span className="text-sm" style={{ color: "var(--text-muted)" }}>
              Уточняющий вопрос — вы можете ответить или пропустить
            </span>
            <div className="flex gap-2">
              <button
                className="rounded-lg px-3 py-1.5 text-sm font-medium transition-colors"
                style={{ background: "var(--accent-muted)", color: "var(--accent)" }}
                onClick={() => {
                  store.setPendingFollowUp(null);
                  // Let user type answer normally - next text.message will be treated as follow-up answer
                }}
              >
                Ответить
              </button>
              <button
                className="rounded-lg px-3 py-1.5 text-sm font-medium transition-colors"
                style={{ background: "rgba(255,255,255,0.06)", color: "var(--text-muted)" }}
                onClick={() => {
                  store.setPendingFollowUp(null);
                  sendMessage({ type: "quiz.follow_up_response", data: { action: "skip" } });
                }}
              >
                Пропустить
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ═══ Pixel Input Bar — 2026-04-18 redesigned:
             - opaque solid background (no stray artifacts behind input)
             - explicit per-element padding so hard-shadows don't collide
             - "SEND" label hides on <sm; keeps bar compact on mobile
         ═══ */}
      <div
        className="shrink-0 relative"
        style={{
          borderTop: "2px solid var(--accent)",
          background: "var(--bg-primary)",
          boxShadow: "0 -2px 0 0 rgba(0,0,0,0.15)",
          zIndex: 10,
          paddingTop: 14,
          paddingBottom: 14,
          paddingLeft: 12,
          paddingRight: 12,
        }}
      >
        <div className="mx-auto flex max-w-3xl items-end gap-3">
          {/* Hint button — pixel amber. 2026-04-18: hidden in blitz (hints not available, user was seeing error toast). */}
          {store.mode !== "blitz" && (
          <motion.button
            onClick={handleHint}
            disabled={hintLoading || store.status !== "active"}
            whileHover={{ y: -1 }}
            whileTap={{ y: 2 }}
            className="flex h-11 w-11 shrink-0 items-center justify-center disabled:opacity-40"
            style={{
              background: "rgba(245,158,11,0.12)",
              border: "2px solid var(--warning)",
              borderRadius: 0,
              color: "var(--warning)",
              boxShadow: "2px 2px 0 0 var(--warning)",
              transition: "box-shadow 120ms, transform 120ms",
            }}
            title="Подсказка"
            aria-label="Подсказка"
          >
            {hintLoading ? <Loader2 size={16} className="animate-spin" /> : <Lightbulb size={16} />}
          </motion.button>
          )}

          {/* Skip button — pixel neutral */}
          <motion.button
            onClick={handleSkip}
            disabled={store.status !== "active"}
            whileHover={{ y: -1 }}
            whileTap={{ y: 2 }}
            className="flex h-11 w-11 shrink-0 items-center justify-center disabled:opacity-40"
            style={{
              background: "var(--input-bg)",
              border: "2px solid var(--border-color)",
              borderRadius: 0,
              color: "var(--text-muted)",
              boxShadow: "2px 2px 0 0 var(--border-color)",
              transition: "box-shadow 120ms, transform 120ms",
            }}
            title="Пропустить"
            aria-label="Пропустить"
          >
            <SkipForward size={16} />
          </motion.button>

          {/* Pixel text input */}
          <div
            className="flex flex-1 items-end relative min-w-0"
            style={{
              background: "var(--input-bg)",
              border: "2px solid var(--accent)",
              borderRadius: 0,
              boxShadow: "2px 2px 0 0 var(--accent-muted)",
              minHeight: 44,
            }}
          >
            <textarea
              ref={inputRef}
              value={store.input}
              onChange={(e) => store.setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                speech.status === "listening"
                  ? "◉ Говорите…"
                  : "▸ ВВЕДИТЕ ОТВЕТ ИЛИ НАЖМИТЕ 🎤"
              }
              rows={1}
              className="flex-1 resize-none bg-transparent px-3 py-2.5 text-sm outline-none placeholder:opacity-50"
              style={{
                color: "var(--text-primary)",
                maxHeight: "120px",
                fontFamily: "var(--font-mono, monospace)",
              }}
              disabled={store.status !== "active"}
            />
            {/* 2026-04-20: live interim transcript — шёпот справа, чтобы
                юзер видел что именно распозналось ДО вставки в input. */}
            {speech.status === "listening" && speech.interimText && (
              <div
                className="absolute right-2 bottom-0 translate-y-full mt-1 max-w-[60%] truncate text-[11px]"
                style={{ color: "var(--accent)" }}
              >
                ▸ {speech.interimText}
              </div>
            )}
          </div>

          {/* 2026-04-20: Mic toggle button.
              Pixel-стиль совпадает с hint/skip/send. Цвет:
                danger (красный) во время записи — явный signal,
                border-accent в покое.
              Если браузер не поддерживает Web Speech API — кнопка
              disabled с tooltip-объяснением. */}
          <motion.button
            onClick={handleMicToggle}
            disabled={store.status !== "active" || !speech.isSupported}
            whileTap={{ y: 2 }}
            className="flex h-11 w-11 shrink-0 items-center justify-center disabled:opacity-40"
            style={{
              background:
                speech.status === "listening"
                  ? "var(--danger)"
                  : "var(--input-bg)",
              border:
                speech.status === "listening"
                  ? "2px solid var(--danger)"
                  : "2px solid var(--accent)",
              borderRadius: 0,
              color:
                speech.status === "listening" ? "#fff" : "var(--accent)",
              boxShadow:
                speech.status === "listening"
                  ? "2px 2px 0 0 #000"
                  : "2px 2px 0 0 var(--accent-muted)",
              transition: "box-shadow 120ms, transform 120ms, background 120ms",
            }}
            title={
              !speech.isSupported
                ? "Голосовой ввод не поддерживается в этом браузере"
                : speech.status === "listening"
                ? "Остановить запись"
                : "Голосовой ответ"
            }
            aria-label={
              speech.status === "listening" ? "Остановить микрофон" : "Включить микрофон"
            }
            aria-pressed={speech.status === "listening"}
          >
            {speech.status === "listening" ? <MicOff size={16} /> : <Mic size={16} />}
          </motion.button>

          {/* Send — pixel arcade accent */}
          <motion.button
            onClick={handleSend}
            disabled={!store.input.trim() || store.status !== "active"}
            whileHover={{ y: -1 }}
            whileTap={{ y: 2 }}
            className="flex h-11 shrink-0 items-center justify-center gap-1.5 px-3 sm:px-4 disabled:opacity-40 font-pixel text-sm uppercase tracking-widest"
            style={{
              background: "var(--accent)",
              border: "2px solid var(--accent)",
              borderRadius: 0,
              color: "#fff",
              boxShadow: "2px 2px 0 0 #000",
              transition: "box-shadow 120ms, transform 120ms",
            }}
            aria-label="Отправить"
          >
            <Send size={14} />
            <span className="hidden sm:inline">SEND</span>
          </motion.button>
        </div>
      </div>
    </div>
  );
}

/* ─── Message Bubble Component ────────────────────────────────────────────── */

function MessageBubble({ message }: { message: QuizMessage }) {
  const isUser = message.type === "answer";
  const isSystem = message.type === "system";
  const isFeedback = message.type === "feedback";
  const isHint = message.type === "hint";
  const isQuestion = message.type === "question";
  const isFollowUp = message.type === "follow_up";

  // V2: Avatar emoji from personality
  const avatarEmoji = message.avatarEmoji;

  // System messages
  if (isSystem) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex justify-center"
      >
        <div
          className="px-4 py-1.5 font-pixel text-sm uppercase tracking-widest"
          style={{
            background: "var(--input-bg)",
            color: "var(--text-muted)",
            border: "2px solid var(--border-color)",
            borderRadius: 0,
            boxShadow: "2px 2px 0 0 rgba(0,0,0,0.15)",
          }}
        >
          ▌{message.content}
        </div>
      </motion.div>
    );
  }

  // ═══ Hint message — amber pixel card
  if (isHint) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-start gap-3"
      >
        <div
          className="flex h-9 w-9 shrink-0 items-center justify-center"
          style={{
            background: "rgba(245,158,11,0.1)",
            border: "2px solid var(--warning)",
            borderRadius: 0,
            boxShadow: "2px 2px 0 0 var(--warning)",
          }}
        >
          <Lightbulb size={14} style={{ color: "var(--warning)" }} />
        </div>
        <div
          className="max-w-[90%] sm:max-w-[80%] px-4 py-3 relative"
          style={{
            background: "rgba(245,158,11,0.06)",
            border: "2px solid var(--warning)",
            borderRadius: 0,
            boxShadow: "3px 3px 0 0 rgba(245,158,11,0.35)",
          }}
        >
          <div
            className="font-pixel text-[13px] uppercase tracking-widest mb-1"
            style={{ color: "var(--warning)" }}
          >
            💡 ПОДСКАЗКА
          </div>
          <p className="text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
            {message.content}
          </p>
        </div>
      </motion.div>
    );
  }

  // ═══ Feedback message — green/red pixel with speed bonus
  if (isFeedback) {
    const correct = message.isCorrect;
    const color = correct ? "var(--success)" : "var(--danger)";
    const bgColor = correct ? "var(--success-muted)" : "var(--danger-muted)";

    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-start gap-3"
      >
        <div
          className="flex h-9 w-9 shrink-0 items-center justify-center"
          style={{
            background: bgColor,
            border: `2px solid ${color}`,
            borderRadius: 0,
            boxShadow: `2px 2px 0 0 ${color}`,
          }}
        >
          {correct ? <CheckCircle2 size={14} style={{ color }} /> : <XCircle size={14} style={{ color }} />}
        </div>
        <div
          className="max-w-[90%] sm:max-w-[80%] px-4 py-3"
          style={{
            background: bgColor,
            border: `2px solid ${color}`,
            borderRadius: 0,
            boxShadow: `3px 3px 0 0 ${color}`,
          }}
        >
          <div
            className="font-pixel text-[13px] uppercase tracking-widest mb-1"
            style={{ color, textShadow: `0 0 6px ${color}` }}
          >
            {correct ? "▸ ВЕРНО! +XP" : "✖ НЕВЕРНО"}
          </div>
          {message.explanation && (
            <p className="text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
              {message.explanation}
            </p>
          )}
          {/* 2026-04-18: dedicated "ПРАВИЛЬНО" block — always visible when wrong answer + correct known */}
          {!message.isCorrect && message.correctAnswer && (
            <div
              className="mt-3 px-3 py-2"
              style={{
                background: "rgba(34,197,94,0.08)",
                border: "2px solid var(--success)",
                borderRadius: 0,
                boxShadow: "2px 2px 0 0 rgba(34,197,94,0.35)",
              }}
            >
              <div className="font-pixel text-[13px] uppercase tracking-widest mb-1" style={{ color: "var(--success)" }}>
                ▸ ПРАВИЛЬНО
              </div>
              <div className="text-sm leading-relaxed" style={{ color: "var(--text-primary)" }}>
                {message.correctAnswer}
              </div>
            </div>
          )}
          {message.articleRef && (
            <div
              className="mt-2 inline-flex items-center gap-1.5 font-pixel text-[13px] uppercase tracking-wider px-2 py-1"
              style={{
                color: "var(--text-muted)",
                background: "var(--input-bg)",
                border: "1px solid var(--border-color)",
                borderRadius: 0,
              }}
            >
              <BookOpen size={11} />
              {message.articleRef}
            </div>
          )}
          {message.speedBonus && message.speedBonus > 0 && (
            <div
              className="mt-2 inline-flex items-center gap-1 px-2 py-1 font-pixel text-[13px] uppercase tracking-wider"
              style={{
                background: "var(--warning)",
                color: "#000",
                border: "2px solid var(--warning)",
                borderRadius: 0,
                boxShadow: "2px 2px 0 0 #000",
              }}
            >
              <Zap size={11} /> +{message.speedBonus} SPEED
            </div>
          )}
        </div>
      </motion.div>
    );
  }

  // ═══ Follow-up message
  if (isFollowUp) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-start gap-3"
      >
        <div
          className="flex h-9 w-9 shrink-0 items-center justify-center text-lg"
          style={{
            background: "var(--accent-muted)",
            border: "2px solid var(--accent)",
            borderRadius: 0,
            boxShadow: "2px 2px 0 0 var(--accent)",
          }}
        >
          {avatarEmoji ? <AppIcon emoji={avatarEmoji} size={18} /> : <AppIcon emoji={"\uD83D\uDCA1"} size={18} />}
        </div>
        <div
          className="max-w-[90%] sm:max-w-[80%] px-4 py-3"
          style={{
            background: "var(--accent-muted)",
            border: "2px solid var(--accent)",
            borderRadius: 0,
            boxShadow: "3px 3px 0 0 var(--accent-muted), 3px 3px 0 2px rgba(0,0,0,0.15)",
          }}
        >
          <div className="font-pixel text-[13px] uppercase tracking-widest mb-1" style={{ color: "var(--accent)" }}>
            ▸ FOLLOW-UP (опц.)
          </div>
          <p className="text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
            {message.content}
          </p>
        </div>
      </motion.div>
    );
  }

  // ═══ Question from AI
  if (isQuestion) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-start gap-3"
      >
        <div
          className="flex h-9 w-9 shrink-0 items-center justify-center text-lg"
          style={{
            background: "var(--accent-muted)",
            border: "2px solid var(--accent)",
            borderRadius: 0,
            boxShadow: "2px 2px 0 0 var(--accent)",
          }}
        >
          {avatarEmoji ? <AppIcon emoji={avatarEmoji} size={18} /> : <BookOpen size={14} style={{ color: "var(--accent)" }} />}
        </div>
        <div
          className="max-w-[90%] sm:max-w-[80%] px-4 py-3"
          style={{
            background: "var(--bg-panel)",
            border: "2px solid var(--accent)",
            borderRadius: 0,
            boxShadow: "3px 3px 0 0 var(--accent-muted), 3px 3px 0 2px rgba(0,0,0,0.15)",
          }}
        >
          {message.category && (
            <div
              className="inline-block font-pixel text-[13px] uppercase tracking-widest mb-2 px-2 py-0.5"
              style={{
                color: "#fff",
                background: "var(--accent)",
                border: "1px solid var(--accent)",
                borderRadius: 0,
              }}
            >
              ▸ {message.category}
            </div>
          )}
          <p className="text-sm leading-relaxed" style={{ color: "var(--text-primary)" }}>
            {message.content}
          </p>
        </div>
      </motion.div>
    );
  }

  // ═══ User answer — pixel accent bubble right-aligned
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex justify-end"
    >
      <div
        className="max-w-[90%] sm:max-w-[80%] px-4 py-3"
        style={{
          background: "var(--accent)",
          color: "#fff",
          border: "2px solid var(--accent)",
          borderRadius: 0,
          boxShadow: "-3px 3px 0 0 #000, 0 0 10px var(--accent-glow)",
        }}
      >
        <div className="font-pixel text-[13px] uppercase tracking-widest mb-1 opacity-70">
          ВЫ ▸
        </div>
        <p className="text-sm leading-relaxed" style={{ color: "#fff" }}>
          {message.content}
        </p>
      </div>
    </motion.div>
  );
}
