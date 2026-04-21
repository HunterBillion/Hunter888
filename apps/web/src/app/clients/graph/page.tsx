"use client";

import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import Link from "next/link";
import {
  ArrowRight,
  ChevronLeft,
  GitBranch,
  Loader2,
  Network,
  Users,
} from "lucide-react";
import { BackButton } from "@/components/ui/BackButton";
import { FunnelChart } from "@/components/clients/FunnelChart";
import { api } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import AuthLayout from "@/components/layout/AuthLayout";
import type { ClientStatus, UserRole } from "@/types";
import { CLIENT_STATUS_COLORS, CLIENT_STATUS_LABELS } from "@/types";

interface GraphTransition {
  from: ClientStatus;
  to: ClientStatus;
}

interface GraphData {
  status_counts: Partial<Record<ClientStatus, number>>;
  transitions: GraphTransition[];
  total_clients: number;
  total_managers: number;
}

const STAGE_ORDER: ClientStatus[] = [
  "new", "contacted", "interested", "consultation", "thinking",
  "consent_given", "contract_signed", "in_process", "completed",
  "lost", "consent_revoked", "paused",
];

function formatCount(value: number): string {
  return new Intl.NumberFormat("ru-RU").format(value);
}

function getScopeLabel(role: UserRole | undefined): string {
  if (role === "admin") return "Видимость: все команды, все менеджеры и РОП.";
  if (role === "rop") return "Видимость: только ваша команда и подчинённые менеджеры.";
  if (role === "manager") return "Видимость: только ваши реальные клиенты.";
  if (role === "methodologist") return "Видимость: read-only по реальным данным и статистике.";
  return "Видимость определяется вашей ролью.";
}

export default function ClientGraphPage() {
  const { user } = useAuth();
  const [data, setData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedStage, setSelectedStage] = useState<ClientStatus>("contacted");

  useEffect(() => {
    if (!user) return;

    api
      .get("/clients/graph/data")
      .then((resp: GraphData) => {
        setData(resp);
        const firstActive = STAGE_ORDER.find((status) => (resp.status_counts[status] || 0) > 0);
        if (firstActive) {
          setSelectedStage(firstActive);
        }
      })
      .catch((err: Error) => setError(err.message || "Ошибка загрузки"))
      .finally(() => setLoading(false));
  }, [user]);

  const scopeLabel = getScopeLabel(user?.role);
  const selectedCount = data?.status_counts[selectedStage] || 0;
  const totalClients = data?.total_clients || 0;
  const selectedShare = totalClients > 0 ? Math.round((selectedCount / totalClients) * 100) : 0;

  const stageFlows = useMemo(() => {
    const transitions = data?.transitions || [];
    return {
      incoming: transitions.filter((item) => item.to === selectedStage),
      outgoing: transitions.filter((item) => item.from === selectedStage),
    };
  }, [data?.transitions, selectedStage]);

  const stageNavigation = useMemo(() => {
    const previous = stageFlows.incoming[0]?.from || null;
    const next = stageFlows.outgoing[0]?.to || null;
    return { previous, next };
  }, [stageFlows]);

  const summary = useMemo(() => {
    const counts = data?.status_counts || {};
    const completed = counts.completed || 0;
    const lost = counts.lost || 0;
    const paused = counts.paused || 0;
    const revoked = counts.consent_revoked || 0;
    return {
      activePath: Math.max(totalClients - completed - lost, 0),
      recoveryPool: lost + paused + revoked,
      managers: data?.total_managers || 0,
    };
  }, [data?.status_counts, data?.total_managers, totalClients]);

  const nodeLayoutDescriptions: Record<ClientStatus, { kind: "primary" | "branch"; description: string }> = {
    new: { kind: "primary", description: "Карточка создана, контакт ещё не подтверждён." },
    contacted: { kind: "primary", description: "Первичный контакт состоялся, клиент в активной обработке." },
    interested: { kind: "primary", description: "Интерес подтверждён, клиент готов двигаться дальше." },
    consultation: { kind: "primary", description: "Назначена или проведена консультация по делу клиента." },
    thinking: { kind: "primary", description: "Клиент на стадии решения, ожидания документов или обратной связи." },
    consent_given: { kind: "primary", description: "Получено согласие на дальнейшую работу и обработку данных." },
    contract_signed: { kind: "primary", description: "Договорный этап завершён, клиент формально подтверждён." },
    in_process: { kind: "primary", description: "Клиент находится в активной юридической работе." },
    completed: { kind: "primary", description: "Основной путь клиента завершён успешно." },
    lost: { kind: "branch", description: "Клиент потерян: отказ, недозвон, прекращение диалога." },
    consent_revoked: { kind: "branch", description: "Клиент отозвал согласие и требует отдельной обработки." },
    paused: { kind: "branch", description: "Работа временно приостановлена, но клиент может вернуться в поток." },
  };

  return (
    <AuthLayout>
      <div className="panel-grid-bg min-h-screen">
        <div className="mx-auto max-w-[1600px] px-4 py-8">
          {/* ─── Header ─── */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between"
          >
            <div className="space-y-2">
              <div className="flex items-center gap-3">
                <BackButton href="/clients" label="К клиентам" />
                <div
                  className="flex h-11 w-11 items-center justify-center rounded-2xl"
                  style={{ background: "var(--accent)", color: "var(--bg-primary)" }}
                >
                  <Network size={20} />
                </div>
                <div>
                  <h1 className="font-display text-2xl font-bold" style={{ color: "var(--text-primary)" }}>
                    Воронка клиентов
                  </h1>
                  <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                    Конверсия между этапами и зоны оттока — видна сразу, без интерактива.
                  </p>
                </div>
              </div>
            </div>
          </motion.div>

          {/* ─── Empty state ─── */}
          {totalClients === 0 && !loading && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="mt-6 glass-panel rounded-2xl p-8 text-center"
            >
              <Users size={48} style={{ color: "var(--text-muted)", margin: "0 auto 16px", opacity: 0.4 }} />
              <h3 className="font-display text-lg font-semibold mb-2" style={{ color: "var(--text-primary)" }}>
                Портфель клиентов пуст
              </h3>
              <p className="text-sm mb-4" style={{ color: "var(--text-muted)" }}>
                Граф дел появится когда вы добавите первого клиента.
              </p>
              <Link href="/clients" className="btn-neon inline-flex items-center gap-2 text-sm">
                Перейти к клиентам
              </Link>
            </motion.div>
          )}

          {/* ─── Summary cards ─── */}
          <div className="mt-6 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {[
              { label: "Карточек в модуле", value: formatCount(totalClients), icon: Users, color: "var(--accent)" },
              { label: "В активном пути", value: formatCount(summary.activePath), icon: ArrowRight, color: "var(--info)" },
              { label: "Зона возврата", value: formatCount(summary.recoveryPool), icon: GitBranch, color: "var(--warning)" },
              { label: "Видимых менеджеров", value: formatCount(summary.managers), icon: Network, color: "var(--success)" },
            ].map((card, index) => {
              const Icon = card.icon;
              return (
                <motion.div
                  key={card.label}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: index * 0.05 }}
                  className="glass-panel p-4"
                >
                  <Icon size={16} style={{ color: card.color }} />
                  <div className="mt-2 text-2xl font-bold" style={{ color: "var(--text-primary)" }}>
                    {card.value}
                  </div>
                  <div className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
                    {card.label.toUpperCase()}
                  </div>
                </motion.div>
              );
            })}
          </div>

          {/* ─── Main content: Funnel + Sidebar ─── */}
          <div className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
            {/* Conversion funnel */}
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              className="glass-panel overflow-hidden p-4 sm:p-5"
            >
              <div className="mb-4">
                <h2 className="text-sm font-semibold uppercase tracking-wide" style={{ color: "var(--accent)" }}>
                  ВОРОНКА КОНВЕРСИИ
                </h2>
                <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                  Каждый этап — доля от первоначального входа и конверсия между этапами.
                </p>
              </div>

              {error && (
                <div className="rounded-2xl p-6 text-sm" style={{ background: "var(--danger-muted)", color: "#FCA5A5" }}>
                  {error}
                </div>
              )}

              {loading && (
                <div className="flex min-h-[320px] items-center justify-center">
                  <Loader2 size={28} className="animate-spin" style={{ color: "var(--accent)" }} />
                </div>
              )}

              {!loading && !error && data && (
                <FunnelChart
                  statusCounts={data.status_counts}
                  selectedStage={selectedStage}
                  onSelectStage={setSelectedStage}
                />
              )}
            </motion.div>

            {/* ─── Sidebar ─── */}
            <motion.aside
              initial={{ opacity: 0, x: 12 }}
              animate={{ opacity: 1, x: 0 }}
              className="space-y-4"
            >
              {/* Selected stage panel */}
              <div className="glass-panel p-5">
                <div className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--accent)" }}>
                  ВЫБРАННЫЙ ЭТАП
                </div>
                <div className="mt-3 flex items-center justify-between gap-3">
                  <div>
                    <h3 className="text-lg font-semibold" style={{ color: "var(--text-primary)" }}>
                      {CLIENT_STATUS_LABELS[selectedStage]}
                    </h3>
                    <p className="mt-1 text-sm" style={{ color: "var(--text-secondary)" }}>
                      {nodeLayoutDescriptions[selectedStage].description}
                    </p>
                  </div>
                  <div
                    className="rounded-2xl px-3 py-2 text-right"
                    style={{
                      background: `${CLIENT_STATUS_COLORS[selectedStage]}18`,
                      border: `1px solid ${CLIENT_STATUS_COLORS[selectedStage]}33`,
                    }}
                  >
                    <div className="text-xl font-bold" style={{ color: CLIENT_STATUS_COLORS[selectedStage] }}>
                      {formatCount(selectedCount)}
                    </div>
                    <div className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                      {selectedShare}% от видимых
                    </div>
                  </div>
                </div>

                <div className="mt-4 grid grid-cols-2 gap-3">
                  <div className="rounded-2xl p-3" style={{ background: "rgba(255,255,255,0.03)" }}>
                    <div className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
                      ТИП
                    </div>
                    <div className="mt-2 text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                      {nodeLayoutDescriptions[selectedStage].kind === "primary" ? "Основной поток" : "Риск / возврат"}
                    </div>
                  </div>
                  <div className="rounded-2xl p-3" style={{ background: "rgba(255,255,255,0.03)" }}>
                    <div className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
                      ДОЛЯ
                    </div>
                    <div className="mt-2 text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                      {selectedShare}%
                    </div>
                  </div>
                </div>

                <div className="mt-4 grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    disabled={!stageNavigation.previous}
                    onClick={() => stageNavigation.previous && setSelectedStage(stageNavigation.previous)}
                    className="inline-flex items-center justify-center gap-2 rounded-xl px-3 py-2 text-xs font-medium"
                    style={{
                      background: stageNavigation.previous ? "var(--input-bg)" : "rgba(255,255,255,0.04)",
                      border: "1px solid var(--border-color)",
                      color: stageNavigation.previous ? "var(--text-primary)" : "var(--text-muted)",
                      opacity: stageNavigation.previous ? 1 : 0.5,
                    }}
                  >
                    <ChevronLeft size={12} />
                    Назад
                  </button>
                  <button
                    type="button"
                    disabled={!stageNavigation.next}
                    onClick={() => stageNavigation.next && setSelectedStage(stageNavigation.next)}
                    className="inline-flex items-center justify-center gap-2 rounded-xl px-3 py-2 text-xs font-medium"
                    style={{
                      background: stageNavigation.next ? "var(--input-bg)" : "rgba(255,255,255,0.04)",
                      border: "1px solid var(--border-color)",
                      color: stageNavigation.next ? "var(--text-primary)" : "var(--text-muted)",
                      opacity: stageNavigation.next ? 1 : 0.5,
                    }}
                  >
                    Вперёд
                    <ArrowRight size={12} />
                  </button>
                </div>
              </div>

              {/* Transitions panel */}
              <div className="glass-panel p-5">
                <div className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--accent)" }}>
                  ПЕРЕХОДЫ
                </div>
                <div className="mt-4 space-y-4">
                  <div>
                    <div className="mb-2 text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
                      МОЖНО ПРИЙТИ ИЗ
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {stageFlows.incoming.length > 0 ? (
                        stageFlows.incoming.map((item) => (
                          <button
                            key={`${item.from}-${item.to}-in`}
                            type="button"
                            onClick={() => setSelectedStage(item.from)}
                            className="rounded-full px-2.5 py-1 text-xs"
                            style={{
                              background: `${CLIENT_STATUS_COLORS[item.from]}18`,
                              color: CLIENT_STATUS_COLORS[item.from],
                              border: `1px solid ${CLIENT_STATUS_COLORS[item.from]}2f`,
                            }}
                          >
                            {CLIENT_STATUS_LABELS[item.from]}
                          </button>
                        ))
                      ) : (
                        <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                          Начальная точка маршрута
                        </span>
                      )}
                    </div>
                  </div>

                  <div>
                    <div className="mb-2 text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
                      МОЖНО УЙТИ В
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {stageFlows.outgoing.length > 0 ? (
                        stageFlows.outgoing.map((item) => (
                          <button
                            key={`${item.from}-${item.to}-out`}
                            type="button"
                            onClick={() => setSelectedStage(item.to)}
                            className="rounded-full px-2.5 py-1 text-xs"
                            style={{
                              background: `${CLIENT_STATUS_COLORS[item.to]}18`,
                              color: CLIENT_STATUS_COLORS[item.to],
                              border: `1px solid ${CLIENT_STATUS_COLORS[item.to]}2f`,
                            }}
                          >
                            {CLIENT_STATUS_LABELS[item.to]}
                          </button>
                        ))
                      ) : (
                        <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                          Финальная точка маршрута
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              </div>

              {/* Branch statuses accent panel */}
              <div className="glass-panel p-5">
                <div className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--accent)" }}>
                  СТАТУСНЫЕ АКЦЕНТЫ
                </div>
                <div className="mt-3 space-y-2">
                  {(["lost", "consent_revoked", "paused"] as ClientStatus[]).map((status) => (
                    <button
                      key={status}
                      type="button"
                      onClick={() => setSelectedStage(status)}
                      className="flex w-full items-center justify-between rounded-2xl px-3 py-2 text-left"
                      style={{
                        background: selectedStage === status ? `${CLIENT_STATUS_COLORS[status]}18` : "rgba(255,255,255,0.03)",
                        border: `1px solid ${selectedStage === status ? CLIENT_STATUS_COLORS[status] : "rgba(255,255,255,0.08)"}`,
                      }}
                    >
                      <span className="text-sm" style={{ color: "var(--text-primary)" }}>
                        {CLIENT_STATUS_LABELS[status]}
                      </span>
                      <span className="text-sm font-semibold" style={{ color: CLIENT_STATUS_COLORS[status] }}>
                        {formatCount(data?.status_counts[status] || 0)}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            </motion.aside>
          </div>
        </div>
      </div>
    </AuthLayout>
  );
}
