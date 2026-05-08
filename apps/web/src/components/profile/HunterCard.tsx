"use client";

/**
 * 2026-05-08 (графическая полировка): glass-panel + rounded-2xl
 * заменены на пиксельный плоский стиль:
 *   - 3px solid border акцентом (rounded-sm — почти square corners)
 *   - аватар: square frame с 3px бордером (вместо rounded-2xl) + пиксельные инициалы
 *   - угловые «glow blobs» убраны — лишний шум на пиксельной странице
 *   - имя: font-pixel вместо font-display, размер 28-36px
 *   - метки роли/команды: пиксельные плашки 2px solid
 *   - level-ring остался, но обведён square фрагментом + текст font-pixel
 *   - XP-bar: square corners, пиксельный outline, неоновый glow
 */

import { motion } from "framer-motion";
import { Zap, Flame } from "lucide-react";
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
  methodologist: "РОП",  // legacy enum — retired 2026-04-26, displays as ROP for stale tokens
};

export function HunterCard({ user, stats, gamification, teamName }: HunterCardProps) {
  const level = gamification?.level ?? 1;
  const xpCurrent = gamification?.xp_current_level ?? 0;
  const xpNext = gamification?.xp_next_level ?? 100;
  const xpPct = xpNext > 0 ? Math.round((xpCurrent / xpNext) * 100) : 0;
  const streakDays = gamification?.streak_days ?? 0;

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
      className="relative overflow-hidden rounded-sm p-5 md:p-7"
      style={{
        background: "linear-gradient(135deg, rgba(8,5,18,0.9), rgba(16,12,28,0.95))",
        border: "3px solid var(--accent)",
        boxShadow: "0 0 18px var(--accent-glow), inset 0 0 12px rgba(167,139,250,0.18)",
      }}
    >
      {/* Пиксельный grid-фон — еле заметная сетка для аркадного ритма */}
      <div
        aria-hidden
        className="absolute inset-0 pointer-events-none"
        style={{
          backgroundImage: `
            repeating-linear-gradient(0deg, rgba(167,139,250,0.07) 0 1px, transparent 1px 28px),
            repeating-linear-gradient(90deg, rgba(167,139,250,0.07) 0 1px, transparent 1px 28px)
          `,
        }}
      />

      <div className="relative z-10 flex flex-col sm:flex-row sm:items-center gap-5 md:gap-6">
        {/* Левый блок: Аватар + Инфо */}
        <div className="flex items-center gap-4 md:gap-5 flex-1 min-w-0">
          {/* Square pixel avatar (вместо rounded-2xl) */}
          <div
            className="w-[88px] h-[88px] rounded-sm flex items-center justify-center font-pixel shrink-0"
            style={{
              background: "linear-gradient(135deg, var(--accent), rgba(167,139,250,0.6))",
              border: "3px solid #0b0b14",
              outline: "2px solid var(--accent)",
              outlineOffset: 0,
              boxShadow: "0 0 14px var(--accent-glow)",
              color: "#0b0b14",
              fontSize: 32,
              letterSpacing: "0.04em",
            }}
          >
            {initials}
          </div>

          <div className="min-w-0 flex-1">
            <h2
              className="font-pixel truncate"
              style={{
                color: "var(--text-primary)",
                fontSize: "clamp(24px, 3.5vw, 36px)",
                lineHeight: 1.05,
                textShadow: "0 0 8px var(--accent-glow)",
              }}
              title={user.full_name}
            >
              {user.full_name}
            </h2>
            <div className="flex items-center gap-2 mt-2 flex-wrap">
              <span
                className="rounded-sm px-2.5 py-1 font-pixel uppercase tracking-widest"
                style={{
                  background: "rgba(167,139,250,0.18)",
                  color: "var(--accent)",
                  border: "2px solid var(--accent)",
                  fontSize: 14,
                }}
              >
                {ROLE_LABELS[user.role] ?? user.role}
              </span>
              {teamName && (
                <span
                  className="rounded-sm px-2.5 py-1 font-pixel uppercase tracking-widest"
                  style={{
                    background: "rgba(255,255,255,0.04)",
                    color: "var(--text-muted)",
                    border: "1px dashed rgba(255,255,255,0.18)",
                    fontSize: 14,
                  }}
                >
                  {teamName}
                </span>
              )}
            </div>
            {streakDays > 0 && (
              <div
                className="inline-flex items-center gap-1.5 mt-3 px-2.5 py-1 rounded-sm"
                style={{
                  background: "rgba(251,146,60,0.12)",
                  border: "2px solid rgba(251,146,60,0.55)",
                }}
              >
                <Flame size={14} style={{ color: "#fb923c" }} />
                <span
                  className="font-pixel font-bold tabular-nums uppercase tracking-widest"
                  style={{ color: "#fb923c", fontSize: 14 }}
                >
                  {streakDays} ДН. СТРИК
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Правый блок: Square level «знак» (вместо круга) */}
        <div
          className="relative shrink-0 self-center flex flex-col items-center justify-center rounded-sm"
          style={{
            width: 96,
            height: 96,
            background: "rgba(167,139,250,0.08)",
            border: "3px solid var(--accent)",
            boxShadow: "0 0 14px var(--accent-glow)",
          }}
        >
          {/* progress border — обводка вокруг square, как «энергия XP» */}
          <svg
            viewBox="0 0 96 96"
            className="absolute inset-0"
            style={{ pointerEvents: "none" }}
          >
            <rect
              x="3" y="3" width="90" height="90"
              fill="none"
              stroke="var(--accent)"
              strokeWidth="3"
              strokeDasharray={360}
              strokeDashoffset={360 * (1 - xpPct / 100)}
              style={{
                filter: "drop-shadow(0 0 6px var(--accent-glow))",
                transition: "stroke-dashoffset 1s ease",
              }}
            />
          </svg>
          <div
            className="font-pixel uppercase tracking-widest"
            style={{ color: "var(--text-muted)", fontSize: 12, lineHeight: 1 }}
          >
            УР.
          </div>
          <div
            className="font-pixel font-black tabular-nums"
            style={{
              color: "var(--accent)",
              fontSize: 36,
              lineHeight: 1.0,
              marginTop: 2,
              textShadow: "0 0 8px var(--accent-glow)",
            }}
          >
            {level}
          </div>
        </div>
      </div>

      {/* XP Progress Bar — square corners, пиксельный outline */}
      <div className="relative z-10 mt-5">
        <div className="flex items-center justify-between mb-2">
          <span
            className="font-pixel uppercase tracking-widest tabular-nums"
            style={{ color: "var(--text-secondary)", fontSize: 14 }}
          >
            <Zap size={14} className="inline mr-1.5" style={{ color: "var(--accent)" }} />
            {xpCurrent.toLocaleString("ru-RU")} / {xpNext.toLocaleString("ru-RU")} XP
          </span>
          <span
            className="font-pixel uppercase tracking-widest"
            style={{ color: "var(--accent)", fontSize: 14 }}
          >
            УР. {level}
          </span>
        </div>
        <div
          className="h-4 rounded-sm overflow-hidden"
          style={{
            background: "rgba(0,0,0,0.45)",
            border: "2px solid rgba(167,139,250,0.4)",
          }}
        >
          <motion.div
            className="h-full rounded-sm"
            initial={{ width: 0 }}
            animate={{ width: `${xpPct}%` }}
            transition={{ duration: 1.2, ease: EASE_SNAP }}
            style={{
              background: "linear-gradient(90deg, var(--accent) 0%, rgba(255,210,80,0.9) 100%)",
              boxShadow: "0 0 10px var(--accent-glow)",
            }}
          />
        </div>
      </div>

      {/* Stats moved to ProgressGraph — no duplicate cards here */}
    </motion.div>
  );
}
