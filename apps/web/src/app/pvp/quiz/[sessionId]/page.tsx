"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  BookOpen,
  Send,
  ArrowLeft,
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
} from "lucide-react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useSound } from "@/hooks/useSound";
import { useKnowledgeStore, type QuizMessage } from "@/stores/useKnowledgeStore";
import { ErrorBoundary } from "@/components/errors/ErrorBoundary";
import { logger } from "@/lib/logger";
import type { WSMessage } from "@/types";

/* ─── Quiz Session Page ──────────────────────────────────────────────────── */

export default function KnowledgeSessionPageWrapper() {
  return (
    <ErrorBoundary>
      <KnowledgeSessionPage />
    </ErrorBoundary>
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
                      ? "rgba(0,255,102,0.1)"
                      : accuracy >= 50
                        ? "rgba(245,158,11,0.1)"
                        : "rgba(255,51,51,0.1)",
                  border: `2px solid ${accuracy >= 75 ? "#00FF6640" : accuracy >= 50 ? "#F59E0B40" : "#FF333340"}`,
                }}
              >
                <Trophy
                  size={36}
                  style={{
                    color:
                      accuracy >= 75
                        ? "#00FF66"
                        : accuracy >= 50
                          ? "#F59E0B"
                          : "#FF3333",
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
                  background: "rgba(0,255,102,0.06)",
                  border: "1px solid rgba(0,255,102,0.15)",
                }}
              >
                <div
                  className="font-display text-3xl font-bold"
                  style={{ color: "#00FF66" }}
                >
                  {store.correct}
                </div>
                <div
                  className="mt-1 font-mono text-xs uppercase tracking-widest"
                  style={{ color: "var(--text-muted)" }}
                >
                  Верно
                </div>
              </div>
              <div
                className="rounded-xl p-4 text-center"
                style={{
                  background: "rgba(255,51,51,0.06)",
                  border: "1px solid rgba(255,51,51,0.15)",
                }}
              >
                <div
                  className="font-display text-3xl font-bold"
                  style={{ color: "#FF3333" }}
                >
                  {store.incorrect}
                </div>
                <div
                  className="mt-1 font-mono text-xs uppercase tracking-widest"
                  style={{ color: "var(--text-muted)" }}
                >
                  Неверно
                </div>
              </div>
              <div
                className="rounded-xl p-4 text-center"
                style={{
                  background: "rgba(99,102,241,0.06)",
                  border: "1px solid rgba(99,102,241,0.15)",
                }}
              >
                <div
                  className="font-display text-3xl font-bold"
                  style={{ color: "#6366F1" }}
                >
                  {accuracy}%
                </div>
                <div
                  className="mt-1 font-mono text-xs uppercase tracking-widest"
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
                  style={{ color: "#F59E0B" }}
                >
                  {store.score}
                </div>
                <div
                  className="mt-1 font-mono text-xs uppercase tracking-widest"
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
                    {"\uD83D\uDD25"}
                  </motion.span>
                  <span className="font-mono text-sm font-bold" style={{ color: "#F97316" }}>
                    {store.streak}
                  </span>
                  {store.streak >= 5 && (
                    <motion.span
                      className="text-xs font-mono text-orange-400 ml-1"
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
                <span className="font-mono text-xs tracking-wider" style={{ color: "var(--text-muted)" }}>
                  СЛОЖНОСТЬ{" "}
                </span>
                {Array.from({ length: 5 }).map((_, i) => (
                  <span key={i} style={{ color: i < store.currentDifficulty ? "#F59E0B" : "var(--text-muted)", fontSize: "12px" }}>
                    {"\u2B50"}
                  </span>
                ))}
              </div>
            )}

            {store.skipped > 0 && (
              <div
                className="mt-3 text-center font-mono text-xs"
                style={{ color: "var(--text-muted)" }}
              >
                Пропущено: {store.skipped}
              </div>
            )}

            {/* #5 fix: Category progress from server results */}
            {Array.isArray(results.category_progress) && (results.category_progress as Array<{ category: string; correct: number; total: number }>).length > 0 && (
              <div className="mt-6">
                <h3 className="font-mono text-xs uppercase tracking-widest mb-3" style={{ color: "var(--text-muted)" }}>
                  По категориям
                </h3>
                <div className="space-y-2">
                  {(results.category_progress as Array<{ category: string; correct: number; total: number }>).map((cat) => {
                    const pct = cat.total > 0 ? Math.round((cat.correct / cat.total) * 100) : 0;
                    return (
                      <div key={cat.category}>
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-xs" style={{ color: "var(--text-secondary)" }}>{cat.category}</span>
                          <span className="font-mono text-xs" style={{ color: pct >= 75 ? "#00FF66" : pct >= 50 ? "#F59E0B" : "#FF3333" }}>
                            {cat.correct}/{cat.total} ({pct}%)
                          </span>
                        </div>
                        <div className="h-1.5 rounded-full overflow-hidden" style={{ background: "rgba(255,255,255,0.06)" }}>
                          <div
                            className="h-full rounded-full transition-all"
                            style={{
                              width: `${pct}%`,
                              background: pct >= 75 ? "#00FF66" : pct >= 50 ? "#F59E0B" : "#FF3333",
                            }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Server summary */}
            {typeof results.summary === "string" && results.summary && (
              <div
                className="mt-4 rounded-xl p-3 text-xs leading-relaxed"
                style={{ background: "rgba(99,102,241,0.06)", border: "1px solid rgba(99,102,241,0.15)", color: "var(--text-secondary)" }}
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
                className="flex flex-1 items-center justify-center gap-2 rounded-xl border px-4 py-3 font-mono text-xs tracking-wider transition-all"
                style={{
                  borderColor: "rgba(255,255,255,0.08)",
                  background: "rgba(255,255,255,0.03)",
                  color: "var(--text-secondary)",
                }}
                whileTap={{ scale: 0.98 }}
              >
                <ArrowLeft size={14} />
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
      className="flex h-screen flex-col"
      style={{ background: "var(--bg-primary)" }}
    >
      {/* Top Bar */}
      <div
        className="shrink-0 border-b px-4 py-3"
        style={{
          borderColor: "rgba(255,255,255,0.06)",
          background: "rgba(3,3,6,0.95)",
          backdropFilter: "blur(20px)",
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
              className="flex h-9 w-9 items-center justify-center rounded-xl border transition-colors"
              style={{
                borderColor: "rgba(255,255,255,0.08)",
                color: "var(--text-secondary)",
              }}
              whileHover={{ background: "rgba(255,255,255,0.06)" }}
              whileTap={{ scale: 0.95 }}
            >
              <ArrowLeft size={16} />
            </motion.button>
            <div>
              <div
                className="font-mono text-xs uppercase tracking-[0.2em]"
                style={{ color: "var(--accent)" }}
              >
                {store.mode === "blitz"
                  ? "БЛИЦ"
                  : store.mode === "themed"
                    ? "ПО ТЕМЕ"
                    : store.mode === "pvp"
                      ? "PVP"
                      : "СВОБОДНЫЙ ДИАЛОГ"}
              </div>
              {store.category && (
                <div
                  className="text-xs"
                  style={{ color: "var(--text-muted)" }}
                >
                  {store.category}
                </div>
              )}
            </div>
          </div>

          {/* Center: Progress */}
          <div className="flex items-center gap-4">
            {store.totalQuestions > 0 && (
              <div className="flex items-center gap-2">
                <div
                  className="h-1.5 w-24 overflow-hidden rounded-full sm:w-32"
                  style={{ background: "rgba(255,255,255,0.06)" }}
                >
                  <motion.div
                    className="h-full rounded-full"
                    style={{ background: "var(--accent)" }}
                    animate={{ width: `${progressPct}%` }}
                    transition={{ duration: 0.3 }}
                  />
                </div>
                <span
                  className="font-mono text-xs"
                  style={{ color: "var(--text-muted)" }}
                >
                  {store.currentQuestion}/{store.totalQuestions}
                </span>
              </div>
            )}
          </div>

          {/* Right: Score + Timer */}
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <CheckCircle2 size={12} style={{ color: "#00FF66" }} />
              <span
                className="font-mono text-xs"
                style={{ color: "#00FF66" }}
              >
                {store.correct}
              </span>
              <XCircle size={12} style={{ color: "#FF3333" }} />
              <span
                className="font-mono text-xs"
                style={{ color: "#FF3333" }}
              >
                {store.incorrect}
              </span>
            </div>

            {store.timeLeft !== null && (
              <div
                className="flex items-center gap-1.5 rounded-lg border px-2.5 py-1"
                style={{
                  borderColor:
                    store.timeLeft <= 30
                      ? "rgba(255,51,51,0.4)"
                      : "rgba(245,158,11,0.3)",
                  background:
                    store.timeLeft <= 30
                      ? "rgba(255,51,51,0.08)"
                      : "rgba(245,158,11,0.08)",
                }}
              >
                <Clock
                  size={12}
                  style={{
                    color:
                      store.timeLeft <= 30 ? "#FF3333" : "#F59E0B",
                  }}
                />
                <span
                  className="font-mono text-sm font-bold"
                  style={{
                    color:
                      store.timeLeft <= 30 ? "#FF3333" : "#F59E0B",
                  }}
                >
                  {formatTime(store.timeLeft)}
                </span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Chat Messages */}
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl px-4 py-6 space-y-4">
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
                className="font-mono text-xs"
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

          {/* Typing indicator */}
          <AnimatePresence>
            {store.isTyping && (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                className="flex items-start gap-3"
              >
                <div
                  className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg"
                  style={{
                    background: "rgba(99,102,241,0.12)",
                    border: "1px solid rgba(99,102,241,0.25)",
                  }}
                >
                  <Brain size={14} style={{ color: "#6366F1" }} />
                </div>
                <div
                  className="rounded-2xl rounded-tl-sm px-4 py-3"
                  style={{
                    background: "rgba(255,255,255,0.04)",
                    border: "1px solid rgba(255,255,255,0.06)",
                  }}
                >
                  <div className="flex gap-1.5">
                    {[0, 1, 2].map((i) => (
                      <motion.div
                        key={i}
                        className="h-2 w-2 rounded-full"
                        style={{ background: "var(--text-muted)" }}
                        animate={{ opacity: [0.3, 1, 0.3] }}
                        transition={{
                          duration: 1,
                          repeat: Infinity,
                          delay: i * 0.2,
                        }}
                      />
                    ))}
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* V2: Follow-up action bar */}
      {store.pendingFollowUp && (
        <div
          className="shrink-0 border-t px-4 py-3"
          style={{
            borderColor: "rgba(99,102,241,0.15)",
            background: "rgba(99,102,241,0.04)",
          }}
        >
          <div className="mx-auto flex max-w-3xl items-center justify-between">
            <span className="text-xs" style={{ color: "var(--text-muted)" }}>
              Уточняющий вопрос — вы можете ответить или пропустить
            </span>
            <div className="flex gap-2">
              <button
                className="rounded-lg px-3 py-1.5 text-xs font-medium transition-colors"
                style={{ background: "rgba(99,102,241,0.15)", color: "#6366F1" }}
                onClick={() => {
                  store.setPendingFollowUp(null);
                  // Let user type answer normally - next text.message will be treated as follow-up answer
                }}
              >
                Ответить
              </button>
              <button
                className="rounded-lg px-3 py-1.5 text-xs font-medium transition-colors"
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

      {/* Input Bar */}
      <div
        className="shrink-0 border-t px-4 py-3"
        style={{
          borderColor: "rgba(255,255,255,0.06)",
          background: "rgba(3,3,6,0.95)",
          backdropFilter: "blur(20px)",
        }}
      >
        <div className="mx-auto flex max-w-3xl items-end gap-2">
          {/* Hint button */}
          <motion.button
            onClick={handleHint}
            disabled={hintLoading || store.status !== "active"}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border transition-colors disabled:opacity-30"
            style={{
              borderColor: "rgba(245,158,11,0.25)",
              background: "rgba(245,158,11,0.06)",
              color: "#F59E0B",
            }}
            whileHover={{ background: "rgba(245,158,11,0.12)" }}
            whileTap={{ scale: 0.95 }}
            title="Подсказка"
          >
            {hintLoading ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Lightbulb size={16} />
            )}
          </motion.button>

          {/* Skip button */}
          <motion.button
            onClick={handleSkip}
            disabled={store.status !== "active"}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border transition-colors disabled:opacity-30"
            style={{
              borderColor: "rgba(255,255,255,0.08)",
              background: "rgba(255,255,255,0.03)",
              color: "var(--text-muted)",
            }}
            whileHover={{ background: "rgba(255,255,255,0.06)" }}
            whileTap={{ scale: 0.95 }}
            title="Пропустить"
          >
            <SkipForward size={16} />
          </motion.button>

          {/* Text input */}
          <div
            className="flex flex-1 items-end rounded-xl border transition-colors"
            style={{
              borderColor: "rgba(255,255,255,0.08)",
              background: "var(--input-bg)",
            }}
          >
            <textarea
              ref={inputRef}
              value={store.input}
              onChange={(e) => store.setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Введите ответ..."
              rows={1}
              className="flex-1 resize-none bg-transparent px-4 py-2.5 text-sm outline-none placeholder:text-[var(--text-muted)]"
              style={{
                color: "var(--text-primary)",
                maxHeight: "120px",
              }}
              disabled={store.status !== "active"}
            />
          </div>

          {/* Send button */}
          <motion.button
            onClick={handleSend}
            disabled={!store.input.trim() || store.status !== "active"}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl transition-colors disabled:opacity-30"
            style={{
              background: "var(--accent)",
              color: "#fff",
            }}
            whileHover={{ opacity: 0.9 }}
            whileTap={{ scale: 0.95 }}
          >
            <Send size={16} />
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
          className="rounded-full px-4 py-1.5 font-mono text-xs uppercase tracking-wider"
          style={{
            background: "rgba(255,255,255,0.04)",
            color: "var(--text-muted)",
            border: "1px solid rgba(255,255,255,0.06)",
          }}
        >
          {message.content}
        </div>
      </motion.div>
    );
  }

  // Hint messages
  if (isHint) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-start gap-3"
      >
        <div
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg"
          style={{
            background: "rgba(245,158,11,0.12)",
            border: "1px solid rgba(245,158,11,0.25)",
          }}
        >
          <Lightbulb size={14} style={{ color: "#F59E0B" }} />
        </div>
        <div
          className="max-w-[90%] sm:max-w-[80%] rounded-2xl rounded-tl-sm px-4 py-3"
          style={{
            background: "rgba(245,158,11,0.06)",
            border: "1px solid rgba(245,158,11,0.15)",
          }}
        >
          <div
            className="font-mono text-xs uppercase tracking-widest mb-1"
            style={{ color: "#F59E0B" }}
          >
            Подсказка
          </div>
          <p className="text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
            {message.content}
          </p>
        </div>
      </motion.div>
    );
  }

  // Feedback messages
  if (isFeedback) {
    const correct = message.isCorrect;
    const color = correct ? "#00FF66" : "#FF3333";
    const bgColor = correct ? "rgba(0,255,102,0.06)" : "rgba(255,51,51,0.06)";
    const borderColor = correct
      ? "rgba(0,255,102,0.18)"
      : "rgba(255,51,51,0.18)";

    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-start gap-3"
      >
        <div
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg"
          style={{
            background: correct
              ? "rgba(0,255,102,0.12)"
              : "rgba(255,51,51,0.12)",
            border: `1px solid ${borderColor}`,
          }}
        >
          {correct ? (
            <CheckCircle2 size={14} style={{ color }} />
          ) : (
            <XCircle size={14} style={{ color }} />
          )}
        </div>
        <div
          className="max-w-[90%] sm:max-w-[80%] rounded-2xl rounded-tl-sm px-4 py-3"
          style={{ background: bgColor, border: `1px solid ${borderColor}` }}
        >
          <div
            className="font-mono text-xs uppercase tracking-widest mb-1"
            style={{ color }}
          >
            {correct ? "Верно!" : "Неверно"}
          </div>
          {message.explanation && (
            <p
              className="text-sm leading-relaxed"
              style={{ color: "var(--text-secondary)" }}
            >
              {message.explanation}
            </p>
          )}
          {message.articleRef && (
            <div
              className="mt-2 flex items-center gap-1.5 font-mono text-xs"
              style={{ color: "var(--text-muted)" }}
            >
              <BookOpen size={13} />
              <span>{message.articleRef}</span>
            </div>
          )}
          {/* V2: Speed bonus badge */}
          {message.speedBonus && message.speedBonus > 0 && (
            <div
              className="mt-2 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-mono font-bold"
              style={{ background: "rgba(34,197,94,0.15)", color: "#22C55E", border: "1px solid rgba(34,197,94,0.25)" }}
            >
              {"\u26A1"} +{message.speedBonus} SPEED BONUS
            </div>
          )}
        </div>
      </motion.div>
    );
  }

  // V2: Follow-up message
  if (isFollowUp) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-start gap-3"
      >
        <div
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-lg"
          style={{
            background: "rgba(99,102,241,0.12)",
            border: "1px solid rgba(99,102,241,0.25)",
          }}
        >
          {avatarEmoji || "\uD83D\uDCA1"}
        </div>
        <div
          className="max-w-[90%] sm:max-w-[80%] rounded-2xl rounded-tl-sm px-4 py-3"
          style={{
            background: "rgba(99,102,241,0.06)",
            border: "1px solid rgba(99,102,241,0.15)",
            borderLeft: "3px solid rgba(99,102,241,0.4)",
          }}
        >
          <div className="font-mono text-xs uppercase tracking-widest mb-1" style={{ color: "#6366F1" }}>
            Уточняющий вопрос (опционально)
          </div>
          <p className="text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
            {message.content}
          </p>
        </div>
      </motion.div>
    );
  }

  // Question from AI
  if (isQuestion) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-start gap-3"
      >
        <div
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-lg"
          style={{
            background: "rgba(99,102,241,0.12)",
            border: "1px solid rgba(99,102,241,0.25)",
          }}
        >
          {avatarEmoji || <BookOpen size={14} style={{ color: "#6366F1" }} />}
        </div>
        <div
          className="max-w-[90%] sm:max-w-[80%] rounded-2xl rounded-tl-sm px-4 py-3"
          style={{
            background: "rgba(255,255,255,0.04)",
            border: "1px solid rgba(255,255,255,0.08)",
          }}
        >
          {message.category && (
            <div
              className="font-mono text-xs uppercase tracking-widest mb-1.5"
              style={{ color: "var(--accent)" }}
            >
              {message.category}
            </div>
          )}
          <p
            className="text-sm leading-relaxed"
            style={{ color: "var(--text-primary)" }}
          >
            {message.content}
          </p>
        </div>
      </motion.div>
    );
  }

  // User answer
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex justify-end"
    >
      <div
        className="max-w-[90%] sm:max-w-[80%] rounded-2xl rounded-tr-sm px-4 py-3"
        style={{
          background: "rgba(99,102,241,0.15)",
          border: "1px solid rgba(99,102,241,0.25)",
        }}
      >
        <p
          className="text-sm leading-relaxed"
          style={{ color: "var(--text-primary)" }}
        >
          {message.content}
        </p>
      </div>
    </motion.div>
  );
}
