"use client";

/**
 * AiQualityPanel — TZ-4 §13.4.1 admin oversight of the conversation
 * policy + persona memory signals.
 *
 * Polls ``GET /admin/ai-quality/summary?days=7`` and renders three
 * blocks:
 *   1. Top-level severity strip + totals card
 *   2. By-manager breakdown (sorted by total descending)
 *   3. Recent feed (last 20 events)
 *
 * Lives inside Методология (not Команда) because the failure modes
 * it surfaces are about *AI behaviour quality* — what the AI client
 * said wrong, what slot it asked twice, when the snapshot drifted —
 * which is the methodologist/RОП craft. Команда стays focused on
 * people-management metrics; this panel does not duplicate that.
 *
 * Refresh strategy: 60s poll + manual refresh button. The
 * NotificationWSProvider already updates per-session counters in
 * `usePolicyStore` for the live call view; this aggregate panel
 * doesn't need real-time push because it's an oversight surface,
 * not a in-flight one.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  AlertTriangle,
  Loader2,
  RefreshCw,
  Shield,
  ShieldAlert,
  Sparkles,
  TrendingUp,
  User as UserIcon,
} from "lucide-react";
import { ApiError, api } from "@/lib/api";
import { sanitizeText } from "@/lib/sanitize";
import { logger } from "@/lib/logger";
import type {
  AiQualityRecentEvent,
  AiQualitySummary,
  AiQualityManagerBreakdown,
} from "@/types";

const POLL_MS = 60_000;
const DEFAULT_WINDOW_DAYS = 7;

const SEVERITY_LABEL: Record<string, string> = {
  critical: "крит",
  high: "выс",
  medium: "сред",
  low: "низ",
};

const SEVERITY_TONE: Record<string, { background: string; color: string }> = {
  critical: {
    background: "color-mix(in srgb, var(--danger) 18%, transparent)",
    color: "var(--danger)",
  },
  high: {
    background: "color-mix(in srgb, var(--warning) 18%, transparent)",
    color: "var(--warning)",
  },
  medium: {
    background: "color-mix(in srgb, var(--info) 18%, transparent)",
    color: "var(--info)",
  },
  low: {
    background: "color-mix(in srgb, var(--text-muted) 18%, transparent)",
    color: "var(--text-muted)",
  },
};

function formatTimestamp(iso: string): string {
  try {
    return new Date(iso).toLocaleString("ru-RU", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function SeverityChips({
  by,
  hideZero = true,
}: {
  by: AiQualitySummary["by_severity"];
  hideZero?: boolean;
}) {
  const order = ["critical", "high", "medium", "low"] as const;
  const items = order.filter((sev) => !hideZero || by[sev] > 0);
  if (!items.length) return null;
  return (
    <div className="inline-flex flex-wrap gap-1.5">
      {items.map((sev) => (
        <span
          key={sev}
          className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-[11px] font-mono"
          style={SEVERITY_TONE[sev]}
        >
          <span className="font-semibold">{by[sev]}</span>
          <span className="opacity-70">{SEVERITY_LABEL[sev]}</span>
        </span>
      ))}
    </div>
  );
}

function TotalCard({
  label,
  value,
  icon: Icon,
  tone = "muted",
}: {
  label: string;
  value: number;
  icon: typeof Shield;
  tone?: "muted" | "warning" | "danger" | "success";
}) {
  const colorMap: Record<string, string> = {
    muted: "var(--text-muted)",
    warning: "var(--warning)",
    danger: "var(--danger)",
    success: "var(--success)",
  };
  return (
    <div
      className="rounded-xl p-4 flex items-start gap-3"
      style={{
        background: "var(--glass-bg)",
        border: "1px solid var(--glass-border)",
      }}
    >
      <Icon size={18} style={{ color: colorMap[tone] }} />
      <div className="min-w-0">
        <div
          className="text-[10px] uppercase tracking-wider"
          style={{ color: "var(--text-muted)" }}
        >
          {label}
        </div>
        <div
          className="mt-1 text-2xl font-mono font-bold"
          style={{ color: "var(--text-primary)" }}
        >
          {value}
        </div>
      </div>
    </div>
  );
}

function ManagerRow({ row }: { row: AiQualityManagerBreakdown }) {
  return (
    <div
      className="rounded-lg p-3 flex items-center justify-between gap-4"
      style={{
        background: "var(--input-bg)",
        border: "1px solid var(--border-color)",
      }}
    >
      <div className="flex items-center gap-2 min-w-0">
        <UserIcon size={14} style={{ color: "var(--text-muted)" }} />
        <span
          className="text-sm truncate"
          style={{ color: "var(--text-primary)" }}
        >
          {sanitizeText(row.manager_name ?? "Неизвестный менеджер")}
        </span>
      </div>
      <div className="flex items-center gap-3">
        <SeverityChips by={row.by_severity} />
        {row.persona_conflicts > 0 && (
          <span
            className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-[11px]"
            style={SEVERITY_TONE.high}
            title={`${row.persona_conflicts} попыток смены идентичности`}
          >
            <ShieldAlert size={11} />
            {row.persona_conflicts}
          </span>
        )}
        <span
          className="text-sm font-mono font-bold"
          style={{ color: "var(--text-secondary)" }}
        >
          {row.total}
        </span>
      </div>
    </div>
  );
}

function RecentRow({ ev }: { ev: AiQualityRecentEvent }) {
  const tone = ev.severity ? SEVERITY_TONE[ev.severity] : SEVERITY_TONE.low;
  return (
    <div
      className="rounded-lg p-2.5 flex items-start gap-3"
      style={{
        background: "var(--input-bg)",
        border: "1px solid var(--border-color)",
      }}
    >
      <span
        className="rounded px-1.5 py-0.5 text-[10px] font-mono shrink-0 mt-0.5"
        style={tone}
      >
        {ev.severity
          ? SEVERITY_LABEL[ev.severity]
          : ev.event_type === "persona.conflict_detected"
            ? "перс"
            : "слот"}
      </span>
      <div className="min-w-0 flex-1">
        <div
          className="text-sm"
          style={{ color: "var(--text-primary)" }}
        >
          {sanitizeText(ev.summary ?? ev.event_type)}
        </div>
        <div
          className="mt-0.5 text-[11px] flex flex-wrap items-center gap-2"
          style={{ color: "var(--text-muted)" }}
        >
          <span>{formatTimestamp(ev.occurred_at)}</span>
          {ev.manager_name && <span>· {sanitizeText(ev.manager_name)}</span>}
          {ev.session_id && (
            <span className="font-mono opacity-70">
              · sess {ev.session_id.slice(0, 8)}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

export function AiQualityPanel() {
  const [summary, setSummary] = useState<AiQualitySummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [windowDays, setWindowDays] = useState<number>(DEFAULT_WINDOW_DAYS);

  const load = useCallback(async () => {
    try {
      const data = await api.get<AiQualitySummary>(
        `/admin/ai-quality/summary?days=${windowDays}&recent_limit=20`,
      );
      setSummary(data);
      setError(null);
    } catch (err) {
      const msg =
        err instanceof ApiError || err instanceof Error
          ? err.message
          : "Не удалось загрузить сводку качества AI";
      logger.error("[AiQualityPanel] fetch failed:", err);
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [windowDays]);

  useEffect(() => {
    void load();
    const id = window.setInterval(() => {
      void load();
    }, POLL_MS);
    return () => window.clearInterval(id);
  }, [load]);

  const isEmpty = useMemo(() => {
    if (!summary) return false;
    return (
      summary.totals.policy_violations === 0 &&
      summary.totals.persona_conflicts === 0
    );
  }, [summary]);

  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.18 }}
      className="space-y-5"
    >
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2
            className="text-lg font-semibold flex items-center gap-2"
            style={{ color: "var(--text-primary)" }}
          >
            <Sparkles size={18} style={{ color: "var(--accent)" }} />
            Качество AI
          </h2>
          <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
            Сводка по нарушениям политики и конфликтам идентичности за
            окно. Полиси-движок работает в warn-only режиме (TZ-4
            §12.3.1) — нарушения логируются, ответы AI не блокируются.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={windowDays}
            onChange={(e) => setWindowDays(Number(e.target.value))}
            className="text-xs rounded-lg px-2 py-1.5"
            style={{
              background: "var(--input-bg)",
              border: "1px solid var(--border-color)",
              color: "var(--text-primary)",
            }}
          >
            <option value={1}>За сутки</option>
            <option value={7}>За 7 дней</option>
            <option value={30}>За 30 дней</option>
          </select>
          <button
            type="button"
            onClick={() => void load()}
            className="text-xs flex items-center gap-1.5 px-3 py-1.5 rounded-lg"
            style={{
              background: "var(--input-bg)",
              border: "1px solid var(--border-color)",
              color: "var(--text-muted)",
            }}
          >
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
            Обновить
          </button>
        </div>
      </header>

      {error && (
        <div
          className="rounded-lg px-3 py-2 text-sm flex items-start gap-2"
          style={{
            background: "color-mix(in srgb, var(--danger) 14%, transparent)",
            color: "var(--danger)",
          }}
        >
          <AlertTriangle size={14} className="mt-0.5 shrink-0" />
          <span>{sanitizeText(error)}</span>
        </div>
      )}

      {loading && !summary ? (
        <div
          className="flex items-center gap-2 text-sm"
          style={{ color: "var(--text-muted)" }}
        >
          <Loader2 size={14} className="animate-spin" />
          Загружаем сводку…
        </div>
      ) : summary && isEmpty ? (
        <div
          className="rounded-lg p-6 text-center text-sm"
          style={{
            background: "var(--input-bg)",
            border: "1px dashed var(--border-color)",
            color: "var(--text-muted)",
          }}
        >
          За выбранное окно нарушений политики и конфликтов идентичности не
          зафиксировано — AI-роли держат идентичность стабильно.
        </div>
      ) : summary ? (
        <>
          {/* Top totals */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <TotalCard
              label="Нарушения политики"
              value={summary.totals.policy_violations}
              icon={Shield}
              tone={summary.totals.policy_violations > 0 ? "warning" : "muted"}
            />
            <TotalCard
              label="Конфликты идентичности"
              value={summary.totals.persona_conflicts}
              icon={ShieldAlert}
              tone={summary.totals.persona_conflicts > 0 ? "danger" : "muted"}
            />
            <TotalCard
              label="Подтверждённые слоты"
              value={summary.totals.slot_locked}
              icon={TrendingUp}
              tone="success"
            />
          </div>

          {/* Severity strip */}
          {(summary.by_severity.critical ||
            summary.by_severity.high ||
            summary.by_severity.medium ||
            summary.by_severity.low) > 0 && (
            <div
              className="rounded-xl p-4"
              style={{
                background: "var(--glass-bg)",
                border: "1px solid var(--glass-border)",
              }}
            >
              <div className="flex items-center justify-between flex-wrap gap-3">
                <span
                  className="text-xs uppercase tracking-wider"
                  style={{ color: "var(--text-muted)" }}
                >
                  Распределение по уровню
                </span>
                <SeverityChips by={summary.by_severity} hideZero={false} />
              </div>
              {summary.by_code.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {summary.by_code.slice(0, 8).map((c) => (
                    <span
                      key={c.code}
                      className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-[11px]"
                      style={{
                        background: "var(--input-bg)",
                        border: "1px solid var(--border-color)",
                        color: "var(--text-muted)",
                      }}
                      title={`${c.count} нарушений по коду ${c.code}`}
                    >
                      <span className="font-mono">{c.count}</span>
                      <span>{c.code}</span>
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* By manager */}
          {summary.by_manager.length > 0 && (
            <section className="space-y-2">
              <h3
                className="text-sm font-semibold"
                style={{ color: "var(--text-secondary)" }}
              >
                По менеджерам ({summary.by_manager.length})
              </h3>
              <div className="space-y-1.5">
                {summary.by_manager.map((row) => (
                  <ManagerRow
                    key={row.manager_id ?? "unknown"}
                    row={row}
                  />
                ))}
              </div>
            </section>
          )}

          {/* Recent feed */}
          {summary.recent.length > 0 && (
            <section className="space-y-2">
              <h3
                className="text-sm font-semibold"
                style={{ color: "var(--text-secondary)" }}
              >
                Лента событий ({summary.recent.length})
              </h3>
              <div className="space-y-1.5">
                {summary.recent.map((ev) => (
                  <RecentRow key={ev.event_id} ev={ev} />
                ))}
              </div>
            </section>
          )}
        </>
      ) : null}
    </motion.section>
  );
}
