"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Trophy, Medal, Crown, TrendingUp, Loader2, Swords, Clock, Zap, Plus, X as XIcon } from "lucide-react";
import AuthLayout from "@/components/layout/AuthLayout";
import { UserAvatar } from "@/components/ui/UserAvatar";
import { api } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { hasRole } from "@/lib/guards";
import type { TournamentLeaderboardEntry, ActiveTournamentResponse, Scenario } from "@/types";

interface GamificationEntry {
  rank: number;
  user_id: string;
  full_name: string;
  avatar_url?: string | null;
  sessions_count: number;
  total_score: number;
  avg_score: number;
}

type Tab = "general" | "tournament";

function getRankIcon(rank: number) {
  if (rank === 1) return <Crown size={18} style={{ color: "#FFD700" }} />;
  if (rank === 2) return <Medal size={18} style={{ color: "#C0C0C0" }} />;
  if (rank === 3) return <Medal size={18} style={{ color: "#CD7F32" }} />;
  return <span className="font-mono text-sm font-bold" style={{ color: "var(--text-muted)" }}>{rank}</span>;
}

function getRankStyle(rank: number) {
  if (rank === 1) return { bg: "rgba(255,215,0,0.08)", border: "rgba(255,215,0,0.2)", glow: "0 0 15px rgba(255,215,0,0.15)" };
  if (rank === 2) return { bg: "rgba(192,192,192,0.06)", border: "rgba(192,192,192,0.15)", glow: "none" };
  if (rank === 3) return { bg: "rgba(205,127,50,0.06)", border: "rgba(205,127,50,0.15)", glow: "none" };
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

  // Create tournament modal
  const [showCreate, setShowCreate] = useState(false);

  // Fetch gamification leaderboard
  useEffect(() => {
    setLoading(true);
    api
      .get(`/gamification/leaderboard?period=${period}`)
      .then((data: GamificationEntry[]) => setEntries(data))
      .catch(() => setEntries([]))
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
            .catch(() => setTournamentEntries(data.leaderboard));
        }
      })
      .catch(() => {})
      .finally(() => setTournamentLoading(false));
  }, []);

  const TABS: { id: Tab; label: string; icon: React.ComponentType<{ size: number; style?: React.CSSProperties }> }[] = [
    { id: "general", label: "Общий", icon: Trophy },
    { id: "tournament", label: "Турнир", icon: Swords },
  ];

  return (
    <AuthLayout>
      <div className="relative panel-grid-bg min-h-screen">
        <div className="mx-auto max-w-3xl px-4 py-8">
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
            <div className="flex items-center gap-2">
              <Trophy size={20} style={{ color: "var(--accent)" }} />
              <h1 className="font-display text-2xl font-bold tracking-[0.15em]" style={{ color: "var(--text-primary)" }}>
                ЛИДЕРБОРД
              </h1>
            </div>
            <p className="mt-2 font-mono text-xs tracking-wider" style={{ color: "var(--text-muted)" }}>
              TOP HUNTERS · BEST SCORES
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
                  className="relative flex-1 flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 font-mono text-xs tracking-wider transition-colors"
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
                      <span className="flex h-2 w-2 rounded-full" style={{ background: "var(--neon-green, #00FF66)" }} />
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
                <div className="mt-6 flex gap-2">
                  {([
                    { key: "week", label: "Неделя" },
                    { key: "month", label: "Месяц" },
                    { key: "all", label: "Всё время" },
                  ] as const).map((p) => (
                    <motion.button
                      key={p.key}
                      onClick={() => setPeriod(p.key)}
                      className="rounded-lg px-4 py-2 font-mono text-xs tracking-wider transition-all"
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
                      className="vh-btn-primary flex items-center gap-2 text-xs"
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
                      style={{ background: "rgba(255,215,0,0.06)", border: "1px solid rgba(255,215,0,0.15)" }}
                    >
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl" style={{ background: "rgba(255,215,0,0.1)" }}>
                        <Swords size={18} style={{ color: "#FFD700" }} />
                      </div>
                      <div className="flex-1">
                        <div className="font-display text-sm font-bold" style={{ color: "var(--text-primary)" }}>
                          {tournament.tournament.title}
                        </div>
                        <div className="flex items-center gap-3 mt-1 font-mono text-[10px]" style={{ color: "var(--text-muted)" }}>
                          <span className="flex items-center gap-1">
                            <Clock size={10} /> {formatTimeLeft(tournament.tournament.week_end)}
                          </span>
                          <span className="flex items-center gap-1" style={{ color: "#FFD700" }}>
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
                      {tournamentLoading ? "Загрузка..." : "Нет активных турниров на этой неделе"}
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
                      .catch(() => {});
                  }
                })
                .catch(() => {});
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
    api.get("/scenarios/").then(setScenarios).catch(() => {});
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
            <Swords size={18} style={{ color: "#FFD700" }} /> Новый турнир
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

          <div className="grid grid-cols-3 gap-3">
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
            <p className="text-xs font-mono" style={{ color: "var(--neon-red, #FF3333)" }}>{error}</p>
          )}

          <motion.button
            onClick={handleCreate}
            disabled={creating}
            className="vh-btn-primary w-full flex items-center justify-center gap-2"
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
  emptyText = "Пока нет данных за этот период",
  items,
}: {
  loading: boolean;
  empty: boolean;
  emptyText?: string;
  items: { rank: number; userId: string; name: string; avatarUrl?: string | null; subtitle: string; score: number; scoreLabel: string }[];
}) {
  if (loading) {
    return (
      <div className="mt-6 flex flex-col items-center py-16">
        <Loader2 size={24} className="animate-spin" style={{ color: "var(--accent)" }} />
        <span className="mt-3 font-mono text-xs" style={{ color: "var(--text-muted)" }}>ЗАГРУЗКА...</span>
      </div>
    );
  }

  if (empty) {
    return (
      <div className="mt-6 flex flex-col items-center py-16">
        <Trophy size={32} style={{ color: "var(--text-muted)" }} />
        <p className="mt-3 font-mono text-xs" style={{ color: "var(--text-muted)" }}>{emptyText}</p>
      </div>
    );
  }

  return (
    <div className="mt-6 space-y-3">
      {items.map((entry, i) => {
        const style = getRankStyle(entry.rank);
        return (
          <motion.div
            key={entry.userId}
            initial={{ opacity: 0, x: -16 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.05 }}
            className="flex items-center gap-4 rounded-xl p-4 transition-all"
            style={{
              background: style.bg,
              border: `1px solid ${style.border}`,
              boxShadow: style.glow,
              backdropFilter: "blur(20px)",
            }}
            whileHover={{ y: -2, boxShadow: "0 4px 20px rgba(139,92,246,0.1)" }}
          >
            <div className="flex items-center gap-3">
              <div className="flex h-8 w-8 items-center justify-center shrink-0">
                {getRankIcon(entry.rank)}
              </div>
              <UserAvatar avatarUrl={entry.avatarUrl} fullName={entry.name} size={36} />
            </div>
            <div className="flex-1">
              <div className="font-medium text-sm" style={{ color: "var(--text-primary)" }}>{entry.name}</div>
              <div className="mt-0.5 font-mono text-[10px]" style={{ color: "var(--text-muted)" }}>{entry.subtitle}</div>
            </div>
            <div className="text-right">
              <div className="flex items-center gap-1">
                <TrendingUp size={12} style={{ color: "var(--accent)" }} />
                <span className="font-display text-lg font-bold" style={{ color: "var(--accent)" }}>
                  {entry.score}
                </span>
              </div>
              <span className="font-mono text-[10px]" style={{ color: "var(--text-muted)" }}>{entry.scoreLabel}</span>
            </div>
          </motion.div>
        );
      })}
    </div>
  );
}
