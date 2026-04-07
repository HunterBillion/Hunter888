"use client";

import { ArrowRight, BookOpen, CheckCircle, Clock, AlertTriangle, Sparkles, Trophy, Phone } from "lucide-react";
import Link from "next/link";
import type { GameStory } from "@/types";
import { GAME_STATUS_LABELS, GAME_STATUS_COLORS } from "@/types";

interface GameStoryCardProps {
  story: GameStory;
}

export function GameStoryCard({ story }: GameStoryCardProps) {
  const color = GAME_STATUS_COLORS[story.game_status] || "var(--text-muted)";
  const statusLabel = GAME_STATUS_LABELS[story.game_status] || story.game_status;

  const progressPct = story.total_calls_planned > 0
    ? Math.round((story.current_call_number / story.total_calls_planned) * 100)
    : 0;

  return (
    <Link href={`/training/crm/${story.id}`}>
      <div
        className="group rounded-[24px] p-5 transition-all duration-200 hover:-translate-y-1"
        style={{
          background: "linear-gradient(180deg, rgba(7,7,9,0.96), rgba(14,14,18,0.94))",
          border: "1px solid rgba(255,255,255,0.08)",
          boxShadow: "0 18px 50px rgba(0,0,0,0.28)",
        }}
      >
        <div
          className="mb-4 rounded-2xl p-3"
          style={{
            background: `radial-gradient(circle at top left, ${color}18, transparent 55%), rgba(255,255,255,0.02)`,
            border: "1px solid rgba(255,255,255,0.06)",
          }}
        >
          <div className="mb-3 flex items-center justify-between gap-2">
            <span className="font-mono text-xs uppercase tracking-[0.24em]" style={{ color: "var(--text-muted)" }}>
              Client Story
            </span>
            <span
              className="rounded-full px-2.5 py-1 text-xs font-mono"
              style={{
                background: `${color}15`,
                color,
                border: `1px solid ${color}35`,
              }}
            >
              {statusLabel}
            </span>
          </div>

          <div className="flex items-start gap-3">
            <div
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl"
              style={{ background: `${color}16`, border: `1px solid ${color}30` }}
            >
              <BookOpen size={16} style={{ color }} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-lg font-semibold leading-tight" style={{ color: "var(--text-primary)" }}>
                {story.story_name}
              </div>
              <div className="mt-1 flex flex-wrap gap-2">
                <span className="inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-mono" style={{ background: "rgba(255,255,255,0.04)", color: "var(--text-muted)" }}>
                  <Phone size={10} />
                  {story.calls_completed}/{story.total_calls_planned}
                </span>
                {story.avg_score !== null && (
                  <span className="inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-mono" style={{ background: "rgba(255,255,255,0.04)", color: "var(--text-muted)" }}>
                    <Trophy size={10} />
                    {Math.round(story.avg_score)}/100
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="flex items-start justify-between gap-2">
          <div>
            <div className="font-mono text-xs uppercase tracking-[0.2em]" style={{ color: "var(--text-muted)" }}>
              Progress Matrix
            </div>
            <div className="mt-1 text-sm" style={{ color: "var(--text-secondary)" }}>
              История клиента, событий: {story.event_count}
            </div>
          </div>
          <ArrowRight size={16} className="transition-transform group-hover:translate-x-1" style={{ color: "var(--text-muted)" }} />
        </div>

        <div className="mt-3">
          <div className="flex items-center justify-between mb-1">
            <span
              className="text-xs font-mono"
              style={{ color: "var(--text-muted)" }}
            >
              Звонок {story.current_call_number} / {story.total_calls_planned}
            </span>
            <span
              className="text-xs font-mono"
              style={{ color: "var(--text-muted)" }}
            >
              {progressPct}%
            </span>
          </div>
          <div
            className="h-1.5 rounded-full overflow-hidden"
            style={{ background: "var(--input-bg)" }}
          >
            <div
              className="h-full rounded-full transition-all duration-300"
              style={{
                width: `${Math.max(progressPct, 2)}%`,
                background: `linear-gradient(90deg, ${color}, rgba(255,255,255,0.92))`,
              }}
            />
          </div>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-2">
          <div className="rounded-2xl p-3" style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.05)" }}>
            <div className="font-mono text-xs uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
              Tension
            </div>
            <div className="mt-1 text-lg font-semibold" style={{ color }}>
              {(story.tension * 10).toFixed(0)}/10
            </div>
          </div>
          <div className="rounded-2xl p-3" style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.05)" }}>
            <div className="font-mono text-xs uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
              Best Score
            </div>
            <div className="mt-1 text-lg font-semibold" style={{ color: "var(--text-primary)" }}>
              {story.best_score !== null ? Math.round(story.best_score) : "—"}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3 mt-4 flex-wrap">
          {story.tension > 0 && (
            <span
              className="flex items-center gap-1 text-xs font-mono"
              style={{ color: "var(--text-muted)" }}
            >
              <AlertTriangle size={10} />
              Напряжение: {(story.tension * 10).toFixed(0)}/10
            </span>
          )}
          {story.event_count > 0 && (
            <span
              className="flex items-center gap-1 text-xs font-mono"
              style={{ color: "var(--text-muted)" }}
            >
              <Clock size={10} />
              {story.event_count} событий
            </span>
          )}
          {story.is_completed && (
            <span
              className="flex items-center gap-1 text-xs font-mono"
              style={{ color: "var(--neon-green)" }}
            >
              <CheckCircle size={10} />
              Завершена
            </span>
          )}
          {!story.is_completed && (
            <span className="flex items-center gap-1 text-xs font-mono" style={{ color: "var(--accent)" }}>
              <Sparkles size={10} />
              Активная continuity
            </span>
          )}
        </div>
      </div>
    </Link>
  );
}
