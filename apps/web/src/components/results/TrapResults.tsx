"use client";

import { motion } from "framer-motion";
import { CheckCircle2, XCircle, Shield } from "lucide-react";
import type { TrapResultItem } from "@/types";

/** @deprecated Use TrapResultItem from @/types instead */
export type TrapResult = TrapResultItem;

interface TrapResultsProps {
  traps: TrapResultItem[];
}

export default function TrapResults({ traps }: TrapResultsProps) {
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
      className="glass-panel rounded-2xl p-6"
    >
      <h3 className="font-display text-sm tracking-widest flex items-center gap-2 mb-4" style={{ color: "var(--text-primary)" }}>
        <Shield size={16} style={{ color: "var(--accent)" }} />
        ЛОВУШКИ
      </h3>

      <div className="space-y-2">
        {traps.map((trap, i) => (
          <motion.div
            key={i}
            variants={item}
            className="flex items-center justify-between rounded-lg px-3 py-2"
            style={{
              background: trap.caught
                ? "rgba(0,255,148,0.06)"
                : "rgba(255,42,109,0.06)",
              borderLeft: `3px solid ${trap.caught ? "var(--neon-green, #00FF94)" : "var(--neon-red, #FF2A6D)"}`,
            }}
          >
            <div className="flex items-center gap-2">
              {trap.caught ? (
                <CheckCircle2 size={14} style={{ color: "var(--neon-green, #00FF94)" }} />
              ) : (
                <XCircle size={14} style={{ color: "var(--neon-red, #FF2A6D)" }} />
              )}
              <span className="text-sm" style={{ color: "var(--text-secondary)" }}>
                {trap.name}
              </span>
            </div>
            <span
              className="font-mono text-xs font-bold"
              style={{
                color: trap.caught
                  ? "var(--neon-green, #00FF94)"
                  : "var(--neon-red, #FF2A6D)",
              }}
            >
              {trap.caught ? `+${trap.bonus || 0}` : `-${trap.penalty || 0}`}
            </span>
          </motion.div>
        ))}
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
