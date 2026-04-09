"use client";

import { motion, AnimatePresence } from "framer-motion";
import { ShieldAlert, ShieldCheck, ShieldQuestion } from "lucide-react";

/**
 * TrapNotification — real-time feedback when manager hits/dodges a trap.
 *
 * Color design system:
 * - FELL (red):    neon-red glow + shield-alert icon — manager fell for the trap
 * - DODGED (green): neon-green glow + shield-check icon — manager navigated correctly
 * - PARTIAL (amber): warning glow + shield-question icon — mixed response
 *
 * Animation: slides up from bottom, pulses glow, auto-dismisses after 4s.
 * During session, the notification should NOT be obstructive — small toast at bottom-right.
 */

export interface TrapEvent {
  trap_name: string;
  category: "legal" | "emotional" | "manipulative";
  status: "fell" | "dodged" | "partial";
  score_delta: number;
  wrong_keywords: string[];
  correct_keywords: string[];
  client_phrase: string;
  correct_example: string;
}

const STATUS_CONFIG = {
  fell: {
    icon: ShieldAlert,
    label: "ЛОВУШКА",
    color: "var(--danger)",
    glow: "rgba(255,42,109,0.25)",
    border: "rgba(255,42,109,0.4)",
    bg: "rgba(255,42,109,0.08)",
    message: "Вы попались в ловушку",
  },
  dodged: {
    icon: ShieldCheck,
    label: "ОБХОД",
    color: "var(--success)",
    glow: "rgba(0,255,148,0.25)",
    border: "rgba(0,255,148,0.4)",
    bg: "rgba(0,255,148,0.08)",
    message: "Ловушка обойдена",
  },
  partial: {
    icon: ShieldQuestion,
    label: "ЧАСТИЧНО",
    color: "var(--warning)",
    glow: "rgba(255,215,0,0.25)",
    border: "rgba(255,215,0,0.4)",
    bg: "rgba(255,215,0,0.08)",
    message: "Неоднозначный ответ",
  },
} as const;

const CATEGORY_LABELS: Record<string, string> = {
  legal: "Юридическая",
  emotional: "Эмоциональная",
  manipulative: "Манипулятивная",
};

interface TrapNotificationProps {
  event: TrapEvent | null;
  onDismiss: () => void;
}

export function TrapNotification({ event, onDismiss }: TrapNotificationProps) {
  if (!event) return null;

  const config = STATUS_CONFIG[event.status] || STATUS_CONFIG.partial;
  const Icon = config.icon;
  const delta = event.score_delta;
  const deltaStr = delta > 0 ? `+${delta}` : `${delta}`;

  return (
    <AnimatePresence>
      {event && (
        <motion.div
          initial={{ opacity: 0, y: 40, scale: 0.95 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 20, scale: 0.95 }}
          transition={{ type: "spring", stiffness: 400, damping: 25 }}
          className="fixed bottom-6 right-6 z-[160] max-w-sm cursor-pointer"
          onClick={onDismiss}
        >
          <motion.div
            className="rounded-xl p-4 backdrop-blur-xl"
            style={{
              background: config.bg,
              border: `1px solid ${config.border}`,
              boxShadow: `0 0 30px ${config.glow}, inset 0 0 20px ${config.glow}`,
            }}
            animate={{
              boxShadow: [
                `0 0 30px ${config.glow}, inset 0 0 20px ${config.glow}`,
                `0 0 50px ${config.glow}, inset 0 0 30px ${config.glow}`,
                `0 0 30px ${config.glow}, inset 0 0 20px ${config.glow}`,
              ],
            }}
            transition={{ duration: 2, repeat: 1, ease: "easeInOut" }}
          >
            {/* Header row */}
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <motion.div
                  animate={{ rotate: event.status === "fell" ? [0, -10, 10, 0] : [0, 5, -5, 0] }}
                  transition={{ duration: 0.5 }}
                >
                  <Icon size={20} color={config.color} />
                </motion.div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold uppercase tracking-wide" style={{ color: config.color }}>
                      {config.label}
                    </span>
                    <span className="text-xs font-medium px-1.5 py-0.5 rounded"
                      style={{ background: "rgba(255,255,255,0.05)", color: "var(--text-muted)" }}>
                      {CATEGORY_LABELS[event.category] || event.category}
                    </span>
                  </div>
                  <div className="text-xs mt-0.5" style={{ color: "var(--text-secondary)" }}>
                    {event.trap_name}
                  </div>
                </div>
              </div>

              {/* Score delta */}
              <motion.div
                className="font-display text-xl font-bold"
                style={{ color: config.color }}
                initial={{ scale: 1.5 }}
                animate={{ scale: 1 }}
                transition={{ type: "spring", stiffness: 300 }}
              >
                {deltaStr}
              </motion.div>
            </div>

            {/* Message */}
            <div className="mt-2 text-xs" style={{ color: "var(--text-muted)" }}>
              {config.message}
            </div>

            {/* Auto-dismiss progress bar */}
            <motion.div
              className="mt-3 h-0.5 rounded-full"
              style={{ background: config.color, opacity: 0.3 }}
              initial={{ width: "100%" }}
              animate={{ width: "0%" }}
              transition={{ duration: 4, ease: "linear" }}
              onAnimationComplete={onDismiss}
            />
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/**
 * TrapSummaryBadge — small badge shown in the stats panel during session.
 * Shows accumulated trap score.
 */
interface TrapSummaryBadgeProps {
  fell: number;
  dodged: number;
  netScore: number;
}

export function TrapSummaryBadge({ fell, dodged, netScore }: TrapSummaryBadgeProps) {
  if (fell === 0 && dodged === 0) return null;

  const color = netScore >= 0 ? "var(--success)" : "var(--danger)";
  const deltaStr = netScore > 0 ? `+${netScore}` : `${netScore}`;

  return (
    <div
      className="rounded-xl p-4"
      style={{
        background: "var(--glass-bg)",
        border: "1px solid var(--glass-border)",
        backdropFilter: "blur(20px)",
      }}
    >
      <div className="text-xs font-semibold uppercase tracking-wide mb-2" style={{ color: "var(--text-muted)" }}>
        TRAP SCORE
      </div>
      <div className="flex items-baseline gap-2">
        <span className="text-2xl font-bold font-display" style={{ color }}>
          {deltaStr}
        </span>
        <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>pts</span>
      </div>
      <div className="mt-2 flex gap-3 text-xs font-mono">
        <span style={{ color: "var(--danger)" }}>
          <ShieldAlert size={10} className="inline mr-1" />{fell}
        </span>
        <span style={{ color: "var(--success)" }}>
          <ShieldCheck size={10} className="inline mr-1" />{dodged}
        </span>
      </div>
    </div>
  );
}
