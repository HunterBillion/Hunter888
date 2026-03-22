"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Brain, Heart, Flame, Shield, AlertTriangle, Frown, Clock, Zap } from "lucide-react";
import type { HumanFactor } from "@/types/story";

const FACTOR_CONFIG: Record<string, { icon: typeof Brain; color: string; label: string }> = {
  stress: { icon: Zap, color: "#FF3333", label: "Стресс" },
  fatigue: { icon: Clock, color: "#F59E0B", label: "Усталость" },
  anger: { icon: Flame, color: "#FF6B35", label: "Гнев" },
  fear: { icon: AlertTriangle, color: "#A78BFA", label: "Страх" },
  distrust: { icon: Shield, color: "#3B82F6", label: "Недоверие" },
  sadness: { icon: Frown, color: "#60A5FA", label: "Грусть" },
  empathy: { icon: Heart, color: "#EC4899", label: "Эмпатия" },
  default: { icon: Brain, color: "#8B5CF6", label: "Фактор" },
};

interface Props {
  factors: HumanFactor[];
}

export function HumanFactorIcons({ factors }: Props) {
  if (factors.length === 0) return null;

  return (
    <div className="flex items-center gap-1.5">
      <span className="font-mono text-[9px] tracking-widest uppercase mr-1" style={{ color: "var(--text-muted)" }}>
        FACTORS
      </span>
      <AnimatePresence>
        {factors.map((f) => {
          const config = FACTOR_CONFIG[f.factor] || FACTOR_CONFIG.default;
          const Icon = config.icon;
          const opacity = Math.max(0.4, f.intensity);
          return (
            <motion.div
              key={f.factor}
              initial={{ scale: 0, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0, opacity: 0 }}
              className="relative group"
              title={`${config.label}: ${Math.round(f.intensity * 100)}%`}
            >
              <div
                className="flex h-7 w-7 items-center justify-center rounded-lg"
                style={{
                  background: `${config.color}15`,
                  border: `1px solid ${config.color}40`,
                  opacity,
                }}
              >
                <Icon size={14} style={{ color: config.color }} />
              </div>
              {/* Intensity bar */}
              <div
                className="absolute -bottom-0.5 left-0.5 right-0.5 h-[2px] rounded-full"
                style={{ background: config.color, opacity: f.intensity }}
              />
              {/* Tooltip */}
              <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden group-hover:block z-50">
                <div
                  className="rounded-lg px-2 py-1 text-[10px] font-mono whitespace-nowrap"
                  style={{ background: "var(--bg-secondary)", border: "1px solid var(--border-color)", color: config.color }}
                >
                  {config.label} {Math.round(f.intensity * 100)}%
                </div>
              </div>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
