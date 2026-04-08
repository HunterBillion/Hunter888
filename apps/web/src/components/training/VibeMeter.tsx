"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Activity } from "lucide-react";
import { type EmotionState, EMOTION_MAP } from "@/types";
import { useReducedMotion } from "@/hooks/useReducedMotion";

const ARCHETYPE_HINTS: Record<string, string> = {
  skeptic: "Скептик: нужны факты и цифры",
  anxious: "Тревожный: нужна эмпатия",
  aggressive: "Агрессивный: сохраняйте спокойствие",
  passive: "Пассивный: задавайте вопросы",
  analytical: "Аналитик: приводите данные",
  emotional: "Эмоциональный: покажите понимание",
  busy: "Занятой: будьте кратки",
  indecisive: "Нерешительный: помогите с выбором",
};

/** The 5 gradient stops for the horizontal bar, left to right. */
const BAR_STOPS = [
  { key: "hostile",     color: EMOTION_MAP.hostile.color },
  { key: "guarded",     color: EMOTION_MAP.guarded.color },
  { key: "curious",     color: EMOTION_MAP.curious.color },
  { key: "negotiating", color: EMOTION_MAP.negotiating.color },
  { key: "deal",        color: EMOTION_MAP.deal.color },
] as const;

const BAR_LABELS = ["Враж", "Настор", "Любоп", "Торг", "Сделка"] as const;

interface VibeMeterProps {
  emotion: EmotionState;
  archetype?: string | null;
  trigger?: string | null;
}

export default function VibeMeter({ emotion, archetype, trigger }: VibeMeterProps) {
  const config = EMOTION_MAP[emotion] || EMOTION_MAP.cold;
  const reducedMotion = useReducedMotion();

  const gradientStr = BAR_STOPS.map((s) => s.color).join(", ");

  return (
    <div className="flex flex-col">
      {/* ── Header ── */}
      <div className="flex items-center justify-between mb-3">
        <h3
          className="text-sm font-semibold uppercase tracking-widest"
          style={{ color: "var(--text-secondary)" }}
        >
          Настроение
        </h3>
        <Activity size={16} style={{ color: "var(--accent)" }} />
      </div>

      {/* ── Center: dot + emotion label ── */}
      <div className="flex items-center justify-center gap-2 mb-1">
        <span
          className="w-3 h-3 rounded-full shrink-0"
          style={{ backgroundColor: config.color, boxShadow: `0 0 8px ${config.glow}` }}
        />
        <AnimatePresence mode="wait">
          <motion.span
            key={emotion}
            className="text-xl font-bold"
            style={{ color: config.color, textShadow: `0 0 12px ${config.glow}` }}
            initial={{ opacity: 0, scale: 1.15 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3 }}
          >
            <motion.span
              className="inline-block"
              animate={
                reducedMotion
                  ? {}
                  : {
                      textShadow: [
                        `0 0 10px ${config.glow}`,
                        `0 0 22px ${config.glow}`,
                        `0 0 10px ${config.glow}`,
                      ],
                    }
              }
              transition={reducedMotion ? {} : { duration: 1.5, ease: "easeInOut" }}
            >
              {config.labelRu}
            </motion.span>
          </motion.span>
        </AnimatePresence>
      </div>

      {/* ── Percentage ── */}
      <div
        className="text-3xl font-bold tabular-nums text-center mb-3"
        style={{ color: config.color }}
      >
        {config.value}%
      </div>

      {/* ── Horizontal gradient bar with indicator ── */}
      <div className="relative h-5 flex items-center">
        {/* Bar track */}
        <div className="absolute left-0 right-0 h-2 rounded-full"
          style={{ background: `linear-gradient(to right, ${gradientStr})` }}
        />
        {/* Indicator dot */}
        <motion.div
          className="absolute w-4 h-4 rounded-full border-2 border-white z-10"
          style={{
            backgroundColor: config.color,
            boxShadow: `0 0 8px ${config.glow}`,
            marginLeft: -8,
          }}
          animate={{ left: `${config.value}%` }}
          transition={{ duration: 0.8, ease: "easeOut" }}
        />
      </div>

      {/* ── 5 tiny labels under the bar ── */}
      <div className="flex justify-between mt-1.5">
        {BAR_STOPS.map((stop, i) => (
          <span
            key={stop.key}
            className="text-xs"
            style={{ color: stop.color }}
          >
            {BAR_LABELS[i]}
          </span>
        ))}
      </div>

      {/* ── Archetype hint ── */}
      {archetype && (
        <div
          className="mt-3 text-center text-xs truncate"
          style={{ color: "var(--text-secondary)" }}
          title={trigger || ARCHETYPE_HINTS[archetype] || archetype}
        >
          {trigger || ARCHETYPE_HINTS[archetype] || archetype}
        </div>
      )}
    </div>
  );
}
