"use client";

/**
 * CoachingCard — post-round coaching overlay for roleplay modes (Duel,
 * Rapid-Fire, Gauntlet, Team 2v2).
 *
 * Phase A (2026-04-20). Unlike the quiz-mode CorrectAnswerReveal (which is
 * binary ✓/✖ with a canonical right answer), sales-roleplay has degrees of
 * quality. This card shows:
 *   • a short one-line coaching tip
 *   • the "ideal reply" the AI judge thought the seller should have said
 *   • 127-ФЗ articles worth citing next time
 *   • legal claim accuracy chips (correct / partial / incorrect)
 *
 * Backend source: `services/pvp_judge.py` JudgeRoundScore → emitted in
 * `judge.score` (Duel), `rapid.round_result` (score.coaching), and
 * `gauntlet.duel_result` (coaching field).
 */

import { motion, AnimatePresence } from "framer-motion";
import { Lightbulb, Quote, BookOpen, X, AlertTriangle, CheckCircle2, MinusCircle } from "lucide-react";

export interface CoachingPayload {
  tip: string;
  idealReply: string;
  keyArticles: string[];
  /** Optional: flags from judge (e.g. "Не задал квалифицирующий вопрос о сумме долга"). */
  flags?: string[];
  /** Optional: per-claim accuracy from RAG validation. */
  legalDetails?: Array<{
    claim?: string;
    accuracy?: "correct" | "correct_cited" | "partial" | "incorrect" | string;
    explanation?: string;
  }>;
  /** Optional: player's score for this round (0-100 normalised). */
  scoreNormalised?: number;
}

interface Props {
  open: boolean;
  accentColor: string;
  payload: CoachingPayload | null;
  onDismiss: () => void;
}

const accuracyIcon = (acc?: string) => {
  if (acc === "correct" || acc === "correct_cited") return CheckCircle2;
  if (acc === "partial") return MinusCircle;
  return AlertTriangle;
};

const accuracyColor = (acc?: string) => {
  if (acc === "correct" || acc === "correct_cited") return "#4ade80";
  if (acc === "partial") return "#facc15";
  return "#f87171";
};

const accuracyLabel = (acc?: string) => {
  if (acc === "correct_cited") return "Верно + цитата";
  if (acc === "correct") return "Верно";
  if (acc === "partial") return "Частично";
  if (acc === "incorrect") return "Ошибка";
  return acc ?? "";
};

export function CoachingCard({ open, accentColor, payload, onDismiss }: Props) {
  return (
    <AnimatePresence>
      {open && payload && (
        <motion.div
          className="fixed inset-0 z-[60] flex items-end sm:items-center justify-center px-4 pb-4 sm:pb-0"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
          style={{ background: "rgba(6, 2, 15, 0.72)", backdropFilter: "blur(6px)" }}
          onClick={onDismiss}
        >
          <motion.div
            className="relative w-full max-w-2xl rounded-2xl overflow-hidden"
            onClick={(e) => e.stopPropagation()}
            initial={{ y: 40, opacity: 0, scale: 0.96 }}
            animate={{ y: 0, opacity: 1, scale: 1 }}
            exit={{ y: 20, opacity: 0, scale: 0.98 }}
            transition={{ type: "spring", stiffness: 300, damping: 26 }}
            style={{
              background: "linear-gradient(180deg, rgba(24,16,40,0.98), rgba(14,9,26,0.98))",
              border: `1px solid ${accentColor}44`,
              boxShadow: `0 30px 80px -20px ${accentColor}55, 0 0 0 1px ${accentColor}22 inset`,
            }}
          >
            {/* Header */}
            <div
              className="flex items-center gap-3 px-5 py-4"
              style={{
                background: `linear-gradient(90deg, ${accentColor}26, transparent)`,
                borderBottom: `1px solid ${accentColor}22`,
              }}
            >
              <div
                className="flex items-center justify-center w-10 h-10 rounded-xl"
                style={{ background: `${accentColor}22`, color: accentColor }}
              >
                <Lightbulb size={20} />
              </div>
              <div className="flex-1">
                <div
                  className="text-[10px] font-semibold uppercase tracking-wider"
                  style={{ color: accentColor }}
                >
                  Разбор раунда
                </div>
                <div
                  className="text-[15px] font-semibold"
                  style={{ color: "#f4f1ff" }}
                >
                  Что стоило сказать
                </div>
              </div>
              {typeof payload.scoreNormalised === "number" && (
                <div
                  className="flex flex-col items-end leading-tight"
                  style={{ color: accentColor }}
                >
                  <span className="font-mono tabular-nums text-2xl font-bold">
                    {Math.round(payload.scoreNormalised)}
                  </span>
                  <span className="text-[10px] uppercase tracking-widest opacity-70">
                    /100
                  </span>
                </div>
              )}
              <button
                onClick={onDismiss}
                className="rounded-lg p-1.5 transition-colors hover:bg-white/10"
                aria-label="Закрыть разбор"
                style={{ color: "#c9bfee" }}
              >
                <X size={16} />
              </button>
            </div>

            <div className="p-5 space-y-4">
              {/* Tip */}
              {payload.tip && (
                <div className="flex items-start gap-3">
                  <div
                    className="shrink-0 w-1 self-stretch rounded-full"
                    style={{ background: accentColor }}
                  />
                  <p
                    className="text-[14px] leading-relaxed"
                    style={{ color: "#e5dfff" }}
                  >
                    {payload.tip}
                  </p>
                </div>
              )}

              {/* Ideal reply */}
              {payload.idealReply && (
                <div
                  className="rounded-xl p-4"
                  style={{
                    background: "rgba(34, 197, 94, 0.08)",
                    border: "1px solid rgba(34, 197, 94, 0.25)",
                  }}
                >
                  <div className="flex items-center gap-2 mb-2">
                    <Quote size={14} style={{ color: "#4ade80" }} />
                    <span
                      className="text-[10px] font-semibold uppercase tracking-wider"
                      style={{ color: "#4ade80" }}
                    >
                      Идеальная реплика
                    </span>
                  </div>
                  <p
                    className="text-[14px] leading-relaxed italic"
                    style={{ color: "#dcfce7" }}
                  >
                    «{payload.idealReply}»
                  </p>
                </div>
              )}

              {/* Articles */}
              {payload.keyArticles && payload.keyArticles.length > 0 && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <BookOpen size={14} style={{ color: accentColor }} />
                    <span
                      className="text-[10px] font-semibold uppercase tracking-wider"
                      style={{ color: accentColor }}
                    >
                      Опоры 127-ФЗ
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {payload.keyArticles.map((a, i) => (
                      <span
                        key={`${a}-${i}`}
                        className="inline-flex items-center rounded-md px-2 py-1 text-[12px] font-mono"
                        style={{
                          background: `${accentColor}18`,
                          color: accentColor,
                          border: `1px solid ${accentColor}33`,
                        }}
                      >
                        {a}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Legal details — per-claim verdict */}
              {payload.legalDetails && payload.legalDetails.length > 0 && (
                <div>
                  <div
                    className="text-[10px] font-semibold uppercase tracking-wider mb-2"
                    style={{ color: "#c9bfee" }}
                  >
                    Правовые утверждения
                  </div>
                  <ul className="space-y-1.5">
                    {payload.legalDetails.slice(0, 4).map((d, i) => {
                      const Icon = accuracyIcon(d.accuracy);
                      const color = accuracyColor(d.accuracy);
                      return (
                        <li
                          key={i}
                          className="flex items-start gap-2 text-[13px] leading-snug"
                          style={{ color: "#e5dfff" }}
                        >
                          <Icon size={14} style={{ color, marginTop: 2 }} />
                          <div className="flex-1 min-w-0">
                            <div className="line-clamp-2">
                              {d.claim || d.explanation || "—"}
                            </div>
                            <div
                              className="text-[10px] uppercase tracking-wider mt-0.5"
                              style={{ color, opacity: 0.9 }}
                            >
                              {accuracyLabel(d.accuracy)}
                            </div>
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}

              {/* Flags */}
              {payload.flags && payload.flags.length > 0 && (
                <details className="group">
                  <summary
                    className="cursor-pointer text-[11px] uppercase tracking-widest select-none"
                    style={{ color: "#c9bfee" }}
                  >
                    Ещё замечаний: {payload.flags.length}
                  </summary>
                  <ul
                    className="mt-2 pl-4 space-y-1 text-[12px] leading-snug list-disc"
                    style={{ color: "#b9aee6" }}
                  >
                    {payload.flags.map((f, i) => (
                      <li key={i}>{f}</li>
                    ))}
                  </ul>
                </details>
              )}
            </div>

            {/* Footer CTA */}
            <div
              className="flex justify-end gap-2 px-5 py-3"
              style={{
                background: "rgba(0,0,0,0.3)",
                borderTop: `1px solid ${accentColor}22`,
              }}
            >
              <button
                onClick={onDismiss}
                className="rounded-lg px-4 py-2 text-[13px] font-semibold transition-all"
                style={{
                  background: accentColor,
                  color: "#0b0b14",
                  boxShadow: `0 0 20px -4px ${accentColor}`,
                }}
              >
                Дальше
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
