"use client";

/**
 * HeroPanel — большая «карточка героя» в стиле выбора персонажа из
 * файтинга. Показывает аватар пользователя (`users.me.avatar_url`),
 * лигу/класс/ранг + ключевые цифры (TP/HS/ELO/XP).
 *
 * 2026-05-08 — часть аркадного редизайна /leaderboard. Заменяет блок
 * <h1>Лидерборд</h1> + описание, который пользователь явно попросил
 * убрать как «мусор».
 *
 * Источник данных: один параллельный fetch:
 *   - /gamification/league/me            → tier, rank, weekly_xp, days_remaining
 *   - /gamification/leaderboard/my-breakdown → training/pvp/knowledge/story/total
 *   - /users/me/profile                  → full_name, avatar_url, total_sessions
 *
 * Геометрия:
 *   - 2-колоночная сетка: [192px avatar] [гибкая инфо-зона]
 *   - на mobile стек, аватар крупный сверху
 *   - все шрифты ≥ 14px (требование пользователя)
 *   - пиксельный бордер 4px + glow + анимированная подсветка ранга
 *
 * Пользователь явно попросил **margin-bottom: 152px (4 см)** под этой
 * панелью. Применено через `mb-[152px]`. Зачем — пока неизвестно (в
 * памяти MEMORY/leaderboard_4cm_padding.md), при следующей реплике
 * напомнить пользователю объяснить.
 */

import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Trophy, Crown, Sword, Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";
import { useAuth } from "@/hooks/useAuth";

interface LeagueMe {
  tier: number;
  tier_name: string;
  rank: number;
  group_size: number;
  weekly_xp: number;
  days_remaining: number;
  promotion_zone: number;
  demotion_zone: number;
}

interface MyBreakdown {
  training: number;
  pvp: number;
  knowledge: number;
  story: number;
  total: number;
}

interface UserProfile {
  full_name: string;
  avatar_url: string | null;
  total_sessions: number;
  avg_score: number | null;
  team_name: string | null;
}

const TIER_PALETTE: Record<
  number,
  { label: string; accent: string; glow: string }
> = {
  0: { label: "Стажёр",        accent: "#94a3b8", glow: "rgba(148,163,184,0.55)" },
  1: { label: "Специалист",    accent: "#4ade80", glow: "rgba(74,222,128,0.55)" },
  2: { label: "Профессионал",  accent: "#a78bfa", glow: "rgba(167,139,250,0.55)" },
  3: { label: "Эксперт",       accent: "#facc15", glow: "rgba(250,204,21,0.6)" },
  4: { label: "Легенда",       accent: "#fb923c", glow: "rgba(251,146,60,0.6)" },
};

function getInitials(name?: string | null): string {
  if (!name) return "??";
  const parts = name.trim().split(/\s+/);
  return parts
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? "")
    .join("") || "??";
}

function ruDays(days: number): string {
  if (days <= 0) return "сегодня сброс";
  const abs = Math.abs(days);
  const mod10 = abs % 10;
  const mod100 = abs % 100;
  if (mod100 >= 11 && mod100 <= 14) return `${days} дней`;
  if (mod10 === 1) return `${days} день`;
  if (mod10 >= 2 && mod10 <= 4) return `${days} дня`;
  return `${days} дней`;
}

export function HeroPanel() {
  const { user } = useAuth();
  const [league, setLeague] = useState<LeagueMe | null>(null);
  const [breakdown, setBreakdown] = useState<MyBreakdown | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [l, b, p] = await Promise.all([
          api.get<LeagueMe>("/gamification/league/me").catch(() => null),
          api.get<MyBreakdown>("/gamification/leaderboard/my-breakdown").catch(
            () => null,
          ),
          api.get<UserProfile>("/users/me/profile").catch(() => null),
        ]);
        if (!cancelled) {
          setLeague(l);
          setBreakdown(b);
          setProfile(p);
          setLoaded(true);
        }
      } catch (e) {
        logger.error("HeroPanel fetch failed", e);
        if (!cancelled) setLoaded(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const palette = useMemo(
    () => (league ? TIER_PALETTE[league.tier] ?? TIER_PALETTE[0] : TIER_PALETTE[0]),
    [league],
  );

  const fullName =
    profile?.full_name || user?.full_name || user?.email?.split("@")[0] || "Игрок";
  const avatarUrl = profile?.avatar_url || user?.avatar_url || null;
  const totalSessions = profile?.total_sessions ?? 0;
  const avgScore = profile?.avg_score ?? null;
  const teamName = profile?.team_name ?? "—";

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: "easeOut" }}
      className="relative overflow-hidden rounded-md p-5 md:p-6 mb-[152px]"
      style={{
        background: `linear-gradient(135deg, rgba(8,5,18,0.92) 0%, rgba(16,12,28,0.85) 60%, rgba(${
          palette.accent === "#a78bfa" ? "30,20,50" : "20,15,30"
        },0.95) 100%)`,
        border: `4px solid ${palette.accent}`,
        boxShadow: `0 0 28px ${palette.glow}, inset 0 0 12px ${palette.accent}33`,
        // Пиксельная отрисовка бордера — никаких сглаживаний.
        imageRendering: "pixelated",
      }}
    >
      {/* Декоративный фон — пиксельная сетка */}
      <div
        aria-hidden
        className="absolute inset-0 pointer-events-none"
        style={{
          backgroundImage: `
            repeating-linear-gradient(0deg, ${palette.accent}11 0 1px, transparent 1px 32px),
            repeating-linear-gradient(90deg, ${palette.accent}11 0 1px, transparent 1px 32px)
          `,
          opacity: 0.6,
        }}
      />

      <div className="relative grid grid-cols-1 md:grid-cols-[180px_1fr] gap-5 md:gap-6 items-center">
        {/* Аватар (192px) */}
        <div className="flex justify-center md:justify-start">
          <div
            className="relative"
            style={{ width: 180, height: 180 }}
          >
            <div
              className="absolute inset-0 rounded-md overflow-hidden"
              style={{
                border: `4px solid ${palette.accent}`,
                boxShadow: `0 0 18px ${palette.glow}`,
                background: "rgba(0,0,0,0.4)",
              }}
            >
              {avatarUrl ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={avatarUrl}
                  alt={fullName}
                  width={180}
                  height={180}
                  style={{
                    width: "100%",
                    height: "100%",
                    objectFit: "cover",
                    imageRendering: "auto",
                  }}
                />
              ) : (
                <div
                  className="w-full h-full flex items-center justify-center font-pixel"
                  style={{
                    fontSize: 64,
                    color: palette.accent,
                    background: `linear-gradient(135deg, ${palette.accent}22, transparent)`,
                  }}
                >
                  {getInitials(fullName)}
                </div>
              )}
            </div>
            {/* Плашка ранга на аватаре */}
            {league && (
              <motion.div
                animate={{ boxShadow: [
                  `0 0 8px ${palette.glow}`,
                  `0 0 18px ${palette.glow}`,
                  `0 0 8px ${palette.glow}`,
                ] }}
                transition={{ duration: 2.5, repeat: Infinity }}
                className="absolute -bottom-3 -right-3 px-3 py-1.5 rounded-sm font-pixel"
                style={{
                  background: palette.accent,
                  color: "#0b0b14",
                  fontSize: 18,
                  border: "3px solid #0b0b14",
                  letterSpacing: "0.05em",
                }}
              >
                #{league.rank}
              </motion.div>
            )}
          </div>
        </div>

        {/* Инфо-зона */}
        <div className="flex flex-col gap-3 min-w-0">
          {/* Имя + класс */}
          <div>
            <div
              className="font-pixel uppercase tracking-widest"
              style={{
                color: palette.accent,
                fontSize: 14,
                letterSpacing: "0.18em",
              }}
            >
              ▰ ИГРОК ▰
            </div>
            <h2
              className="font-pixel truncate"
              style={{
                color: "var(--text-primary)",
                fontSize: "clamp(28px, 4vw, 40px)",
                lineHeight: 1.05,
                marginTop: 2,
                textShadow: `0 0 8px ${palette.glow}`,
              }}
            >
              {fullName}
            </h2>
            <div
              className="flex flex-wrap items-baseline gap-x-4 gap-y-1 mt-2"
              style={{ fontSize: 14 }}
            >
              <span
                className="font-pixel uppercase tracking-widest"
                style={{ color: palette.accent }}
              >
                КЛАСС: {league?.tier_name ?? palette.label}
              </span>
              <span
                className="font-pixel uppercase tracking-widest"
                style={{ color: "var(--text-muted)" }}
              >
                КОМАНДА: {teamName}
              </span>
            </div>
          </div>

          {/* Стат-бар */}
          <div
            className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-2"
            style={{ minHeight: 64 }}
          >
            <StatCell
              icon={<Trophy size={16} />}
              label="XP за неделю"
              value={league?.weekly_xp ?? 0}
              accent={palette.accent}
            />
            <StatCell
              icon={<Crown size={16} />}
              label="Hunter Score"
              value={breakdown?.total ?? 0}
              accent={palette.accent}
            />
            <StatCell
              icon={<Sword size={16} />}
              label="Сессии"
              value={totalSessions}
              accent={palette.accent}
            />
            <StatCell
              icon={<Sparkles size={16} />}
              label="Ср. балл"
              value={avgScore !== null ? avgScore.toFixed(1) : "—"}
              accent={palette.accent}
            />
          </div>

          {/* Footer-строка про сезон + сброс */}
          <div
            className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-1 font-pixel uppercase tracking-widest"
            style={{ color: "var(--text-muted)", fontSize: 14 }}
          >
            {league && (
              <>
                <span>
                  В когорте: <span style={{ color: palette.accent }}>#{league.rank} / {league.group_size}</span>
                </span>
                <span aria-hidden>·</span>
                <span>
                  Сброс лиги: <span style={{ color: palette.accent }}>{ruDays(league.days_remaining)}</span>
                </span>
              </>
            )}
            {!league && loaded && (
              <span>Лига формируется в понедельник</span>
            )}
          </div>
        </div>
      </div>
    </motion.div>
  );
}

function StatCell({
  icon,
  label,
  value,
  accent,
}: {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  accent: string;
}) {
  return (
    <div
      className="rounded-sm p-2"
      style={{
        background: "rgba(0,0,0,0.45)",
        border: `1px solid ${accent}55`,
      }}
    >
      <div
        className="font-pixel uppercase tracking-widest flex items-center gap-1.5"
        style={{ color: accent, fontSize: 14, lineHeight: 1.1 }}
      >
        <span style={{ opacity: 0.85 }}>{icon}</span>
        {label}
      </div>
      <div
        className="font-pixel tabular-nums"
        style={{
          color: "var(--text-primary)",
          fontSize: 24,
          lineHeight: 1.05,
          marginTop: 2,
        }}
      >
        {value}
      </div>
    </div>
  );
}
