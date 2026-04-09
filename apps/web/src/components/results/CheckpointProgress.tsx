"use client";

import { motion } from "framer-motion";
import { CheckCircle2, Circle, Flag } from "lucide-react";

export interface CheckpointResult {
  name: string;
  hit: boolean;
  time?: string;
}

interface CheckpointProgressProps {
  checkpoints: CheckpointResult[];
}

export default function CheckpointProgress({ checkpoints }: CheckpointProgressProps) {
  if (!checkpoints || checkpoints.length === 0) return null;

  const hitCount = checkpoints.filter((c) => c.hit).length;

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-panel rounded-2xl p-6"
    >
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-display text-sm tracking-widest flex items-center gap-2" style={{ color: "var(--text-primary)" }}>
          <Flag size={16} style={{ color: "var(--accent)" }} />
          ЧЕКПОИНТЫ СКРИПТА
        </h3>
        <span className="font-mono text-xs" style={{ color: "var(--text-muted)" }}>
          {hitCount}/{checkpoints.length}
        </span>
      </div>

      {/* Horizontal timeline */}
      <div className="relative">
        {/* Connection line */}
        <div
          className="absolute top-3 left-3 right-3 h-px"
          style={{ background: "var(--border-color)" }}
        />

        <div className="flex justify-between relative">
          {checkpoints.map((cp, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, scale: 0.5 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: 0.1 + i * 0.08 }}
              className="flex flex-col items-center"
              style={{ width: `${100 / checkpoints.length}%` }}
            >
              {/* Dot */}
              <div className="relative z-10 mb-2">
                {cp.hit ? (
                  <motion.div
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    transition={{ type: "spring", stiffness: 400, damping: 12, delay: 0.2 + i * 0.08 }}
                  >
                    <CheckCircle2
                      size={22}
                      strokeWidth={2.5}
                      style={{
                        color: "var(--success)",
                        filter: "drop-shadow(0 0 4px rgba(61,220,132,0.4))",
                      }}
                    />
                  </motion.div>
                ) : (
                  <Circle
                    size={22}
                    strokeWidth={1.5}
                    style={{ color: "var(--border-color)" }}
                  />
                )}
              </div>

              {/* Label */}
              <span
                className="text-xs font-mono text-center leading-tight max-w-[80px] truncate"
                style={{
                  color: cp.hit ? "var(--text-primary)" : "var(--text-muted)",
                }}
                title={cp.name}
              >
                {cp.name}
              </span>

              {/* Time stamp */}
              {cp.time && (
                <span className="text-xs font-mono mt-0.5" style={{ color: "var(--text-muted)" }}>
                  {cp.time}
                </span>
              )}
            </motion.div>
          ))}
        </div>
      </div>
    </motion.div>
  );
}
