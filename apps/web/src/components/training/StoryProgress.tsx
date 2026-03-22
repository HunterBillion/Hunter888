"use client";

import { motion } from "framer-motion";
import { Phone } from "lucide-react";

interface Props {
  callNumber: number;
  totalCalls: number;
}

export function StoryProgress({ callNumber, totalCalls }: Props) {
  if (totalCalls <= 1) return null;

  const progress = totalCalls > 0 ? (callNumber / totalCalls) * 100 : 0;

  return (
    <div
      className="flex items-center gap-3 rounded-xl px-4 py-2"
      style={{
        background: "var(--glass-bg)",
        border: "1px solid var(--glass-border)",
        backdropFilter: "blur(12px)",
      }}
    >
      <Phone size={13} style={{ color: "var(--accent)" }} />
      <span className="font-mono text-[11px] tracking-wider" style={{ color: "var(--text-secondary)" }}>
        ЗВОНОК <span style={{ color: "var(--accent)", fontWeight: 700 }}>{callNumber}</span>
        <span style={{ color: "var(--text-muted)" }}> / {totalCalls}</span>
      </span>
      <div className="flex-1 h-1.5 rounded-full" style={{ background: "var(--input-bg)" }}>
        <motion.div
          className="h-full rounded-full"
          style={{ background: "var(--accent)" }}
          animate={{ width: `${progress}%` }}
          transition={{ duration: 0.5 }}
        />
      </div>
    </div>
  );
}
