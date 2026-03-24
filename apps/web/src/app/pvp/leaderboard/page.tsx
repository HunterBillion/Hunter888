"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Trophy, Shield, Loader2, TrendingUp, Crown, Medal, Plus } from "lucide-react";
import AuthLayout from "@/components/layout/AuthLayout";
import { usePvPStore } from "@/stores/usePvPStore";
import { RankBadge } from "@/components/pvp/RankBadge";
import { UserAvatar } from "@/components/ui/UserAvatar";
import { useAuth } from "@/hooks/useAuth";
import { EmptyState } from "@/components/ui/EmptyState";
import { hasRole } from "@/lib/guards";
import { api } from "@/lib/api";
import type { PvPRankTier } from "@/types";
import { PVP_RANK_LABELS, PVP_RANK_COLORS } from "@/types";

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
  }, [tierFilter]); // eslint-disable-line react-hooks/exhaustive-deps

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
                  className="vh-btn-primary flex items-center gap-2 text-xs"
                  whileTap={{ scale: 0.97 }}
                >
                  <Plus size={14} /> Новый сезон
                </motion.button>
              )}
            </div>
          </motion.div>

          {/* Season banner */}
          {store.activeSeason && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="mt-4 rounded-xl p-3 flex items-center gap-3"
              style={{ background: "rgba(255,215,0,0.06)", border: "1px solid rgba(255,215,0,0.15)" }}
            >
              <Shield size={16} style={{ color: "#FFD700" }} />
              <span className="text-sm" style={{ color: "var(--text-secondary)" }}>
                {store.activeSeason.name}
              </span>
            </motion.div>
          )}

          {/* Tier filters */}
          <div className="mt-6 flex gap-2 flex-wrap">
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
                      <div className="mt-0.5 font-mono text-[10px]" style={{ color: "var(--text-muted)" }}>
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
        </div>
      </div>
    </AuthLayout>
  );
}
