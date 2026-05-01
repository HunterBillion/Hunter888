"use client";

/**
 * Bulk-assign training modal — used from the Команда sub-tab.
 *
 * ROP picks a scenario from the dropdown, ticks managers from the team,
 * sets optional deadline, clicks "Назначить". Backend returns per-row
 * status; the modal shows a result table so the user sees who got
 * skipped (e.g. cross-team, deactivated).
 */

import { useEffect, useState } from "react";
import { ApiError, api } from "@/lib/api";
import { type BulkAssignResponse, bulkAssignTraining } from "@/lib/api/team";

interface ManagerOption {
  id: string;
  full_name: string;
  email: string;
  is_active: boolean;
}

interface ScenarioOption {
  id: string;
  title: string;
  scenario_code: string | null;
}

interface ScenariosListResponse {
  scenarios: ScenarioOption[];
  total?: number;
}

interface Props {
  open: boolean;
  onClose: () => void;
  onAssigned?: (resp: BulkAssignResponse) => void;
}

export function BulkAssignModal({ open, onClose, onAssigned }: Props) {
  const [managers, setManagers] = useState<ManagerOption[]>([]);
  const [scenarios, setScenarios] = useState<ScenarioOption[]>([]);
  const [selectedManagers, setSelectedManagers] = useState<Set<string>>(new Set());
  const [scenarioId, setScenarioId] = useState<string>("");
  const [deadline, setDeadline] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BulkAssignResponse | null>(null);

  useEffect(() => {
    if (!open) {
      setSelectedManagers(new Set());
      setScenarioId("");
      setDeadline("");
      setError(null);
      setResult(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    Promise.all([
      api.get<ManagerOption[]>("/users/?role=manager&limit=200"),
      api.get<ScenariosListResponse>("/rop/scenarios?page=1&page_size=200"),
    ])
      .then(([m, s]) => {
        if (cancelled) return;
        setManagers(Array.isArray(m) ? m : []);
        setScenarios(Array.isArray(s.scenarios) ? s.scenarios : []);
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
  }, [open]);

  const toggleManager = (id: string) => {
    setSelectedManagers((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const onSubmit = async () => {
    if (!scenarioId || selectedManagers.size === 0) return;
    setLoading(true);
    setError(null);
    try {
      const resp = await bulkAssignTraining(
        scenarioId,
        Array.from(selectedManagers),
        deadline || undefined,
      );
      setResult(resp);
      onAssigned?.(resp);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="glass-panel max-w-2xl w-full max-h-[90vh] overflow-y-auto rounded-2xl p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-start justify-between mb-4">
          <div>
            <h2 className="text-xl font-semibold">Массовое назначение тренинга</h2>
            <p className="text-sm opacity-70 mt-1">
              Назначить один сценарий нескольким менеджерам сразу.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="opacity-70 hover:opacity-100 px-2 py-1 text-lg leading-none"
            aria-label="Закрыть"
          >
            ×
          </button>
        </header>

        {!result && (
          <div className="space-y-4">
            <div>
              <label className="block text-xs uppercase tracking-wider opacity-60 mb-1">
                Сценарий
              </label>
              <select
                value={scenarioId}
                onChange={(e) => setScenarioId(e.target.value)}
                disabled={loading}
                className="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-sm"
              >
                <option value="">— выбрать —</option>
                {scenarios.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.title}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs uppercase tracking-wider opacity-60 mb-1">
                Менеджеры команды ({selectedManagers.size} выбрано из {managers.length})
              </label>
              <div className="border border-white/10 rounded max-h-60 overflow-y-auto">
                {managers.map((m) => (
                  <label
                    key={m.id}
                    className="flex items-center gap-2 p-2 text-sm border-b border-white/5 cursor-pointer hover:bg-white/5"
                  >
                    <input
                      type="checkbox"
                      checked={selectedManagers.has(m.id)}
                      onChange={() => toggleManager(m.id)}
                    />
                    <span className="flex-1 truncate">{m.full_name}</span>
                    <span className="text-xs opacity-60 truncate">{m.email}</span>
                    {!m.is_active && (
                      <span className="text-xs" style={{ color: "var(--danger)" }}>
                        неактивен
                      </span>
                    )}
                  </label>
                ))}
                {!managers.length && !loading && (
                  <p className="p-3 text-xs opacity-60">Менеджеры не найдены.</p>
                )}
              </div>
            </div>

            <div>
              <label className="block text-xs uppercase tracking-wider opacity-60 mb-1">
                Дедлайн (опционально)
              </label>
              <input
                type="datetime-local"
                value={deadline}
                onChange={(e) => setDeadline(e.target.value)}
                className="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-sm"
              />
            </div>

            {error && (
              <div
                className="text-sm rounded p-3 border"
                style={{
                  color: "var(--danger)",
                  background: "rgba(239,68,68,0.1)",
                  borderColor: "rgba(239,68,68,0.4)",
                }}
              >
                {error}
              </div>
            )}

            <div className="flex justify-end gap-2">
              <button
                type="button"
                className="px-4 py-2 rounded-lg opacity-70 hover:opacity-100"
                onClick={onClose}
              >
                Отмена
              </button>
              <button
                type="button"
                onClick={onSubmit}
                disabled={loading || !scenarioId || selectedManagers.size === 0}
                className="px-4 py-2 rounded-lg bg-[var(--accent)] disabled:opacity-40"
              >
                {loading ? "Назначаем…" : `Назначить (${selectedManagers.size})`}
              </button>
            </div>
          </div>
        )}

        {result && (
          <div className="space-y-4">
            <div className="rounded-lg p-3 bg-green-900/20 border border-green-700/40 text-sm">
              Назначено: {result.assigned} · пропущено: {result.skipped} · ошибок: {result.errors}
            </div>
            <table className="w-full text-xs">
              <thead className="opacity-60">
                <tr>
                  <th className="text-left py-1">user_id</th>
                  <th className="text-left py-1">статус</th>
                  <th className="text-left py-1">детали</th>
                </tr>
              </thead>
              <tbody>
                {result.rows.map((r) => (
                  <tr key={r.user_id} className="border-t border-white/5">
                    <td className="py-1 font-mono">{r.user_id.slice(0, 8)}…</td>
                    <td className="py-1">
                      <span
                        className="px-2 py-0.5 rounded text-xs"
                        style={{
                          background:
                            r.status === "assigned"
                              ? "rgba(34,197,94,0.2)"
                              : r.status === "error"
                              ? "rgba(239,68,68,0.2)"
                              : "rgba(120,120,120,0.2)",
                        }}
                      >
                        {r.status}
                      </span>
                    </td>
                    <td className="py-1 opacity-70 text-xs">{r.error || ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="flex justify-end">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 rounded-lg bg-[var(--accent)]"
              >
                Закрыть
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
