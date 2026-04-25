"use client";

/**
 * /admin/client-domain — TZ-1 operations center.
 *
 * Reads the consolidated ``/admin/client-domain/dashboard`` endpoint and
 * renders:
 *   • traffic-light health badge (green/yellow/red with reason);
 *   • 4 headline counters + parity ratio gauge;
 *   • 24h event-type distribution (bar chart);
 *   • read-only view of feature flags;
 *   • quick-actions: refresh · self-test · repair events · repair projections;
 *   • recent DomainEvents table for debugging a specific action.
 *
 * All mutations go through admin-only endpoints behind CSRF — ``api.post``
 * handles the header+cookie pair automatically.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  FlaskConical,
  HeartPulse,
  Info,
  Inbox,
  Loader2,
  RefreshCw,
  Wrench,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";

import { api, ApiError } from "@/lib/api";

type ClientDomainView = "health" | "ops" | "events" | "followups";

const SUB_TABS: { id: ClientDomainView; label: string; icon: typeof Activity }[] = [
  { id: "health", label: "Здоровье", icon: HeartPulse },
  { id: "ops", label: "Операции", icon: Wrench },
  { id: "events", label: "События", icon: Activity },
  { id: "followups", label: "Follow-ups", icon: Inbox },
];

// ── Types ────────────────────────────────────────────────────────────────

type HealthStatus = "green" | "yellow" | "red";

interface ParityReport {
  total_interactions: number;
  total_events: number;
  total_projections: number;
  interactions_without_domain_event_id: number;
  events_without_projection: number;
  projections_without_interaction: number;
  events_without_lead_client_id: number;
}

interface HealthVerdict {
  status: HealthStatus;
  reason: string;
  parity_ratio: number;
}

interface EventTypes {
  since_hours: number;
  total: number;
  by_type: Record<string, number>;
}

interface Flags {
  client_domain_dual_write_enabled: boolean;
  client_domain_cutover_read_enabled: boolean;
  client_domain_strict_emit: boolean;
}

interface RecentEvent {
  id: string;
  event_type: string;
  lead_client_id: string | null;
  actor_type: string;
  actor_id: string | null;
  source: string;
  aggregate_type: string | null;
  aggregate_id: string | null;
  session_id: string | null;
  correlation_id: string | null;
  occurred_at: string | null;
  schema_version: number;
  idempotency_key: string;
}

interface DashboardResponse {
  generated_at: string;
  parity: ParityReport;
  health: HealthVerdict;
  flags: Flags;
  event_types: EventTypes;
  recent_events: RecentEvent[];
}

interface SelfTestStep {
  name: string;
  status: "ok" | "fail";
  error?: string;
  event_id?: string;
  idempotency_key?: string;
}

interface SelfTestResult {
  passed: boolean;
  started_at: string;
  finished_at: string;
  steps: SelfTestStep[];
}

// ── Helpers ──────────────────────────────────────────────────────────────

const HEALTH_COLORS: Record<HealthStatus, { bg: string; fg: string; border: string }> = {
  green: { bg: "rgba(34,197,94,0.12)", fg: "#22c55e", border: "rgba(34,197,94,0.35)" },
  yellow: { bg: "rgba(234,179,8,0.14)", fg: "#eab308", border: "rgba(234,179,8,0.4)" },
  red: { bg: "rgba(239,68,68,0.14)", fg: "#ef4444", border: "rgba(239,68,68,0.4)" },
};

function formatTimestamp(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}

function formatPercent(ratio: number): string {
  return `${(ratio * 100).toFixed(ratio === 1 ? 0 : 2)}%`;
}

// ── Small UI atoms ───────────────────────────────────────────────────────

function StatCard({
  label,
  value,
  accent = "var(--accent)",
  hint,
  alert = false,
}: {
  label: string;
  value: React.ReactNode;
  accent?: string;
  hint?: string;
  alert?: boolean;
}) {
  return (
    <div
      className="rounded-xl p-4"
      style={{
        background: "var(--bg-panel)",
        border: alert
          ? "1px solid rgba(239,68,68,0.55)"
          : "1px solid var(--border-color)",
      }}
    >
      <div
        className="text-[11px] uppercase tracking-wider mb-1 font-semibold"
        style={{ color: alert ? "#ef4444" : "var(--text-muted)" }}
      >
        {label}
      </div>
      <div
        className="text-2xl font-bold"
        style={{ color: alert ? "#ef4444" : accent }}
      >
        {value}
      </div>
      {hint && (
        <div
          className="text-[11px] mt-1"
          style={{ color: "var(--text-muted)" }}
        >
          {hint}
        </div>
      )}
    </div>
  );
}

function FlagBadge({ enabled, label, note }: { enabled: boolean; label: string; note?: string }) {
  return (
    <div
      className="rounded-lg p-3 flex items-start gap-3"
      style={{
        background: "var(--bg-panel)",
        border: "1px solid var(--border-color)",
      }}
    >
      <div
        className="mt-0.5 h-4 w-4 rounded-full"
        style={{
          background: enabled ? "#22c55e" : "#6b7280",
          boxShadow: enabled ? "0 0 0 3px rgba(34,197,94,0.2)" : "none",
        }}
      />
      <div className="flex-1 min-w-0">
        <div
          className="text-sm font-medium"
          style={{ color: "var(--text-primary)" }}
        >
          {label}
        </div>
        <div
          className="text-[11px] mt-0.5"
          style={{ color: "var(--text-muted)" }}
        >
          {enabled ? "ВКЛЮЧЕНО" : "ВЫКЛЮЧЕНО"}
          {note ? ` · ${note}` : ""}
        </div>
      </div>
    </div>
  );
}

function HealthBadge({ health }: { health: HealthVerdict }) {
  const pal = HEALTH_COLORS[health.status];
  const Icon = health.status === "green" ? CheckCircle2 : health.status === "yellow" ? AlertCircle : XCircle;
  const label = health.status === "green" ? "Здоров" : health.status === "yellow" ? "Требует внимания" : "Критично";
  return (
    <div
      className="rounded-xl p-4 flex items-start gap-4"
      style={{
        background: pal.bg,
        border: `1px solid ${pal.border}`,
      }}
    >
      <div
        className="flex h-12 w-12 items-center justify-center rounded-full flex-shrink-0"
        style={{ background: pal.border, color: pal.fg }}
      >
        <Icon size={24} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-3 flex-wrap">
          <span
            className="text-lg font-bold uppercase tracking-wide"
            style={{ color: pal.fg }}
          >
            {label}
          </span>
          <span
            className="text-sm"
            style={{ color: "var(--text-secondary)" }}
          >
            Parity ratio: <strong>{formatPercent(health.parity_ratio)}</strong>
          </span>
        </div>
        <p
          className="text-sm mt-2"
          style={{ color: "var(--text-secondary)" }}
        >
          {health.reason}
        </p>
      </div>
    </div>
  );
}

function EventTypeBar({ total, by_type }: EventTypes) {
  const entries = useMemo(
    () => Object.entries(by_type).sort((a, b) => b[1] - a[1]),
    [by_type],
  );
  if (total === 0) {
    return (
      <div
        className="text-sm italic rounded-lg p-6 text-center"
        style={{
          background: "var(--bg-panel)",
          color: "var(--text-muted)",
          border: "1px dashed var(--border-color)",
        }}
      >
        За последние 24 часа событий нет. Это нормально, если пилот ещё не начался.
      </div>
    );
  }
  const max = entries[0][1];
  return (
    <div className="space-y-2">
      {entries.map(([type, count]) => {
        const pct = (count / max) * 100;
        return (
          <div key={type} className="flex items-center gap-3">
            <div
              className="text-xs font-mono flex-shrink-0 w-56 truncate"
              style={{ color: "var(--text-secondary)" }}
              title={type}
            >
              {type}
            </div>
            <div
              className="flex-1 h-5 rounded relative overflow-hidden"
              style={{ background: "var(--bg-secondary)" }}
            >
              <div
                className="h-full"
                style={{
                  width: `${pct}%`,
                  background: "linear-gradient(90deg, var(--accent), var(--accent-muted, var(--accent)))",
                  transition: "width 400ms ease",
                }}
              />
            </div>
            <div
              className="text-sm font-semibold w-12 text-right"
              style={{ color: "var(--text-primary)" }}
            >
              {count}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── TZ-2 §12 TaskFollowUp observability types ───────────────────────────

interface TaskFollowUpRow {
  id: string;
  lead_client_id: string;
  session_id: string | null;
  domain_event_id: string | null;
  reason: string;
  channel: string | null;
  due_at: string | null;
  status: string;
  auto_generated: boolean;
  created_at: string | null;
  completed_at: string | null;
}

interface TaskFollowUpsResponse {
  items: TaskFollowUpRow[];
  total: number;
  page: number;
  per_page: number;
  by_status: Record<string, number>;
  by_reason: Record<string, number>;
  overdue_in_page: number;
}

// ── Page ─────────────────────────────────────────────────────────────────

export default function ClientDomainAdminPage() {
  const [data, setData] = useState<DashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busy, setBusy] = useState<null | "refresh" | "self-test" | "repair-events" | "repair-projections">(null);
  const [selfTest, setSelfTest] = useState<SelfTestResult | null>(null);
  const [showHelp, setShowHelp] = useState(false);
  const [view, setView] = useState<ClientDomainView>("health");
  // TZ-2 §12 — read-only observability of task_followups (canonical
  // alongside the legacy manager_reminders that managers see in CRM).
  const [followups, setFollowups] = useState<TaskFollowUpsResponse | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      setLoading(true);
      setLoadError(null);
      // Two parallel reads — dashboard remains the primary source of truth
      // for the page; task-followups is a sibling observability call. Failure
      // of the followups call is non-fatal: the existing dashboard renders
      // unchanged and the section just shows an empty state.
      const [d, fu] = await Promise.all([
        api.get<DashboardResponse>(
          "/admin/client-domain/dashboard",
          signal ? { signal } : undefined,
        ),
        api.get<TaskFollowUpsResponse>(
          "/admin/task-followups?per_page=20",
          signal ? { signal } : undefined,
        ).catch(() => null),
      ]);
      if (signal?.aborted) return;
      setData(d);
      setFollowups(fu);
    } catch (err) {
      if (signal?.aborted) return;
      // Ignore aborts triggered by unmount/refetch — they are not user-
      // visible failures.
      if (err instanceof DOMException && err.name === "AbortError") return;
      const msg = err instanceof ApiError ? err.message : String(err);
      setLoadError(msg);
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  // F-L12-1 fix: abort the in-flight request on unmount/remount so a
  // late response can't setState on a dead component.
  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const refresh = useCallback(async () => {
    setBusy("refresh");
    try {
      await load();
      toast.success("Данные обновлены");
    } finally {
      setBusy(null);
    }
  }, [load]);

  const runSelfTest = useCallback(async () => {
    setBusy("self-test");
    setSelfTest(null);
    try {
      const result = await api.post<SelfTestResult>("/admin/client-domain/self-test", {});
      setSelfTest(result);
      if (result.passed) {
        toast.success("Self-test пройден — pipeline дышит");
      } else {
        toast.error("Self-test провалился — см. детали ниже");
      }
      await load();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : String(err);
      toast.error(`Self-test не запустился: ${msg}`);
    } finally {
      setBusy(null);
    }
  }, [load]);

  const runRepair = useCallback(
    async (kind: "events" | "projections") => {
      const confirmMsg =
        kind === "events"
          ? "Backfill DomainEvent для legacy-интеракций. Идемпотентно (ключ repair:client_interaction:<id>). Продолжить?"
          : "Создать отсутствующие projection-строки для событий без timeline-записи. Продолжить?";
      if (!window.confirm(confirmMsg)) return;
      setBusy(kind === "events" ? "repair-events" : "repair-projections");
      try {
        const endpoint =
          kind === "events"
            ? "/admin/client-domain/repair/events"
            : "/admin/client-domain/repair/projections";
        const result = await api.post<{ repaired_events?: number; repaired_projections?: number }>(
          endpoint,
          {},
        );
        const count = result.repaired_events ?? result.repaired_projections ?? 0;
        toast.success(`Репейр завершён · обновлено записей: ${count}`);
        await load();
      } catch (err) {
        const msg = err instanceof ApiError ? err.message : String(err);
        toast.error(`Репейр не удался: ${msg}`);
      } finally {
        setBusy(null);
      }
    },
    [load],
  );

  // ── render ────────────────────────────────────────────────────────────

  const parity = data?.parity;
  const health = data?.health;
  const flags = data?.flags;
  const eventTypes = data?.event_types;

  return (
    <div className="space-y-6 max-w-6xl">
      {/* Header + actions */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="max-w-2xl">
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            TZ-1 · Единый клиентский домен. Здесь видны реальные инварианты
            системы: хватает ли каждому действию своего DomainEvent, нет ли
            legacy-дрейфа, насколько чиста проекция CRM timeline. Нажмите
            «Self-test», чтобы прогнать живой round-trip, или «Репейр» — если
            parity-ratio просел ниже 100 %.
          </p>
          {data && (
            <div className="text-[11px] mt-2" style={{ color: "var(--text-muted)" }}>
              Обновлено: {formatTimestamp(data.generated_at)}
            </div>
          )}
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <button
            type="button"
            onClick={refresh}
            disabled={busy !== null}
            className="inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition disabled:opacity-50"
            style={{
              background: "var(--bg-panel)",
              border: "1px solid var(--border-color)",
              color: "var(--text-primary)",
            }}
          >
            {busy === "refresh" ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <RefreshCw size={14} />
            )}
            Обновить
          </button>

          <button
            type="button"
            onClick={runSelfTest}
            disabled={busy !== null}
            className="inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition disabled:opacity-50"
            style={{
              background: "var(--accent)",
              color: "white",
              border: "1px solid var(--accent)",
            }}
          >
            {busy === "self-test" ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <FlaskConical size={14} />
            )}
            Self-test
          </button>
        </div>
      </div>

      {/* Health badge */}
      {loadError && (
        <div
          className="rounded-xl p-4 flex items-start gap-3"
          style={{
            background: "rgba(239,68,68,0.08)",
            border: "1px solid rgba(239,68,68,0.35)",
            color: "#ef4444",
          }}
        >
          <AlertCircle size={18} />
          <div className="flex-1 text-sm">{loadError}</div>
          <button
            type="button"
            onClick={refresh}
            className="text-xs underline"
            style={{ color: "#ef4444" }}
          >
            Повторить
          </button>
        </div>
      )}

      {loading && !data ? (
        <div
          className="rounded-xl p-6 flex items-center gap-3"
          style={{
            background: "var(--bg-panel)",
            border: "1px solid var(--border-color)",
            color: "var(--text-muted)",
          }}
        >
          <Loader2 size={16} className="animate-spin" />
          Загружаю dashboard…
        </div>
      ) : null}

      {/* Sub-tab strip — splits the previously-monolithic page into four
          focused views so admins don't have to scroll past 1100 lines to
          find one button. The action buttons in the header (Refresh,
          Self-test) stay always-visible because they're cross-cutting. */}
      <div
        className="flex items-center gap-1 rounded-lg p-1 overflow-x-auto"
        style={{
          background: "var(--bg-secondary)",
          border: "1px solid var(--border-color)",
        }}
        role="tablist"
        aria-label="Разделы клиентского домена"
      >
        {SUB_TABS.map(({ id, label, icon: Icon }) => {
          const active = view === id;
          return (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setView(id)}
              className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-md whitespace-nowrap transition"
              style={{
                color: active ? "white" : "var(--text-secondary)",
                background: active ? "var(--accent)" : "transparent",
                border: "none",
                cursor: "pointer",
              }}
            >
              <Icon size={14} />
              {label}
            </button>
          );
        })}
      </div>

      {/* ── Health view ── */}
      {view === "health" && health && <HealthBadge health={health} />}

      {/* Parity counters */}
      {view === "health" && parity && (
        <div>
          <div
            className="text-[11px] font-semibold uppercase tracking-widest mb-2 flex items-center gap-1"
            style={{ color: "var(--text-muted)" }}
          >
            <Activity size={12} /> Parity report
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
            <StatCard
              label="DomainEvent всего"
              value={parity.total_events}
              hint="Канонический журнал"
            />
            <StatCard
              label="CRM интеракций"
              value={parity.total_interactions}
              hint="Legacy timeline"
            />
            <StatCard
              label="Projection-строк"
              value={parity.total_projections}
              hint="Должно ≈ events"
            />
            <StatCard
              label="Parity ratio"
              value={health ? formatPercent(health.parity_ratio) : "—"}
              hint="1.0 = идеал"
              accent={
                health?.status === "green"
                  ? "#22c55e"
                  : health?.status === "yellow"
                    ? "#eab308"
                    : "#ef4444"
              }
            />
            <StatCard
              label="Interactions без event"
              value={parity.interactions_without_domain_event_id}
              alert={parity.interactions_without_domain_event_id > 0}
              hint="Цель: 0"
            />
            <StatCard
              label="Events без projection"
              value={parity.events_without_projection}
              alert={parity.events_without_projection > 0}
              hint="Цель: 0"
            />
            <StatCard
              label="Projections без interaction"
              value={parity.projections_without_interaction}
              alert={parity.projections_without_interaction > 0}
              hint="Цель: 0"
            />
            <StatCard
              label="Events без lead_client_id"
              value={parity.events_without_lead_client_id}
              alert={parity.events_without_lead_client_id > 0}
              hint="Инвариант §13.4 · 0"
            />
          </div>
        </div>
      )}

      {/* ── Ops view ── */}
      {/* Repair actions */}
      {view === "ops" && parity && (
        <div
          className="rounded-xl p-4"
          style={{
            background: "var(--bg-panel)",
            border: "1px solid var(--border-color)",
          }}
        >
          <div
            className="text-[11px] font-semibold uppercase tracking-widest mb-3 flex items-center gap-1"
            style={{ color: "var(--text-muted)" }}
          >
            <Wrench size={12} /> Репейр
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => runRepair("events")}
              disabled={busy !== null}
              className="inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition disabled:opacity-50"
              style={{
                background: "var(--bg-secondary)",
                border: "1px solid var(--border-color)",
                color: "var(--text-primary)",
              }}
            >
              {busy === "repair-events" ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Wrench size={14} />
              )}
              Восстановить DomainEvent&apos;ы для legacy-интеракций
            </button>
            <button
              type="button"
              onClick={() => runRepair("projections")}
              disabled={busy !== null}
              className="inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition disabled:opacity-50"
              style={{
                background: "var(--bg-secondary)",
                border: "1px solid var(--border-color)",
                color: "var(--text-primary)",
              }}
            >
              {busy === "repair-projections" ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Wrench size={14} />
              )}
              Восстановить projection-строки
            </button>
          </div>
          <p
            className="text-[11px] mt-3"
            style={{ color: "var(--text-muted)" }}
          >
            Обе операции идемпотентны. Ограничение — 500 записей за раз;
            повторите, если repair вернул значение около лимита.
          </p>
        </div>
      )}

      {/* Self-test result — appears in Ops view (where you triggered it). */}
      {view === "ops" && selfTest && (
        <div
          className="rounded-xl p-4"
          style={{
            background: selfTest.passed
              ? "rgba(34,197,94,0.08)"
              : "rgba(239,68,68,0.08)",
            border: selfTest.passed
              ? "1px solid rgba(34,197,94,0.35)"
              : "1px solid rgba(239,68,68,0.35)",
          }}
        >
          <div
            className="flex items-center gap-2 font-semibold mb-2"
            style={{ color: selfTest.passed ? "#22c55e" : "#ef4444" }}
          >
            {selfTest.passed ? <CheckCircle2 size={16} /> : <XCircle size={16} />}
            Self-test {selfTest.passed ? "пройден" : "провален"}
          </div>
          <ul className="text-sm space-y-1" style={{ color: "var(--text-secondary)" }}>
            {selfTest.steps.map((step, idx) => (
              <li key={idx} className="flex items-baseline gap-2 font-mono text-[12px]">
                <span style={{ color: step.status === "ok" ? "#22c55e" : "#ef4444" }}>
                  {step.status === "ok" ? "✓" : "✗"}
                </span>
                <span>{step.name}</span>
                {step.event_id && (
                  <span style={{ color: "var(--text-muted)" }}>
                    · event_id: {step.event_id.slice(0, 8)}
                  </span>
                )}
                {step.error && (
                  <span style={{ color: "#ef4444" }}>· {step.error}</span>
                )}
              </li>
            ))}
          </ul>
          <div className="text-[11px] mt-2" style={{ color: "var(--text-muted)" }}>
            {formatTimestamp(selfTest.started_at)} → {formatTimestamp(selfTest.finished_at)}
          </div>
        </div>
      )}

      {/* ── Events view ── */}
      {/* Event types */}
      {view === "events" && eventTypes && (
        <div>
          <div
            className="text-[11px] font-semibold uppercase tracking-widest mb-2 flex items-center gap-1"
            style={{ color: "var(--text-muted)" }}
          >
            <Clock size={12} /> Типы событий · последние {eventTypes.since_hours} ч
            <span style={{ color: "var(--text-secondary)" }}>
              · всего {eventTypes.total}
            </span>
          </div>
          <div
            className="rounded-xl p-4"
            style={{
              background: "var(--bg-panel)",
              border: "1px solid var(--border-color)",
            }}
          >
            <EventTypeBar {...eventTypes} />
          </div>
        </div>
      )}

      {/* ── Follow-ups view ── */}
      {/* TZ-2 §12 — TaskFollowUp observability */}
      {view === "followups" && followups && (
        <div>
          <div
            className="text-[11px] font-semibold uppercase tracking-widest mb-2 flex items-center gap-1"
            style={{ color: "var(--text-muted)" }}
          >
            <Clock size={12} /> §12 TaskFollowUp · pending
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
            <StatCard
              label="всего"
              value={followups.total}
              hint="строк под текущим фильтром"
            />
            <StatCard
              label="pending"
              value={followups.by_status.pending ?? 0}
              accent="#3b82f6"
              hint="ожидают касания"
            />
            <StatCard
              label="done"
              value={followups.by_status.done ?? 0}
              accent="var(--accent)"
            />
            <StatCard
              label="overdue (на странице)"
              value={followups.overdue_in_page}
              alert={followups.overdue_in_page > 0}
              hint="due_at в прошлом"
            />
          </div>
          {followups.items.length === 0 ? (
            <div
              className="rounded-xl p-4 text-sm"
              style={{
                background: "var(--bg-panel)",
                border: "1px solid var(--border-color)",
                color: "var(--text-muted)",
              }}
            >
              Список пуст — policy не создавала follow-up&apos;ов в недавних
              сессиях. Это норма пока ни один CRM-клиент не дошёл до исхода
              «callback_requested» или «needs_followup».
            </div>
          ) : (
            <div
              className="rounded-xl overflow-hidden"
              style={{
                background: "var(--bg-panel)",
                border: "1px solid var(--border-color)",
              }}
            >
              <table className="w-full text-sm">
                <thead>
                  <tr
                    style={{
                      borderBottom: "1px solid var(--border-color)",
                      color: "var(--text-muted)",
                    }}
                  >
                    <th className="text-left px-3 py-2 font-medium">due_at</th>
                    <th className="text-left px-3 py-2 font-medium">reason</th>
                    <th className="text-left px-3 py-2 font-medium">channel</th>
                    <th className="text-left px-3 py-2 font-medium">status</th>
                    <th className="text-left px-3 py-2 font-medium">lead</th>
                  </tr>
                </thead>
                <tbody>
                  {followups.items.map((row) => {
                    const overdueRow =
                      row.status === "pending" &&
                      row.due_at !== null &&
                      new Date(row.due_at) < new Date();
                    return (
                      <tr
                        key={row.id}
                        style={{
                          borderBottom: "1px solid var(--border-color)",
                          color: overdueRow
                            ? "#ef4444"
                            : "var(--text-primary)",
                        }}
                      >
                        <td className="px-3 py-2">{formatTimestamp(row.due_at)}</td>
                        <td className="px-3 py-2 font-mono text-xs">
                          {row.reason}
                        </td>
                        <td className="px-3 py-2 text-xs">
                          {row.channel ?? "—"}
                        </td>
                        <td className="px-3 py-2 text-xs">
                          <span
                            className="rounded px-2 py-0.5"
                            style={{
                              background:
                                row.status === "pending"
                                  ? "rgba(59,130,246,0.15)"
                                  : row.status === "done"
                                  ? "rgba(34,197,94,0.15)"
                                  : "rgba(148,163,184,0.15)",
                              color:
                                row.status === "pending"
                                  ? "#3b82f6"
                                  : row.status === "done"
                                  ? "var(--accent)"
                                  : "var(--text-muted)",
                            }}
                          >
                            {row.status}
                          </span>
                        </td>
                        <td
                          className="px-3 py-2 font-mono text-xs"
                          style={{ color: "var(--text-muted)" }}
                        >
                          {row.lead_client_id.slice(0, 8)}…
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {followups.total > followups.items.length && (
                <div
                  className="px-3 py-2 text-xs text-center"
                  style={{
                    color: "var(--text-muted)",
                    borderTop: "1px solid var(--border-color)",
                  }}
                >
                  Показано {followups.items.length} из {followups.total}.
                  Пагинация — следующая итерация.
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Flags — health-status info, lives in Health tab. */}
      {view === "health" && flags && (
        <div>
          <div
            className="text-[11px] font-semibold uppercase tracking-widest mb-2 flex items-center gap-1"
            style={{ color: "var(--text-muted)" }}
          >
            <ShieldAlert size={12} /> Feature flags
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            <FlagBadge
              enabled={flags.client_domain_dual_write_enabled}
              label="Dual-write"
              note="писать и legacy, и DomainEvent"
            />
            <FlagBadge
              enabled={flags.client_domain_cutover_read_enabled}
              label="Cutover read-path"
              note="UI читает из projection"
            />
            <FlagBadge
              enabled={flags.client_domain_strict_emit}
              label="Strict emit"
              note="emit-failures откатывают txn"
            />
          </div>
          <p
            className="text-[11px] mt-2 flex items-start gap-1.5"
            style={{ color: "var(--text-muted)" }}
          >
            <Info size={12} className="flex-shrink-0 mt-0.5" />
            Флаги читаются из <code>.env.production</code> при старте API.
            Чтобы флипнуть cutover — правьте env и делайте{" "}
            <code>docker compose restart api</code>. Runtime toggle отключён
            намеренно, чтобы избежать дрейфа конфигурации в середине запроса.
          </p>
        </div>
      )}

      {/* Recent events */}
      {view === "events" && data?.recent_events && (
        <div>
          <div
            className="text-[11px] font-semibold uppercase tracking-widest mb-2 flex items-center gap-1"
            style={{ color: "var(--text-muted)" }}
          >
            <Clock size={12} /> Последние {data.recent_events.length} DomainEvent&apos;ов
          </div>
          {data.recent_events.length === 0 ? (
            <div
              className="text-sm italic rounded-lg p-6 text-center"
              style={{
                background: "var(--bg-panel)",
                color: "var(--text-muted)",
                border: "1px dashed var(--border-color)",
              }}
            >
              Журнал пуст. Создайте клиента или завершите тренировку — появится запись.
            </div>
          ) : (
            <div
              className="rounded-xl overflow-x-auto"
              style={{
                background: "var(--bg-panel)",
                border: "1px solid var(--border-color)",
              }}
            >
              <table className="w-full text-sm">
                <thead>
                  <tr
                    className="text-[11px] uppercase tracking-wider"
                    style={{
                      color: "var(--text-muted)",
                      borderBottom: "1px solid var(--border-color)",
                    }}
                  >
                    <th className="px-3 py-2 text-left font-semibold">Когда</th>
                    <th className="px-3 py-2 text-left font-semibold">Событие</th>
                    <th className="px-3 py-2 text-left font-semibold">Источник</th>
                    <th className="px-3 py-2 text-left font-semibold">Lead</th>
                    <th className="px-3 py-2 text-left font-semibold">Actor</th>
                    <th className="px-3 py-2 text-left font-semibold">Correlation</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent_events.map((e) => (
                    <tr
                      key={e.id}
                      style={{
                        borderTop: "1px solid var(--border-color)",
                        color: "var(--text-secondary)",
                      }}
                    >
                      <td className="px-3 py-2 whitespace-nowrap font-mono text-[11px]">
                        {formatTimestamp(e.occurred_at)}
                      </td>
                      <td
                        className="px-3 py-2 font-mono text-[12px]"
                        style={{ color: "var(--text-primary)" }}
                      >
                        {e.event_type}
                      </td>
                      <td className="px-3 py-2 text-[12px]">{e.source}</td>
                      <td className="px-3 py-2 font-mono text-[11px]" title={e.lead_client_id || ""}>
                        {e.lead_client_id ? e.lead_client_id.slice(0, 8) : "—"}
                      </td>
                      <td className="px-3 py-2 text-[12px]">
                        {e.actor_type}
                        {e.actor_id ? ` · ${e.actor_id.slice(0, 8)}` : ""}
                      </td>
                      <td className="px-3 py-2 font-mono text-[11px]" title={e.correlation_id || ""}>
                        {e.correlation_id ? e.correlation_id.slice(0, 12) : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Help */}
      <div>
        <button
          type="button"
          onClick={() => setShowHelp((x) => !x)}
          className="inline-flex items-center gap-2 text-xs uppercase tracking-wider"
          style={{ color: "var(--text-muted)" }}
        >
          {showHelp ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          Как этим пользоваться
        </button>
        {showHelp && (
          <div
            className="mt-3 rounded-xl p-4 text-sm space-y-2"
            style={{
              background: "var(--bg-panel)",
              border: "1px solid var(--border-color)",
              color: "var(--text-secondary)",
            }}
          >
            <p>
              <strong>Что это:</strong> операционная консоль единого клиентского домена
              (TZ-1). Каждое действие в CRM параллельно пишется в канонический журнал{" "}
              <code>domain_events</code>. Проекции собирают из него обратно{" "}
              <code>client_interactions</code>, и их количество должно совпадать.
            </p>
            <p>
              <strong>Три критичных числа = 0:</strong>{" "}
              <code>interactions_without_domain_event_id</code>,{" "}
              <code>events_without_projection</code>,{" "}
              <code>events_without_lead_client_id</code>.
              Если видите цифру {'>'} 0 — жмите «Восстановить», потом «Обновить».
            </p>
            <p>
              <strong>Self-test</strong> создаёт фиктивный LeadClient, шлёт ping-
              событие, читает обратно и всё удаляет. Это быстрая проверка, что
              pipeline жив (useful после деплоя).
            </p>
            <p>
              <strong>Cutover</strong> — фаза 5 из TZ §12. Включается, когда parity_ratio
              стабильно = 1.0 и накопилось хотя бы ~50 DomainEvent&apos;ов. Включение:
              <code>CLIENT_DOMAIN_CUTOVER_READ_ENABLED=true</code> в{" "}
              <code>/opt/hunter888/.env.production</code> + рестарт API.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
