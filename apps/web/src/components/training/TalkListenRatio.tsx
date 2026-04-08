"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Mic, Headphones } from "lucide-react";

interface TalkListenRatioProps {
  talkPercent: number;
}

function getTalkColor(pct: number): string {
  if (pct <= 40) return "var(--neon-green, #00FF94)";
  if (pct <= 60) return "var(--neon-amber, #FFD700)";
  return "var(--neon-red, #FF2A6D)";
}

export default function TalkListenRatio({ talkPercent }: TalkListenRatioProps) {
  const listenPercent = 100 - talkPercent;
  const talkColor = getTalkColor(talkPercent);
  const [hovered, setHovered] = useState(false);

  return (
    <div
      className="flex flex-col relative"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div className="text-sm font-semibold uppercase tracking-wide mb-2.5" style={{ color: "var(--text-secondary)" }}>
        Говорю / Слушаю
      </div>
      <div className="flex items-center gap-3 text-base font-bold tabular-nums">
        <Mic size={15} style={{ color: talkColor }} />
        <span style={{ color: talkColor }}>{talkPercent}%</span>
        <span style={{ color: "var(--text-muted)" }}>/</span>
        <Headphones size={15} style={{ color: "var(--accent)" }} />
        <span style={{ color: "var(--accent)" }}>{listenPercent}%</span>
      </div>
      <div className="flex h-2 mt-3 rounded-full overflow-hidden" style={{ background: "var(--input-bg)" }}>
        <motion.div
          className="h-full rounded-l-full"
          style={{ background: talkColor }}
          animate={{ width: `${talkPercent}%` }}
          transition={{ duration: 0.8 }}
        />
        <motion.div
          className="h-full rounded-r-full"
          style={{ background: "var(--accent)" }}
          animate={{ width: `${listenPercent}%` }}
          transition={{ duration: 0.8 }}
        />
      </div>

      {/* Hover tooltip */}
      <AnimatePresence>
        {hovered && (
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 4 }}
            className="absolute bottom-full left-0 right-0 mb-1 rounded-lg p-3 text-xs z-10 leading-relaxed"
            style={{
              background: "var(--bg-secondary)",
              border: "1px solid var(--border-color)",
              color: "var(--text-secondary)",
            }}
          >
            Оптимально: говорить &lt;40%, слушать &gt;60%.
            Зелёный — хорошо, жёлтый — норма, красный — много говорите.
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
