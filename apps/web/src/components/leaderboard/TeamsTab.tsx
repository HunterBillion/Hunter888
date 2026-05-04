"use client";

/**
 * TeamsTab — sales-office (team) leaderboard, embedded into /leaderboard.
 *
 * Replaces the standalone /pvp/teams page. Ranks teams by Bayesian-shrunk
 * average score so a 1-session team can't outrank a 100-session team. The
 * caller's own team is always shown — pinned below the top-10 if outside.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  Crown,
  Loader2,
  Trophy,
  Users,
  TrendingUp,
  RefreshCw,
} from "lucide-react";
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
  score: number;
  total_score: number;
}

interface TeamsResponse {
  rows: TeamRow[];
  my_team_row: TeamRow | null;
  total_teams: number;
  global_avg: number;
}

type Period = "week" | "month" | "all";

const PERIOD_LABEL: Record<Period, string> = {
  week: "Неделя",
  month: "Месяц",
  all: "Всё время",
};

const RANK_CROWN: Record<number, string> = {
  1: "var(--rank-gold, #F7D154)",
  2: "var(--rank-silver, #C8CDD3)",
  3: "var(--rank-bronze, #C88A56)",
};

export function TeamsTab() {
  const [data, setData] = useState<TeamsResponse | null>(null);
  const [period, setPeriod] = useState<Period>("week");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (p: Period) => {
    setLoading(true);
    try {
      const resp = await api.get<TeamsResponse>(
        `/gamification/leaderboard/teams?period=${p}`,
      );
      setData(resp);
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

  const accent = "#fbbf24";

  const podium = useMemo(
    () => (data?.rows ?? []).filter((r) => r.rank <= 3),
    [data],
  );
  const tail = useMemo(
    () => (data?.rows ?? []).filter((r) => r.rank > 3),
    [data],
  );
  const myRow = data?.my_team_row ?? null;

  return (
    <div>
      {/* Period switcher + refresh */}
      <div className="flex items-center justify-between gap-3 mb-5">
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
                background: period === p ? accent : "transparent",
                color: period === p ? "#0b0b14" : "var(--text-muted)",
              }}
            >
              {PERIOD_LABEL[p]}
            </button>
          ))}
        </div>
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

      {loading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 size={24} className="animate-spin" style={{ color: accent }} />
        </div>
      ) : !data || data.rows.length === 0 ? (
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
            Лидерборд пуст
          </div>
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            Команда попадает в рейтинг после 3+ завершённых сессий за период.
            Попробуй ещё позже или расширь период.
          </p>
        </div>
      ) : (
        <>
          {/* Context strip */}
          <div
            className="flex flex-wrap items-center gap-4 mb-4 px-4 py-2.5 rounded-xl text-xs"
            style={{
              background: "var(--bg-panel)",
              border: "1px solid var(--border-color)",
              color: "var(--text-muted)",
            }}
          >
            <span className="inline-flex items-center gap-1.5">
              <Users size={12} style={{ color: accent }} />
              {data.total_teams} команд активно
            </span>
            <span>·</span>
            <span>средний балл по компании: {data.global_avg}</span>
            <span className="hidden md:inline">·</span>
            <span className="hidden md:inline">
              ранг по skill-adjusted score (Bayesian)
            </span>
          </div>

          {/* Podium — top 3 */}
          {podium.length > 0 && (
            <div className="grid grid-cols-3 gap-3 md:gap-4 items-end mb-5">
              {[2, 1, 3].map((displayRank) => {
                const row = podium.find((r) => r.rank === displayRank);
                if (!row) return <div key={displayRank} />;
                const isFirst = row.rank === 1;
                const height = isFirst ? 170 : row.rank === 2 ? 140 : 120;
                const crown = RANK_CROWN[row.rank];
                const mine = myRow?.team_id === row.team_id;
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
                      style={{ color: "var(--text-primary)" }}
                    >
                      {row.score.toFixed(1)}
                    </div>
                    <div
                      className="text-[10px] uppercase tracking-wider"
                      style={{ color: "var(--text-muted)" }}
                    >
                      adj · raw {row.avg_score.toFixed(1)}
                    </div>
                  </motion.div>
                );
              })}
            </div>
          )}

          {/* Tail */}
          {tail.length > 0 && (
            <div
              className="rounded-2xl overflow-hidden"
              style={{
                background: "var(--bg-panel)",
                border: "1px solid var(--border-color)",
              }}
            >
              {tail.map((row) => (
                <TeamRowItem
                  key={row.team_id}
                  row={row}
                  mine={myRow?.team_id === row.team_id}
                  accent={accent}
                />
              ))}
            </div>
          )}

          {/* Pinned: my team if outside top-10 */}
          {myRow && (
            <div
              className="rounded-2xl overflow-hidden mt-3"
              style={{
                background: `${accent}10`,
                border: `1px solid ${accent}55`,
              }}
            >
              <div
                className="px-4 py-1.5 text-[10px] uppercase tracking-widest font-semibold"
                style={{ color: accent }}
              >
                Твоя команда
              </div>
              <TeamRowItem row={myRow} mine accent={accent} />
            </div>
          )}
        </>
      )}
    </div>
  );
}

function TeamRowItem({
  row,
  mine,
  accent,
}: {
  row: TeamRow;
  mine: boolean;
  accent: string;
}) {
  return (
    <motion.div
      layout
      className="grid grid-cols-[48px_minmax(0,1fr)_auto_auto] items-center gap-3 px-4 py-3"
      style={{
        background: mine ? `${accent}10` : "transparent",
        borderBottom: "1px solid rgba(255,255,255,0.04)",
      }}
    >
      <span
        className="font-mono font-semibold tabular-nums"
        style={{ color: mine ? accent : "var(--text-primary)" }}
      >
        #{row.rank}
      </span>
      <div className="min-w-0">
        <div
          className="text-sm font-medium truncate"
          style={{ color: mine ? accent : "var(--text-primary)" }}
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
          {row.active_members} игроков · {row.total_sessions} сессий
        </div>
      </div>
      <div
        className="flex items-center gap-1 text-sm font-mono tabular-nums"
        style={{ color: mine ? accent : "var(--text-primary)" }}
      >
        <TrendingUp size={12} style={{ color: accent, opacity: 0.7 }} />
        {row.score.toFixed(1)}
      </div>
      <div
        className="text-[11px] font-mono tabular-nums hidden sm:block"
        style={{ color: "var(--text-muted)" }}
      >
        raw {row.avg_score.toFixed(1)}
      </div>
    </motion.div>
  );
}
