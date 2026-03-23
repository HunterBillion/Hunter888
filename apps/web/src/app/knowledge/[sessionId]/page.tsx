"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import { useKnowledgeStore, type QuizMessage } from "@/stores/useKnowledgeStore";
import { logger } from "@/lib/logger";

/* ─── Quiz Session Page ──────────────────────────────────────────────────── */

export default function KnowledgeSessionPage() {
  const params = useParams();
  const router = useRouter();
  const sessionId = params.sessionId as string;

  const store = useKnowledgeStore();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [showResults, setShowResults] = useState(false);
  const [hintLoading, setHintLoading] = useState(false);

  // Initialize session if needed
  useEffect(() => {
    if (!store.sessionId || store.sessionId !== sessionId) {
      store.setSessionId(sessionId);
      store.setStatus("connecting");
    }
  }, [sessionId]); // eslint-disable-line react-hooks/exhaustive-deps

  // WebSocket message handler
  const handleMessage = useCallback(
    (data: Record<string, unknown>) => {
      const type = data.type as string;

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

        case "question": {
          store.addMessage({
            type: "question",
            content: data.content as string,
            category: data.category as string | undefined,
          });
          store.setIsTyping(false);
          break;
        }

        case "feedback": {
          store.addMessage({
            type: "feedback",
            content: data.explanation as string || "",
            isCorrect: data.is_correct as boolean,
            explanation: data.explanation as string | undefined,
            articleRef: data.article_ref as string | undefined,
          });
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

        case "hint": {
          store.addMessage({
            type: "hint",
            content: data.content as string,
          });
          setHintLoading(false);
          break;
        }

        case "system": {
          store.addMessage({
            type: "system",
            content: data.content as string,
          });
          break;
        }

        case "typing": {
          store.setIsTyping(true);
          break;
        }

        case "timer_sync": {
          store.setTimeLeft(data.time_left as number);
          break;
        }

        case "session_completed": {
          store.setResults(data.results as Record<string, unknown>);
          store.setStatus("completed");
          setShowResults(true);
          if (timerRef.current) {
            clearInterval(timerRef.current);
            timerRef.current = null;
          }
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
    [sessionId], // eslint-disable-line react-hooks/exhaustive-deps
  );

  // WebSocket connection
  const { sendMessage, isConnected, connectionState } = useWebSocket({
    path: `/ws/knowledge/${sessionId}`,
    onMessage: handleMessage,
    autoConnect: true,
  });

  // Set active status once connected
  useEffect(() => {
    if (isConnected && store.status === "connecting") {
      store.setStatus("active");
    }
  }, [isConnected]); // eslint-disable-line react-hooks/exhaustive-deps

  // Timer for blitz mode
  useEffect(() => {
    if (store.mode === "blitz" && store.timeLeft !== null && store.status === "active") {
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
  }, [store.mode, store.status, store.timeLeft !== null]); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [store.messages.length, store.isTyping]);

  // Send answer
  const handleSend = useCallback(() => {
    const text = store.input.trim();
    if (!text || store.status !== "active") return;

    store.addMessage({ type: "answer", content: text });
    sendMessage({ type: "answer", content: text });
    store.setInput("");
    store.setIsTyping(true);

    // Focus back on input
    setTimeout(() => inputRef.current?.focus(), 50);
  }, [store.input, store.status, sendMessage]); // eslint-disable-line react-hooks/exhaustive-deps

  // Skip question
  const handleSkip = useCallback(() => {
    sendMessage({ type: "skip" });
    store.addMessage({ type: "system", content: "Вопрос пропущен" });
  }, [sendMessage]); // eslint-disable-line react-hooks/exhaustive-deps

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
                  "linear-gradient(90deg, transparent, #8B5CF6, transparent)",
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
                  className="mt-1 font-mono text-[10px] uppercase tracking-widest"
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
                  className="mt-1 font-mono text-[10px] uppercase tracking-widest"
                  style={{ color: "var(--text-muted)" }}
                >
                  Неверно
                </div>
              </div>
              <div
                className="rounded-xl p-4 text-center"
                style={{
                  background: "rgba(139,92,246,0.06)",
                  border: "1px solid rgba(139,92,246,0.15)",
                }}
              >
                <div
                  className="font-display text-3xl font-bold"
                  style={{ color: "#8B5CF6" }}
                >
                  {accuracy}%
                </div>
                <div
                  className="mt-1 font-mono text-[10px] uppercase tracking-widest"
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
                  className="mt-1 font-mono text-[10px] uppercase tracking-widest"
                  style={{ color: "var(--text-muted)" }}
                >
                  Очки
                </div>
              </div>
            </div>

            {store.skipped > 0 && (
              <div
                className="mt-3 text-center font-mono text-xs"
                style={{ color: "var(--text-muted)" }}
              >
                Пропущено: {store.skipped}
              </div>
            )}

            <div className="mt-8 flex gap-3">
              <motion.button
                onClick={() => {
                  store.reset();
                  router.push("/knowledge");
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
                  router.push("/knowledge");
                }}
                className="vh-btn-primary flex flex-1 items-center justify-center gap-2"
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
                router.push("/knowledge");
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
                className="font-mono text-[10px] uppercase tracking-[0.2em]"
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
                  className="font-mono text-[10px]"
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
                    background: "rgba(139,92,246,0.12)",
                    border: "1px solid rgba(139,92,246,0.25)",
                  }}
                >
                  <Brain size={14} style={{ color: "#8B5CF6" }} />
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

  // System messages
  if (isSystem) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex justify-center"
      >
        <div
          className="rounded-full px-4 py-1.5 font-mono text-[10px] uppercase tracking-wider"
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
          className="max-w-[80%] rounded-2xl rounded-tl-sm px-4 py-3"
          style={{
            background: "rgba(245,158,11,0.06)",
            border: "1px solid rgba(245,158,11,0.15)",
          }}
        >
          <div
            className="font-mono text-[9px] uppercase tracking-widest mb-1"
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
          className="max-w-[80%] rounded-2xl rounded-tl-sm px-4 py-3"
          style={{ background: bgColor, border: `1px solid ${borderColor}` }}
        >
          <div
            className="font-mono text-[9px] uppercase tracking-widest mb-1"
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
              className="mt-2 flex items-center gap-1.5 font-mono text-[10px]"
              style={{ color: "var(--text-muted)" }}
            >
              <BookOpen size={10} />
              <span>{message.articleRef}</span>
            </div>
          )}
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
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg"
          style={{
            background: "rgba(139,92,246,0.12)",
            border: "1px solid rgba(139,92,246,0.25)",
          }}
        >
          <BookOpen size={14} style={{ color: "#8B5CF6" }} />
        </div>
        <div
          className="max-w-[80%] rounded-2xl rounded-tl-sm px-4 py-3"
          style={{
            background: "rgba(255,255,255,0.04)",
            border: "1px solid rgba(255,255,255,0.08)",
          }}
        >
          {message.category && (
            <div
              className="font-mono text-[9px] uppercase tracking-widest mb-1.5"
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
        className="max-w-[80%] rounded-2xl rounded-tr-sm px-4 py-3"
        style={{
          background: "rgba(139,92,246,0.15)",
          border: "1px solid rgba(139,92,246,0.25)",
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
