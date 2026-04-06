"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Trophy, Shield, Loader2, TrendingUp, Crown, Medal, Plus } from "lucide-react";
import AuthLayout from "@/components/layout/AuthLayout";
import { usePvPStore } from "@/stores/usePvPStore";
import { useKnowledgeStore } from "@/stores/useKnowledgeStore";
import { RankBadge } from "@/components/pvp/RankBadge";
import { UserAvatar } from "@/components/ui/UserAvatar";
import { useAuth } from "@/hooks/useAuth";
import { EmptyState } from "@/components/ui/EmptyState";
import { hasRole } from "@/lib/guards";
import { api } from "@/lib/api";
import type { PvPRankTier } from "@/types";
import { PVP_RANK_LABELS, PVP_RANK_COLORS } from "@/types";

const ARENA_PERIODS = [
  { key: "all" as const, label: "Все время" },
  { key: "month" as const, label: "За месяц" },
  { key: "week" as const, label: "За неделю" },
];

const TIERS: { key: string; label: string }[] = [
  { key: "all", label: "Все" },
  { key: "diamond", label: "Алмаз" },
  { key: "platinum", label: "Платина" },
  { key: "gold", label: "Золото" },
  { key: "silver", label: "Серебро" },
  { key: "bronze", label: "Бронза" },
];

function getRankIcon(rank: number) {
  if (rank === 1) return <Crown size={18} style={{ color: "#FFD700" }} />;
  if (rank === 2) return <Medal size={18} style={{ color: "#C0C0C0" }} />;
  if (rank === 3) return <Medal size={18} style={{ color: "#CD7F32" }} />;
  return <span className="font-mono text-sm font-bold" style={{ color: "var(--text-muted)" }}>{rank}</span>;
}

export default function PvPLeaderboardPage() {
  const { user } = useAuth();
  const store = usePvPStore();
  const [tierFilter, setTierFilter] = useState("all");
  const isAdmin = hasRole(user, ["admin"]);

  useEffect(() => {
    store.fetchLeaderboard(tierFilter);
    store.fetchActiveSeason();
  }, [tierFilter]); // eslint-disable-line react-hooks/exhaustive-deps -- store actions are stable Zustand refs

  const handleCreateSeason = async () => {
    const name = prompt("Название сезона:");
    if (!name) return;
    try {
      const now = new Date();
      const end = new Date(now.getTime() + 30 * 86400000); // 30 days
      await api.post("/pvp/admin/season/create", {
        name,
        start_date: now.toISOString(),
        end_date: end.toISOString(),
        rewards: {
          diamond: { xp: 500, badge: "diamond_champion" },
          platinum: { xp: 300, badge: "platinum_hero" },
          gold: { xp: 150, badge: "gold_warrior" },
        },
      });
      store.fetchActiveSeason();
    } catch (e) {
      alert((e as Error).message);
    }
  };

  return (
    <AuthLayout>
      <div className="relative panel-grid-bg min-h-screen">
        <div className="mx-auto max-w-3xl px-4 py-8">
          {/* Header */}
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
            <div className="flex items-center justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <Trophy size={20} style={{ color: "var(--accent)" }} />
                  <h1 className="font-display text-2xl font-bold tracking-[0.15em]" style={{ color: "var(--text-primary)" }}>
                    PVP РЕЙТИНГ
                  </h1>
                </div>
                <p className="mt-1 font-mono text-xs tracking-wider" style={{ color: "var(--text-muted)" }}>
                  GLICKO-2 · {store.leaderboardTotal} ИГРОКОВ
                </p>
              </div>
              {isAdmin && (
                <motion.button
                  onClick={handleCreateSeason}
                  className="btn-neon flex items-center gap-2 text-xs"
                  whileTap={{ scale: 0.97 }}
                >
                  <Plus size={14} /> Новый сезон
                </motion.button>
              )}
            </div>
          </motion.div>

          {/* Season banner with countdown and rewards */}
          {store.activeSeason && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="mt-4 rounded-xl p-4"
              style={{ background: "linear-gradient(135deg, rgba(255,215,0,0.08), rgba(255,165,0,0.04))", border: "1px solid rgba(255,215,0,0.2)" }}
            >
              <div className="flex items-center gap-2 mb-2">
                <Shield size={16} style={{ color: "#FFD700" }} />
                <span className="text-sm font-bold" style={{ color: "#FFD700" }}>
                  {store.activeSeason.name}
                </span>
                {store.activeSeason.end_date && (
                  <span className="ml-auto text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                    До конца: {(() => {
                      const diff = new Date(store.activeSeason.end_date).getTime() - Date.now();
                      if (diff <= 0) return "Завершён";
                      const d = Math.floor(diff / 86400000);
                      return d > 0 ? `${d}д` : `${Math.floor(diff / 3600000)}ч`;
                    })()}
                  </span>
                )}
              </div>
              {/* Season rewards by tier */}
              {store.activeSeason.rewards && (
                <div className="flex gap-3 mt-2 text-xs font-mono flex-wrap">
                  {Object.entries(store.activeSeason.rewards as Record<string, { xp: number }>).map(([tier, reward]) => (
                    <span key={tier} style={{ color: "var(--text-muted)" }}>
                      {tier === "diamond" ? "\uD83D\uDC8E" : tier === "platinum" ? "\u2728" : "\uD83E\uDD47"}{" "}
                      {tier}: +{reward.xp} XP
                    </span>
                  ))}
                </div>
              )}
            </motion.div>
          )}

          {/* Tier filters — horizontal scroll on mobile */}
          <div className="mt-6 flex gap-2 overflow-x-auto pb-2 scrollbar-hide">
            {TIERS.map((t) => (
              <motion.button
                key={t.key}
                onClick={() => setTierFilter(t.key)}
                className="rounded-lg px-3 py-1.5 font-mono text-xs transition-all"
                style={{
                  background: tierFilter === t.key ? "var(--accent-muted)" : "var(--input-bg)",
                  border: `1px solid ${tierFilter === t.key ? "var(--accent)" : "var(--border-color)"}`,
                  color: tierFilter === t.key ? "var(--accent)" : "var(--text-muted)",
                }}
                whileTap={{ scale: 0.97 }}
              >
                {t.label}
              </motion.button>
            ))}
          </div>

          {/* Leaderboard */}
          {store.leaderboardLoading ? (
            <div className="mt-8 flex justify-center py-16">
              <Loader2 size={24} className="animate-spin" style={{ color: "var(--accent)" }} />
            </div>
          ) : store.leaderboard.length === 0 ? (
            <EmptyState
              icon={Trophy}
              title="Пока нет данных"
              description="Проведите первый PvP-бой, чтобы попасть в рейтинг"
              actionLabel="Начать бой"
              onAction={() => window.location.href = "/pvp"}
            />
          ) : (
            <div className="mt-6 space-y-3">
              {store.leaderboard.map((entry, i) => {
                const color = PVP_RANK_COLORS[entry.rank_tier as PvPRankTier] || "var(--text-muted)";
                const isTopThree = entry.rank <= 3;
                return (
                  <motion.div
                    key={entry.user_id}
                    initial={{ opacity: 0, x: -16 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.03 }}
                    className="flex items-center gap-4 rounded-xl p-4"
                    style={{
                      background: isTopThree ? `${color}08` : "var(--glass-bg)",
                      border: `1px solid ${isTopThree ? `${color}25` : "var(--glass-border)"}`,
                      boxShadow: entry.rank === 1 ? `0 0 15px ${color}15` : "none",
                      backdropFilter: "blur(20px)",
                    }}
                  >
                    <div className="flex items-center gap-3">
                      <div className="flex h-8 w-8 items-center justify-center">
                        {getRankIcon(entry.rank)}
                      </div>
                      <UserAvatar
                        avatarUrl={entry.avatar_url}
                        fullName={entry.username}
                        size={36}
                      />
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                          {entry.username}
                        </span>
                        <RankBadge tier={entry.rank_tier as PvPRankTier} size="sm" />
                      </div>
                      <div className="mt-0.5 font-mono text-xs" style={{ color: "var(--text-muted)" }}>
                        {entry.wins}W / {entry.losses}L · streak {entry.current_streak > 0 ? "+" : ""}{entry.current_streak}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="flex items-center gap-1">
                        <TrendingUp size={12} style={{ color }} />
                        <span className="font-display text-lg font-bold" style={{ color }}>
                          {Math.round(entry.rating)}
                        </span>
                      </div>
                    </div>
                  </motion.div>
                );
              })}
            </div>
          )}

          {/* Arena Knowledge Leaderboard */}
          <ArenaLeaderboardSection />
        </div>
      </div>
    </AuthLayout>
  );
}


function ArenaLeaderboardSection() {
  const kStore = useKnowledgeStore();
  const [period, setPeriod] = useState<"week" | "month" | "all">("all");

  useEffect(() => {
    kStore.fetchArenaLeaderboard(period);
  }, [period]); // eslint-disable-line react-hooks/exhaustive-deps -- kStore.fetchArenaLeaderboard is a stable Zustand action

  return (
    <div className="mt-12">
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
        <div className="flex items-center gap-2 mb-4">
          <Trophy size={20} style={{ color: "var(--accent)" }} />
          <h2 className="font-display text-xl font-bold tracking-[0.15em]" style={{ color: "var(--text-primary)" }}>
            АРЕНА ЗНАНИЙ
          </h2>
        </div>
      </motion.div>

      {/* Period tabs */}
      <div className="flex gap-2 flex-wrap">
        {ARENA_PERIODS.map((t) => (
          <motion.button
            key={t.key}
            onClick={() => setPeriod(t.key)}
            className="rounded-lg px-3 py-1.5 font-mono text-xs transition-all"
            style={{
              background: period === t.key ? "var(--accent-muted)" : "var(--input-bg)",
              border: `1px solid ${period === t.key ? "var(--accent)" : "var(--border-color)"}`,
              color: period === t.key ? "var(--accent)" : "var(--text-muted)",
            }}
            whileTap={{ scale: 0.97 }}
          >
            {t.label}
          </motion.button>
        ))}
      </div>

      {/* Arena leaderboard entries */}
      {kStore.arenaLeaderboardLoading ? (
        <div className="mt-6 flex justify-center py-10">
          <Loader2 size={24} className="animate-spin" style={{ color: "var(--accent)" }} />
        </div>
      ) : kStore.arenaLeaderboard.length === 0 ? (
        <EmptyState
          icon={Trophy}
          title="Пока нет данных"
          description="Пройдите первый тест в Арене знаний"
          actionLabel="К Арене"
          onAction={() => window.location.href = "/knowledge"}
        />
      ) : (
        <div className="mt-4 space-y-3">
          {kStore.arenaLeaderboard.map((entry, i) => (
            <motion.div
              key={entry.user_id}
              initial={{ opacity: 0, x: -16 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.03 }}
              className="flex items-center gap-4 rounded-xl p-4"
              style={{
                background: entry.rank <= 3 ? "rgba(255,215,0,0.04)" : "var(--glass-bg)",
                border: `1px solid ${entry.rank <= 3 ? "rgba(255,215,0,0.15)" : "var(--glass-border)"}`,
                backdropFilter: "blur(20px)",
              }}
            >
              <div className="flex h-8 w-8 items-center justify-center">
                {getRankIcon(entry.rank)}
              </div>
              <div className="flex-1">
                <span className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                  {entry.username}
                </span>
                {period === "all" && entry.rank_tier && (
                  <div className="mt-0.5 font-mono text-xs" style={{ color: "var(--text-muted)" }}>
                    {entry.wins ?? 0}W / {entry.losses ?? 0}L
                    {(entry.streak ?? 0) !== 0 && ` · streak ${(entry.streak ?? 0) > 0 ? "+" : ""}${entry.streak}`}
                  </div>
                )}
                {period !== "all" && (
                  <div className="mt-0.5 font-mono text-xs" style={{ color: "var(--text-muted)" }}>
                    {entry.sessions_count} сессий · avg {entry.avg_score}
                  </div>
                )}
              </div>
              <div className="text-right">
                {period === "all" ? (
                  <div className="flex items-center gap-1">
                    <TrendingUp size={12} style={{ color: "var(--accent)" }} />
                    <span className="font-display text-lg font-bold" style={{ color: "var(--accent)" }}>
                      {Math.round(entry.rating ?? 0)}
                    </span>
                  </div>
                ) : (
                  <span className="font-display text-lg font-bold" style={{ color: "var(--accent)" }}>
                    {Math.round(entry.total_score ?? 0)}
                  </span>
                )}
              </div>
            </motion.div>
          ))}
        </div>
      )}

      {/* User rank if not in top */}
      {kStore.arenaLeaderboardUserRank && (
        <div className="mt-3 rounded-xl p-3 text-center font-mono text-xs" style={{
          background: "var(--accent-muted)",
          border: "1px solid var(--accent)",
          color: "var(--accent)",
        }}>
          {`Вы: #${String((kStore.arenaLeaderboardUserRank as Record<string, unknown>)?.rank ?? "?")}`}
          {period === "all" && ` · ${Math.round(Number((kStore.arenaLeaderboardUserRank as Record<string, unknown>)?.rating) || 0)} ELO`}
          {period !== "all" && ` · ${Math.round(Number((kStore.arenaLeaderboardUserRank as Record<string, unknown>)?.total_score) || 0)} очков`}
        </div>
      )}
    </div>
  );
}
