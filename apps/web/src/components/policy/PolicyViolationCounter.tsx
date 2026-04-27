"use client";

/**
 * PolicyViolationCounter — TZ-4 §10 / §13.4.1 sidebar badge.
 *
 * Renders a per-session counter of
 * ``conversation.policy_violation_detected`` events grouped by
 * severity. In warn-only mode (D5 default) clicks open a
 * read-only drawer; in enforce mode (D7) ``critical`` violations
 * already blocked their replies upstream — the badge is then a
 * post-hoc audit signal.
 *
 * Wiring (planned):
 *   * The call/page.tsx hook subscribes to the WS event
 *     ``conversation.policy_violation_detected`` and bumps the
 *     ``severityCounts`` map via the parent's reducer.
 *   * For D6 this component ships as a pure presentation primitive —
 *     no live subscription yet, so the call-page can pre-flight the
 *     visual placement and the D7 cutover wires the event source.
 */

import { motion } from "framer-motion";
import { AlertTriangle, Bell } from "lucide-react";

export type PolicySeverity = "low" | "medium" | "high" | "critical";

const SEVERITY_TONES: Record<PolicySeverity, { background: string; color: string }> = {
  low: {
    background: "color-mix(in srgb, var(--text-muted) 18%, transparent)",
    color: "var(--text-muted)",
  },
  medium: {
    background: "color-mix(in srgb, var(--info) 18%, transparent)",
    color: "var(--info)",
  },
  high: {
    background: "color-mix(in srgb, var(--warning) 18%, transparent)",
    color: "var(--warning)",
  },
  critical: {
    background: "color-mix(in srgb, var(--danger) 18%, transparent)",
    color: "var(--danger)",
  },
};

interface PolicyViolationCounterProps {
  /** Per-severity counts. Pass zeros for severities you haven't
   * observed — the component hides them automatically. */
  severityCounts: Partial<Record<PolicySeverity, number>>;
  /** Whether the engine is in enforce mode (controls the chip's
   * default tone — warn-only stays muted, enforce flips louder). */
  enforceActive?: boolean;
  /** Optional click handler — opens the drawer/log. */
  onClick?: () => void;
}

export function PolicyViolationCounter({
  severityCounts,
  enforceActive = false,
  onClick,
}: PolicyViolationCounterProps) {
  const total = (Object.values(severityCounts).filter(Boolean) as number[]).reduce(
    (a, b) => a + b,
    0,
  );
  if (total === 0) return null;

  const ordered: PolicySeverity[] = ["critical", "high", "medium", "low"];
  const present = ordered.filter((sev) => (severityCounts[sev] ?? 0) > 0);

  const Wrapper = onClick ? motion.button : motion.div;

  return (
    <Wrapper
      onClick={onClick}
      type={onClick ? "button" : undefined}
      whileTap={onClick ? { scale: 0.96 } : undefined}
      title={
        enforceActive
          ? "Полиси-движок в enforce-режиме: critical нарушения блокируют сообщения"
          : "Полиси-движок в warn-only — нарушения логируются, сообщения проходят"
      }
      className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[11px]"
      style={{
        background: enforceActive
          ? "color-mix(in srgb, var(--danger) 12%, transparent)"
          : "var(--input-bg)",
        border: `1px solid ${
          enforceActive
            ? "color-mix(in srgb, var(--danger) 35%, transparent)"
            : "var(--border-color)"
        }`,
        color: "var(--text-muted)",
        cursor: onClick ? "pointer" : "default",
      }}
    >
      {enforceActive ? <AlertTriangle size={11} /> : <Bell size={11} />}
      <span style={{ color: "var(--text-secondary)" }}>Полиси:</span>
      {present.map((sev) => (
        <span
          key={sev}
          className="inline-flex items-center rounded px-1 font-mono"
          style={SEVERITY_TONES[sev]}
          title={`${severityCounts[sev]} ${sev}`}
        >
          {severityCounts[sev]}
          <span className="ml-0.5 opacity-60">{sev[0]}</span>
        </span>
      ))}
    </Wrapper>
  );
}
