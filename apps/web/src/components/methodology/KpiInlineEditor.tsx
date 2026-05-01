"use client";

/**
 * Inline editor for per-manager KPI targets.
 *
 * Used inside the Команда sub-tab. Renders a row with three editable
 * cells (sessions/month, avg score, max days without session) plus a
 * status badge per cell when actuals are supplied via props.
 *
 * Click a cell → shows an input → blur or Enter saves via PATCH; Esc
 * cancels. Backend uses PATCH with explicit-null semantics: setting
 * "" in the input clears that target (FE hides the bar).
 */

import { useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api";
import {
  type KpiStatus,
  type KpiTarget,
  fetchKpiTarget,
  kpiStatusGreaterIsBetter,
  kpiStatusLowerIsBetter,
  updateKpiTarget,
} from "@/lib/api/team_kpi";

interface Props {
  userId: string;
  fullName: string;
  // Live values from /team/analytics — when available, the editor draws
  // a status badge alongside the target. When undefined the editor is
  // pure target-management (no progress bars).
  actualSessions30d?: number | null;
  actualAvgScore30d?: number | null;
  actualDaysSinceLast?: number | null;
  onSaved?: (next: KpiTarget) => void;
}

export function KpiInlineEditor({
  userId,
  fullName,
  actualSessions30d = null,
  actualAvgScore30d = null,
  actualDaysSinceLast = null,
  onSaved,
}: Props) {
  const [target, setTarget] = useState<KpiTarget | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchKpiTarget(userId)
      .then((t) => {
        if (!cancelled) setTarget(t);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [userId]);

  const save = async (
    field: "target_sessions_per_month" | "target_avg_score" | "target_max_days_without_session",
    raw: string,
  ) => {
    // Empty string → null (clear target). Otherwise parse number.
    let value: number | null;
    const trimmed = raw.trim();
    if (trimmed === "") {
      value = null;
    } else {
      const num = Number(trimmed);
      if (Number.isNaN(num)) {
        setError(`Не удалось распознать число: ${raw}`);
        return;
      }
      value = field === "target_avg_score" ? num : Math.round(num);
    }
    setError(null);
    try {
      const next = await updateKpiTarget(userId, { [field]: value });
      setTarget(next);
      onSaved?.(next);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  };

  if (loading) {
    return (
      <div className="text-xs opacity-60">Загружаем KPI {fullName}…</div>
    );
  }

  const sessStatus = kpiStatusGreaterIsBetter(
    actualSessions30d,
    target?.target_sessions_per_month ?? null,
  );
  const scoreStatus = kpiStatusGreaterIsBetter(
    actualAvgScore30d,
    target?.target_avg_score ?? null,
  );
  const daysStatus = kpiStatusLowerIsBetter(
    actualDaysSinceLast,
    target?.target_max_days_without_session ?? null,
  );

  return (
    <div className="flex flex-wrap items-center gap-3 text-xs py-1">
      <KpiCell
        label="Сессий/мес"
        valueActual={actualSessions30d}
        valueTarget={target?.target_sessions_per_month ?? null}
        status={sessStatus}
        onSave={(raw) => save("target_sessions_per_month", raw)}
        suffix=""
      />
      <KpiCell
        label="Сред. скор"
        valueActual={actualAvgScore30d}
        valueTarget={target?.target_avg_score ?? null}
        status={scoreStatus}
        onSave={(raw) => save("target_avg_score", raw)}
        suffix=""
        decimals={1}
      />
      <KpiCell
        label="Макс дней без сессии"
        valueActual={actualDaysSinceLast}
        valueTarget={target?.target_max_days_without_session ?? null}
        status={daysStatus}
        onSave={(raw) => save("target_max_days_without_session", raw)}
        suffix="дн"
      />
      {error && (
        <span className="text-xs" style={{ color: "var(--danger)" }}>
          {error}
        </span>
      )}
    </div>
  );
}

function KpiCell({
  label,
  valueActual,
  valueTarget,
  status,
  onSave,
  suffix,
  decimals = 0,
}: {
  label: string;
  valueActual: number | null;
  valueTarget: number | null;
  status: KpiStatus;
  onSave: (raw: string) => void | Promise<void>;
  suffix: string;
  decimals?: number;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<string>(
    valueTarget === null ? "" : String(valueTarget),
  );
  // Audit fix (#11): blur and Enter both fire on Enter-press because
  // setEditing(false) unmounts the input → blur cascades → second PATCH.
  // savedRef guards: once Enter has fired the save, blur skips it.
  // Same applies to two rapid Enter presses (input is gone).
  const savedRef = useRef(false);

  // Sync draft with prop changes (e.g. parent refresh after save).
  useEffect(() => {
    setDraft(valueTarget === null ? "" : String(valueTarget));
  }, [valueTarget]);

  const fmt = (n: number | null) =>
    n === null
      ? "—"
      : decimals > 0
      ? n.toFixed(decimals)
      : String(Math.round(n));

  const colorByStatus: Record<KpiStatus, string | undefined> = {
    no_target: undefined,
    no_data: "var(--text-muted)",
    ahead: "var(--accent)",
    behind: "var(--danger)",
  };

  return (
    <div className="flex flex-col gap-0.5">
      <span className="opacity-50" style={{ fontSize: "10px" }}>
        {label}
      </span>
      <div className="flex items-center gap-1">
        <span style={{ color: colorByStatus[status] }}>
          {fmt(valueActual)}
          {suffix && ` ${suffix}`}
        </span>
        <span className="opacity-40">/</span>
        {editing ? (
          <input
            autoFocus
            type="number"
            step={decimals > 0 ? "0.1" : "1"}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={async () => {
              setEditing(false);
              // Skip if the just-fired keydown (Enter) already saved.
              if (savedRef.current) {
                savedRef.current = false;
                return;
              }
              await onSave(draft);
            }}
            onKeyDown={async (e) => {
              if (e.key === "Enter") {
                savedRef.current = true;  // signal blur to skip
                setEditing(false);
                await onSave(draft);
              } else if (e.key === "Escape") {
                savedRef.current = true;  // also skip blur save
                setEditing(false);
                setDraft(valueTarget === null ? "" : String(valueTarget));
              }
            }}
            className="bg-white/5 border border-white/20 rounded px-1 py-0.5 w-16 text-xs"
            placeholder="—"
          />
        ) : (
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="opacity-70 hover:opacity-100 underline-offset-2 hover:underline"
            title="Нажмите чтобы изменить цель"
          >
            {valueTarget === null ? "цель?" : `${fmt(valueTarget)}${suffix && ` ${suffix}`}`}
          </button>
        )}
      </div>
    </div>
  );
}
