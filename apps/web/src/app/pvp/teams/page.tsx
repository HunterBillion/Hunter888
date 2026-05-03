"use client";

/**
 * /pvp/teams — Weekly Team Leaderboard.
 *
 * Phase C (2026-04-20). B2B layer over the player cohort: sales teams
 * (офис продаж) compete against each other by weighted average score of
 * all team members over the selected window. Data from
 *  `GET /gamification/leaderboard/teams?period=week|month|all`.
 *
 * Style matches `LeagueHeroCard` + `/pvp/league` — same crown/tier vibe
 * but with the Clash-Royale-style clan framing (Московский офис vs
 * Петербургский офис).
 */

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  ArrowLeft,
  Crown,
  Loader2,
  Trophy,
  Users,
  TrendingUp,
  RefreshCw,
} from "lucide-react";
import AuthLayout from "@/components/layout/AuthLayout";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";
import { useNotificationStore } from "@/stores/useNotificationStore";

interface TeamRow {
  rank: number;
  team_id: string;
  team_name: string;
  active_members: number;
  total_sessions: number;
  avg_score: number;
  total_score: number;
}

type Period = "week" | "month" | "all";

const PERIOD_LABEL: Record<Period, { short: string; full: string }> = {
  week: { short: "Неделя", full: "За неделю" },
  month: { short: "Месяц", full: "За месяц" },
  all: { short: "Всё время", full: "Всё время" },
};

const RANK_CROWN: Record<number, string> = {
  1: "#facc15",
  2: "#cbd5e1",
  3: "#f59e0b",
};

export default function TeamsLeaderboardPage() {
  const [rows, setRows] = useState<TeamRow[]>([]);
  const [period, setPeriod] = useState<Period>("week");
  const [loading, setLoading] = useState(true);
  const [myTeamId, setMyTeamId] = useState<string | null>(null);

  const load = useCallback(async (p: Period) => {
    setLoading(true);
    try {
      const data = await api.get<TeamRow[]>(
        `/gamification/leaderboard/teams?period=${p}`,
      );
      setRows(Array.isArray(data) ? data : []);
    } catch (e) {
      logger.error("teams leaderboard load failed", e);
      useNotificationStore.getState().addToast({
        type: "error",
        title: "Не удалось загрузить лидерборд команд",
        body: "Проверь соединение и попробуй обновить страницу.",
      });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(period);
  }, [period, load]);

  // Pull my team_id from /auth/me so we can highlight the current user's
  // team row without leaking private data into the leaderboard response.
  useEffect(() => {
    (async () => {
      try {
        const me = await api.get<{ team_id?: string | null }>("/auth/me");
        setMyTeamId(me.team_id ?? null);
      } catch {
        // Non-fatal; just skip the "ты" highlight.
      }
    })();
  }, []);

  const podium = useMemo(() => rows.filter((r) => r.rank <= 3), [rows]);
  const tail = useMemo(() => rows.filter((r) => r.rank > 3), [rows]);

  const accent = "#fbbf24"; // gold — matches TournamentTheme

  return (
    <AuthLayout>
      <div className="max-w-3xl mx-auto px-4 md:px-6 py-6">
        <div className="flex items-center justify-between mb-5">
          <Link
            href="/pvp"
            className="inline-flex items-center gap-1.5 text-sm"
            style={{ color: "var(--text-muted)" }}
          >
            <ArrowLeft size={14} />
            На арену
          </Link>
          <button
            type="button"
            onClick={() => load(period)}
            className="inline-flex items-center gap-1.5 text-[11px] uppercase tracking-widest px-2 py-1 rounded-md"
            style={{
              color: "var(--text-muted)",
              border: "1px solid var(--border-color)",
            }}
          >
            <RefreshCw size={11} />
            Обновить
          </button>
        </div>

        {/* Hero */}
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="relative overflow-hidden rounded-2xl p-5 md:p-6 mb-5"
          style={{
            background: `linear-gradient(135deg, ${accent}14 0%, rgba(16,12,28,0.85) 55%, rgba(16,12,28,0.95) 100%)`,
            border: `1px solid ${accent}33`,
          }}
        >
          <div className="flex items-start justify-between gap-4">
            <div>
              <div
                className="text-[10px] uppercase tracking-wider font-semibold"
                style={{ color: accent }}
              >
                Команды компании
              </div>
              <h1
                className="text-2xl md:text-3xl font-bold mt-1"
                style={{ color: "var(--text-primary)" }}
              >
                Лидерборд офисов продаж
              </h1>
              <p
                className="text-sm mt-2 max-w-lg"
                style={{ color: "var(--text-muted)" }}
              >
                Средний балл команды по завершённым тренировкам. Минимум 3
                сессии за период — иначе команда не попадает в рейтинг.
              </p>
            </div>
            <div
              className="flex h-14 w-14 items-center justify-center rounded-2xl shrink-0"
              style={{
                background: `${accent}22`,
                color: accent,
                border: `1px solid ${accent}55`,
              }}
            >
              <Users size={26} />
            </div>
          </div>

          <div className="mt-5 inline-flex rounded-xl p-1 gap-1"
               style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.06)" }}>
            {(Object.keys(PERIOD_LABEL) as Period[]).map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => setPeriod(p)}
                className="px-3 py-1 rounded-lg text-xs font-semibold uppercase tracking-wider transition-all"
                style={{
                  background: period === p ? accent : "transparent",
                  color: period === p ? "#0b0b14" : "var(--text-muted)",
                }}
              >
                {PERIOD_LABEL[p].short}
              </button>
            ))}
          </div>
        </motion.div>

        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 size={24} className="animate-spin" style={{ color: accent }} />
          </div>
        ) : rows.length === 0 ? (
          <div
            className="rounded-2xl p-8 text-center"
            style={{
              background: "var(--bg-panel)",
              border: "1px solid var(--border-color)",
            }}
          >
            <Trophy size={28} style={{ color: accent }} className="mx-auto mb-3" />
            <div
              className="font-semibold mb-1"
              style={{ color: "var(--text-primary)" }}
            >
              {PERIOD_LABEL[period].full} — лидерборд пуст
            </div>
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>
              Нужно минимум 3 завершённые сессии в команде. Попробуй ещё
              позже или расширь период.
            </p>
          </div>
        ) : (
          <>
            {/* Podium — top 3 */}
            {podium.length > 0 && (
              <div className="grid grid-cols-3 gap-3 md:gap-4 items-end mb-5">
                {[2, 1, 3].map((displayRank) => {
                  const row = podium.find((r) => r.rank === displayRank);
                  if (!row) return <div key={displayRank} />;
                  const isFirst = row.rank === 1;
                  const height = isFirst ? 170 : row.rank === 2 ? 140 : 120;
                  const crown = RANK_CROWN[row.rank];
                  const mine = myTeamId === row.team_id;
                  return (
                    <motion.div
                      key={row.team_id}
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: 0.1 * row.rank }}
                      className="rounded-2xl p-3 md:p-4 flex flex-col items-center text-center"
                      style={{
                        height,
                        background: mine
                          ? `${accent}1a`
                          : "rgba(255,255,255,0.03)",
                        border: `2px solid ${mine ? accent : `${crown}66`}`,
                        boxShadow: isFirst
                          ? `0 18px 36px -16px ${crown}99`
                          : undefined,
                      }}
                    >
                      <Crown size={isFirst ? 24 : 18} style={{ color: crown }} />
                      <div
                        className="mt-1 font-mono font-bold text-sm tabular-nums"
                        style={{ color: crown }}
                      >
                        #{row.rank}
                      </div>
                      <div
                        className="font-semibold text-sm md:text-base line-clamp-2 mt-1 leading-tight"
                        style={{ color: "var(--text-primary)" }}
                      >
                        {row.team_name}
                      </div>
                      <div
                        className="mt-auto font-mono text-lg md:text-xl font-black tabular-nums"
                        style={{ color: mine ? accent : "var(--text-primary)" }}
                      >
                        {row.avg_score.toFixed(1)}
                      </div>
                      <div
                        className="text-[10px] uppercase tracking-wider"
                        style={{ color: "var(--text-muted)" }}
                      >
                        средний балл
                      </div>
                    </motion.div>
                  );
                })}
              </div>
            )}

            {/* Tail list */}
            {tail.length > 0 && (
              <div
                className="rounded-2xl overflow-hidden"
                style={{
                  background: "var(--bg-panel)",
                  border: "1px solid var(--border-color)",
                }}
              >
                {tail.map((row) => {
                  const mine = myTeamId === row.team_id;
                  return (
                    <motion.div
                      key={row.team_id}
                      layout
                      className="grid grid-cols-[48px_minmax(0,1fr)_auto_auto] items-center gap-3 px-4 py-3"
                      style={{
                        background: mine ? `${accent}12` : "transparent",
                        borderBottom: "1px solid rgba(255,255,255,0.04)",
                      }}
                    >
                      <span
                        className="font-mono font-semibold tabular-nums"
                        style={{
                          color: mine ? accent : "var(--text-primary)",
                        }}
                      >
                        #{row.rank}
                      </span>
                      <div className="min-w-0">
                        <div
                          className="text-sm font-medium truncate"
                          style={{
                            color: mine ? accent : "var(--text-primary)",
                          }}
                        >
                          {row.team_name}
                          {mine && (
                            <span
                              className="ml-2 text-[10px] font-semibold uppercase tracking-widest"
                              style={{ color: accent }}
                            >
                              твоя
                            </span>
                          )}
                        </div>
                        <div
                          className="text-[11px] font-mono mt-0.5"
                          style={{ color: "var(--text-muted)" }}
                        >
                          {row.active_members} игроков · {row.total_sessions}{" "}
                          сессий
                        </div>
                      </div>
                      <div
                        className="flex items-center gap-1 text-sm font-mono tabular-nums"
                        style={{
                          color: mine ? accent : "var(--text-primary)",
                        }}
                      >
                        <TrendingUp size={12} style={{ color: accent, opacity: 0.7 }} />
                        {row.avg_score.toFixed(1)}
                      </div>
                      <div
                        className="text-[11px] font-mono tabular-nums hidden sm:block"
                        style={{ color: "var(--text-muted)" }}
                      >
                        Σ {row.total_score.toFixed(0)}
                      </div>
                    </motion.div>
                  );
                })}
              </div>
            )}
          </>
        )}
      </div>
    </AuthLayout>
  );
}
