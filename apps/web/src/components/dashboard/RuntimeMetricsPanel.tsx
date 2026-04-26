"use client";

/**
 * RuntimeMetricsPanel — TZ-2 §18 observability surface.
 *
 * Renders the three counter families exposed by
 * ``GET /admin/runtime/metrics`` (Prometheus text format):
 *
 *   • ``runtime_blocked_starts_total`` — guard violations on session
 *     start/end. Spike on a specific guard label is the early-warning
 *     for a frontend that just started sending bad payloads.
 *   • ``runtime_finalize_total``       — completion_policy entries by
 *     ``completed_via`` × ``outcome`` × ``policy_mode`` × ``freshness``.
 *     ``freshness=idempotent`` rows isolate double-finalize attempts
 *     (REST↔WS race or producer bug).
 *   • ``runtime_followup_gap_total``   — follow-up helper drops by
 *     ``reason``. Tells expected drops (``no_real_client`` on a
 *     simulation session) from drift (``no_lead_resolution`` after
 *     cutover, missing policy mapping for a new outcome).
 *
 * Counts are in-process per worker — Prometheus scrape aggregates across
 * workers. Restart resets them; this panel reads the live value, so
 * after a deploy the table is empty until the first request hits.
 *
 * Auto-refresh every 30s (off-screen tabs pause via the visibility API).
 * Mounted from SystemPanel — caller is admin-gated.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertOctagon,
  CheckCircle2,
  Clock,
  Loader2,
  RefreshCw,
  ShieldAlert,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";

import { getApiBaseUrl } from "@/lib/public-origin";
import { logger } from "@/lib/logger";
import { DashboardSkeleton } from "@/components/ui/Skeleton";

// ── Types ────────────────────────────────────────────────────────────────

interface CounterRow {
  metric: string;
  labels: Record<string, string>;
  value: number;
}

interface ParsedMetrics {
  blocked_starts: CounterRow[];
  finalize: CounterRow[];
  followup_gap: CounterRow[];
  generated_at: string;
}

// ── Prometheus text parser ──────────────────────────────────────────────

const LABEL_RE = /([a-zA-Z_][a-zA-Z0-9_]*)="([^"]*)"/g;

function parseLabels(labelStr: string): Record<string, string> {
  const out: Record<string, string> = {};
  let match: RegExpExecArray | null;
  LABEL_RE.lastIndex = 0;
  while ((match = LABEL_RE.exec(labelStr)) !== null) {
    out[match[1]] = match[2];
  }
  return out;
}

/** Parse the three counter families. Ignores `# HELP`/`# TYPE` lines. */
function parsePrometheus(text: string): ParsedMetrics {
  const blocked: CounterRow[] = [];
  const finalize: CounterRow[] = [];
  const gap: CounterRow[] = [];

  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    // Format: metric_name{label1="v1",label2="v2"} 42
    const braceStart = line.indexOf("{");
    const braceEnd = line.indexOf("}");
    if (braceStart < 0 || braceEnd < 0) continue;
    const metric = line.slice(0, braceStart);
    const labelStr = line.slice(braceStart + 1, braceEnd);
    const valueStr = line.slice(braceEnd + 1).trim();
    const value = Number(valueStr);
    if (Number.isNaN(value)) continue;

    const row: CounterRow = {
      metric,
      labels: parseLabels(labelStr),
      value,
    };

    if (metric === "runtime_blocked_starts_total") blocked.push(row);
    else if (metric === "runtime_finalize_total") finalize.push(row);
    else if (metric === "runtime_followup_gap_total") gap.push(row);
  }

  // Sort: highest count first within each family — operator scans from
  // the top to spot dominant labels.
  blocked.sort((a, b) => b.value - a.value);
  finalize.sort((a, b) => b.value - a.value);
  gap.sort((a, b) => b.value - a.value);

  return {
    blocked_starts: blocked,
    finalize,
    followup_gap: gap,
    generated_at: new Date().toISOString(),
  };
}

// ── Section render helpers ──────────────────────────────────────────────

function familyTotal(rows: CounterRow[]): number {
  return rows.reduce((s, r) => s + r.value, 0);
}

function CounterTable({
  rows,
  labelOrder,
  emptyMessage,
}: {
  rows: CounterRow[];
  labelOrder: string[];
  emptyMessage: string;
}) {
  if (rows.length === 0) {
    return (
      <div
        className="rounded-lg p-4 text-sm italic text-center"
        style={{ background: "var(--bg-panel)", color: "var(--text-muted)" }}
      >
        {emptyMessage}
      </div>
    );
  }
  return (
    <div className="overflow-x-auto rounded-lg" style={{ border: "1px solid var(--border-color)" }}>
      <table className="w-full text-sm">
        <thead style={{ background: "var(--input-bg)" }}>
          <tr>
            {labelOrder.map((l) => (
              <th
                key={l}
                className="px-3 py-2 text-left font-semibold text-xs uppercase tracking-wide"
                style={{ color: "var(--text-muted)" }}
              >
                {l}
              </th>
            ))}
            <th
              className="px-3 py-2 text-right font-semibold text-xs uppercase tracking-wide"
              style={{ color: "var(--text-muted)" }}
            >
              count
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr
              key={i}
              style={{
                borderTop: i === 0 ? undefined : "1px solid var(--border-color)",
              }}
            >
              {labelOrder.map((l) => (
                <td key={l} className="px-3 py-2 font-mono text-xs" style={{ color: "var(--text-secondary)" }}>
                  {r.labels[l] ?? "—"}
                </td>
              ))}
              <td
                className="px-3 py-2 text-right font-mono font-bold"
                style={{ color: "var(--text-primary)" }}
              >
                {r.value.toLocaleString("ru-RU")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Component ───────────────────────────────────────────────────────────

const REFRESH_MS = 30_000;

export function RuntimeMetricsPanel() {
  const [metrics, setMetrics] = useState<ParsedMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const fetchMetrics = useCallback(async (silent = false) => {
    if (!silent) setRefreshing(true);
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/admin/runtime/metrics`, {
        credentials: "include",
        headers: { Accept: "text/plain" },
      });
      if (!res.ok) {
        const msg = `HTTP ${res.status}`;
        if (res.status === 401 || res.status === 403) {
          throw new Error("Доступ только для администратора");
        }
        throw new Error(msg);
      }
      const text = await res.text();
      setMetrics(parsePrometheus(text));
      setError(null);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Не удалось загрузить метрики";
      logger.error("[RuntimeMetricsPanel] fetch failed:", err);
      setError(msg);
      if (!silent) toast.error(msg);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  // Initial load + auto-refresh while tab is visible
  useEffect(() => {
    fetchMetrics(true);
    let timer: ReturnType<typeof setInterval> | null = null;

    const start = () => {
      if (timer) return;
      timer = setInterval(() => fetchMetrics(true), REFRESH_MS);
    };
    const stop = () => {
      if (timer) clearInterval(timer);
      timer = null;
    };

    start();
    const onVisibility = () => {
      if (document.visibilityState === "visible") start();
      else stop();
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      stop();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [fetchMetrics]);

  const totals = useMemo(() => {
    if (!metrics) return { blocked: 0, finalize: 0, gap: 0 };
    return {
      blocked: familyTotal(metrics.blocked_starts),
      finalize: familyTotal(metrics.finalize),
      gap: familyTotal(metrics.followup_gap),
    };
  }, [metrics]);

  // Idempotent finalize bucket — spike here = double-finalize bug.
  const idempotentFinalizes = useMemo(() => {
    if (!metrics) return 0;
    return metrics.finalize
      .filter((r) => r.labels.freshness === "idempotent")
      .reduce((s, r) => s + r.value, 0);
  }, [metrics]);

  if (loading && !metrics) return <DashboardSkeleton />;

  if (error && !metrics) {
    return (
      <div
        className="rounded-lg p-6 flex flex-col items-center text-center gap-3"
        style={{ background: "var(--danger-muted)", border: "1px solid var(--danger)" }}
      >
        <XCircle size={28} style={{ color: "var(--danger)" }} />
        <p className="text-sm font-medium" style={{ color: "var(--danger)" }}>
          {error}
        </p>
        <button
          onClick={() => fetchMetrics()}
          className="px-3 py-1.5 rounded-md text-xs font-medium"
          style={{ background: "var(--accent-muted)", color: "var(--accent)" }}
        >
          Попробовать снова
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {/* Header + refresh */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Activity size={16} style={{ color: "var(--accent)" }} />
          <h3 className="text-sm font-semibold uppercase tracking-wide" style={{ color: "var(--text-secondary)" }}>
            TZ-2 Runtime Telemetry
          </h3>
          {refreshing && (
            <Loader2 size={12} className="animate-spin" style={{ color: "var(--text-muted)" }} />
          )}
        </div>
        <div className="flex items-center gap-3">
          {metrics?.generated_at && (
            <span className="text-xs flex items-center gap-1" style={{ color: "var(--text-muted)" }}>
              <Clock size={11} />
              {new Date(metrics.generated_at).toLocaleTimeString("ru-RU")}
            </span>
          )}
          <button
            onClick={() => fetchMetrics()}
            disabled={refreshing}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium disabled:opacity-50"
            style={{ background: "var(--accent-muted)", color: "var(--accent)" }}
          >
            <RefreshCw size={11} className={refreshing ? "animate-spin" : ""} />
            Обновить
          </button>
        </div>
      </div>

      {/* Headline tiles */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Tile
          label="Blocked starts"
          value={totals.blocked}
          icon={ShieldAlert}
          accent="var(--warning)"
          hint="Guard violations (start + end)"
        />
        <Tile
          label="Finalize"
          value={totals.finalize}
          icon={CheckCircle2}
          accent="var(--success)"
          hint="Все завершения сессий"
        />
        <Tile
          label="Idempotent finalize"
          value={idempotentFinalizes}
          icon={AlertOctagon}
          accent={idempotentFinalizes > 0 ? "var(--warning)" : "var(--text-muted)"}
          hint="Двойные finalize (REST↔WS race)"
        />
        <Tile
          label="Follow-up gap"
          value={totals.gap}
          icon={ShieldAlert}
          accent="var(--text-muted)"
          hint="Follow-up'ы, которые не создались"
        />
      </div>

      {/* Detail tables */}
      <Section
        title="runtime_blocked_starts_total"
        subtitle="Срабатывания guard'ов на старте/завершении сессии"
      >
        <CounterTable
          rows={metrics?.blocked_starts ?? []}
          labelOrder={["guard", "phase", "mode", "runtime_type"]}
          emptyMessage="Пока ни один guard не срабатывал — это норма для свежего деплоя."
        />
      </Section>

      <Section
        title="runtime_finalize_total"
        subtitle="REST↔WS parity: ratio completed_via × outcome × freshness"
      >
        <CounterTable
          rows={metrics?.finalize ?? []}
          labelOrder={["completed_via", "outcome", "policy_mode", "freshness"]}
          emptyMessage="Завершений ещё не было."
        />
      </Section>

      <Section
        title="runtime_followup_gap_total"
        subtitle="Случаи, когда follow-up не создался — по причине"
      >
        <CounterTable
          rows={metrics?.followup_gap ?? []}
          labelOrder={["reason", "outcome", "helper"]}
          emptyMessage="Follow-up gap'ов не зафиксировано."
        />
      </Section>

      <p className="text-xs italic" style={{ color: "var(--text-muted)" }}>
        Счётчики живут в памяти процесса и сбрасываются при рестарте api.
        Auto-refresh каждые {REFRESH_MS / 1000}с пока вкладка активна.
      </p>
    </div>
  );
}

function Tile({
  label,
  value,
  icon: Icon,
  accent,
  hint,
}: {
  label: string;
  value: number;
  icon: typeof Activity;
  accent: string;
  hint: string;
}) {
  return (
    <div
      className="rounded-xl p-4"
      style={{
        background: "var(--bg-panel)",
        border: `1px solid color-mix(in srgb, ${accent} 25%, var(--border-color))`,
      }}
    >
      <div className="flex items-center gap-2 mb-2">
        <Icon size={14} style={{ color: accent }} />
        <span className="text-[11px] uppercase tracking-wide font-semibold" style={{ color: "var(--text-muted)" }}>
          {label}
        </span>
      </div>
      <div className="font-display text-2xl font-bold tabular-nums" style={{ color: accent }}>
        {value.toLocaleString("ru-RU")}
      </div>
      <p className="text-xs mt-1.5" style={{ color: "var(--text-muted)" }}>
        {hint}
      </p>
    </div>
  );
}

function Section({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-baseline gap-3">
        <h4 className="font-mono text-xs font-bold" style={{ color: "var(--text-primary)" }}>
          {title}
        </h4>
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>
          {subtitle}
        </p>
      </div>
      {children}
    </div>
  );
}
