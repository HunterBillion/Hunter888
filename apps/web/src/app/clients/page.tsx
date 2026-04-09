"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Users, Search, Filter, Plus, Loader2, ChevronDown, Check, UserCheck, Download, X, Copy } from "lucide-react";
import { api } from "@/lib/api";
import { getApiBaseUrl } from "@/lib/public-origin";
import { getToken } from "@/lib/auth";
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
import Link from "next/link";
import { useRouter } from "next/navigation";

interface ManagerOption {
  id: string;
  full_name: string;
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

  const [createOpen, setCreateOpen] = useState(false);
  const [clients, setClients] = useState<CRMClient[]>([]);
  const [stats, setStats] = useState<PipelineStats[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<ClientStatus | "">("");
  const [statusOpen, setStatusOpen] = useState(false);
  const statusRef = useRef<HTMLDivElement>(null);
  const [page, setPage] = useState(1);
  const limit = 20;

  // F6.3: Bulk operations for admin/rop
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [showReassign, setShowReassign] = useState(false);
  const [exporting, setExporting] = useState(false);

  // F4.2: Manager filter for admin/rop
  const [managers, setManagers] = useState<ManagerOption[]>([]);
  const [managerFilter, setManagerFilter] = useState("");
  const [managerOpen, setManagerOpen] = useState(false);
  const managerRef = useRef<HTMLDivElement>(null);

  // Load managers list for admin/rop
  useEffect(() => {
    if (!isAdminOrRop) return;
    api.get("/users?role=manager&limit=100")
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
      if (search) params.set("search", search);
      if (statusFilter) params.set("status", statusFilter);
      if (managerFilter) params.set("manager_id", managerFilter);
      params.set("page", String(page));
      params.set("per_page", String(limit));

      const data: ClientListResponse = await api.get(`/clients?${params}`);
      setClients(data.items);
      setTotal(data.total);
    } catch (err) { logger.error("Failed to fetch clients:", err); }
    setLoading(false);
  }, [search, statusFilter, managerFilter, page]);

  const fetchStats = useCallback(async () => {
    try {
      const data: PipelineStats[] = await api.get("/clients/pipeline/stats");
      setStats(data);
    } catch (err) { logger.error("Failed to fetch pipeline stats:", err); }
  }, []);

  useEffect(() => { fetchClients(); }, [fetchClients]);
  useEffect(() => { fetchStats(); }, [fetchStats]);

  const totalPages = Math.ceil(total / limit);

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
    try {
      const resp = await fetch(
        `${getApiBaseUrl()}/api/clients/bulk/export`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${getToken() || ""}`,
          },
          body: JSON.stringify({ client_ids: Array.from(selected) }),
        },
      );
      if (resp.ok) {
        const payload = await resp.json();
        const blob = new Blob([JSON.stringify(payload, null, 2)], {
          type: "application/json",
        });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `clients_export_${new Date().toISOString().slice(0, 10)}.json`;
        a.click();
        URL.revokeObjectURL(url);
      }
    } catch { /* ignore */ }
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
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <Link href="/clients/graph" prefetch={true}>
                <motion.button
                  className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium"
                  style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)", color: "var(--text-secondary)" }}
                  whileTap={{ scale: 0.97 }}
                >
                  <Users size={12} /> Граф
                </motion.button>
              </Link>
              {isAdminOrRop && (
                <Link href="/clients/duplicates" prefetch={true}>
                  <motion.button
                    className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium"
                    style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)", color: "var(--text-secondary)" }}
                    whileTap={{ scale: 0.97 }}
                  >
                    <Copy size={12} /> Дубли
                  </motion.button>
                </Link>
              )}
              <Link href="/clients/pipeline" prefetch={true}>
                <motion.button
                  className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium"
                  style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)", color: "var(--text-secondary)" }}
                  whileTap={{ scale: 0.97 }}
                >
                  <Filter size={12} /> Воронка
                </motion.button>
              </Link>
              {!isReadOnly && (
                <motion.button
                  onClick={() => setCreateOpen(true)}
                  className="btn-neon flex items-center gap-1.5 text-sm"
                  whileTap={{ scale: 0.97 }}
                >
                  <Plus size={14} /> Добавить
                </motion.button>
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
              icon={Users}
              title={search || statusFilter ? "Клиенты не найдены" : "Пока нет клиентов"}
              description={search || statusFilter ? "Попробуйте изменить параметры поиска" : "Добавьте первого клиента для начала работы с CRM"}
              actionLabel={!search && !statusFilter ? "Добавить клиента" : undefined}
              onAction={undefined}
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
        <ClientCreateModal
          open={createOpen}
          onClose={() => setCreateOpen(false)}
          onCreated={(id) => {
            setCreateOpen(false);
            router.push(`/clients/${id}`);
          }}
        />
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
