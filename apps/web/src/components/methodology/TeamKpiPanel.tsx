"use client";

/**
 * Standalone KPI editor for the Команда sub-tab.
 *
 * Loads managers via `GET /users/?role=manager` AND live actuals via
 * `GET /team/analytics` (PR #122). Builds a userId → actuals map and
 * passes per-manager numbers down to KpiInlineEditor so the cells
 * render coloured progress badges (red/accent) instead of just "—".
 *
 * Bridge note: this used to load managers only and the editor showed
 * actuals as "—" because TeamAnalyticsWidget held them in its own
 * state. After PR #122 + #151 both landed on main, this component is
 * the single owner of the analytics fetch for the KPI surface — the
 * widget keeps its own fetch for the team-level header (analytics is
 * a small endpoint, two parallel calls is fine for a pilot of 15
 * testers).
 */

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { KpiInlineEditor } from "./KpiInlineEditor";
import {
  type TeamAnalyticsResponse,
  fetchTeamAnalytics,
} from "@/lib/api/team";

interface ManagerListItem {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
}

interface ActualBundle {
  sessions30d: number | null;
  avgScore30d: number | null;
  daysSinceLastSession: number | null;
}

interface Props {
  /** Optional refresh-trigger from the parent (e.g. after a CSV import). */
  refreshKey?: number;
}

export function TeamKpiPanel({ refreshKey = 0 }: Props) {
  const [managers, setManagers] = useState<ManagerListItem[]>([]);
  const [actualsByUserId, setActualsByUserId] = useState<Record<string, ActualBundle>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [analyticsError, setAnalyticsError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setAnalyticsError(null);

    // Two parallel fetches. If analytics fails (e.g. caller is admin
    // with no team_id), we degrade gracefully — managers still render,
    // editor shows "—" instead of progress badges. Doesn't fail the
    // whole panel.
    const managersP = api
      .get<ManagerListItem[]>("/users/?role=manager&limit=200")
      .catch((e) => {
        throw new Error(
          "Не удалось загрузить менеджеров: " +
            (e instanceof Error ? e.message : String(e)),
        );
      });
    const analyticsP = fetchTeamAnalytics().catch((e) => {
      // Soft-fail: stash the error, return null → no actuals.
      if (!cancelled)
        setAnalyticsError(e instanceof Error ? e.message : String(e));
      return null as TeamAnalyticsResponse | null;
    });

    Promise.all([managersP, analyticsP])
      .then(([m, a]) => {
        if (cancelled) return;
        setManagers(Array.isArray(m) ? m : []);
        if (a && Array.isArray(a.managers)) {
          const map: Record<string, ActualBundle> = {};
          for (const row of a.managers) {
            map[row.user_id] = {
              sessions30d: row.sessions_30d,
              avgScore30d: row.avg_score_30d,
              daysSinceLastSession: row.days_since_last_session,
            };
          }
          setActualsByUserId(map);
        }
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
  }, [refreshKey]);

  if (loading) {
    return (
      <div className="glass-panel rounded-xl p-4 mb-4 text-sm opacity-60">
        Загружаем менеджеров команды…
      </div>
    );
  }
  if (error) {
    return (
      <div
        className="glass-panel rounded-xl p-4 mb-4 text-sm"
        style={{ color: "var(--danger)" }}
      >
        Не удалось загрузить менеджеров: {error}
      </div>
    );
  }
  if (managers.length === 0) {
    return null; // RopList shows its own empty state
  }

  const haveActuals = Object.keys(actualsByUserId).length > 0;

  return (
    <details className="glass-panel rounded-xl p-4 mb-4">
      <summary className="cursor-pointer text-sm font-semibold select-none">
        Цели менеджеров (KPI)
        <span className="ml-2 opacity-60 font-normal">
          {managers.length} {managers.length === 1 ? "менеджер" : "менеджеров"}
        </span>
      </summary>
      <p className="text-xs opacity-60 mt-2">
        {haveActuals
          ? "Нажмите цель чтобы изменить. Цветной значок справа — прогресс относительно цели за последние 30 дней."
          : "Нажмите цель чтобы изменить. Пустое поле = «нет цели» (индикатор скроется)."}
      </p>
      {analyticsError && !haveActuals && (
        <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
          ⚠ Прогресс не загрузился ({analyticsError}). Цели редактируются, бейджи отключены.
        </p>
      )}
      <div className="mt-3 space-y-3">
        {managers.map((m) => {
          const actual = actualsByUserId[m.id];
          return (
            <div
              key={m.id}
              className="border-t border-white/5 pt-3 first:border-t-0 first:pt-0"
            >
              <div className="text-sm font-medium mb-1">
                {m.full_name}
                {!m.is_active && (
                  <span
                    className="ml-2 text-xs"
                    style={{ color: "var(--danger)" }}
                  >
                    неактивен
                  </span>
                )}
                <span className="ml-2 text-xs opacity-50">{m.email}</span>
              </div>
              <KpiInlineEditor
                userId={m.id}
                fullName={m.full_name}
                actualSessions30d={actual?.sessions30d ?? null}
                actualAvgScore30d={actual?.avgScore30d ?? null}
                actualDaysSinceLast={actual?.daysSinceLastSession ?? null}
              />
            </div>
          );
        })}
      </div>
    </details>
  );
}
