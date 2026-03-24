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
      className="rounded-xl p-5 flex flex-col relative overflow-hidden"
      style={{
        background: "var(--glass-bg)",
        border: "1px solid var(--glass-border)",
        borderRight: "2px solid var(--glass-border)",
        backdropFilter: "blur(20px)",
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <h3 className="font-display tracking-widest text-sm flex justify-between items-center w-full mb-4" style={{ color: "var(--text-secondary)" }}>
        <span>VIBE METER</span>
        <Activity size={16} style={{ color: "var(--accent)" }} />
      </h3>

      <div className="flex justify-center py-2 relative">
        {/* Labels on left — 10-state scale (top=deal, bottom=hostile) */}
        <div className="absolute left-0 top-2 bottom-2 flex flex-col justify-between items-end pr-3 border-r font-mono text-[9px] leading-tight" style={{ borderColor: "var(--border-color)" }}>
          <span className="font-bold" style={{ color: EMOTION_MAP.deal.color }}>{EMOTION_MAP.deal.labelRu}</span>
          <span style={{ color: EMOTION_MAP.negotiating.color }}>{EMOTION_MAP.negotiating.labelRu}</span>
          <span style={{ color: EMOTION_MAP.considering.color }}>{EMOTION_MAP.considering.labelRu}</span>
          <span style={{ color: EMOTION_MAP.curious.color }}>{EMOTION_MAP.curious.labelRu}</span>
          <span style={{ color: EMOTION_MAP.testing.color }}>{EMOTION_MAP.testing.labelRu}</span>
          <span style={{ color: EMOTION_MAP.guarded.color }}>{EMOTION_MAP.guarded.labelRu}</span>
          <span style={{ color: EMOTION_MAP.cold.color }}>{EMOTION_MAP.cold.labelRu}</span>
          <span style={{ color: EMOTION_MAP.hostile.color }}>{EMOTION_MAP.hostile.labelRu}</span>
        </div>

        {/* Thermometer tube */}
        <div
          className="w-14 h-40 rounded-full border relative overflow-hidden ml-16"
          style={{
            background: "var(--input-bg)",
            borderColor: "var(--border-color)",
            boxShadow: "inset 0 4px 20px var(--shadow-sm)",
          }}
        >
          {/* Grid lines */}
          <div className="absolute inset-0 flex flex-col justify-between py-2 pointer-events-none opacity-20">
            {[0, 1, 2, 3, 4, 5, 6].map((i) => (
              <div key={i} className="w-full h-px bg-white" />
            ))}
          </div>

          {/* Fill */}
          <motion.div
            className="absolute bottom-0 left-0 w-full"
            style={{
              background: `linear-gradient(to top, ${EMOTION_MAP.hostile.color}, ${EMOTION_MAP.cold.color}, ${EMOTION_MAP.guarded.color}, ${EMOTION_MAP.curious.color}, ${EMOTION_MAP.considering.color}, ${EMOTION_MAP.negotiating.color}, ${EMOTION_MAP.deal.color})`,
              boxShadow: `0 0 20px ${config.glow}`,
            }}
            animate={{ height: fillPercent }}
            transition={{ duration: 1.5, ease: "easeOut" }}
          >
            <div className="absolute top-0 w-full h-2 bg-white/30 blur-[2px] rounded-t-full" />
          </motion.div>
        </div>
      </div>

      {/* Current state label with pulse-glow on change */}
      <AnimatePresence mode="wait">
        <motion.div
          className="mt-3 text-center font-mono text-xs font-bold tracking-widest"
          style={{ color: config.color, textShadow: `0 0 10px ${config.glow}` }}
          key={emotion}
          initial={{ opacity: 0, y: 5, scale: 1.15 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: -5 }}
          transition={{ duration: 0.4 }}
        >
          {/* Pulse ring on emotion change */}
          <motion.span
            className="inline-block"
            animate={reducedMotion ? {} : {
              textShadow: [
                `0 0 10px ${config.glow}`,
                `0 0 25px ${config.glow}`,
                `0 0 10px ${config.glow}`,
              ],
            }}
            transition={reducedMotion ? {} : { duration: 1.5, ease: "easeInOut" }}
          >
            {config.labelRu}
          </motion.span>
        </motion.div>
      </AnimatePresence>

      {/* Archetype hint — e.g. "Скептик: нужны факты и цифры" */}
      {archetype && (
        <div
          className="mt-2 text-center text-[10px] font-mono truncate"
          style={{ color: "var(--text-muted)" }}
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
            className="absolute bottom-2 left-2 right-2 rounded-lg p-2 text-[10px] font-mono z-10"
            style={{
              background: "var(--bg-secondary)",
              border: "1px solid var(--border-color)",
              color: "var(--text-muted)",
            }}
          >
            Эмоция клиента: {config.labelRu}.{" "}
            {archetype ? (ARCHETYPE_HINTS[archetype] || "Подберите подход") : "Влияйте через правильные техники продаж."}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
