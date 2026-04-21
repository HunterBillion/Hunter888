"use client";

/**
 * ChestOpenModal — animated chest opening with reveal of random rewards.
 *
 * Two phases:
 *   1. Chest shaking animation (1.5s) — anticipation
 *   2. Reward reveal with confetti — satisfaction
 */

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Gift, X, Sparkles, Coins, Award } from "lucide-react";

interface ChestReward {
  chest_type: string;
  xp_reward: number;
  ap_reward: number;
  item_reward: string | null;
  item_name: string | null;
  is_rare_drop: boolean;
}

interface ChestOpenModalProps {
  reward: ChestReward | null;
  onClose: () => void;
}

const CHEST_COLORS: Record<string, { bg: string; border: string; glow: string }> = {
  bronze: { bg: "color-mix(in srgb, var(--rank-bronze) 60%, #000)", border: "var(--rank-bronze)", glow: "color-mix(in srgb, var(--rank-bronze) 30%, transparent)" },
  silver: { bg: "color-mix(in srgb, var(--rank-silver) 60%, #000)", border: "var(--rank-silver)", glow: "color-mix(in srgb, var(--rank-silver) 30%, transparent)" },
  gold: { bg: "color-mix(in srgb, var(--rank-gold) 60%, #000)", border: "var(--rank-gold)", glow: "color-mix(in srgb, var(--rank-gold) 40%, transparent)" },
};

const CHEST_EMOJI: Record<string, string> = {
  bronze: "\uD83E\uDDF0",   // toolbox
  silver: "\uD83D\uDCE6",   // package
  gold: "\uD83C\uDF81",     // wrapped gift
};

export default function ChestOpenModal({ reward, onClose }: ChestOpenModalProps) {
  const [phase, setPhase] = useState<"shaking" | "revealed">("shaking");

  useEffect(() => {
    if (!reward) return;
    setPhase("shaking");
    const timer = setTimeout(() => setPhase("revealed"), 1500);
    return () => clearTimeout(timer);
  }, [reward]);

  // Auto-close after 5s
  useEffect(() => {
    if (phase !== "revealed") return;
    const timer = setTimeout(onClose, 5000);
    return () => clearTimeout(timer);
  }, [phase, onClose]);

  if (!reward) return null;

  const colors = CHEST_COLORS[reward.chest_type] || CHEST_COLORS.bronze;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-[300] flex items-center justify-center bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      >
        <motion.div
          initial={{ scale: 0.8, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.8, opacity: 0 }}
          className="relative w-80 rounded-2xl p-6 text-center"
          style={{
            background: "var(--bg-secondary)",
            boxShadow: `0 0 60px ${colors.glow}`,
          }}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Close */}
          <button
            onClick={onClose}
            className="absolute top-3 right-3 text-[var(--text-muted)] hover:text-[var(--text-primary)]"
          >
            <X size={16} />
          </button>

          {phase === "shaking" ? (
            /* Phase 1: Shaking chest */
            <motion.div
              animate={{
                rotate: [0, -5, 5, -5, 5, -3, 3, 0],
                scale: [1, 1.05, 1, 1.05, 1, 1.02, 1],
              }}
              transition={{ duration: 1.5, ease: "easeInOut" }}
              className="py-8"
            >
              <span className="text-7xl">
                {CHEST_EMOJI[reward.chest_type]}
              </span>
              <p className="mt-4 text-sm text-[var(--text-muted)] animate-pulse">
                Открываем...
              </p>
            </motion.div>
          ) : (
            /* Phase 2: Reveal */
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4 }}
              className="py-4"
            >
              <p className="text-lg font-bold text-[var(--text-primary)] mb-4">
                {reward.is_rare_drop ? "\u2728 Редкая находка!" : "Награда!"}
              </p>

              <div className="space-y-3">
                {/* XP */}
                <div className="flex items-center justify-center gap-2">
                  <Sparkles size={18} className="text-[var(--accent)]" />
                  <span className="text-2xl font-black font-mono text-[var(--accent)]">
                    +{reward.xp_reward} XP
                  </span>
                </div>

                {/* AP */}
                {reward.ap_reward > 0 && (
                  <div className="flex items-center justify-center gap-2">
                    <Coins size={16} className="text-[var(--warning)]" />
                    <span className="text-lg font-bold text-[var(--warning)]">
                      +{reward.ap_reward} AP
                    </span>
                  </div>
                )}

                {/* Item */}
                {reward.item_name && (
                  <motion.div
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    transition={{ delay: 0.3, type: "spring" }}
                    className="rounded-lg p-3 mt-2"
                    style={{
                      background: `linear-gradient(135deg, ${colors.glow}, transparent)`,
                      border: `1px solid ${colors.border}`,
                    }}
                  >
                    <div className="flex items-center justify-center gap-2">
                      <Award size={16} style={{ color: colors.border }} />
                      <span className="text-sm font-semibold" style={{ color: colors.border }}>
                        {reward.item_name}
                      </span>
                    </div>
                  </motion.div>
                )}
              </div>

              <button
                onClick={onClose}
                className="mt-5 w-full rounded-lg py-2.5 text-sm font-semibold transition-colors"
                style={{
                  background: colors.border,
                  color: "#1a1a2e",
                }}
              >
                Забрать
              </button>
            </motion.div>
          )}
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
