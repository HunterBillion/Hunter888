"use client";

/**
 * Standalone KPI editor for the Команда sub-tab.
 *
 * Loads managers via `GET /users/?role=manager` (already used by
 * MethodologyPanel) and renders a KpiInlineEditor row per manager.
 * Independent of PR #122's TeamAnalyticsWidget — when both ship,
 * the widget can pass real `actualSessions30d` etc. to this editor
 * via props for live progress indicators.
 *
 * Until then, the editor renders target-only (actuals shown as "—").
 */

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { KpiInlineEditor } from "./KpiInlineEditor";

interface ManagerListItem {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
}

interface Props {
  /** Optional refresh-trigger from the parent (e.g. after a CSV import). */
  refreshKey?: number;
}

export function TeamKpiPanel({ refreshKey = 0 }: Props) {
  const [managers, setManagers] = useState<ManagerListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .get<ManagerListItem[]>("/users/?role=manager&limit=200")
      .then((data) => {
        if (!cancelled) setManagers(Array.isArray(data) ? data : []);
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

  return (
    <details className="glass-panel rounded-xl p-4 mb-4">
      <summary className="cursor-pointer text-sm font-semibold select-none">
        Цели менеджеров (KPI)
        <span className="ml-2 opacity-60 font-normal">
          {managers.length} {managers.length === 1 ? "менеджер" : "менеджеров"}
        </span>
      </summary>
      <p className="text-xs opacity-60 mt-2">
        Нажмите цель чтобы изменить. Пустое поле = «нет цели»
        (индикатор скроется). Прогресс-бар появится после деплоя
        аналитики команды.
      </p>
      <div className="mt-3 space-y-3">
        {managers.map((m) => (
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
            <KpiInlineEditor userId={m.id} fullName={m.full_name} />
          </div>
        ))}
      </div>
    </details>
  );
}
