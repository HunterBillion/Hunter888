"use client";

/**
 * /admin/users — read-only registry of users.
 *
 * Backed by GET /users/?role=<role>&limit=N which the backend already
 * exposes (apps/api/app/api/users.py:501). Showing this list is the
 * single biggest gap the admin panel had: managers, ROPs, and
 * methodologists existed in the DB but the panel had no page to
 * inspect them.
 *
 * Auth + AuthLayout + role-guard handled by the parent admin/layout.tsx.
 */

import { useCallback, useEffect, useState } from "react";
import { Loader2, Users as UsersIcon, AlertCircle } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { roleName } from "@/lib/guards";

interface UserListItem {
  id: string;
  email: string;
  full_name: string;
  role: string;
  team_name: string | null;
  is_active: boolean;
  avatar_url: string | null;
  created_at: string;
}

const ROLE_FILTERS: { value: string; label: string }[] = [
  { value: "", label: "Все" },
  { value: "manager", label: "Менеджеры" },
  { value: "rop", label: "РОПы" },
  { value: "methodologist", label: "Методологи" },
  { value: "admin", label: "Админы" },
];

const ROLE_BADGE_COLOR: Record<string, string> = {
  admin: "#ef4444",
  rop: "#a78bfa",
  methodologist: "#fbbf24",
  manager: "#22c55e",
};

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

export default function AdminUsersPage() {
  const [users, setUsers] = useState<UserListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [roleFilter, setRoleFilter] = useState<string>("");

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    try {
      const qs = roleFilter
        ? `?role=${encodeURIComponent(roleFilter)}&limit=200`
        : "?limit=200";
      const data = await api.get<UserListItem[]>(
        `/users/${qs}`,
        signal ? { signal } : undefined,
      );
      if (signal?.aborted) return;
      setUsers(Array.isArray(data) ? data : []);
    } catch (err) {
      if (signal?.aborted) return;
      if (err instanceof DOMException && err.name === "AbortError") return;
      const msg = err instanceof ApiError ? err.message : String(err);
      setError(msg);
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [roleFilter]);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  return (
    <div className="space-y-4 max-w-6xl">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <p className="text-sm max-w-2xl" style={{ color: "var(--text-muted)" }}>
          Все пользователи системы. Фильтр по роли — справа. Чтобы изменить
          роль или забанить пользователя, используйте бэкенд-эндпоинты —
          UI для этого пока не реализован.
        </p>

        <div
          className="flex items-center gap-1 rounded-lg p-1"
          style={{
            background: "var(--bg-secondary)",
            border: "1px solid var(--border-color)",
          }}
          role="tablist"
        >
          {ROLE_FILTERS.map(({ value, label }) => {
            const active = roleFilter === value;
            return (
              <button
                key={value || "all"}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => setRoleFilter(value)}
                className="px-3 py-1.5 text-xs font-medium rounded-md transition"
                style={{
                  background: active ? "var(--accent)" : "transparent",
                  color: active ? "white" : "var(--text-secondary)",
                  border: "none",
                  cursor: "pointer",
                }}
              >
                {label}
              </button>
            );
          })}
        </div>
      </div>

      {error && (
        <div
          className="rounded-xl p-4 flex items-start gap-3"
          style={{
            background: "rgba(239,68,68,0.08)",
            border: "1px solid rgba(239,68,68,0.35)",
            color: "#ef4444",
          }}
        >
          <AlertCircle size={18} />
          <div className="flex-1 text-sm">{error}</div>
          <button
            type="button"
            onClick={() => load()}
            className="text-xs underline"
            style={{ color: "#ef4444" }}
          >
            Повторить
          </button>
        </div>
      )}

      {loading && users.length === 0 ? (
        <div
          className="rounded-xl p-6 flex items-center gap-3"
          style={{
            background: "var(--bg-panel)",
            border: "1px solid var(--border-color)",
            color: "var(--text-muted)",
          }}
        >
          <Loader2 size={16} className="animate-spin" />
          Загружаю список…
        </div>
      ) : null}

      {!loading && !error && users.length === 0 && (
        <div
          className="rounded-xl p-8 text-sm text-center"
          style={{
            background: "var(--bg-panel)",
            border: "1px dashed var(--border-color)",
            color: "var(--text-muted)",
          }}
        >
          <UsersIcon size={32} style={{ margin: "0 auto 8px", opacity: 0.4 }} />
          Список пуст
        </div>
      )}

      {users.length > 0 && (
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
                <th className="px-3 py-2 text-left font-semibold">Имя</th>
                <th className="px-3 py-2 text-left font-semibold">Email</th>
                <th className="px-3 py-2 text-left font-semibold">Роль</th>
                <th className="px-3 py-2 text-left font-semibold">Команда</th>
                <th className="px-3 py-2 text-left font-semibold">Статус</th>
                <th className="px-3 py-2 text-left font-semibold">Создан</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => {
                const color = ROLE_BADGE_COLOR[u.role] ?? "var(--text-muted)";
                return (
                  <tr
                    key={u.id}
                    style={{
                      borderTop: "1px solid var(--border-color)",
                      color: "var(--text-secondary)",
                      opacity: u.is_active ? 1 : 0.5,
                    }}
                  >
                    <td className="px-3 py-2" style={{ color: "var(--text-primary)" }}>
                      {u.full_name || "—"}
                    </td>
                    <td className="px-3 py-2 font-mono text-[12px]">{u.email}</td>
                    <td className="px-3 py-2">
                      <span
                        className="inline-flex rounded px-2 py-0.5 text-[11px] font-medium"
                        style={{
                          background: `${color}1a`,
                          color,
                          border: `1px solid ${color}33`,
                        }}
                      >
                        {roleName(u.role)}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-[12px]">
                      {u.team_name ?? "—"}
                    </td>
                    <td className="px-3 py-2 text-[12px]">
                      {u.is_active ? (
                        <span style={{ color: "#22c55e" }}>активен</span>
                      ) : (
                        <span style={{ color: "var(--text-muted)" }}>неактивен</span>
                      )}
                    </td>
                    <td className="px-3 py-2 font-mono text-[11px]" style={{ color: "var(--text-muted)" }}>
                      {formatDate(u.created_at)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div
            className="px-3 py-2 text-xs"
            style={{
              color: "var(--text-muted)",
              borderTop: "1px solid var(--border-color)",
            }}
          >
            Показано {users.length} {users.length === 1 ? "пользователь" : "пользователей"}
          </div>
        </div>
      )}
    </div>
  );
}
