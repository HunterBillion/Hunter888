"use client";

import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import Link from "next/link";
import { ArrowLeft, ArrowRight, GitBranch, Loader2, Network, RotateCcw, Users } from "lucide-react";
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

type StageMeta = {
  x: number;
  y: number;
  kind: "primary" | "branch";
  description: string;
};

const STAGE_LAYOUT: Record<ClientStatus, StageMeta> = {
  new: {
    x: 7,
    y: 16,
    kind: "primary",
    description: "Карточка создана, контакт ещё не подтверждён.",
  },
  contacted: {
    x: 20,
    y: 16,
    kind: "primary",
    description: "Первичный контакт состоялся, клиент в активной обработке.",
  },
  interested: {
    x: 33,
    y: 16,
    kind: "primary",
    description: "Интерес подтверждён, клиент готов двигаться дальше.",
  },
  consultation: {
    x: 46,
    y: 16,
    kind: "primary",
    description: "Назначена или проведена консультация по делу клиента.",
  },
  thinking: {
    x: 59,
    y: 16,
    kind: "primary",
    description: "Клиент на стадии решения, ожидания документов или обратной связи.",
  },
  consent_given: {
    x: 46,
    y: 46,
    kind: "primary",
    description: "Получено согласие на дальнейшую работу и обработку данных.",
  },
  contract_signed: {
    x: 59,
    y: 46,
    kind: "primary",
    description: "Договорный этап завершён, клиент формально подтверждён.",
  },
  in_process: {
    x: 72,
    y: 46,
    kind: "primary",
    description: "Клиент находится в активной юридической работе.",
  },
  completed: {
    x: 85,
    y: 46,
    kind: "primary",
    description: "Основной путь клиента завершён успешно.",
  },
  lost: {
    x: 33,
    y: 78,
    kind: "branch",
    description: "Клиент потерян: отказ, недозвон, прекращение диалога.",
  },
  consent_revoked: {
    x: 59,
    y: 78,
    kind: "branch",
    description: "Клиент отозвал согласие и требует отдельной обработки.",
  },
  paused: {
    x: 72,
    y: 78,
    kind: "branch",
    description: "Работа временно приостановлена, но клиент может вернуться в поток.",
  },
};

const STAGE_ORDER: ClientStatus[] = [
  "new",
  "contacted",
  "interested",
  "consultation",
  "thinking",
  "consent_given",
  "contract_signed",
  "in_process",
  "completed",
  "lost",
  "consent_revoked",
  "paused",
];

const branchStages = new Set<ClientStatus>(["lost", "consent_revoked", "paused"]);

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

  const selectedCount = data?.status_counts[selectedStage] || 0;
  const totalClients = data?.total_clients || 0;
  const selectedShare = totalClients > 0 ? Math.round((selectedCount / totalClients) * 100) : 0;
  const maxCount = Math.max(...STAGE_ORDER.map((status) => data?.status_counts[status] || 0), 1);
  const scopeLabel = getScopeLabel(user?.role);

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
      completed,
      managers: data?.total_managers || 0,
    };
  }, [data?.status_counts, data?.total_managers, totalClients]);

  return (
    <AuthLayout>
      <div className="panel-grid-bg min-h-screen">
        <div className="mx-auto max-w-7xl px-4 py-8">
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between"
          >
            <div className="space-y-2">
              <div className="flex items-center gap-3">
                <Link
                  href="/clients"
                  className="flex h-11 w-11 items-center justify-center rounded-2xl border transition-colors"
                  style={{ borderColor: "var(--border-color)", color: "var(--text-muted)" }}
                >
                  <ArrowLeft size={18} />
                </Link>
                <div
                  className="flex h-11 w-11 items-center justify-center rounded-2xl"
                  style={{ background: "var(--accent)", color: "#050505" }}
                >
                  <Network size={20} />
                </div>
                <div>
                  <h1 className="font-display text-2xl font-bold" style={{ color: "var(--text-primary)" }}>
                    Lifecycle Graph
                  </h1>
                  <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                    Карта этапов клиента, а не оргструктура менеджеров.
                  </p>
                </div>
              </div>
              <p className="max-w-3xl text-sm" style={{ color: "var(--text-secondary)" }}>
                Экран показывает единый маршрут клиента, ветки потерь и возврата, а также фактическое распределение
                текущих карточек по этапам.
              </p>
              <p className="text-xs font-mono tracking-[0.16em]" style={{ color: "var(--text-muted)" }}>
                {scopeLabel}
              </p>
            </div>

            <button
              type="button"
              onClick={() => setSelectedStage("contacted")}
              className="inline-flex items-center gap-2 rounded-xl px-3 py-2 text-xs font-mono"
              style={{
                background: "var(--input-bg)",
                border: "1px solid var(--border-color)",
                color: "var(--text-secondary)",
              }}
            >
              <RotateCcw size={14} />
              Сбросить фокус
            </button>
          </motion.div>

          <div className="mt-6 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {[
              { label: "Карточек в модуле", value: formatCount(totalClients), icon: Users, color: "var(--accent)" },
              { label: "В активном пути", value: formatCount(summary.activePath), icon: ArrowRight, color: "#3B82F6" },
              { label: "Зона возврата", value: formatCount(summary.recoveryPool), icon: GitBranch, color: "#F97316" },
              { label: "Видимых менеджеров", value: formatCount(summary.managers), icon: Network, color: "#10B981" },
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
                  <div className="text-[10px] font-mono tracking-wider" style={{ color: "var(--text-muted)" }}>
                    {card.label.toUpperCase()}
                  </div>
                </motion.div>
              );
            })}
          </div>

          <div className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              className="glass-panel overflow-hidden p-4 sm:p-5"
            >
              <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h2 className="text-sm font-mono tracking-[0.2em]" style={{ color: "var(--accent)" }}>
                    CLIENT PATH MAP
                  </h2>
                  <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                    Основной путь сверху, ветки риска и возврата снизу.
                  </p>
                </div>
                <div className="flex flex-wrap gap-2 text-[10px] font-mono">
                  <span
                    className="rounded-full px-2 py-1"
                    style={{ background: "rgba(59,130,246,0.12)", color: "#3B82F6", border: "1px solid rgba(59,130,246,0.25)" }}
                  >
                    Основной путь
                  </span>
                  <span
                    className="rounded-full px-2 py-1"
                    style={{ background: "rgba(249,115,22,0.12)", color: "#F97316", border: "1px solid rgba(249,115,22,0.25)" }}
                  >
                    Ветви риска
                  </span>
                </div>
              </div>

              {error && (
                <div className="rounded-2xl p-6 text-sm" style={{ background: "rgba(239,68,68,0.12)", color: "#FCA5A5" }}>
                  {error}
                </div>
              )}

              {loading && (
                <div className="flex min-h-[520px] items-center justify-center">
                  <Loader2 size={28} className="animate-spin" style={{ color: "var(--accent)" }} />
                </div>
              )}

              {!loading && !error && (
                <div
                  className="relative overflow-hidden rounded-[28px] border"
                  style={{
                    minHeight: 540,
                    background:
                      "radial-gradient(circle at top, rgba(255,212,0,0.08), transparent 32%), linear-gradient(180deg, rgba(8,8,12,0.94), rgba(6,7,10,0.98))",
                    borderColor: "rgba(255,255,255,0.08)",
                  }}
                >
                  <svg className="absolute inset-0 h-full w-full" viewBox="0 0 1000 600" preserveAspectRatio="none">
                    <defs>
                      <marker id="graph-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                        <path d="M0 0L10 5L0 10Z" fill="rgba(255,255,255,0.35)" />
                      </marker>
                    </defs>
                    {(data?.transitions || []).map((transition) => {
                      const from = STAGE_LAYOUT[transition.from];
                      const to = STAGE_LAYOUT[transition.to];
                      if (!from || !to) {
                        return null;
                      }
                      const isSelected = selectedStage === transition.from || selectedStage === transition.to;
                      const edgeColor = isSelected ? "rgba(255,212,0,0.75)" : "rgba(255,255,255,0.18)";
                      return (
                        <line
                          key={`${transition.from}-${transition.to}`}
                          x1={from.x * 10}
                          y1={from.y * 6}
                          x2={to.x * 10}
                          y2={to.y * 6}
                          stroke={edgeColor}
                          strokeWidth={isSelected ? 3 : 1.5}
                          strokeDasharray={branchStages.has(transition.to) ? "8 7" : undefined}
                          markerEnd="url(#graph-arrow)"
                        />
                      );
                    })}
                  </svg>

                  <div className="relative min-h-[540px]">
                    {STAGE_ORDER.map((status) => {
                      const meta = STAGE_LAYOUT[status];
                      const count = data?.status_counts[status] || 0;
                      const color = CLIENT_STATUS_COLORS[status];
                      const isSelected = selectedStage === status;
                      const width = 108 + Math.round((count / maxCount) * 44);

                      return (
                        <button
                          key={status}
                          type="button"
                          onClick={() => setSelectedStage(status)}
                          className="absolute rounded-[24px] px-4 py-3 text-left transition-all"
                          style={{
                            left: `${meta.x}%`,
                            top: `${meta.y}%`,
                            width,
                            transform: "translate(-50%, -50%)",
                            background: isSelected ? `${color}22` : "rgba(255,255,255,0.03)",
                            border: `1px solid ${isSelected ? color : "rgba(255,255,255,0.08)"}`,
                            boxShadow: isSelected ? `0 0 0 1px ${color}44, 0 18px 45px rgba(0,0,0,0.28)` : "0 14px 30px rgba(0,0,0,0.18)",
                          }}
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <div className="text-[10px] font-mono tracking-[0.18em]" style={{ color: isSelected ? color : "var(--text-muted)" }}>
                                {meta.kind === "primary" ? "PRIMARY" : "BRANCH"}
                              </div>
                              <div className="mt-1 text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
                                {CLIENT_STATUS_LABELS[status]}
                              </div>
                            </div>
                            <div
                              className="flex h-8 min-w-8 items-center justify-center rounded-full px-2 text-sm font-semibold"
                              style={{ background: `${color}22`, color }}
                            >
                              {formatCount(count)}
                            </div>
                          </div>
                          <div className="mt-2 text-[11px]" style={{ color: "var(--text-muted)" }}>
                            {count > 0 ? `${Math.round((count / Math.max(totalClients, 1)) * 100)}% видимых карточек` : "Пока нет карточек"}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
            </motion.div>

            <motion.aside
              initial={{ opacity: 0, x: 12 }}
              animate={{ opacity: 1, x: 0 }}
              className="space-y-4"
            >
              <div className="glass-panel p-5">
                <div className="text-xs font-mono tracking-[0.2em]" style={{ color: "var(--accent)" }}>
                  ВЫБРАННЫЙ ЭТАП
                </div>
                <div className="mt-3 flex items-center justify-between gap-3">
                  <div>
                    <h3 className="text-lg font-semibold" style={{ color: "var(--text-primary)" }}>
                      {CLIENT_STATUS_LABELS[selectedStage]}
                    </h3>
                    <p className="mt-1 text-sm" style={{ color: "var(--text-secondary)" }}>
                      {STAGE_LAYOUT[selectedStage].description}
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
                    <div className="text-[10px] font-mono" style={{ color: "var(--text-muted)" }}>
                      {selectedShare}% от видимых
                    </div>
                  </div>
                </div>

                <div className="mt-4 grid grid-cols-2 gap-3">
                  <div className="rounded-2xl p-3" style={{ background: "rgba(255,255,255,0.03)" }}>
                    <div className="text-[10px] font-mono tracking-[0.16em]" style={{ color: "var(--text-muted)" }}>
                      ТИП ЭТАПА
                    </div>
                    <div className="mt-2 text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                      {STAGE_LAYOUT[selectedStage].kind === "primary" ? "Основной путь" : "Служебная ветка"}
                    </div>
                  </div>
                  <div className="rounded-2xl p-3" style={{ background: "rgba(255,255,255,0.03)" }}>
                    <div className="text-[10px] font-mono tracking-[0.16em]" style={{ color: "var(--text-muted)" }}>
                      РИСК
                    </div>
                    <div className="mt-2 text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                      {branchStages.has(selectedStage) ? "Нужен контроль" : "Нормальный поток"}
                    </div>
                  </div>
                </div>

                <div className="mt-4 grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    disabled={!stageNavigation.previous}
                    onClick={() => stageNavigation.previous && setSelectedStage(stageNavigation.previous)}
                    className="inline-flex items-center justify-center gap-2 rounded-xl px-3 py-2 text-xs font-mono"
                    style={{
                      background: stageNavigation.previous ? "var(--input-bg)" : "rgba(255,255,255,0.04)",
                      border: "1px solid var(--border-color)",
                      color: stageNavigation.previous ? "var(--text-primary)" : "var(--text-muted)",
                      opacity: stageNavigation.previous ? 1 : 0.5,
                    }}
                  >
                    <ArrowLeft size={12} />
                    Назад
                  </button>
                  <button
                    type="button"
                    disabled={!stageNavigation.next}
                    onClick={() => stageNavigation.next && setSelectedStage(stageNavigation.next)}
                    className="inline-flex items-center justify-center gap-2 rounded-xl px-3 py-2 text-xs font-mono"
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

              <div className="glass-panel p-5">
                <div className="text-xs font-mono tracking-[0.2em]" style={{ color: "var(--accent)" }}>
                  ПЕРЕХОДЫ
                </div>
                <div className="mt-4 space-y-4">
                  <div>
                    <div className="mb-2 text-[10px] font-mono tracking-[0.16em]" style={{ color: "var(--text-muted)" }}>
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
                    <div className="mb-2 text-[10px] font-mono tracking-[0.16em]" style={{ color: "var(--text-muted)" }}>
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

              <div className="glass-panel p-5">
                <div className="text-xs font-mono tracking-[0.2em]" style={{ color: "var(--accent)" }}>
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
