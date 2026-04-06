"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Scale, Heart, ArrowRight, Shield, Zap, Lightbulb, Eye, EyeOff } from "lucide-react";
import type { CoachingWhisper } from "@/types";
import { useSessionStore } from "@/stores/useSessionStore";

const ICON_MAP: Record<string, typeof Scale> = {
  scale: Scale,
  heart: Heart,
  "arrow-right": ArrowRight,
  shield: Shield,
  zap: Zap,
};

const TYPE_COLORS: Record<string, string> = {
  legal: "rgba(234, 179, 8, 0.15)",
  emotion: "rgba(239, 68, 68, 0.12)",
  stage: "rgba(34, 197, 94, 0.12)",
  objection: "rgba(139, 92, 246, 0.12)",
  transition: "rgba(59, 130, 246, 0.12)",
};

const TYPE_BORDER_COLORS: Record<string, string> = {
  legal: "rgba(234, 179, 8, 0.3)",
  emotion: "rgba(239, 68, 68, 0.25)",
  stage: "rgba(34, 197, 94, 0.25)",
  objection: "rgba(139, 92, 246, 0.25)",
  transition: "rgba(59, 130, 246, 0.25)",
};

const TYPE_ICON_COLORS: Record<string, string> = {
  legal: "#EAB308",
  emotion: "#EF4444",
  stage: "#22C55E",
  objection: "#6366F1",
  transition: "#3B82F6",
};

function formatTimeAgo(timestamp: number): string {
  const diff = Math.floor((Date.now() - timestamp) / 1000);
  if (diff < 60) return "только что";
  const min = Math.floor(diff / 60);
  if (min === 1) return "1 мин назад";
  if (min < 5) return `${min} мин назад`;
  return `${min} мин назад`;
}

interface WhisperPanelProps {
  onToggle?: (enabled: boolean) => void;
}

export default function WhisperPanel({ onToggle }: WhisperPanelProps) {
  const whispers = useSessionStore((s) => s.whispers);
  const enabled = useSessionStore((s) => s.whispersEnabled);

  const handleToggle = () => {
    const next = !enabled;
    useSessionStore.getState().setWhispersEnabled(next);
    onToggle?.(next);
  };

  return (
    <div
      className="rounded-xl p-4"
      style={{
        background: "var(--glass-bg)",
        border: "1px solid var(--glass-border)",
        backdropFilter: "blur(20px)",
      }}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Lightbulb size={15} style={{ color: "var(--accent)" }} />
          <span className="font-mono text-xs uppercase tracking-wider font-semibold" style={{ color: "var(--text-secondary)" }}>
            Коучинг
          </span>
        </div>
        <button
          onClick={handleToggle}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg transition-colors"
          style={{
            background: enabled ? "rgba(34, 197, 94, 0.12)" : "rgba(255, 255, 255, 0.05)",
            color: enabled ? "#22C55E" : "var(--text-muted)",
          }}
          title={enabled ? "Отключить подсказки" : "Включить подсказки"}
        >
          {enabled ? <Eye size={13} /> : <EyeOff size={13} />}
          <span className="font-mono text-xs uppercase font-medium">{enabled ? "ВКЛ" : "ВЫКЛ"}</span>
        </button>
      </div>

      {!enabled && (
        <div className="text-xs" style={{ color: "var(--text-muted)", opacity: 0.6 }}>
          Подсказки отключены
        </div>
      )}

      {enabled && whispers.length === 0 && (
        <div className="text-xs" style={{ color: "var(--text-muted)", opacity: 0.6 }}>
          Подсказки появятся по ходу разговора
        </div>
      )}

      <AnimatePresence mode="popLayout">
        {enabled && whispers.map((w, i) => {
          const IconComponent = ICON_MAP[w.icon] || Lightbulb;
          const opacity = i === 0 ? 1 : i === 1 ? 0.6 : 0.35;

          return (
            <motion.div
              key={`${w.type}-${w.timestamp}`}
              initial={{ opacity: 0, y: -8, scale: 0.95 }}
              animate={{ opacity, y: 0, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9 }}
              transition={{ duration: 0.3, delay: i * 0.05 }}
              className="mt-2.5 rounded-lg px-3 py-2.5"
              style={{
                background: TYPE_COLORS[w.type] || "rgba(255,255,255,0.05)",
                border: `1px solid ${TYPE_BORDER_COLORS[w.type] || "rgba(255,255,255,0.1)"}`,
              }}
            >
              <div className="flex items-start gap-2.5">
                <IconComponent
                  size={16}
                  style={{ color: TYPE_ICON_COLORS[w.type] || "var(--accent)", marginTop: 2, flexShrink: 0 }}
                />
                <div className="flex-1 min-w-0">
                  <div className="text-sm leading-relaxed" style={{ color: "var(--text-primary)" }}>
                    {w.message}
                  </div>
                  <div className="mt-1 text-xs font-mono uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                    {formatTimeAgo(w.timestamp)}
                  </div>
                </div>
              </div>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
