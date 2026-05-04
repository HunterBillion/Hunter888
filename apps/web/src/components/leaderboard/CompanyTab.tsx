"use client";

/**
 * CompanyTab — unified company-wide leaderboard.
 *
 * Replaces three separate tabs (Охотник, Неделя, Месяц) with one tab and
 * an internal period switch (Неделя · Месяц · Всё время). The "Всё время"
 * period reuses the Hunter Score endpoint; week/month reuse the weekly-TP
 * + monthly-tournament endpoints. Sidebar still shows TP breakdown.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, Sparkles, Trophy } from "lucide-react";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";
import {
  PodiumCard,
  type PodiumEntry,
} from "@/components/leaderboard/PodiumCard";
import {
  LeaderboardTable,
  type LeaderboardRow,
} from "@/components/leaderboard/LeaderboardTable";
import {
  TPBreakdown,
  type TPBreakdownData,
} from "@/components/leaderboard/TPBreakdown";

type Period = "week" | "month" | "all";

const PERIOD_LABEL: Record<Period, string> = {
  week: "Неделя",
  month: "Месяц",
  all: "Всё время",
};

interface HunterEntry {
  rank: number;
  user_id: string;
  full_name: string;
  avatar_url?: string | null;
  hunter_score: number;
  current_level: number;
  week_tp: number;
  delta_vs_last_week: number;
  is_me: boolean;
}

interface WeeklyEntry {
  rank: number;
  user_id: string;
  full_name: string;
  avatar_url?: string | null;
  week_tp: number;
  is_me: boolean;
}

interface MonthlyEntry {
  rank: number;
  user_id: string;
  full_name: string;
  best_score: number;
  attempts: number;
}

interface MonthlyResp {
  tournament?: { id: string } | null;
  leaderboard?: MonthlyEntry[];
}

const periodMeta: Record<
  Period,
  { unit: string; emptyTitle: string; emptyBody: string }
> = {
  week: {
    unit: "TP",
    emptyTitle: "На этой неделе ещё нет активностей",
    emptyBody: "Пройди тренировку — TP появятся здесь сразу.",
  },
  month: {
    unit: "pts",
    emptyTitle: "Месячный турнир не активен",
    emptyBody:
      "Админ запускает турнир раз в месяц. Текущий не объявлен — следи за уведомлениями.",
  },
  all: {
    unit: "HS",
    emptyTitle: "Hunter Score копится с первой тренировки",
    emptyBody: "Сделай хотя бы одну сессию — попадёшь в общий рейтинг.",
  },
};

export function CompanyTab() {
  const [period, setPeriod] = useState<Period>("week");

  const [hunters, setHunters] = useState<HunterEntry[] | null>(null);
  const [weekly, setWeekly] = useState<WeeklyEntry[] | null>(null);
  const [monthly, setMonthly] = useState<MonthlyEntry[] | null>(null);
  const [breakdown, setBreakdown] = useState<TPBreakdownData | null>(null);
  const [breakdownLoading, setBreakdownLoading] = useState(true);
  const [loading, setLoading] = useState(false);

  const loadPeriod = useCallback(async (p: Period) => {
    setLoading(true);
    try {
      if (p === "all") {
        const data = await api.get<HunterEntry[]>(
          "/gamification/leaderboard/hunters?scope=company&limit=50",
        );
        setHunters(Array.isArray(data) ? data : []);
      } else if (p === "week") {
        const data = await api.get<WeeklyEntry[]>(
          "/gamification/leaderboard/weekly-tp?scope=company&limit=50",
        );
        setWeekly(Array.isArray(data) ? data : []);
      } else {
        const data = await api.get<MonthlyResp>(
          "/tournament/active?type=monthly_championship",
        );
        setMonthly(data?.leaderboard ?? []);
      }
    } catch (err) {
      logger.error(`company leaderboard load failed (${p}):`, err);
      if (p === "all") setHunters([]);
      if (p === "week") setWeekly([]);
      if (p === "month") setMonthly([]);
    } finally {
      setLoading(false);
    }
  }, []);

  // Load breakdown once.
  useEffect(() => {
    (async () => {
      setBreakdownLoading(true);
      try {
        const d = await api.get<TPBreakdownData>(
          "/gamification/leaderboard/my-breakdown",
        );
        setBreakdown(d);
      } catch (err) {
        logger.error("breakdown fetch failed", err);
        setBreakdown(null);
      } finally {
        setBreakdownLoading(false);
      }
    })();
  }, []);

  useEffect(() => {
    loadPeriod(period);
  }, [period, loadPeriod]);

  // Derive rows + podium for the active period.
  const { rows, podium } = useMemo<{
    rows: LeaderboardRow[];
    podium: PodiumEntry[];
  }>(() => {
    if (period === "all" && hunters) {
      const r: LeaderboardRow[] = hunters.map((h) => ({
        rank: h.rank,
        user_id: h.user_id,
        full_name: h.full_name,
        avatar_url: h.avatar_url,
        score: h.hunter_score,
        delta: h.delta_vs_last_week,
        subtitle: `Ур. ${h.current_level} · ${h.week_tp} TP за неделю`,
        is_me: h.is_me,
      }));
      const p: PodiumEntry[] = hunters.slice(0, 3).map((h) => ({
        user_id: h.user_id,
        full_name: h.full_name,
        avatar_url: h.avatar_url,
        score: h.hunter_score,
        delta: h.delta_vs_last_week,
        scoreUnit: "HS",
      }));
      return { rows: r, podium: p };
    }
    if (period === "week" && weekly) {
      const r: LeaderboardRow[] = weekly.map((w) => ({
        rank: w.rank,
        user_id: w.user_id,
        full_name: w.full_name,
        avatar_url: w.avatar_url,
        score: w.week_tp,
        is_me: w.is_me,
      }));
      const p: PodiumEntry[] = weekly.slice(0, 3).map((w) => ({
        user_id: w.user_id,
        full_name: w.full_name,
        avatar_url: w.avatar_url,
        score: w.week_tp,
        scoreUnit: "TP",
      }));
      return { rows: r, podium: p };
    }
    if (period === "month" && monthly) {
      const r: LeaderboardRow[] = monthly.map((m) => ({
        rank: m.rank,
        user_id: m.user_id,
        full_name: m.full_name,
        score: m.best_score,
        subtitle: `${m.attempts} попыток`,
        is_me: false,
      }));
      const p: PodiumEntry[] = monthly.slice(0, 3).map((m) => ({
        user_id: m.user_id,
        full_name: m.full_name,
        score: m.best_score,
        scoreUnit: "pts",
      }));
      return { rows: r, podium: p };
    }
    return { rows: [], podium: [] };
  }, [period, hunters, weekly, monthly]);

  const meta = periodMeta[period];
  const hasData = rows.length > 0;

  return (
    <div className="grid gap-5 md:grid-cols-[1fr_320px]">
      <div className="space-y-5 min-w-0">
        {/* Period switcher */}
        <div
          className="inline-flex rounded-xl p-1 gap-1"
          style={{
            background: "rgba(255,255,255,0.04)",
            border: "1px solid rgba(255,255,255,0.06)",
          }}
        >
          {(Object.keys(PERIOD_LABEL) as Period[]).map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => setPeriod(p)}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold uppercase tracking-wider transition-all"
              style={{
                background: period === p ? "var(--accent)" : "transparent",
                color: period === p ? "#fff" : "var(--text-muted)",
              }}
            >
              {PERIOD_LABEL[p]}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2
              size={24}
              className="animate-spin"
              style={{ color: "var(--accent)" }}
            />
          </div>
        ) : !hasData ? (
          <EmptyCta
            title={meta.emptyTitle}
            body={meta.emptyBody}
            ctaLabel="Открыть тренировку"
            ctaHref="/training"
          />
        ) : (
          <>
            {podium.length >= 3 && (
              <PodiumCard
                top3={podium}
                title={
                  period === "all"
                    ? "Топ-3 охотника"
                    : period === "week"
                      ? "Топ-3 недели"
                      : "Топ-3 турнира"
                }
              />
            )}
            <LeaderboardTable rows={rows} scoreUnit={meta.unit} />
          </>
        )}
      </div>

      <div className="min-w-0">
        <TPBreakdown data={breakdown} loading={breakdownLoading} />
      </div>
    </div>
  );
}

function EmptyCta({
  title,
  body,
  ctaLabel,
  ctaHref,
}: {
  title: string;
  body: string;
  ctaLabel: string;
  ctaHref: string;
}) {
  return (
    <div
      className="rounded-2xl p-8 text-center"
      style={{
        background:
          "linear-gradient(135deg, rgba(167,139,250,0.08) 0%, var(--bg-panel) 100%)",
        border: "1px solid var(--border-color)",
      }}
    >
      <div
        className="inline-flex h-12 w-12 items-center justify-center rounded-2xl mb-3"
        style={{ background: "rgba(167,139,250,0.18)", color: "#a78bfa" }}
      >
        <Trophy size={22} />
      </div>
      <h3
        className="text-base font-semibold mb-1"
        style={{ color: "var(--text-primary)" }}
      >
        {title}
      </h3>
      <p
        className="text-sm mb-4 max-w-md mx-auto"
        style={{ color: "var(--text-muted)" }}
      >
        {body}
      </p>
      <a
        href={ctaHref}
        className="inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-semibold"
        style={{ background: "var(--accent)", color: "#fff" }}
      >
        <Sparkles size={14} />
        {ctaLabel}
      </a>
    </div>
  );
}

