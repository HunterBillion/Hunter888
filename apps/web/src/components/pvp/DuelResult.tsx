"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Trophy, TrendingUp, TrendingDown, ArrowRight, Minus, ChevronDown, BookOpen, Zap, PlayCircle } from "lucide-react";
import Link from "next/link";

interface PlayerBreakdown {
  selling_score: number;
  acting_score: number;
  legal_score: number;
  total: number;
  selling_breakdown?: Record<string, number>;
  acting_breakdown?: Record<string, number>;
  legal_details?: { claim: string; accuracy: string; explanation: string }[];
  best_reply?: string;
  recommendations?: string[];
  flags?: string[];
}

interface Props {
  myTotal: number;
  opponentTotal: number;
  isWinner: boolean;
  isDraw: boolean;
  isPvE: boolean;
  ratingChangeApplied: boolean;
  myRatingDelta: number;
  summary: string;
  onClose: () => void;
  duelId?: string | null;
  myBreakdown?: PlayerBreakdown | null;
  opponentBreakdown?: PlayerBreakdown | null;
  turningPoint?: { round?: number; description?: string } | null;
}

const SELLING_LABELS: Record<string, string> = {
  objection_handling: "Возражения",
  persuasion: "Убедительность",
  structure: "Структура",
  closing: "Закрытие",
  legal_knowledge: "Юр. знания",
};

const ACTING_LABELS: Record<string, string> = {
  archetype_authenticity: "Аутентичность",
  emotional_depth: "Эмоц. глубина",
  realism: "Реализм",
};

export function DuelResult({
  myTotal,
  opponentTotal,
  isWinner,
  isDraw,
  isPvE,
  ratingChangeApplied,
  myRatingDelta,
  summary,
  onClose,
  duelId,
  myBreakdown,
  opponentBreakdown,
  turningPoint,
}: Props) {
  const [showDetails, setShowDetails] = useState(false);

  // Emit PvP win celebration event
  useEffect(() => {
    if (isWinner) {
      window.dispatchEvent(new CustomEvent("gamification", { detail: { type: "pvp-win" } }));
    }
  }, [isWinner]);

  const resultColor = isDraw ? "var(--warning)" : isWinner ? "var(--success)" : "var(--danger)";
  const resultText = isDraw ? "Ничья" : isWinner ? "Победа!" : "Поражение";
  const deltaSign = myRatingDelta >= 0 ? "+" : "";

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="fixed inset-0 z-[200] flex items-center justify-center overflow-y-auto py-8"
      style={{ background: "rgba(0,0,0,0.9)" }}
    >
      <motion.div
        initial={{ scale: 0.8, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ type: "spring", stiffness: 200, damping: 20 }}
        className="cyber-card max-w-lg w-full mx-4 p-8 text-center"
      >
        {/* Result icon */}
        <motion.div
          initial={{ scale: 0 }}
          animate={{ scale: [0, 1.3, 1] }}
          transition={{ duration: 0.6, delay: 0.2 }}
          className="mx-auto w-20 h-20 rounded-full flex items-center justify-center mb-4"
          style={{ background: `color-mix(in srgb, ${resultColor} 8%, transparent)`, border: `2px solid color-mix(in srgb, ${resultColor} 25%, transparent)` }}
        >
          {isDraw ? (
            <Minus size={36} style={{ color: resultColor }} />
          ) : isWinner ? (
            <Trophy size={36} style={{ color: resultColor }} />
          ) : (
            <TrendingDown size={36} style={{ color: resultColor }} />
          )}
        </motion.div>

        {/* Result text */}
        <motion.h2
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
          className="font-display text-3xl font-black tracking-wider"
          style={{ color: resultColor, textShadow: `0 0 30px color-mix(in srgb, ${resultColor} 25%, transparent)` }}
        >
          {resultText}
        </motion.h2>

        {/* Scores */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.6 }}
          className="mt-6 flex items-center justify-center gap-6"
        >
          <div>
            <div className="font-mono text-xs uppercase" style={{ color: "var(--text-muted)" }}>ВЫ</div>
            <div className="font-display text-3xl font-bold" style={{ color: "var(--accent)" }}>
              {Math.round(myTotal)}
            </div>
          </div>
          <span className="font-mono text-lg" style={{ color: "var(--text-muted)" }}>vs</span>
          <div>
            <div className="font-mono text-xs uppercase" style={{ color: "var(--text-muted)" }}>СОПЕРНИК</div>
            <div className="font-display text-3xl font-bold" style={{ color: "var(--text-secondary)" }}>
              {Math.round(opponentTotal)}
            </div>
          </div>
        </motion.div>

        {/* Rating delta */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.8 }}
          className={`mt-4 inline-flex items-center gap-2 font-mono text-lg font-bold px-4 py-2 rounded-xl stat-chip ${ratingChangeApplied && myRatingDelta >= 0 ? "neon-pulse" : ""}`}
          style={{
            background: ratingChangeApplied ? (myRatingDelta >= 0 ? "rgba(61,220,132,0.1)" : "rgba(229,72,77,0.1)") : "rgba(212,168,75,0.1)",
            color: ratingChangeApplied ? (myRatingDelta >= 0 ? "var(--success)" : "var(--danger)") : "var(--warning)",
            border: `1px solid ${ratingChangeApplied ? (myRatingDelta >= 0 ? "rgba(61,220,132,0.2)" : "rgba(229,72,77,0.2)") : "rgba(212,168,75,0.2)"}`,
          }}
        >
          {ratingChangeApplied ? (
            myRatingDelta >= 0 ? <TrendingUp size={18} /> : <TrendingDown size={18} />
          ) : (
            <Minus size={18} />
          )}
          {ratingChangeApplied ? `${deltaSign}${Math.round(myRatingDelta)} рейтинга` : isPvE ? "PvE без рейтинга" : "Рейтинг не изменён"}
        </motion.div>

        {/* Turning point */}
        {turningPoint?.description && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.9 }}
            className="mt-3 flex items-center justify-center gap-2 text-xs font-mono"
            style={{ color: "var(--accent)" }}
          >
            <Zap size={12} />
            {turningPoint.description}
          </motion.div>
        )}

        {/* Summary */}
        {summary && (
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 1 }}
            className="mt-4 text-sm leading-relaxed"
            style={{ color: "var(--text-secondary)" }}
          >
            {summary}
          </motion.p>
        )}

        {/* Detailed breakdown toggle */}
        {myBreakdown && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 1.1 }}
            className="mt-4"
          >
            <button
              type="button"
              onClick={() => setShowDetails(!showDetails)}
              className="inline-flex items-center gap-1.5 text-xs font-mono"
              style={{ color: "var(--accent)" }}
            >
              <ChevronDown
                size={12}
                className="transition-transform"
                style={{ transform: showDetails ? "rotate(180deg)" : "rotate(0deg)" }}
              />
              {showDetails ? "Скрыть детали" : "Подробный разбор"}
            </button>

            <AnimatePresence>
              {showDetails && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.3 }}
                  className="overflow-hidden"
                >
                  <div className="mt-3 space-y-3 text-left">
                    {/* My selling breakdown */}
                    {myBreakdown.selling_breakdown && Object.keys(myBreakdown.selling_breakdown).length > 0 && (
                      <div className="glass-panel rounded-lg p-3">
                        <div className="text-xs font-mono tracking-wider mb-2 flex items-center gap-1.5" style={{ color: "var(--accent)" }}>
                          <Zap size={9} /> ВАШИ ПРОДАЖИ
                        </div>
                        <div className="space-y-1">
                          {Object.entries(myBreakdown.selling_breakdown).map(([key, val]) => (
                            <div key={key} className="flex items-center justify-between">
                              <span className="text-xs font-mono" style={{ color: "var(--text-secondary)" }}>
                                {SELLING_LABELS[key] || key}
                              </span>
                              <span className="text-xs font-mono font-bold" style={{ color: "var(--text-primary)" }}>
                                {val}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* My acting breakdown */}
                    {myBreakdown.acting_breakdown && Object.keys(myBreakdown.acting_breakdown).length > 0 && (
                      <div className="glass-panel rounded-lg p-3">
                        <div className="text-xs font-mono tracking-wider mb-2 flex items-center gap-1.5" style={{ color: "var(--accent)" }}>
                          <Trophy size={9} /> ВАША ИГРА КЛИЕНТА
                        </div>
                        <div className="space-y-1">
                          {Object.entries(myBreakdown.acting_breakdown).map(([key, val]) => (
                            <div key={key} className="flex items-center justify-between">
                              <span className="text-xs font-mono" style={{ color: "var(--text-secondary)" }}>
                                {ACTING_LABELS[key] || key}
                              </span>
                              <span className="text-xs font-mono font-bold" style={{ color: "var(--text-primary)" }}>
                                {val}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Best reply */}
                    {myBreakdown.best_reply && (
                      <div
                        className="rounded-lg px-3 py-2"
                        style={{ background: "rgba(61,220,132,0.06)", borderLeft: "2px solid var(--success)" }}
                      >
                        <div className="text-xs font-mono tracking-wider mb-1" style={{ color: "var(--success)" }}>
                          ЛУЧШАЯ РЕПЛИКА
                        </div>
                        <p className="text-xs italic leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                          &ldquo;{myBreakdown.best_reply}&rdquo;
                        </p>
                      </div>
                    )}

                    {/* Recommendations */}
                    {myBreakdown.recommendations && myBreakdown.recommendations.length > 0 && (
                      <div className="glass-panel rounded-lg p-3">
                        <div className="text-xs font-mono tracking-wider mb-2 flex items-center gap-1" style={{ color: "var(--accent)" }}>
                          <BookOpen size={13} /> РЕКОМЕНДАЦИИ
                        </div>
                        <ul className="space-y-1">
                          {myBreakdown.recommendations.map((rec, i) => (
                            <li key={i} className="text-xs leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                              {rec}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        )}

        {/* Close button */}
        <motion.button
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1.2 }}
          onClick={onClose}
          className="mt-6 btn-neon flex items-center gap-2 mx-auto"
          whileTap={{ scale: 0.97 }}
        >
          Продолжить <ArrowRight size={14} />
        </motion.button>

        {duelId && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 1.4 }}
            className="mt-3 text-center"
          >
            <Link
              href={`/pvp/duel/${duelId}?replay=true`}
              className="inline-flex items-center gap-2 text-sm"
              style={{ color: "var(--text-muted)" }}
            >
              <PlayCircle size={14} /> Посмотреть повтор
            </Link>
          </motion.div>
        )}
      </motion.div>
    </motion.div>
  );
}
