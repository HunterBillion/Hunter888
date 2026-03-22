"use client";

import { useEffect, useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  Zap, TrendingUp, Target, Clock, ArrowRight, Crosshair,
  Users, BarChart3, Loader2, X, Lightbulb, Flame, RotateCcw,
  Swords, Crown, Medal, ClipboardList,
} from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import AuthLayout from "@/components/layout/AuthLayout";
import { ReminderWidget } from "@/components/clients/ReminderWidget";
import { TrainingRecommendations } from "@/components/clients/TrainingRecommendations";
import { useTrainingStore } from "@/stores/useTrainingStore";
import type { DashboardManager } from "@/types";

function scoreColor(score: number | null): string {
  if (score === null) return "var(--text-muted)";
  if (score >= 70) return "var(--neon-green)";
  if (score >= 40) return "var(--neon-amber)";
  return "var(--neon-red)";
}

// F4: Tips database
const TIPS = [
  "Задавайте открытые вопросы — клиент сам расскажет о своих проблемах",
  "Не спорьте с возражениями — присоединяйтесь: «Я вас понимаю»",
  "Называйте конкретные цифры и кейсы — это убеждает скептиков",
  "Не торопитесь с презентацией — сначала выявите потребность",
  "Молчание клиента — не отказ, а время на обдумывание",
  "Используйте имя клиента — это повышает доверие на 30%",
  "Завершайте разговор конкретным следующим шагом, а не «перезвоню»",
  "Слушайте тон голоса — он говорит больше, чем слова",
  "Первые 10 секунд определяют, будет ли клиент слушать дальше",
  "Лучший аргумент — история похожего клиента, который уже решил проблему",
];

// F3: Daily challenges
const CHALLENGES = [
  { title: "Покорить скептика", desc: "Пройди сценарий с Алексеем Михайловым и набери 70+ баллов", type: "cold_call", minScore: 70 },
  { title: "Мастер эмпатии", desc: "Доведи тревожного клиента до состояния OPEN без единого давления", type: "cold_call", minScore: 60 },
  { title: "3 сессии за день", desc: "Пройди 3 тренировочных сессии за сегодня", type: "any", minScore: 0 },
  { title: "Идеальный скрипт", desc: "Набери 90%+ по показателю «Следование скрипту»", type: "cold_call", minScore: 90 },
  { title: "Укротитель агрессии", desc: "Пройди сценарий с агрессивным директором и доведи до сделки", type: "cold_call", minScore: 65 },
];

export default function HomePage() {
  const router = useRouter();
  const { user } = useAuth();
  const [dashboard, setDashboard] = useState<DashboardManager | null>(null);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);

  // F1: Portal animation state — show once per browser session
  const [showPortal, setShowPortal] = useState(() => {
    if (typeof window === "undefined") return false;
    return !sessionStorage.getItem("vh_portal_shown");
  });
  // F2: Welcome toast
  const [showWelcome, setShowWelcome] = useState(false);
  // F3: Daily challenge
  const [showChallenge, setShowChallenge] = useState(false);
  const [challengeDismissed, setChallengeDissmissed] = useState(false);

  // F4: Tip of the day (deterministic by date)
  const todayTip = useMemo(() => {
    const day = new Date();
    const idx = (day.getFullYear() * 366 + day.getMonth() * 31 + day.getDate()) % TIPS.length;
    return TIPS[idx];
  }, []);

  // F3: Today's challenge
  const todayChallenge = useMemo(() => {
    const day = new Date();
    const idx = (day.getFullYear() * 366 + day.getMonth() * 31 + day.getDate() + 7) % CHALLENGES.length;
    return CHALLENGES[idx];
  }, []);

  useEffect(() => {
    if (!user) return;
    api
      .get("/dashboard/manager")
      .then((data: DashboardManager) => setDashboard(data))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [user]);

  // F1: Portal auto-dismiss
  useEffect(() => {
    if (!showPortal) return;
    sessionStorage.setItem("vh_portal_shown", "1");
    const timer = setTimeout(() => {
      setShowPortal(false);
      // F2: Show welcome after portal
      setTimeout(() => setShowWelcome(true), 300);
      // F3: Show challenge after welcome
      setTimeout(() => {
        const lastChallenge = localStorage.getItem("vh_last_challenge");
        const today = new Date().toDateString();
        if (lastChallenge !== today) {
          setShowChallenge(true);
        }
      }, 2500);
    }, 1800);
    return () => clearTimeout(timer);
  }, []);

  // F2: Auto-dismiss welcome
  useEffect(() => {
    if (showWelcome) {
      const t = setTimeout(() => setShowWelcome(false), 4000);
      return () => clearTimeout(t);
    }
  }, [showWelcome]);

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
        const scenarios: { id: string }[] = await api.get("/scenarios/");
        if (!scenarios.length) { setStarting(false); return; }
        scenarioId = scenarios[Math.floor(Math.random() * scenarios.length)].id;
      }
      const session = await api.post("/training/sessions", { scenario_id: scenarioId });
      router.push(`/training/${session.id}`);
    } catch {
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

        {/* F1: Portal entry animation */}
        <AnimatePresence>
          {showPortal && (
            <motion.div
              className="fixed inset-0 z-[200] flex items-center justify-center"
              style={{ background: "var(--bg-primary)" }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.5 }}
            >
              {/* Tunnel rings */}
              {[0, 1, 2, 3, 4].map((i) => (
                <motion.div
                  key={i}
                  className="absolute rounded-full border"
                  style={{ borderColor: "var(--accent)", opacity: 0.15 }}
                  initial={{ width: 0, height: 0, opacity: 0 }}
                  animate={{
                    width: [0, 600 + i * 200],
                    height: [0, 600 + i * 200],
                    opacity: [0, 0.3, 0],
                  }}
                  transition={{
                    duration: 1.5,
                    delay: i * 0.2,
                    ease: "easeOut",
                  }}
                />
              ))}

              {/* Center flash */}
              <motion.div
                className="absolute w-4 h-4 rounded-full"
                style={{ background: "var(--accent)", boxShadow: "0 0 60px var(--accent-glow)" }}
                initial={{ scale: 0.5, opacity: 0 }}
                animate={{ scale: [0.5, 3, 80], opacity: [0, 1, 0] }}
                transition={{ duration: 1.5, ease: [0.16, 1, 0.3, 1] }}
              />

              {/* Logo */}
              <motion.div
                className="relative z-10"
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: [0, 1, 1, 0], scale: [0.8, 1, 1, 1.2] }}
                transition={{ duration: 1.5, times: [0, 0.2, 0.6, 1] }}
              >
                <Crosshair size={40} style={{ color: "var(--accent)" }} />
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* F2: Welcome back toast */}
        <AnimatePresence>
          {showWelcome && (
            <motion.div
              initial={{ opacity: 0, y: -50, x: "-50%" }}
              animate={{ opacity: 1, y: 0, x: "-50%" }}
              exit={{ opacity: 0, y: -30, x: "-50%" }}
              className="fixed top-20 left-1/2 z-[150] glass-panel px-6 py-4 flex items-center gap-4"
              style={{ minWidth: 320, boxShadow: "0 0 30px var(--accent-glow)" }}
            >
              <div className="flex h-10 w-10 items-center justify-center rounded-xl" style={{ background: "var(--accent)" }}>
                {streakDays > 0 ? <Flame size={20} className="text-white" /> : <Crosshair size={20} className="text-white" />}
              </div>
              <div>
                <div className="font-display text-sm font-bold" style={{ color: "var(--text-primary)" }}>
                  С возвращением, {firstName}!
                </div>
                <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
                  {streakDays > 0 ? `${streakDays}-дневный streak 🔥 · Level ${level}` : `Level ${level} · ${xpCurrent} XP`}
                </div>
              </div>
              <button onClick={() => setShowWelcome(false)} className="ml-auto" style={{ color: "var(--text-muted)" }}>
                <X size={14} />
              </button>
            </motion.div>
          )}
        </AnimatePresence>

        {/* F3: Daily challenge popup */}
        <AnimatePresence>
          {showChallenge && !challengeDismissed && (
            <motion.div
              initial={{ opacity: 0, scale: 0.9, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              className="fixed bottom-6 right-6 z-[150] glass-panel p-5 w-80"
              style={{ boxShadow: "0 8px 40px var(--accent-glow)", borderColor: "var(--accent)" }}
            >
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-2">
                  <div className="flex h-8 w-8 items-center justify-center rounded-lg" style={{ background: "var(--accent-muted)" }}>
                    <Target size={16} style={{ color: "var(--accent)" }} />
                  </div>
                  <div>
                    <div className="font-mono text-[9px] uppercase tracking-widest" style={{ color: "var(--accent)" }}>ЗАДАНИЕ ДНЯ</div>
                    <div className="font-display text-sm font-bold" style={{ color: "var(--text-primary)" }}>{todayChallenge.title}</div>
                  </div>
                </div>
                <button onClick={() => { setChallengeDissmissed(true); localStorage.setItem("vh_last_challenge", new Date().toDateString()); }}
                  style={{ color: "var(--text-muted)" }}
                >
                  <X size={14} />
                </button>
              </div>
              <p className="text-xs mb-3" style={{ color: "var(--text-secondary)" }}>{todayChallenge.desc}</p>
              <motion.button
                onClick={() => { setChallengeDissmissed(true); localStorage.setItem("vh_last_challenge", new Date().toDateString()); router.push("/training"); }}
                className="vh-btn-primary w-full flex items-center justify-center gap-2 text-sm py-2"
                whileTap={{ scale: 0.97 }}
              >
                Принять вызов <ArrowRight size={14} />
              </motion.button>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="mx-auto max-w-5xl px-4 py-8">
          {/* Welcome + Quick Start */}
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: showPortal ? 2 : 0 }}
            className="flex flex-col md:flex-row md:items-end md:justify-between gap-4"
          >
            <div>
              <h1 className="font-display text-3xl font-bold tracking-wider" style={{ color: "var(--text-primary)" }}>
                Привет, {firstName}
              </h1>
              <p className="mt-1 font-mono text-xs tracking-wider" style={{ color: "var(--text-muted)" }}>
                LEVEL {level} · {streakDays > 0 ? `${streakDays}-ДНЕВНЫЙ STREAK 🔥` : "НАЧНИТЕ STREAK СЕГОДНЯ"}
              </p>
            </div>

            <motion.button
              onClick={quickStart}
              disabled={starting}
              className="vh-btn-primary flex items-center gap-3 text-lg px-8 py-4 shrink-0"
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              {starting ? <Loader2 size={20} className="animate-spin" /> : <><Zap size={20} /> Quick Start <ArrowRight size={18} /></>}
            </motion.button>
          </motion.div>

          {/* XP Progress */}
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: showPortal ? 2.1 : 0.1 }} className="mt-6">
            <div className="flex items-center justify-between mb-1">
              <span className="font-mono text-[10px] tracking-wider" style={{ color: "var(--text-muted)" }}>УРОВЕНЬ {level}</span>
              <span className="font-mono text-[10px]" style={{ color: "var(--accent)" }}>{xpCurrent}/{xpNext} XP</span>
            </div>
            <div className="xp-bar h-3">
              <motion.div className="xp-bar-fill" initial={{ width: 0 }} animate={{ width: `${xpPct}%` }} transition={{ duration: 1, delay: showPortal ? 2.3 : 0.3 }} />
            </div>
          </motion.div>

          {/* Tournament Banner */}
          {!loading && dashboard?.tournament && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: showPortal ? 2.15 : 0.12 }}
              className="mt-4 rounded-xl p-4 flex items-center gap-4 cursor-pointer transition-all"
              style={{ background: "rgba(255,215,0,0.06)", border: "1px solid rgba(255,215,0,0.15)" }}
              whileHover={{ y: -1, boxShadow: "0 4px 20px rgba(255,215,0,0.1)" }}
              onClick={() => router.push("/leaderboard")}
            >
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl" style={{ background: "rgba(255,215,0,0.1)" }}>
                <Swords size={18} style={{ color: "#FFD700" }} />
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[9px] uppercase tracking-widest" style={{ color: "#FFD700" }}>ТУРНИР</span>
                  <span className="flex h-1.5 w-1.5 rounded-full animate-pulse" style={{ background: "var(--neon-green, #00FF66)" }} />
                </div>
                <div className="text-sm font-medium mt-0.5" style={{ color: "var(--text-primary)" }}>
                  {dashboard.tournament.title}
                </div>
                {/* Mini podium */}
                {dashboard.tournament.leaderboard.length > 0 && (
                  <div className="flex items-center gap-2 mt-1">
                    {dashboard.tournament.leaderboard.slice(0, 3).map((e) => (
                      <span key={e.user_id} className="font-mono text-[9px] flex items-center gap-0.5" style={{ color: "var(--text-muted)" }}>
                        {e.rank === 1 ? <Crown size={9} style={{ color: "#FFD700" }} /> : e.rank === 2 ? <Medal size={9} style={{ color: "#C0C0C0" }} /> : <Medal size={9} style={{ color: "#CD7F32" }} />}
                        {e.full_name.split(" ")[0]}
                      </span>
                    ))}
                  </div>
                )}
              </div>
              <ArrowRight size={16} style={{ color: "#FFD700" }} />
            </motion.div>
          )}

          {/* P3-25: Continue last session shortcut */}
          {lastSession && lastSession.status === "completed" && lastSession.score_total !== null && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: showPortal ? 2.15 : 0.15 }}
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

          {/* F4: Tip of the day */}
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: showPortal ? 2.2 : 0.2 }}
            className="mt-6 rounded-xl p-4 flex items-start gap-3"
            style={{ background: "var(--accent-muted)", border: "1px solid var(--glass-border)" }}
          >
            <Lightbulb size={18} className="shrink-0 mt-0.5" style={{ color: "var(--accent)" }} />
            <div>
              <div className="font-mono text-[9px] uppercase tracking-widest mb-1" style={{ color: "var(--accent)" }}>СОВЕТ ДНЯ</div>
              <p className="text-sm" style={{ color: "var(--text-secondary)" }}>{todayTip}</p>
            </div>
          </motion.div>

          {/* Stats Grid */}
          {!loading && (
            <div className="mt-8 grid grid-cols-2 md:grid-cols-4 gap-4">
              {[
                { label: "Сессий", value: stats?.completed_sessions ?? 0, icon: Target, color: "var(--accent)" },
                { label: "Ср. балл", value: stats?.avg_score != null ? Math.round(stats.avg_score) : "—", icon: TrendingUp, color: scoreColor(stats?.avg_score ?? null) },
                { label: "Лучший", value: stats?.best_score != null ? Math.round(stats.best_score) : "—", icon: BarChart3, color: scoreColor(stats?.best_score ?? null) },
                { label: "На неделе", value: stats?.sessions_this_week ?? 0, icon: Clock, color: "var(--neon-amber, #FFD700)" },
              ].map((card, i) => {
                const Icon = card.icon;
                return (
                  <motion.div key={card.label} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: (showPortal ? 2.3 : 0.15) + i * 0.05 }} className="glass-panel p-5"
                  >
                    <Icon size={16} style={{ color: card.color }} />
                    <div className="mt-2 font-display text-2xl font-bold" style={{ color: "var(--text-primary)" }}>{card.value}</div>
                    <div className="mt-0.5 font-mono text-[10px] uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>{card.label}</div>
                  </motion.div>
                );
              })}
            </div>
          )}

          {/* Recommendations */}
          {!loading && recommendations.length > 0 && (
            <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: showPortal ? 2.5 : 0.35 }} className="mt-8">
              <div className="flex items-center justify-between mb-4">
                <h2 className="font-display text-lg font-bold tracking-wider flex items-center gap-2" style={{ color: "var(--text-primary)" }}>
                  <Crosshair size={18} style={{ color: "var(--accent)" }} /> РЕКОМЕНДАЦИИ
                </h2>
                <button onClick={() => router.push("/training")} className="font-mono text-xs flex items-center gap-1" style={{ color: "var(--accent)" }}>
                  Все сценарии <ArrowRight size={12} />
                </button>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {recommendations.slice(0, 6).map((rec, i) => (
                  <motion.div key={rec.scenario_id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: (showPortal ? 2.6 : 0.4) + i * 0.05 }}
                    className="glass-panel p-4 cursor-pointer transition-all"
                    whileHover={{ y: -2, boxShadow: "0 4px 20px var(--accent-glow)" }}
                    onClick={async () => {
                      try {
                        const session = await api.post("/training/sessions", { scenario_id: rec.scenario_id });
                        router.push(`/training/${session.id}`);
                      } catch { /* ignore */ }
                    }}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-mono text-[9px] uppercase tracking-wider px-2 py-0.5 rounded-full" style={{ background: "var(--accent-muted)", color: "var(--accent)" }}>
                        {rec.archetype}
                      </span>
                      <span className="font-mono text-[10px]" style={{ color: rec.difficulty >= 7 ? "var(--neon-red, #FF3333)" : rec.difficulty >= 4 ? "var(--neon-amber, #FFD700)" : "var(--neon-green, #00FF94)" }}>
                        {rec.difficulty}/10
                      </span>
                    </div>
                    <div className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>{rec.title}</div>
                    {rec.tags.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {rec.tags.slice(0, 2).map((tag) => (
                          <span key={tag} className="text-[9px] font-mono px-1.5 py-0.5 rounded" style={{ background: "var(--input-bg)", color: "var(--text-muted)" }}>
                            {tag}
                          </span>
                        ))}
                      </div>
                    )}
                  </motion.div>
                ))}
              </div>
            </motion.div>
          )}

          {/* F6.1: Training recommendations based on client losses */}
          {!loading && user?.role && ["manager", "rop", "admin"].includes(user.role) && (
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: showPortal ? 2.65 : 0.45 }} className="mt-6">
              <TrainingRecommendations />
            </motion.div>
          )}

          {/* Client reminders — only for roles with client access */}
          {!loading && user?.role && ["manager", "rop", "admin"].includes(user.role) && (
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: showPortal ? 2.7 : 0.5 }} className="mt-6">
              <ReminderWidget />
            </motion.div>
          )}

          {/* Team link for ROP */}
          {user?.role && (user.role === "rop" || user.role === "admin") && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: showPortal ? 2.8 : 0.6 }} className="mt-8">
              <button onClick={() => router.push("/dashboard")} className="glass-panel p-5 w-full flex items-center gap-4 transition-all hover:brightness-110">
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
            <div className="mt-8 space-y-6">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {[1, 2, 3, 4].map((i) => (
                  <div key={i} className="glass-panel p-5 space-y-3 animate-pulse">
                    <div className="h-4 w-4 rounded bg-[var(--input-bg)]" />
                    <div className="h-7 w-16 rounded bg-[var(--input-bg)]" />
                    <div className="h-2.5 w-12 rounded bg-[var(--input-bg)]" />
                  </div>
                ))}
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {[1, 2, 3].map((j) => (
                  <div key={j} className="glass-panel p-4 space-y-3 animate-pulse">
                    <div className="flex justify-between">
                      <div className="h-3 w-16 rounded-full bg-[var(--input-bg)]" />
                      <div className="h-3 w-8 rounded bg-[var(--input-bg)]" />
                    </div>
                    <div className="h-4 w-3/4 rounded bg-[var(--input-bg)]" />
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </AuthLayout>
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
  const overdueCount = assigned.filter((a) => new Date(a.deadline) < now).length;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="mt-4 glass-panel p-4 flex items-center gap-4 cursor-pointer transition-all"
      style={{
        borderLeft: overdueCount > 0 ? "3px solid var(--neon-red, #FF3333)" : "3px solid var(--accent)",
      }}
      whileHover={{ y: -1, boxShadow: "0 4px 20px var(--accent-glow)" }}
      onClick={() => router.push("/training?tab=assigned")}
    >
      <div
        className="flex h-10 w-10 items-center justify-center rounded-xl"
        style={{ background: overdueCount > 0 ? "rgba(255,51,51,0.1)" : "var(--accent-muted)" }}
      >
        <ClipboardList size={18} style={{ color: overdueCount > 0 ? "var(--neon-red, #FF3333)" : "var(--accent)" }} />
      </div>
      <div className="flex-1">
        <div className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
          Назначенные тренировки
        </div>
        <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
          {assigned.length} {assigned.length === 1 ? "сценарий" : assigned.length < 5 ? "сценария" : "сценариев"}
          {overdueCount > 0 && (
            <span style={{ color: "var(--neon-red, #FF3333)", fontWeight: 600 }}>
              {" "}· {overdueCount} просрочено!
            </span>
          )}
        </div>
      </div>
      <span
        className="min-w-[24px] h-6 flex items-center justify-center rounded-full text-xs font-bold text-white px-1.5"
        style={{ background: overdueCount > 0 ? "var(--neon-red, #FF3333)" : "var(--accent)" }}
      >
        {assigned.length}
      </span>
      <ArrowRight size={16} style={{ color: "var(--text-muted)" }} />
    </motion.div>
  );
}
