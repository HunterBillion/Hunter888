"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Swords, TrendingUp, TrendingDown, Minus } from "lucide-react";
import { useSound } from "@/hooks/useSound";
import { useHaptic } from "@/hooks/useHaptic";
import { Confetti } from "@/components/ui/Confetti";

interface PvPVictoryScreenProps {
  isWinner: boolean;
  isDraw: boolean;
  myScore: number;
  opponentScore: number;
  ratingDelta: number;
  onContinue: () => void;
}

export function PvPVictoryScreen({
  isWinner,
  isDraw,
  myScore,
  opponentScore,
  ratingDelta,
  onContinue,
}: PvPVictoryScreenProps) {
  const [phase, setPhase] = useState<"reveal" | "details">("reveal");
  const [confettiTrigger, setConfettiTrigger] = useState(0);
  const { playSound } = useSound();
  const haptic = useHaptic();

  useEffect(() => {
    if (isWinner) {
      playSound("victory");
      haptic("victory");
      setConfettiTrigger((n) => n + 1);
    } else if (isDraw) {
      playSound("success");
      haptic("tap");
    } else {
      playSound("defeat");
      haptic("error");
    }

    const timer = setTimeout(() => setPhase("details"), 2000);
    return () => clearTimeout(timer);
  }, [isWinner, isDraw, playSound, haptic]);

  const resultColor = isWinner
    ? "var(--gf-xp)"
    : isDraw
    ? "var(--text-secondary)"
    : "var(--danger)";

  const resultText = isWinner ? "ПОБЕДА" : isDraw ? "НИЧЬЯ" : "ПОРАЖЕНИЕ";
  const resultGlow = isWinner
    ? "rgba(255, 215, 0, 0.4)"
    : isDraw
    ? "rgba(180, 180, 200, 0.2)"
    : "rgba(229, 72, 77, 0.3)";

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-[200] flex items-center justify-center"
      style={{ background: "rgba(0, 0, 0, 0.9)" }}
    >
      <Confetti trigger={confettiTrigger} />

      <AnimatePresence mode="wait">
        {/* Phase 1: Result reveal */}
        {phase === "reveal" && (
          <motion.div
            key="reveal"
            initial={{ scale: 3, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ opacity: 0, scale: 0.8 }}
            transition={{ type: "spring", stiffness: 200, damping: 15 }}
            className="text-center space-y-4"
          >
            <motion.div
              animate={isWinner ? { rotate: [0, -10, 10, 0] } : {}}
              transition={{ duration: 0.5, delay: 0.3 }}
            >
              <Swords
                size={64}
                style={{
                  color: resultColor,
                  filter: `drop-shadow(0 0 20px ${resultGlow})`,
                }}
              />
            </motion.div>
            <div
              className="font-display font-black text-7xl tracking-[0.2em]"
              style={{
                color: resultColor,
                textShadow: `0 0 60px ${resultGlow}`,
              }}
            >
              {resultText}
            </div>
          </motion.div>
        )}

        {/* Phase 2: Score details */}
        {phase === "details" && (
          <motion.div
            key="details"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-center space-y-8"
          >
            {/* Score comparison */}
            <div className="flex items-center gap-8 justify-center">
              <div>
                <div
                  className="font-display text-6xl font-bold"
                  style={{ color: isWinner ? "var(--gf-xp)" : "var(--text-primary)" }}
                >
                  {myScore}
                </div>
                <div className="text-sm font-mono mt-1" style={{ color: "var(--text-muted)" }}>
                  ВЫ
                </div>
              </div>
              <div
                className="font-mono text-2xl font-bold"
                style={{ color: "var(--text-muted)" }}
              >
                :
              </div>
              <div>
                <div
                  className="font-display text-6xl font-bold"
                  style={{ color: !isWinner && !isDraw ? "var(--gf-xp)" : "var(--text-primary)" }}
                >
                  {opponentScore}
                </div>
                <div className="text-sm font-mono mt-1" style={{ color: "var(--text-muted)" }}>
                  СОПЕРНИК
                </div>
              </div>
            </div>

            {/* Rating change */}
            <motion.div
              initial={{ scale: 0, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ delay: 0.3, type: "spring" }}
              className="inline-flex items-center gap-2 rounded-full px-5 py-2"
              style={{
                background: ratingDelta >= 0
                  ? "rgba(61, 220, 132, 0.1)"
                  : "rgba(229, 72, 77, 0.1)",
                border: `1px solid ${ratingDelta >= 0 ? "rgba(61, 220, 132, 0.3)" : "rgba(229, 72, 77, 0.3)"}`,
              }}
            >
              {ratingDelta > 0 ? (
                <TrendingUp size={18} style={{ color: "var(--success)" }} />
              ) : ratingDelta < 0 ? (
                <TrendingDown size={18} style={{ color: "var(--danger)" }} />
              ) : (
                <Minus size={18} style={{ color: "var(--text-muted)" }} />
              )}
              <span
                className="font-mono font-bold text-lg"
                style={{
                  color: ratingDelta > 0 ? "var(--success)" : ratingDelta < 0 ? "var(--danger)" : "var(--text-muted)",
                }}
              >
                {ratingDelta > 0 ? "+" : ""}{ratingDelta} ELO
              </span>
            </motion.div>

            {/* Continue */}
            <motion.button
              onClick={onContinue}
              className="btn-neon flex items-center gap-2 mx-auto text-lg px-8 py-4"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.5 }}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              Подробный разб��р
            </motion.button>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
