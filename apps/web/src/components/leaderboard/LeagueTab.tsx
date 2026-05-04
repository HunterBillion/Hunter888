"use client";

/**
 * LeagueTab — main "my weekly league" view in /leaderboard.
 *
 * 2026-05-04 v2: redesigned per user feedback. Now matches the visual
 * weight of the other tabs — adds a real podium (PodiumCard), keeps the
 * sparkline (me vs cohort median), unified crown palette, polls only
 * when the tab is visible.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import {
  Trophy,
  Crown,
  ChevronUp,
  ChevronDown,
  ShieldCheck,
  Clock,
  Loader2,
  Sparkles,
  TrendingUp,
} from "lucide-react";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";
import { useNotificationStore } from "@/stores/useNotificationStore";
import { PodiumCard, type PodiumEntry } from "@/components/leaderboard/PodiumCard";

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
}

interface TimelineData {
  days: { date: string; my_xp: number; median_xp: number }[];
  my_total: number;
  median_total: number;
  delta_vs_median: number;
}

const TIER_PALETTE: Record<
  number,
  { label: string; accent: string; glow: string; bg: string }
> = {
  0: { label: "Стажёр", accent: "#94a3b8", glow: "rgba(148,163,184,0.45)", bg: "rgba(148,163,184,0.08)" },
  1: { label: "Специалист", accent: "#4ade80", glow: "rgba(74,222,128,0.45)", bg: "rgba(74,222,128,0.08)" },
  2: { label: "Профессионал", accent: "#a78bfa", glow: "rgba(167,139,250,0.45)", bg: "rgba(167,139,250,0.08)" },
  3: { label: "Эксперт", accent: "#facc15", glow: "rgba(250,204,21,0.5)", bg: "rgba(250,204,21,0.08)" },
  4: { label: "Легенда", accent: "#fb923c", glow: "rgba(251,146,60,0.5)", bg: "rgba(251,146,60,0.08)" },
};

export function pluralizeDays(days: number): string {
  if (days === 0) return "сегодня сброс";
  const abs = Math.abs(days);
  const mod10 = abs % 10;
  const mod100 = abs % 100;
  if (mod100 >= 11 && mod100 <= 14) return `${days} дней`;
  if (mod10 === 1) return `${days} день`;
  if (mod10 >= 2 && mod10 <= 4) return `${days} дня`;
  return `${days} дней`;
}

function Sparkline({ days, accent }: { days: TimelineData["days"]; accent: string }) {
  const W = 140;
  const H = 38;
  const pad = 3;
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
  const xAt = (i: number) => pad + ((W - 2 * pad) * i) / Math.max(1, days.length - 1);
  const yAt = (v: number) => H - pad - ((H - 2 * pad) * v) / max;
  const line = (vals: number[]) =>
    vals.map((v, i) => `${i === 0 ? "M" : "L"} ${xAt(i).toFixed(1)} ${yAt(v).toFixed(1)}`).join(" ");
  const area = `${line(cumMe)} L ${xAt(cumMe.length - 1).toFixed(1)} ${H - pad} L ${pad} ${H - pad} Z`;
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} aria-hidden>
      <path d={area} fill={accent} opacity={0.18} />
      <path d={line(cumMed)} fill="none" stroke="#94a3b8" strokeWidth={1.25} strokeDasharray="2 2" opacity={0.7} />
      <path d={line(cumMe)} fill="none" stroke={accent} strokeWidth={1.75} />
    </svg>
  );
}

function zoneMeta(rank: number, promo: number, demo: number) {
  if (rank > 0 && rank <= promo) {
    return { label: "Зона повышения", sub: `top ${promo} повышаются`, color: "#4ade80", icon: ChevronUp };
  }
  if (rank >= demo) {
    return { label: "Зона понижения", sub: `низ ${Math.max(0, demo - 1)} теряют лигу`, color: "#f87171", icon: ChevronDown };
  }
  return { label: "Безопасная зона", sub: "держишь позицию", color: "#94a3b8", icon: ShieldCheck };
}

export function LeagueTab() {
  const [data, setData] = useState<LeagueData | null>(null);
  const [timeline, setTimeline] = useState<TimelineData | null>(null);
  const [loading, setLoading] = useState(true);
  const mountedRef = useRef(true);

  const fetch = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const [d, t] = await Promise.all([
        api.get<LeagueData>("/gamification/league/me"),
        api.get<TimelineData>("/gamification/league/me/timeline").catch((err) => {
          logger.error("league timeline fetch failed", err);
          return null;
        }),
      ]);
      if (mountedRef.current) {
        setData(d);
        setTimeline(t);
      }
    } catch (e) {
      logger.error("league fetch failed", e);
      if (!silent) {
        useNotificationStore.getState().addToast({
          type: "error",
          title: "Не удалось загрузить лигу",
          body: "Проверь соединение и обнови страницу.",
        });
      }
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    fetch();
    const onVisibility = () => {
      if (document.visibilityState === "visible") fetch(true);
    };
    const int = setInterval(onVisibility, 45_000);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      mountedRef.current = false;
      clearInterval(int);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [fetch]);

  const palette = data ? TIER_PALETTE[data.tier] ?? TIER_PALETTE[0] : TIER_PALETTE[0];
  const days = Math.max(0, Math.round(data?.days_remaining ?? 0));
  const standings = useMemo(
    () => [...(data?.standings ?? [])].sort((a, b) => a.rank - b.rank),
    [data],
  );
  const podium: PodiumEntry[] = useMemo(
    () =>
      standings
        .filter((s) => s.rank <= 3)
        .map((s) => ({
          user_id: s.user_id,
          full_name: s.full_name,
          avatar_url: s.avatar_url ?? null,
          score: s.weekly_xp,
          scoreUnit: "XP",
        })),
    [standings],
  );
  const zone = data ? zoneMeta(data.rank, data.promotion_zone, data.demotion_zone) : null;

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 size={24} className="animate-spin" style={{ color: palette.accent }} />
      </div>
    );
  }

  if (!data || data.group_size === 0) {
    // Empty state CTA — actionable, not a dead-end "никого нет" message.
    return (
      <div
        className="rounded-2xl p-8 text-center"
        style={{
          background: `linear-gradient(135deg, ${palette.bg} 0%, var(--bg-panel) 100%)`,
          border: `1px solid ${palette.accent}33`,
        }}
      >
        <div
          className="inline-flex h-14 w-14 items-center justify-center rounded-2xl mb-3"
          style={{ background: `${palette.accent}22`, color: palette.accent }}
        >
          <Trophy size={26} />
        </div>
        <h2
          className="text-lg font-semibold mb-1"
          style={{ color: "var(--text-primary)" }}
        >
          Лига формируется в понедельник 08:00
        </h2>
        <p className="text-sm mb-4 max-w-md mx-auto" style={{ color: "var(--text-muted)" }}>
          Когорта из ~15 игроков подбирается по уровню и команде. Пока что —
          играй тренировку, чтобы накопить XP к следующему сбросу.
        </p>
        <a
          href="/training"
          className="inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-semibold"
          style={{ background: palette.accent, color: "#0b0b14" }}
        >
          <Sparkles size={14} />
          Начать тренировку
        </a>
      </div>
    );
  }

  const ZoneIcon = zone!.icon;
  const deltaSign = (timeline?.delta_vs_median ?? 0) >= 0 ? "+" : "";
  const deltaColor = (timeline?.delta_vs_median ?? 0) >= 0 ? "#4ade80" : "#f87171";

  return (
    <div className="space-y-5">
      {/* Hero */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="relative overflow-hidden rounded-2xl p-5 md:p-6"
        style={{
          background: `linear-gradient(135deg, ${palette.bg} 0%, rgba(16,12,28,0.85) 55%, rgba(16,12,28,0.95) 100%)`,
          border: `1px solid ${palette.accent}33`,
        }}
      >
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div
              className="flex h-14 w-14 items-center justify-center rounded-2xl"
              style={{
                background: `${palette.accent}22`,
                border: `1px solid ${palette.accent}55`,
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
                className="text-2xl md:text-3xl font-bold"
                style={{ color: "var(--text-primary)" }}
              >
                {data.tier_name}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-5">
            <div className="text-center">
              <div
                className="text-[10px] uppercase tracking-wider"
                style={{ color: "var(--text-muted)" }}
              >
                Твоя позиция
              </div>
              <div
                className="text-3xl md:text-4xl font-black tabular-nums"
                style={{ color: palette.accent }}
              >
                #{data.rank}
              </div>
              <div className="text-xs" style={{ color: "var(--text-muted)" }}>
                из {data.group_size} · {data.weekly_xp} XP
              </div>
            </div>
            <div className="text-center">
              <div
                className="text-[10px] uppercase tracking-wider"
                style={{ color: "var(--text-muted)" }}
              >
                <Clock size={10} className="inline -mt-0.5 mr-1" />
                сброс
              </div>
              <div
                className="text-xl md:text-2xl font-bold font-mono tabular-nums"
                style={{ color: "var(--text-primary)" }}
              >
                {pluralizeDays(days)}
              </div>
            </div>
          </div>
        </div>

        {/* Sparkline + zones row */}
        <div className="mt-4 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold"
              style={{ background: `${zone!.color}1f`, color: zone!.color }}
            >
              <ZoneIcon size={13} />
              {zone!.label}
            </div>
            <span className="text-xs" style={{ color: "var(--text-muted)" }}>
              {zone!.sub}
            </span>
          </div>
          {timeline && timeline.days.length > 0 && (
            <div
              className="flex items-center gap-2"
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
                  className="text-sm font-mono font-semibold tabular-nums inline-flex items-center gap-1"
                  style={{ color: deltaColor }}
                >
                  <TrendingUp size={12} />
                  {deltaSign}
                  {timeline.delta_vs_median} XP
                </div>
              </div>
            </div>
          )}
        </div>

        <div
          className="mt-3 flex items-center gap-5 text-[11px] uppercase tracking-widest"
          style={{ color: "var(--text-muted)" }}
        >
          <span className="inline-flex items-center gap-1">
            <ChevronUp size={12} style={{ color: "#4ade80" }} />
            промо: топ-{data.promotion_zone}
          </span>
          <span className="inline-flex items-center gap-1">
            <ChevronDown size={12} style={{ color: "#f87171" }} />
            вылет: #{data.demotion_zone}+
          </span>
        </div>
      </motion.div>

      {/* Podium — only when ≥3 in cohort, otherwise it looks empty */}
      {podium.length >= 3 && <PodiumCard top3={podium} title="Топ-3 когорты" />}

      {/* Standings list (always) */}
      <div
        className="rounded-2xl overflow-hidden"
        style={{
          background: "var(--bg-panel)",
          border: "1px solid var(--border-color)",
        }}
      >
        {standings.map((s, idx) => {
          const prevRank = standings[idx - 1]?.rank ?? 0;
          const crossedPromo = prevRank <= data.promotion_zone && s.rank > data.promotion_zone;
          const crossedDemo = prevRank < data.demotion_zone && s.rank >= data.demotion_zone;
          const isPromo = s.rank <= data.promotion_zone;
          const isDemo = s.rank >= data.demotion_zone;
          const zoneColor = isPromo ? "#4ade80" : isDemo ? "#f87171" : "#94a3b8";
          return (
            <div key={s.user_id}>
              {crossedPromo && (
                <div className="relative h-0 border-t-2 border-dashed flex items-center" style={{ borderColor: "#4ade8044" }}>
                  <span
                    className="absolute left-4 -translate-y-1/2 px-2 text-[10px] font-semibold uppercase tracking-widest"
                    style={{ background: "var(--bg-panel)", color: "#4ade80" }}
                  >
                    ▲ зона повышения
                  </span>
                </div>
              )}
              {crossedDemo && (
                <div className="relative h-0 border-t-2 border-dashed flex items-center" style={{ borderColor: "#f8717144" }}>
                  <span
                    className="absolute left-4 -translate-y-1/2 px-2 text-[10px] font-semibold uppercase tracking-widest"
                    style={{ background: "var(--bg-panel)", color: "#f87171" }}
                  >
                    ▼ зона понижения
                  </span>
                </div>
              )}
              <motion.div
                layout
                className="grid grid-cols-[48px_minmax(0,1fr)_auto_auto] items-center gap-3 px-4 py-3"
                style={{
                  background: s.is_me ? `${palette.accent}12` : "transparent",
                  borderBottom: "1px solid rgba(255,255,255,0.04)",
                }}
              >
                <div className="flex items-center gap-1.5">
                  {s.rank <= 3 ? (
                    <Crown
                      size={16}
                      style={{
                        color:
                          s.rank === 1
                            ? "var(--rank-gold, #F7D154)"
                            : s.rank === 2
                              ? "var(--rank-silver, #C8CDD3)"
                              : "var(--rank-bronze, #C88A56)",
                      }}
                    />
                  ) : (
                    <span className="w-4" />
                  )}
                  <span
                    className="text-sm font-mono font-semibold tabular-nums"
                    style={{ color: s.is_me ? palette.accent : "var(--text-primary)" }}
                  >
                    #{s.rank}
                  </span>
                </div>
                <div className="min-w-0">
                  <div
                    className="text-sm font-medium truncate"
                    style={{ color: s.is_me ? palette.accent : "var(--text-primary)" }}
                  >
                    {s.full_name}
                    {s.is_me && (
                      <span
                        className="ml-2 text-[10px] font-semibold uppercase tracking-widest"
                        style={{ color: palette.accent }}
                      >
                        вы
                      </span>
                    )}
                  </div>
                </div>
                <div
                  className="text-sm font-mono tabular-nums"
                  style={{ color: s.is_me ? palette.accent : "var(--text-primary)" }}
                >
                  {s.weekly_xp}
                </div>
                <div className="text-[11px] uppercase tracking-wider" style={{ color: zoneColor }}>
                  {isPromo ? <ChevronUp size={14} /> : isDemo ? <ChevronDown size={14} /> : <ShieldCheck size={14} />}
                </div>
              </motion.div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
