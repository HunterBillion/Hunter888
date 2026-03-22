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
      className="rounded-xl p-4 relative"
      style={{
        background: "var(--glass-bg)",
        border: "1px solid var(--glass-border)",
        backdropFilter: "blur(20px)",
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div className="font-mono text-[10px] uppercase tracking-wider mb-2" style={{ color: "var(--text-muted)" }}>
        Говорю / Слушаю
      </div>
      <div className="flex items-center gap-2 font-mono text-sm">
        <Mic size={12} style={{ color: talkColor }} />
        <span style={{ color: talkColor }}>{talkPercent}%</span>
        <span style={{ color: "var(--text-muted)" }}>/</span>
        <Headphones size={12} style={{ color: "var(--accent)" }} />
        <span style={{ color: "var(--accent)" }}>{listenPercent}%</span>
      </div>
      <div className="flex h-1.5 mt-2 rounded-full overflow-hidden" style={{ background: "var(--input-bg)" }}>
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
            className="absolute bottom-full left-0 right-0 mb-1 rounded-lg p-2 text-[10px] font-mono z-10"
            style={{
              background: "var(--bg-secondary)",
              border: "1px solid var(--border-color)",
              color: "var(--text-muted)",
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
