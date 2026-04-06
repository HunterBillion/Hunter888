"use client";

import { useMemo } from "react";
import { motion } from "framer-motion";
import { Trophy, Swords, Clock, Check, Minus, Shield } from "lucide-react";
import type { BracketData, BracketMatchData } from "@/stores/useTournamentStore";

function getRoundLabel(roundNum: number, totalRounds: number): string {
  const fromEnd = totalRounds - roundNum;
  if (fromEnd === 0) return "Финал";
  if (fromEnd === 1) return "Полуфинал";
  if (fromEnd === 2) return "1/4 финала";
  if (fromEnd === 3) return "1/8 финала";
  return `Раунд ${roundNum}`;
}

function MatchCard({
  match,
  isCurrentRound,
}: {
  match: BracketMatchData;
  isCurrentRound: boolean;
}) {
  const isCompleted = match.status === "completed" || match.status === "bye";
  const isPending = match.status === "pending";
  const isActive = match.status === "active";

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      className={`cyber-card overflow-hidden ${isActive ? "neon-pulse" : ""}`}
      style={{ minWidth: 190, ["--_accent-alpha" as string]: isCompleted ? "0.25" : isActive ? "0.4" : "0.1" }}
    >
      {/* Player 1 */}
      <PlayerRow
        name={match.player1_name}
        score={match.player1_score}
        isWinner={match.winner_id !== null && match.winner_id === match.player1_id}
        isCompleted={isCompleted}
      />
      <div style={{ height: 1, background: "var(--glass-border)" }} />
      {/* Player 2 */}
      <PlayerRow
        name={match.player2_name}
        score={match.player2_score}
        isWinner={match.winner_id !== null && match.winner_id === match.player2_id}
        isCompleted={isCompleted}
      />
      {/* Status badge */}
      <div className="flex items-center justify-center py-1.5">
        {isCompleted ? (
          <span className="status-badge status-badge--online">
            <Check size={8} /> ЗАВЕРШЁН
          </span>
        ) : isActive ? (
          <span className="status-badge status-badge--warning">
            <Swords size={8} /> ИДЁТ БОЙ
          </span>
        ) : (
          <span className="status-badge status-badge--neutral">
            <Clock size={8} /> ОЖИДАНИЕ
          </span>
        )}
      </div>
    </motion.div>
  );
}

function PlayerRow({
  name,
  score,
  isWinner,
  isCompleted,
}: {
  name: string;
  score: number | null;
  isWinner: boolean;
  isCompleted: boolean;
}) {
  const isTBD = name === "TBD";
  const isBye = name === "BYE";

  return (
    <div
      className="flex items-center gap-2 px-3 py-2"
      style={{
        background: isWinner ? "rgba(0,255,148,0.07)" : "transparent",
      }}
    >
      {isWinner && <Trophy size={13} style={{ color: "var(--neon-green)" }} className="shrink-0" />}
      {!isWinner && isCompleted && <Minus size={13} style={{ color: "var(--text-muted)" }} className="shrink-0" />}
      <span
        className="text-xs font-mono truncate flex-1"
        style={{
          color: isTBD || isBye ? "var(--text-muted)" : isWinner ? "var(--text-primary)" : "var(--text-secondary)",
          fontStyle: isTBD || isBye ? "italic" : "normal",
        }}
      >
        {name}
      </span>
      {score !== null && (
        <span className="stat-chip" style={{ ["--stat-color" as string]: isWinner ? "var(--neon-green)" : "var(--text-muted)" }}>
          <span className="stat-chip__value" style={{ color: isWinner ? "var(--neon-green)" : "var(--text-muted)" }}>
            {Math.round(score)}
          </span>
        </span>
      )}
    </div>
  );
}

interface Props {
  bracket: BracketData;
}

export function BracketView({ bracket }: Props) {
  const roundNumbers = useMemo(
    () => Object.keys(bracket.rounds).map(Number).sort((a, b) => a - b),
    [bracket.rounds],
  );

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center gap-2">
        <Shield size={16} style={{ color: "var(--accent)" }} />
        <span className="badge-neon">
          СЕТКА ТУРНИРА
        </span>
        <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
          {bracket.bracket_size} участников · {bracket.total_rounds} раундов
        </span>
      </div>

      {/* Bracket grid — horizontal scroll */}
      <div className="overflow-x-auto pb-4">
        <div className="flex gap-6" style={{ minWidth: roundNumbers.length * 220 }}>
          {roundNumbers.map((rnd) => {
            const matches = bracket.rounds[String(rnd)] || [];
            const isCurrentRound = rnd === bracket.current_round;

            return (
              <div key={rnd} className="flex-shrink-0" style={{ width: 210 }}>
                {/* Round header */}
                <div
                  className={`text-center text-xs font-mono tracking-wider mb-3 py-1.5 rounded ${isCurrentRound ? "badge-neon" : ""}`}
                  style={
                    isCurrentRound
                      ? {}
                      : { color: "var(--text-muted)", background: "transparent", border: "1px solid var(--glass-border)" }
                  }
                >
                  {getRoundLabel(rnd, bracket.total_rounds)}
                </div>

                {/* Matches in this round */}
                <div
                  className="flex flex-col justify-around"
                  style={{ gap: rnd === 1 ? 8 : 8 * Math.pow(2, rnd - 1) }}
                >
                  {matches.map((match) => (
                    <MatchCard
                      key={match.id}
                      match={match}
                      isCurrentRound={isCurrentRound}
                    />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Winner announcement */}
      {!bracket.is_active && bracket.participants.some((p) => p.final_placement === 1) && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="glow-card"
        >
          <div className="glow-card-inner rounded-xl p-6 text-center">
            <Trophy size={32} className="mx-auto mb-2 neon-pulse" style={{ color: "var(--neon-amber, #FFD700)" }} />
            <div className="font-display text-xl font-bold" style={{ color: "var(--neon-amber, #FFD700)" }}>
              {bracket.participants.find((p) => p.final_placement === 1)?.full_name}
            </div>
            <div className="badge-neon mt-2" style={{ display: "inline-block" }}>
              ПОБЕДИТЕЛЬ ТУРНИРА
            </div>
          </div>
        </motion.div>
      )}

      {/* Participants list */}
      <div className="glass-panel rounded-xl p-4">
        <div className="text-xs font-mono tracking-wider mb-3 flex items-center gap-2" style={{ color: "var(--text-muted)" }}>
          <Swords size={13} style={{ color: "var(--accent)" }} />
          УЧАСТНИКИ ({bracket.participants.length})
        </div>
        <div className="grid grid-cols-2 gap-1.5">
          {bracket.participants.map((p) => {
            const isPodium = p.final_placement && p.final_placement <= 3;
            return (
              <div
                key={p.user_id}
                className="flex items-center gap-2 rounded-lg px-2.5 py-2"
                style={{
                  background: isPodium
                    ? "rgba(255,215,0,0.05)"
                    : "var(--glass-bg)",
                  border: `1px solid ${
                    p.eliminated_at_round
                      ? "rgba(255,42,109,0.12)"
                      : isPodium
                        ? "rgba(255,215,0,0.15)"
                        : "var(--glass-border)"
                  }`,
                }}
              >
                <span
                  className="text-xs font-mono w-5 text-center font-bold"
                  style={{ color: "var(--accent)" }}
                >
                  #{p.seed ?? "-"}
                </span>
                <span
                  className="text-xs font-mono truncate flex-1"
                  style={{
                    color: p.eliminated_at_round ? "var(--text-muted)" : "var(--text-secondary)",
                    textDecoration: p.eliminated_at_round ? "line-through" : "none",
                  }}
                >
                  {p.full_name}
                </span>
                {isPodium && (
                  <span className="text-xs">
                    {p.final_placement === 1 ? "🥇" : p.final_placement === 2 ? "🥈" : "🥉"}
                  </span>
                )}
                {p.eliminated_at_round && !isPodium && (
                  <span className="status-badge status-badge--danger" style={{ fontSize: "12px", padding: "1px 4px" }}>
                    R{p.eliminated_at_round}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
