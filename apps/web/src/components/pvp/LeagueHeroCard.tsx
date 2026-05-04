"use client";

/**
 * LeagueHeroCard — Duolingo-style weekly-league hero widget for /pvp.
 *
 * Phase B (2026-04-20). Phase C (2026-05-04): merged into /leaderboard
 * tabs. CTA buttons now deep-link into `/leaderboard?tab=league|teams`.
 *
 * Shows the player their current cohort position prominently:
 *   • tier badge + rank
 *   • promotion / demotion / safe zone indicator
 *   • days countdown to Sunday 23:59 reset (correct russian plurals)
 *   • 7-day sparkline of weekly_xp vs cohort median (live trajectory)
 *   • podium top-3 preview using same crown palette as /leaderboard
 *
 * Endpoints:
 *   GET /gamification/league/me       — tier/rank/standings
 *   GET /gamification/league/me/timeline — daily XP me vs cohort median
 */

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  Trophy,
  ChevronUp,
  ChevronDown,
  ShieldCheck,
  Clock,
  ArrowRight,
  Crown,
  Building2,
} from "lucide-react";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";

interface LeagueStanding {
  user_id: string;
  full_name: string;
  weekly_xp: number;
  rank: number;
  is_me: boolean;
  avatar_url?: string | null;
}

interface LeagueData {
  tier: number;
  tier_name: string;
  group_size: number;
  rank: number;
  weekly_xp: number;
  standings: LeagueStanding[];
  promotion_zone: number;
  demotion_zone: number;
  days_remaining: number;
  week_start?: string;
}

interface TimelinePoint {
  date: string;
  my_xp: number;
  median_xp: number;
}

interface TimelineData {
  week_start: string;
  days: TimelinePoint[];
  my_total: number;
  median_total: number;
  delta_vs_median: number;
}

const TIER_PALETTE: Record<
  number,
  { label: string; accent: string; glow: string; bg: string }
> = {
  0: {
    label: "Стажёр",
    accent: "#94a3b8",
    glow: "rgba(148,163,184,0.45)",
    bg: "rgba(148,163,184,0.08)",
  },
  1: {
    label: "Специалист",
    accent: "#4ade80",
    glow: "rgba(74,222,128,0.45)",
    bg: "rgba(74,222,128,0.08)",
  },
  2: {
    label: "Профессионал",
    accent: "#a78bfa",
    glow: "rgba(167,139,250,0.45)",
    bg: "rgba(167,139,250,0.08)",
  },
  3: {
    label: "Эксперт",
    accent: "#facc15",
    glow: "rgba(250,204,21,0.5)",
    bg: "rgba(250,204,21,0.08)",
  },
  4: {
    label: "Легенда",
    accent: "#fb923c",
    glow: "rgba(251,146,60,0.5)",
    bg: "rgba(251,146,60,0.08)",
  },
};

function pluralizeDays(days: number): string {
  if (days === 0) return "сегодня сброс";
  const abs = Math.abs(days);
  const mod10 = abs % 10;
  const mod100 = abs % 100;
  if (mod100 >= 11 && mod100 <= 14) return `${days} дней`;
  if (mod10 === 1) return `${days} день`;
  if (mod10 >= 2 && mod10 <= 4) return `${days} дня`;
  return `${days} дней`;
}

function zoneMeta(rank: number, promo: number, demo: number) {
  if (rank > 0 && rank <= promo) {
    return {
      label: "Зона повышения",
      sub: `top ${promo} повышаются`,
      color: "#4ade80",
      icon: ChevronUp,
    };
  }
  if (rank >= demo) {
    return {
      label: "Зона понижения",
      sub: `низ ${Math.max(0, demo - 1)} теряют лигу`,
      color: "#f87171",
      icon: ChevronDown,
    };
  }
  return {
    label: "Безопасная зона",
    sub: "держишь позицию",
    color: "#94a3b8",
    icon: ShieldCheck,
  };
}

/**
 * Tiny 7-point dual-line sparkline. Pure SVG, ~80x32. Shows me vs cohort
 * median as cumulative weekly XP. Filled area on `me` so the eye picks
 * the player's own trajectory immediately.
 */
function Sparkline({
  days,
  accent,
}: {
  days: TimelinePoint[];
  accent: string;
}) {
  const W = 96;
  const H = 32;
  const pad = 2;

  // Cumulative — gameification feel ("my line goes up").
  const cumMe: number[] = [];
  const cumMed: number[] = [];
  let me = 0;
  let med = 0;
  for (const p of days) {
    me += p.my_xp;
    med += p.median_xp;
    cumMe.push(me);
    cumMed.push(med);
  }
  const max = Math.max(1, ...cumMe, ...cumMed);

  const xAt = (i: number) =>
    pad + ((W - 2 * pad) * i) / Math.max(1, days.length - 1);
  const yAt = (v: number) => H - pad - ((H - 2 * pad) * v) / max;

  const linePath = (vals: number[]) =>
    vals
      .map((v, i) => `${i === 0 ? "M" : "L"} ${xAt(i).toFixed(2)} ${yAt(v).toFixed(2)}`)
      .join(" ");

  const areaPath = `${linePath(cumMe)} L ${xAt(cumMe.length - 1).toFixed(2)} ${H - pad} L ${pad} ${H - pad} Z`;

  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} aria-hidden>
      <path d={areaPath} fill={accent} opacity={0.18} />
      <path
        d={linePath(cumMed)}
        fill="none"
        stroke="#94a3b8"
        strokeWidth={1.25}
        strokeDasharray="2 2"
        opacity={0.7}
      />
      <path d={linePath(cumMe)} fill="none" stroke={accent} strokeWidth={1.75} />
    </svg>
  );
}

export function LeagueHeroCard() {
  const [data, setData] = useState<LeagueData | null>(null);
  const [timeline, setTimeline] = useState<TimelineData | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchAll = useCallback(async () => {
    try {
      const [d, t] = await Promise.all([
        api.get<LeagueData>("/gamification/league/me"),
        api.get<TimelineData>("/gamification/league/me/timeline").catch((err) => {
          logger.error("league timeline fetch failed", err);
          return null;
        }),
      ]);
      setData(d);
      setTimeline(t);
    } catch (err) {
      logger.error("LeagueHeroCard fetch failed", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  const palette = data ? TIER_PALETTE[data.tier] ?? TIER_PALETTE[0] : TIER_PALETTE[0];
  const zone = useMemo(
    () =>
      data ? zoneMeta(data.rank, data.promotion_zone, data.demotion_zone) : null,
    [data],
  );

  const podium = useMemo(
    () => (data?.standings ?? []).filter((s) => s.rank <= 3).slice(0, 3),
    [data],
  );

  if (loading) {
    return (
      <div
        className="rounded-2xl p-4"
        style={{
          background: "var(--bg-panel)",
          border: "1px solid var(--border-color)",
        }}
      >
        <div className="flex items-center gap-2 text-sm text-[var(--text-muted)]">
          <Trophy size={14} />
          <span>Загружаю недельную лигу…</span>
        </div>
      </div>
    );
  }

  if (!data || data.group_size === 0) {
    return (
      <div
        className="rounded-2xl p-4"
        style={{
          background: "var(--bg-panel)",
          border: "1px solid var(--border-color)",
        }}
      >
        <div className="flex items-center gap-2 text-sm text-[var(--text-muted)]">
          <Trophy size={14} />
          <span>Недельная лига формируется в понедельник 08:00.</span>
        </div>
      </div>
    );
  }

  const ZoneIcon = zone!.icon;
  const days = Math.max(0, Math.round(data.days_remaining));
  const daysLabel = days === 0 ? "сегодня сброс" : pluralizeDays(days);

  // Crown palette MUST match /leaderboard PodiumCard for visual continuity.
  const crownColor = (rank: number) =>
    rank === 1
      ? "var(--rank-gold, #F7D154)"
      : rank === 2
        ? "var(--rank-silver, #C8CDD3)"
        : "var(--rank-bronze, #C88A56)";

  const deltaSign = (timeline?.delta_vs_median ?? 0) >= 0 ? "+" : "";
  const deltaColor =
    (timeline?.delta_vs_median ?? 0) >= 0 ? "#4ade80" : "#f87171";

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
      className="relative overflow-hidden rounded-2xl p-4 md:p-5"
      style={{
        background: `linear-gradient(135deg, ${palette.bg} 0%, rgba(16,12,28,0.85) 60%, rgba(16,12,28,0.95) 100%)`,
        border: `1px solid ${palette.accent}33`,
        boxShadow: `0 20px 48px -22px ${palette.glow}, 0 0 0 1px ${palette.accent}14 inset`,
      }}
    >
      {/* Decorative glow */}
      <div
        aria-hidden
        className="pointer-events-none absolute -top-16 -right-16 h-48 w-48 rounded-full"
        style={{
          background: `radial-gradient(circle, ${palette.glow} 0%, transparent 65%)`,
          opacity: 0.45,
        }}
      />

      <div className="relative grid gap-4 md:grid-cols-[auto_1fr_auto] md:items-center">
        {/* ─ Tier badge + rank ─ */}
        <div className="flex items-center gap-3">
          <div
            className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl"
            style={{
              background: `${palette.accent}22`,
              border: `1px solid ${palette.accent}55`,
              boxShadow: `inset 0 0 18px ${palette.glow}`,
              color: palette.accent,
            }}
          >
            <Trophy size={26} />
          </div>
          <div>
            <div
              className="text-[10px] uppercase tracking-wider font-semibold"
              style={{ color: palette.accent }}
            >
              Недельная лига
            </div>
            <div
              className="text-xl md:text-2xl font-bold leading-tight"
              style={{ color: "var(--text-primary)" }}
            >
              {palette.label}
            </div>
            <div className="flex items-baseline gap-1.5">
              <span
                className="text-3xl md:text-4xl font-black font-display tabular-nums"
                style={{ color: palette.accent }}
              >
                #{data.rank}
              </span>
              <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                из {data.group_size}
              </span>
              <span
                className="text-xs font-mono ml-1"
                style={{ color: "var(--text-muted)" }}
              >
                · {data.weekly_xp} XP
              </span>
            </div>
          </div>
        </div>

        {/* ─ Zone + sparkline + countdown ─ */}
        <div className="md:pl-3 md:border-l md:border-white/5 md:ml-2 space-y-2">
          <div className="flex items-center gap-2">
            <ZoneIcon size={16} style={{ color: zone!.color }} />
            <span
              className="text-sm font-semibold"
              style={{ color: zone!.color }}
            >
              {zone!.label}
            </span>
          </div>
          <div className="text-xs" style={{ color: "var(--text-muted)" }}>
            {zone!.sub}
          </div>

          {timeline && timeline.days.length > 0 && (
            <div
              className="flex items-center gap-2 pt-1"
              title="Накопленный XP за неделю — ты vs медиана когорты"
            >
              <Sparkline days={timeline.days} accent={palette.accent} />
              <div className="leading-tight">
                <div
                  className="text-[10px] uppercase tracking-wider"
                  style={{ color: "var(--text-muted)" }}
                >
                  vs медиана
                </div>
                <div
                  className="text-sm font-mono font-semibold tabular-nums"
                  style={{ color: deltaColor }}
                >
                  {deltaSign}
                  {timeline.delta_vs_median} XP
                </div>
              </div>
            </div>
          )}

          <div
            className="flex items-center gap-1.5 text-[11px] font-mono uppercase tracking-widest"
            style={{ color: "var(--text-muted)" }}
          >
            <Clock size={11} />
            {daysLabel}
          </div>
        </div>

        {/* ─ Podium preview ─ */}
        <div className="hidden md:flex items-end gap-2 pr-1">
          {podium.length === 0 ? (
            <div className="text-xs text-[var(--text-muted)] italic">
              нет данных
            </div>
          ) : (
            podium.map((p) => (
              <div
                key={p.user_id}
                className="flex flex-col items-center w-[74px] text-center"
              >
                <Crown size={14} style={{ color: crownColor(p.rank) }} />
                <div
                  className="mt-1 rounded-lg px-1.5 py-1 w-full"
                  style={{
                    background: p.is_me ? palette.bg : "rgba(255,255,255,0.03)",
                    border: p.is_me
                      ? `1px solid ${palette.accent}55`
                      : "1px solid rgba(255,255,255,0.08)",
                  }}
                >
                  <div
                    className="text-[11px] font-semibold truncate"
                    style={{
                      color: p.is_me ? palette.accent : "var(--text-primary)",
                    }}
                  >
                    {p.full_name.split(" ")[0]}
                  </div>
                  <div
                    className="text-[10px] font-mono tabular-nums"
                    style={{ color: "var(--text-muted)" }}
                  >
                    {p.weekly_xp} XP
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* ─ CTA ─ */}
      <div className="relative mt-4 flex flex-wrap items-center justify-between gap-3">
        <div
          className="flex items-center gap-2 text-[11px] uppercase tracking-widest"
          style={{ color: "var(--text-muted)" }}
        >
          <span>промо: топ-{data.promotion_zone}</span>
          <span>·</span>
          <span>вылет: #{data.demotion_zone}+</span>
        </div>
        <div className="flex items-center gap-2">
          <Link
            href="/leaderboard?tab=teams"
            className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-all"
            style={{
              background: "transparent",
              color: palette.accent,
              border: `1px solid ${palette.accent}55`,
            }}
            title="Лидерборд офисов продаж"
          >
            <Building2 size={13} />
            Команды
          </Link>
          <Link
            href="/leaderboard?tab=league"
            className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-all"
            style={{
              background: palette.accent,
              color: "#0b0b14",
              boxShadow: `0 10px 20px -12px ${palette.glow}`,
            }}
          >
            Вся лига
            <ArrowRight size={13} />
          </Link>
        </div>
      </div>
    </motion.div>
  );
}
