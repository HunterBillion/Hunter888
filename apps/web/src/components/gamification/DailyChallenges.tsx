"use client";

/**
 * Daily Challenges — shows today's challenges with progress.
 * Completing challenges gives XP multiplier.
 */

import { motion } from "framer-motion";
import { Flame, CheckCircle2, Circle, Trophy } from "lucide-react";

interface Challenge {
  id: string;
  title: string;
  description: string;
  progress: number;  // 0-1
  target: number;
  current: number;
  xp_reward: number;
  completed: boolean;
}

interface DailyChallengesProps {
  challenges: Challenge[];
  multiplier?: number;  // 1.0 - 1.5x
}

export default function DailyChallenges({
  challenges = [],
  multiplier = 1.0,
}: DailyChallengesProps) {
  const completed = challenges.filter((c) => c.completed).length;
  const total = challenges.length;

  return (
    <div className="rounded-xl bg-[var(--bg-secondary)] p-5">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Flame size={18} className="text-[var(--warning)]" />
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">Ежедневные задания</h3>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-[var(--text-muted)]">{completed}/{total}</span>
          {multiplier > 1 && (
            <span className="rounded-md bg-[var(--warning-muted)] px-1.5 py-0.5 text-xs font-bold text-[var(--warning)]">
              x{multiplier.toFixed(1)}
            </span>
          )}
        </div>
      </div>

      {/* Challenges */}
      {challenges.length === 0 ? (
        <div className="py-6 text-center">
          <Trophy size={32} className="mx-auto mb-2 text-[var(--text-muted)] opacity-30" />
          <p className="text-xs text-[var(--text-muted)]">Задания появятся после первой тренировки</p>
        </div>
      ) : (
        <div className="space-y-3">
          {challenges.map((c) => (
            <motion.div
              key={c.id}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className={`rounded-lg px-3 py-2.5 ${
                c.completed ? "bg-[var(--success-muted)]" : "bg-[var(--bg-tertiary)]"
              }`}
            >
              <div className="flex items-start gap-2.5">
                {c.completed ? (
                  <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-[var(--success)]" />
                ) : (
                  <Circle size={16} className="mt-0.5 shrink-0 text-[var(--text-muted)]" />
                )}
                <div className="flex-1">
                  <div className="flex items-center justify-between">
                    <p className={`text-sm font-medium ${c.completed ? "text-[var(--success)]" : "text-[var(--text-primary)]"}`}>
                      {c.title}
                    </p>
                    <span className="text-xs text-[var(--accent)]">+{c.xp_reward} XP</span>
                  </div>
                  <p className="mt-0.5 text-xs text-[var(--text-muted)]">{c.description}</p>
                  {!c.completed && (
                    <div className="mt-2 flex items-center gap-2">
                      <div className="h-1.5 flex-1 rounded-full bg-[var(--bg-secondary)]">
                        <div
                          className="h-full rounded-full bg-[var(--accent)] transition-all"
                          style={{ width: `${Math.min(100, c.progress * 100)}%` }}
                        />
                      </div>
                      <span className="text-xs text-[var(--text-muted)]">{c.current}/{c.target}</span>
                    </div>
                  )}
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
