"use client";

/**
 * LeagueTab — weekly cohort leaderboard, embedded into /leaderboard.
 *
 * Replaces the standalone /pvp/league page. Shows the player's ~15-person
 * cohort with podium, promo/demo zones, and the current user always
 * highlighted. Auto-refreshes every 45s while the tab is visible.
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
} from "lucide-react";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";
import { useNotificationStore } from "@/stores/useNotificationStore";

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

const TIER_ACCENT: Record<number, string> = {
  0: "#94a3b8",
  1: "#4ade80",
  2: "#a78bfa",
  3: "#facc15",
  4: "#fb923c",
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

export function LeagueTab() {
  const [data, setData] = useState<LeagueData | null>(null);
  const [loading, setLoading] = useState(true);
  const mountedRef = useRef(true);

  const fetchLeague = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const d = await api.get<LeagueData>("/gamification/league/me");
      if (mountedRef.current) setData(d);
    } catch (e) {
      logger.error("league/me fetch failed", e);
      if (!silent) {
        useNotificationStore.getState().addToast({
          type: "error",
          title: "Не удалось загрузить лигу",
          body: "Проверь соединение и попробуй обновить страницу.",
        });
      }
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    fetchLeague();
    // Polling only while visible — saves battery on backgrounded tabs.
    const onVisibility = () => {
      if (document.visibilityState === "visible") fetchLeague(true);
    };
    const int = setInterval(onVisibility, 45_000);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      mountedRef.current = false;
      clearInterval(int);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [fetchLeague]);

  const accent = data ? TIER_ACCENT[data.tier] ?? "#94a3b8" : "#94a3b8";
  const days = Math.max(0, Math.round(data?.days_remaining ?? 0));

  const standings = useMemo(
    () => [...(data?.standings ?? [])].sort((a, b) => a.rank - b.rank),
    [data],
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 size={24} className="animate-spin" style={{ color: accent }} />
      </div>
    );
  }

  if (!data || data.group_size === 0) {
    return (
      <div
        className="rounded-2xl p-8 text-center"
        style={{
          background: "var(--bg-panel)",
          border: "1px solid var(--border-color)",
        }}
      >
        <Trophy size={32} style={{ color: accent }} className="mx-auto mb-3" />
        <h2
          className="text-lg font-semibold mb-1"
          style={{ color: "var(--text-primary)" }}
        >
          Лига формируется в понедельник 08:00
        </h2>
        <p className="text-sm" style={{ color: "var(--text-muted)" }}>
          Когорта из ~15 игроков подбирается по уровню и команде. Играй —
          в понедельник появится список соперников.
        </p>
      </div>
    );
  }

  return (
    <>
      {/* Hero strip */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="relative overflow-hidden rounded-2xl p-5 md:p-6 mb-5"
        style={{
          background: `linear-gradient(135deg, ${accent}14 0%, rgba(16,12,28,0.85) 55%, rgba(16,12,28,0.95) 100%)`,
          border: `1px solid ${accent}33`,
        }}
      >
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div
              className="flex h-14 w-14 items-center justify-center rounded-2xl"
              style={{
                background: `${accent}22`,
                border: `1px solid ${accent}55`,
                color: accent,
              }}
            >
              <Trophy size={26} />
            </div>
            <div>
              <div
                className="text-[10px] uppercase tracking-wider font-semibold"
                style={{ color: accent }}
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
                style={{ color: accent }}
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
        <div
          className="mt-4 flex items-center gap-5 text-[11px] uppercase tracking-widest"
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

      {/* Standings */}
      <div
        className="rounded-2xl overflow-hidden"
        style={{
          background: "var(--bg-panel)",
          border: "1px solid var(--border-color)",
        }}
      >
        {standings.map((s, idx) => {
          const prevRank = standings[idx - 1]?.rank ?? 0;
          const crossedPromo =
            prevRank <= data.promotion_zone && s.rank > data.promotion_zone;
          const crossedDemo =
            prevRank < data.demotion_zone && s.rank >= data.demotion_zone;

          const isPromo = s.rank <= data.promotion_zone;
          const isDemo = s.rank >= data.demotion_zone;
          const zoneColor = isPromo
            ? "#4ade80"
            : isDemo
              ? "#f87171"
              : "#94a3b8";

          return (
            <div key={s.user_id}>
              {crossedPromo && (
                <div
                  className="relative h-0 border-t-2 border-dashed flex items-center"
                  style={{ borderColor: "#4ade8044" }}
                >
                  <span
                    className="absolute left-4 -translate-y-1/2 px-2 text-[10px] font-semibold uppercase tracking-widest"
                    style={{
                      background: "var(--bg-panel)",
                      color: "#4ade80",
                    }}
                  >
                    ▲ зона повышения
                  </span>
                </div>
              )}
              {crossedDemo && (
                <div
                  className="relative h-0 border-t-2 border-dashed flex items-center"
                  style={{ borderColor: "#f8717144" }}
                >
                  <span
                    className="absolute left-4 -translate-y-1/2 px-2 text-[10px] font-semibold uppercase tracking-widest"
                    style={{
                      background: "var(--bg-panel)",
                      color: "#f87171",
                    }}
                  >
                    ▼ зона понижения
                  </span>
                </div>
              )}

              <motion.div
                layout
                className="grid grid-cols-[48px_minmax(0,1fr)_auto_auto] items-center gap-3 px-4 py-3"
                style={{
                  background: s.is_me ? `${accent}12` : "transparent",
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
                    style={{ color: s.is_me ? accent : "var(--text-primary)" }}
                  >
                    #{s.rank}
                  </span>
                </div>
                <div className="min-w-0">
                  <div
                    className="text-sm font-medium truncate"
                    style={{ color: s.is_me ? accent : "var(--text-primary)" }}
                  >
                    {s.full_name}
                    {s.is_me && (
                      <span
                        className="ml-2 text-[10px] font-semibold uppercase tracking-widest"
                        style={{ color: accent }}
                      >
                        вы
                      </span>
                    )}
                  </div>
                </div>
                <div
                  className="text-sm font-mono tabular-nums"
                  style={{ color: s.is_me ? accent : "var(--text-primary)" }}
                >
                  {s.weekly_xp}
                </div>
                <div
                  className="text-[11px] uppercase tracking-wider"
                  style={{ color: zoneColor }}
                >
                  {isPromo ? (
                    <ChevronUp size={14} />
                  ) : isDemo ? (
                    <ChevronDown size={14} />
                  ) : (
                    <ShieldCheck size={14} />
                  )}
                </div>
              </motion.div>
            </div>
          );
        })}
      </div>
    </>
  );
}
