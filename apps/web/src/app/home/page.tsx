"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { motion } from "framer-motion";
import {
  ArrowRight, Loader2, X, RotateCcw, Check, Phone,
} from "lucide-react";
import {
  Lightning, TrendUp, Target, Clock, Crosshair,
  UsersThree, ChartBar, Flame, Sword, Crown, Medal,
  ClipboardText, Sun, Moon, Star,
} from "@phosphor-icons/react";
import { Button } from "@/components/ui/Button";
import { PixelInfoButton } from "@/components/ui/PixelInfoButton";
import { api } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import AuthLayout from "@/components/layout/AuthLayout";
import { NavigatorBlock } from "@/components/ui/NavigatorBlock";
import { DailyRemindersPill } from "@/components/clients/DailyRemindersPill";
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
import DailyDrillCard from "@/components/gamification/DailyDrillCard";
import MorningWarmupCard from "@/components/gamification/MorningWarmupCard";
import WeeklyLeague from "@/components/gamification/WeeklyLeague";
import OfficeShelf from "@/components/gamification/OfficeShelf";
import SeasonBanner from "@/components/gamification/SeasonBanner";
import ChapterProgress from "@/components/gamification/ChapterProgress";
// useTiltEffect kept in hooks/ for future use on non-motion elements


// ── Time-of-day greeting (subtle, above name) ─────────────────────────
function getTimeGreeting(): string {
  const h = new Date().getHours();
  if (h >= 5 && h < 12) return "Доброе утро";
  if (h >= 12 && h < 17) return "Добрый день";
  if (h >= 17 && h < 22) return "Добрый вечер";
  return "Ночная смена";
}

interface StoryProgressData {
  current_chapter: number;
  chapter_name: string;
  epoch_name: string;
  chapter_sessions: number;
  chapter_avg_score: number;
  next_chapter: number | null;
  next_unlock_level: number | null;
  next_unlock_sessions: number | null;
  next_unlock_score: number | null;
  manager_level: number;
  progress_pct: number;
}

interface DailyHookData {
  weak_points?: string[];
  focus_recommendation?: string;
  worst_trap?: string;
  worst_trap_count?: number;
}

interface DailyHookResult {
  headline: string;   // bold primary text
  subtext: string;    // secondary description
  emotion: string;    // css color
  icon: typeof Sun;
  priority: number;
}

/**
 * Personalized daily hook — 9-priority system.
 * Returns structured data for dedicated DailyHook card (not cramped into status line).
 */
function getDailyHook(
  dashboard: DashboardManager & { daily_hook?: DailyHookData } | null,
  story: StoryProgressData | null,
): DailyHookResult {
  if (!dashboard) return { headline: "Готов к охоте?", subtext: "", emotion: "var(--accent)", icon: Crosshair, priority: 9 };

  const streak = dashboard.gamification?.streak_days ?? 0;
  const lastScore = dashboard.recent_sessions?.[0]?.score_total ?? null;
  const totalSessions = dashboard.stats?.total_sessions ?? 0;
  const hook = (dashboard as { daily_hook?: DailyHookData }).daily_hook;
  const worstTrap = hook?.worst_trap;
  const worstTrapCount = hook?.worst_trap_count ?? 0;
  const weakSkill = hook?.weak_points?.[0];

  // P1/P2 streak hooks removed 2026-04-18 — user feedback: "Серия: N дней"
  // headline was noisy and duplicated the streak badge in the hero. The streak
  // counter chip stays visible below the name; no hero headline for streak.
  void streak; // keep variable referenced, used elsewhere in this function

  // P3: Last score < 50 — revenge
  if (lastScore !== null && lastScore < 50) {
    const trapInfo = worstTrap ? `Ловушка '${worstTrap}' сломала тебя.` : "Прошлый звонок не задался.";
    return {
      headline: `Вчера ${Math.round(lastScore)}/100`,
      subtext: `${trapInfo} Цель сегодня — ${Math.min(Math.round(lastScore) + 15, 100)}`,
      emotion: "var(--danger)", icon: Crosshair, priority: 3,
    };
  }

  // P4: Last score 50-70 — focus on weak skill
  if (lastScore !== null && lastScore >= 50 && lastScore <= 70) {
    const skillInfo = weakSkill ? `'${weakSkill}' тянет вниз.` : "Есть куда расти.";
    return {
      headline: `${Math.round(lastScore)}/100 — неплохо`,
      subtext: `${skillInfo} Сфокусируйся на слабом месте`,
      emotion: "var(--warning)", icon: Target, priority: 4,
    };
  }

  // P5: Failed trap 2+ times
  if (worstTrap && worstTrapCount >= 2) {
    return {
      headline: `Ловушка '${worstTrap}'`,
      subtext: `Победила тебя ${worstTrapCount} раз. Сегодня она вернётся`,
      emotion: "var(--danger)", icon: Crosshair, priority: 5,
    };
  }

  // P6: Chapter unlock approaching
  if (story && story.next_chapter && story.progress_pct >= 70) {
    return {
      headline: `Глава ${story.next_chapter} почти открыта`,
      subtext: `${Math.round(story.progress_pct)}% прогресса. Ещё немного`,
      emotion: "var(--accent)", icon: Star, priority: 6,
    };
  }

  // P6b: New chapter just started
  if (story && story.chapter_sessions === 0 && story.current_chapter > 1) {
    return {
      headline: `Глава ${story.current_chapter}: ${story.chapter_name}`,
      subtext: "Новый враг. Новые правила",
      emotion: "var(--accent)", icon: Star, priority: 6,
    };
  }

  // P7: New user (day 1)
  if (totalSessions === 0) {
    return {
      headline: "Твой первый клиент ждёт",
      subtext: "Добро пожаловать, Охотник. Начни прямо сейчас",
      emotion: "var(--accent)", icon: Crosshair, priority: 7,
    };
  }

  // P8: New user (days 2-3)
  if (totalSessions >= 1 && totalSessions <= 3) {
    return {
      headline: "Ты вернулся",
      subtext: "Хороший знак. Вчера было легко. Сегодня — нет",
      emotion: "var(--accent)", icon: Lightning, priority: 8,
    };
  }

  // P9: Fallback
  return { headline: "Готов к охоте?", subtext: "", emotion: "var(--accent)", icon: Crosshair, priority: 9 };
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
  const [storyProgress, setStoryProgress] = useState<StoryProgressData | null>(null);
  // 2026-04-20: lightweight "warm-up done today?" indicator for the hero.
  // Sourced from /morning-drill/streak — the same endpoint the card uses.
  const [warmupDoneToday, setWarmupDoneToday] = useState<boolean | null>(null);
  const [waitingClient, setWaitingClient] = useState<{
    full_name: string;
    age: number;
    city: string;
    archetype_code: string;
    difficulty: number;
    trust_level: number;
    total_debt: number;
    scenario_id: string;
    lead_source: string;
    gender: string;
  } | null>(null);


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
    api.get<StoryProgressData>("/story/progress")
      .then((data) => setStoryProgress(data))
      .catch(() => { /* optional — story not blocking */ });
    api.get<{ client: typeof waitingClient }>("/home/waiting-client")
      .then((data) => setWaitingClient(data.client))
      .catch(() => { /* optional — fallback to old quickStart */ });
    api.get("/gamification/goals")
      .then((data: unknown) => {
        if (data && typeof data === "object") {
          const d = data as Record<string, unknown>;
          // Support both: {goals: [...]} flat array and {daily: [...], weekly: [...], goals: [...]}
          if ("goals" in d && Array.isArray(d.goals)) {
            setDailyGoals(d.goals as Array<{ id: string; title: string; xp: number; progress: number; target: number }>);
          }
        }
      })
      .catch(() => { /* optional */ });
    api.get<{ completed_today: boolean }>("/morning-drill/streak")
      .then((s) => setWarmupDoneToday(!!s.completed_today))
      .catch(() => { /* non-blocking badge */ });
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

  // 2026-04-20: targeted goal refresh after warm-up / other micro-actions.
  // MorningWarmupCard dispatches `goals:refresh` on /complete success. We
  // only refetch the goals endpoint — NOT the whole dashboard — because
  // the rest of the page state hasn't changed.
  useEffect(() => {
    const onGoalsRefresh = () => {
      api.get("/gamification/goals")
        .then((data: unknown) => {
          if (data && typeof data === "object") {
            const d = data as Record<string, unknown>;
            if ("goals" in d && Array.isArray(d.goals)) {
              setDailyGoals(
                d.goals as Array<{
                  id: string; title: string; xp: number; progress: number; target: number;
                }>,
              );
            }
          }
        })
        .catch(() => { /* non-blocking */ });
      // The hero "warm-up ✓" badge also needs to flip after /complete.
      api.get<{ completed_today: boolean }>("/morning-drill/streak")
        .then((s) => setWarmupDoneToday(!!s.completed_today))
        .catch(() => { /* non-blocking */ });
    };
    window.addEventListener("goals:refresh", onGoalsRefresh);
    return () => window.removeEventListener("goals:refresh", onGoalsRefresh);
  }, []);

  // 2026-04-18: автообновление рекомендаций + статистики каждые 60 сек
  // (без таймера на UI — тихое обновление). Пауза при скрытой вкладке
  // уже обеспечивается visibilitychange выше. Предотвращает "залипание"
  // карточек рекомендаций на стартовых данных после прохождения сессии.
  useEffect(() => {
    if (!user) return;
    const intervalId = setInterval(() => {
      if (document.visibilityState === "visible") {
        fetchDashboard();
      }
    }, 60_000);
    return () => clearInterval(intervalId);
  }, [user]);


  const recommendations = dashboard?.recommendations ?? [];
  const recentSessions = dashboard?.recent_sessions ?? [];
  const lastSession = recentSessions[0] ?? null;

  const quickStart = async () => {
    if (starting) return;
    setStarting(true);
    try {
      // Prefer the waiting client (new /home/start flow)
      if (waitingClient) {
        const session = await api.post("/home/start", {});
        if (session?.id) {
          router.push(`/training/${session.id}`);
          setTimeout(() => setStarting(false), 1000);
          return;
        }
      }
      // Fallback: old random scenario flow
      let scenarioId: string;
      if (recommendations.length > 0) {
        const rec = recommendations[Math.floor(Math.random() * recommendations.length)];
        scenarioId = rec.scenario_id;
      } else {
        const scenariosData = await api.get("/scenarios/");
        const scenarios: { id: string }[] = Array.isArray(scenariosData) ? scenariosData : [];
        if (!scenarios.length) { setStarting(false); return; }
        scenarioId = scenarios[Math.floor(Math.random() * scenarios.length)].id;
      }
      const session = await api.post("/training/sessions", { scenario_id: scenarioId });
      if (!session?.id) throw new Error("Invalid session response");
      router.push(`/training/${session.id}`);
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
            className="relative rounded-2xl overflow-hidden p-6 sm:p-8 mb-6 glass-panel"
          >
            {/* Accent corner glow */}
            <div
              className="absolute -top-16 -left-16 w-48 sm:w-64 h-48 sm:h-64 rounded-full pointer-events-none"
              style={{ background: "radial-gradient(circle, var(--accent-muted) 0%, transparent 70%)" }}
            />

            {/* Info button — top-right of hero card */}
            <div className="absolute top-4 right-4 z-20">
              <PixelInfoButton
                title="Командный центр"
                sections={[
                  { icon: Lightning, label: "Уровень и XP", text: "Растёт от каждой завершённой тренировки. Нужно XP/next для следующего уровня" },
                  { icon: Flame, label: "Серия дней", text: "Сколько дней подряд вы тренируетесь. 7+ дней = бонус Streak Freeze на случай пропуска" },
                  { icon: Crosshair, label: "Quick Start", text: "Кнопка-огонёк слева: мгновенно подберёт сценарий под ваш уровень и начнёт тренировку" },
                  { icon: Target, label: "Ожидающий клиент", text: "Если вы прервали звонок — он покажется здесь. Можно продолжить с того же момента" },
                  { icon: ClipboardText, label: "Ежедневный вызов", text: "Случайное задание с повышенной наградой. Обновляется каждый день в 00:00 МСК" },
                  { icon: TrendUp, label: "Рекомендации", text: "AI-Coach подбирает 3 тренировки на основе ваших слабых мест" },
                ]}
                footer="Горячие клавиши: S — быстрый старт, H — история, L — лидерборд"
              />
            </div>

            <div className="relative z-10 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-6">
              {/* Left: identity + level */}
              <div className="flex items-center gap-5">
                {/* Level ring */}
                <div className="relative shrink-0" style={{ width: 88, height: 88 }}>
                  <svg width="88" height="88" viewBox="0 0 88 88" className="rotate-[-90deg]">
                    {/* Background track */}
                    <circle cx="44" cy="44" r="38" fill="none" stroke="var(--accent-muted)" strokeWidth="5" />
                    {/* Main progress arc */}
                    <circle
                      cx="44" cy="44" r="38" fill="none"
                      stroke="var(--accent)"
                      strokeWidth="5"
                      strokeLinecap="round"
                      strokeDasharray={`${2 * Math.PI * 38}`}
                      strokeDashoffset={`${2 * Math.PI * 38 * (1 - xpPct / 100)}`}
                      style={{ filter: "drop-shadow(0 0 4px var(--accent-glow))", transition: "stroke-dashoffset 1s ease" }}
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
                  <div className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--text-muted)" }}>
                    {getTimeGreeting()}
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
                        <Flame weight="duotone" size={10} /> {streakDays} дней
                      </span>
                    )}
                    <span
                      className="inline-flex items-center gap-1 font-mono text-xs px-2.5 py-1 rounded-full uppercase tracking-wider"
                      style={{ background: "var(--accent-muted)", border: "1px solid var(--accent-glow)", color: "var(--accent)" }}
                    >
                      <Lightning weight="duotone" size={10} /> {xpCurrent} / {xpNext} XP
                    </span>
                    {warmupDoneToday !== null && (
                      <span
                        className="inline-flex items-center gap-1 font-mono text-xs px-2.5 py-1 rounded-full uppercase tracking-wider"
                        style={
                          warmupDoneToday
                            ? {
                                background:
                                  "color-mix(in srgb, var(--success) 12%, transparent)",
                                border:
                                  "1px solid color-mix(in srgb, var(--success) 35%, transparent)",
                                color: "var(--success)",
                              }
                            : {
                                background: "var(--input-bg)",
                                border: "1px solid var(--border-color)",
                                color: "var(--text-muted)",
                              }
                        }
                        title={
                          warmupDoneToday
                            ? "Сегодняшняя разминка зачтена"
                            : "Разминка сегодня ещё не пройдена"
                        }
                      >
                        {warmupDoneToday ? (
                          <>
                            <Check size={10} /> Разминка
                          </>
                        ) : (
                          <>
                            <Sun weight="duotone" size={10} /> Разминка ждёт
                          </>
                        )}
                      </span>
                    )}
                    {/* 2026-04-20: today's reminders — pill + pop-over.
                        Renders nothing when the user has no reminders, so
                        the badge row stays clean for new users. Previously
                        lived as a full-width widget below all panels where
                        nobody saw it. */}
                    <DailyRemindersPill />
                  </div>
                </div>
              </div>

              {/* Right: Quick Start CTA — hidden when waiting client card below is shown,
                  since both do the same thing (start a session). */}
              {!waitingClient && (
                <motion.button
                  onClick={quickStart}
                  disabled={starting}
                  className="inline-flex items-center justify-center gap-3 font-display font-bold shrink-0 rounded-xl uppercase tracking-wide transition-all duration-200 disabled:opacity-40"
                  style={{ fontSize: "clamp(0.95rem, 2vw, 1.1rem)", padding: "clamp(0.875rem, 2vw, 1.1rem) clamp(1.5rem, 4vw, 2.5rem)", background: "var(--accent)", color: "#fff", border: "1px solid var(--accent)", boxShadow: "0 0 20px var(--accent-glow), 0 0 60px var(--accent-muted)", animation: starting ? "none" : "pulse-glow 2.5s ease-in-out infinite" }}
                  whileHover={{ scale: 1.04, boxShadow: "0 12px 40px var(--accent-glow)" }}
                  whileTap={{ scale: 0.97 }}
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ duration: 0.6, delay: 0, ease: EASE_SNAP }}
                >
                  {starting
                    ? <Loader2 size={20} className="animate-spin" />
                    : <><Lightning weight="duotone" size={20} /><span>Быстрая охота</span><ArrowRight size={18} /></>
                  }
                </motion.button>
              )}
            </div>

            {/* XP bar inside hero */}
            <motion.div
              className="relative z-10 mt-5"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.2 }}
            >
              {/* 2026-04-18: увеличена высота 6px → 10px (≈1.67×),
                  добавлен 3-стоповый градиент (deep → accent → light),
                  inner glow + shimmer animation.
                  ВАЖНО: класс .xp-bar задаёт h-2 (8px), но раньше inline
                  `h-1.5` перезаписывал на 6px. Теперь `h-[10px]` — явная
                  высота без каскадного конфликта. */}
              <div
                className="xp-bar rounded-full relative overflow-hidden"
                style={{
                  height: "10px",
                  background: "var(--input-bg)",
                  border: "1px solid color-mix(in srgb, var(--accent) 22%, transparent)",
                  boxShadow: "inset 0 1px 2px rgba(0, 0, 0, 0.2)",
                }}
              >
                <motion.div
                  className="xp-bar-fill h-full rounded-full"
                  initial={{ width: 0 }}
                  animate={{ width: `${xpPct}%` }}
                  transition={{ duration: 1.2, delay: 0.35, ease: EASE_SNAP }}
                  style={{
                    background: "linear-gradient(90deg, var(--brand-deep), var(--accent) 60%, color-mix(in srgb, var(--accent) 70%, white 30%))",
                    boxShadow: "0 0 12px color-mix(in srgb, var(--accent) 50%, transparent)",
                  }}
                />
              </div>
              {/* 2026-04-20: увеличен контраст цифр под XP-баром (276/500 —
                  пользователь "цифры не видны вообще"). Было text-muted,
                  теперь числа text-primary + semibold, а "XP" и "До уровня"
                  остаются приглушёнными лейблами. tabular-nums для ровной
                  ширины. */}
              <div className="mt-2 flex justify-between items-baseline gap-2 flex-wrap">
                <span
                  className="font-mono text-[13px] tabular-nums"
                  style={{ color: "var(--text-muted)" }}
                >
                  <span className="font-semibold" style={{ color: "var(--text-primary)" }}>
                    {xpCurrent}
                  </span>
                  {" / "}
                  <span className="font-semibold" style={{ color: "var(--text-primary)" }}>
                    {xpNext}
                  </span>
                  {" XP"}
                </span>
                <span
                  className="font-mono text-[13px] tabular-nums"
                  style={{ color: "var(--text-muted)" }}
                >
                  {"До уровня "}
                  <span className="font-semibold" style={{ color: "var(--accent)" }}>
                    {level + 1}
                  </span>
                  {": "}
                  <span className="font-semibold" style={{ color: "var(--accent)" }}>
                    {xpNext - xpCurrent}
                  </span>
                  {" XP"}
                </span>
              </div>
            </motion.div>
          </motion.div>

          {/* ── WAITING CLIENT — rotates every ~1 hour ──────────────────── */}
          {waitingClient && (
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.15, duration: 0.5, ease: EASE_SNAP }}
              className="relative rounded-2xl overflow-hidden p-5 sm:p-6 mb-6 glass-panel"
              style={{ border: "1px solid var(--accent-muted)" }}
            >
              {/* 2026-04-18: зелёная пульсирующая точка → анимация
                  звонящего телефона. framer-motion rotate keyframes
                  имитируют "shake" звонка. Круглый фон + ping-пульс для
                  визуального акцента. */}
              <div className="flex items-center gap-2.5 mb-3">
                <span
                  className="relative flex h-7 w-7 items-center justify-center rounded-full"
                  style={{ background: "color-mix(in srgb, var(--color-green, #22c55e) 15%, transparent)" }}
                >
                  {/* Ping pulse */}
                  <span
                    className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-60"
                    style={{ background: "var(--color-green, #22c55e)" }}
                  />
                  {/* Phone icon with ring-shake animation */}
                  <motion.span
                    className="relative inline-flex items-center justify-center"
                    animate={{ rotate: [0, -14, 14, -14, 14, -8, 8, 0] }}
                    transition={{
                      duration: 0.9,
                      repeat: Infinity,
                      repeatDelay: 1.3,
                      ease: "easeInOut",
                    }}
                  >
                    <Phone size={14} strokeWidth={2.5} style={{ color: "var(--color-green, #22c55e)" }} />
                  </motion.span>
                </span>
                <span className="font-mono text-xs uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                  Входящий звонок
                </span>
              </div>

              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                <div className="min-w-0">
                  <h3 className="font-display font-bold text-lg truncate" style={{ color: "var(--text-primary)" }}>
                    {waitingClient.full_name}
                  </h3>
                  <div className="flex flex-wrap items-center gap-2 mt-1.5">
                    <span className="font-mono text-xs px-2 py-0.5 rounded-full" style={{ background: "var(--accent-muted)", color: "var(--accent)" }}>
                      {waitingClient.city}
                    </span>
                    <span className="font-mono text-xs px-2 py-0.5 rounded-full" style={{ background: "var(--surface-secondary)", color: "var(--text-secondary)" }}>
                      Долг: {(waitingClient.total_debt / 1000).toFixed(0)}K
                    </span>
                    <span className="font-mono text-xs px-2 py-0.5 rounded-full" style={{ background: "var(--surface-secondary)", color: "var(--text-secondary)" }}>
                      {"★".repeat(Math.min(waitingClient.difficulty, 5))}{"☆".repeat(Math.max(0, 5 - waitingClient.difficulty))}
                    </span>
                  </div>
                </div>

                <motion.button
                  onClick={quickStart}
                  disabled={starting}
                  className="inline-flex items-center justify-center gap-2 font-display font-bold shrink-0 rounded-xl uppercase tracking-wide transition-all duration-200 disabled:opacity-40"
                  style={{
                    fontSize: "0.9rem",
                    padding: "0.75rem 1.5rem",
                    background: "var(--color-green, #22c55e)",
                    color: "#fff",
                    border: "none",
                    boxShadow: "0 0 16px rgba(34, 197, 94, 0.3)",
                  }}
                  whileHover={{ scale: 1.04 }}
                  whileTap={{ scale: 0.97 }}
                >
                  {starting
                    ? <Loader2 size={16} className="animate-spin" />
                    : <><Crosshair weight="duotone" size={16} /><span>Ответить</span></>
                  }
                </motion.button>
              </div>
            </motion.div>
          )}

          {/* 2026-04-20: РЕКОМЕНДАЦИИ — сверху, сразу под Hero / Waiting Client.
              Раньше блок жил ниже Stats/Mission — пользователи не скроллили
              до него и рекомендации почти не кликались. Формат: 3 карточки
              в одну строку, компактнее оригинала (меньше padding, нет
              "top accent line" decor — это убивало плотность).
              Кнопка "Все сценарии →" справа уводит в /training. */}
          {!loading && recommendations.length > 0 && (
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.18, duration: 0.4, ease: EASE_SNAP }}
              className="mt-4"
            >
              <div className="flex items-center justify-between mb-3">
                <h2
                  className="font-display font-bold tracking-wider flex items-center gap-2"
                  style={{
                    fontSize: "clamp(0.9rem, 2vw, 1.05rem)",
                    color: "var(--text-primary)",
                  }}
                >
                  <Crosshair
                    weight="duotone"
                    size={16}
                    style={{ color: "var(--accent)" }}
                  />
                  РЕКОМЕНДУЕМ НАЧАТЬ С
                </h2>
                <motion.button
                  onClick={() => router.push("/training")}
                  className="font-medium text-xs flex items-center gap-1.5 px-2.5 py-1 rounded-lg transition-colors"
                  style={{
                    color: "var(--accent)",
                    background: "var(--accent-muted)",
                  }}
                  whileHover={{ scale: 1.04 }}
                  whileTap={{ scale: 0.97 }}
                >
                  Все сценарии <ArrowRight size={12} />
                </motion.button>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {recommendations.slice(0, 3).map((rec, i) => {
                  const diffColor =
                    rec.difficulty >= 7
                      ? "var(--danger)"
                      : rec.difficulty >= 4
                      ? "var(--warning)"
                      : "var(--success)";
                  return (
                    <motion.div
                      key={rec.scenario_id}
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{
                        delay: 0.22 + i * TIMING.staggerStep,
                        duration: 0.35,
                        ease: EASE_SNAP,
                      }}
                      className="glass-panel p-4 cursor-pointer group relative overflow-hidden"
                      whileHover={{
                        y: -2,
                        boxShadow: "0 6px 24px var(--accent-glow)",
                      }}
                      onClick={async () => {
                        try {
                          const session = await api.post(
                            "/training/sessions",
                            { scenario_id: rec.scenario_id },
                          );
                          router.push(`/training/${session.id}`);
                        } catch (err) {
                          logger.error("Failed to start training session:", err);
                          useNotificationStore.getState().addToast({
                            title: "Ошибка",
                            body: "Не удалось начать тренировку",
                            type: "error",
                          });
                        }
                      }}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <span
                          className="font-medium text-[11px] uppercase tracking-wide px-2 py-0.5 rounded-full"
                          style={{
                            background: "var(--accent-muted)",
                            color: "var(--accent)",
                          }}
                        >
                          {rec.archetype}
                        </span>
                        <div className="flex gap-0.5">
                          {[...Array(5)].map((_, j) => (
                            <div
                              key={j}
                              className="w-1 h-1 rounded-full"
                              style={{
                                background:
                                  j < Math.ceil(rec.difficulty / 2)
                                    ? diffColor
                                    : "var(--input-bg)",
                              }}
                            />
                          ))}
                        </div>
                      </div>
                      <div
                        className="text-sm font-semibold leading-snug group-hover:text-[var(--accent)] transition-colors line-clamp-2"
                        style={{ color: "var(--text-primary)" }}
                      >
                        {rec.title}
                      </div>
                      {rec.tags.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {rec.tags.slice(0, 2).map((tag) => (
                            <span
                              key={tag}
                              className="text-[10px] font-medium px-1.5 py-0.5 rounded"
                              style={{
                                background: "var(--input-bg)",
                                color: "var(--text-muted)",
                              }}
                            >
                              {tag}
                            </span>
                          ))}
                        </div>
                      )}
                      <div className="absolute bottom-3 right-3 opacity-0 group-hover:opacity-100 transition-opacity">
                        <ArrowRight size={14} style={{ color: "var(--accent)" }} />
                      </div>
                    </motion.div>
                  );
                })}
              </div>
            </motion.div>
          )}

          {/* 2026-04-18: Daily Hook panel ("Готов к охоте?" fallback) removed
              per user feedback — fallback headline for users with no context
              was empty-looking noise. Specific hooks (bad-trap, worst-skill,
              story-unlock) were informative but rarely the default state. */}
          {false && (() => { return null; })()}

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
                <Sword weight="duotone" size={18} style={{ color: RANK.gold }} />
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
                {dashboard.tournament?.leaderboard?.length > 0 && (
                  <div className="flex items-center gap-2 mt-1">
                    {dashboard.tournament.leaderboard.slice(0, 3).map((e) => (
                      <span key={e.user_id} className="font-mono text-xs flex items-center gap-0.5" style={{ color: "var(--text-muted)" }}>
                        {e.rank === 1 ? <Crown weight="duotone" size={9} style={{ color: RANK.gold }} /> : e.rank === 2 ? <Medal weight="duotone" size={9} style={{ color: RANK.silver }} /> : <Medal weight="duotone" size={9} style={{ color: RANK.bronze }} />}
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

          {/* Stats Grid.
              2026-04-18 fix: sparkData больше НЕ hardcoded массивы —
              теперь выводятся из dashboard.recent_sessions (последние 7
              значений). Если сессий мало — массив короче, StatCard сам
              рисует flat line. Это отражает реальную историю пользователя. */}
          {!loading && (() => {
            const recent = dashboard?.recent_sessions ?? [];
            // Берём последние 7 сессий в хронологическом порядке (старые → новые)
            const lastSessions = [...recent].slice(0, 7).reverse();
            const scoreSeries = lastSessions
              .map((s) => (typeof s.score_total === "number" ? Math.round(s.score_total) : null))
              .filter((v): v is number => v !== null);
            // Running max для "Лучший"
            const bestSeries: number[] = [];
            let runningMax = 0;
            for (const v of scoreSeries) {
              runningMax = Math.max(runningMax, v);
              bestSeries.push(runningMax);
            }
            // Для "Сессий" — накопительно 1,2,3...N по числу последних сессий
            const sessionsCumulative = scoreSeries.map((_, i) => i + 1);
            // За неделю: агрегируем по дням (bucket last 7 days)
            const now = Date.now();
            const weekBuckets = Array.from({ length: 7 }, () => 0);
            for (const s of recent) {
              if (!s.started_at) continue;
              const daysAgo = Math.floor((now - new Date(s.started_at).getTime()) / 86400000);
              if (daysAgo >= 0 && daysAgo < 7) weekBuckets[6 - daysAgo] += 1;
            }

            const cards = [
              { label: "Сессий", value: stats?.completed_sessions ?? 0, icon: Target, color: "var(--accent)", suffix: "", sparkData: sessionsCumulative.length > 1 ? sessionsCumulative : [stats?.completed_sessions ?? 0] },
              { label: "Ср. балл", value: stats?.avg_score != null ? Math.round(stats.avg_score) : 0, icon: TrendUp, color: scoreColor(stats?.avg_score ?? null), suffix: "", sparkData: scoreSeries.length > 1 ? scoreSeries : [Math.round(stats?.avg_score ?? 0)] },
              { label: "Лучший", value: stats?.best_score != null ? Math.round(stats.best_score) : 0, icon: ChartBar, color: scoreColor(stats?.best_score ?? null), suffix: "", sparkData: bestSeries.length > 1 ? bestSeries : [Math.round(stats?.best_score ?? 0)] },
              { label: "За неделю", value: stats?.sessions_this_week ?? 0, icon: Clock, color: STREAK.light, suffix: "", sparkData: weekBuckets },
            ];
            return (
              <div className="mt-4 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3 sm:gap-4">
                {cards.map((card, i) => (
                  <StatCard key={card.label} card={card} i={i} />
                ))}
              </div>
            );
          })()}

          {/* ── MISSION PANEL: Drill + Goals + League + Season — all in one ──
              2026-04-18: панель поднимается выше через mt-5 вместо mt-6,
              увеличен padding, шрифт заголовка 16px, добавлен pixel-border
              stylized эффект для визуального акцента (как у карточек
              тренировок в панели "Pixel Cyber"). Contrast goals bigger. */}
          {!loading && (
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3 }}
              className="mt-5 pixel-border glass-panel rounded-2xl p-6 sm:p-7"
              style={{
                "--pixel-border-color": "color-mix(in srgb, var(--accent) 40%, var(--border-color))",
              } as React.CSSProperties}
            >
              {/* Panel header — 14px uppercase pixel font, accent icon bigger */}
              {/* 2026-04-18: шрифт заголовка через inline-style на
                  var(--font-vt323) напрямую — Tailwind-класс `font-pixel`
                  иногда не подцеплялся из-за cascade/tree-shaking в dev
                  mode. Теперь VT323 гарантированно применяется. */}
              <div className="flex items-center justify-between mb-5">
                <h2
                  className="font-bold tracking-widest uppercase flex items-center gap-2.5"
                  style={{
                    color: "var(--text-primary)",
                    fontFamily: "var(--font-vt323), 'Press Start 2P', monospace",
                    fontSize: "20px",
                    letterSpacing: "0.14em",
                  }}
                >
                  <Target weight="duotone" size={22} style={{ color: "var(--accent)" }} />
                  Задания на сегодня
                </h2>
                <SeasonBanner />
              </div>

              {/* Story arc progress (Путь Охотника) */}
              <ChapterProgress />

              {/* Two-column: Drill (left) + Goals (right) */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                {/* Разминка дня.
                    2026-04-17: заменила чат-style DailyDrillCard.
                    2026-04-18: был введён time-gate (05:00-12:00) — скрывал
                    карточку днём/вечером.
                    2026-04-20 (owner feedback): time-gate снят — ROP зашёл в
                    обед и не увидел разминку, "не могу пройти свою". Теперь
                    карточка видна весь день, пока не completed_today. Сама
                    MorningWarmupCard уже показывает "✓ Разминка зачтена"
                    когда streak endpoint вернёт completed_today=true. */}
                <MorningWarmupCard />
                {false && <DailyDrillCard drillStreak={dashboard?.gamification?.streak_days ?? 0} />}

                {/* Right: Goals progress.
                    2026-04-18: увеличен шрифт (text-sm → text-base),
                    прогресс-бар выше (h-1.5 → h-2), числа font-pixel. */}
                <div className="space-y-4 flex flex-col justify-center">
                  {dailyGoals.length > 0 ? (
                    dailyGoals.slice(0, 4).map((goal: { id: string; title: string; xp: number; progress: number; target: number }) => (
                      <div key={goal.id}>
                        <div className="flex justify-between items-center text-base mb-1.5">
                          <span
                            className="font-medium"
                            style={{ color: goal.progress >= goal.target ? "var(--success)" : "var(--text-primary)" }}
                          >
                            {goal.progress >= goal.target ? <><Check size={16} className="inline mr-1" /></> : ""}
                            {goal.title}
                          </span>
                          <span
                            className="shrink-0 ml-2 tabular-nums"
                            style={{
                              color: "var(--text-muted)",
                              fontFamily: "var(--font-vt323), monospace",
                              letterSpacing: "0.04em",
                              // 2026-04-18: VT323 at 14px renders much smaller than sans-serif 14px.
                              // Bump to 20px so numbers match the title visually.
                              fontSize: 20,
                              lineHeight: "1",
                            }}
                          >
                            {goal.progress}/{goal.target} <span style={{ color: "var(--warning)" }}>+{goal.xp}</span>
                          </span>
                        </div>
                        <div className="h-2 rounded-full overflow-hidden" style={{ background: "var(--input-bg)" }}>
                          <div
                            className="h-full rounded-full transition-all duration-300"
                            style={{
                              width: `${Math.min(100, (goal.progress / goal.target) * 100)}%`,
                              background: goal.progress >= goal.target ? "var(--success)" : "var(--accent)",
                            }}
                          />
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="flex items-center gap-2 text-sm text-[var(--text-muted)] py-4">
                      <Target weight="duotone" size={16} style={{ color: "var(--accent)" }} />
                      Цели загружаются...
                    </div>
                  )}
                  {/* Daily Challenge inline */}
                  {dailyChallenge && (
                    <div className="rounded-lg bg-[var(--input-bg)] p-3 flex items-center justify-between">
                      <div className="flex items-center gap-2 min-w-0">
                        <Lightning weight="duotone" size={14} style={{ color: "var(--warning)" }} />
                        <span className="text-xs text-[var(--text-secondary)] truncate">{dailyChallenge.title}</span>
                      </div>
                      <span className="text-xs font-mono shrink-0" style={{ color: "var(--warning)" }}>+{dailyChallenge.rewardXp}</span>
                    </div>
                  )}
                </div>
              </div>

              {/* Bottom row: League + Office compact */}
              <div className="flex items-center justify-between pt-3" style={{ borderTop: "1px solid var(--input-bg)" }}>
                {/* League mini */}
                <WeeklyLeague />

                {/* Office shelf compact */}
                <OfficeShelf
                  level={dashboard?.gamification?.level ?? 1}
                  compact
                />
              </div>
            </motion.div>
          )}

          {/* 2026-04-20: старый большой блок "РЕКОМЕНДАЦИИ" (6 карточек)
              удалён — теперь 3 карточки живут сразу под Hero / Waiting
              Client. Если пользователю нужно больше — кнопка "Все сценарии"
              в верхнем блоке ведёт в /training с полным списком. */}

          {/* F6.1: Training recommendations based on client losses */}
          {!loading && user?.role && ["manager", "rop", "admin"].includes(user.role) && (
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.45 }} className="mt-6">
              <TrainingRecommendations />
            </motion.div>
          )}

          {/* 2026-04-20: client reminders block moved to hero as
              <DailyRemindersPill /> — smaller footprint, much higher
              visibility. The full-width widget that used to sit here was
              below the fold for most users. */}

          {/* Team link for ROP — removed 2026-04-18 per feedback. ROP accesses
              the dashboard from the main header nav; showing a duplicate CTA
              on /home was noise. */}

          {loading && (
            <div className="mt-2 space-y-4 stagger-cascade">
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
                {[1, 2, 3, 4].map((i) => (
                  <div key={i} className="glass-panel p-4 sm:p-5 space-y-3" style={{ borderLeft: "3px solid var(--accent-glow)" }}>
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
      transition={{ delay: 0.05 + i * 0.06, duration: 0.3, ease: EASE_SNAP }}
      whileHover={{ y: -3, boxShadow: `0 8px 32px color-mix(in srgb, ${card.color} 15%, transparent)`, transition: { duration: 0.1 } }}
      whileTap={{ scale: 0.96, transition: { duration: 0.08 } }}
      className="glass-panel p-4 sm:p-5 group cursor-default relative overflow-hidden"
      style={{ borderLeft: `3px solid ${card.color}`, transition: "box-shadow 0.1s ease-out" }}
    >
      {/* Subtle bg glow */}
      <div
        className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-150 pointer-events-none"
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
        PRO TIP: <kbd className="px-1.5 py-0.5 rounded text-xs" style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)" }}>⌘K</kbd> — поиск · <kbd className="px-1.5 py-0.5 rounded text-xs" style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)" }}>?</kbd> — все шорткаты
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
        style={{ background: overdueCount > 0 ? "var(--danger-muted)" : "var(--accent-muted)" }}
      >
        <ClipboardText weight="duotone" size={18} style={{ color: overdueCount > 0 ? "var(--danger)" : "var(--accent)" }} />
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
