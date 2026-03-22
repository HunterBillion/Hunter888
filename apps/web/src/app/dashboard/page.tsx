"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  LayoutDashboard,
  Users,
  Loader2,
  TrendingUp,
  Clock,
  Target,
  Trophy,
  ArrowRight,
  ShieldAlert,
  Crown,
  Medal,
  Flame,
} from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import AuthLayout from "@/components/layout/AuthLayout";
import { ClientStats } from "@/components/clients/ClientStats";
import { TrainingRecommendations } from "@/components/clients/TrainingRecommendations";
import type { DashboardROP, TeamMember, DashboardTournament, PipelineStats } from "@/types";

function scoreColor(score: number | null) {
  if (score === null) return "var(--text-muted)";
  if (score >= 70) return "#00FF66";
  if (score >= 40) return "var(--warning)";
  return "#FF3333";
}

const podiumColors = ["#FFD700", "#C0C0C0", "#CD7F32"]; // gold, silver, bronze

export default function DashboardPage() {
  const router = useRouter();
  const { user } = useAuth();
  const [data, setData] = useState<DashboardROP | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pipelineStats, setPipelineStats] = useState<PipelineStats[]>([]);

  useEffect(() => {
    if (!user) return;

    const allowed = user.role === "rop" || user.role === "admin";
    if (!allowed) {
      setError("Доступ ограничен");
      setLoading(false);
      return;
    }

    api
      .get("/dashboard/rop")
      .then((resp: DashboardROP) => setData(resp))
      .catch((err) => setError(err.message || "Ошибка загрузки"))
      .finally(() => setLoading(false));

    api.get("/clients/stats")
      .then((stats: PipelineStats[]) => setPipelineStats(stats))
      .catch(() => {});
  }, [user]);

  return (
    <AuthLayout>
      <div className="relative panel-grid-bg min-h-screen">
        <div className="mx-auto max-w-6xl px-4 py-8">
          {/* Header */}
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
            <div className="flex items-center gap-2">
              <LayoutDashboard size={20} style={{ color: "var(--accent)" }} />
              <h1
                className="font-display text-2xl font-bold tracking-wider"
                style={{ color: "var(--text-primary)" }}
              >
                ПАНЕЛЬ РОП
              </h1>
            </div>
            <p className="mt-2 font-mono text-xs tracking-wider" style={{ color: "var(--text-muted)" }}>
              {data?.team.name ? `КОМАНДА: ${data.team.name.toUpperCase()}` : "АНАЛИТИКА КОМАНДЫ"}
            </p>
          </motion.div>

          {loading ? (
            <div className="mt-16 flex flex-col items-center">
              <Loader2 size={24} className="animate-spin" style={{ color: "var(--accent)" }} />
              <span className="mt-3 font-mono text-xs" style={{ color: "var(--text-muted)" }}>ЗАГРУЗКА...</span>
            </div>
          ) : error ? (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="mt-16 flex flex-col items-center"
            >
              <ShieldAlert size={40} style={{ color: "var(--danger)" }} />
              <p className="mt-3 text-sm" style={{ color: "var(--danger)" }}>{error}</p>
            </motion.div>
          ) : data ? (
            <>
              {/* Summary cards */}
              <div className="mt-8 grid grid-cols-2 md:grid-cols-4 gap-4">
                {[
                  { label: "Менеджеров", value: data.team.total_members, icon: Users, color: "var(--accent)" },
                  { label: "Всего сессий", value: data.stats.total_sessions, icon: Target, color: "#00FF66" },
                  { label: "Средний балл", value: data.stats.avg_score !== null ? Math.round(data.stats.avg_score) : "—", icon: TrendingUp, color: "var(--warning)" },
                  { label: "Активны на неделе", value: data.stats.active_this_week, icon: Clock, color: "#E028CC" },
                ].map((card, i) => {
                  const Icon = card.icon;
                  return (
                    <motion.div
                      key={card.label}
                      initial={{ opacity: 0, y: 12 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: 0.1 + i * 0.05 }}
                      className="glass-panel p-5"
                    >
                      <Icon size={18} style={{ color: card.color }} />
                      <div className="mt-3 font-display text-2xl font-bold" style={{ color: "var(--text-primary)" }}>
                        {card.value}
                      </div>
                      <div className="mt-1 font-mono text-[10px] uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
                        {card.label}
                      </div>
                    </motion.div>
                  );
                })}
              </div>

              {/* Best performer highlight */}
              {data.stats.best_performer && (
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.35 }}
                  className="mt-4 glass-panel p-4 flex items-center gap-3"
                  style={{ borderLeft: "3px solid #FFD700" }}
                >
                  <Crown size={18} style={{ color: "#FFD700" }} />
                  <div>
                    <span className="font-mono text-[10px] uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
                      Лучший результат
                    </span>
                    <p className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                      {data.stats.best_performer}
                    </p>
                  </div>
                </motion.div>
              )}

              {/* Pipeline widget */}
              {pipelineStats.length > 0 && (
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.4 }}
                  className="mt-6"
                >
                  <div className="flex items-center justify-between mb-3">
                    <h2 className="font-display text-sm tracking-widest flex items-center gap-2" style={{ color: "var(--text-secondary)" }}>
                      <Users size={16} style={{ color: "var(--accent)" }} />
                      ВОРОНКА КЛИЕНТОВ
                    </h2>
                    <Link href="/clients/pipeline" className="font-mono text-[10px] flex items-center gap-1" style={{ color: "var(--accent)" }}>
                      Открыть <ArrowRight size={10} />
                    </Link>
                  </div>
                  <ClientStats stats={pipelineStats} />
                </motion.div>
              )}

              {/* F6.1: Training recommendations for ROP */}
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.45 }}
                className="mt-6"
              >
                <TrainingRecommendations />
              </motion.div>

              <div className="mt-6 grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Managers table — spans 2 cols on lg */}
                <motion.div
                  initial={{ opacity: 0, y: 16 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.3 }}
                  className="glass-panel overflow-hidden lg:col-span-2"
                >
                  <div className="p-4 border-b flex items-center gap-2" style={{ borderColor: "var(--border-color)", background: "rgba(0,0,0,0.2)" }}>
                    <Users size={16} style={{ color: "var(--accent)" }} />
                    <h2 className="font-display text-sm tracking-widest" style={{ color: "var(--text-secondary)" }}>
                      МЕНЕДЖЕРЫ
                    </h2>
                    <span className="ml-auto font-mono text-[10px]" style={{ color: "var(--text-muted)" }}>
                      {data.team.active_members}/{data.team.total_members} активных
                    </span>
                  </div>

                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr style={{ borderBottom: "1px solid var(--border-color)" }}>
                          {["Имя", "Роль", "Сессий", "Ср. балл", "Лучший", "На неделе", ""].map((h) => (
                            <th
                              key={h}
                              className="px-4 py-3 text-left font-mono text-[10px] uppercase tracking-widest"
                              style={{ color: "var(--text-muted)" }}
                            >
                              {h}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {data.members.map((m, i) => (
                          <motion.tr
                            key={m.id}
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            transition={{ delay: 0.35 + i * 0.03 }}
                            className="transition-colors hover:brightness-125"
                            style={{ borderBottom: "1px solid var(--border-color)" }}
                          >
                            <td className="px-4 py-3">
                              <div className="flex items-center gap-2">
                                {!m.is_active && (
                                  <span className="w-1.5 h-1.5 rounded-full bg-red-500 shrink-0" title="Неактивен" />
                                )}
                                <div>
                                  <div style={{ color: "var(--text-primary)" }}>{m.full_name}</div>
                                  <div className="text-xs" style={{ color: "var(--text-muted)" }}>{m.email}</div>
                                </div>
                              </div>
                            </td>
                            <td className="px-4 py-3">
                              <span
                                className="rounded-full px-2 py-0.5 text-xs font-mono"
                                style={{ background: "var(--accent-muted)", color: "var(--accent)" }}
                              >
                                {m.role}
                              </span>
                            </td>
                            <td className="px-4 py-3 font-mono" style={{ color: "var(--text-primary)" }}>
                              {m.total_sessions}
                            </td>
                            <td className="px-4 py-3 font-mono font-bold" style={{ color: scoreColor(m.avg_score) }}>
                              {m.avg_score !== null ? Math.round(m.avg_score) : "—"}
                            </td>
                            <td className="px-4 py-3 font-mono font-bold" style={{ color: scoreColor(m.best_score) }}>
                              {m.best_score !== null ? Math.round(m.best_score) : "—"}
                            </td>
                            <td className="px-4 py-3 font-mono" style={{ color: "var(--text-secondary)" }}>
                              {m.sessions_this_week}
                            </td>
                            <td className="px-4 py-3">
                              <motion.button
                                onClick={() => router.push(`/profile?user=${m.id}`)}
                                className="flex items-center gap-1 text-xs"
                                style={{ color: "var(--accent)" }}
                                whileHover={{ x: 3 }}
                              >
                                <ArrowRight size={14} />
                              </motion.button>
                            </td>
                          </motion.tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </motion.div>

                {/* Tournament sidebar */}
                <motion.div
                  initial={{ opacity: 0, y: 16 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.4 }}
                  className="glass-panel overflow-hidden flex flex-col"
                >
                  <div className="p-4 border-b flex items-center gap-2" style={{ borderColor: "var(--border-color)", background: "rgba(0,0,0,0.2)" }}>
                    <Trophy size={16} style={{ color: "#FFD700" }} />
                    <h2 className="font-display text-sm tracking-widest" style={{ color: "var(--text-secondary)" }}>
                      ТУРНИР
                    </h2>
                  </div>

                  {data.tournament ? (
                    <div className="p-4 flex-1 flex flex-col">
                      <div className="mb-3">
                        <h3 className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                          {data.tournament.title}
                        </h3>
                        <p className="font-mono text-[10px] mt-1" style={{ color: "var(--text-muted)" }}>
                          До {new Date(data.tournament.week_end).toLocaleDateString("ru-RU", { day: "numeric", month: "short" })}
                        </p>
                      </div>

                      <div className="space-y-2 flex-1">
                        {data.tournament.leaderboard.map((entry, i) => (
                          <motion.div
                            key={entry.user_id}
                            initial={{ opacity: 0, x: 8 }}
                            animate={{ opacity: 1, x: 0 }}
                            transition={{ delay: 0.5 + i * 0.05 }}
                            className="flex items-center gap-3 rounded-lg px-3 py-2"
                            style={{
                              background: i < 3 ? `${podiumColors[i]}08` : "transparent",
                              borderLeft: i < 3 ? `2px solid ${podiumColors[i]}` : "2px solid transparent",
                            }}
                          >
                            <span
                              className="w-5 text-center font-mono text-xs font-bold"
                              style={{ color: i < 3 ? podiumColors[i] : "var(--text-muted)" }}
                            >
                              {entry.rank}
                            </span>
                            <div className="flex-1 min-w-0">
                              <span className="text-xs truncate block" style={{ color: "var(--text-primary)" }}>
                                {entry.full_name}
                              </span>
                            </div>
                            <span className="font-mono text-xs font-bold" style={{ color: scoreColor(entry.best_score) }}>
                              {Math.round(entry.best_score)}
                            </span>
                          </motion.div>
                        ))}
                      </div>

                      {data.tournament.leaderboard.length === 0 && (
                        <div className="flex-1 flex items-center justify-center">
                          <p className="font-mono text-xs" style={{ color: "var(--text-muted)" }}>
                            Пока нет участников
                          </p>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="p-6 flex-1 flex flex-col items-center justify-center text-center">
                      <Trophy size={32} style={{ color: "var(--border-color)" }} />
                      <p className="mt-3 text-xs" style={{ color: "var(--text-muted)" }}>
                        Нет активных турниров
                      </p>
                    </div>
                  )}
                </motion.div>
              </div>
            </>
          ) : null}
        </div>
      </div>
    </AuthLayout>
  );
}
