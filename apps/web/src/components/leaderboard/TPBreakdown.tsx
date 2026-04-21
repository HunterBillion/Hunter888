"use client";

import { motion } from "framer-motion";
import { Crosshair, Swords, BookOpen, Users } from "lucide-react";

export interface TPBreakdownData {
  training: number;
  pvp: number;
  knowledge: number;
  story: number;
  total: number;
}

interface TPBreakdownProps {
  data: TPBreakdownData | null;
  loading?: boolean;
}

const SOURCES = [
  { key: "training", label: "Тренировки", icon: Crosshair, color: "var(--accent, #6B4DC7)" },
  { key: "pvp",      label: "PvP",        icon: Swords,    color: "var(--danger, #ef4444)" },
  { key: "knowledge",label: "Знания",     icon: BookOpen,  color: "var(--info, #3b82f6)" },
  { key: "story",    label: "Мульти",     icon: Users,     color: "var(--warning, #f59e0b)" },
] as const;

export function TPBreakdown({ data, loading }: TPBreakdownProps) {
  if (loading || !data) {
    return (
      <div className="glass-panel p-5">
        <div className="text-xs font-semibold uppercase tracking-widest mb-3" style={{ color: "var(--text-muted)" }}>
          Мои очки недели
        </div>
        <div className="text-sm" style={{ color: "var(--text-muted)" }}>
          {loading ? "Загрузка..." : "—"}
        </div>
      </div>
    );
  }

  const total = Math.max(1, data.total);

  return (
    <div className="glass-panel p-5">
      <div className="flex items-baseline justify-between mb-4">
        <div className="text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
          Мои очки недели
        </div>
        <div className="font-display font-bold text-2xl tabular-nums" style={{ color: "var(--accent)" }}>
          {data.total} <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>TP</span>
        </div>
      </div>

      <div className="space-y-2.5">
        {SOURCES.map((src, i) => {
          const value = data[src.key as keyof TPBreakdownData] as number;
          const pct = (value / total) * 100;
          const Icon = src.icon;
          return (
            <motion.div
              key={src.key}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.06 }}
            >
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <Icon size={12} style={{ color: src.color }} />
                  <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
                    {src.label}
                  </span>
                </div>
                <div className="flex items-baseline gap-2">
                  <span
                    className="font-mono font-bold text-sm tabular-nums"
                    style={{ color: value > 0 ? "var(--text-primary)" : "var(--text-muted)" }}
                  >
                    {value}
                  </span>
                  <span className="text-[10px] font-mono" style={{ color: "var(--text-muted)" }}>
                    TP
                  </span>
                </div>
              </div>
              <div
                className="h-1.5 rounded-full overflow-hidden"
                style={{ background: "var(--input-bg)" }}
              >
                <motion.div
                  className="h-full rounded-full"
                  initial={{ width: 0 }}
                  animate={{ width: `${pct}%` }}
                  transition={{ duration: 0.6, delay: i * 0.06 + 0.1, ease: "easeOut" }}
                  style={{
                    background: `linear-gradient(90deg, ${src.color}, color-mix(in srgb, ${src.color} 50%, transparent))`,
                    boxShadow: value > 0 ? `0 0 6px color-mix(in srgb, ${src.color} 40%, transparent)` : undefined,
                  }}
                />
              </div>
            </motion.div>
          );
        })}
      </div>

      {data.total === 0 && (
        <div
          className="mt-4 p-3 rounded-lg text-center"
          style={{
            background: "var(--input-bg)",
            border: "1px dashed var(--border-color)",
            color: "var(--text-muted)",
            fontSize: "12px",
          }}
        >
          Пройдите тренировку, дуэль или квиз — очки появятся здесь.
        </div>
      )}
    </div>
  );
}
