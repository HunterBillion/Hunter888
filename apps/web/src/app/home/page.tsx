"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { motion } from "framer-motion";
import {
  Zap, TrendingUp, Target, Clock, ArrowRight, Crosshair,
  Users, BarChart3, Loader2, X, Flame, RotateCcw,
  Swords, Crown, Medal, ClipboardList,
} from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import AuthLayout from "@/components/layout/AuthLayout";
import { NavigatorBlock } from "@/components/ui/NavigatorBlock";
import { ReminderWidget } from "@/components/clients/ReminderWidget";
import { TrainingRecommendations } from "@/components/clients/TrainingRecommendations";
import { useTrainingStore } from "@/stores/useTrainingStore";
import type { DashboardManager } from "@/types";
import { scoreColor } from "@/lib/utils";
import { Sparkline } from "@/components/ui/Sparkline";
import { AnimatedCounter } from "@/components/ui/AnimatedCounter";
import { LoadingTip } from "@/components/ui/Skeleton";
import { useNotificationStore } from "@/stores/useNotificationStore";
import { logger } from "@/lib/logger";
import { EASE_SNAP, TIMING, STORAGE, RANK, STREAK } from "@/lib/constants";
// useTiltEffect kept in hooks/ for future use on non-motion elements


function getGreeting(): string {
  const h = new Date().getHours();
  if (h >= 5 && h < 8) return "Раннее утро — лучшее время";
  if (h >= 8 && h < 12) return "Доброе утро";
  if (h >= 12 && h < 14) return "Добрый день";
  if (h >= 14 && h < 17) return "Продуктивного дня";
  if (h >= 17 && h < 19) return "Добрый вечер";
  if (h >= 19 && h < 22) return "Вечерняя тренировка";
  if (h >= 22 && h < 24) return "Поздний сет";
  return "Ночная смена";
}

// F3: Daily challenges — expanded pool in /lib/daily-challenges.ts

export default function HomePage() {
  const router = useRouter();
  const { user } = useAuth();
  const [dashboard, setDashboard] = useState<DashboardManager | null>(null);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [dailyChallenge, setDailyChallenge] = useState<{ title: string; desc: string; rewardXp: number } | null>(null);
  const [dailyGoals, setDailyGoals] = useState<Array<{ id: string; title: string; xp: number; progress: number; target: number }>>([]);


  const fetchDashboard = () => {
    if (!user) return;
    api
      .get("/dashboard/manager")
      .then((data: DashboardManager) => setDashboard(data))
      .catch((err) => { logger.error("Failed to load dashboard:", err); })
      .finally(() => setLoading(false));
    // Fetch daily challenge + goals (non-blocking, safe parsing)
    api.get("/gamification/daily-challenge")
      .then((data: unknown) => {
        if (data && typeof data === "object" && "title" in data && "desc" in data) {
          setDailyChallenge(data as { title: string; desc: string; rewardXp: number });
        }
      })
      .catch(() => { /* optional */ });
    api.get("/gamification/goals")
      .then((data: unknown) => {
        if (data && typeof data === "object" && "goals" in data && Array.isArray((data as Record<string, unknown>).goals)) {
          setDailyGoals((data as { goals: Array<{ id: string; title: string; xp: number; progress: number; target: number }> }).goals);
        }
      })
      .catch(() => { /* optional */ });
  };

  useEffect(() => {
    fetchDashboard();
  }, [user]);

  // Refetch gamification & stats when user returns to the tab
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible") {
        fetchDashboard();
      }
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [user]);


  const recommendations = dashboard?.recommendations ?? [];
  const recentSessions = dashboard?.recent_sessions ?? [];
  const lastSession = recentSessions[0] ?? null;

  const quickStart = async () => {
    if (starting) return;
    setStarting(true);
    try {
      let scenarioId: string;
      if (recommendations.length > 0) {
        const rec = recommendations[Math.floor(Math.random() * recommendations.length)];
        scenarioId = rec.scenario_id;
      } else {
        // Fallback: fetch scenarios directly and pick a random one
        const scenariosData = await api.get("/scenarios/");
        const scenarios: { id: string }[] = Array.isArray(scenariosData) ? scenariosData : [];
        if (!scenarios.length) { setStarting(false); return; }
        scenarioId = scenarios[Math.floor(Math.random() * scenarios.length)].id;
      }
      const session = await api.post("/training/sessions", { scenario_id: scenarioId });
      if (!session?.id) throw new Error("Invalid session response");
      router.push(`/training/${session.id}`);
      // Reset after navigation so the button works if user navigates back
      setTimeout(() => setStarting(false), 1000);
    } catch (err) {
      useNotificationStore.getState().addToast({
        title: "Ошибка запуска",
        body: "Не удалось начать тренировку. Попробуйте ещё раз.",
        type: "error",
      });
      logger.error("Quick start failed:", err);
      setStarting(false);
    }
  };

  const streakDays = dashboard?.gamification.streak_days ?? 0;
  const level = dashboard?.gamification.level ?? 1;
  const xpCurrent = dashboard?.gamification.xp_current_level ?? 0;
  const xpNext = dashboard?.gamification.xp_next_level ?? 100;
  const xpPct = xpNext > 0 ? Math.round((xpCurrent / xpNext) * 100) : 0;
  const firstName = user?.full_name?.split(" ")[0] || "Охотник";
  const stats = dashboard?.stats ?? null;

  return (
    <AuthLayout>
      <div className="relative panel-grid-bg min-h-screen">

        <div className="app-page">

          {/* ── COMMAND CENTER HERO ───────────────────────────────────────── */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0, duration: 0.6, ease: EASE_SNAP }}
            className="relative rounded-2xl overflow-hidden p-6 sm:p-8 mb-6"
            style={{
              background: "linear-gradient(135deg, rgba(99,102,241,0.10) 0%, rgba(99,102,241,0.04) 50%, transparent 100%)",
              border: "1px solid rgba(99,102,241,0.18)",
            }}
          >
            {/* Accent corner glow */}
            <div
              className="absolute -top-16 -left-16 w-48 sm:w-64 h-48 sm:h-64 rounded-full pointer-events-none"
              style={{ background: "radial-gradient(circle, rgba(99,102,241,0.14) 0%, transparent 70%)" }}
            />

            <div className="relative z-10 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-6">
              {/* Left: identity + level */}
              <div className="flex items-center gap-5">
                {/* Level ring */}
                <div className="relative shrink-0" style={{ width: 88, height: 88 }}>
                  <svg width="88" height="88" viewBox="0 0 88 88" className="rotate-[-90deg]">
                    {/* Background track */}
                    <circle cx="44" cy="44" r="38" fill="none" stroke="rgba(99,102,241,0.12)" strokeWidth="5" />
                    {/* Glow track (soft underlayer) */}
                    <circle
                      cx="44" cy="44" r="38" fill="none"
                      stroke="var(--accent-glow)"
                      strokeWidth="8"
                      strokeLinecap="round"
                      strokeDasharray={`${2 * Math.PI * 38}`}
                      strokeDashoffset={`${2 * Math.PI * 38 * (1 - xpPct / 100)}`}
                      style={{ filter: "blur(4px)", opacity: 0.5, transition: "stroke-dashoffset 1s ease" }}
                    />
                    {/* Main progress arc */}
                    <circle
                      cx="44" cy="44" r="38" fill="none"
                      stroke="var(--accent)"
                      strokeWidth="5"
                      strokeLinecap="round"
                      strokeDasharray={`${2 * Math.PI * 38}`}
                      strokeDashoffset={`${2 * Math.PI * 38 * (1 - xpPct / 100)}`}
                      style={{ filter: "drop-shadow(0 0 8px var(--accent-glow))", transition: "stroke-dashoffset 1s ease" }}
                    />
                  </svg>
                  <div className="absolute inset-0 flex items-center justify-center">
                    <span className="font-display font-black text-2xl" style={{ color: "var(--accent)" }}>
                      {level}
                    </span>
                  </div>
                </div>

                {/* Name + status */}
                <div className="min-w-0">
                  <div className="font-semibold text-sm uppercase tracking-wide mb-1.5" style={{ color: "var(--accent)", opacity: 0.8 }}>
                    {getGreeting()}
                  </div>
                  <h1
                    className="font-display font-black leading-none truncate"
                    style={{
                      fontSize: "clamp(1.6rem, 5vw, 2.6rem)",
                      color: "var(--text-primary)",
                    }}
                  >
                    <span style={{ color: "var(--accent)" }}>{firstName}</span>
                  </h1>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    {streakDays > 0 && (
                      <span
                        className="inline-flex items-center gap-1 font-mono text-xs px-2.5 py-1 rounded-full uppercase tracking-wider"
                        style={{ background: STREAK.rgba(0.1), border: `1px solid ${STREAK.rgba(0.25)}`, color: STREAK.light }}
                      >
                        <Flame size={10} /> {streakDays} дней
                      </span>
                    )}
                    <span
                      className="inline-flex items-center gap-1 font-mono text-xs px-2.5 py-1 rounded-full uppercase tracking-wider"
                      style={{ background: "var(--accent-muted)", border: "1px solid rgba(99,102,241,0.25)", color: "var(--accent)" }}
                    >
                      <Zap size={10} /> {xpCurrent} / {xpNext} XP
                    </span>
                  </div>
                </div>
              </div>

              {/* Right: Quick Start CTA */}
              <motion.button
                onClick={quickStart}
                disabled={starting}
                className="btn-neon flex items-center justify-center gap-3 font-display font-bold shrink-0"
                style={{ fontSize: "clamp(0.95rem, 2vw, 1.1rem)", padding: "clamp(0.85rem, 2vw, 1.1rem) clamp(1.5rem, 4vw, 2.5rem)" }}
                whileHover={{ scale: 1.04, boxShadow: "0 12px 40px rgba(79,70,229,0.55)" }}
                whileTap={{ scale: 0.97 }}
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.6, delay: 0, ease: EASE_SNAP }}
              >
                {starting
                  ? <Loader2 size={20} className="animate-spin" />
                  : <><Zap size={20} /><span>Быстрая охота</span><ArrowRight size={18} /></>
                }
              </motion.button>
            </div>

            {/* XP bar inside hero */}
            <motion.div
              className="relative z-10 mt-5"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.2 }}
            >
              <div className="xp-bar h-1.5 rounded-full" style={{ background: "rgba(99,102,241,0.1)" }}>
                <motion.div
                  className="xp-bar-fill h-full rounded-full"
                  initial={{ width: 0 }}
                  animate={{ width: `${xpPct}%` }}
                  transition={{ duration: 1.2, delay: 0.35, ease: EASE_SNAP }}
                />
              </div>
              {/* 2.6: "До уровня N" hint */}
              <div className="mt-1.5 flex justify-between">
                <span className="font-mono text-sm" style={{ color: "var(--text-muted)" }}>
                  {xpCurrent} / {xpNext} XP
                </span>
                <span className="font-mono text-sm" style={{ color: "var(--accent)" }}>
                  До уровня {level + 1}: {xpNext - xpCurrent} XP
                </span>
              </div>
            </motion.div>
          </motion.div>

          {/* Tournament Banner */}
          {!loading && dashboard?.tournament && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.12 }}
              className="mt-4 rounded-xl p-4 flex items-center gap-4 cursor-pointer transition-all"
              style={{ background: RANK.goldRgba(0.06), border: `1px solid ${RANK.goldRgba(0.15)}` }}
              whileHover={{ y: -1, boxShadow: `0 4px 20px ${RANK.goldRgba(0.1)}` }}
              onClick={() => router.push("/leaderboard")}
            >
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl" style={{ background: RANK.goldRgba(0.1) }}>
                <Swords size={18} style={{ color: RANK.gold }} />
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-xs uppercase tracking-wide" style={{ color: RANK.gold }}>ТУРНИР</span>
                  <span className="flex h-1.5 w-1.5 rounded-full animate-pulse" style={{ background: "var(--success)" }} />
                </div>
                <div className="text-sm font-medium mt-0.5" style={{ color: "var(--text-primary)" }}>
                  {dashboard.tournament.title}
                </div>
                {/* Mini podium */}
                {dashboard.tournament.leaderboard.length > 0 && (
                  <div className="flex items-center gap-2 mt-1">
                    {dashboard.tournament.leaderboard.slice(0, 3).map((e) => (
                      <span key={e.user_id} className="font-mono text-xs flex items-center gap-0.5" style={{ color: "var(--text-muted)" }}>
                        {e.rank === 1 ? <Crown size={9} style={{ color: RANK.gold }} /> : e.rank === 2 ? <Medal size={9} style={{ color: RANK.silver }} /> : <Medal size={9} style={{ color: RANK.bronze }} />}
                        {e.full_name.split(" ")[0]}
                      </span>
                    ))}
                  </div>
                )}
              </div>
              <ArrowRight size={16} style={{ color: RANK.gold }} />
            </motion.div>
          )}

          {/* P3-25: Continue last session shortcut */}
          {lastSession && lastSession.status === "completed" && lastSession.score_total !== null && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.15 }}
              className="mt-4 glass-panel p-4 flex items-center gap-4 cursor-pointer transition-all"
              whileHover={{ y: -1, boxShadow: "0 4px 20px var(--accent-glow)" }}
              onClick={() => router.push(`/results/${lastSession.id}`)}
            >
              <div className="flex h-10 w-10 items-center justify-center rounded-xl" style={{ background: "var(--accent-muted)" }}>
                <RotateCcw size={18} style={{ color: "var(--accent)" }} />
              </div>
              <div className="flex-1">
                <div className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>Последняя сессия</div>
                <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
                  Результат: {Math.round(lastSession.score_total)}/100
                </div>
              </div>
              <ArrowRight size={16} style={{ color: "var(--text-muted)" }} />
            </motion.div>
          )}

          {/* Assigned trainings badge */}
          <AssignedBadge />

          {/* НАВИГАТОР — 6-hour rotating quote */}
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="mt-5"
          >
            <NavigatorBlock />
          </motion.div>

          {/* Keyboard shortcut discovery — first 3 visits */}
          <ShortcutHint />

          {/* Stats Grid */}
          {!loading && (
            <div className="mt-2 grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
              {[
                { label: "Сессий", value: stats?.completed_sessions ?? 0, icon: Target, color: "var(--accent)", suffix: "", sparkData: [1, 2, 1, 3, 2, 4, stats?.completed_sessions ?? 0] },
                { label: "Ср. балл", value: stats?.avg_score != null ? Math.round(stats.avg_score) : 0, icon: TrendingUp, color: scoreColor(stats?.avg_score ?? null), suffix: "", sparkData: [60, 65, 55, 70, 68, 75, Math.round(stats?.avg_score ?? 0)] },
                { label: "Лучший", value: stats?.best_score != null ? Math.round(stats.best_score) : 0, icon: BarChart3, color: scoreColor(stats?.best_score ?? null), suffix: "", sparkData: [50, 60, 65, 70, 75, 80, Math.round(stats?.best_score ?? 0)] },
                { label: "За неделю", value: stats?.sessions_this_week ?? 0, icon: Clock, color: STREAK.light, suffix: "", sparkData: [0, 1, 0, 2, 1, 1, stats?.sessions_this_week ?? 0] },
              ].map((card, i) => (
                <StatCard key={card.label} card={card} i={i} />
              ))}
            </div>
          )}

          {/* Daily Challenge + Goals */}
          {!loading && (
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3 }}
              className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-4"
            >
              {/* Daily Challenge */}
              {dailyChallenge && (
                <div className="glass-panel rounded-2xl p-5 flex flex-col gap-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Zap size={16} style={{ color: "#FFB400" }} />
                      <span className="font-display font-semibold text-sm" style={{ color: "var(--text-primary)" }}>
                        Вызов дня
                      </span>
                    </div>
                    <span className="font-mono text-sm" style={{ color: "#FFB400" }}>+{dailyChallenge.rewardXp} XP</span>
                  </div>
                  <div>
                    <p className="font-semibold text-sm" style={{ color: "var(--text-primary)" }}>{dailyChallenge.title}</p>
                    <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>{dailyChallenge.desc}</p>
                  </div>
                  <Link href="/training">
                    <span className="btn-neon text-xs inline-flex items-center gap-1.5">
                      <Crosshair size={13} /> Начать
                    </span>
                  </Link>
                </div>
              )}
              {/* Daily Goals */}
              {dailyGoals.length > 0 && (
                <div className="glass-panel rounded-2xl p-5 flex flex-col gap-3">
                  <div className="flex items-center gap-2">
                    <Target size={16} style={{ color: "var(--accent)" }} />
                    <span className="font-display font-semibold text-sm" style={{ color: "var(--text-primary)" }}>
                      Цели на сегодня
                    </span>
                  </div>
                  <div className="space-y-2.5">
                    {dailyGoals.slice(0, 3).map((goal: { id: string; title: string; xp: number; progress: number; target: number }) => (
                      <div key={goal.id}>
                        <div className="flex justify-between text-sm mb-1">
                          <span style={{ color: goal.progress >= goal.target ? "#00FF66" : "var(--text-secondary)" }}>
                            {goal.progress >= goal.target ? "✓ " : ""}{goal.title}
                          </span>
                          <span className="font-mono" style={{ color: "var(--text-muted)" }}>
                            {goal.progress}/{goal.target}
                          </span>
                        </div>
                        <div className="h-1.5 rounded-full overflow-hidden" style={{ background: "var(--input-bg)" }}>
                          <div
                            className="h-full rounded-full transition-all duration-500"
                            style={{
                              width: `${Math.min(100, (goal.progress / goal.target) * 100)}%`,
                              background: goal.progress >= goal.target ? "#00FF66" : "var(--accent)",
                            }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </motion.div>
          )}

          {/* Recommendations */}
          {!loading && recommendations.length > 0 && (
            <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.35 }} className="mt-8">
              <div className="flex items-center justify-between mb-4 sm:mb-5">
                <h2 className="font-display font-bold tracking-wider flex items-center gap-2.5" style={{ fontSize: "clamp(1rem, 2.5vw, 1.25rem)", color: "var(--text-primary)" }}>
                  <Crosshair size={18} style={{ color: "var(--accent)" }} /> РЕКОМЕНДАЦИИ
                </h2>
                <motion.button
                  onClick={() => router.push("/training")}
                  className="font-medium text-xs flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-colors"
                  style={{ color: "var(--accent)", background: "var(--accent-muted)" }}
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                >
                  Все сценарии <ArrowRight size={13} />
                </motion.button>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {recommendations.slice(0, 6).map((rec, i) => {
                  const diffColor = rec.difficulty >= 7 ? "var(--danger)" : rec.difficulty >= 4 ? "var(--warning)" : "var(--success)";
                  return (
                    <motion.div
                      key={rec.scenario_id}
                      initial={{ opacity: 0, y: 16, scale: 0.96 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      transition={{ delay: (0.4) + i * TIMING.staggerStep, duration: 0.5, ease: EASE_SNAP }}
                      className="glass-panel glass-panel-glow p-5 cursor-pointer group relative overflow-hidden"
                      whileHover={{ y: -4, boxShadow: "0 8px 32px var(--accent-glow)", borderColor: "var(--border-hover)" }}
                      onClick={async () => {
                        try {
                          const session = await api.post("/training/sessions", { scenario_id: rec.scenario_id });
                          router.push(`/training/${session.id}`);
                        } catch (err) {
                          logger.error("Failed to start training session:", err);
                          useNotificationStore.getState().addToast({ title: "Ошибка", body: "Не удалось начать тренировку", type: "error" });
                        }
                      }}
                    >
                      {/* Subtle top accent line */}
                      <div className="absolute top-0 left-4 right-4 h-[1px] rounded-full" style={{ background: `linear-gradient(90deg, transparent, var(--accent), transparent)`, opacity: 0.4 }} />

                      <div className="flex items-center justify-between mb-3">
                        <span className="font-medium text-xs uppercase tracking-wide px-2.5 py-1 rounded-full" style={{ background: "var(--accent-muted)", color: "var(--accent)" }}>
                          {rec.archetype}
                        </span>
                        <div className="flex items-center gap-1.5">
                          <div className="flex gap-0.5">
                            {[...Array(5)].map((_, j) => (
                              <div key={j} className="w-1.5 h-1.5 rounded-full transition-all duration-300" style={{
                                background: j < Math.ceil(rec.difficulty / 2) ? diffColor : "var(--input-bg)",
                                boxShadow: j < Math.ceil(rec.difficulty / 2) ? `0 0 4px ${diffColor}` : "none",
                              }} />
                            ))}
                          </div>
                        </div>
                      </div>

                      <div className="text-base font-semibold leading-snug group-hover:text-[var(--accent)] transition-colors duration-300" style={{ color: "var(--text-primary)" }}>
                        {rec.title}
                      </div>

                      {rec.tags.length > 0 && (
                        <div className="mt-3 flex flex-wrap gap-1.5">
                          {rec.tags.slice(0, 3).map((tag) => (
                            <span key={tag} className="text-xs font-medium px-2 py-0.5 rounded-md" style={{ background: "var(--input-bg)", color: "var(--text-muted)", border: "1px solid var(--glass-border)" }}>
                              {tag}
                            </span>
                          ))}
                        </div>
                      )}

                      {/* Hover arrow */}
                      <div className="absolute bottom-4 right-4 opacity-0 group-hover:opacity-100 transition-all duration-300 transform translate-x-2 group-hover:translate-x-0">
                        <ArrowRight size={16} style={{ color: "var(--accent)" }} />
                      </div>
                    </motion.div>
                  );
                })}
              </div>
            </motion.div>
          )}

          {/* F6.1: Training recommendations based on client losses */}
          {!loading && user?.role && ["manager", "rop", "admin"].includes(user.role) && (
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.45 }} className="mt-6">
              <TrainingRecommendations />
            </motion.div>
          )}

          {/* Client reminders — only for roles with client access */}
          {!loading && user?.role && ["manager", "rop", "admin"].includes(user.role) && (
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.5 }} className="mt-6">
              <ReminderWidget />
            </motion.div>
          )}

          {/* Team link for ROP */}
          {user?.role && (user.role === "rop" || user.role === "admin") && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.6 }} className="mt-8">
              <button onClick={() => router.push("/dashboard")} className="glass-panel glass-panel-interactive p-5 w-full flex items-center gap-4 transition-all">
                <Users size={20} style={{ color: "var(--accent)" }} />
                <div className="text-left">
                  <div className="font-medium text-sm" style={{ color: "var(--text-primary)" }}>Панель команды</div>
                  <div className="text-xs" style={{ color: "var(--text-muted)" }}>Аналитика, назначение тренировок, прогресс</div>
                </div>
                <ArrowRight size={16} className="ml-auto" style={{ color: "var(--text-muted)" }} />
              </button>
            </motion.div>
          )}

          {loading && (
            <div className="mt-2 space-y-4 stagger-cascade">
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
                {[1, 2, 3, 4].map((i) => (
                  <div key={i} className="glass-panel p-4 sm:p-5 space-y-3" style={{ borderLeft: "3px solid rgba(99,102,241,0.2)" }}>
                    <div className="h-9 w-9 rounded-xl skeleton-neon" />
                    <div className="h-8 w-16 rounded-lg skeleton-neon" />
                    <div className="h-2.5 w-12 rounded skeleton-neon" />
                  </div>
                ))}
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {[1, 2, 3].map((j) => (
                  <div key={j} className="glass-panel p-5 space-y-3">
                    <div className="flex justify-between">
                      <div className="h-4 w-20 rounded-full skeleton-neon" />
                      <div className="flex gap-0.5">{[1,2,3,4,5].map(d => <div key={d} className="w-1.5 h-1.5 rounded-full skeleton-neon" />)}</div>
                    </div>
                    <div className="h-5 w-3/4 rounded-lg skeleton-neon" />
                    <div className="flex gap-1.5">
                      <div className="h-3.5 w-12 rounded-md skeleton-neon" />
                      <div className="h-3.5 w-16 rounded-md skeleton-neon" />
                    </div>
                  </div>
                ))}
              </div>
              <LoadingTip />
            </div>
          )}
        </div>
      </div>
    </AuthLayout>
  );
}

/* ─── Assigned Trainings Badge ─────────────────────────────────────────────── */

/* ─── Stat Card with Tilt Effect ───────────────────────────────────────── */

interface StatCardProps {
  card: { label: string; value: number; icon: typeof Target; color: string; suffix: string; sparkData?: number[] };
  i: number;
}

function StatCard({ card, i }: StatCardProps) {
  const Icon = card.icon;

  return (
    <motion.div
      key={card.label}
      initial={{ opacity: 0, y: 20, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ delay: (0.15) + i * TIMING.staggerStep, duration: 0.5, ease: EASE_SNAP }}
      whileHover={{ y: -3, boxShadow: `0 8px 32px color-mix(in srgb, ${card.color} 15%, transparent)` }}
      className="glass-panel p-4 sm:p-5 group cursor-default relative overflow-hidden"
      style={{ borderLeft: `3px solid ${card.color}`, transition: "box-shadow 0.3s ease-out" }}
    >
      {/* Subtle bg glow */}
      <div
        className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none"
        style={{ background: `radial-gradient(ellipse at top left, color-mix(in srgb, ${card.color} 3%, transparent) 0%, transparent 70%)` }}
      />
      <div className="relative z-10">
        <div className="flex items-center justify-between mb-3">
          <div
            className="flex h-9 w-9 sm:h-10 sm:w-10 items-center justify-center rounded-xl transition-transform duration-300 group-hover:scale-110"
            style={{ background: `color-mix(in srgb, ${card.color} 9%, transparent)` }}
          >
            <Icon size={18} style={{ color: card.color }} />
          </div>
          {card.sparkData && typeof card.value === "number" && card.value > 0 && (
            <Sparkline data={card.sparkData} width={56} height={22} color={card.color} />
          )}
        </div>
        <div
          className="font-display font-black leading-none"
          style={{ fontSize: "clamp(1.6rem, 4vw, 2.2rem)", color: "var(--text-primary)" }}
        >
          {typeof card.value === "number"
            ? <AnimatedCounter value={card.value} duration={900} />
            : "—"}
        </div>
        <div className="mt-1.5 font-semibold text-xs uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
          {card.label}
        </div>
      </div>
    </motion.div>
  );
}

/* ─── Keyboard Shortcut Discovery Hint ─────────────────────────────────── */

function ShortcutHint() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE.shortcutHintVisits);
      const visits = raw ? parseInt(raw, 10) : 0;
      if (visits >= 3) return;
      localStorage.setItem(STORAGE.shortcutHintVisits, String(visits + 1));
      setVisible(true);
    } catch { /* localStorage unavailable */ }
  }, []);

  if (!visible) return null;

  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: "auto" }}
      exit={{ opacity: 0, height: 0 }}
      className="mt-3 flex items-center justify-between rounded-lg px-4 py-2.5"
      style={{ background: "var(--accent-muted)", border: "1px solid var(--border-color)" }}
    >
      <span className="font-semibold text-xs uppercase tracking-wide" style={{ color: "var(--accent)" }}>
        PRO TIP: <kbd className="px-1.5 py-0.5 rounded text-[10px]" style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)" }}>⌘K</kbd> — поиск · <kbd className="px-1.5 py-0.5 rounded text-[10px]" style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)" }}>?</kbd> — все шорткаты
      </span>
      <button
        onClick={() => { setVisible(false); try { localStorage.setItem(STORAGE.shortcutHintVisits, "3"); } catch {} }}
        style={{ color: "var(--text-muted)" }}
      >
        <X size={12} />
      </button>
    </motion.div>
  );
}

/* ─── Assigned Trainings Badge ─────────────────────────────────────────────── */

function AssignedBadge() {
  const router = useRouter();
  const { assigned, assignedLoading, fetchAssigned } = useTrainingStore();

  useEffect(() => {
    fetchAssigned();
  }, [fetchAssigned]);

  if (assignedLoading || assigned.length === 0) return null;

  const now = new Date();
  const overdueCount = assigned.filter((a) => a.deadline && new Date(a.deadline) < now).length;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="mt-4 glass-panel p-4 flex items-center gap-4 cursor-pointer transition-all"
      style={{
        borderLeft: overdueCount > 0 ? "3px solid var(--danger)" : "3px solid var(--accent)",
      }}
      whileHover={{ y: -1, boxShadow: "0 4px 20px var(--accent-glow)" }}
      onClick={() => router.push("/training?tab=assigned")}
    >
      <div
        className="flex h-10 w-10 items-center justify-center rounded-xl"
        style={{ background: overdueCount > 0 ? "rgba(255,51,51,0.1)" : "var(--accent-muted)" }}
      >
        <ClipboardList size={18} style={{ color: overdueCount > 0 ? "var(--danger)" : "var(--accent)" }} />
      </div>
      <div className="flex-1">
        <div className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
          Назначенные тренировки
        </div>
        <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
          {assigned.length} {assigned.length === 1 ? "сценарий" : assigned.length < 5 ? "сценария" : "сценариев"}
          {overdueCount > 0 && (
            <span style={{ color: "var(--danger)", fontWeight: 600 }}>
              {" "}· {overdueCount} просрочено!
            </span>
          )}
        </div>
      </div>
      <span
        className="min-w-[24px] h-6 flex items-center justify-center rounded-full text-xs font-bold text-white px-1.5"
        style={{ background: overdueCount > 0 ? "var(--danger)" : "var(--accent)" }}
      >
        {assigned.length}
      </span>
      <ArrowRight size={16} style={{ color: "var(--text-muted)" }} />
    </motion.div>
  );
}
