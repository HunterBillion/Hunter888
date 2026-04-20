"use client";

/**
 * CorrectAnswerReveal — post-answer overlay that teaches.
 *
 * Sprint 1 (2026-04-20). User feedback: "после неверного не вижу
 * правильного ответа". Previously Arena just flashed ✖ НЕВЕРНО and
 * "Не удалось получить разбор" — no learning moment.
 *
 * This component shows:
 *   - verdict chip (✓ верно / ✖ неверно)
 *   - score delta (+8 XP / -2 XP)
 *   - the actual correct answer (green highlight)
 *   - the governing article (linked when we know it)
 *   - short RAG-grounded explanation
 *   - two CTAs: "Понял" (dismiss) + "Показать полный текст" (opens article)
 *
 * Styled to match the arena theme (accent color passed in). Escape key
 * and background click both dismiss.
 */

import { useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Check, X, BookOpen, Sparkles, ArrowRight } from "lucide-react";

export interface CorrectAnswerPayload {
  isCorrect: boolean;
  scoreDelta: number;
  /** Canonical right answer summary (e.g. "500 000 рублей"). */
  correctAnswer?: string | null;
  /** Law citation (e.g. "ст. 213.3 127-ФЗ"). */
  articleReference?: string | null;
  /** 1-3 sentence plain-language grounding from RAG. */
  explanation?: string | null;
  /** Optional URL to the article source (legalacts.ru etc.). */
  sourceUrl?: string | null;
  /** User's original input — shown grey-struck on wrong. */
  userAnswer?: string | null;
}

interface Props {
  open: boolean;
  payload: CorrectAnswerPayload | null;
  /** Theme accent — arena theme color, passed from ArenaShell. */
  accentColor?: string;
  onDismiss: () => void;
  onShowSource?: () => void;
}

export function CorrectAnswerReveal({
  open,
  payload,
  accentColor = "#a78bfa",
  onDismiss,
  onShowSource,
}: Props) {
  const cardRef = useRef<HTMLDivElement>(null);

  // Esc to dismiss
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onDismiss();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onDismiss]);

  if (!payload) return null;

  const good = payload.isCorrect;
  const verdictColor = good ? "#22c55e" : "#ef4444";
  const deltaPrefix = payload.scoreDelta >= 0 ? "+" : "";

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[200] flex items-center justify-center px-4 py-6"
          style={{ background: "rgba(0,0,0,0.72)", backdropFilter: "blur(6px)" }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={(e) => {
            if (e.target === e.currentTarget) onDismiss();
          }}
        >
          <motion.div
            ref={cardRef}
            className="w-full max-w-lg rounded-2xl overflow-hidden"
            style={{
              background: "var(--bg-secondary)",
              border: `2px solid ${verdictColor}`,
              boxShadow: `0 0 48px ${verdictColor}55, 0 20px 60px rgba(0,0,0,0.6)`,
            }}
            initial={{ scale: 0.9, y: 24 }}
            animate={{ scale: 1, y: 0 }}
            exit={{ scale: 0.95, y: 12 }}
            transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
          >
            {/* Verdict header */}
            <div
              className="flex items-center justify-between px-6 py-4"
              style={{
                background: `linear-gradient(135deg, ${verdictColor}22, ${verdictColor}08)`,
                borderBottom: `1px solid ${verdictColor}33`,
              }}
            >
              <div className="flex items-center gap-3">
                <motion.div
                  className="flex h-10 w-10 items-center justify-center rounded-full"
                  style={{ background: verdictColor, color: "#0b0b14" }}
                  initial={{ scale: 0, rotate: -180 }}
                  animate={{ scale: 1, rotate: 0 }}
                  transition={{ delay: 0.08, type: "spring", stiffness: 200 }}
                >
                  {good ? <Check size={22} strokeWidth={3} /> : <X size={22} strokeWidth={3} />}
                </motion.div>
                <div>
                  <div
                    className="text-xl font-display font-bold tracking-wide"
                    style={{ color: verdictColor }}
                  >
                    {good ? "ВЕРНО" : "НЕВЕРНО"}
                  </div>
                  <div
                    className="text-[11px] uppercase tracking-wider"
                    style={{ color: "var(--text-muted)" }}
                  >
                    {good ? "Отличная работа" : "Давай разберём"}
                  </div>
                </div>
              </div>

              {/* Score delta — animated count-in */}
              <motion.div
                className="font-mono text-2xl font-bold"
                style={{ color: verdictColor }}
                initial={{ opacity: 0, x: 12 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.2 }}
              >
                {deltaPrefix}
                {payload.scoreDelta.toFixed(1)}
                <span
                  className="text-[11px] ml-1 font-semibold uppercase"
                  style={{ color: "var(--text-muted)" }}
                >
                  XP
                </span>
              </motion.div>
            </div>

            {/* Body */}
            <div className="p-6 space-y-4">
              {/* Your answer (only shown when wrong) */}
              {!good && payload.userAnswer && (
                <div>
                  <div
                    className="text-[10px] font-semibold uppercase tracking-wider mb-1"
                    style={{ color: "var(--text-muted)" }}
                  >
                    Твой ответ
                  </div>
                  <div
                    className="text-sm px-3 py-2 rounded-lg line-through"
                    style={{
                      background: "var(--input-bg)",
                      color: "var(--text-muted)",
                      border: "1px solid var(--border-color)",
                    }}
                  >
                    {payload.userAnswer}
                  </div>
                </div>
              )}

              {/* Correct answer block — always highlighted green */}
              {payload.correctAnswer && (
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.25 }}
                >
                  <div className="flex items-center gap-1.5 mb-1">
                    <Sparkles size={13} style={{ color: "#22c55e" }} />
                    <span
                      className="text-[10px] font-semibold uppercase tracking-wider"
                      style={{ color: "#22c55e" }}
                    >
                      Правильный ответ
                    </span>
                  </div>
                  <div
                    className="text-base font-medium px-3 py-2.5 rounded-lg"
                    style={{
                      background: "rgba(34,197,94,0.12)",
                      border: "1px solid rgba(34,197,94,0.32)",
                      color: "var(--text-primary)",
                    }}
                  >
                    {payload.correctAnswer}
                  </div>
                </motion.div>
              )}

              {/* Article reference */}
              {payload.articleReference && (
                <motion.div
                  className="flex items-center gap-2 text-sm"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.35 }}
                >
                  <BookOpen size={14} style={{ color: accentColor }} />
                  <span
                    className="text-[10px] font-semibold uppercase tracking-wider"
                    style={{ color: "var(--text-muted)" }}
                  >
                    Статья:
                  </span>
                  <span style={{ color: accentColor, fontWeight: 600 }}>
                    {payload.articleReference}
                  </span>
                </motion.div>
              )}

              {/* Explanation */}
              {payload.explanation && (
                <motion.div
                  className="text-sm leading-relaxed"
                  style={{ color: "var(--text-secondary)" }}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.4 }}
                >
                  {payload.explanation}
                </motion.div>
              )}
            </div>

            {/* Footer CTAs */}
            <div
              className="flex items-center gap-2 px-6 py-3"
              style={{ borderTop: "1px solid var(--border-color)", background: "var(--bg-primary)" }}
            >
              {onShowSource && payload.sourceUrl && (
                <button
                  type="button"
                  onClick={onShowSource}
                  className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg transition-colors"
                  style={{
                    color: "var(--text-secondary)",
                    background: "var(--input-bg)",
                    border: "1px solid var(--border-color)",
                  }}
                >
                  <BookOpen size={12} /> Полный текст
                </button>
              )}
              <div className="flex-1" />
              <button
                type="button"
                onClick={onDismiss}
                className="flex items-center gap-1.5 text-sm font-semibold px-4 py-2 rounded-lg transition-all active:scale-95"
                style={{
                  background: accentColor,
                  color: "#0b0b14",
                  boxShadow: `0 4px 14px ${accentColor}55`,
                }}
              >
                {good ? "Дальше" : "Понял, дальше"}
                <ArrowRight size={14} />
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
