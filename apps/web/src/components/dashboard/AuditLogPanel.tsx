"use client";

/**
 * AuditLogPanel — reusable 152-ФЗ audit-log table.
 *
 * Mounted from two places:
 *   - /admin/audit-log (admin-only, full system scope)
 *   - /dashboard tab "Аудит-журнал" (admin → all; ROP → own team only,
 *     enforced server-side via require_role("admin","rop") + actor.team_id
 *     subquery in apps/api/app/api/clients.py::api_get_audit_log)
 *
 * The `scope` prop is purely cosmetic — it tweaks the header subtitle so
 * the user knows whose actions they're seeing. The actual data filtering
 * happens on the backend based on the caller's role.
 */

import { useEffect, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ShieldCheck,
  Loader2,
  ChevronLeft,
  ChevronRight,
  Filter,
  X,
  Eye,
  UserPlus,
  Pencil,
  Trash2,
  FileCheck,
  FileX,
  Download,
  Bell,
  GitMerge,
  Shuffle,
  Activity,
  Calendar,
  Layers,
  Zap,
} from "lucide-react";
import { api } from "@/lib/api";
import { formatDateTimeFull } from "@/lib/utils";

interface AuditLogEntry {
  id: string;
  actor_id: string | null;
  actor_name: string | null;
  actor_role: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  old_values: Record<string, unknown> | null;
  new_values: Record<string, unknown> | null;
  ip_address: string | null;
  created_at: string;
}

interface AuditLogResponse {
  items: AuditLogEntry[];
  total: number;
  page: number;
  per_page: number;
}

const ACTION_META: Record<string, { label: string; icon: typeof Eye; color: string }> = {
  view_client:       { label: "Просмотр",           icon: Eye,       color: "var(--info)" },
  create_client:     { label: "Создание клиента",   icon: UserPlus,  color: "var(--success)" },
  update_client:     { label: "Обновление",         icon: Pencil,    color: "var(--warning)" },
  delete_client:     { label: "Удаление",           icon: Trash2,    color: "var(--danger)" },
  grant_consent:     { label: "Согласие выдано",     icon: FileCheck, color: "var(--success)" },
  revoke_consent:    { label: "Согласие отозвано",   icon: FileX,     color: "var(--danger)" },
  export_data:       { label: "Экспорт данных",     icon: Download,  color: "var(--accent-hover)" },
  send_notification: { label: "Уведомление",        icon: Bell,      color: "var(--info)" },
  change_status:     { label: "Смена статуса",      icon: Activity,  color: "var(--warning)" },
  merge_clients:     { label: "Объединение",        icon: GitMerge,  color: "var(--accent-hover)" },
  bulk_reassign:     { label: "Перераспределение",  icon: Shuffle,   color: "#F472B6" },
  // TZ-4 D2 — attachment pipeline writes audit log on every upload
  // (apps/api/app/api/clients.py:733). Surface here so the activity
  // tab can filter document uploads alongside CRM actions.
  upload_attachment: { label: "Загружен документ",  icon: FileCheck, color: "var(--accent)" },
};

const ENTITY_LABELS: Record<string, string> = {
  real_clients:        "Клиенты",
  client_consents:     "Согласия",
  client_interactions: "Взаимодействия",
  // TZ-4 D2 entity surface — attachment pipeline write-audit rows.
  attachments:         "Документы",
};

const ROLE_LABELS: Record<string, string> = {
  admin:        "Админ",
  rop:          "РОП",
  manager:      "Менеджер",
  methodologist:"РОП",  // legacy enum — retired 2026-04-26, displays as ROP for stale tokens
  system:       "Система",
};


/**
 * Russian plural form for audit-log row counts.
 *   1, 21, 31… → "запись"
 *   2-4, 22-24, 32-34… → "записи"
 *   0, 5-20, 25-30, 100… → "записей"
 * `total < 5` ladder is wrong for {11..14}, {21..24}, etc.
 */
export function pluralizeEntries(n: number): string {
  const abs = Math.abs(n) % 100;
  const last = abs % 10;
  if (abs > 10 && abs < 20) return "записей";
  if (last === 1) return "запись";
  if (last >= 2 && last <= 4) return "записи";
  return "записей";
}

/**
 * `<input type="date">` returns "YYYY-MM-DD". `new Date(s).toISOString()`
 * parses that as UTC midnight, then converts to UTC ISO — which for any
 * browser TZ east of UTC shifts the boundary to "earlier than the user
 * meant". Russian users picking "from 2026-05-05" otherwise miss the
 * 00:00–03:00 MSK slice. Build the boundary in local time and convert.
 */
export function localDateBoundary(date: string, mode: "start" | "end"): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date);
  if (m) {
    const [, y, mo, d] = m;
    const local = mode === "start"
      ? new Date(Number(y), Number(mo) - 1, Number(d), 0, 0, 0, 0)
      : new Date(Number(y), Number(mo) - 1, Number(d), 23, 59, 59, 999);
    return local.toISOString();
  }
  // Defensive fallback — `<input type="date">` only emits "YYYY-MM-DD" or
  // empty (gated upstream), so this branch should be unreachable. Don't
  // throw on garbage: hand back the original string and let the backend
  // validator surface the error.
  const fallback = new Date(date);
  return Number.isNaN(fallback.getTime()) ? date : fallback.toISOString();
}

function actionBadge(action: string) {
  const meta = ACTION_META[action] || { label: action, icon: Zap, color: "#94A3B8" };
  const Icon = meta.icon;
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium"
      style={{ background: `${meta.color}18`, color: meta.color, border: `1px solid ${meta.color}33` }}
    >
      <Icon size={12} />
      {meta.label}
    </span>
  );
}

function DiffViewer({ oldValues, newValues }: { oldValues: Record<string, unknown> | null; newValues: Record<string, unknown> | null }) {
  if (!oldValues && !newValues) return <span style={{ color: "var(--text-muted)" }}>—</span>;
  const allKeys = Array.from(new Set([
    ...Object.keys(oldValues || {}),
    ...Object.keys(newValues || {}),
  ]));
  return (
    <div className="space-y-1 text-xs" style={{ fontFamily: "var(--font-mono)" }}>
      {allKeys.map((key) => {
        const oldVal = oldValues?.[key];
        const newVal = newValues?.[key];
        const changed = JSON.stringify(oldVal) !== JSON.stringify(newVal);
        if (!changed && oldVal === undefined) return null;
        return (
          <div key={key} className="flex gap-2">
            <span style={{ color: "var(--text-muted)", minWidth: 120 }}>{key}:</span>
            {changed ? (
              <>
                {oldVal !== undefined && (
                  <span style={{ color: "var(--danger)", textDecoration: "line-through" }}>
                    {String(oldVal ?? "null")}
                  </span>
                )}
                {newVal !== undefined && (
                  <span style={{ color: "var(--success)" }}>
                    {String(newVal ?? "null")}
                  </span>
                )}
              </>
            ) : (
              <span style={{ color: "var(--text-secondary)" }}>{String(oldVal)}</span>
            )}
          </div>
        );
      })}
    </div>
  );
}

interface Props {
  /** Cosmetic scope hint — backend enforces actual filtering based on caller role. */
  scope?: "all" | "team";
}

export function AuditLogPanel({ scope = "all" }: Props) {
  const [entries, setEntries] = useState<AuditLogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [perPage] = useState(25);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterAction, setFilterAction] = useState("");
  const [filterEntity, setFilterEntity] = useState("");
  const [filterDateFrom, setFilterDateFrom] = useState("");
  const [filterDateTo, setFilterDateTo] = useState("");
  const [showFilters, setShowFilters] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      params.set("page", String(page));
      params.set("per_page", String(perPage));
      if (filterAction) params.set("action", filterAction);
      if (filterEntity) params.set("entity_type", filterEntity);
      if (filterDateFrom) params.set("date_from", localDateBoundary(filterDateFrom, "start"));
      if (filterDateTo) params.set("date_to", localDateBoundary(filterDateTo, "end"));

      const resp: AuditLogResponse = await api.get(`/clients/audit-log?${params.toString()}`);
      setEntries(resp.items);
      setTotal(resp.total);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Ошибка загрузки";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [page, perPage, filterAction, filterEntity, filterDateFrom, filterDateTo]);

  useEffect(() => { fetchLogs(); }, [fetchLogs]);

  const totalPages = Math.ceil(total / perPage) || 1;
  const clearFilters = () => {
    setFilterAction("");
    setFilterEntity("");
    setFilterDateFrom("");
    setFilterDateTo("");
    setPage(1);
  };
  const hasActiveFilters = filterAction || filterEntity || filterDateFrom || filterDateTo;

  return (
    <div style={{ maxWidth: 1200, margin: "0 auto" }}>
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        className="flex items-center justify-between flex-wrap gap-4"
        style={{ marginBottom: 24 }}
      >
        <p className="text-sm" style={{ color: "var(--text-muted)", margin: 0 }}>
          {scope === "team"
            ? "Действия членов вашей команды с клиентскими данными"
            : "152-ФЗ · Все действия с персональными данными"}
        </p>

        <div className="flex items-center gap-2">
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => setShowFilters((v) => !v)}
            className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium"
            style={{
              background: showFilters ? "var(--accent)" : "var(--glass-bg)",
              color: showFilters ? "#000" : "var(--text-primary)",
              border: `1px solid ${showFilters ? "var(--accent)" : "var(--glass-border)"}`,
              cursor: "pointer",
            }}
          >
            <Filter size={15} />
            Фильтры
            {hasActiveFilters && (
              <span
                className="flex h-4 w-4 items-center justify-center rounded-full text-xs font-bold"
                style={{ background: "var(--danger)", color: "#fff" }}
              >
                !
              </span>
            )}
          </motion.button>
          <span style={{ color: "var(--text-muted)", fontSize: 14 }}>
            {total} {pluralizeEntries(total)}
          </span>
        </div>
      </motion.div>

      <AnimatePresence>
        {showFilters && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.25 }}
            className="glass-panel rounded-xl overflow-hidden"
            style={{ marginBottom: 16, padding: 16 }}
          >
            <div className="flex items-center justify-between" style={{ marginBottom: 12 }}>
              <span style={{ color: "var(--text-primary)", fontSize: 14, fontWeight: 600 }}>Фильтры</span>
              {hasActiveFilters && (
                <button
                  onClick={clearFilters}
                  className="flex items-center gap-1 text-xs"
                  style={{ color: "var(--danger)", background: "none", border: "none", cursor: "pointer" }}
                >
                  <X size={12} /> Сбросить
                </button>
              )}
            </div>

            <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))" }}>
              <div>
                <label style={{ fontSize: 14, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>
                  <Zap size={14} style={{ display: "inline", marginRight: 4 }} />
                  Действие
                </label>
                <select
                  value={filterAction}
                  onChange={(e) => { setFilterAction(e.target.value); setPage(1); }}
                  style={{ width: "100%", padding: "6px 10px", borderRadius: 8, background: "var(--input-bg)", color: "var(--text-primary)", border: "1px solid var(--border-color)", fontSize: 14 }}
                >
                  <option value="">Все действия</option>
                  {Object.entries(ACTION_META).map(([key, meta]) => (
                    <option key={key} value={key}>{meta.label}</option>
                  ))}
                </select>
              </div>

              <div>
                <label style={{ fontSize: 14, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>
                  <Layers size={14} style={{ display: "inline", marginRight: 4 }} />
                  Тип сущности
                </label>
                <select
                  value={filterEntity}
                  onChange={(e) => { setFilterEntity(e.target.value); setPage(1); }}
                  style={{ width: "100%", padding: "6px 10px", borderRadius: 8, background: "var(--input-bg)", color: "var(--text-primary)", border: "1px solid var(--border-color)", fontSize: 14 }}
                >
                  <option value="">Все типы</option>
                  {Object.entries(ENTITY_LABELS).map(([key, label]) => (
                    <option key={key} value={key}>{label}</option>
                  ))}
                </select>
              </div>

              <div>
                <label style={{ fontSize: 14, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>
                  <Calendar size={14} style={{ display: "inline", marginRight: 4 }} />
                  Дата от
                </label>
                <input
                  type="date"
                  value={filterDateFrom}
                  onChange={(e) => { setFilterDateFrom(e.target.value); setPage(1); }}
                  style={{ width: "100%", padding: "6px 10px", borderRadius: 8, background: "var(--input-bg)", color: "var(--text-primary)", border: "1px solid var(--border-color)", fontSize: 14 }}
                />
              </div>

              <div>
                <label style={{ fontSize: 14, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>
                  <Calendar size={14} style={{ display: "inline", marginRight: 4 }} />
                  Дата до
                </label>
                <input
                  type="date"
                  value={filterDateTo}
                  onChange={(e) => { setFilterDateTo(e.target.value); setPage(1); }}
                  style={{ width: "100%", padding: "6px 10px", borderRadius: 8, background: "var(--input-bg)", color: "var(--text-primary)", border: "1px solid var(--border-color)", fontSize: 14 }}
                />
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {error && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="glass-panel rounded-xl"
          style={{ padding: 24, textAlign: "center", color: "var(--danger)", marginBottom: 16 }}
        >
          {error}
        </motion.div>
      )}

      {loading && (
        <div className="flex items-center justify-center" style={{ padding: 80 }}>
          <Loader2 size={28} className="animate-spin" style={{ color: "var(--accent)" }} />
        </div>
      )}

      {!loading && !error && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
          className="glass-panel rounded-xl overflow-hidden"
        >
          <div
            className="grid items-center gap-3 px-4 py-3 text-xs font-semibold"
            style={{
              gridTemplateColumns: "160px 1fr 120px 120px 100px 40px",
              color: "var(--text-muted)",
              borderBottom: "1px solid var(--border-color)",
              textTransform: "uppercase",
              letterSpacing: "0.05em",
            }}
          >
            <span>Дата</span>
            <span>Действие</span>
            <span>Сущность</span>
            <span>Исполнитель</span>
            <span>Роль</span>
            <span></span>
          </div>

          {entries.length === 0 ? (
            <div style={{ padding: 48, textAlign: "center", color: "var(--text-muted)" }}>
              <ShieldCheck size={40} style={{ margin: "0 auto 12px", opacity: 0.3 }} />
              <p style={{ margin: 0 }}>Записей не найдено</p>
            </div>
          ) : (
            entries.map((entry) => (
              <motion.div
                key={entry.id}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.2 }}
              >
                <div
                  className="grid items-center gap-3 px-4 py-3"
                  style={{
                    gridTemplateColumns: "160px 1fr 120px 120px 100px 40px",
                    borderBottom: "1px solid var(--border-color)",
                    cursor: (entry.old_values || entry.new_values) ? "pointer" : "default",
                    background: expandedId === entry.id ? "var(--input-bg)" : "transparent",
                    transition: "background 0.15s",
                  }}
                  onClick={() => {
                    if (entry.old_values || entry.new_values) {
                      setExpandedId(expandedId === entry.id ? null : entry.id);
                    }
                  }}
                >
                  <span style={{ fontSize: 14, color: "var(--text-secondary)", fontFamily: "var(--font-mono)" }}>
                    {formatDateTimeFull(entry.created_at)}
                  </span>
                  <div>{actionBadge(entry.action)}</div>
                  <span style={{ fontSize: 14, color: "var(--text-secondary)" }}>
                    {ENTITY_LABELS[entry.entity_type] || entry.entity_type}
                  </span>
                  <span
                    style={{ fontSize: 14, color: "var(--text-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                    title={entry.actor_name || "Система"}
                  >
                    {entry.actor_name || "Система"}
                  </span>
                  <span
                    className="inline-flex rounded px-1.5 py-0.5 text-xs font-medium"
                    style={{ background: "var(--input-bg)", color: "var(--text-muted)", border: "1px solid var(--border-color)" }}
                  >
                    {ROLE_LABELS[entry.actor_role || ""] || entry.actor_role || "—"}
                  </span>
                  <div style={{ textAlign: "center" }}>
                    {(entry.old_values || entry.new_values) && (
                      <motion.span
                        animate={{ rotate: expandedId === entry.id ? 90 : 0 }}
                        style={{ display: "inline-block", color: "var(--text-muted)" }}
                      >
                        ▸
                      </motion.span>
                    )}
                  </div>
                </div>

                <AnimatePresence>
                  {expandedId === entry.id && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      exit={{ opacity: 0, height: 0 }}
                      transition={{ duration: 0.2 }}
                      style={{
                        padding: "12px 20px 16px",
                        background: "var(--input-bg)",
                        borderBottom: "1px solid var(--border-color)",
                        overflow: "hidden",
                      }}
                    >
                      <div className="grid gap-4" style={{ gridTemplateColumns: "1fr 1fr" }}>
                        <div className="space-y-2 text-xs">
                          <div>
                            <span style={{ color: "var(--text-muted)" }}>ID записи: </span>
                            <span style={{ color: "var(--text-secondary)", fontFamily: "var(--font-mono)" }}>
                              {entry.id.slice(0, 8)}…
                            </span>
                          </div>
                          {entry.entity_id && (
                            <div>
                              <span style={{ color: "var(--text-muted)" }}>ID сущности: </span>
                              <span style={{ color: "var(--text-secondary)", fontFamily: "var(--font-mono)" }}>
                                {entry.entity_id.slice(0, 8)}…
                              </span>
                            </div>
                          )}
                          {entry.ip_address && (
                            <div>
                              <span style={{ color: "var(--text-muted)" }}>IP: </span>
                              <span style={{ color: "var(--text-secondary)", fontFamily: "var(--font-mono)" }}>
                                {entry.ip_address}
                              </span>
                            </div>
                          )}
                        </div>
                        <div>
                          <span style={{ color: "var(--text-muted)", fontSize: 14, display: "block", marginBottom: 6 }}>
                            Изменения:
                          </span>
                          <DiffViewer oldValues={entry.old_values} newValues={entry.new_values} />
                        </div>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
            ))
          )}

          {total > perPage && (
            <div
              className="flex items-center justify-between px-4 py-3"
              style={{ borderTop: "1px solid var(--border-color)" }}
            >
              <span style={{ fontSize: 14, color: "var(--text-muted)" }}>
                Стр. {page} из {totalPages}
              </span>
              <div className="flex gap-2">
                <button
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  className="flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs font-medium"
                  style={{
                    background: "var(--glass-bg)",
                    color: page <= 1 ? "var(--text-muted)" : "var(--text-primary)",
                    border: "1px solid var(--glass-border)",
                    cursor: page <= 1 ? "not-allowed" : "pointer",
                    opacity: page <= 1 ? 0.5 : 1,
                  }}
                >
                  <ChevronLeft size={14} /> Назад
                </button>
                <button
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  className="flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs font-medium"
                  style={{
                    background: "var(--glass-bg)",
                    color: page >= totalPages ? "var(--text-muted)" : "var(--text-primary)",
                    border: "1px solid var(--glass-border)",
                    cursor: page >= totalPages ? "not-allowed" : "pointer",
                    opacity: page >= totalPages ? 0.5 : 1,
                  }}
                >
                  Вперёд <ChevronRight size={14} />
                </button>
              </div>
            </div>
          )}
        </motion.div>
      )}
    </div>
  );
}
