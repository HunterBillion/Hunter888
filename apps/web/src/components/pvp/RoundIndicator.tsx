"use client";

import { motion } from "framer-motion";
import { ArrowLeftRight } from "lucide-react";
import { useReducedMotion } from "@/hooks/useReducedMotion";

interface Props {
  roundNumber: number;
  myRole: "seller" | "client";
  timeRemaining: number;
}

export function RoundIndicator({ roundNumber, myRole, timeRemaining }: Props) {
  const reducedMotion = useReducedMotion();
  const mins = Math.floor(timeRemaining / 60);
  const secs = timeRemaining % 60;
  const isLow = timeRemaining <= 60;

  return (
    <div
      className="flex items-center justify-between px-5 py-3 rounded-xl"
      style={{
        background: "var(--glass-bg)",
        border: "1px solid var(--glass-border)",
        backdropFilter: "blur(12px)",
      }}
    >
      {/* Round */}
      <div className="flex items-center gap-3">
        <div className="flex gap-1">
          {[1, 2].map((r) => (
            <div
              key={r}
              className="w-8 h-1.5 rounded-full"
              style={{
                background: r === roundNumber ? "var(--accent)" : r < roundNumber ? "var(--neon-green)" : "var(--input-bg)",
              }}
            />
          ))}
        </div>
        <span className="font-mono text-xs tracking-wider" style={{ color: "var(--text-secondary)" }}>
          РАУНД {roundNumber}/2
        </span>
        {roundNumber === 0 && (
          <motion.div
            animate={reducedMotion ? {} : { scale: [1, 1.1, 1] }}
            transition={reducedMotion ? {} : { repeat: Infinity, duration: 1.5 }}
            className="flex items-center gap-1 font-mono text-xs"
            style={{ color: "var(--warning)" }}
          >
            <ArrowLeftRight size={12} /> СМЕНА РОЛЕЙ
          </motion.div>
        )}
      </div>

      {/* Role badge */}
      <div
        className="font-mono text-xs tracking-widest uppercase px-3 py-1 rounded-lg"
        style={{
          background: myRole === "seller" ? "rgba(99,102,241,0.1)" : "rgba(59,130,246,0.1)",
          border: `1px solid ${myRole === "seller" ? "rgba(99,102,241,0.3)" : "rgba(59,130,246,0.3)"}`,
          color: myRole === "seller" ? "var(--accent)" : "var(--info)",
        }}
      >
        {myRole === "seller" ? "МЕНЕДЖЕР" : "КЛИЕНТ"}
      </div>

      {/* Timer */}
      <div
        className={`font-mono text-lg font-bold ${isLow && !reducedMotion ? "animate-pulse" : ""}`}
        style={{ color: isLow ? "var(--neon-red)" : "var(--text-primary)" }}
      >
        {mins}:{secs.toString().padStart(2, "0")}
      </div>
    </div>
  );
}
