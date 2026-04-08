"use client";

import { useState } from "react";
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

interface VibeMeterProps {
  emotion: EmotionState;
  archetype?: string | null;
  trigger?: string | null;
}

export default function VibeMeter({ emotion, archetype, trigger }: VibeMeterProps) {
  const config = EMOTION_MAP[emotion] || EMOTION_MAP.cold;
  const fillPercent = `${config.value}%`;
  const [hovered, setHovered] = useState(false);
  const reducedMotion = useReducedMotion();

  return (
    <div
      className="rounded-xl p-4 flex flex-col relative overflow-hidden"
      style={{
        background: "var(--glass-bg)",
        border: "1px solid var(--glass-border)",
        backdropFilter: "blur(20px)",
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-display tracking-widest text-sm font-semibold uppercase" style={{ color: "var(--text-secondary)" }}>
          Настроение
        </h3>
        <Activity size={16} style={{ color: "var(--accent)" }} />
      </div>

      <div className="flex gap-4 items-center">
        {/* Compact labels */}
        <div className="flex flex-col justify-between text-xs font-medium leading-snug shrink-0" style={{ height: 130 }}>
          <span className="font-semibold" style={{ color: EMOTION_MAP.deal.color }}>{EMOTION_MAP.deal.labelRu}</span>
          <span style={{ color: EMOTION_MAP.negotiating.color }}>{EMOTION_MAP.negotiating.labelRu}</span>
          <span style={{ color: EMOTION_MAP.curious.color }}>{EMOTION_MAP.curious.labelRu}</span>
          <span style={{ color: EMOTION_MAP.guarded.color }}>{EMOTION_MAP.guarded.labelRu}</span>
          <span style={{ color: EMOTION_MAP.hostile.color }}>{EMOTION_MAP.hostile.labelRu}</span>
        </div>

        {/* Thermometer tube */}
        <div
          className="w-12 rounded-full border relative overflow-hidden flex-shrink-0"
          style={{
            height: 130,
            background: "var(--input-bg)",
            borderColor: "var(--border-color)",
          }}
        >
          {/* Grid lines */}
          <div className="absolute inset-0 flex flex-col justify-between py-2 pointer-events-none opacity-20">
            {[0, 1, 2, 3, 4].map((i) => (
              <div key={i} className="w-full h-px bg-white" />
            ))}
          </div>

          {/* Fill */}
          <motion.div
            className="absolute bottom-0 left-0 w-full"
            style={{
              background: `linear-gradient(to top, ${EMOTION_MAP.hostile.color}, ${EMOTION_MAP.cold.color}, ${EMOTION_MAP.curious.color}, ${EMOTION_MAP.negotiating.color}, ${EMOTION_MAP.deal.color})`,
              boxShadow: `0 0 16px ${config.glow}`,
            }}
            animate={{ height: fillPercent }}
            transition={{ duration: 1.2, ease: "easeOut" }}
          >
            <div className="absolute top-0 w-full h-1.5 bg-white/30 blur-[2px] rounded-t-full" />
          </motion.div>
        </div>

        {/* Current state — right side, large */}
        <div className="flex-1 flex flex-col items-center justify-center min-w-0">
          <AnimatePresence mode="wait">
            <motion.div
              className="text-base font-bold tracking-wide text-center"
              style={{ color: config.color, textShadow: `0 0 12px ${config.glow}` }}
              key={emotion}
              initial={{ opacity: 0, scale: 1.2 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.35 }}
            >
              <motion.span
                className="inline-block"
                animate={reducedMotion ? {} : {
                  textShadow: [
                    `0 0 10px ${config.glow}`,
                    `0 0 22px ${config.glow}`,
                    `0 0 10px ${config.glow}`,
                  ],
                }}
                transition={reducedMotion ? {} : { duration: 1.5, ease: "easeInOut" }}
              >
                {config.labelRu}
              </motion.span>
            </motion.div>
          </AnimatePresence>

          <div className="mt-1.5 text-2xl font-bold font-mono" style={{ color: config.color }}>
            {config.value}%
          </div>
        </div>
      </div>

      {/* Archetype hint */}
      {archetype && (
        <div
          className="mt-3 text-center text-xs truncate"
          style={{ color: "var(--text-secondary)" }}
          title={trigger || ARCHETYPE_HINTS[archetype] || archetype}
        >
          {trigger || ARCHETYPE_HINTS[archetype] || archetype}
        </div>
      )}

      {/* Hover tooltip */}
      <AnimatePresence>
        {hovered && (
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 4 }}
            className="absolute bottom-2 left-2 right-2 rounded-lg p-2.5 text-xs z-10"
            style={{
              background: "var(--bg-secondary)",
              border: "1px solid var(--border-color)",
              color: "var(--text-secondary)",
            }}
          >
            Эмоция: {config.labelRu}.{" "}
            {archetype ? (ARCHETYPE_HINTS[archetype] || "Подберите подход") : "Влияйте через правильные техники."}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
