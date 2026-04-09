"use client";

import { useState } from "react";
import { useSessionStore } from "@/stores/useSessionStore";
import { AppIcon } from "@/components/ui/AppIcon";

const STATUS_CONFIG = {
  fell: { icon: "\u274C", color: "var(--danger)", label: "Fell" },
  dodged: { icon: "\u2705", color: "var(--success)", label: "Dodge" },
  partial: { icon: "\u26A0\uFE0F", color: "var(--warning, #f59e0b)", label: "Partial" },
} as const;

const CATEGORY_LABELS: Record<string, string> = {
  legal: "Юридическая",
  emotional: "Эмоциональная",
  manipulative: "Манипулятивная",
  expert: "Экспертная",
  price: "Ценовая",
  provocative: "Провокация",
  professional: "Профессиональная",
  procedural: "Процедурная",
};

export default function TrapLog() {
  const trapHistory = useSessionStore((s) => s.trapHistory);
  const trapNetScore = useSessionStore((s) => s.trapNetScore);
  const [expanded, setExpanded] = useState(false);

  if (trapHistory.length === 0) return null;

  return (
    <div className="flex flex-col">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between text-left"
      >
        <span className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--text-secondary)" }}>
          Ловушки ({trapHistory.length})
        </span>
        <div className="flex items-center gap-2.5">
          <span
            className="text-sm font-mono font-bold"
            style={{ color: trapNetScore >= 0 ? "var(--success)" : "var(--danger)" }}
          >
            {trapNetScore >= 0 ? "+" : ""}{trapNetScore}
          </span>
          <span className="text-xs" style={{ color: "var(--text-muted)" }}>
            {expanded ? "\u25B2" : "\u25BC"}
          </span>
        </div>
      </button>

      {expanded && (
        <div className="mt-3 space-y-2 max-h-40 overflow-y-auto">
          {trapHistory.map((trap, i) => {
            const cfg = STATUS_CONFIG[trap.status as keyof typeof STATUS_CONFIG] || STATUS_CONFIG.partial;
            return (
              <div key={i} className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-2 min-w-0">
                  <AppIcon emoji={cfg.icon} size={14} />
                  <span className="truncate" style={{ color: "var(--text-primary)" }}>
                    {CATEGORY_LABELS[trap.category] || trap.category}: {trap.trap_name}
                  </span>
                </div>
                <span className="font-mono font-bold shrink-0 ml-2" style={{ color: cfg.color }}>
                  {trap.score_delta >= 0 ? "+" : ""}{trap.score_delta}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
