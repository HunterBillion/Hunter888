"use client";

import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Kanban,
  ArrowLeft,
  Loader2,
  BarChart3,
  RefreshCw,
  Eye,
  EyeOff,
} from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { useKanbanDrag } from "@/hooks/useKanbanDrag";
import AuthLayout from "@/components/layout/AuthLayout";
import { PipelineColumn } from "@/components/clients/PipelineColumn";
import { PipelineCard } from "@/components/clients/PipelineCard";
import type { CRMClient, ClientStatus, PipelineStats } from "@/types";
import { PIPELINE_STATUSES, CLIENT_STATUS_LABELS, CLIENT_STATUS_COLORS } from "@/types";

export default function PipelinePage() {
  const { user } = useAuth();
  const router = useRouter();

  // F4.4: Methodologist redirect
  useEffect(() => {
    if (user && user.role === "methodologist") {
      router.replace("/home");
    }
  }, [user, router]);

  const [clients, setClients] = useState<CRMClient[]>([]);
  const [stats, setStats] = useState<PipelineStats[]>([]);
  const [loading, setLoading] = useState(true);
  const [showLost, setShowLost] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  // ── Column refs for touch hit-testing ──
  const columnRefs = useRef<Map<string, HTMLElement>>(new Map());

  const setColumnRef = useCallback((status: string, el: HTMLElement | null) => {
    if (el) columnRefs.current.set(status, el);
    else columnRefs.current.delete(status);
  }, []);

  // ── Data fetching ──
  const fetchClients = useCallback(async () => {
    try {
      const data = await api.get("/clients?limit=500");
      setClients(data.items || []);
    } catch {
      /* API may not exist yet */
    }
    setLoading(false);
  }, []);

  const fetchStats = useCallback(async () => {
    try {
      const data: PipelineStats[] = await api.get("/clients/stats");
      setStats(data);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    fetchClients();
    fetchStats();
  }, [fetchClients, fetchStats]);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    await Promise.all([fetchClients(), fetchStats()]);
    setRefreshing(false);
  }, [fetchClients, fetchStats]);

  // ── Drop handler with optimistic update ──
  const handleDrop = useCallback(
    async (clientId: string, newStatus: string) => {
      const client = clients.find((c) => c.id === clientId);
      if (!client || client.status === newStatus) return;

      // Optimistic update
      setClients((prev) =>
        prev.map((c) =>
          c.id === clientId ? { ...c, status: newStatus as ClientStatus } : c,
        ),
      );

      try {
        await api.patch(`/clients/${clientId}/status`, { new_status: newStatus });
        // Refresh stats after successful status change
        fetchStats();
      } catch {
        // Revert on failure
        fetchClients();
      }
    },
    [clients, fetchClients, fetchStats],
  );

  // ── Kanban drag hook ──
  const {
    state: dragState,
    scrollContainerRef,
    handleDragStart,
    handleDragOver,
    handleDragLeave,
    handleDrop: handleColumnDrop,
    handleDragEnd,
    handleTouchStart,
    handleTouchMove,
    handleTouchEnd,
  } = useKanbanDrag({ onDrop: handleDrop, columnRefs });

  // ── Grouped clients by status (respects user pipeline_columns preference) ──
  const visibleStatuses = useMemo(() => {
    const prefs = (user as { preferences?: Record<string, unknown> } | null)?.preferences;
    const savedCols = Array.isArray(prefs?.pipeline_columns) ? prefs.pipeline_columns as string[] : null;
    const base: ClientStatus[] = savedCols
      ? PIPELINE_STATUSES.filter((s) => savedCols.includes(s))
      : [...PIPELINE_STATUSES];
    if (base.length < 2) return [...PIPELINE_STATUSES]; // fallback: show all if too few
    if (showLost) base.push("lost");
    return base;
  }, [showLost, user]);

  const grouped = useMemo(() => {
    return visibleStatuses.reduce(
      (acc, status) => {
        acc[status] = clients.filter((c) => c.status === status);
        return acc;
      },
      {} as Record<ClientStatus, CRMClient[]>,
    );
  }, [clients, visibleStatuses]);

  // ── Stats bar ──
  const totalClients = clients.length;
  const activeClients = clients.filter(
    (c) => c.status !== "lost" && c.status !== "completed",
  ).length;
  const totalDebt = clients.reduce((sum, c) => sum + (c.debt_amount ?? 0), 0);

  // ── Dragged client for overlay ──
  const draggedClient = dragState.activeId
    ? clients.find((c) => c.id === dragState.activeId)
    : null;

  return (
    <AuthLayout>
      <div className="flex flex-col h-[calc(100vh-64px)] panel-grid-bg">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="px-4 pt-6 pb-4 shrink-0"
        >
          <div className="mx-auto max-w-[1600px]">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Link
                  href="/clients"
                  className="transition-colors hover:opacity-80"
                  style={{ color: "var(--text-muted)" }}
                >
                  <ArrowLeft size={16} />
                </Link>
                <Kanban size={20} style={{ color: "var(--accent)" }} />
                <h1
                  className="font-display text-2xl font-bold tracking-[0.15em]"
                  style={{ color: "var(--text-primary)" }}
                >
                  ВОРОНКА
                </h1>
              </div>

              <div className="flex items-center gap-2">
                {/* Stats pills */}
                <div className="hidden sm:flex items-center gap-2 mr-3">
                  <span
                    className="text-[10px] font-mono px-2 py-1 rounded-lg"
                    style={{
                      background: "var(--input-bg)",
                      color: "var(--text-muted)",
                      border: "1px solid var(--border-color)",
                    }}
                  >
                    <BarChart3 size={10} className="inline mr-1" />
                    {activeClients} актив. / {totalClients} всего
                  </span>
                  {totalDebt > 0 && (
                    <span
                      className="text-[10px] font-mono px-2 py-1 rounded-lg"
                      style={{
                        background: "var(--input-bg)",
                        color: "var(--accent)",
                        border: "1px solid var(--border-color)",
                      }}
                    >
                      {(totalDebt / 1_000_000).toFixed(1)}M ₽ долга
                    </span>
                  )}
                </div>

                {/* Show/hide lost */}
                <motion.button
                  onClick={() => setShowLost((v) => !v)}
                  className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-[10px] font-mono"
                  style={{
                    background: showLost ? "rgba(255,51,51,0.1)" : "var(--input-bg)",
                    border: `1px solid ${showLost ? "rgba(255,51,51,0.3)" : "var(--border-color)"}`,
                    color: showLost ? "#FF3333" : "var(--text-muted)",
                  }}
                  whileTap={{ scale: 0.97 }}
                >
                  {showLost ? <EyeOff size={11} /> : <Eye size={11} />}
                  Потерянные
                </motion.button>

                {/* Refresh */}
                <motion.button
                  onClick={handleRefresh}
                  className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-[10px] font-mono"
                  style={{
                    background: "var(--input-bg)",
                    border: "1px solid var(--border-color)",
                    color: "var(--text-muted)",
                  }}
                  whileTap={{ scale: 0.97 }}
                >
                  <RefreshCw
                    size={11}
                    className={refreshing ? "animate-spin" : ""}
                  />
                </motion.button>
              </div>
            </div>

            {/* Mini funnel bar */}
            {stats.length > 0 && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.2 }}
                className="mt-3 flex rounded-lg overflow-hidden h-1.5"
                style={{ background: "var(--input-bg)" }}
              >
                {stats
                  .filter((s) => PIPELINE_STATUSES.includes(s.status))
                  .map((s) => {
                    const pct = totalClients > 0 ? (s.count / totalClients) * 100 : 0;
                    return pct > 0 ? (
                      <div
                        key={s.status}
                        style={{
                          width: `${Math.max(pct, 2)}%`,
                          background: CLIENT_STATUS_COLORS[s.status],
                          opacity: 0.7,
                        }}
                        title={`${CLIENT_STATUS_LABELS[s.status]}: ${s.count}`}
                      />
                    ) : null;
                  })}
              </motion.div>
            )}
          </div>
        </motion.div>

        {/* Kanban board */}
        {loading ? (
          <div className="flex items-center justify-center flex-1">
            <Loader2
              size={24}
              className="animate-spin"
              style={{ color: "var(--accent)" }}
            />
          </div>
        ) : (
          <div
            ref={(el) => {
              scrollContainerRef.current = el;
            }}
            className="flex-1 overflow-x-auto overflow-y-hidden px-4 pb-4"
            style={{ scrollbarWidth: "thin" }}
          >
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.1 }}
              className="flex gap-3 mx-auto max-w-[1600px] h-full"
            >
              {visibleStatuses.map((status, i) => (
                <motion.div
                  key={status}
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.04 * i }}
                  className="h-full"
                >
                  <PipelineColumn
                    ref={(el) => setColumnRef(status, el)}
                    status={status}
                    clients={grouped[status] || []}
                    isOver={dragState.overColumn === status}
                    activeId={dragState.activeId}
                    onDragOver={handleDragOver}
                    onDragLeave={handleDragLeave}
                    onDrop={handleColumnDrop}
                    onDragStart={handleDragStart}
                    onDragEnd={handleDragEnd}
                    onTouchStart={handleTouchStart}
                    onTouchMove={handleTouchMove}
                    onTouchEnd={handleTouchEnd}
                  />
                </motion.div>
              ))}
            </motion.div>
          </div>
        )}

        {/* Touch drag overlay (mobile only) */}
        <AnimatePresence>
          {dragState.isTouchDrag && draggedClient && dragState.clonePos && (
            <motion.div
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1.05 }}
              exit={{ opacity: 0, scale: 0.8 }}
              transition={{ duration: 0.15 }}
              style={{
                position: "fixed",
                left: dragState.clonePos.x - 130,
                top: dragState.clonePos.y - 40,
                width: "260px",
                zIndex: 9999,
                pointerEvents: "none",
                filter: "drop-shadow(0 8px 24px rgba(0,0,0,0.4))",
              }}
            >
              <PipelineCard client={draggedClient} />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </AuthLayout>
  );
}
