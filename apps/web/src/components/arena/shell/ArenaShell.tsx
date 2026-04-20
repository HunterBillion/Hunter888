"use client";

/**
 * ArenaShell — unified layout for ALL 5 PvP modes (arena/duel/rapid/pve/tournament).
 *
 * Sprint 1 (2026-04-20). Before this component each mode had its own
 * page with its own header, scoreboard, and input. User complaint: "все
 * режимы должны быть похожи визуально". Fix: one shell, five slots,
 * mode-specific theme.
 *
 * Layout:
 *   +---------------------------------------------------+
 *   |           Header (timer, mode badge, exit)        |
 *   +-------+-----------------------------+-------------+
 *   | Score | Main round panel            | Progress    |
 *   | board |  (question / answer reveal) | HUD         |
 *   | (L)   |                             | (R)         |
 *   +-------+-----------------------------+-------------+
 *   | Footer: ArenaAnswerInput (mic + input + lifelines) |
 *   +---------------------------------------------------+
 *
 * On mobile the 3-column layout collapses to a vertical stack with the
 * scoreboard moving into a drawer (not implemented this sprint, but the
 * slot contract makes it easy to add later).
 */

import { motion } from "framer-motion";
import { LogOut, Volume2, VolumeX } from "lucide-react";
import { useEffect, useState } from "react";

import type { ArenaMode } from "@/components/arena/themes";
import { themeFor } from "@/components/arena/themes";
import { useSFX } from "@/components/arena/sfx/useSFX";

interface Props {
  mode: ArenaMode;
  /** Current round number, for the header centre pill. */
  roundNumber?: number;
  /** Total rounds in the match — when provided renders "N / total". */
  totalRounds?: number;
  /** Seconds remaining on round timer (null = hide). */
  timeLeftSec?: number | null;
  /** Handler for the top-right exit button. */
  onExit?: () => void;
  /** Slot content. */
  scoreboard?: React.ReactNode;
  hud?: React.ReactNode;
  main: React.ReactNode;
  footer?: React.ReactNode;
  /** Full-screen overlays (reveal, celebration, round transition). */
  overlays?: React.ReactNode;
}

export function ArenaShell({
  mode,
  roundNumber,
  totalRounds,
  timeLeftSec,
  onExit,
  scoreboard,
  hud,
  main,
  footer,
  overlays,
}: Props) {
  const theme = themeFor(mode);
  const sfx = useSFX();
  const [muted, setMuted] = useState<boolean>(false);

  // Prime SFX pack on mount so first play has zero latency.
  useEffect(() => {
    sfx.prime();
    setMuted(sfx.isMuted());
  }, [sfx]);

  const timeClass = (timeLeftSec ?? 99) <= 10 ? "animate-pulse" : "";
  const timeColor =
    (timeLeftSec ?? 99) <= 10 ? "var(--danger)" : theme.accent;

  return (
    <div
      className="flex flex-col h-screen overflow-hidden"
      style={{
        background: "var(--bg-primary)",
        color: "var(--text-primary)",
      }}
    >
      {/* ── Header ───────────────────────────────────────────────── */}
      <div
        className="flex items-center justify-between px-4 md:px-6 py-3 glass-panel"
        style={{
          borderBottom: `1px solid ${theme.accent}33`,
          background: `linear-gradient(180deg, ${theme.accent}08 0%, transparent 100%)`,
        }}
      >
        <div className="flex items-center gap-3">
          {onExit && (
            <button
              onClick={onExit}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors"
              style={{
                background: "var(--danger-muted)",
                color: "var(--danger)",
                border: "1px solid var(--danger-muted)",
              }}
              title="Выйти"
            >
              <LogOut size={14} />
              Выход
            </button>
          )}
          <div className="hidden sm:block">
            <div
              className="text-xs font-semibold uppercase tracking-wider"
              style={{ color: theme.accent }}
            >
              {theme.label}
            </div>
            <div
              className="text-[10px] uppercase tracking-wider opacity-70"
              style={{ color: "var(--text-muted)" }}
            >
              {theme.tagline}
            </div>
          </div>
        </div>

        {/* Centre: round counter */}
        {roundNumber !== undefined && (
          <div
            className="hidden md:flex items-center gap-2 rounded-full px-3 py-1"
            style={{
              background: `${theme.accent}14`,
              border: `1px solid ${theme.accent}33`,
            }}
          >
            <span
              className="text-[10px] font-semibold uppercase tracking-wider"
              style={{ color: "var(--text-muted)" }}
            >
              Раунд
            </span>
            <span
              className="font-mono font-bold tabular-nums"
              style={{ color: theme.accent }}
            >
              {roundNumber}
              {totalRounds ? ` / ${totalRounds}` : ""}
            </span>
          </div>
        )}

        {/* Right: timer + mute */}
        <div className="flex items-center gap-3">
          {timeLeftSec !== null && timeLeftSec !== undefined && (
            <div
              className={`text-lg font-mono font-bold tabular-nums ${timeClass}`}
              style={{ color: timeColor, letterSpacing: "-0.02em" }}
            >
              {Math.floor(timeLeftSec / 60)}:
              {String(timeLeftSec % 60).padStart(2, "0")}
            </div>
          )}
          <button
            onClick={() => {
              const next = sfx.toggleMute();
              setMuted(next);
            }}
            className="flex items-center justify-center h-8 w-8 rounded-lg transition-colors"
            style={{
              background: "var(--input-bg)",
              color: muted ? "var(--text-muted)" : theme.accent,
              border: "1px solid var(--border-color)",
            }}
            title={muted ? "Включить звук" : "Выключить звук"}
            aria-label={muted ? "Unmute" : "Mute"}
          >
            {muted ? <VolumeX size={15} /> : <Volume2 size={15} />}
          </button>
        </div>
      </div>

      {/* ── Body: 3-column grid ─────────────────────────────────── */}
      <div className="flex-1 grid grid-cols-1 md:grid-cols-[220px_minmax(0,1fr)_240px] gap-0 overflow-hidden">
        {/* Left — scoreboard */}
        <aside
          className="hidden md:block overflow-y-auto p-3 border-r"
          style={{ borderColor: "var(--border-color)" }}
        >
          {scoreboard}
        </aside>

        {/* Centre — main panel */}
        <motion.main
          className="overflow-y-auto px-4 md:px-6 py-5"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25 }}
        >
          {main}
        </motion.main>

        {/* Right — progress HUD */}
        <aside
          className="hidden md:block overflow-y-auto p-3 border-l"
          style={{ borderColor: "var(--border-color)" }}
        >
          {hud}
        </aside>
      </div>

      {/* ── Footer (answer input) ───────────────────────────────── */}
      {footer && (
        <div
          className="shrink-0 px-3 md:px-6 py-3 border-t"
          style={{
            borderColor: `${theme.accent}22`,
            background: `linear-gradient(0deg, ${theme.accent}05 0%, transparent 100%)`,
          }}
        >
          {footer}
        </div>
      )}

      {/* ── Overlays (reveal, celebration, round transition) ───── */}
      {overlays}
    </div>
  );
}
