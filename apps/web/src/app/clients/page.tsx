"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Search, Filter, Plus, Loader2, ChevronDown, Check, UserCheck, Download, X } from "lucide-react";
import { UsersThree } from "@phosphor-icons/react";
import { api } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import AuthLayout from "@/components/layout/AuthLayout";
import { CRMClientCard } from "@/components/clients/CRMClientCard";
import { ClientStats } from "@/components/clients/ClientStats";
import type { CRMClient, ClientStatus, PipelineStats, ClientListResponse, UserRole } from "@/types";
import { CLIENT_STATUS_LABELS } from "@/types";
import { ClientCreateModal } from "@/components/clients/ClientCreateModal";
import { logger } from "@/lib/logger";
import { BulkReassignModal } from "@/components/clients/BulkReassignModal";
import { EmptyState } from "@/components/ui/EmptyState";
import { ClientListSkeleton } from "@/components/ui/Skeleton";
import { PixelInfoButton } from "@/components/ui/PixelInfoButton";
import Link from "next/link";
import { useRouter, useSearchParams, usePathname } from "next/navigation";

interface ManagerOption {
  id: string;
  full_name: string;
}

/** Serialize rows to CSV — RFC 4180 compliant, UTF-8 BOM is prepended by caller. */
function toCsv(rows: Record<string, unknown>[]): string {
  if (!rows.length) return "";
  const headers = Object.keys(rows[0]);
  const escape = (v: unknown) => {
    if (v == null) return "";
    const s = typeof v === "object" ? JSON.stringify(v) : String(v);
    return /[",\n;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const lines = [headers.join(",")];
  for (const row of rows) {
    lines.push(headers.map((h) => escape(row[h])).join(","));
  }
  return lines.join("\n");
}

export default function ClientsPage() {
  const { user } = useAuth();
  const router = useRouter();
  const userRole = user?.role as UserRole | undefined;
  const isAdminOrRop = userRole === "admin" || userRole === "rop";
  const isReadOnly = userRole === "methodologist";
  const canExportSelected = userRole === "admin" || userRole === "rop" || userRole === "methodologist";
  const scopeLabel =
    userRole === "admin"
      ? "Администратор: все команды, все менеджеры и РОП."
      : userRole === "rop"
        ? "РОП: только ваша команда и нижестоящие менеджеры."
        : userRole === "manager"
          ? "Менеджер: только ваши реальные клиенты."
          : userRole === "methodologist"
            ? "Методолог: read-only по реальным данным и статистике."
            : "";

  // URL-backed filters — survive F5 and can be shared via link
  const searchParams = useSearchParams();
  const pathname = usePathname();

  const [clients, setClients] = useState<CRMClient[]>([]);
  const [stats, setStats] = useState<PipelineStats[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState(() => searchParams.get("q") ?? "");
  const [debouncedSearch, setDebouncedSearch] = useState(search);
  const [statusFilter, setStatusFilter] = useState<ClientStatus | "">(
    () => (searchParams.get("status") as ClientStatus | null) ?? ""
  );
  const [statusOpen, setStatusOpen] = useState(false);
  const statusRef = useRef<HTMLDivElement>(null);
  const [page, setPage] = useState(() => {
    const p = parseInt(searchParams.get("page") ?? "1", 10);
    return Number.isFinite(p) && p > 0 ? p : 1;
  });
  const limit = 20;

  // Debounce search input — don't hit API on every keystroke
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 350);
    return () => clearTimeout(t);
  }, [search]);

  // F6.3: Bulk operations for admin/rop
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [showReassign, setShowReassign] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  // F4.2: Manager filter for admin/rop
  const [managers, setManagers] = useState<ManagerOption[]>([]);
  const [managerFilter, setManagerFilter] = useState(() => searchParams.get("manager") ?? "");
  const [managerOpen, setManagerOpen] = useState(false);
  const managerRef = useRef<HTMLDivElement>(null);

  // Sync filters → URL (replace so back-button doesn't go through every keystroke)
  useEffect(() => {
    const params = new URLSearchParams();
    if (debouncedSearch) params.set("q", debouncedSearch);
    if (statusFilter) params.set("status", statusFilter);
    if (managerFilter) params.set("manager", managerFilter);
    if (page > 1) params.set("page", String(page));
    const qs = params.toString();
    const url = qs ? `${pathname}?${qs}` : pathname;
    router.replace(url, { scroll: false });
  }, [debouncedSearch, statusFilter, managerFilter, page, pathname, router]);

  // Load managers list for admin/rop
  useEffect(() => {
    if (!isAdminOrRop) return;
    api.get("/users/?role=manager&limit=100")
      .then((data: ManagerOption[]) => setManagers(Array.isArray(data) ? data : []))
      .catch((err) => { logger.error("Failed to load managers:", err); });
  }, [isAdminOrRop]);

  // Close dropdowns on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (statusRef.current && !statusRef.current.contains(e.target as Node)) {
        setStatusOpen(false);
      }
      if (managerRef.current && !managerRef.current.contains(e.target as Node)) {
        setManagerOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const fetchClients = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (debouncedSearch) params.set("search", debouncedSearch);
      if (statusFilter) params.set("status", statusFilter);
      if (managerFilter) params.set("manager_id", managerFilter);
      params.set("page", String(page));
      params.set("per_page", String(limit));

      const data: ClientListResponse = await api.get(`/clients?${params}`);
      setClients(data.items);
      setTotal(data.total);
    } catch (err) { logger.error("Failed to fetch clients:", err); }
    setLoading(false);
  }, [debouncedSearch, statusFilter, managerFilter, page]);

  const fetchStats = useCallback(async () => {
    try {
      const data: PipelineStats[] = await api.get("/clients/pipeline/stats");
      setStats(data);
    } catch (err) { logger.error("Failed to fetch pipeline stats:", err); }
  }, []);

  useEffect(() => { fetchClients(); }, [fetchClients]);
  useEffect(() => { fetchStats(); }, [fetchStats]);

  const totalPages = Math.ceil(total / limit);

  // Status summary counts
  const activeCount = clients.filter((c) => ["in_process", "contract_signed", "consultation"].includes(c.status)).length;
  const thinkingCount = clients.filter((c) => ["thinking", "interested", "contacted"].includes(c.status)).length;

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selected.size === clients.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(clients.map((c) => c.id)));
    }
  };

  const handleExport = async () => {
    setExporting(true);
    setExportError(null);
    try {
      // Use the standard api client (handles auth refresh, CSRF, retries)
      const payload = await api.post<{ items?: Record<string, unknown>[] }>(
        "/clients/bulk/export",
        { client_ids: Array.from(selected) },
      );
      const items = Array.isArray(payload?.items) ? payload.items : [];
      const csv = toCsv(items);
      const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `clients_export_${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Не удалось выполнить экспорт";
      setExportError(msg);
      logger.error("Export error:", err);
    }
    setExporting(false);
  };

  return (
    <AuthLayout>
      <div className="panel-grid-bg min-h-screen">
        <div className="app-page">
        {/* Header — compact */}
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4">
            <div>
              {scopeLabel && (
                <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                  {scopeLabel}
                </p>
              )}
              {!loading && clients.length > 0 && (
                <div className="flex items-center gap-3 text-xs font-mono mt-1" style={{ color: "var(--text-muted)" }}>
                  <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full" style={{ background: "var(--success)" }} />{activeCount} активных</span>
                  <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full" style={{ background: "var(--warning)" }} />{thinkingCount} думают</span>
                  <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full" style={{ background: "var(--text-muted)" }} />{total} всего</span>
                </div>
              )}
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <Link href="/clients/graph" prefetch={true}>
                <motion.button
                  className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium"
                  style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)", color: "var(--text-secondary)" }}
                  whileTap={{ scale: 0.97 }}
                >
                  <UsersThree size={12} weight="duotone" /> Граф
                </motion.button>
              </Link>
              {/* Duplicates page removed — auto-detection planned */}
              <Link href="/clients/pipeline" prefetch={true}>
                <motion.button
                  className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium"
                  style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)", color: "var(--text-secondary)" }}
                  whileTap={{ scale: 0.97 }}
                >
                  <Filter size={12} /> Воронка
                </motion.button>
              </Link>
              <PixelInfoButton
                title="Клиенты (CRM)"
                sections={[
                  { icon: UsersThree, label: "Карточки клиентов", text: "Каждая карточка — AI-клиент, которого вы встречали на тренировке. Показывает статус, прогресс, напоминания" },
                  { icon: Filter, label: "Воронка", text: "Канбан-доска по статусам: новый → в работе → думает → согласие/отказ" },
                  { icon: Search, label: "Поиск + фильтры", text: "Ищите по имени, фильтруйте по статусу, руководителю, дате последнего касания" },
                  { icon: UserCheck, label: "Массовые действия", text: "Для админов/РОП: переназначить клиентов другому менеджеру, экспорт CSV" },
                  { icon: Plus, label: "Новая тренировка", text: "Создаёт новую тренировку — после разбора клиент появится здесь автоматически" },
                ]}
                footer="Совет: кликните карточку → откроется граф взаимодействий с клиентом"
              />
              {!isReadOnly && (
                <Link href="/training">
                  <motion.button
                    className="btn-neon flex items-center gap-1.5 text-sm"
                    whileTap={{ scale: 0.97 }}
                  >
                    <Plus size={14} /> Новая тренировка
                  </motion.button>
                </Link>
              )}
            </div>
          </div>
        </motion.div>

        {/* Stats */}
        {stats.length > 0 && (
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="mt-6">
            <ClientStats stats={stats} />
          </motion.div>
        )}

        {/* Filters */}
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="mt-6 flex flex-col sm:flex-row gap-3"
        >
          <div className="relative flex-1">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: "var(--text-muted)" }} />
            <input
              type="text"
              value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(1); }}
              placeholder="Поиск по имени, телефону, email..."
              className="vh-input pl-9 w-full"
            />
          </div>
          {/* Custom status dropdown */}
          <div ref={statusRef} className="relative w-full sm:w-52">
            <motion.button
              onClick={() => setStatusOpen(!statusOpen)}
              className="vh-input w-full flex items-center justify-between gap-2 text-left"
              whileTap={{ scale: 0.98 }}
            >
              <span style={{ color: statusFilter ? "var(--text-primary)" : "var(--text-muted)" }}>
                {statusFilter ? CLIENT_STATUS_LABELS[statusFilter] : "Все статусы"}
              </span>
              <motion.span
                animate={{ rotate: statusOpen ? 180 : 0 }}
                transition={{ duration: 0.2 }}
              >
                <ChevronDown size={14} style={{ color: "var(--text-muted)" }} />
              </motion.span>
            </motion.button>

            <AnimatePresence>
              {statusOpen && (
                <motion.div
                  initial={{ opacity: 0, y: -8, scaleY: 0.9 }}
                  animate={{ opacity: 1, y: 4, scaleY: 1 }}
                  exit={{ opacity: 0, y: -8, scaleY: 0.9 }}
                  transition={{ duration: 0.2, ease: [0.4, 0, 0.2, 1] }}
                  className="absolute z-50 top-full left-0 right-0 origin-top rounded-xl overflow-hidden"
                  style={{
                    background: "var(--glass-bg)",
                    border: "1px solid var(--glass-border)",
                    backdropFilter: "blur(20px)",
                    boxShadow: "0 12px 40px rgba(0,0,0,0.3)",
                  }}
                >
                  <div className="max-h-64 overflow-y-auto py-1" style={{ scrollbarWidth: "thin" }}>
                    {/* "Все статусы" option */}
                    <motion.button
                      onClick={() => { setStatusFilter(""); setPage(1); setStatusOpen(false); }}
                      className="w-full flex items-center gap-2 px-3 py-2.5 text-sm transition-colors"
                      style={{ color: !statusFilter ? "var(--accent)" : "var(--text-secondary)" }}
                      whileHover={{ background: "var(--accent-muted)" }}
                    >
                      {!statusFilter && <Check size={12} style={{ color: "var(--accent)" }} />}
                      <span className={!statusFilter ? "ml-0" : "ml-5"}>Все статусы</span>
                    </motion.button>

                    {/* Divider */}
                    <div className="mx-3 my-1 h-px" style={{ background: "var(--border-color)" }} />

                    {/* Status options */}
                    {(["new", "contacted", "interested", "consultation", "thinking", "consent_given", "contract_signed", "in_process", "completed", "paused", "consent_revoked", "lost"] as ClientStatus[]).map((s, i) => (
                      <motion.button
                        key={s}
                        onClick={() => { setStatusFilter(s); setPage(1); setStatusOpen(false); }}
                        initial={{ opacity: 0, x: -8 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: i * 0.02, duration: 0.15 }}
                        className="w-full flex items-center gap-2 px-3 py-2 text-sm transition-colors"
                        style={{ color: statusFilter === s ? "var(--accent)" : "var(--text-secondary)" }}
                        whileHover={{ background: "var(--accent-muted)" }}
                      >
                        {statusFilter === s && <Check size={12} style={{ color: "var(--accent)" }} />}
                        <span className={statusFilter === s ? "ml-0" : "ml-5"}>{CLIENT_STATUS_LABELS[s]}</span>
                      </motion.button>
                    ))}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* F4.2: Manager filter for admin/rop */}
          {isAdminOrRop && managers.length > 0 && (
            <div ref={managerRef} className="relative w-full sm:w-52">
              <motion.button
                onClick={() => setManagerOpen(!managerOpen)}
                className="vh-input w-full flex items-center justify-between gap-2 text-left"
                whileTap={{ scale: 0.98 }}
              >
                <span style={{ color: managerFilter ? "var(--text-primary)" : "var(--text-muted)" }}>
                  {managerFilter ? managers.find((m) => m.id === managerFilter)?.full_name || "Менеджер" : "Все менеджеры"}
                </span>
                <motion.span
                  animate={{ rotate: managerOpen ? 180 : 0 }}
                  transition={{ duration: 0.2 }}
                >
                  <ChevronDown size={14} style={{ color: "var(--text-muted)" }} />
                </motion.span>
              </motion.button>

              <AnimatePresence>
                {managerOpen && (
                  <motion.div
                    initial={{ opacity: 0, y: -8, scaleY: 0.9 }}
                    animate={{ opacity: 1, y: 4, scaleY: 1 }}
                    exit={{ opacity: 0, y: -8, scaleY: 0.9 }}
                    transition={{ duration: 0.2, ease: [0.4, 0, 0.2, 1] }}
                    className="absolute z-50 top-full left-0 right-0 origin-top rounded-xl overflow-hidden"
                    style={{
                      background: "var(--glass-bg)",
                      border: "1px solid var(--glass-border)",
                      backdropFilter: "blur(20px)",
                      boxShadow: "0 12px 40px rgba(0,0,0,0.3)",
                    }}
                  >
                    <div className="max-h-64 overflow-y-auto py-1" style={{ scrollbarWidth: "thin" }}>
                      <motion.button
                        onClick={() => { setManagerFilter(""); setPage(1); setManagerOpen(false); }}
                        className="w-full flex items-center gap-2 px-3 py-2.5 text-sm transition-colors"
                        style={{ color: !managerFilter ? "var(--accent)" : "var(--text-secondary)" }}
                        whileHover={{ background: "var(--accent-muted)" }}
                      >
                        {!managerFilter && <Check size={12} style={{ color: "var(--accent)" }} />}
                        <span className={!managerFilter ? "ml-0" : "ml-5"}>Все менеджеры</span>
                      </motion.button>
                      <div className="mx-3 my-1 h-px" style={{ background: "var(--border-color)" }} />
                      {managers.map((m, i) => (
                        <motion.button
                          key={m.id}
                          onClick={() => { setManagerFilter(m.id); setPage(1); setManagerOpen(false); }}
                          initial={{ opacity: 0, x: -8 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{ delay: i * 0.02, duration: 0.15 }}
                          className="w-full flex items-center gap-2 px-3 py-2 text-sm transition-colors"
                          style={{ color: managerFilter === m.id ? "var(--accent)" : "var(--text-secondary)" }}
                          whileHover={{ background: "var(--accent-muted)" }}
                        >
                          {managerFilter === m.id && <Check size={12} style={{ color: "var(--accent)" }} />}
                          <span className={managerFilter === m.id ? "ml-0" : "ml-5"}>{m.full_name}</span>
                        </motion.button>
                      ))}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )}
        </motion.div>

        {/* F6.3: Bulk toolbar */}
        {canExportSelected && selected.size > 0 && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            className="mt-4 flex items-center gap-3 rounded-xl p-3"
            style={{ background: "var(--accent-muted)", border: "1px solid var(--accent)" }}
          >
            <span className="text-xs font-mono" style={{ color: "var(--accent)" }}>
              {selected.size} выбрано
            </span>
            {isAdminOrRop && (
              <motion.button
                onClick={() => setShowReassign(true)}
                className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium"
                style={{ background: "var(--accent)", color: "white" }}
                whileTap={{ scale: 0.97 }}
              >
                <UserCheck size={12} /> Переназначить
              </motion.button>
            )}
            <motion.button
              onClick={handleExport}
              disabled={exporting}
              className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium"
              style={{ background: "var(--input-bg)", color: "var(--text-secondary)", border: "1px solid var(--border-color)" }}
              whileTap={{ scale: 0.97 }}
            >
              {exporting ? <Loader2 size={12} className="animate-spin" /> : <Download size={12} />}
              Экспорт
            </motion.button>
            <motion.button
              onClick={() => setSelected(new Set())}
              className="ml-auto"
              style={{ color: "var(--text-muted)" }}
              whileTap={{ scale: 0.9 }}
            >
              <X size={14} />
            </motion.button>
            {exportError && (
              <span className="text-xs ml-2" style={{ color: "var(--danger)" }}>{exportError}</span>
            )}
          </motion.div>
        )}

        {/* Client list */}
        <div className="mt-6 space-y-2">
          {/* Select all for admin/rop */}
          {canExportSelected && clients.length > 0 && !loading && (
            <div className="flex items-center gap-2 mb-2">
              <motion.button
                onClick={toggleSelectAll}
                className="w-4 h-4 rounded border flex items-center justify-center shrink-0"
                style={{
                  borderColor: selected.size === clients.length ? "var(--accent)" : "var(--border-color)",
                  background: selected.size === clients.length ? "var(--accent)" : "transparent",
                }}
                whileTap={{ scale: 0.9 }}
              >
                {selected.size === clients.length && <Check size={10} className="text-white" />}
              </motion.button>
              <span className="text-xs font-medium" style={{ color: "var(--text-muted)" }}>Выбрать все</span>
            </div>
          )}

          {loading ? (
            <ClientListSkeleton />
          ) : clients.length === 0 ? (
            <EmptyState
              title={search || statusFilter ? "Нет совпадений в портфеле" : "Портфель пуст — время открыть первое дело"}
              description={search || statusFilter ? "Попробуйте изменить фильтры или сбросить поиск — клиент может быть в другом статусе" : "Завершите первую тренировку и нажмите «Добавить в CRM». Каждый клиент — это ваш прогресс"}
              hint={!search && !statusFilter ? "Первый клиент — первый шаг к результату" : undefined}
              illustration={
                search || statusFilter
                  ? <motion.div className="mb-4 flex h-20 w-20 items-center justify-center rounded-2xl" style={{ background: "var(--accent-muted)" }} animate={{ y: [0, -4, 0] }} transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}><UsersThree size={48} weight="duotone" style={{ color: "var(--accent)", opacity: 0.7 }} /></motion.div>
                  : <img src="/pixel/empty/treasure-locked.png" alt="" className="w-24 h-24 mx-auto mb-2 opacity-80" />
              }
              actionLabel={!search && !statusFilter ? "Начать тренировку" : undefined}
              onAction={!search && !statusFilter ? () => window.location.href = "/training" : undefined}
            />
          ) : (
            clients.map((c, i) => (
              <motion.div
                key={c.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.02 * i }}
                className="flex items-center gap-2"
              >
                {canExportSelected && (
                  <motion.button
                    onClick={() => toggleSelect(c.id)}
                    className="w-4 h-4 rounded border flex items-center justify-center shrink-0"
                    style={{
                      borderColor: selected.has(c.id) ? "var(--accent)" : "var(--border-color)",
                      background: selected.has(c.id) ? "var(--accent)" : "transparent",
                    }}
                    whileTap={{ scale: 0.9 }}
                  >
                    {selected.has(c.id) && <Check size={10} className="text-white" />}
                  </motion.button>
                )}
                <div className="flex-1">
                  <CRMClientCard client={c} userRole={userRole} />
                </div>
              </motion.div>
            ))
          )}
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-center gap-2 mt-6">
            {(() => {
              const pages: (number | "ellipsis-l" | "ellipsis-r")[] = [];
              const delta = 2;
              const left = Math.max(2, page - delta);
              const right = Math.min(totalPages - 1, page + delta);

              pages.push(1);
              if (left > 2) pages.push("ellipsis-l");
              for (let i = left; i <= right; i++) pages.push(i);
              if (right < totalPages - 1) pages.push("ellipsis-r");
              if (totalPages > 1) pages.push(totalPages);

              return pages.map((p) =>
                typeof p === "string" ? (
                  <span key={p} className="w-8 h-8 flex items-center justify-center text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                    ...
                  </span>
                ) : (
                  <motion.button
                    key={p}
                    onClick={() => setPage(p)}
                    className="w-8 h-8 rounded-lg text-xs font-mono"
                    style={{
                      background: p === page ? "var(--accent)" : "var(--input-bg)",
                      color: p === page ? "white" : "var(--text-muted)",
                      border: `1px solid ${p === page ? "var(--accent)" : "var(--border-color)"}`,
                    }}
                    whileTap={{ scale: 0.95 }}
                  >
                    {p}
                  </motion.button>
                ),
              );
            })()}
          </div>
        )}
        {/* ClientCreateModal removed — clients are added via training sessions */}
        <BulkReassignModal
          open={showReassign}
          clientIds={Array.from(selected)}
          onClose={() => setShowReassign(false)}
          onDone={() => {
            setShowReassign(false);
            setSelected(new Set());
            fetchClients();
          }}
        />
        </div>
      </div>
    </AuthLayout>
  );
}
