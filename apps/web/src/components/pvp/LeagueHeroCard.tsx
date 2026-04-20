"use client";

/**
 * LeagueHeroCard — Duolingo-style weekly-league hero widget for /pvp.
 *
 * Phase B (2026-04-20). Shows the player their current cohort position
 * prominently, with:
 *   • large tier badge + rank
 *   • promotion / demotion / safe zone indicator with live countdown to
 *     Sunday 23:59 reset
 *   • podium top-3 preview
 *   • weekly XP + CTA link to the full league page `/pvp/league`
 *
 * Data source: `GET /gamification/league/me` — already returns
 *   { tier, tier_name, rank, weekly_xp, standings[...],
 *     promotion_zone, demotion_zone, days_remaining }
 *
 * When the league hasn't been formed yet (Monday 08:00 cron hasn't run
 * or user is brand new) we show a gentle "формируется в понедельник"
 * empty state instead of hiding.
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

export function LeagueHeroCard() {
  const [data, setData] = useState<LeagueData | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchLeague = useCallback(async () => {
    try {
      const d = await api.get<LeagueData>("/gamification/league/me");
      setData(d);
    } catch (err) {
      logger.error("LeagueHeroCard fetch failed", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchLeague();
  }, [fetchLeague]);

  const palette = data ? TIER_PALETTE[data.tier] ?? TIER_PALETTE[0] : TIER_PALETTE[0];
  const zone = useMemo(
    () =>
      data
        ? zoneMeta(data.rank, data.promotion_zone, data.demotion_zone)
        : null,
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
  // Days remaining — backend gives float days; show rounded + hint.
  const days = Math.max(0, Math.round(data.days_remaining));
  const daysLabel =
    days === 0
      ? "сегодня сброс"
      : days === 1
        ? "1 день до сброса"
        : `${days} ${days < 5 ? "дня" : "дней"} до сброса`;

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
              <span className="text-xs font-mono ml-1" style={{ color: "var(--text-muted)" }}>
                · {data.weekly_xp} XP
              </span>
            </div>
          </div>
        </div>

        {/* ─ Zone + countdown ─ */}
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
          <div className="flex items-center gap-1.5 text-[11px] font-mono uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
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
                <Crown
                  size={14}
                  style={{
                    color:
                      p.rank === 1
                        ? "#facc15"
                        : p.rank === 2
                          ? "#cbd5e1"
                          : "#f59e0b",
                  }}
                />
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
                    style={{ color: p.is_me ? palette.accent : "var(--text-primary)" }}
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
      <div className="relative mt-4 flex items-center justify-between">
        <div className="hidden md:flex items-center gap-2 text-[11px] uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
          <span>промо: топ-{data.promotion_zone}</span>
          <span>·</span>
          <span>вылет: #{data.demotion_zone}+</span>
        </div>
        <div className="flex items-center gap-2">
          <Link
            href="/pvp/teams"
            className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-all"
            style={{
              background: "transparent",
              color: palette.accent,
              border: `1px solid ${palette.accent}55`,
            }}
            title="Лидерборд команд компании"
          >
            Команды
          </Link>
          <Link
            href="/pvp/league"
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
