"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { CheckCircle2, XCircle, Shield, ChevronDown, BookOpen, Scale } from "lucide-react";
import type { TrapResultItem } from "@/types";

/** @deprecated Use TrapResultItem from @/types instead */
export type TrapResult = TrapResultItem;

interface TrapResultsProps {
  traps: TrapResultItem[];
}

const CATEGORY_LABELS: Record<string, string> = {
  legal: "Юридическая",
  emotional: "Эмоциональная",
  manipulative: "Манипулятивная",
  expert: "Экспертная",
  price: "Ценовая",
  provocative: "Провокационная",
  professional: "Профессиональная",
  procedural: "Процедурная",
};

export default function TrapResults({ traps }: TrapResultsProps) {
  const [expanded, setExpanded] = useState<number | null>(null);

  if (!traps || traps.length === 0) return null;

  const totalBonus = traps.reduce((sum, t) => sum + (t.caught && t.bonus ? t.bonus : 0), 0);
  const totalPenalty = traps.reduce((sum, t) => sum + (!t.caught && t.penalty ? t.penalty : 0), 0);
  const net = totalBonus - totalPenalty;

  const container = {
    hidden: { opacity: 0 },
    show: { opacity: 1, transition: { staggerChildren: 0.1 } },
  };
  const item = {
    hidden: { opacity: 0, x: -12 },
    show: { opacity: 1, x: 0 },
  };

  return (
    <motion.div
      variants={container}
      initial="hidden"
      animate="show"
      className="cyber-card rounded-2xl p-6"
    >
      <h3 className="font-display text-sm tracking-widest flex items-center gap-2 mb-4" style={{ color: "var(--text-primary)" }}>
        <Shield size={16} style={{ color: "var(--accent)" }} />
        ЛОВУШКИ
      </h3>

      <div className="space-y-2">
        {traps.map((trap, i) => {
          const isExpanded = expanded === i;
          const hasDetails = !!(trap.correct_example || trap.explanation || trap.client_phrase);
          const isFell = trap.status === "fell" || (!trap.caught && trap.status !== "partial");
          const isPartial = trap.status === "partial";

          return (
            <motion.div key={i} variants={item}>
              <button
                type="button"
                className="w-full text-left rounded-lg px-3 py-2"
                onClick={() => hasDetails && setExpanded(isExpanded ? null : i)}
                style={{
                  cursor: hasDetails ? "pointer" : "default",
                  background: trap.caught
                    ? "rgba(0,255,148,0.06)"
                    : isPartial
                      ? "rgba(245,158,11,0.06)"
                      : "rgba(255,42,109,0.06)",
                  borderLeft: `3px solid ${
                    trap.caught
                      ? "var(--neon-green, #00FF94)"
                      : isPartial
                        ? "#f59e0b"
                        : "var(--neon-red, #FF2A6D)"
                  }`,
                }}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 min-w-0">
                    {trap.caught ? (
                      <CheckCircle2 size={14} className="shrink-0" style={{ color: "var(--neon-green, #00FF94)" }} />
                    ) : (
                      <XCircle size={14} className="shrink-0" style={{ color: isPartial ? "#f59e0b" : "var(--neon-red, #FF2A6D)" }} />
                    )}
                    <span className="text-sm truncate" style={{ color: "var(--text-secondary)" }}>
                      {trap.name}
                    </span>
                    {trap.category && (
                      <span className="status-badge status-badge--neutral shrink-0" style={{ fontSize: "12px" }}>
                        {CATEGORY_LABELS[trap.category] || trap.category}
                      </span>
                    )}
                    {hasDetails && (
                      <ChevronDown
                        size={12}
                        className="shrink-0 transition-transform"
                        style={{
                          transform: isExpanded ? "rotate(180deg)" : "rotate(0deg)",
                          color: "var(--text-muted)",
                        }}
                      />
                    )}
                  </div>
                  <span
                    className="font-mono text-xs font-bold shrink-0 ml-2"
                    style={{
                      color: trap.caught
                        ? "var(--neon-green, #00FF94)"
                        : isPartial
                          ? "#f59e0b"
                          : "var(--neon-red, #FF2A6D)",
                    }}
                  >
                    {trap.caught ? `+${trap.bonus || 0}` : `-${trap.penalty || 0}`}
                  </span>
                </div>
              </button>

              {/* Expandable details */}
              <AnimatePresence>
                {isExpanded && hasDetails && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.2 }}
                    className="overflow-hidden"
                  >
                    <div
                      className="mx-3 mb-2 mt-1 rounded-lg px-3 py-2.5 space-y-2"
                      style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)" }}
                    >
                      {/* Client phrase that triggered the trap */}
                      {trap.client_phrase && (
                        <div className="space-y-0.5">
                          <span className="text-xs font-mono tracking-wider" style={{ color: "var(--text-muted)" }}>
                            ФРАЗА КЛИЕНТА
                          </span>
                          <p className="text-xs leading-relaxed italic" style={{ color: "var(--text-secondary)" }}>
                            &ldquo;{trap.client_phrase}&rdquo;
                          </p>
                        </div>
                      )}

                      {/* Explanation */}
                      {trap.explanation && (
                        <div className="space-y-0.5">
                          <span className="text-xs font-mono tracking-wider flex items-center gap-1" style={{ color: "var(--text-muted)" }}>
                            <BookOpen size={9} /> ПОЯСНЕНИЕ
                          </span>
                          <p className="text-xs leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                            {trap.explanation}
                          </p>
                        </div>
                      )}

                      {/* Correct example — the key "replay" data */}
                      {trap.correct_example && (isFell || isPartial) && (
                        <div
                          className="rounded px-2.5 py-2 space-y-0.5"
                          style={{
                            background: "rgba(0,255,148,0.06)",
                            borderLeft: "2px solid var(--neon-green, #00FF94)",
                          }}
                        >
                          <span className="text-xs font-mono tracking-wider" style={{ color: "var(--neon-green, #00FF94)" }}>
                            ПРАВИЛЬНЫЙ ОТВЕТ
                          </span>
                          <p className="text-xs leading-relaxed" style={{ color: "var(--text-primary)" }}>
                            {trap.correct_example}
                          </p>
                        </div>
                      )}

                      {/* Law reference */}
                      {trap.law_reference && (
                        <div className="flex items-start gap-1.5 pt-0.5">
                          <Scale size={10} className="shrink-0 mt-0.5" style={{ color: "var(--accent)" }} />
                          <p className="text-xs font-mono" style={{ color: "var(--accent)" }}>
                            {trap.law_reference}
                          </p>
                        </div>
                      )}

                      {/* Keywords */}
                      {((trap.wrong_keywords && trap.wrong_keywords.length > 0) || (trap.correct_keywords && trap.correct_keywords.length > 0)) && (
                        <div className="flex flex-wrap gap-1 pt-0.5">
                          {trap.wrong_keywords?.map((kw, ki) => (
                            <span
                              key={`w${ki}`}
                              className="badge-neon text-xs"
                              style={{ background: "rgba(255,42,109,0.1)", color: "var(--neon-red)", borderColor: "rgba(255,42,109,0.25)" }}
                            >
                              {kw}
                            </span>
                          ))}
                          {trap.correct_keywords?.map((kw, ki) => (
                            <span
                              key={`c${ki}`}
                              className="badge-neon text-xs"
                              style={{ background: "rgba(0,255,148,0.1)", color: "var(--neon-green)", borderColor: "rgba(0,255,148,0.25)" }}
                            >
                              {kw}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          );
        })}
      </div>

      {/* Net score */}
      <div
        className="mt-4 pt-3 flex items-center justify-between font-mono text-xs"
        style={{ borderTop: "1px solid var(--border-color)" }}
      >
        <span style={{ color: "var(--text-muted)" }}>Итого:</span>
        <div className="flex items-center gap-3">
          <span style={{ color: "var(--neon-green, #00FF94)" }}>+{totalBonus}</span>
          <span style={{ color: "var(--text-muted)" }}>/</span>
          <span style={{ color: "var(--neon-red, #FF2A6D)" }}>-{totalPenalty}</span>
          <span style={{ color: "var(--text-muted)" }}>=</span>
          <span
            className="font-bold"
            style={{
              color: net >= 0 ? "var(--neon-green, #00FF94)" : "var(--neon-red, #FF2A6D)",
            }}
          >
            {net >= 0 ? `+${net}` : net}
          </span>
        </div>
      </div>
    </motion.div>
  );
}
