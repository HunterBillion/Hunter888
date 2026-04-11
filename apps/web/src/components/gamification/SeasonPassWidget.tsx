"use client";

/**
 * Season Pass Widget — shows current season tier progress.
 * Tier 0-30, monthly reset. Rewards at milestones.
 */

import { motion } from "framer-motion";
import { Star, Gift, Lock } from "lucide-react";

interface SeasonTier {
  tier: number;
  name: string;
  xp_required: number;
  reward?: string;
  is_premium?: boolean;
}

const SEASON_TIERS: SeasonTier[] = [
  { tier: 1, name: "Старт", xp_required: 0 },
  { tier: 5, name: "Новичок", xp_required: 500, reward: "Рамка профиля: Бронза" },
  { tier: 10, name: "Практикант", xp_required: 1500, reward: "Титул: Упорный" },
  { tier: 15, name: "Специалист", xp_required: 3000, reward: "Эксклюзивный сценарий", is_premium: true },
  { tier: 20, name: "Эксперт", xp_required: 5000, reward: "Рамка профиля: Золото" },
  { tier: 25, name: "Мастер", xp_required: 8000, reward: "Титул: Мастер переговоров", is_premium: true },
  { tier: 30, name: "Легенда", xp_required: 12000, reward: "Уникальный аватар" },
];

interface SeasonPassWidgetProps {
  currentTier: number;
  currentXP: number;
  seasonName?: string;
  daysRemaining?: number;
  isPremium?: boolean;
}

export default function SeasonPassWidget({
  currentTier = 0,
  currentXP = 0,
  seasonName = "Сезон 1",
  daysRemaining = 30,
  isPremium = false,
}: SeasonPassWidgetProps) {
  const nextMilestone = SEASON_TIERS.find((t) => t.tier > currentTier) || SEASON_TIERS[SEASON_TIERS.length - 1];
  const prevMilestone = [...SEASON_TIERS].reverse().find((t) => t.tier <= currentTier) || SEASON_TIERS[0];
  const progress = nextMilestone.xp_required > prevMilestone.xp_required
    ? ((currentXP - prevMilestone.xp_required) / (nextMilestone.xp_required - prevMilestone.xp_required)) * 100
    : 100;

  return (
    <div className="rounded-xl bg-[var(--bg-secondary)] p-5">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Star size={18} className="text-[var(--warning)]" />
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">{seasonName}</h3>
        </div>
        <span className="text-xs text-[var(--text-muted)]">{daysRemaining} дней</span>
      </div>

      {/* Current tier */}
      <div className="mb-3 flex items-center justify-between">
        <span className="text-2xl font-bold text-[var(--accent)]">Тир {currentTier}</span>
        <span className="text-xs text-[var(--text-secondary)]">{currentXP} XP</span>
      </div>

      {/* Progress bar */}
      <div className="mb-4 h-2 w-full rounded-full bg-[var(--bg-tertiary)]">
        <motion.div
          className="h-full rounded-full bg-gradient-to-r from-[var(--accent)] to-[var(--warning)]"
          initial={{ width: 0 }}
          animate={{ width: `${Math.min(100, Math.max(0, progress))}%` }}
          transition={{ duration: 0.8, ease: "easeOut" }}
        />
      </div>

      {/* Next milestone */}
      <p className="mb-4 text-xs text-[var(--text-muted)]">
        До тира {nextMilestone.tier}: {Math.max(0, nextMilestone.xp_required - currentXP)} XP
      </p>

      {/* Milestones */}
      <div className="space-y-2">
        {SEASON_TIERS.filter((t) => t.reward).map((tier) => {
          const unlocked = currentTier >= tier.tier;
          const locked = tier.is_premium && !isPremium;
          return (
            <div
              key={tier.tier}
              className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm ${
                unlocked
                  ? "bg-[var(--success)]/10 text-[var(--text-primary)]"
                  : "bg-[var(--bg-tertiary)] text-[var(--text-muted)]"
              }`}
            >
              {unlocked ? (
                <Gift size={14} className="text-[var(--success)]" />
              ) : locked ? (
                <Lock size={14} className="text-[var(--warning)]" />
              ) : (
                <Star size={14} />
              )}
              <span className="flex-1">
                Тир {tier.tier}: {tier.reward}
              </span>
              {locked && !unlocked && (
                <span className="text-xs text-[var(--warning)]">Premium</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
