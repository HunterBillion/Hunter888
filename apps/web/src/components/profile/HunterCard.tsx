"use client";

import { motion } from "framer-motion";
import { Zap, Flame, Trophy, TrendingUp, Star } from "lucide-react";
import { AnimatedCounter } from "@/components/ui/AnimatedCounter";
import { scoreColor, colorAlpha } from "@/lib/utils";
import { EASE_SNAP } from "@/lib/constants";

interface HunterCardProps {
  user: { full_name: string; email: string; role: string };
  stats: { completed_sessions: number; avg_score: number | null; best_score: number | null } | null;
  gamification: {
    level: number;
    xp_current_level: number;
    xp_next_level: number;
    streak_days: number;
    total_xp: number;
  } | null;
  teamName?: string;
}

const ROLE_LABELS: Record<string, string> = {
  manager: "Менеджер",
  rop: "РОП",
  admin: "Администратор",
  methodologist: "Методолог",
};

export function HunterCard({ user, stats, gamification, teamName }: HunterCardProps) {
  const level = gamification?.level ?? 1;
  const xpCurrent = gamification?.xp_current_level ?? 0;
  const xpNext = gamification?.xp_next_level ?? 100;
  const xpPct = xpNext > 0 ? Math.round((xpCurrent / xpNext) * 100) : 0;
  const streakDays = gamification?.streak_days ?? 0;

  const firstName = user.full_name.split(" ")[0] || "Охотник";
  const initials = user.full_name
    .split(" ")
    .slice(0, 2)
    .map((s) => s[0])
    .join("")
    .toUpperCase();

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      className="relative overflow-hidden rounded-2xl p-8"
      style={{
        background: "linear-gradient(135deg, var(--glass-bg), var(--accent-muted))",
        border: "1px solid var(--accent-muted)",
        backdropFilter: "blur(24px) saturate(1.5)",
        boxShadow: "0 8px 32px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.05)",
      }}
    >
      {/* Corner glows */}
      <div className="absolute -top-20 -right-20 w-64 h-64 rounded-full pointer-events-none" style={{ background: "radial-gradient(circle, var(--accent-muted) 0%, transparent 70%)" }} />
      <div className="absolute -bottom-16 -left-16 w-48 h-48 rounded-full pointer-events-none" style={{ background: "radial-gradient(circle, var(--accent-muted) 0%, transparent 70%)" }} />

      <div className="relative z-10 flex flex-col sm:flex-row sm:items-center gap-6">
        {/* Left: Avatar + Info */}
        <div className="flex items-center gap-5 flex-1">
          {/* Avatar */}
          <div
            className="w-[80px] h-[80px] rounded-2xl flex items-center justify-center text-2xl font-bold text-white shrink-0"
            style={{
              background: "linear-gradient(135deg, var(--accent), var(--accent-glow))",
              boxShadow: "0 8px 32px var(--accent-glow), inset 0 1px 0 rgba(255,255,255,0.2)",
            }}
          >
            {initials}
          </div>

          <div className="min-w-0">
            <h2 className="font-display text-3xl font-black truncate" style={{ color: "var(--text-primary)" }}>
              {user.full_name}
            </h2>
            <div className="flex items-center gap-2 mt-1 flex-wrap">
              <span
                className="rounded-full px-3 py-1 text-sm font-mono font-semibold"
                style={{ background: "var(--accent-muted)", color: "var(--accent)" }}
              >
                {ROLE_LABELS[user.role] ?? user.role}
              </span>
              {teamName && (
                <span className="text-base" style={{ color: "var(--text-muted)" }}>
                  {teamName}
                </span>
              )}
            </div>
            {streakDays > 0 && (
              <div className="flex items-center gap-1 mt-2">
                <Flame size={14} style={{ color: "var(--streak-color)" }} />
                <span className="font-mono text-sm font-bold" style={{ color: "var(--streak-color)" }}>
                  {streakDays} дней streak
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Right: Level Ring */}
        <div className="relative shrink-0 self-center w-16 h-16 sm:w-[88px] sm:h-[88px]">
          <svg viewBox="0 0 88 88" className="w-full h-full rotate-[-90deg]">
            <circle cx="44" cy="44" r="38" fill="none" stroke="var(--accent-muted)" strokeWidth="5" />
            <circle
              cx="44" cy="44" r="38" fill="none"
              stroke="var(--accent)"
              strokeWidth="5"
              strokeLinecap="round"
              strokeDasharray={`${2 * Math.PI * 38}`}
              strokeDashoffset={`${2 * Math.PI * 38 * (1 - xpPct / 100)}`}
              style={{ filter: "drop-shadow(0 0 8px var(--accent-glow))", transition: "stroke-dashoffset 1s ease" }}
            />
          </svg>
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="font-display font-black text-2xl" style={{ color: "var(--accent)" }}>
              {level}
            </span>
          </div>
        </div>
      </div>

      {/* XP Progress Bar */}
      <div className="relative z-10 mt-6">
        <div className="flex items-center justify-between mb-2">
          <span className="font-mono text-sm font-semibold" style={{ color: "var(--text-secondary)" }}>
            <Zap size={16} className="inline mr-1" />
            {xpCurrent} / {xpNext} XP
          </span>
          <span className="font-mono text-sm font-semibold" style={{ color: "var(--accent)" }}>
            Level {level}
          </span>
        </div>
        <div className="h-3 rounded-full" style={{ background: "var(--input-bg)" }}>
          <motion.div
            className="h-full rounded-full"
            initial={{ width: 0 }}
            animate={{ width: `${xpPct}%` }}
            transition={{ duration: 1.2, ease: EASE_SNAP }}
            style={{ background: "var(--accent)", boxShadow: "0 0 8px var(--accent-glow)" }}
          />
        </div>
      </div>

      {/* Stats moved to ProgressGraph — no duplicate cards here */}
    </motion.div>
  );
}
