"use client";

import { Suspense, useEffect, useState, useCallback } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { Loader2, Trophy, Calendar, Swords, BookOpen, Crown, Building2 } from "lucide-react";
import AuthLayout from "@/components/layout/AuthLayout";
import { api } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { logger } from "@/lib/logger";
import { PodiumCard, type PodiumEntry } from "@/components/leaderboard/PodiumCard";
import { LeaderboardTable, type LeaderboardRow } from "@/components/leaderboard/LeaderboardTable";
import { TPBreakdown, type TPBreakdownData } from "@/components/leaderboard/TPBreakdown";
import { LeagueTab } from "@/components/leaderboard/LeagueTab";
import { TeamsTab } from "@/components/leaderboard/TeamsTab";
import { PixelInfoButton } from "@/components/ui/PixelInfoButton";

/** Hunter Score row from GET /gamification/leaderboard/hunters */
interface HunterEntry {
  rank: number;
  user_id: string;
  full_name: string;
  avatar_url?: string | null;
  hunter_score: number;
  current_level: number;
  week_tp: number;
  prev_week_tp: number;
  delta_vs_last_week: number;
  is_me: boolean;
}

/** Weekly TP row from GET /gamification/leaderboard/weekly-tp */
interface WeeklyTpEntry {
  rank: number;
  user_id: string;
  full_name: string;
  avatar_url?: string | null;
  week_tp: number;
  is_me: boolean;
}

type Tab = "hunter" | "league" | "teams" | "week" | "month" | "arena" | "knowledge";

const TABS: { key: Tab; label: string; icon: typeof Trophy }[] = [
  { key: "hunter", label: "Охотник", icon: Crown },
  { key: "league", label: "Лига", icon: Trophy },
  { key: "teams", label: "Команды", icon: Building2 },
  { key: "week", label: "Неделя", icon: Calendar },
  { key: "month", label: "Месяц", icon: Trophy },
  { key: "arena", label: "Арена", icon: Swords },
  { key: "knowledge", label: "Знания", icon: BookOpen },
];

const VALID_TABS: Tab[] = ["hunter", "league", "teams", "week", "month", "arena", "knowledge"];

export default function LeaderboardPageWrapper() {
  // useSearchParams requires a Suspense boundary in Next 14 app router.
  return (
    <Suspense fallback={null}>
      <LeaderboardPage />
    </Suspense>
  );
}

function LeaderboardPage() {
  const { user } = useAuth();
  const params = useSearchParams();
  const router = useRouter();
  const initialTab = (() => {
    const t = params?.get("tab");
    return t && (VALID_TABS as string[]).includes(t) ? (t as Tab) : "hunter";
  })();
  const [activeTab, setActiveTab] = useState<Tab>(initialTab);

  // Reflect ?tab= in URL when user clicks tabs (so sharable + back-button works).
  const switchTab = useCallback(
    (next: Tab) => {
      setActiveTab(next);
      const url = next === "hunter" ? "/leaderboard" : `/leaderboard?tab=${next}`;
      router.replace(url, { scroll: false });
    },
    [router],
  );

  // Re-sync if user navigates with browser back/forward.
  useEffect(() => {
    const t = params?.get("tab");
    const next = t && (VALID_TABS as string[]).includes(t) ? (t as Tab) : "hunter";
    setActiveTab(next);
  }, [params]);

  // Hunter tab state
  const [hunters, setHunters] = useState<HunterEntry[]>([]);
  const [hunterLoading, setHunterLoading] = useState(true);

  // Weekly TP tab state
  const [weeklyTp, setWeeklyTp] = useState<WeeklyTpEntry[]>([]);
  const [weeklyLoading, setWeeklyLoading] = useState(true);

  // My TP breakdown (shown alongside hunter & week tabs)
  const [breakdown, setBreakdown] = useState<TPBreakdownData | null>(null);
  const [breakdownLoading, setBreakdownLoading] = useState(true);

  // Monthly / arena / knowledge — reuse existing endpoints
  const [monthlyRows, setMonthlyRows] = useState<LeaderboardRow[] | null>(null);
  const [arenaRows, setArenaRows] = useState<LeaderboardRow[] | null>(null);
  const [knowledgeRows, setKnowledgeRows] = useState<LeaderboardRow[] | null>(null);

  const fetchHunters = useCallback(async () => {
    setHunterLoading(true);
    try {
      const data: HunterEntry[] = await api.get("/gamification/leaderboard/hunters?scope=company&limit=50");
      setHunters(Array.isArray(data) ? data : []);
    } catch (err) {
      logger.error("Failed to load hunter leaderboard:", err);
      setHunters([]);
    } finally {
      setHunterLoading(false);
    }
  }, []);

  const fetchWeeklyTp = useCallback(async () => {
    setWeeklyLoading(true);
    try {
      const data: WeeklyTpEntry[] = await api.get("/gamification/leaderboard/weekly-tp?scope=company&limit=50");
      setWeeklyTp(Array.isArray(data) ? data : []);
    } catch (err) {
      logger.error("Failed to load weekly TP:", err);
      setWeeklyTp([]);
    } finally {
      setWeeklyLoading(false);
    }
  }, []);

  const fetchBreakdown = useCallback(async () => {
    setBreakdownLoading(true);
    try {
      const data: TPBreakdownData = await api.get("/gamification/leaderboard/my-breakdown");
      setBreakdown(data);
    } catch (err) {
      logger.error("Failed to load TP breakdown:", err);
      setBreakdown(null);
    } finally {
      setBreakdownLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!user) return;
    fetchHunters();
    fetchBreakdown();
    fetchWeeklyTp();
  }, [user, fetchHunters, fetchBreakdown, fetchWeeklyTp]);

  // Lazy-load less common tabs
  useEffect(() => {
    if (!user) return;
    if (activeTab === "arena" && arenaRows === null) {
      api.get<{ entries?: Array<{ rank: number; user_id: string; full_name: string; rating: number; rank_tier?: string }> }>("/pvp/leaderboard?limit=50")
        .then((data) => {
          const entries = data?.entries ?? [];
          setArenaRows(entries.map((e) => ({
            rank: e.rank,
            user_id: e.user_id,
            full_name: e.full_name,
            score: e.rating,
            subtitle: e.rank_tier ? String(e.rank_tier).toUpperCase() : null,
            is_me: e.user_id === user.id,
          })));
        })
        .catch(() => setArenaRows([]));
    }
    if (activeTab === "knowledge" && knowledgeRows === null) {
      api.get<Array<{ rank: number; user_id: string; full_name: string; rating: number }>>("/knowledge/arena/leaderboard?limit=50")
        .then((data) => {
          const arr = Array.isArray(data) ? data : [];
          setKnowledgeRows(arr.map((e) => ({
            rank: e.rank,
            user_id: e.user_id,
            full_name: e.full_name,
            score: e.rating,
            is_me: e.user_id === user.id,
          })));
        })
        .catch(() => setKnowledgeRows([]));
    }
    if (activeTab === "month" && monthlyRows === null) {
      api.get<{ tournament?: { id: string } | null; leaderboard?: Array<{ rank: number; user_id: string; full_name: string; best_score: number; attempts: number }> }>("/tournament/active?type=monthly_championship")
        .then((data) => {
          const arr = data?.leaderboard ?? [];
          setMonthlyRows(arr.map((e) => ({
            rank: e.rank,
            user_id: e.user_id,
            full_name: e.full_name,
            score: e.best_score,
            subtitle: `${e.attempts} попыток`,
            is_me: e.user_id === user.id,
          })));
        })
        .catch(() => setMonthlyRows([]));
    }
  }, [activeTab, user, arenaRows, knowledgeRows, monthlyRows]);

  // Convert Hunter entries → table rows
  const hunterRows: LeaderboardRow[] = hunters.map((h) => ({
    rank: h.rank,
    user_id: h.user_id,
    full_name: h.full_name,
    avatar_url: h.avatar_url,
    score: h.hunter_score,
    delta: h.delta_vs_last_week,
    subtitle: `Ур. ${h.current_level} · ${h.week_tp} TP за неделю`,
    is_me: h.is_me,
  }));

  const hunterPodium: PodiumEntry[] = hunters.slice(0, 3).map((h) => ({
    user_id: h.user_id,
    full_name: h.full_name,
    avatar_url: h.avatar_url,
    score: h.hunter_score,
    delta: h.delta_vs_last_week,
    scoreUnit: "HS",
  }));

  const weeklyRows: LeaderboardRow[] = weeklyTp.map((w) => ({
    rank: w.rank,
    user_id: w.user_id,
    full_name: w.full_name,
    avatar_url: w.avatar_url,
    score: w.week_tp,
    subtitle: null,
    is_me: w.is_me,
  }));

  const weeklyPodium: PodiumEntry[] = weeklyTp.slice(0, 3).map((w) => ({
    user_id: w.user_id,
    full_name: w.full_name,
    score: w.week_tp,
    scoreUnit: "TP",
  }));

  return (
    <AuthLayout>
      <div className="panel-grid-bg min-h-screen">
        <div className="app-page max-w-6xl">
          {/* Header */}
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="mb-6 flex items-start justify-between gap-3"
          >
            <div>
              <h1 className="font-display text-2xl md:text-3xl font-bold tracking-tight" style={{ color: "var(--text-primary)" }}>
                Лидерборд
              </h1>
              <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
                Единый рейтинг охотников. Очки от всех активностей: тренировки, PvP, квизы, мульти-сессии.
              </p>
            </div>
            <PixelInfoButton
              title="Лидерборд"
              sections={[
                { icon: Trophy, label: "Рейтинг охотника", text: "Общий рейтинг охотников компании — чем выше, тем элитнее" },
                { icon: Crown, label: "Лига недели", text: "Автогруппы по 20 игроков близкого уровня. Топ-3 получают сундук-награды в воскресенье 23:00 МСК" },
                { icon: Calendar, label: "Неделя/Месяц", text: "TP — очки за тренировки, накапливаются еженедельно и сбрасываются в понедельник" },
                { icon: Swords, label: "PvP-дуэли", text: "Отдельный рейтинг дуэлей. Стартовый ранг: Бронза → Серебро → Золото → Платина" },
                { icon: BookOpen, label: "Арена знаний", text: "Квизы по 127-ФЗ. Очки начисляются за правильные + быстрые ответы" },
              ]}
              footer="Подсказка: кликните на свою строку — откроется детализация откуда пришли очки"
            />
          </motion.div>

          {/* Tabs */}
          <div
            className="flex gap-1 mb-6 p-1 rounded-xl overflow-x-auto"
            style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)" }}
          >
            {TABS.map((t) => {
              const Icon = t.icon;
              const active = activeTab === t.key;
              return (
                <button
                  key={t.key}
                  onClick={() => switchTab(t.key)}
                  className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-all shrink-0"
                  style={{
                    background: active ? "var(--accent)" : "transparent",
                    color: active ? "#fff" : "var(--text-secondary)",
                    boxShadow: active ? "0 2px 10px var(--accent-glow)" : "none",
                  }}
                >
                  <Icon size={14} />
                  {t.label}
                </button>
              );
            })}
          </div>

          <AnimatePresence mode="wait">
            <motion.div
              key={activeTab}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.18 }}
              className={
                activeTab === "hunter" || activeTab === "week"
                  ? "grid gap-5 md:grid-cols-[1fr_320px]"
                  : "grid gap-5"
              }
            >
              <div className="space-y-5 min-w-0">
                {activeTab === "hunter" && (
                  <>
                    {hunterLoading ? (
                      <div className="flex items-center justify-center py-16">
                        <Loader2 size={24} className="animate-spin" style={{ color: "var(--accent)" }} />
                      </div>
                    ) : (
                      <>
                        {hunterPodium.length >= 3 && (
                          <PodiumCard top3={hunterPodium} title="Топ-3 охотника" />
                        )}
                        <LeaderboardTable
                          rows={hunterRows}
                          scoreUnit="HS"
                          emptyMessage="Пока никто не накопил Hunter Score. Тренируйтесь — цифры появятся!"
                        />
                      </>
                    )}
                  </>
                )}

                {activeTab === "week" && (
                  <>
                    {weeklyLoading ? (
                      <div className="flex items-center justify-center py-16">
                        <Loader2 size={24} className="animate-spin" style={{ color: "var(--accent)" }} />
                      </div>
                    ) : (
                      <>
                        {weeklyPodium.length >= 3 && (
                          <PodiumCard top3={weeklyPodium} title="Топ-3 недели" />
                        )}
                        <LeaderboardTable
                          rows={weeklyRows}
                          scoreUnit="TP"
                          emptyMessage="На этой неделе ещё нет активностей — пройдите тренировку, чтобы начать."
                        />
                      </>
                    )}
                  </>
                )}

                {activeTab === "league" && <LeagueTab />}

                {activeTab === "teams" && <TeamsTab />}

                {activeTab === "month" && (
                  <>
                    {monthlyRows === null ? (
                      <div className="flex items-center justify-center py-16">
                        <Loader2 size={24} className="animate-spin" style={{ color: "var(--accent)" }} />
                      </div>
                    ) : monthlyRows.length === 0 ? (
                      <div className="glass-panel p-8 text-center">
                        <Trophy size={36} className="mx-auto mb-3" style={{ color: "var(--text-muted)", opacity: 0.4 }} />
                        <div className="font-display font-semibold mb-1" style={{ color: "var(--text-primary)" }}>
                          Месячный турнир не активен
                        </div>
                        <div className="text-sm" style={{ color: "var(--text-muted)" }}>
                          Админ может создать турнир типа &laquo;monthly_championship&raquo; через панель управления.
                        </div>
                      </div>
                    ) : (
                      <LeaderboardTable rows={monthlyRows} scoreUnit="pts" />
                    )}
                  </>
                )}

                {activeTab === "arena" && (
                  <>
                    {arenaRows === null ? (
                      <div className="flex items-center justify-center py-16">
                        <Loader2 size={24} className="animate-spin" style={{ color: "var(--accent)" }} />
                      </div>
                    ) : (
                      <LeaderboardTable
                        rows={arenaRows}
                        scoreUnit="ELO"
                        emptyMessage="В арене пока никто не сыграл — сразитесь первым."
                      />
                    )}
                  </>
                )}

                {activeTab === "knowledge" && (
                  <>
                    {knowledgeRows === null ? (
                      <div className="flex items-center justify-center py-16">
                        <Loader2 size={24} className="animate-spin" style={{ color: "var(--accent)" }} />
                      </div>
                    ) : (
                      <LeaderboardTable
                        rows={knowledgeRows}
                        scoreUnit="ELO"
                        emptyMessage="Пока нет участников. Пройдите квиз в Арене Знаний."
                      />
                    )}
                  </>
                )}
              </div>

              {/* Sidebar — TP breakdown for Hunter & Week tabs */}
              {(activeTab === "hunter" || activeTab === "week") && (
                <div className="min-w-0">
                  <TPBreakdown data={breakdown} loading={breakdownLoading} />
                </div>
              )}
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </AuthLayout>
  );
}
