"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Trophy, Medal, Crown, TrendingUp, Loader2, Swords, Clock, Zap, Plus, X as XIcon } from "lucide-react";
import AuthLayout from "@/components/layout/AuthLayout";
import { UserAvatar } from "@/components/ui/UserAvatar";
import { LeaderboardSkeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { api } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { hasRole } from "@/lib/guards";
import { RANK } from "@/lib/constants";
import type { TournamentLeaderboardEntry, ActiveTournamentResponse, Scenario } from "@/types";
import { logger } from "@/lib/logger";

interface GamificationEntry {
  rank: number;
  user_id: string;
  full_name: string;
  avatar_url?: string | null;
  sessions_count: number;
  total_score: number;
  avg_score: number;
}

interface CompositeEntry {
  rank: number;
  user_id: string;
  full_name: string;
  avatar_url?: string | null;
  composite_score: number;
  training_avg: number;
  pvp_rating_norm: number;
  knowledge_score: number;
  streak_bonus: number;
}

type Tab = "general" | "tournament" | "composite";

function getRankIcon(rank: number) {
  if (rank === 1) return <Crown size={18} style={{ color: RANK.gold }} />;
  if (rank === 2) return <Medal size={18} style={{ color: RANK.silver }} />;
  if (rank === 3) return <Medal size={18} style={{ color: RANK.bronze }} />;
  return <span className="font-mono text-sm font-bold" style={{ color: "var(--text-muted)" }}>{rank}</span>;
}

function getRankStyle(rank: number) {
  if (rank === 1) return { bg: RANK.goldRgba(0.08), border: RANK.goldRgba(0.2), glow: `0 0 15px ${RANK.goldRgba(0.15)}` };
  if (rank === 2) return { bg: RANK.silverRgba(0.06), border: RANK.silverRgba(0.15), glow: "none" };
  if (rank === 3) return { bg: RANK.bronzeRgba(0.06), border: RANK.bronzeRgba(0.15), glow: "none" };
  return { bg: "var(--glass-bg)", border: "var(--glass-border)", glow: "none" };
}

function formatTimeLeft(weekEnd: string): string {
  const diff = new Date(weekEnd).getTime() - Date.now();
  if (diff <= 0) return "Завершён";
  const days = Math.floor(diff / 86400000);
  const hours = Math.floor((diff % 86400000) / 3600000);
  if (days > 0) return `${days}д ${hours}ч`;
  return `${hours}ч`;
}

export default function LeaderboardPage() {
  const { user } = useAuth();
  const canCreateTournament = hasRole(user, ["admin", "rop"]);
  const [tab, setTab] = useState<Tab>("general");
  const [period, setPeriod] = useState<"week" | "month" | "all">("week");
  const [entries, setEntries] = useState<GamificationEntry[]>([]);
  const [loading, setLoading] = useState(true);

  // Tournament state
  const [tournament, setTournament] = useState<ActiveTournamentResponse | null>(null);
  const [tournamentEntries, setTournamentEntries] = useState<TournamentLeaderboardEntry[]>([]);
  const [tournamentLoading, setTournamentLoading] = useState(true);

  // Composite leaderboard state
  const [compositeEntries, setCompositeEntries] = useState<CompositeEntry[]>([]);
  const [compositeLoading, setCompositeLoading] = useState(false);

  // Create tournament modal
  const [showCreate, setShowCreate] = useState(false);

  // Fetch gamification leaderboard
  useEffect(() => {
    setLoading(true);
    api
      .get(`/gamification/leaderboard?period=${period}`)
      .then((data: GamificationEntry[]) => setEntries(data))
      .catch((err) => { logger.error("Failed to load leaderboard:", err); setEntries([]); })
      .finally(() => setLoading(false));
  }, [period]);

  // Fetch tournament data
  useEffect(() => {
    api.get("/tournament/active")
      .then((data: ActiveTournamentResponse) => {
        setTournament(data);
        if (data.tournament) {
          // Fetch full leaderboard (top 20)
          api.get(`/tournament/leaderboard/${data.tournament.id}`)
            .then((lb: TournamentLeaderboardEntry[]) => setTournamentEntries(lb))
            .catch((err) => { logger.error("Failed to load tournament leaderboard:", err); setTournamentEntries(data.leaderboard); });
        }
      })
      .catch((err) => { logger.error("Failed to load active tournament:", err); })
      .finally(() => setTournamentLoading(false));
  }, []);

  // Fetch composite leaderboard when tab switches
  useEffect(() => {
    if (tab !== "composite") return;
    setCompositeLoading(true);
    api.get("/gamification/leaderboard/composite")
      .then((data: CompositeEntry[]) => setCompositeEntries(data))
      .catch((err) => { logger.error("Failed to load composite leaderboard:", err); setCompositeEntries([]); })
      .finally(() => setCompositeLoading(false));
  }, [tab]);

  const TABS: { id: Tab; label: string; icon: React.ComponentType<{ size: number; style?: React.CSSProperties }> }[] = [
    { id: "general", label: "Общий", icon: Trophy },
    { id: "tournament", label: "Турнир", icon: Swords },
    { id: "composite", label: "Комплексный", icon: Zap },
  ];

  return (
    <AuthLayout>
      <div className="relative panel-grid-bg min-h-screen">
        <div className="app-page max-w-3xl">
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
            <h1 className="font-display text-2xl font-bold tracking-wider" style={{ color: "var(--text-primary)" }}>
              РЕЙТИНГ
            </h1>
            <p className="mt-1 text-sm" style={{ color: "var(--text-muted)" }}>
              Лучшие результаты за период
            </p>
          </motion.div>

          {/* Tabs */}
          <div className="mt-6 flex gap-1 rounded-xl p-1" style={{ background: "var(--input-bg)" }}>
            {TABS.map((t) => {
              const Icon = t.icon;
              const active = tab === t.id;
              return (
                <button
                  key={t.id}
                  onClick={() => setTab(t.id)}
                  className="relative flex-1 flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 font-medium text-sm tracking-wide transition-colors"
                  style={{ color: active ? "var(--text-primary)" : "var(--text-muted)" }}
                >
                  {active && (
                    <motion.div
                      layoutId="lbActiveTab"
                      className="absolute inset-0 rounded-lg"
                      style={{ background: "var(--glass-bg)", border: "1px solid var(--glass-border)" }}
                      transition={{ type: "spring", stiffness: 400, damping: 30 }}
                    />
                  )}
                  <span className="relative z-10 flex items-center gap-2">
                    <Icon size={14} style={{ color: active ? "var(--accent)" : "var(--text-muted)" }} />
                    {t.label}
                    {t.id === "tournament" && tournament?.tournament && (
                      <span className="flex h-2 w-2 rounded-full" style={{ background: "var(--success)" }} />
                    )}
                  </span>
                </button>
              );
            })}
          </div>

          <AnimatePresence mode="wait">
            {tab === "general" && (
              <motion.div key="general" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.2 }}>
                {/* Period selector */}
                <div className="mt-6 flex gap-2 overflow-x-auto scrollbar-hide">
                  {([
                    { key: "week", label: "Неделя" },
                    { key: "month", label: "Месяц" },
                    { key: "all", label: "Всё время" },
                  ] as const).map((p) => (
                    <motion.button
                      key={p.key}
                      onClick={() => setPeriod(p.key)}
                      className="rounded-lg px-3 sm:px-4 py-2.5 font-medium text-sm tracking-wide transition-all whitespace-nowrap"
                      style={{
                        background: period === p.key ? "var(--accent-muted)" : "var(--input-bg)",
                        border: `1px solid ${period === p.key ? "var(--accent)" : "var(--border-color)"}`,
                        color: period === p.key ? "var(--accent)" : "var(--text-muted)",
                      }}
                      whileTap={{ scale: 0.97 }}
                    >
                      {p.label}
                    </motion.button>
                  ))}
                </div>

                <LeaderboardList
                  loading={loading}
                  empty={entries.length === 0}
                  items={entries.map((e) => ({
                    rank: e.rank,
                    userId: e.user_id,
                    name: e.full_name,
                    avatarUrl: e.avatar_url,
                    subtitle: `${e.sessions_count} сессий · ср. ${Math.round(e.avg_score)}`,
                    score: Math.round(e.total_score),
                    scoreLabel: "ОЧКИ",
                  }))}
                />
              </motion.div>
            )}

            {tab === "tournament" && (
              <motion.div key="tournament" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.2 }}>
                {/* Create tournament button for Admin/ROP */}
                {canCreateTournament && (
                  <div className="mt-6 flex justify-end">
                    <motion.button
                      onClick={() => setShowCreate(true)}
                      className="btn-neon flex items-center gap-2 text-xs"
                      whileTap={{ scale: 0.97 }}
                    >
                      <Plus size={14} /> Создать турнир
                    </motion.button>
                  </div>
                )}

                {tournament?.tournament ? (
                  <>
                    {/* Tournament info banner */}
                    <div className="mt-6 rounded-xl p-4 flex items-center gap-4"
                      style={{ background: "color-mix(in srgb, var(--rank-gold) 6%, transparent)", border: "1px solid color-mix(in srgb, var(--rank-gold) 15%, transparent)" }}
                    >
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl" style={{ background: "color-mix(in srgb, var(--rank-gold) 10%, transparent)" }}>
                        <Swords size={18} style={{ color: RANK.gold }} />
                      </div>
                      <div className="flex-1">
                        <div className="font-display text-sm font-bold" style={{ color: "var(--text-primary)" }}>
                          {tournament.tournament.title}
                        </div>
                        <div className="flex items-center gap-3 mt-1 font-mono text-xs" style={{ color: "var(--text-muted)" }}>
                          <span className="flex items-center gap-1">
                            <Clock size={10} /> {formatTimeLeft(tournament.tournament.week_end)}
                          </span>
                          <span className="flex items-center gap-1" style={{ color: RANK.gold }}>
                            <Crown size={10} /> {tournament.tournament.bonus_xp[0]} XP
                          </span>
                          <span className="flex items-center gap-1">
                            <Zap size={10} /> макс. {tournament.tournament.max_attempts} попыток
                          </span>
                        </div>
                      </div>
                    </div>

                    <LeaderboardList
                      loading={tournamentLoading}
                      empty={tournamentEntries.length === 0}
                      emptyText="Пока нет участников турнира"
                      items={tournamentEntries.map((e) => ({
                        rank: e.rank,
                        userId: e.user_id,
                        name: e.full_name,
                        avatarUrl: e.avatar_url,
                        subtitle: `${e.attempts} попыт${e.attempts === 1 ? "ка" : e.attempts < 5 ? "ки" : "ок"}`,
                        score: Math.round(e.best_score),
                        scoreLabel: "ЛУЧШИЙ",
                      }))}
                    />
                  </>
                ) : (
                  <div className="mt-16 flex flex-col items-center py-8">
                    <Swords size={32} style={{ color: "var(--text-muted)" }} />
                    <p className="mt-3 text-sm" style={{ color: "var(--text-muted)" }}>
                      {tournamentLoading ? "Загрузка..." : "Охотничьих турниров нет на этой неделе"}
                    </p>
                  </div>
                )}
              </motion.div>
            )}

            {tab === "composite" && (
              <motion.div key="composite" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.2 }}>
                {compositeLoading ? (
                  <div className="flex justify-center py-12">
                    <Loader2 size={20} className="animate-spin" style={{ color: "var(--accent)" }} />
                  </div>
                ) : compositeEntries.length > 0 ? (
                  <div className="mt-6 space-y-2" role="list" aria-label="Комплексный рейтинг">
                    {/* Formula legend */}
                    <div className="glass-panel p-3 mb-4 flex flex-wrap gap-3 text-xs font-medium" style={{ color: "var(--text-muted)" }}>
                      <span className="badge-neon text-xs">40% Тренировки</span>
                      <span className="badge-neon text-xs">30% PvP</span>
                      <span className="badge-neon text-xs">20% Знания</span>
                      <span className="badge-neon text-xs">10% Серия</span>
                    </div>

                    {compositeEntries.map((entry) => {
                      const rankStyle = getRankStyle(entry.rank);
                      const isMe = entry.user_id === user?.id;
                      return (
                        <motion.div
                          key={entry.user_id}
                          role="listitem"
                          initial={{ opacity: 0, y: 8 }}
                          animate={{ opacity: 1, y: 0 }}
                          className={`cyber-card flex items-center gap-3 px-4 py-3 ${isMe ? "neon-pulse" : ""}`}
                          style={{
                            background: rankStyle.bg,
                            border: `1px solid ${rankStyle.border}`,
                            boxShadow: rankStyle.glow,
                          }}
                        >
                          <div className="w-8 text-center">{getRankIcon(entry.rank)}</div>
                          <UserAvatar fullName={entry.full_name} avatarUrl={entry.avatar_url} size={32} />
                          <div className="flex-1 min-w-0">
                            <div className="text-sm font-medium truncate" style={{ color: isMe ? "var(--accent)" : "var(--text-primary)" }}>
                              {entry.full_name}
                            </div>
                            <div className="flex gap-2 mt-1 flex-wrap">
                              <span className="stat-chip text-xs" style={{ color: "var(--accent)" }}>
                                T:{Math.round(entry.training_avg)}
                              </span>
                              <span className="stat-chip text-xs" style={{ color: "var(--success)" }}>
                                P:{Math.round(entry.pvp_rating_norm)}
                              </span>
                              <span className="stat-chip text-xs" style={{ color: "var(--warning)" }}>
                                K:{Math.round(entry.knowledge_score)}
                              </span>
                              <span className="stat-chip text-xs" style={{ color: "var(--warning)" }}>
                                S:{Math.round(entry.streak_bonus)}
                              </span>
                            </div>
                          </div>
                          <div className="text-right">
                            <div className="font-mono text-lg font-bold" style={{ color: "var(--accent)" }}>
                              {Math.round(entry.composite_score)}
                            </div>
                            <div className="text-xs" style={{ color: "var(--text-muted)" }}>очков</div>
                          </div>
                        </motion.div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="mt-16 flex flex-col items-center py-8">
                    <Zap size={32} style={{ color: "var(--text-muted)" }} />
                    <p className="mt-3 text-sm" style={{ color: "var(--text-muted)" }}>
                      Недостаточно данных для комплексного рейтинга
                    </p>
                  </div>
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
      {/* Create Tournament Modal */}
      <AnimatePresence>
        {showCreate && (
          <CreateTournamentModal
            onClose={() => setShowCreate(false)}
            onCreated={() => {
              setShowCreate(false);
              // Refresh tournament data
              api.get("/tournament/active")
                .then((data: ActiveTournamentResponse) => {
                  setTournament(data);
                  if (data.tournament) {
                    api.get(`/tournament/leaderboard/${data.tournament.id}`)
                      .then((lb: TournamentLeaderboardEntry[]) => setTournamentEntries(lb))
                      .catch((err) => { logger.error("Failed to reload tournament leaderboard:", err); });
                  }
                })
                .catch((err) => { logger.error("Failed to reload tournament data:", err); });
            }}
          />
        )}
      </AnimatePresence>
    </AuthLayout>
  );
}

/* ─── Create Tournament Modal ──────────────────────────────────────────────── */

function CreateTournamentModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [title, setTitle] = useState("");
  const [scenarioId, setScenarioId] = useState("");
  const [maxAttempts, setMaxAttempts] = useState(3);
  const [bonusFirst, setBonusFirst] = useState(500);
  const [bonusSecond, setBonusSecond] = useState(300);
  const [bonusThird, setBonusThird] = useState(150);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get("/scenarios/").then(setScenarios).catch((err) => { logger.error("Failed to load scenarios:", err); });
  }, []);

  const handleCreate = async () => {
    if (!title.trim() || !scenarioId) {
      setError("Укажите название и сценарий");
      return;
    }
    setCreating(true);
    setError("");
    try {
      await api.post("/tournament/create-weekly", {
        title: title.trim(),
        scenario_id: scenarioId,
        max_attempts: maxAttempts,
        bonus_xp_first: bonusFirst,
        bonus_xp_second: bonusSecond,
        bonus_xp_third: bonusThird,
      });
      onCreated();
    } catch (e) {
      setError((e as Error).message || "Ошибка создания");
    } finally {
      setCreating(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-[200] flex items-center justify-center"
      style={{ background: "rgba(0,0,0,0.7)" }}
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <motion.div
        initial={{ scale: 0.9, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.9, opacity: 0 }}
        className="glass-panel max-w-md w-full mx-4 p-6"
      >
        <div className="flex items-center justify-between mb-5">
          <h2 className="font-display text-lg font-bold flex items-center gap-2" style={{ color: "var(--text-primary)" }}>
            <Swords size={18} style={{ color: RANK.gold }} /> Новый турнир
          </h2>
          <button onClick={onClose} className="p-1 rounded-lg" style={{ color: "var(--text-muted)" }}>
            <XIcon size={18} />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="vh-label">Название</label>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Турнир недели: Скептики"
              className="vh-input w-full"
            />
          </div>

          <div>
            <label className="vh-label">Сценарий</label>
            <select
              value={scenarioId}
              onChange={(e) => setScenarioId(e.target.value)}
              className="vh-input w-full"
            >
              <option value="">Выберите сценарий...</option>
              {scenarios.map((s) => (
                <option key={s.id} value={s.id}>{s.title} ({s.difficulty}/10)</option>
              ))}
            </select>
          </div>

          <div>
            <label className="vh-label">Макс. попыток</label>
            <input
              type="number"
              value={maxAttempts}
              onChange={(e) => setMaxAttempts(Number(e.target.value))}
              min={1}
              max={10}
              className="vh-input w-full"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <label className="vh-label">🥇 XP</label>
              <input type="number" value={bonusFirst} onChange={(e) => setBonusFirst(Number(e.target.value))} className="vh-input w-full" />
            </div>
            <div>
              <label className="vh-label">🥈 XP</label>
              <input type="number" value={bonusSecond} onChange={(e) => setBonusSecond(Number(e.target.value))} className="vh-input w-full" />
            </div>
            <div>
              <label className="vh-label">🥉 XP</label>
              <input type="number" value={bonusThird} onChange={(e) => setBonusThird(Number(e.target.value))} className="vh-input w-full" />
            </div>
          </div>

          {error && (
            <p className="text-xs" style={{ color: "var(--danger)" }}>{error}</p>
          )}

          <motion.button
            onClick={handleCreate}
            disabled={creating}
            className="btn-neon w-full flex items-center justify-center gap-2"
            whileTap={{ scale: 0.98 }}
          >
            {creating ? <Loader2 size={16} className="animate-spin" /> : <><Swords size={16} /> Создать турнир</>}
          </motion.button>
        </div>
      </motion.div>
    </motion.div>
  );
}

/* ─── Shared Leaderboard List ──────────────────────────────────────────────── */

function LeaderboardList({
  loading,
  empty,
  emptyText = "Таблица пуста — займи первое место",
  items,
}: {
  loading: boolean;
  empty: boolean;
  emptyText?: string;
  items: { rank: number; userId: string; name: string; avatarUrl?: string | null; subtitle: string; score: number; scoreLabel: string }[];
}) {
  if (loading) {
    return (
      <LeaderboardSkeleton />
    );
  }

  if (empty) {
    return (
      <EmptyState
        icon={Trophy}
        title={emptyText}
        description="Пройдите охоту, чтобы попасть в рейтинг"
        hint="1 сессия — и вы среди охотников"
      />
    );
  }

  return (
    <div className="mt-6 space-y-3" role="list" aria-label="Рейтинг участников">
      {items.map((entry, i) => {
        const style = getRankStyle(entry.rank);
        return (
          <motion.div
            key={entry.userId}
            role="listitem"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
            className="cyber-card flex items-center gap-2 sm:gap-4 p-3 sm:p-4 transition-all relative overflow-hidden group"
            style={{
              background: style.bg,
              border: `1px solid ${style.border}`,
              boxShadow: style.glow,
            }}
            whileHover={{ y: -2, boxShadow: `0 4px 20px ${entry.rank <= 3 ? style.border : "rgba(99,102,241,0.1)"}` }}
          >
            {/* Rank accent bar — slides in on hover */}
            <div
              className="absolute left-0 top-0 bottom-0 w-0 group-hover:w-[3px] transition-all duration-300"
              style={{ background: entry.rank === 1 ? RANK.gold : entry.rank === 2 ? RANK.silver : entry.rank === 3 ? RANK.bronze : "var(--accent)" }}
            />
            <div className="flex items-center gap-2 sm:gap-3 shrink-0">
              <div className="flex h-7 w-7 sm:h-8 sm:w-8 items-center justify-center">
                {getRankIcon(entry.rank)}
              </div>
              <UserAvatar avatarUrl={entry.avatarUrl} fullName={entry.name} size={32} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="font-medium text-xs sm:text-sm truncate" style={{ color: "var(--text-primary)" }}>{entry.name}</div>
              <div className="mt-0.5 text-xs sm:text-xs truncate" style={{ color: "var(--text-muted)" }}>{entry.subtitle}</div>
            </div>
            <div className="text-right shrink-0">
              <div className="flex items-center gap-1">
                <TrendingUp size={12} style={{ color: entry.rank === 1 ? RANK.gold : entry.rank === 2 ? RANK.silver : entry.rank === 3 ? RANK.bronze : "var(--accent)" }} />
                <motion.span
                  className="font-display text-base sm:text-lg font-bold inline-block"
                  style={{ color: entry.rank === 1 ? RANK.gold : entry.rank === 2 ? RANK.silver : entry.rank === 3 ? RANK.bronze : "var(--accent)" }}
                  initial={{ scale: 0.8, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  transition={{ delay: i * 0.05 + 0.15, type: "spring", stiffness: 400, damping: 25 }}
                  whileHover={{ scale: 1.12 }}
                >
                  {entry.score}
                </motion.span>
              </div>
              <span className="text-xs sm:text-xs" style={{ color: "var(--text-muted)" }}>{entry.scoreLabel}</span>
            </div>
          </motion.div>
        );
      })}
    </div>
  );
}
