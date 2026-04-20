"use client";

/**
 * QuizThinkingIndicator — rotating arcade-style "loading" messages + time-aware
 * stage progression so users perceive progress during slow LLM calls.
 *
 * 2026-04-18 streaming-v1: instead of true token-streaming (requires backend
 * refactor), we simulate "streaming feel" with staged messages:
 *   0-3s  → quick rotation of short probes ("ИЩУ В КОДЕКСЕ…")
 *   3-8s  → longer "ещё работаю" messages
 *   8-15s → "Почти готово, ещё чуть-чуть" + fast dot pulse
 *   15s+  → "Извините, модель сегодня медленная — ответ вот-вот будет"
 *
 * Matches what user said they need: "нет чувство — да никаких кроме плохо
 * чувства не дает". Now user sees active narrative instead of dead wait.
 */

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Brain, Loader2 } from "lucide-react";

// Stage 1: fast rotation (0-3s)
const QUICK = [
  "ИЩУ В КОДЕКСЕ…",
  "АНАЛИЗИРУЮ ОТВЕТ…",
  "СВЕРЯЮ С 127-ФЗ…",
  "ПРОВЕРЯЮ ПРАКТИКУ…",
];
// Stage 2: longer probes (3-8s)
const MEDIUM = [
  "СОБИРАЮ АРГУМЕНТЫ…",
  "ЧИТАЮ ПЛЕНУМ ВС РФ…",
  "ВЗВЕШИВАЮ ОТВЕТ…",
  "ФОРМУЛИРУЮ РАЗБОР…",
];
// Stage 3: reassurance (8-15s)
const SLOW = [
  "ЕЩЁ НЕМНОГО…",
  "ПОЧТИ ГОТОВО…",
  "ЗАКАНЧИВАЮ…",
];
// Stage 4: long-wait apology (15s+)
const VERY_SLOW = "МОДЕЛЬ СЕГОДНЯ МЕДЛЕННАЯ — ОТВЕТ ВОТ-ВОТ БУДЕТ";

export function QuizThinkingIndicator() {
  const [elapsed, setElapsed] = useState(0); // milliseconds
  const [idx, setIdx] = useState(0);

  useEffect(() => {
    const start = Date.now();
    const t = setInterval(() => {
      setElapsed(Date.now() - start);
      setIdx((i) => i + 1);
    }, 1400);
    return () => clearInterval(t);
  }, []);

  // Pick pool by elapsed time
  let pool: string[];
  let accent = "var(--accent)";
  if (elapsed < 3000) { pool = QUICK; }
  else if (elapsed < 8000) { pool = MEDIUM; }
  else if (elapsed < 15000) { pool = SLOW; accent = "var(--warning)"; }
  else { pool = [VERY_SLOW]; accent = "var(--warning)"; }
  const message = pool[idx % pool.length];

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      className="flex items-start gap-3"
    >
      <div
        className="flex shrink-0 items-center justify-center font-pixel"
        style={{
          width: 44, height: 44,
          background: "var(--accent-muted)",
          border: `2px solid ${accent}`,
          borderRadius: 0,
          boxShadow: `2px 2px 0 0 ${accent}`,
        }}
      >
        {elapsed < 8000 ? (
          <motion.div
            animate={{ rotate: [0, -10, 10, -10, 10, 0] }}
            transition={{ duration: 2.2, repeat: Infinity, ease: "easeInOut" }}
          >
            <Brain size={18} style={{ color: accent }} />
          </motion.div>
        ) : (
          <Loader2 size={18} className="animate-spin" style={{ color: accent }} />
        )}
      </div>
      <div
        className="px-5 py-3.5"
        style={{
          background: "var(--bg-panel)",
          border: `2px solid ${accent}`,
          borderRadius: 0,
          boxShadow: `2px 2px 0 0 var(--accent-muted)`,
          minWidth: 240,
        }}
      >
        <div className="flex gap-2 items-center font-pixel uppercase tracking-widest" style={{ color: accent, fontSize: 13 }}>
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
          <span className="inline-flex gap-0.5 items-center">
            {[0, 1, 2].map((i) => (
              <motion.span
                key={i}
                style={{ display: "inline-block", width: 4, height: 4, background: "var(--accent)", borderRadius: 0 }}
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
