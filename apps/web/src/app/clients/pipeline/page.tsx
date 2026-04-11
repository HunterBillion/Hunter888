"use client";

import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Kanban,
  Loader2,
  BarChart3,
  RefreshCw,
  Eye,
  EyeOff,
  LayoutGrid,
  Plus,
  SlidersHorizontal,
} from "lucide-react";
import { BackButton } from "@/components/ui/BackButton";
import { api } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { useKanbanDrag } from "@/hooks/useKanbanDrag";
import { useAuthStore } from "@/stores/useAuthStore";
import AuthLayout from "@/components/layout/AuthLayout";
import { ClientCreateModal } from "@/components/clients/ClientCreateModal";
import { InteractionCreateModal } from "@/components/clients/InteractionCreateModal";
import { PipelineColumn } from "@/components/clients/PipelineColumn";
import { PipelineCard, type PipelineCardField } from "@/components/clients/PipelineCard";
import { ReminderCreateModal } from "@/components/clients/ReminderCreateModal";
import type { CRMClient, ClientStatus, PipelineStats, UserRole } from "@/types";
import { PIPELINE_STATUSES, CLIENT_STATUS_LABELS, CLIENT_STATUS_COLORS } from "@/types";
import { logger } from "@/lib/logger";

const DEFAULT_CARD_FIELDS: PipelineCardField[] = ["debt", "phone", "next_contact", "updated"];
const CARD_FIELD_OPTIONS: Array<{ key: PipelineCardField; label: string }> = [
  { key: "phone", label: "Телефон" },
  { key: "debt", label: "Долг" },
  { key: "next_contact", label: "След. контакт" },
  { key: "manager", label: "Менеджер" },
  { key: "updated", label: "Обновлено" },
  { key: "source", label: "Источник" },
];

export default function PipelinePage() {
  const { user } = useAuth();
  const userRole = user?.role as UserRole | undefined;
  const isReadOnly = userRole === "methodologist";

  const [clients, setClients] = useState<CRMClient[]>([]);
  const [stats, setStats] = useState<PipelineStats[]>([]);
  const [loading, setLoading] = useState(true);
  const [showLost, setShowLost] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [noteClient, setNoteClient] = useState<CRMClient | null>(null);
  const [reminderClient, setReminderClient] = useState<CRMClient | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [showCustomize, setShowCustomize] = useState(false);
  const [savingPrefs, setSavingPrefs] = useState(false);
  const [layoutMode, setLayoutMode] = useState<"grid" | "board">("grid");
  const [cardFields, setCardFields] = useState<PipelineCardField[]>(DEFAULT_CARD_FIELDS);
  const [pipelineColumns, setPipelineColumns] = useState<ClientStatus[]>([...PIPELINE_STATUSES]);

  // ── Column refs for touch hit-testing ──
  const columnRefs = useRef<Map<string, HTMLElement>>(new Map());

  const setColumnRef = useCallback((status: string, el: HTMLElement | null) => {
    if (el) columnRefs.current.set(status, el);
    else columnRefs.current.delete(status);
  }, []);

  // ── Data fetching ──
  const fetchClients = useCallback(async () => {
    try {
      const allItems: CRMClient[] = [];
      let page = 1;
      let pages = 1;

      do {
        const data = await api.get(`/clients?page=${page}&per_page=100`);
        allItems.push(...(data.items || []));
        pages = data.pages || 1;
        page += 1;
      } while (page <= pages && page <= 20);

      setClients(allItems);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка загрузки клиентов");
    }
    setLoading(false);
  }, []);

  const fetchStats = useCallback(async () => {
    try {
      const data: PipelineStats[] = await api.get("/clients/pipeline/stats");
      setStats(data);
    } catch (err) {
      // Stats are non-critical — log but don't block the UI
      logger.warn("[Pipeline] Failed to load stats:", err);
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

  const handleInlineNoteSubmit = useCallback(async (client: CRMClient, text: string) => {
    await api.post(`/clients/${client.id}/interactions`, {
      interaction_type: "note",
      content: text,
    });
    await fetchClients();
  }, [fetchClients]);

  // ── Drop handler with optimistic update ──
  const handleDrop = useCallback(
    async (clientId: string, newStatus: string) => {
      if (isReadOnly) return;
      const client = clients.find((c) => c.id === clientId);
      if (!client || client.status === newStatus) return;
      let reason: string | undefined;
      if (newStatus === "lost" || newStatus === "consent_revoked") {
        const promptLabel =
          newStatus === "lost"
            ? "Укажите причину потери клиента"
            : "Укажите причину отзыва согласия";
        const value = window.prompt(promptLabel)?.trim();
        if (!value) return;
        reason = value;
      }

      // Optimistic update
      setClients((prev) =>
        prev.map((c) =>
          c.id === clientId ? { ...c, status: newStatus as ClientStatus } : c,
        ),
      );

      try {
        setError(null);
        await api.patch(`/clients/${clientId}/status`, { new_status: newStatus, reason });
        // Refresh stats after successful status change
        fetchStats();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Не удалось сменить статус");
        // Revert on failure
        fetchClients();
      }
    },
    [clients, fetchClients, fetchStats, isReadOnly],
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

  useEffect(() => {
    const prefs = (user as { preferences?: Record<string, unknown> } | null)?.preferences;
    const savedCols = Array.isArray(prefs?.pipeline_columns) ? (prefs.pipeline_columns as ClientStatus[]) : null;
    const savedLayout = prefs?.pipeline_layout === "board" ? "board" : "grid";
    const savedFields = Array.isArray(prefs?.pipeline_card_fields)
      ? (prefs.pipeline_card_fields.filter((item): item is PipelineCardField =>
          ["phone", "debt", "next_contact", "manager", "updated", "source"].includes(String(item)),
        ))
      : null;

    setPipelineColumns(savedCols && savedCols.length >= 2 ? savedCols : [...PIPELINE_STATUSES]);
    setLayoutMode(savedLayout);
    setCardFields(savedFields && savedFields.length > 0 ? savedFields : DEFAULT_CARD_FIELDS);
  }, [user]);

  const persistPipelinePrefs = useCallback(
    async (patch: {
      pipeline_columns?: ClientStatus[];
      pipeline_layout?: "grid" | "board";
      pipeline_card_fields?: PipelineCardField[];
    }) => {
      setSavingPrefs(true);
      setError(null);
      try {
        await api.post("/users/me/preferences", patch);
        useAuthStore.getState().updatePreferences(patch as Record<string, unknown>);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Не удалось сохранить настройки канбана");
      } finally {
        setSavingPrefs(false);
      }
    },
    [],
  );

  // ── Grouped clients by status (respects user pipeline_columns preference) ──
  const visibleStatuses = useMemo(() => {
    const base: ClientStatus[] = pipelineColumns.length >= 2 ? [...pipelineColumns] : [...PIPELINE_STATUSES];
    if (base.length < 2) return [...PIPELINE_STATUSES]; // fallback: show all if too few
    if (showLost) base.push("lost");
    return base;
  }, [pipelineColumns, showLost]);

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
  const scopeLabel = useMemo(() => {
    if (userRole === "admin") return "Администратор: все команды и все менеджеры.";
    if (userRole === "rop") return "РОП: только ваша команда и нижестоящие менеджеры.";
    if (userRole === "manager") return "Менеджер: только ваши клиенты и ваши действия.";
    if (userRole === "methodologist") return "Методолог: read-only, без смены статусов и без записи данных.";
    return "";
  }, [userRole]);

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
                <BackButton href="/clients" label="К клиентам" />
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
                    className="text-xs font-mono px-2 py-1 rounded-lg"
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
                      className="text-xs font-mono px-2 py-1 rounded-lg"
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
                  className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium"
                  style={{
                    background: showLost ? "rgba(229,72,77,0.1)" : "var(--input-bg)",
                    border: `1px solid ${showLost ? "rgba(229,72,77,0.3)" : "var(--border-color)"}`,
                    color: showLost ? "var(--danger)" : "var(--text-muted)",
                  }}
                  whileTap={{ scale: 0.97 }}
                >
                  {showLost ? <EyeOff size={11} /> : <Eye size={11} />}
                  Потерянные
                </motion.button>

                {/* Refresh */}
                <motion.button
                  onClick={handleRefresh}
                  className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium"
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
                {!isReadOnly && (
                  <motion.button
                    onClick={() => setCreateOpen(true)}
                    className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium"
                    style={{
                      background: "var(--accent)",
                      border: "1px solid var(--accent)",
                      color: "var(--bg-primary)",
                    }}
                    whileTap={{ scale: 0.97 }}
                  >
                    <Plus size={11} />
                    Новая карточка
                  </motion.button>
                )}
                <motion.button
                  onClick={() => setShowCustomize((prev) => !prev)}
                  className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium"
                  style={{
                    background: showCustomize ? "var(--accent-muted)" : "var(--input-bg)",
                    border: `1px solid ${showCustomize ? "var(--accent)" : "var(--border-color)"}`,
                    color: showCustomize ? "var(--accent)" : "var(--text-muted)",
                  }}
                  whileTap={{ scale: 0.97 }}
                >
                  <SlidersHorizontal size={11} />
                  Конструктор
                </motion.button>
              </div>
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-2">
              <span
                className="rounded-lg px-3 py-1 text-xs font-medium"
                style={{
                  background: "var(--input-bg)",
                  border: "1px solid var(--border-color)",
                  color: "var(--text-muted)",
                }}
              >
                {scopeLabel}
              </span>
              {!isReadOnly && (
                <>
                  <span
                    className="rounded-lg px-3 py-1 text-xs font-medium"
                    style={{
                      background: "rgba(59,130,246,0.12)",
                      border: "1px solid rgba(59,130,246,0.25)",
                      color: "#93C5FD",
                    }}
                  >
                    Перетаскивание меняет статус
                  </span>
                  <span
                    className="rounded-lg px-3 py-1 text-xs font-medium"
                    style={{
                      background: "rgba(16,185,129,0.12)",
                      border: "1px solid rgba(16,185,129,0.25)",
                      color: "#6EE7B7",
                    }}
                  >
                    На карточке доступны заметка и напоминание
                  </span>
                </>
              )}
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

            <AnimatePresence>
              {showCustomize && (
                <motion.div
                  initial={{ opacity: 0, y: -8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  className="mt-4 rounded-2xl border p-4"
                  style={{
                    background: "rgba(255,255,255,0.03)",
                    borderColor: "var(--border-color)",
                  }}
                >
                  <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                    <div className="space-y-2">
                      <div className="flex items-center gap-2">
                        <LayoutGrid size={14} style={{ color: "var(--accent)" }} />
                        <span className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--accent)" }}>
                          НАСТРОЙКА КАНБАНА
                        </span>
                      </div>
                      <p className="max-w-2xl text-sm" style={{ color: "var(--text-muted)" }}>
                        Каждый пользователь собирает свою доску сам: режим раскладки, видимые этапы и состав карточки.
                        Настройка сохраняется в профиле и влияет только на ваш аккаунт.
                      </p>
                    </div>
                    <span
                      className="rounded-lg px-3 py-1 text-xs font-medium"
                      style={{
                        background: "var(--input-bg)",
                        border: "1px solid var(--border-color)",
                        color: savingPrefs ? "var(--accent)" : "var(--text-muted)",
                      }}
                    >
                      {savingPrefs ? "Сохраняю..." : "Сохранение авто"}
                    </span>
                  </div>

                  <div className="mt-4 grid gap-4 xl:grid-cols-3">
                    <div>
                      <div className="mb-2 text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
                        РАСКЛАДКА
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {(["grid", "board"] as const).map((mode) => (
                          <button
                            key={mode}
                            type="button"
                            onClick={() => {
                              setLayoutMode(mode);
                              void persistPipelinePrefs({ pipeline_layout: mode });
                            }}
                            className="rounded-lg px-3 py-2 text-xs font-medium"
                            style={{
                              background: layoutMode === mode ? "var(--accent-muted)" : "var(--input-bg)",
                              border: `1px solid ${layoutMode === mode ? "var(--accent)" : "var(--border-color)"}`,
                              color: layoutMode === mode ? "var(--accent)" : "var(--text-secondary)",
                            }}
                          >
                            {mode === "grid" ? "Ряды" : "Доска"}
                          </button>
                        ))}
                      </div>
                    </div>

                    <div>
                      <div className="mb-2 text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
                        ПОЛЯ КАРТОЧКИ
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {CARD_FIELD_OPTIONS.map((field) => {
                          const active = cardFields.includes(field.key);
                          return (
                            <button
                              key={field.key}
                              type="button"
                              onClick={() => {
                                const next = active
                                  ? cardFields.filter((item) => item !== field.key)
                                  : [...cardFields, field.key];
                                const finalFields = next.length > 0 ? next : DEFAULT_CARD_FIELDS;
                                setCardFields(finalFields);
                                void persistPipelinePrefs({ pipeline_card_fields: finalFields });
                              }}
                              className="rounded-lg px-3 py-2 text-xs font-medium"
                              style={{
                                background: active ? "var(--accent-muted)" : "var(--input-bg)",
                                border: `1px solid ${active ? "var(--accent)" : "var(--border-color)"}`,
                                color: active ? "var(--accent)" : "var(--text-secondary)",
                              }}
                            >
                              {field.label}
                            </button>
                          );
                        })}
                      </div>
                    </div>

                    <div>
                      <div className="mb-2 text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
                        ВИДИМЫЕ ЭТАПЫ
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {PIPELINE_STATUSES.map((status) => {
                          const active = pipelineColumns.includes(status);
                          return (
                            <button
                              key={status}
                              type="button"
                              onClick={() => {
                                const next = active
                                  ? pipelineColumns.filter((item) => item !== status)
                                  : [...pipelineColumns, status];
                                if (next.length < 2) return;
                                setPipelineColumns(next);
                                void persistPipelinePrefs({ pipeline_columns: next });
                              }}
                              className="rounded-lg px-3 py-2 text-xs font-medium"
                              style={{
                                background: active ? "var(--accent-muted)" : "var(--input-bg)",
                                border: `1px solid ${active ? "var(--accent)" : "var(--border-color)"}`,
                                color: active ? "var(--accent)" : "var(--text-secondary)",
                              }}
                            >
                              {CLIENT_STATUS_LABELS[status]}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
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
            className={
              layoutMode === "board"
                ? "flex-1 overflow-x-auto overflow-y-hidden px-4 pb-4"
                : "flex-1 overflow-y-auto px-4 pb-4"
            }
            style={{ scrollbarWidth: "thin" }}
          >
            {error && (
              <div
                className="mx-auto mb-4 max-w-[1600px] rounded-xl px-4 py-3 text-sm"
                style={{
                  background: "color-mix(in srgb, var(--danger) 12%, transparent)",
                  border: "1px solid color-mix(in srgb, var(--danger) 20%, transparent)",
                  color: "var(--danger)",
                }}
              >
                {error}
              </div>
            )}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.1 }}
              className={
                layoutMode === "board"
                  ? "mx-auto flex min-w-max gap-3 pb-6 snap-x snap-mandatory"
                  : "mx-auto grid max-w-[1600px] gap-3 pb-6 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4"
              }
            >
              {visibleStatuses.map((status, i) => (
                <motion.div
                  key={status}
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.04 * i }}
                  className="h-full snap-start min-w-[260px]"
                >
                  <PipelineColumn
                    ref={(el) => setColumnRef(status, el)}
                    status={status}
                    clients={grouped[status] || []}
                    isOver={dragState.overColumn === status}
                    activeId={dragState.activeId}
                    userRole={userRole}
                    readOnly={isReadOnly}
                    layoutMode={layoutMode}
                    visibleFields={cardFields}
                    onQuickNote={isReadOnly ? undefined : setNoteClient}
                    onReminder={isReadOnly ? undefined : setReminderClient}
                    onInlineNoteSubmit={isReadOnly ? undefined : handleInlineNoteSubmit}
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
              <PipelineCard client={draggedClient} userRole={userRole} readOnly visibleFields={cardFields} />
            </motion.div>
          )}
        </AnimatePresence>

        {!isReadOnly && (
          <ClientCreateModal
            open={createOpen}
            onClose={() => setCreateOpen(false)}
            onCreated={() => {
              setCreateOpen(false);
              fetchClients();
              fetchStats();
            }}
          />
        )}

        {!isReadOnly && noteClient && (
          <InteractionCreateModal
            open={Boolean(noteClient)}
            clientId={noteClient.id}
            initialType="note"
            onClose={() => setNoteClient(null)}
            onCreated={() => {
              setNoteClient(null);
              fetchClients();
            }}
          />
        )}

        {!isReadOnly && reminderClient && (
          <ReminderCreateModal
            open={Boolean(reminderClient)}
            clientId={reminderClient.id}
            clientName={reminderClient.full_name}
            onClose={() => setReminderClient(null)}
            onCreated={() => {
              setReminderClient(null);
              fetchClients();
            }}
          />
        )}
      </div>
    </AuthLayout>
  );
}
