"use client";

import { motion } from "framer-motion";
import { Trophy, TrendingUp, TrendingDown, ArrowRight, Minus } from "lucide-react";

interface Props {
  myTotal: number;
  opponentTotal: number;
  isWinner: boolean;
  isDraw: boolean;
  myRatingDelta: number;
  summary: string;
  onClose: () => void;
}

export function DuelResult({ myTotal, opponentTotal, isWinner, isDraw, myRatingDelta, summary, onClose }: Props) {
  const resultColor = isDraw ? "var(--warning)" : isWinner ? "var(--neon-green, #00FF66)" : "var(--neon-red, #FF3333)";
  const resultText = isDraw ? "НИЧЬЯ" : isWinner ? "ПОБЕДА!" : "ПОРАЖЕНИЕ";
  const deltaSign = myRatingDelta >= 0 ? "+" : "";

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="fixed inset-0 z-[200] flex items-center justify-center"
      style={{ background: "rgba(0,0,0,0.9)" }}
    >
      <motion.div
        initial={{ scale: 0.8, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ type: "spring", stiffness: 200, damping: 20 }}
        className="glass-panel max-w-md w-full mx-4 p-8 text-center"
      >
        {/* Result icon */}
        <motion.div
          initial={{ scale: 0 }}
          animate={{ scale: [0, 1.3, 1] }}
          transition={{ duration: 0.6, delay: 0.2 }}
          className="mx-auto w-20 h-20 rounded-full flex items-center justify-center mb-4"
          style={{ background: `${resultColor}15`, border: `2px solid ${resultColor}40` }}
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
          style={{ color: resultColor, textShadow: `0 0 30px ${resultColor}40` }}
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
            <div className="font-mono text-[10px] uppercase" style={{ color: "var(--text-muted)" }}>ВЫ</div>
            <div className="font-display text-3xl font-bold" style={{ color: "var(--accent)" }}>
              {Math.round(myTotal)}
            </div>
          </div>
          <span className="font-mono text-lg" style={{ color: "var(--text-muted)" }}>vs</span>
          <div>
            <div className="font-mono text-[10px] uppercase" style={{ color: "var(--text-muted)" }}>СОПЕРНИК</div>
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
          className="mt-4 inline-flex items-center gap-2 font-mono text-lg font-bold px-4 py-2 rounded-xl"
          style={{
            background: myRatingDelta >= 0 ? "rgba(0,255,102,0.1)" : "rgba(255,51,51,0.1)",
            color: myRatingDelta >= 0 ? "var(--neon-green)" : "var(--neon-red)",
          }}
        >
          {myRatingDelta >= 0 ? <TrendingUp size={18} /> : <TrendingDown size={18} />}
          {deltaSign}{Math.round(myRatingDelta)} рейтинга
        </motion.div>

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

        {/* Close button */}
        <motion.button
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1.2 }}
          onClick={onClose}
          className="mt-6 vh-btn-primary flex items-center gap-2 mx-auto"
          whileTap={{ scale: 0.97 }}
        >
          Продолжить <ArrowRight size={14} />
        </motion.button>
      </motion.div>
    </motion.div>
  );
}
