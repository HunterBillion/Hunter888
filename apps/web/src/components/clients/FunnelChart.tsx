"use client";

import { motion } from "framer-motion";
import { ArrowDown, TrendingDown } from "lucide-react";
import type { ClientStatus } from "@/types";
import { CLIENT_STATUS_COLORS, CLIENT_STATUS_LABELS } from "@/types";

/**
 * FunnelChart — horizontal sales funnel with conversion-rate bars.
 *
 * Replaces the heavy ForceGraph / network visualization that showed
 * status-to-status links without actionable insights.
 *
 * Shows only the "primary path" (new → contacted → ... → completed),
 * with branches (lost / paused / consent_revoked) as an outflow summary.
 * Each step has a bar proportional to the widest step, count, and
 * conversion % from the previous step.
 */

const PRIMARY_PATH: ClientStatus[] = [
  "new",
  "contacted",
  "interested",
  "consultation",
  "thinking",
  "consent_given",
  "contract_signed",
  "in_process",
  "completed",
];

const BRANCH_STATUSES: ClientStatus[] = ["lost", "consent_revoked", "paused"];

interface FunnelChartProps {
  statusCounts: Partial<Record<ClientStatus, number>>;
  selectedStage?: ClientStatus;
  onSelectStage?: (stage: ClientStatus) => void;
}

export function FunnelChart({ statusCounts, selectedStage, onSelectStage }: FunnelChartProps) {
  const getCount = (s: ClientStatus) => statusCounts[s] ?? 0;
  const primaryCounts = PRIMARY_PATH.map(getCount);
  const maxCount = Math.max(...primaryCounts, 1);
  const topCount = primaryCounts[0] || 1;

  // Conversion from stage-1 to current stage (survival rate)
  const conversionFromTop = (count: number) =>
    topCount > 0 ? Math.round((count / topCount) * 100) : 0;

  // Step-to-step conversion (how many moved from previous)
  const stepConversion = (idx: number) => {
    if (idx === 0) return null;
    const prev = primaryCounts[idx - 1];
    const cur = primaryCounts[idx];
    if (prev === 0) return null;
    return Math.round((cur / prev) * 100);
  };

  const totalBranch = BRANCH_STATUSES.reduce((s, st) => s + getCount(st), 0);

  return (
    <div className="space-y-3">
      {/* Primary funnel */}
      <div className="space-y-2">
        {PRIMARY_PATH.map((status, idx) => {
          const count = primaryCounts[idx];
          const pctOfMax = maxCount > 0 ? (count / maxCount) * 100 : 0;
          const pctOfTop = conversionFromTop(count);
          const stepPct = stepConversion(idx);
          const isActive = selectedStage === status;
          const color = CLIENT_STATUS_COLORS[status];
          const label = CLIENT_STATUS_LABELS[status];
          const dropPct = stepPct !== null && stepPct < 100 ? 100 - stepPct : null;

          return (
            <motion.div
              key={status}
              initial={{ opacity: 0, x: -12 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: idx * 0.04 }}
            >
              {/* Drop indicator between steps */}
              {idx > 0 && dropPct !== null && dropPct > 0 && (
                <div className="flex items-center gap-2 pl-3 py-1 text-xs" style={{ color: "var(--text-muted)" }}>
                  <TrendingDown size={11} style={{ color: "var(--danger, #ef4444)" }} />
                  <span>
                    Отток {dropPct}% · перешло {stepPct}%
                  </span>
                  <div className="flex-1 h-px" style={{ background: "var(--border-color)" }} />
                </div>
              )}

              <button
                type="button"
                onClick={() => onSelectStage?.(status)}
                className="w-full text-left glass-panel p-3 transition-all hover:opacity-95"
                style={{
                  borderLeft: `3px solid ${isActive ? color : "transparent"}`,
                  background: isActive
                    ? `color-mix(in srgb, ${color} 8%, var(--input-bg))`
                    : undefined,
                }}
              >
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-2 min-w-0">
                    <div
                      className="w-2 h-2 rounded-full shrink-0"
                      style={{
                        background: color,
                        boxShadow: `0 0 8px color-mix(in srgb, ${color} 50%, transparent)`,
                      }}
                    />
                    <span
                      className="font-mono text-xs uppercase tracking-wider truncate"
                      style={{ color: "var(--text-primary)" }}
                    >
                      {label}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 shrink-0 text-xs font-mono">
                    <span style={{ color: "var(--text-muted)" }}>{pctOfTop}%</span>
                    <span
                      className="font-bold tabular-nums"
                      style={{ color: count > 0 ? "var(--text-primary)" : "var(--text-muted)" }}
                    >
                      {count}
                    </span>
                  </div>
                </div>

                {/* Proportional bar */}
                <div className="h-2 rounded-full overflow-hidden" style={{ background: "var(--input-bg)" }}>
                  <motion.div
                    className="h-full rounded-full"
                    initial={{ width: 0 }}
                    animate={{ width: `${pctOfMax}%` }}
                    transition={{ duration: 0.6, delay: idx * 0.04, ease: "easeOut" }}
                    style={{
                      background: `linear-gradient(90deg, ${color}, color-mix(in srgb, ${color} 60%, transparent))`,
                      boxShadow: count > 0 ? `0 0 8px color-mix(in srgb, ${color} 40%, transparent)` : undefined,
                    }}
                  />
                </div>
              </button>
            </motion.div>
          );
        })}
      </div>

      {/* Branch outflow summary */}
      {totalBranch > 0 && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.4 }}
          className="pt-3 border-t"
          style={{ borderColor: "var(--border-color)" }}
        >
          <div
            className="text-[10px] font-semibold uppercase tracking-widest mb-2 flex items-center gap-2"
            style={{ color: "var(--text-muted)" }}
          >
            <ArrowDown size={10} /> Оттоки и паузы
          </div>
          <div className="grid grid-cols-3 gap-2">
            {BRANCH_STATUSES.map((status) => {
              const count = getCount(status);
              const pct = topCount > 0 ? Math.round((count / topCount) * 100) : 0;
              const isActive = selectedStage === status;
              const color = CLIENT_STATUS_COLORS[status];
              return (
                <button
                  key={status}
                  type="button"
                  onClick={() => onSelectStage?.(status)}
                  className="text-left glass-panel p-2.5 transition-all hover:opacity-95"
                  style={{
                    borderLeft: `3px solid ${isActive ? color : "transparent"}`,
                    opacity: count === 0 ? 0.5 : 1,
                  }}
                >
                  <div className="flex items-center gap-1.5 mb-1">
                    <div className="w-1.5 h-1.5 rounded-full" style={{ background: color }} />
                    <span className="font-mono text-[10px] uppercase tracking-wider truncate" style={{ color: "var(--text-primary)" }}>
                      {CLIENT_STATUS_LABELS[status]}
                    </span>
                  </div>
                  <div className="flex items-baseline gap-1.5">
                    <span className="font-mono font-bold text-sm tabular-nums" style={{ color: count > 0 ? color : "var(--text-muted)" }}>
                      {count}
                    </span>
                    <span className="text-[10px]" style={{ color: "var(--text-muted)" }}>
                      · {pct}%
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        </motion.div>
      )}
    </div>
  );
}
