"use client";

/**
 * Команда — sub-tab summary widget.
 *
 * Shows team-level KPIs (avg score 30d / total sessions / "тихих"
 * managers) + a per-manager mini-roster with sessions count and days
 * since last session. Embedded ABOVE the existing RopList in
 * MethodologyPanel.
 */

import { useEffect, useState } from "react";
import {
  type TeamAnalyticsResponse,
  fetchTeamAnalytics,
} from "@/lib/api/team";

interface Props {
  refreshKey?: number;
}

export function TeamAnalyticsWidget({ refreshKey = 0 }: Props) {
  const [data, setData] = useState<TeamAnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchTeamAnalytics()
      .then((d) => {
        if (!cancelled) setData(d);
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
        Загружаем аналитику команды…
      </div>
    );
  }
  if (error) {
    return (
      <div className="glass-panel rounded-xl p-4 mb-4 text-sm" style={{ color: "var(--danger)" }}>
        Не удалось загрузить аналитику: {error}
      </div>
    );
  }
  if (!data) return null;

  const fmtScore = (n: number | null) =>
    n === null ? "—" : n.toFixed(1);

  return (
    <div className="glass-panel rounded-xl p-4 mb-4 space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <Stat label="Средний скор (30д)" value={fmtScore(data.team_avg_score_30d)} />
        <Stat label="Сессий за 30д" value={String(data.team_total_sessions_30d)} />
        <Stat
          label="Без сессий 30д"
          value={String(data.managers_with_zero_sessions_30d)}
          danger={data.managers_with_zero_sessions_30d > 0}
        />
      </div>
      {data.managers.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer opacity-70 hover:opacity-100">
            Менеджеры команды ({data.managers.length})
          </summary>
          <table className="w-full mt-2 text-xs">
            <thead>
              <tr className="opacity-60">
                <th className="text-left py-1">Менеджер</th>
                <th className="text-right py-1">Сессий 30д</th>
                <th className="text-right py-1">Avg score</th>
                <th className="text-right py-1">Без сессии</th>
              </tr>
            </thead>
            <tbody>
              {data.managers.map((m) => (
                <tr key={m.user_id} className="border-t border-white/5">
                  <td className="py-1">
                    {m.full_name}
                    {!m.is_active && (
                      <span className="ml-2 text-xs" style={{ color: "var(--danger)" }}>
                        неактивен
                      </span>
                    )}
                  </td>
                  <td className="py-1 text-right tabular-nums">{m.sessions_30d}</td>
                  <td className="py-1 text-right tabular-nums">{fmtScore(m.avg_score_30d)}</td>
                  <td
                    className="py-1 text-right tabular-nums"
                    style={{
                      color:
                        m.days_since_last_session !== null && m.days_since_last_session > 14
                          ? "var(--danger)"
                          : undefined,
                    }}
                  >
                    {m.days_since_last_session === null
                      ? "никогда"
                      : `${m.days_since_last_session} дн.`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  danger,
}: {
  label: string;
  value: string;
  danger?: boolean;
}) {
  return (
    <div className="text-center">
      <div className="text-xs uppercase tracking-wider opacity-60">{label}</div>
      <div
        className="text-2xl font-bold mt-1"
        style={{ color: danger ? "var(--danger)" : "var(--accent)" }}
      >
        {value}
      </div>
    </div>
  );
}
