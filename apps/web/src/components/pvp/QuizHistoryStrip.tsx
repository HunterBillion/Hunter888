"use client";

/**
 * QuizHistoryStrip — Phase 2 (PR-22).
 *
 * Компактная полоска ✓/✗ за все Q1..QN в текущей сессии. Помещается над
 * чатом или в сайдбаре. Hover на dot → tooltip с превью вопроса/ответа.
 *
 * Sources:
 *   - feedback messages (с verdictLevel) — основа цветовой палитры
 *   - question messages — для tooltip-preview
 */

import { useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { QuizMessage } from "@/stores/useKnowledgeStore";

type Level = "correct" | "partial" | "off_topic" | "wrong" | "pending";

const LEVEL_COLOR: Record<Level, string> = {
  correct: "var(--success, #22c55e)",
  partial: "var(--warning, #f59e0b)",
  off_topic: "#60a5fa",
  wrong: "var(--danger, #ef4444)",
  pending: "var(--text-muted)",
};

interface Cell {
  index: number;
  level: Level;
  questionPreview: string;
  answerPreview: string;
}

interface QuizHistoryStripProps {
  messages: QuizMessage[];
  totalQuestions: number;
  /** Когда сидит в right-sidebar — показываем компакт-вариант. */
  variant?: "compact" | "wide";
}

export function QuizHistoryStrip({ messages, totalQuestions, variant = "compact" }: QuizHistoryStripProps) {
  const [hovered, setHovered] = useState<number | null>(null);

  const cells = useMemo<Cell[]>(() => {
    // Pair feedbacks with their preceding question/answer.
    // Strategy: walk messages in order, track current Q/answer, append a
    // cell whenever a feedback arrives.
    const result: Cell[] = [];
    let lastQuestion = "";
    let lastAnswer = "";
    for (const m of messages) {
      if (m.type === "question") lastQuestion = m.content ?? "";
      else if (m.type === "answer") lastAnswer = m.content ?? "";
      else if (m.type === "feedback") {
        const level: Level =
          (m.verdictLevel as Level | undefined) ??
          (m.isCorrect ? "correct" : "wrong");
        result.push({
          index: result.length,
          level,
          questionPreview: lastQuestion.slice(0, 80),
          answerPreview: lastAnswer.slice(0, 80),
        });
      }
    }
    return result;
  }, [messages]);

  const slots = totalQuestions > 0 ? Math.max(totalQuestions, cells.length) : cells.length;
  if (slots === 0) return null;

  const dotSize = variant === "wide" ? 20 : 16;
  const gap = variant === "wide" ? 8 : 6;

  return (
    <div
      className="relative rounded-2xl px-3 py-2.5"
      style={{
        background: "linear-gradient(135deg, rgba(255,255,255,0.04) 0%, rgba(255,255,255,0.02) 100%)",
        border: "1px solid rgba(255,255,255,0.08)",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        boxShadow: "inset 0 1px 0 rgba(255,255,255,0.05)",
      }}
    >
      <div
        className="font-display font-bold uppercase tracking-widest mb-3 flex items-center justify-between"
        style={{ color: "var(--text-secondary)", fontSize: 13, letterSpacing: "0.16em" }}
      >
        <span>История</span>
        <span className="font-mono tabular-nums" style={{ color: "var(--text-primary)", fontSize: 14 }}>
          {cells.length}/{slots}
        </span>
      </div>
      <div
        className="flex flex-wrap items-center"
        style={{ gap }}
        onMouseLeave={() => setHovered(null)}
      >
        {Array.from({ length: slots }).map((_, i) => {
          const cell = cells[i];
          const level: Level = cell?.level ?? "pending";
          const color = LEVEL_COLOR[level];
          const isHover = hovered === i;
          return (
            <div key={i} className="relative">
              <motion.button
                type="button"
                onMouseEnter={() => cell && setHovered(i)}
                onFocus={() => cell && setHovered(i)}
                whileHover={cell ? { scale: 1.18 } : undefined}
                className="rounded-md"
                style={{
                  width: dotSize,
                  height: dotSize,
                  background: cell
                    ? `linear-gradient(135deg, ${color} 0%, color-mix(in srgb, ${color} 70%, black) 100%)`
                    : "rgba(255,255,255,0.06)",
                  border: cell
                    ? `1px solid color-mix(in srgb, ${color} 60%, white)`
                    : "1px solid rgba(255,255,255,0.1)",
                  boxShadow: cell
                    ? `0 0 ${isHover ? 10 : 4}px ${color}88, inset 0 1px 0 rgba(255,255,255,0.18)`
                    : "none",
                  cursor: cell ? "pointer" : "default",
                  transition: "box-shadow 220ms",
                }}
                aria-label={cell ? `Q${i + 1}: ${level}` : `Q${i + 1}: ещё не отвечен`}
              />
              <AnimatePresence>
                {isHover && cell && (
                  <motion.div
                    initial={{ opacity: 0, y: 4, scale: 0.92 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: 4, scale: 0.92 }}
                    transition={{ duration: 0.14 }}
                    className="absolute z-30 left-1/2 -translate-x-1/2 top-full mt-2 rounded-xl px-3 py-2 pointer-events-none"
                    style={{
                      width: 240,
                      background: "linear-gradient(135deg, rgba(15,15,20,0.96) 0%, rgba(15,15,20,0.88) 100%)",
                      border: `1px solid ${color}55`,
                      boxShadow: `0 12px 32px rgba(0,0,0,0.4), 0 0 0 1px ${color}30`,
                      backdropFilter: "blur(24px)",
                    }}
                  >
                    <div
                      className="font-display font-bold uppercase tracking-widest mb-1"
                      style={{ color, fontSize: 10, letterSpacing: "0.16em" }}
                    >
                      Q{i + 1} · {level === "correct" ? "Верно" : level === "partial" ? "Почти" : level === "off_topic" ? "Не по теме" : "Неверно"}
                    </div>
                    <div
                      className="mb-1"
                      style={{ color: "var(--text-primary)", fontSize: 11, lineHeight: 1.35 }}
                    >
                      {cell.questionPreview}
                      {cell.questionPreview.length >= 80 && "…"}
                    </div>
                    {cell.answerPreview && (
                      <div
                        className="font-mono"
                        style={{ color: "var(--text-muted)", fontSize: 10, lineHeight: 1.35 }}
                      >
                        Ваш ответ: {cell.answerPreview}
                        {cell.answerPreview.length >= 80 && "…"}
                      </div>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          );
        })}
      </div>
    </div>
  );
}
