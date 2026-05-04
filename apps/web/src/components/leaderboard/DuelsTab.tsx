"use client";

/**
 * DuelsTab — unified PvP-duel leaderboard.
 *
 * Replaces two empty-feeling tabs (Арена + Знания) with one tab and a
 * mode toggle (Голосовые дуэли · Дуэли знаний). Both are ELO-based but
 * served by separate endpoints. Empty states have a real CTA into the
 * relevant duel surface instead of a dead-end "никто не сыграл" line.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, Mic, BookOpen, Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { logger } from "@/lib/logger";
import {
  PodiumCard,
  type PodiumEntry,
} from "@/components/leaderboard/PodiumCard";
import {
  LeaderboardTable,
  type LeaderboardRow,
} from "@/components/leaderboard/LeaderboardTable";

type Mode = "voice" | "knowledge";

const MODES: {
  key: Mode;
  label: string;
  icon: typeof Mic;
  ctaHref: string;
  ctaLabel: string;
  emptyTitle: string;
  emptyBody: string;
}[] = [
  {
    key: "voice",
    label: "Голос",
    icon: Mic,
    ctaHref: "/pvp",
    ctaLabel: "Найти соперника",
    emptyTitle: "В голосовой арене ещё никто не сыграл",
    emptyBody: "Стань первым — найди соперника и выйграй дуэль 1-на-1.",
  },
  {
    key: "knowledge",
    label: "Знания",
    icon: BookOpen,
    ctaHref: "/pvp",
    ctaLabel: "Открыть квиз",
    emptyTitle: "Дуэли знаний ещё не запущены",
    emptyBody: "Пройди квиз по 127-ФЗ — баллы попадут в этот рейтинг.",
  },
];

interface RawArenaEntry {
  rank: number;
  user_id: string;
  full_name: string;
  rating: number;
  rank_tier?: string;
}

interface ArenaResp {
  entries?: RawArenaEntry[];
}

interface RawKnowledgeEntry {
  rank: number;
  user_id: string;
  full_name: string;
  rating: number;
}

export function DuelsTab() {
  const { user } = useAuth();
  const [mode, setMode] = useState<Mode>("voice");
  const [voiceRows, setVoiceRows] = useState<LeaderboardRow[] | null>(null);
  const [knowledgeRows, setKnowledgeRows] = useState<LeaderboardRow[] | null>(null);
  const [loading, setLoading] = useState(false);

  const meta = useMemo(() => MODES.find((m) => m.key === mode)!, [mode]);

  const load = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    try {
      if (mode === "voice" && voiceRows === null) {
        const data = await api.get<ArenaResp>("/pvp/leaderboard?limit=50");
        const entries = data?.entries ?? [];
        setVoiceRows(
          entries.map((e) => ({
            rank: e.rank,
            user_id: e.user_id,
            full_name: e.full_name,
            score: e.rating,
            subtitle: e.rank_tier ? String(e.rank_tier).toUpperCase() : null,
            is_me: e.user_id === user.id,
          })),
        );
      }
      if (mode === "knowledge" && knowledgeRows === null) {
        const data = await api.get<RawKnowledgeEntry[]>(
          "/knowledge/arena/leaderboard?limit=50",
        );
        const arr = Array.isArray(data) ? data : [];
        setKnowledgeRows(
          arr.map((e) => ({
            rank: e.rank,
            user_id: e.user_id,
            full_name: e.full_name,
            score: e.rating,
            is_me: e.user_id === user.id,
          })),
        );
      }
    } catch (err) {
      logger.error(`duels leaderboard load failed (${mode}):`, err);
      if (mode === "voice") setVoiceRows([]);
      if (mode === "knowledge") setKnowledgeRows([]);
    } finally {
      setLoading(false);
    }
  }, [mode, user, voiceRows, knowledgeRows]);

  useEffect(() => {
    load();
  }, [load]);

  const rows = mode === "voice" ? voiceRows : knowledgeRows;
  const podium: PodiumEntry[] = useMemo(
    () =>
      (rows ?? []).slice(0, 3).map((r) => ({
        user_id: r.user_id,
        full_name: r.full_name,
        avatar_url: r.avatar_url ?? null,
        score: r.score,
        scoreUnit: "ELO",
      })),
    [rows],
  );

  return (
    <div className="space-y-5">
      {/* Mode switch */}
      <div
        className="inline-flex rounded-xl p-1 gap-1"
        style={{
          background: "rgba(255,255,255,0.04)",
          border: "1px solid rgba(255,255,255,0.06)",
        }}
      >
        {MODES.map((m) => {
          const Icon = m.icon;
          const active = mode === m.key;
          return (
            <button
              key={m.key}
              type="button"
              onClick={() => setMode(m.key)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold uppercase tracking-wider transition-all"
              style={{
                background: active ? "var(--accent)" : "transparent",
                color: active ? "#fff" : "var(--text-muted)",
              }}
            >
              <Icon size={13} />
              {m.label}
            </button>
          );
        })}
      </div>

      {loading || rows === null ? (
        <div className="flex items-center justify-center py-16">
          <Loader2
            size={24}
            className="animate-spin"
            style={{ color: "var(--accent)" }}
          />
        </div>
      ) : rows.length === 0 ? (
        <EmptyCta meta={meta} />
      ) : (
        <>
          {podium.length >= 3 && (
            <PodiumCard
              top3={podium}
              title={
                mode === "voice" ? "Топ-3 голосовых дуэлянтов" : "Топ-3 знатоков"
              }
            />
          )}
          <LeaderboardTable rows={rows} scoreUnit="ELO" />
        </>
      )}
    </div>
  );
}

function EmptyCta({ meta }: { meta: (typeof MODES)[number] }) {
  const Icon = meta.icon;
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
        <Icon size={22} />
      </div>
      <h3
        className="text-base font-semibold mb-1"
        style={{ color: "var(--text-primary)" }}
      >
        {meta.emptyTitle}
      </h3>
      <p
        className="text-sm mb-4 max-w-md mx-auto"
        style={{ color: "var(--text-muted)" }}
      >
        {meta.emptyBody}
      </p>
      <a
        href={meta.ctaHref}
        className="inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-semibold"
        style={{ background: "var(--accent)", color: "#fff" }}
      >
        <Sparkles size={14} />
        {meta.ctaLabel}
      </a>
    </div>
  );
}
