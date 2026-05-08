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

/**
 * ZoneBanner — крупная плашка-разделитель между зонами в standings.
 *
 * 2026-05-08: заменяет «надпись на пунктирной линии» из старой версии.
 * Стиль повторяет UI Дуолинго: большая чёткая плашка с цветным фоном,
 * иконка слева, заголовок жирным шрифтом 16px, описание под ним 13px.
 * Высота банера ~64px — это создаёт явную визуальную границу между
 * зонами, а не «ускользающую» надпись.
 */
function ZoneBanner({ kind }: { kind: "promo" | "demo" }) {
  const isPromo = kind === "promo";
  const color = isPromo ? "#4ade80" : "#f87171";
  const Icon = isPromo ? ChevronUp : ChevronDown;
  return (
    <div
      className="flex items-center gap-3 px-4 md:px-5 py-3"
      style={{
        background: `linear-gradient(90deg, ${color}22 0%, ${color}0a 100%)`,
        borderTop: `2px solid ${color}55`,
        borderBottom: `2px solid ${color}55`,
      }}
    >
      <div
        className="flex items-center justify-center rounded-md"
        style={{
          width: 36,
          height: 36,
          background: `${color}33`,
          border: `2px solid ${color}`,
          flexShrink: 0,
        }}
      >
        <Icon size={22} style={{ color }} strokeWidth={3} />
      </div>
      <div className="min-w-0 flex-1">
        <div
          className="font-pixel uppercase tracking-widest"
          style={{ color, fontSize: 16, lineHeight: 1.1 }}
        >
          {isPromo ? "ЗОНА ПОВЫШЕНИЯ" : "ЗОНА ПОНИЖЕНИЯ"}
        </div>
        <div
          className="font-pixel uppercase tracking-wider mt-1"
          style={{ color: "var(--text-muted)", fontSize: 13 }}
        >
          {isPromo
            ? "те, кто выше — поднимутся в следующую лигу"
            : "те, кто ниже — потеряют лигу до следующей недели"}
        </div>
      </div>
    </div>
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
      {/*
        2026-05-08 (полировка): большой Hero-блок «Недельная лига /
        Профессионал / #N / сброс» удалён — он визуально дублировал
        HeroPanel наверху страницы. Оставили только полезное:
          - zone meta strip (промо / безопасная / понижение)
          - sparkline (XP по дням vs медиана когорты)
          - bounds-строка (промо: топ-N · вылет: #M+)
        Сама plate с тиром лиги, рангом и сбросом — она уже есть в
        HeroPanel над всеми секциями.
      */}
      <div
        className="flex flex-wrap items-center justify-between gap-4 px-2"
      >
        <div className="flex items-center gap-3">
          <div
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-sm font-pixel uppercase tracking-widest"
            style={{
              background: `${zone!.color}1f`,
              color: zone!.color,
              border: `1px solid ${zone!.color}55`,
              fontSize: 14,
            }}
          >
            <ZoneIcon size={14} />
            {zone!.label}
          </div>
          <span
            className="font-pixel uppercase tracking-widest"
            style={{ color: "var(--text-muted)", fontSize: 14 }}
          >
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
                className="font-pixel uppercase tracking-widest"
                style={{ color: "var(--text-muted)", fontSize: 14 }}
              >
                vs медиана
              </div>
              <div
                className="font-mono font-semibold tabular-nums inline-flex items-center gap-1"
                style={{ color: deltaColor, fontSize: 14 }}
              >
                <TrendingUp size={14} />
                {deltaSign}
                {timeline.delta_vs_median} XP
              </div>
            </div>
          </div>
        )}
      </div>

      <div
        className="flex flex-wrap items-center gap-5 px-2 font-pixel uppercase tracking-widest"
        style={{ color: "var(--text-muted)", fontSize: 14 }}
      >
        <span className="inline-flex items-center gap-1.5">
          <ChevronUp size={14} style={{ color: "#4ade80" }} />
          промо: топ-{data.promotion_zone}
        </span>
        <span className="inline-flex items-center gap-1.5">
          <ChevronDown size={14} style={{ color: "#f87171" }} />
          вылет: #{data.demotion_zone}+
        </span>
        <span className="inline-flex items-center gap-1.5">
          <Clock size={14} />
          сброс: {pluralizeDays(days)}
        </span>
      </div>

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
        {/*
          2026-05-08 (полировка по фидбеку «Дуолинго-style»): размеры
          подняты во всех колонках — имена 16px, ранги 18px, XP 18px
          tabular-nums. Padding по вертикали py-4 (был py-3) для
          «дыхания» строк. Crown ↑ 18px вместо 16. Аватар в кружочке
          (если есть avatar_url, иначе пиксельные инициалы) на 36px
          слева — добавляет визуальный якорь как у Дуолинго.

          Zone-разделители стали полноценными плашками, а не «надписи на
          линии». Дуолинго-стиль: цельная плашка-полоска с цветным
          фоном, иконка слева, заголовок жирный, подпись мелкая под ним.
        */}
        {standings.map((s, idx) => {
          const prevRank = standings[idx - 1]?.rank ?? 0;
          const crossedPromo = prevRank <= data.promotion_zone && s.rank > data.promotion_zone;
          const crossedDemo = prevRank < data.demotion_zone && s.rank >= data.demotion_zone;
          const isPromo = s.rank <= data.promotion_zone;
          const isDemo = s.rank >= data.demotion_zone;
          const zoneColor = isPromo ? "#4ade80" : isDemo ? "#f87171" : "#94a3b8";
          const initials = (s.full_name || "?")
            .trim()
            .split(/\s+/)
            .slice(0, 2)
            .map((p) => p[0]?.toUpperCase() ?? "")
            .join("") || "?";
          return (
            <div key={s.user_id}>
              {crossedPromo && <ZoneBanner kind="promo" />}
              {crossedDemo && <ZoneBanner kind="demo" />}
              <motion.div
                layout
                className="grid grid-cols-[44px_44px_minmax(0,1fr)_auto_28px] items-center gap-3 md:gap-4 px-4 md:px-5 py-4"
                style={{
                  background: s.is_me ? `${palette.accent}1c` : "transparent",
                  borderBottom: "1px solid rgba(255,255,255,0.05)",
                  borderLeft: s.is_me ? `3px solid ${palette.accent}` : "3px solid transparent",
                }}
              >
                {/* Ранг + корона */}
                <div className="flex items-center gap-1.5">
                  {s.rank <= 3 ? (
                    <Crown
                      size={18}
                      style={{
                        color:
                          s.rank === 1
                            ? "var(--rank-gold, #F7D154)"
                            : s.rank === 2
                              ? "var(--rank-silver, #C8CDD3)"
                              : "var(--rank-bronze, #C88A56)",
                        filter: `drop-shadow(0 0 6px ${
                          s.rank === 1
                            ? "rgba(247,209,84,0.5)"
                            : s.rank === 2
                              ? "rgba(200,205,211,0.4)"
                              : "rgba(200,138,86,0.4)"
                        })`,
                      }}
                    />
                  ) : (
                    <span className="w-[18px]" />
                  )}
                  <span
                    className="font-mono font-bold tabular-nums"
                    style={{
                      color: s.is_me ? palette.accent : "var(--text-primary)",
                      fontSize: 18,
                    }}
                  >
                    #{s.rank}
                  </span>
                </div>

                {/* Аватар-кружок (или пиксельные инициалы) */}
                <div
                  className="flex items-center justify-center font-pixel rounded-full overflow-hidden shrink-0"
                  style={{
                    width: 36,
                    height: 36,
                    background: s.is_me
                      ? `${palette.accent}33`
                      : "rgba(255,255,255,0.05)",
                    border: `2px solid ${s.is_me ? palette.accent : "rgba(255,255,255,0.12)"}`,
                    color: s.is_me ? palette.accent : "var(--text-secondary)",
                    fontSize: 14,
                  }}
                >
                  {s.avatar_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={s.avatar_url}
                      alt={s.full_name}
                      width={36}
                      height={36}
                      style={{ width: "100%", height: "100%", objectFit: "cover" }}
                    />
                  ) : (
                    initials
                  )}
                </div>

                {/* Имя + бейдж «вы» */}
                <div className="min-w-0">
                  <div
                    className="font-medium truncate"
                    style={{
                      color: s.is_me ? palette.accent : "var(--text-primary)",
                      fontSize: 16,
                      lineHeight: 1.2,
                    }}
                  >
                    {s.full_name}
                  </div>
                  {s.is_me && (
                    <div
                      className="font-pixel uppercase tracking-widest mt-0.5"
                      style={{ color: palette.accent, fontSize: 12 }}
                    >
                      вы
                    </div>
                  )}
                </div>

                {/* XP — крупно, с подписью под ним */}
                <div className="text-right">
                  <div
                    className="font-mono font-bold tabular-nums"
                    style={{
                      color: s.is_me ? palette.accent : "var(--text-primary)",
                      fontSize: 18,
                      lineHeight: 1.1,
                    }}
                  >
                    {s.weekly_xp}
                  </div>
                  <div
                    className="font-pixel uppercase tracking-widest"
                    style={{ color: "var(--text-muted)", fontSize: 11 }}
                  >
                    XP
                  </div>
                </div>

                {/* Иконка зоны (вверх / вниз / щит) */}
                <div className="flex items-center justify-center">
                  {isPromo ? (
                    <ChevronUp size={20} style={{ color: zoneColor }} />
                  ) : isDemo ? (
                    <ChevronDown size={20} style={{ color: zoneColor }} />
                  ) : (
                    <ShieldCheck size={18} style={{ color: zoneColor, opacity: 0.6 }} />
                  )}
                </div>
              </motion.div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
