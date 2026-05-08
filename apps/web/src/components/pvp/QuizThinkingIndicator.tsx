"use client";

/**
 * QuizThinkingIndicator — glass-arena rotating loader with stage-aware
 * messages so users perceive progress during slow LLM calls.
 *
 * Stages (PR-24 redesign):
 *   0-3s  → quick rotation of short probes ("ИЩУ В КОДЕКСЕ…") — accent
 *   3-8s  → longer "ещё работаю" messages — accent
 *   8-15s → "Почти готово" + warning accent + dot pulse
 *   15s+  → "Модель медленная, ответ вот-вот" — danger accent
 *
 * Стиль обновлён под Arcade Stage: glass-card с soft shadow, font-display
 * вместо font-pixel, animated brain-spinner с tilted bob (без NES рамок).
 */

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Brain, Loader2 } from "lucide-react";

const QUICK = [
  "Ищу в кодексе…",
  "Анализирую ответ…",
  "Сверяю с 127-ФЗ…",
  "Проверяю практику…",
];
const MEDIUM = [
  "Собираю аргументы…",
  "Читаю Пленум ВС РФ…",
  "Взвешиваю ответ…",
  "Формулирую разбор…",
];
const SLOW = [
  "Ещё немного…",
  "Почти готово…",
  "Заканчиваю…",
];
const VERY_SLOW = "Модель сегодня медленная — ответ вот-вот";

export function QuizThinkingIndicator() {
  const [elapsed, setElapsed] = useState(0);
  const [idx, setIdx] = useState(0);

  useEffect(() => {
    const start = Date.now();
    const t = setInterval(() => {
      setElapsed(Date.now() - start);
      setIdx((i) => i + 1);
    }, 1400);
    return () => clearInterval(t);
  }, []);

  let pool: string[];
  let accent = "var(--accent)";
  if (elapsed < 3000) { pool = QUICK; }
  else if (elapsed < 8000) { pool = MEDIUM; }
  else if (elapsed < 15000) { pool = SLOW; accent = "var(--warning)"; }
  else { pool = [VERY_SLOW]; accent = "var(--danger)"; }
  const message = pool[idx % pool.length];

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      className="flex items-start gap-3"
    >
      {/* Avatar — glass round with brain or spinner */}
      <div
        className="flex shrink-0 items-center justify-center rounded-xl"
        style={{
          width: 52, height: 52,
          background: `linear-gradient(135deg, color-mix(in srgb, ${accent} 22%, transparent) 0%, color-mix(in srgb, ${accent} 6%, transparent) 100%)`,
          border: `1px solid color-mix(in srgb, ${accent} 45%, transparent)`,
          boxShadow: `0 4px 14px color-mix(in srgb, ${accent} 28%, transparent), inset 0 1px 0 rgba(255,255,255,0.08)`,
          backdropFilter: "blur(20px)",
        }}
      >
        {elapsed < 8000 ? (
          <motion.div
            animate={{ rotate: [0, -10, 10, -10, 10, 0] }}
            transition={{ duration: 2.2, repeat: Infinity, ease: "easeInOut" }}
          >
            <Brain size={22} style={{ color: accent, filter: `drop-shadow(0 0 6px ${accent})` }} />
          </motion.div>
        ) : (
          <Loader2 size={22} className="animate-spin" style={{ color: accent }} />
        )}
      </div>

      {/* Bubble — glass tile */}
      <div
        className="px-5 py-3.5 rounded-2xl"
        style={{
          background: `linear-gradient(135deg, color-mix(in srgb, ${accent} 8%, rgba(255,255,255,0.04)) 0%, rgba(255,255,255,0.02) 100%)`,
          border: `1px solid color-mix(in srgb, ${accent} 28%, transparent)`,
          boxShadow: `0 6px 20px color-mix(in srgb, ${accent} 14%, transparent), inset 0 1px 0 rgba(255,255,255,0.05)`,
          backdropFilter: "blur(20px) saturate(1.2)",
          minWidth: 240,
        }}
      >
        <div
          className="flex gap-2 items-center font-display font-bold uppercase"
          style={{ color: accent, fontSize: 15, letterSpacing: "0.12em" }}
        >
          <motion.span
            key={idx}
            initial={{ opacity: 0, y: 2 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -2 }}
            transition={{ duration: 0.22, ease: "easeOut" }}
            style={{ minWidth: 160 }}
          >
            {message}
          </motion.span>
          <span className="inline-flex gap-0.5 items-center ml-1">
            {[0, 1, 2].map((i) => (
              <motion.span
                key={i}
                className="rounded-full"
                style={{ display: "inline-block", width: 4, height: 4, background: accent, boxShadow: `0 0 4px ${accent}` }}
                animate={{ opacity: [0.2, 1, 0.2] }}
                transition={{ duration: 1, repeat: Infinity, delay: i * 0.18 }}
              />
            ))}
          </span>
        </div>
      </div>
    </motion.div>
  );
}
