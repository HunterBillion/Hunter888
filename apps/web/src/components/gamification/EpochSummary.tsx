"use client";

/**
 * EpochSummary — flashback/dossiér shown when a user completes an epoch.
 * Displays: score over time, traps, PvP wins, chapter milestones.
 */

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Trophy, Star, Flame, Shield, Sword, X } from "lucide-react";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";
import { Button } from "@/components/ui/Button";

interface EpochStats {
  epoch: number;
  epoch_name: string;
  chapters_completed: number[];
  total_sessions: number;
  avg_score_start: number;
  avg_score_end: number;
  score_growth_pct: number;
  traps_encountered: number;
  traps_dodged: number;
  pvp_wins: number;
  pvp_losses: number;
  best_score: number;
  total_xp_earned: number;
  days_spent: number;
  milestones: string[];
}

const EPOCH_THEMES = [
  { name: "ПЕРВЫЕ ЗВОНКИ", color: "#22c55e", icon: Flame },
  { name: "МАСТЕРСТВО", color: "#f59e0b", icon: Shield },
  { name: "НАСТАВНИК", color: "var(--accent)", icon: Star },
  { name: "ЛЕГЕНДА", color: "#a855f7", icon: Trophy },
];

interface Props {
  epochId: number;
  onClose: () => void;
}

export default function EpochSummary({ epochId, onClose }: Props) {
  const [stats, setStats] = useState<EpochStats | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchStats = useCallback(async () => {
    try {
      const d = await api.get<EpochStats>(`/story/epoch-summary/${epochId}`);
      setStats(d);
    } catch (err) {
      logger.error("Failed to fetch epoch summary:", err);
    } finally {
      setLoading(false);
    }
  }, [epochId]);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  const theme = EPOCH_THEMES[epochId - 1] || EPOCH_THEMES[0];
  const EpochIcon = theme.icon;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
        onClick={onClose}
      >
        <motion.div
          initial={{ scale: 0.9, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.9, opacity: 0 }}
          transition={{ type: "spring", stiffness: 300, damping: 25 }}
          className="relative w-full max-w-lg rounded-2xl border border-[var(--border-color)] bg-[var(--bg-primary)] p-6 shadow-2xl"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Close button */}
          <button
            onClick={onClose}
            className="absolute top-4 right-4 text-[var(--text-muted)] hover:text-[var(--text-primary)]"
          >
            <X size={20} />
          </button>

          {/* Header */}
          <div className="text-center mb-6">
            <div
              className="inline-flex items-center justify-center w-16 h-16 rounded-full mb-3"
              style={{ backgroundColor: `${theme.color}20`, color: theme.color }}
            >
              <EpochIcon size={32} />
            </div>
            <h2 className="text-xl font-bold text-[var(--text-primary)]">
              Эпоха {epochId} завершена
            </h2>
            <p className="text-sm text-[var(--text-muted)] mt-1">
              {theme.name}
            </p>
          </div>

          {loading || !stats ? (
            <div className="text-center py-8 text-[var(--text-muted)]">Загрузка досье...</div>
          ) : (
            <div className="space-y-4">
              {/* Score growth — the hero stat */}
              <div
                className="rounded-xl p-4 text-center"
                style={{ backgroundColor: `${theme.color}10`, border: `1px solid ${theme.color}30` }}
              >
                <div className="text-3xl font-black" style={{ color: theme.color }}>
                  +{stats.score_growth_pct}%
                </div>
                <div className="text-xs text-[var(--text-muted)] mt-1">
                  Рост среднего балла: {stats.avg_score_start} → {stats.avg_score_end}
                </div>
              </div>

              {/* Stats grid */}
              <div className="grid grid-cols-2 gap-3">
                <StatCard
                  icon={<Flame size={16} />}
                  label="Сессий"
                  value={stats.total_sessions}
                  color={theme.color}
                />
                <StatCard
                  icon={<Trophy size={16} />}
                  label="Лучший балл"
                  value={stats.best_score}
                  color={theme.color}
                />
                <StatCard
                  icon={<Shield size={16} />}
                  label="Ловушек обезврежено"
                  value={`${stats.traps_dodged}/${stats.traps_encountered}`}
                  color={theme.color}
                />
                <StatCard
                  icon={<Sword size={16} />}
                  label="PvP побед"
                  value={`${stats.pvp_wins}/${stats.pvp_wins + stats.pvp_losses}`}
                  color={theme.color}
                />
              </div>

              {/* XP earned */}
              <div className="text-center text-sm text-[var(--text-muted)]">
                <span className="font-mono font-bold" style={{ color: "var(--warning)" }}>
                  +{stats.total_xp_earned.toLocaleString()} XP
                </span>
                {" за "}
                {stats.days_spent} дней
              </div>

              {/* Milestones */}
              {stats.milestones.length > 0 && (
                <div className="space-y-1">
                  <div className="text-xs font-medium text-[var(--text-secondary)] uppercase tracking-wider">
                    Достижения эпохи
                  </div>
                  {stats.milestones.map((m, i) => (
                    <div key={i} className="flex items-center gap-2 text-sm text-[var(--text-primary)]">
                      <Star size={12} style={{ color: theme.color }} />
                      {m}
                    </div>
                  ))}
                </div>
              )}

              <Button
                onClick={onClose}
                className="w-full mt-2"
                style={{ backgroundColor: theme.color }}
              >
                Продолжить путь
              </Button>
            </div>
          )}
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}

function StatCard({
  icon,
  label,
  value,
  color,
}: {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  color: string;
}) {
  return (
    <div className="rounded-lg border border-[var(--border-color)] bg-[var(--bg-secondary)] p-3">
      <div className="flex items-center gap-1.5 text-xs text-[var(--text-muted)] mb-1">
        <span style={{ color }}>{icon}</span>
        {label}
      </div>
      <div className="text-lg font-bold text-[var(--text-primary)]">{value}</div>
    </div>
  );
}
