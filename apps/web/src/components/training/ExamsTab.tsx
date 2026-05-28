"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Award,
  Clock,
  CheckCircle,
  XCircle,
  Lock,
  ArrowRight,
  Trophy,
  Download,
  RefreshCw,
} from "lucide-react";
import { api } from "@/lib/api";
import { useGamificationStore } from "@/stores/useGamificationStore";

/* ── Types ────────────────────────────────────────────────────────── */

interface ExamLevel {
  level: number;
  name: string;
  status: "locked" | "available" | "in_progress" | "passed" | "failed";
  questionsCount?: number;
  passThreshold?: number;
  timeLimit?: number;
  failedAttempts?: number;
  certificateId?: string;
  serialNumber?: string;
}

interface ExamQuestion {
  question: string;
  options: string[];
  index: number;
}

interface ExamResult {
  passed: boolean;
  score: number;
  correct: number;
  total: number;
  threshold: number;
  results: {
    question_index: number;
    user_answer: number | null;
    correct_answer: number;
    is_correct: boolean;
    explanation: string;
  }[];
  certificate_id?: string;
  serial_number?: string;
}

const EXAM_LEVELS = [5, 10, 15, 20];

const LEVEL_NAMES: Record<number, string> = {
  5: "Ст. менеджер",
  10: "Грандмастер",
  15: "Профессионал",
  20: "Легенда",
};

/* ── Component ────────────────────────────────────────────────────── */

export default function ExamsTab() {
  const userLevel = useGamificationStore((s) => s.level);
  const [examLevels, setExamLevels] = useState<ExamLevel[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeExam, setActiveExam] = useState<{
    attemptId: string;
    questions: ExamQuestion[];
    timeLimit: number;
    level: number;
  } | null>(null);
  const [currentQ, setCurrentQ] = useState(0);
  const [answers, setAnswers] = useState<Record<number, number>>({});
  const [timeLeft, setTimeLeft] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<ExamResult | null>(null);
  const [starting, setStarting] = useState<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  /* ── Load exam statuses ────────────────────────────────────────── */

  const loadStatuses = useCallback(async () => {
    setLoading(true);
    try {
      const levels: ExamLevel[] = [];
      for (const lvl of EXAM_LEVELS) {
        if (userLevel >= lvl - 1) {
          try {
            const data = await api.get<any>(`/exams/status?level=${lvl}`);
            levels.push({
              level: lvl,
              name: LEVEL_NAMES[lvl] || `Уровень ${lvl}`,
              status: data.status,
              questionsCount: data.questions_count,
              passThreshold: data.pass_threshold,
              timeLimit: data.time_limit,
              failedAttempts: data.failed_attempts,
              certificateId: data.certificate_id,
              serialNumber: data.serial_number,
            });
          } catch {
            levels.push({
              level: lvl,
              name: LEVEL_NAMES[lvl] || `Уровень ${lvl}`,
              status: "available",
              questionsCount: 15,
              passThreshold: 80,
              timeLimit: 900,
            });
          }
        } else {
          levels.push({
            level: lvl,
            name: LEVEL_NAMES[lvl] || `Уровень ${lvl}`,
            status: "locked",
          });
        }
      }
      setExamLevels(levels);
    } finally {
      setLoading(false);
    }
  }, [userLevel]);

  useEffect(() => {
    loadStatuses();
  }, [loadStatuses]);

  /* ── Timer ─────────────────────────────────────────────────────── */

  useEffect(() => {
    if (activeExam && timeLeft > 0) {
      timerRef.current = setInterval(() => {
        setTimeLeft((t) => {
          if (t <= 1) {
            handleSubmit();
            return 0;
          }
          return t - 1;
        });
      }, 1000);
      return () => {
        if (timerRef.current) clearInterval(timerRef.current);
      };
    }
  }, [activeExam, timeLeft > 0]); // eslint-disable-line react-hooks/exhaustive-deps

  /* ── Start exam ────────────────────────────────────────────────── */

  const handleStart = async (level: number) => {
    setStarting(level);
    try {
      const data = await api.post<any>("/exams/start", { level });
      setActiveExam({
        attemptId: data.attempt_id,
        questions: data.questions,
        timeLimit: data.time_limit,
        level,
      });
      setTimeLeft(data.time_limit);
      setCurrentQ(0);
      setAnswers({});
      setResult(null);
    } catch (e: any) {
      console.error("Failed to start exam:", e);
    } finally {
      setStarting(null);
    }
  };

  /* ── Submit exam ───────────────────────────────────────────────── */

  const handleSubmit = async () => {
    if (!activeExam || submitting) return;
    setSubmitting(true);
    if (timerRef.current) clearInterval(timerRef.current);

    try {
      const answerList = Object.entries(answers).map(([qi, ai]) => ({
        question_index: parseInt(qi),
        answer: ai,
      }));

      const data = await api.post<ExamResult>("/exams/submit", {
        attempt_id: activeExam.attemptId,
        answers: answerList,
      });

      setResult(data);
      setActiveExam(null);
      loadStatuses();
    } catch (e: any) {
      console.error("Failed to submit exam:", e);
    } finally {
      setSubmitting(false);
    }
  };

  /* ── Download certificate ──────────────────────────────────────── */

  const handleDownload = async (certId: string) => {
    window.open(`/api/exams/certificate/${certId}`, "_blank");
  };

  /* ── Format time ───────────────────────────────────────────────── */

  const formatTime = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${m}:${sec.toString().padStart(2, "0")}`;
  };

  /* ── Render: Active exam ───────────────────────────────────────── */

  if (activeExam) {
    const q = activeExam.questions[currentQ];
    const progress = ((currentQ + 1) / activeExam.questions.length) * 100;
    const answeredCount = Object.keys(answers).length;
    const isUrgent = timeLeft < 60;

    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="space-y-4"
      >
        {/* Top bar */}
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Award size={16} style={{ color: "var(--accent)" }} />
            <span className="font-pixel text-xs uppercase" style={{ color: "var(--text-muted)" }}>
              Экзамен Level {activeExam.level}
            </span>
          </div>
          <div
            className="flex items-center gap-1.5 font-mono text-sm px-3 py-1 rounded-full"
            style={{
              background: isUrgent ? "rgba(239,68,68,0.15)" : "var(--input-bg)",
              color: isUrgent ? "var(--danger, #ef4444)" : "var(--text-primary)",
            }}
          >
            <Clock size={14} />
            {formatTime(timeLeft)}
          </div>
        </div>

        {/* Progress bar */}
        <div className="w-full h-1.5 rounded-full" style={{ background: "var(--input-bg)" }}>
          <motion.div
            className="h-full rounded-full"
            style={{ background: "var(--accent)", width: `${progress}%` }}
            transition={{ duration: 0.3 }}
          />
        </div>

        {/* Question */}
        <AnimatePresence mode="wait">
          <motion.div
            key={currentQ}
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            transition={{ duration: 0.2 }}
            className="rounded-xl p-5"
            style={{ background: "var(--card-bg)", border: "1px solid var(--input-bg)" }}
          >
            <div className="flex items-center gap-2 mb-3">
              <span className="text-xs font-mono px-2 py-0.5 rounded" style={{ background: "var(--input-bg)", color: "var(--text-muted)" }}>
                {currentQ + 1}/{activeExam.questions.length}
              </span>
            </div>

            <h3 className="text-sm font-medium mb-4" style={{ color: "var(--text-primary)" }}>
              {q.question}
            </h3>

            <div className="space-y-2">
              {q.options.map((opt, idx) => {
                const selected = answers[currentQ] === idx;
                return (
                  <motion.button
                    key={idx}
                    onClick={() => setAnswers((prev) => ({ ...prev, [currentQ]: idx }))}
                    className="w-full text-left px-4 py-3 rounded-lg text-sm transition-all"
                    style={{
                      background: selected ? "color-mix(in srgb, var(--accent) 15%, transparent)" : "var(--input-bg)",
                      border: `1.5px solid ${selected ? "var(--accent)" : "transparent"}`,
                      color: selected ? "var(--accent)" : "var(--text-secondary)",
                    }}
                    whileHover={{ scale: 1.01 }}
                    whileTap={{ scale: 0.99 }}
                  >
                    <span className="font-mono text-xs mr-2" style={{ opacity: 0.5 }}>
                      {String.fromCharCode(65 + idx)}.
                    </span>
                    {opt}
                  </motion.button>
                );
              })}
            </div>
          </motion.div>
        </AnimatePresence>

        {/* Navigation */}
        <div className="flex items-center justify-between gap-3">
          <button
            onClick={() => setCurrentQ((p) => Math.max(0, p - 1))}
            disabled={currentQ === 0}
            className="px-4 py-2 rounded-lg text-sm font-medium transition-all"
            style={{
              background: "var(--input-bg)",
              color: currentQ === 0 ? "var(--text-muted)" : "var(--text-primary)",
              opacity: currentQ === 0 ? 0.5 : 1,
            }}
          >
            Назад
          </button>

          <span className="text-xs" style={{ color: "var(--text-muted)" }}>
            Ответов: {answeredCount}/{activeExam.questions.length}
          </span>

          {currentQ < activeExam.questions.length - 1 ? (
            <button
              onClick={() => setCurrentQ((p) => Math.min(activeExam.questions.length - 1, p + 1))}
              className="px-4 py-2 rounded-lg text-sm font-medium transition-all"
              style={{ background: "var(--accent)", color: "white" }}
            >
              Далее
            </button>
          ) : (
            <motion.button
              onClick={handleSubmit}
              disabled={submitting}
              className="px-4 py-2 rounded-lg text-sm font-medium transition-all"
              style={{ background: "var(--success)", color: "white" }}
              whileTap={{ scale: 0.95 }}
            >
              {submitting ? "Проверка..." : "Завершить"}
            </motion.button>
          )}
        </div>

        {/* Question dots */}
        <div className="flex flex-wrap gap-1.5 justify-center">
          {activeExam.questions.map((_, i) => (
            <button
              key={i}
              onClick={() => setCurrentQ(i)}
              className="w-6 h-6 rounded-md text-[10px] font-mono flex items-center justify-center transition-all"
              style={{
                background: i === currentQ
                  ? "var(--accent)"
                  : answers[i] !== undefined
                  ? "color-mix(in srgb, var(--success) 25%, var(--input-bg))"
                  : "var(--input-bg)",
                color: i === currentQ ? "white" : "var(--text-muted)",
              }}
            >
              {i + 1}
            </button>
          ))}
        </div>
      </motion.div>
    );
  }

  /* ── Render: Results ───────────────────────────────────────────── */

  if (result) {
    return (
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="space-y-4"
      >
        <div
          className="rounded-xl p-6 text-center"
          style={{ background: "var(--card-bg)", border: "1px solid var(--input-bg)" }}
        >
          {result.passed ? (
            <>
              <Trophy size={48} style={{ color: "var(--success)", margin: "0 auto 12px" }} />
              <h3 className="text-lg font-bold mb-1" style={{ color: "var(--success)" }}>
                Экзамен сдан!
              </h3>
              <p className="text-sm mb-3" style={{ color: "var(--text-muted)" }}>
                {result.score}% — {result.correct} из {result.total} правильно
              </p>
              {result.serial_number && (
                <p className="font-mono text-xs mb-4" style={{ color: "var(--text-muted)" }}>
                  Сертификат: {result.serial_number}
                </p>
              )}
              {result.certificate_id && (
                <motion.button
                  onClick={() => handleDownload(result.certificate_id!)}
                  className="flex items-center gap-2 mx-auto px-4 py-2 rounded-lg text-sm font-medium"
                  style={{ background: "var(--accent)", color: "white" }}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                >
                  <Download size={14} />
                  Скачать сертификат
                </motion.button>
              )}
            </>
          ) : (
            <>
              <XCircle size={48} style={{ color: "var(--danger, #ef4444)", margin: "0 auto 12px" }} />
              <h3 className="text-lg font-bold mb-1" style={{ color: "var(--danger, #ef4444)" }}>
                Не сдан
              </h3>
              <p className="text-sm mb-1" style={{ color: "var(--text-muted)" }}>
                {result.score}% — нужно {result.threshold}%
              </p>
              <p className="text-xs mb-4" style={{ color: "var(--text-muted)" }}>
                {result.correct} из {result.total} правильно
              </p>
            </>
          )}
        </div>

        {/* Review */}
        <div className="space-y-2">
          <h4 className="text-xs font-pixel uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
            Разбор ответов
          </h4>
          {result.results.map((r, i) => (
            <div
              key={i}
              className="rounded-lg p-3 text-xs"
              style={{
                background: r.is_correct
                  ? "color-mix(in srgb, var(--success) 8%, var(--card-bg))"
                  : "color-mix(in srgb, var(--danger, #ef4444) 8%, var(--card-bg))",
                border: `1px solid ${r.is_correct ? "color-mix(in srgb, var(--success) 20%, transparent)" : "color-mix(in srgb, var(--danger, #ef4444) 20%, transparent)"}`,
              }}
            >
              <div className="flex items-start gap-2">
                {r.is_correct ? (
                  <CheckCircle size={14} style={{ color: "var(--success)", flexShrink: 0, marginTop: 1 }} />
                ) : (
                  <XCircle size={14} style={{ color: "var(--danger, #ef4444)", flexShrink: 0, marginTop: 1 }} />
                )}
                <div>
                  <span style={{ color: "var(--text-primary)" }}>Вопрос {i + 1}</span>
                  {r.explanation && (
                    <p className="mt-1" style={{ color: "var(--text-muted)" }}>{r.explanation}</p>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>

        <motion.button
          onClick={() => { setResult(null); loadStatuses(); }}
          className="w-full py-2.5 rounded-lg text-sm font-medium"
          style={{ background: "var(--input-bg)", color: "var(--text-primary)" }}
          whileTap={{ scale: 0.98 }}
        >
          Вернуться к экзаменам
        </motion.button>
      </motion.div>
    );
  }

  /* ── Render: Exam list ─────────────────────────────────────────── */

  if (loading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="h-24 rounded-xl animate-pulse" style={{ background: "var(--input-bg)" }} />
        ))}
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className="space-y-4"
    >
      <div className="flex items-center gap-2 mb-2">
        <Award size={18} style={{ color: "var(--accent)" }} />
        <span className="font-pixel text-xs uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
          Сдай экзамен — получи сертификат
        </span>
      </div>

      <div className="space-y-3">
        {examLevels.map((exam) => {
          const locked = exam.status === "locked";
          const passed = exam.status === "passed";

          return (
            <motion.div
              key={exam.level}
              className="rounded-xl p-4 transition-all"
              style={{
                background: locked ? "var(--input-bg)" : "var(--card-bg)",
                border: `1px solid ${passed ? "color-mix(in srgb, var(--success) 30%, transparent)" : "var(--input-bg)"}`,
                opacity: locked ? 0.5 : 1,
              }}
              whileHover={locked ? {} : { scale: 1.01 }}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div
                    className="w-10 h-10 rounded-lg flex items-center justify-center font-bold text-sm"
                    style={{
                      background: passed
                        ? "color-mix(in srgb, var(--success) 15%, transparent)"
                        : locked
                        ? "var(--input-bg)"
                        : "color-mix(in srgb, var(--accent) 15%, transparent)",
                      color: passed ? "var(--success)" : locked ? "var(--text-muted)" : "var(--accent)",
                    }}
                  >
                    {locked ? <Lock size={18} /> : passed ? <CheckCircle size={18} /> : <span>{exam.level}</span>}
                  </div>

                  <div>
                    <h4 className="text-sm font-medium" style={{ color: locked ? "var(--text-muted)" : "var(--text-primary)" }}>
                      {locked ? `Уровень ${exam.level}` : `Экзамен: ${exam.name}`}
                    </h4>
                    <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                      {locked && "Разблокируется при достижении уровня"}
                      {exam.status === "available" && `${exam.questionsCount} вопросов · ${exam.passThreshold}% для сдачи · ${Math.round((exam.timeLimit || 900) / 60)} мин`}
                      {exam.status === "in_progress" && "Экзамен в процессе — продолжить"}
                      {passed && `Сдан! Сертификат: ${exam.serialNumber || "—"}`}
                      {exam.status === "failed" && `Попыток: ${exam.failedAttempts || 0} · ${exam.questionsCount} вопросов`}
                    </p>
                  </div>
                </div>

                <div>
                  {!locked && !passed && (
                    <motion.button
                      onClick={() => handleStart(exam.level)}
                      disabled={starting === exam.level}
                      className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium transition-all"
                      style={{
                        background: exam.status === "failed" ? "var(--warning)" : "var(--accent)",
                        color: "white",
                      }}
                      whileHover={{ scale: 1.05 }}
                      whileTap={{ scale: 0.95 }}
                    >
                      {starting === exam.level ? (
                        <RefreshCw size={12} className="animate-spin" />
                      ) : exam.status === "failed" ? (
                        <><RefreshCw size={12} /> Пересдать</>
                      ) : exam.status === "in_progress" ? (
                        <><ArrowRight size={12} /> Продолжить</>
                      ) : (
                        <><ArrowRight size={12} /> Начать</>
                      )}
                    </motion.button>
                  )}
                  {passed && exam.certificateId && (
                    <motion.button
                      onClick={() => handleDownload(exam.certificateId!)}
                      className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium"
                      style={{ background: "var(--input-bg)", color: "var(--success)" }}
                      whileHover={{ scale: 1.05 }}
                      whileTap={{ scale: 0.95 }}
                    >
                      <Download size={12} /> PDF
                    </motion.button>
                  )}
                </div>
              </div>
            </motion.div>
          );
        })}
      </div>

      <div
        className="flex items-center gap-2 text-xs px-3 py-2 rounded-lg"
        style={{ background: "var(--input-bg)", color: "var(--text-muted)" }}
      >
        <Award size={14} style={{ color: "var(--warning)" }} />
        Экзамены открываются на уровнях 5, 10, 15 и 20. После сдачи — сертификат!
      </div>
    </motion.div>
  );
}
