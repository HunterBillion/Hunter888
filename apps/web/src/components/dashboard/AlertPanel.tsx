"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Bell, AlertTriangle, Trophy, TrendingDown, UserX, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";

interface Alert {
  type: "inactive" | "record" | "skill_drop" | "overdue";
  manager_id: string;
  manager_name: string;
  message: string;
  severity: "critical" | "warning" | "success" | "info";
  created_at: string;
  value: number;
}

const SEVERITY_COLORS: Record<string, { bg: string; border: string; icon: string }> = {
  critical: { bg: "rgba(239, 68, 68, 0.1)", border: "rgba(239, 68, 68, 0.3)", icon: "var(--danger)" },
  warning: { bg: "rgba(249, 115, 22, 0.1)", border: "rgba(249, 115, 22, 0.3)", icon: "var(--warning)" },
  success: { bg: "rgba(34, 197, 94, 0.1)", border: "rgba(34, 197, 94, 0.3)", icon: "var(--success)" },
  info: { bg: "rgba(59, 130, 246, 0.1)", border: "rgba(59, 130, 246, 0.3)", icon: "var(--info)" },
};

const TYPE_ICONS: Record<string, typeof Bell> = {
  inactive: UserX,
  record: Trophy,
  skill_drop: TrendingDown,
  overdue: AlertTriangle,
};

interface AlertPanelProps {
  compact?: boolean;
}

export function AlertPanel({ compact = false }: AlertPanelProps) {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    api.get("/dashboard/rop/alerts")
      .then((res: { alerts: Alert[]; total: number }) => setAlerts(res.alerts || []))
      .catch((err) => logger.error("[AlertPanel] Failed to load alerts:", err))
      .finally(() => setLoading(false));
  }, []);

  const criticalCount = alerts.filter((a) => a.severity === "critical" || a.severity === "warning").length;
  const filteredAlerts = compact
    ? alerts.filter((a) => a.severity === "critical" || a.severity === "warning").slice(0, 3)
    : alerts;
  const displayed = compact ? filteredAlerts : expanded ? alerts : alerts.slice(0, 3);

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.2 }}
      className="glass-panel rounded-xl p-5"
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Bell size={16} style={{ color: "var(--accent)" }} />
          <span className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
            Алерты
          </span>
          {criticalCount > 0 && (
            <span
              className="px-1.5 py-0.5 rounded-full text-xs font-mono font-bold"
              style={{ background: "rgba(239, 68, 68, 0.2)", color: "var(--danger)" }}
            >
              {criticalCount}
            </span>
          )}
        </div>
        <span className="text-xs font-medium" style={{ color: "var(--text-muted)" }}>
          {alerts.length} всего
        </span>
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-16">
          <Loader2 size={16} className="animate-spin" style={{ color: "var(--accent)" }} />
        </div>
      ) : alerts.length === 0 ? (
        <div className="text-xs py-3 text-center" style={{ color: "var(--text-muted)" }}>
          Нет активных алертов
        </div>
      ) : (
        <>
          <div className="space-y-2">
            <AnimatePresence>
              {displayed.map((alert, i) => {
                const colors = SEVERITY_COLORS[alert.severity] || SEVERITY_COLORS.info;
                const Icon = TYPE_ICONS[alert.type] || Bell;

                return (
                  <motion.div
                    key={`${alert.type}-${alert.manager_id}-${i}`}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0 }}
                    transition={{ delay: i * 0.05 }}
                    className="flex items-start gap-2 rounded-lg px-3 py-2"
                    style={{ background: colors.bg, border: `1px solid ${colors.border}` }}
                  >
                    <Icon size={14} style={{ color: colors.icon, marginTop: 1, flexShrink: 0 }} />
                    <div className="flex-1 min-w-0">
                      <div className="text-xs font-medium truncate" style={{ color: "var(--text-primary)" }}>
                        {alert.manager_name}
                      </div>
                      <div className="text-xs" style={{ color: "var(--text-secondary)" }}>
                        {alert.message}
                      </div>
                    </div>
                  </motion.div>
                );
              })}
            </AnimatePresence>
          </div>

          {!compact && alerts.length > 3 && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="mt-2 w-full text-center text-xs font-medium uppercase tracking-wide py-1 rounded transition-colors"
              style={{ color: "var(--accent)", background: "rgba(124,106,232,0.08)" }}
            >
              {expanded ? "Свернуть" : `Показать все (${alerts.length})`}
            </button>
          )}
        </>
      )}
    </motion.div>
  );
}
