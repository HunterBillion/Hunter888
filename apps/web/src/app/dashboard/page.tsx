"use client";

import { useEffect, useMemo, useState, useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  LayoutDashboard,
  ArrowRight,
  ArrowUpDown,
  ChevronUp,
  ChevronDown,
  FileBarChart,
  Star,
  ShieldAlert,
} from "lucide-react";
import {
  UsersThree,
  TrendUp,
  Clock,
  Target,
  Trophy,
  ShieldWarning,
  Crown,
  ChartBar,
  BookOpen,
} from "@phosphor-icons/react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import AuthLayout from "@/components/layout/AuthLayout";
import { BackButton } from "@/components/ui/BackButton";
import { PixelInfoButton } from "@/components/ui/PixelInfoButton";
import { DashboardSkeleton } from "@/components/ui/Skeleton";
import { AnimatedCounter } from "@/components/ui/AnimatedCounter";
import { ScoreBadge } from "@/components/ui/ScoreBadge";
import { ClientStats } from "@/components/clients/ClientStats";
import { TrainingRecommendations } from "@/components/clients/TrainingRecommendations";
import { KnowledgeDashboardWidget } from "@/components/dashboard/KnowledgeDashboardWidget";
import { OceanProfileWidget } from "@/components/dashboard/OceanProfileWidget";
import { TeamHeatmap } from "@/components/dashboard/TeamHeatmap";
import { WeakLinks } from "@/components/dashboard/WeakLinks";
import { Benchmark } from "@/components/dashboard/Benchmark";
import { WeeklyReport } from "@/components/dashboard/WeeklyReport";
import { TeamTrendChart } from "@/components/dashboard/TeamTrendChart";
import { ActivityChart } from "@/components/dashboard/ActivityChart";
import { AlertPanel } from "@/components/dashboard/AlertPanel";
import BehaviorProfileCard from "@/components/behavior/BehaviorProfileCard";
import { ActivityFeed } from "@/components/activity/ActivityFeed";
import { useActivityFeed } from "@/hooks/useActivityFeed";
import type { DashboardROP, TeamMember, PipelineStats } from "@/types";
import { useNotificationStore } from "@/stores/useNotificationStore";
import { scoreColor } from "@/lib/utils";
import { getApiBaseUrl } from "@/lib/public-origin";
import { logger } from "@/lib/logger";
import dynamic from "next/dynamic";
import { DashboardSkeleton as WikiFallback } from "@/components/ui/Skeleton";

const WikiDashboard = dynamic(
  () => import("@/components/dashboard/WikiDashboard").then((m) => m.WikiDashboard),
  { loading: () => <WikiFallback />, ssr: false }
);

const ReportsDashboard = dynamic(
  () => import("@/components/dashboard/ReportsDashboard").then((m) => m.ReportsDashboard),
  { loading: () => <WikiFallback />, ssr: false }
);

const ReviewsAdmin = dynamic(
  () => import("@/components/dashboard/ReviewsAdmin").then((m) => m.ReviewsAdmin),
  { loading: () => <WikiFallback />, ssr: false }
);

/* ─── Constants ──────────────────────────────────────────────────────────── */

type TabId = "overview" | "analytics" | "team" | "tournament" | "wiki" | "reports" | "reviews";

const TABS: { id: TabId; label: string; icon: any; adminOnly?: boolean }[] = [
  { id: "overview", label: "Обзор", icon: LayoutDashboard },
  { id: "analytics", label: "Аналитика", icon: ChartBar },
  { id: "team", label: "Команда", icon: UsersThree },
  { id: "tournament", label: "Турнир", icon: Trophy },
  { id: "wiki", label: "Wiki", icon: BookOpen },
  { id: "reports", label: "Отчёты", icon: FileBarChart },
  { id: "reviews", label: "Отзывы", icon: Star, adminOnly: true },
];

const AVATAR_COLORS = [
  "var(--accent)", "var(--accent)", "var(--magenta)", "#F43F5E", "var(--warning)",
  "#EAB308", "var(--success)", "#14B8A6", "var(--info)", "var(--info)",
];

const podiumColors = ["var(--warning)", "var(--text-secondary)", "var(--warning)"];

type SortKey = "full_name" | "total_sessions" | "avg_score" | "best_score" | "sessions_this_week";
type SortDir = "asc" | "desc";

/* ─── Helpers ────────────────────────────────────────────────────────────── */

function getAvatarColor(id: string): string {
  let hash = 0;
  for (let i = 0; i < id.length; i++) hash = ((hash << 5) - hash + id.charCodeAt(i)) | 0;
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
}

function getInitials(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
}

/* ─── Component ──────────────────────────────────────────────────────────── */

export default function DashboardPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user } = useAuth();
  const [data, setData] = useState<DashboardROP | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pipelineStats, setPipelineStats] = useState<PipelineStats[]>([]);

  // Tab state — synced with URL
  const tabParam = searchParams.get("tab") as TabId | null;
  const [activeTab, setActiveTab] = useState<TabId>("overview");

  useEffect(() => {
    if (tabParam && TABS.some((t) => t.id === tabParam)) {
      setActiveTab(tabParam);
    }
  }, [tabParam]);

  const switchTab = useCallback((id: TabId) => {
    setActiveTab(id);
    const url = new URL(window.location.href);
    url.searchParams.set("tab", id);
    window.history.replaceState(null, "", url.toString());
  }, []);

  // Sorting for managers table
  const [sortKey, setSortKey] = useState<SortKey>("avg_score");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const toggleSort = useCallback((key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }, [sortKey]);

  const activityItems = useActivityFeed(data?.members ?? []);

  const sortedMembers = useMemo(() => {
    if (!data) return [];
    return [...data.members].sort((a, b) => {
      let va: number | string = (a as unknown as Record<string, number | string | null>)[sortKey] ?? -Infinity;
      let vb: number | string = (b as unknown as Record<string, number | string | null>)[sortKey] ?? -Infinity;
      if (va === null || va === undefined || va === -Infinity) va = typeof vb === "string" ? "" : -Infinity;
      if (vb === null || vb === undefined || vb === -Infinity) vb = typeof va === "string" ? "" : -Infinity;
      if (typeof va === "string") return sortDir === "asc" ? va.localeCompare(vb as string) : (vb as string).localeCompare(va);
      return sortDir === "asc" ? (va as number) - (vb as number) : (vb as number) - (va as number);
    });
  }, [data, sortKey, sortDir]);

  // Data fetching
  useEffect(() => {
    if (!user) return;
    const allowed = user.role === "rop" || user.role === "admin";
    if (!allowed) { setError("Доступ ограничен"); setLoading(false); return; }

    api.get("/dashboard/rop")
      .then((resp: DashboardROP) => setData(resp))
      .catch((err) => setError(err.message || "Ошибка загрузки"))
      .finally(() => setLoading(false));

    api.get("/clients/pipeline/stats")
      .then((stats: PipelineStats[]) => setPipelineStats(stats))
      .catch((err) => {
        logger.error("Failed to load pipeline stats:", err);
        useNotificationStore.getState().addToast({ title: "Воронка продаж", body: "Не удалось загрузить статистику воронки", type: "error" });
      });
  }, [user]);

  const handleExportPdf = useCallback(async () => {
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/dashboard/rop/export?period=week`, { credentials: "include" });
      if (!res.ok) {
        useNotificationStore.getState().addToast({ title: "Ошибка экспорта", body: `Не удалось скачать отчёт (${res.status})`, type: "error" });
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "team_report.pdf";
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      useNotificationStore.getState().addToast({ title: "Ошибка экспорта", body: "Не удалось скачать PDF-отчёт. Проверьте соединение.", type: "error" });
      logger.error("PDF export failed:", err);
    }
  }, []);

  /* ─── Sortable column header ───────────────────────────────────────────── */
  const SortHeader = ({ label, sortField }: { label: string; sortField: SortKey }) => (
    <th
      className="px-5 py-4 text-left font-semibold text-xs uppercase tracking-wide cursor-pointer select-none group"
      style={{ color: "var(--text-muted)" }}
      onClick={() => toggleSort(sortField)}
    >
      <span className="inline-flex items-center gap-1">
        {label}
        {sortKey === sortField ? (
          sortDir === "asc" ? <ChevronUp size={10} /> : <ChevronDown size={10} />
        ) : (
          <ArrowUpDown size={10} className="opacity-0 group-hover:opacity-50 transition-opacity" />
        )}
      </span>
    </th>
  );

  return (
    <AuthLayout>
      <div className="relative panel-grid-bg min-h-screen">
        <div className="app-page">
          <BackButton href="/home" label="На главную" />

          {/* ─── Header ────────────────────────────────────────────────── */}
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <LayoutDashboard size={24} style={{ color: "var(--accent)" }} />
                <h1 className="font-display text-3xl font-bold tracking-wider" style={{ color: "var(--text-primary)" }}>
                  ПАНЕЛЬ РОП
                </h1>
              </div>
              <PixelInfoButton
                title="Панель РОП"
                sections={[
                  { icon: ChartBar, label: "Обзор", text: "Ключевые метрики команды: активность, средний балл, TP за неделю, вовлечённость" },
                  { icon: UsersThree, label: "Команда", text: "Список менеджеров с рейтингами, сравнение между собой, выявление отстающих" },
                  { icon: Target, label: "Heatmap", text: "Тепловая карта ошибок: где команда слабее всего (возражения, техники, знания)" },
                  { icon: Trophy, label: "Benchmark", text: "Сравнение вашей команды с другими командами/компаниями (анонимно)" },
                  { icon: TrendUp, label: "ROI", text: "Сколько тренировок → сколько закрытых сделок. Reports tab — PDF экспорт" },
                  { icon: BookOpen, label: "Wiki", text: "Корпоративные знания: скрипты возражений, регламенты. Автосинтез из успешных диалогов" },
                ]}
                footer="Быстрые действия: Export PDF (Reports tab), массовая рассылка заданий (Team tab)"
              />
            </div>
            <p className="mt-2 font-medium text-sm tracking-wide" style={{ color: "var(--text-muted)" }}>
              {data?.team.name ? `КОМАНДА: ${data.team.name.toUpperCase()}` : "АНАЛИТИКА КОМАНДЫ"}
            </p>
          </motion.div>

          {/* ─── Loading / Error ────────────────────────────────────────── */}
          {loading ? (
            <DashboardSkeleton />
          ) : error ? (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mt-16 flex flex-col items-center">
              <ShieldWarning size={40} weight="duotone" style={{ color: "var(--danger)" }} />
              <p className="mt-3 text-sm" style={{ color: "var(--danger)" }}>{error}</p>
            </motion.div>
          ) : data ? (
            <>
              {/* ─── Sticky Tab Bar ──────────────────────────────────────── */}
              <div
                className="sticky top-[60px] z-20 mt-6 flex items-stretch gap-2"
              >
                <div
                  className="flex-1 flex items-center justify-center gap-1 rounded-xl p-1.5 overflow-x-auto"
                  style={{ background: "var(--glass-bg)", border: "1px solid var(--glass-border)", backdropFilter: "blur(20px)" }}
                >
                  {TABS.filter((tab) => !tab.adminOnly || user?.role === "admin").map((tab) => {
                    const Icon = tab.icon;
                    const isActive = activeTab === tab.id;
                    return (
                      <button
                        key={tab.id}
                        onClick={() => switchTab(tab.id)}
                        className="relative flex items-center justify-center gap-2 flex-1 px-3 sm:px-5 py-3 rounded-xl font-medium text-sm uppercase tracking-wide whitespace-nowrap transition-all duration-200"
                        style={{
                          color: isActive ? "var(--text-primary)" : "var(--text-muted)",
                          fontWeight: isActive ? 700 : 500,
                        }}
                      >
                        <Icon size={18} weight="duotone" style={{ color: isActive ? "var(--accent)" : undefined }} />
                        <span className="hidden sm:inline">{tab.label}</span>
                        {isActive && (
                          <motion.div
                            layoutId="dashboard-tab-indicator"
                            className="absolute inset-0 rounded-xl"
                            style={{
                              background: "linear-gradient(135deg, var(--accent-muted), rgba(107,77,199,0.05))",
                              border: "1px solid var(--accent)",
                              boxShadow: "0 0 16px var(--accent-glow), inset 0 1px 0 rgba(255,255,255,0.06)",
                            }}
                            transition={{ type: "spring", stiffness: 400, damping: 30 }}
                          />
                        )}
                      </button>
                    );
                  })}
                </div>
                {/* 2026-04-20: admin-only shortcut to /admin section.
                    Sits next to the tab bar (not inside it) because admin
                    pages live on a separate route with their own layout. */}
                {user?.role === "admin" && (
                  <Link
                    href="/admin"
                    className="hidden md:inline-flex items-center gap-2 px-4 rounded-xl font-medium text-sm uppercase tracking-wide whitespace-nowrap transition hover:brightness-110"
                    style={{
                      background: "color-mix(in srgb, #fbbf24 14%, var(--glass-bg))",
                      border: "1px solid color-mix(in srgb, #fbbf24 40%, transparent)",
                      color: "#fbbf24",
                      backdropFilter: "blur(20px)",
                    }}
                    title="Панель администратора"
                  >
                    <ShieldAlert size={16} />
                    <span>Админка</span>
                  </Link>
                )}
              </div>

              {/* ─── Tab Content ──────────────────────────────────────────── */}
              <AnimatePresence mode="wait">
                <motion.div
                  key={activeTab}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.15 }}
                  className="mt-6"
                >

                  {/* ═══════════ TAB: OVERVIEW ═══════════════════════════════ */}
                  {activeTab === "overview" && (
                    <div className="space-y-6">

                      {/* Hero Metric */}
                      <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        className="relative overflow-hidden rounded-2xl p-8"
                        style={{
                          background: "linear-gradient(135deg, var(--glass-bg), var(--accent-muted))",
                          border: "1px solid var(--accent-glow)",
                          backdropFilter: "blur(24px) saturate(1.5)",
                          boxShadow: "0 8px 32px var(--overlay-bg), inset 0 1px 0 rgba(255,255,255,0.05)",
                        }}
                      >
                        {/* Corner glow */}
                        <div className="absolute -top-16 -left-16 w-48 h-48 rounded-full pointer-events-none" style={{ background: "radial-gradient(circle, var(--accent-muted) 0%, transparent 70%)" }} />
                        <div className="flex flex-col sm:flex-row sm:items-center gap-6">
                          {/* Main score */}
                          <div className="flex-shrink-0">
                            <div className="font-semibold text-sm uppercase tracking-wide mb-2" style={{ color: "var(--text-muted)" }}>
                              СРЕДНИЙ БАЛЛ КОМАНДЫ
                            </div>
                            <div
                              className="font-display font-black tabular-nums"
                              style={{
                                fontSize: "clamp(3.5rem, 7vw, 5rem)",
                                color: scoreColor(data.stats.avg_score),
                                lineHeight: 1.1,
                                minHeight: "1.1em",
                                textShadow: `0 0 40px color-mix(in srgb, ${scoreColor(data.stats.avg_score)} 25%, transparent)`,
                              }}
                            >
                              {data.stats.avg_score !== null ? (
                                <AnimatedCounter value={Math.round(data.stats.avg_score)} />
                              ) : "—"}
                            </div>
                            {data.stats.best_performer && (
                              <div className="flex items-center gap-1.5 mt-2">
                                <Crown size={16} weight="duotone" style={{ color: "var(--gf-xp)" }} />
                                <span className="text-sm" style={{ color: "var(--text-secondary)" }}>
                                  Лучший: <span className="font-medium" style={{ color: "var(--text-primary)" }}>{data.stats.best_performer}</span>
                                </span>
                              </div>
                            )}
                          </div>

                          {/* Secondary stats */}
                          <div className="flex-1 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3 sm:gap-4">
                            {[
                              { label: "Охотников", value: data.team.total_members, icon: UsersThree, color: "var(--accent)" },
                              { label: "Всего сессий", value: data.stats.total_sessions, icon: Target, color: "var(--success)" },
                              { label: "Активных", value: data.stats.active_this_week, icon: Clock, color: "var(--magenta)" },
                              { label: "В команде", value: data.team.active_members, icon: TrendUp, color: "var(--warning)" },
                            ].map((stat) => {
                              const SIcon = stat.icon;
                              return (
                                <div
                                  key={stat.label}
                                  className="rounded-xl px-4 py-4 relative overflow-hidden"
                                  style={{ background: "var(--input-bg)", border: `1px solid color-mix(in srgb, ${stat.color} 8%, transparent)` }}
                                >
                                  <div className="absolute -top-4 -right-4 w-16 h-16 rounded-full pointer-events-none" style={{ background: `radial-gradient(circle, color-mix(in srgb, ${stat.color} 6%, transparent) 0%, transparent 70%)` }} />
                                  <div className="flex items-center gap-2 mb-2">
                                    <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: `color-mix(in srgb, ${stat.color} 8%, transparent)` }}>
                                      <SIcon size={16} weight="duotone" style={{ color: stat.color }} />
                                    </div>
                                    <span className="font-semibold text-xs uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
                                      {stat.label}
                                    </span>
                                  </div>
                                  <div className="font-display text-2xl font-bold" style={{ color: "var(--text-primary)" }}>
                                    <AnimatedCounter value={stat.value} />
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      </motion.div>

                      {/* Alerts — compact */}
                      <AlertPanel compact />

                      {/* Activity Feed */}
                      <ActivityFeed items={activityItems} loading={loading} />

                      {/* Managers Table */}
                      <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        transition={{ delay: 0.1 }}
                        className="cyber-card overflow-hidden"
                      >
                        <div className="p-5 border-b flex items-center gap-2" style={{ borderColor: "var(--border-color)", background: "var(--input-bg)" }}>
                          <UsersThree size={18} weight="duotone" style={{ color: "var(--accent)" }} />
                          <h2 className="font-display text-base tracking-widest" style={{ color: "var(--text-secondary)" }}>
                            ОХОТНИКИ
                          </h2>
                          <span className="ml-auto font-mono text-xs" style={{ color: "var(--text-muted)" }}>
                            {data.team.active_members}/{data.team.total_members} активных
                          </span>
                        </div>

                        <div className="relative overflow-x-auto">
                          <div className="pointer-events-none absolute right-0 top-0 bottom-0 w-8 z-10 md:hidden" style={{ background: "linear-gradient(to left, var(--surface-card), transparent)" }} />
                          <table className="w-full text-sm min-w-[600px]">
                            <thead>
                              <tr style={{ borderBottom: "1px solid var(--border-color)" }}>
                                <SortHeader label="Имя" sortField="full_name" />
                                <th className="px-5 py-4 text-left font-semibold text-xs uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
                                  Роль
                                </th>
                                <SortHeader label="Сессий" sortField="total_sessions" />
                                <SortHeader label="Ср. балл" sortField="avg_score" />
                                <SortHeader label="Лучший" sortField="best_score" />
                                <SortHeader label="Неделя" sortField="sessions_this_week" />
                                <th className="px-5 py-4" style={{ width: 48 }} />
                              </tr>
                            </thead>
                            <tbody>
                              {sortedMembers.map((m, i) => {
                                const avatarColor = getAvatarColor(m.id);
                                return (
                                  <motion.tr
                                    key={m.id}
                                    initial={{ opacity: 0 }}
                                    animate={{ opacity: 1 }}
                                    transition={{ duration: 0.2 }}
                                    className="transition-all group table-row-accent"
                                    style={{ borderBottom: "1px solid var(--border-color)" }}
                                  >
                                    <td className="px-5 py-4">
                                      <div className="flex items-center gap-3">
                                        {/* Avatar */}
                                        <div
                                          className="w-11 h-11 rounded-xl flex items-center justify-center text-sm font-bold text-white shrink-0 transition-all duration-200 group-hover:scale-110 group-hover:shadow-lg"
                                          style={{ background: `linear-gradient(135deg, ${avatarColor}, ${avatarColor}CC)`, boxShadow: `0 2px 8px ${avatarColor}30` }}
                                        >
                                          {getInitials(m.full_name)}
                                        </div>
                                        <div>
                                          <div className="flex items-center gap-1.5">
                                            {!m.is_active && (
                                              <span className="w-1.5 h-1.5 rounded-full bg-red-500 shrink-0" title="Неактивен" />
                                            )}
                                            <span style={{ color: "var(--text-primary)" }}>{m.full_name}</span>
                                          </div>
                                          <div className="text-sm" style={{ color: "var(--text-muted)" }}>{m.email}</div>
                                        </div>
                                      </div>
                                    </td>
                                    <td className="px-5 py-4">
                                      <span
                                        className="rounded-full px-3 py-1 text-sm font-medium"
                                        style={{ background: "var(--accent-muted)", color: "var(--accent)" }}
                                      >
                                        {m.role}
                                      </span>
                                    </td>
                                    <td className="px-5 py-4 font-mono" style={{ color: "var(--text-primary)" }}>
                                      {m.total_sessions}
                                    </td>
                                    <td className="px-5 py-4">
                                      <ScoreBadge score={m.avg_score} size="sm" />
                                    </td>
                                    <td className="px-5 py-4">
                                      <ScoreBadge score={m.best_score} size="sm" />
                                    </td>
                                    <td className="px-5 py-4 font-mono" style={{ color: "var(--text-secondary)" }}>
                                      {m.sessions_this_week}
                                    </td>
                                    <td className="px-5 py-4">
                                      <motion.button
                                        onClick={() => router.push(`/profile?user=${m.id}`)}
                                        className="flex items-center gap-1 text-xs opacity-0 group-hover:opacity-100 transition-opacity"
                                        style={{ color: "var(--accent)" }}
                                        whileHover={{ x: 3 }}
                                      >
                                        <ArrowRight size={14} />
                                      </motion.button>
                                    </td>
                                  </motion.tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      </motion.div>
                    </div>
                  )}

                  {/* ═══════════ TAB: ANALYTICS ══════════════════════════════ */}
                  {activeTab === "analytics" && (
                    <div className="space-y-8">
                      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        <TeamTrendChart />
                        <ActivityChart />
                      </div>

                      <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        className="rounded-2xl p-5"
                        style={{ background: "var(--glass-bg)", border: "1px solid var(--glass-border)", backdropFilter: "blur(20px)" }}
                      >
                        <TeamHeatmap />
                      </motion.div>

                      <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        transition={{ delay: 0.1 }}
                        className="rounded-2xl p-5"
                        style={{ background: "var(--glass-bg)", border: "1px solid var(--glass-border)", backdropFilter: "blur(20px)" }}
                      >
                        <Benchmark />
                      </motion.div>

                      <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        transition={{ delay: 0.2 }}
                        className="rounded-2xl p-5"
                        style={{ background: "var(--glass-bg)", border: "1px solid var(--glass-border)", backdropFilter: "blur(20px)" }}
                      >
                        <WeeklyReport />
                      </motion.div>
                    </div>
                  )}

                  {/* ═══════════ TAB: TEAM ════════════════════════════════════ */}
                  {activeTab === "team" && (
                    <div className="space-y-5">
                      <AlertPanel />

                      <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        className="rounded-2xl p-5"
                        style={{ background: "var(--glass-bg)", border: "1px solid var(--glass-border)", backdropFilter: "blur(20px)" }}
                      >
                        <WeakLinks />
                      </motion.div>

                      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        <BehaviorProfileCard />
                        <OceanProfileWidget />
                      </div>

                      <TrainingRecommendations />
                    </div>
                  )}

                  {/* ═══════════ TAB: TOURNAMENT ══════════════════════════════ */}
                  {activeTab === "tournament" && (
                    <div className="space-y-6">
                      {/* Tournament Block */}
                      <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        className="cyber-card overflow-hidden"
                      >
                        <div className="p-5 border-b flex items-center gap-2" style={{ borderColor: "var(--border-color)", background: "var(--input-bg)" }}>
                          <Trophy size={18} weight="duotone" style={{ color: "var(--gf-xp)" }} />
                          <h2 className="font-display text-base tracking-widest" style={{ color: "var(--text-secondary)" }}>
                            ТУРНИР
                          </h2>
                        </div>

                        {data.tournament ? (
                          <div className="p-5">
                            <div className="mb-4">
                              <h3 className="text-base font-medium" style={{ color: "var(--text-primary)" }}>
                                {data.tournament.title}
                              </h3>
                              <p className="font-mono text-xs mt-1" style={{ color: "var(--text-muted)" }}>
                                До {new Date(data.tournament.week_end).toLocaleDateString("ru-RU", { day: "numeric", month: "short" })}
                              </p>
                            </div>

                            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2 sm:gap-3">
                              {data.tournament.leaderboard.map((entry, i) => (
                                <motion.div
                                  key={entry.user_id}
                                  initial={{ opacity: 0 }}
                                  animate={{ opacity: 1 }}
                                  transition={{ delay: i * 0.05 }}
                                  className="flex items-center gap-3 rounded-lg px-4 py-3"
                                  style={{
                                    background: i < 3 ? `color-mix(in srgb, ${podiumColors[i]} 3%, transparent)` : "var(--input-bg)",
                                    borderLeft: i < 3 ? `3px solid ${podiumColors[i]}` : "3px solid transparent",
                                  }}
                                >
                                  <span
                                    className="w-6 text-center font-mono text-sm font-bold"
                                    style={{ color: i < 3 ? podiumColors[i] : "var(--text-muted)" }}
                                  >
                                    {entry.rank}
                                  </span>
                                  <div className="flex-1 min-w-0">
                                    <span className="text-sm truncate block" style={{ color: "var(--text-primary)" }}>
                                      {entry.full_name}
                                    </span>
                                  </div>
                                  <span className="font-mono text-sm font-bold" style={{ color: scoreColor(entry.best_score) }}>
                                    {Math.round(entry.best_score)}
                                  </span>
                                </motion.div>
                              ))}
                            </div>

                            {data.tournament.leaderboard.length === 0 && (
                              <div className="py-8 flex items-center justify-center">
                                <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                                  Пока нет участников
                                </p>
                              </div>
                            )}
                          </div>
                        ) : (
                          <div className="p-8 flex flex-col items-center justify-center text-center">
                            <Trophy size={40} weight="duotone" style={{ color: "var(--border-color)" }} />
                            <p className="mt-3 text-sm" style={{ color: "var(--text-muted)" }}>
                              Нет активных турниров
                            </p>
                          </div>
                        )}
                      </motion.div>

                      {/* Knowledge + Pipeline */}
                      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        <KnowledgeDashboardWidget />

                        {pipelineStats.length > 0 && (
                          <motion.div
                            initial={{ opacity: 0, y: 12 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: 0.1 }}
                          >
                            <div className="flex items-center justify-between mb-3">
                              <h2 className="font-display text-sm tracking-widest flex items-center gap-2" style={{ color: "var(--text-secondary)" }}>
                                <UsersThree size={16} weight="duotone" style={{ color: "var(--accent)" }} />
                                ВОРОНКА КЛИЕНТОВ
                              </h2>
                              <Link href="/clients/pipeline" className="font-medium text-xs flex items-center gap-1" style={{ color: "var(--accent)" }}>
                                Открыть <ArrowRight size={10} />
                              </Link>
                            </div>
                            <ClientStats stats={pipelineStats} />
                          </motion.div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* ═══════════ TAB: WIKI ══════════════════════════════════ */}
                  {activeTab === "wiki" && (
                    <div>
                      <WikiDashboard />
                    </div>
                  )}

                  {/* ═══════════ TAB: REPORTS ═══════════════════════════════ */}
                  {activeTab === "reports" && (
                    <div>
                      <ReportsDashboard
                        teamMode
                        teamMembers={(data?.members ?? []).map((m) => ({
                          id: m.id,
                          name: m.full_name || m.email,
                        }))}
                      />
                    </div>
                  )}

                  {/* ═══════════ TAB: REVIEWS (admin only) ═════════════════ */}
                  {activeTab === "reviews" && user?.role === "admin" && (
                    <div>
                      <ReviewsAdmin />
                    </div>
                  )}

                </motion.div>
              </AnimatePresence>
            </>
          ) : null}
        </div>
      </div>
    </AuthLayout>
  );
}
