"use client";

/**
 * UsersAdminPanel — admin registry of users with inline edit modal.
 *
 * Mounted from two places:
 *   - /admin/users (admin-only, kept as a thin re-export for back-compat)
 *   - /dashboard tab "Система" sub-tab "Пользователи"
 *
 * Backed by:
 *   - GET   /users/?role=<role>&limit=N   — list (apps/api/app/api/users.py)
 *   - PATCH /admin/users/{id}             — edit role/team/is_active/full_name
 *
 * Caller is responsible for the admin role gate; this component does
 * not check itself.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, Users as UsersIcon, AlertCircle, Pencil, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { roleName } from "@/lib/guards";

interface UserListItem {
  id: string;
  email: string;
  full_name: string;
  role: string;
  team_id?: string | null;
  team_name: string | null;
  is_active: boolean;
  avatar_url: string | null;
  created_at: string;
}

const ROLE_FILTERS: { value: string; label: string }[] = [
  { value: "", label: "Все" },
  { value: "manager", label: "Менеджеры" },
  { value: "rop", label: "РОПы" },
  // methodologist filter removed 2026-04-26 — role retired, ex-methodologists
  // were migrated to rop in alembic 20260426_002. Filter by "rop" instead.
  { value: "admin", label: "Админы" },
];

const ROLE_BADGE_COLOR: Record<string, string> = {
  admin: "#ef4444",
  rop: "#a78bfa",
  methodologist: "#a78bfa",  // same as rop — stale tokens display identically
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

interface PatchUserResponse {
  user_id: string;
  email: string;
  role: string;
  team_id: string | null;
  team_name: string | null;
  is_active: boolean;
  full_name: string;
  changed_fields: string[];
  role_version_bumped: boolean;
  tokens_revoked: boolean;
}

export function UsersAdminPanel() {
  const [users, setUsers] = useState<UserListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [roleFilter, setRoleFilter] = useState<string>("");
  const [editing, setEditing] = useState<UserListItem | null>(null);

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
          Все пользователи системы. Фильтр по роли — справа. Кнопка
          «Изменить» в строке открывает модалку для смены роли, команды,
          статуса или ФИО — все правки попадают в audit_log.
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
                <th className="px-3 py-2 text-right font-semibold">Действия</th>
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
                    <td className="px-3 py-2 text-right">
                      <button
                        type="button"
                        onClick={() => setEditing(u)}
                        className="inline-flex items-center gap-1 rounded px-2 py-1 text-[11px] font-medium transition"
                        style={{
                          background: "var(--bg-secondary)",
                          color: "var(--text-secondary)",
                          border: "1px solid var(--border-color)",
                          cursor: "pointer",
                        }}
                        aria-label={`Изменить ${u.full_name || u.email}`}
                      >
                        <Pencil size={12} /> Изменить
                      </button>
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

      {editing && (
        <EditUserModal
          user={editing}
          knownTeams={Array.from(
            new Map(
              users
                .filter((u) => u.team_id && u.team_name)
                .map((u) => [u.team_id as string, u.team_name as string]),
            ).entries(),
          ).map(([id, name]) => ({ id, name }))}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            void load();
          }}
        />
      )}
    </div>
  );
}


// ── EditUserModal ─────────────────────────────────────────────────────


interface EditUserModalProps {
  user: UserListItem;
  knownTeams: { id: string; name: string }[];
  onClose: () => void;
  onSaved: () => void;
}

function EditUserModal({ user, knownTeams, onClose, onSaved }: EditUserModalProps) {
  const [role, setRole] = useState<string>(user.role);
  const [teamId, setTeamId] = useState<string>(user.team_id ?? "");
  const [isActive, setIsActive] = useState<boolean>(user.is_active);
  const [fullName, setFullName] = useState<string>(user.full_name);
  const [reason, setReason] = useState<string>("");
  const [saving, setSaving] = useState(false);
  const [errMsg, setErrMsg] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);

  const dirty = useMemo(() => {
    const fields: string[] = [];
    if (role !== user.role) fields.push("role");
    const newTeamId = teamId.trim() || null;
    const oldTeamId = user.team_id ?? null;
    if (newTeamId !== oldTeamId) fields.push("team_id");
    if (isActive !== user.is_active) fields.push("is_active");
    if (fullName.trim() !== user.full_name) fields.push("full_name");
    return fields;
  }, [role, teamId, isActive, fullName, user]);

  const canSave = dirty.length > 0 && reason.trim().length >= 8 && !saving;

  const submit = async () => {
    if (!canSave) return;
    setSaving(true);
    setErrMsg(null);
    setOkMsg(null);

    const body: Record<string, unknown> = { reason: reason.trim() };
    if (dirty.includes("role")) body.role = role;
    if (dirty.includes("team_id")) body.team_id = teamId.trim() || null;
    if (dirty.includes("is_active")) body.is_active = isActive;
    if (dirty.includes("full_name")) body.full_name = fullName.trim();

    try {
      const resp = await api.patch<PatchUserResponse>(
        `/admin/users/${user.id}`,
        body,
      );
      const summary = resp.changed_fields.join(", ") || "без изменений";
      const tail = [
        resp.role_version_bumped ? "роль обновлена" : null,
        resp.tokens_revoked ? "токены отозваны" : null,
      ]
        .filter(Boolean)
        .join("; ");
      setOkMsg(`Сохранено (${summary})${tail ? " — " + tail : ""}`);
      setTimeout(onSaved, 800);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : String(err);
      setErrMsg(msg);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`Редактирование ${user.full_name || user.email}`}
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.55)",
        zIndex: 100,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "16px",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="rounded-xl"
        style={{
          background: "var(--bg-panel)",
          border: "1px solid var(--border-color)",
          maxWidth: 520,
          width: "100%",
          maxHeight: "90vh",
          overflowY: "auto",
        }}
      >
        <div
          className="flex items-center justify-between px-5 py-3"
          style={{ borderBottom: "1px solid var(--border-color)" }}
        >
          <div>
            <div className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
              Редактирование пользователя
            </div>
            <div className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
              {user.email}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Закрыть"
            style={{
              background: "transparent",
              border: "none",
              color: "var(--text-muted)",
              cursor: "pointer",
              padding: 4,
            }}
          >
            <X size={18} />
          </button>
        </div>

        <div className="px-5 py-4 space-y-3">
          <Field label="ФИО">
            <input
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              maxLength={200}
              style={inputStyle}
            />
          </Field>

          <Field label="Роль">
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              style={inputStyle}
            >
              <option value="manager">Менеджер</option>
              <option value="rop">РОП</option>
              <option value="admin">Администратор</option>
            </select>
          </Field>

          <Field label="Команда">
            <div className="flex items-center gap-2">
              <select
                value={teamId}
                onChange={(e) => setTeamId(e.target.value)}
                style={{ ...inputStyle, flex: 1 }}
              >
                <option value="">— без команды —</option>
                {knownTeams.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
                {/* If the current team isn't in the dropdown (e.g. admin
                    sees a manager from a team that filter excluded),
                    keep the existing team_id selectable so the patch
                    doesn't accidentally clear it. */}
                {teamId &&
                  !knownTeams.some((t) => t.id === teamId) && (
                    <option value={teamId}>(текущая, id={teamId.slice(0, 8)}…)</option>
                  )}
              </select>
              <input
                type="text"
                value={teamId}
                onChange={(e) => setTeamId(e.target.value)}
                placeholder="UUID или пусто"
                style={{ ...inputStyle, width: 180, fontFamily: "monospace", fontSize: 11 }}
              />
            </div>
          </Field>

          <Field label="Статус">
            <label className="flex items-center gap-2 text-sm" style={{ color: "var(--text-secondary)" }}>
              <input
                type="checkbox"
                checked={isActive}
                onChange={(e) => setIsActive(e.target.checked)}
              />
              {isActive ? "Активен" : "Деактивирован (токены будут отозваны)"}
            </label>
          </Field>

          <Field label={`Причина изменения (${reason.trim().length}/8 минимум, обязательно для audit_log)`}>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={2}
              maxLength={500}
              placeholder="Например: «Перевод из команды Sales в B2B по запросу руководителя»"
              style={{ ...inputStyle, resize: "vertical" }}
            />
          </Field>

          {dirty.length > 0 && (
            <div
              className="text-xs px-3 py-2 rounded"
              style={{
                background: "rgba(167,139,250,0.08)",
                border: "1px solid rgba(167,139,250,0.3)",
                color: "var(--text-secondary)",
              }}
            >
              К сохранению: {dirty.join(", ")}
            </div>
          )}

          {errMsg && (
            <div
              className="text-xs px-3 py-2 rounded"
              style={{
                background: "rgba(239,68,68,0.08)",
                border: "1px solid rgba(239,68,68,0.35)",
                color: "#ef4444",
              }}
            >
              {errMsg}
            </div>
          )}
          {okMsg && (
            <div
              className="text-xs px-3 py-2 rounded"
              style={{
                background: "rgba(34,197,94,0.08)",
                border: "1px solid rgba(34,197,94,0.35)",
                color: "#22c55e",
              }}
            >
              {okMsg}
            </div>
          )}
        </div>

        <div
          className="flex items-center justify-end gap-2 px-5 py-3"
          style={{ borderTop: "1px solid var(--border-color)" }}
        >
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            style={{
              ...buttonStyle,
              background: "transparent",
              border: "1px solid var(--border-color)",
              color: "var(--text-secondary)",
            }}
          >
            Отмена
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={!canSave}
            style={{
              ...buttonStyle,
              background: canSave ? "var(--accent)" : "var(--bg-secondary)",
              color: canSave ? "white" : "var(--text-muted)",
              cursor: canSave ? "pointer" : "not-allowed",
            }}
          >
            {saving ? <Loader2 size={14} className="animate-spin" /> : "Сохранить"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <div className="text-[11px] uppercase tracking-wider mb-1" style={{ color: "var(--text-muted)" }}>
        {label}
      </div>
      {children}
    </label>
  );
}

const inputStyle: React.CSSProperties = {
  width: "100%",
  background: "var(--bg-secondary)",
  border: "1px solid var(--border-color)",
  color: "var(--text-primary)",
  borderRadius: 6,
  padding: "8px 10px",
  fontSize: 13,
};

const buttonStyle: React.CSSProperties = {
  borderRadius: 6,
  padding: "6px 14px",
  fontSize: 13,
  fontWeight: 500,
  border: "none",
};
