"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import {
  Loader2,
  ArrowRight,
  CheckCircle2,
} from "lucide-react";
import {
  BookOpen,
  Sword,
  TrendUp,
  Warning,
  Lightbulb,
  Brain,
  Clock,
  Flame,
} from "@phosphor-icons/react";
import Link from "next/link";
import { api } from "@/lib/api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface CategoryProgress {
  category: string;
  display_name: string;
  accuracy: number;
  total_answered: number;
  correct_answers: number;
}

interface PvPStats {
  rating: number;
  rank_tier: string;
  wins: number;
  losses: number;
  current_streak: number;
}

interface Recommendation {
  category: string;
  accuracy: number;
  recommendation: string;
  priority: string;
  suggested_action: string;
}

interface SrsStats {
  total_cards: number;
  overdue: number;
  mastered: number;
  learning: number;
  avg_ease_factor: number;
}

interface KnowledgeStats {
  overall_accuracy: number;
  total_quizzes: number;
  category_progress: CategoryProgress[];
  pvp_stats: PvPStats;
  weak_areas: string[];
  recommendations: Recommendation[];
  recent_sessions: Array<{
    id: string;
    mode: string;
    score: number;
    correct: number;
    total: number;
    date: string | null;
  }>;
}

// ---------------------------------------------------------------------------
// Rank display helpers
// ---------------------------------------------------------------------------

/** Normalize backend rank_tier (e.g. "gold_2") to base tier ("gold") for lookups */
function normalizeRankTierLocal(raw: string): string {
  return raw.replace(/_[123]$/, "");
}

const RANK_COLORS: Record<string, string> = {
  unranked: "var(--text-muted)",
  iron: "var(--text-muted)",
  bronze: "var(--rank-bronze)",
  silver: "var(--rank-silver)",
  gold: "var(--rank-gold)",
  platinum: "var(--rank-platinum)",
  diamond: "var(--rank-diamond)",
  master: "var(--rank-master, var(--danger))",
  grandmaster: "var(--rank-grandmaster, var(--warning))",
};

const RANK_NAMES: Record<string, string> = {
  unranked: "Без ранга",
  iron: "Железо",
  bronze: "Бронза",
  silver: "Серебро",
  gold: "Золото",
  platinum: "Платина",
  diamond: "Алмаз",
  master: "Мастер",
  grandmaster: "Грандмастер",
};

const PRIORITY_COLORS: Record<string, string> = {
  critical: "var(--danger)",
  high: "var(--warning)",
  medium: "var(--accent)",
};

// ---------------------------------------------------------------------------
// ProgressBar component
// ---------------------------------------------------------------------------

function ProgressBar({ value, max = 100 }: { value: number; max?: number }) {
  const pct = max > 0 ? Math.min((value / max) * 100, 100) : 0;
  const color =
    pct >= 80
      ? "var(--success)"
      : pct >= 60
        ? "var(--warning)"
        : pct >= 40
          ? "#FF8C00"
          : "var(--danger)";

  return (
    <div
      className="h-1.5 rounded-full overflow-hidden"
      style={{ background: "var(--bg-secondary)" }}
    >
      <motion.div
        className="h-full rounded-full"
        style={{ background: color }}
        initial={{ width: 0 }}
        animate={{ width: `${pct}%` }}
        transition={{ duration: 0.6, ease: "easeOut" }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main widget
// ---------------------------------------------------------------------------

interface KnowledgeDashboardWidgetProps {
  userId?: string;
}

export function KnowledgeDashboardWidget({ userId }: KnowledgeDashboardWidgetProps) {
  const [data, setData] = useState<KnowledgeStats | null>(null);
  const [srs, setSrs] = useState<SrsStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const params = userId ? `?user_id=${userId}` : "";
    Promise.all([
      api.get(`/dashboard/knowledge-stats${params}`).catch(() => null),
      api.get("/knowledge/srs/stats").catch(() => null),
    ]).then(([statsResp, srsResp]) => {
      if (statsResp) setData(statsResp as KnowledgeStats);
      if (srsResp) setSrs(srsResp as SrsStats);
    }).finally(() => setLoading(false));
  }, [userId]);

  if (loading) {
    return (
      <div className="glass-panel p-5 flex items-center justify-center py-8">
        <Loader2 size={18} className="animate-spin" style={{ color: "var(--accent)" }} />
      </div>
    );
  }

  if (!data) return null;

  const pvp = data.pvp_stats;
  const normalizedTier = normalizeRankTierLocal(pvp?.rank_tier || "unranked");
  const rankColor = RANK_COLORS[normalizedTier] || "var(--text-muted)";

  return (
    <motion.div
      className="glass-panel p-5"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.1 }}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <BookOpen size={16} weight="duotone" style={{ color: "var(--accent)" }} />
          <h3
            className="text-xs font-semibold uppercase tracking-wide"
            style={{ color: "var(--accent)" }}
          >
            ЗНАНИЯ ФЗ-127
          </h3>
        </div>
        {data.total_quizzes > 0 && (
          <span
            className="text-xs font-medium"
            style={{ color: "var(--text-muted)" }}
          >
            {data.total_quizzes} ответов
          </span>
        )}
      </div>

      {/* Overall accuracy */}
      {data.total_quizzes > 0 ? (
        <>
          <div className="mb-4">
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
                Общая точность
              </span>
              <span
                className="text-sm font-mono font-bold"
                style={{
                  color:
                    data.overall_accuracy >= 80
                      ? "var(--success)"
                      : data.overall_accuracy >= 60
                        ? "var(--warning)"
                        : "var(--danger)",
                }}
              >
                {data.overall_accuracy}%
              </span>
            </div>
            <ProgressBar value={data.overall_accuracy} />
          </div>

          {/* Category progress (compact grid) */}
          <div className="grid grid-cols-2 gap-x-4 gap-y-2 mb-4">
            {data.category_progress
              .filter((cp) => cp.total_answered > 0)
              .slice(0, 6)
              .map((cp) => (
                <div key={cp.category}>
                  <div className="flex items-center justify-between mb-0.5">
                    <span
                      className="text-xs truncate"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {cp.display_name}
                    </span>
                    <span
                      className="text-xs font-mono"
                      style={{ color: "var(--text-secondary)" }}
                    >
                      {cp.accuracy}%
                    </span>
                  </div>
                  <ProgressBar value={cp.accuracy} />
                </div>
              ))}
          </div>

          {/* PvP Stats */}
          {pvp && (
            <div
              className="flex items-center gap-3 mb-4 p-2 rounded"
              style={{ background: "var(--bg-secondary)" }}
            >
              <Sword size={14} weight="duotone" style={{ color: rankColor }} />
              <span className="text-xs font-mono" style={{ color: rankColor }}>
                {Math.round(pvp.rating)} ELO
              </span>
              <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                {RANK_NAMES[normalizedTier] || pvp.rank_tier}
              </span>
              <span className="text-xs font-mono" style={{ color: "var(--text-secondary)" }}>
                {pvp.wins}W {pvp.losses}L
              </span>
              {pvp.current_streak > 0 && (
                <span className="text-xs" style={{ color: "var(--gf-streak)" }}>
                  <Flame size={14} weight="duotone" className="inline" /> {pvp.current_streak}
                </span>
              )}
            </div>
          )}

          {/* SRS Spaced Repetition stats */}
          {srs && srs.total_cards > 0 && (
            <div
              className="flex items-center gap-3 mb-4 p-2.5 rounded-lg"
              style={{ background: "var(--bg-secondary)", border: "1px solid var(--glass-border)" }}
            >
              <Brain size={14} weight="duotone" style={{ color: "var(--accent)" }} />
              <div className="flex-1 grid grid-cols-3 gap-2">
                <div className="text-center">
                  <div className="text-xs font-mono font-bold" style={{ color: srs.overdue > 0 ? "var(--danger)" : "var(--success)" }}>
                    {srs.overdue}
                  </div>
                  <div className="text-xs font-semibold" style={{ color: "var(--text-muted)" }}>ПОВТОР</div>
                </div>
                <div className="text-center">
                  <div className="text-xs font-mono font-bold" style={{ color: "var(--accent)" }}>
                    {srs.learning}
                  </div>
                  <div className="text-xs font-semibold" style={{ color: "var(--text-muted)" }}>УЧЁБА</div>
                </div>
                <div className="text-center">
                  <div className="text-xs font-mono font-bold" style={{ color: "var(--success)" }}>
                    {srs.mastered}
                  </div>
                  <div className="text-xs font-semibold" style={{ color: "var(--text-muted)" }}>УСВОЕНО</div>
                </div>
              </div>
              {srs.overdue > 0 && (
                <Link href="/pvp?tab=knowledge">
                  <span className="status-badge status-badge--danger" style={{ fontSize: "14px", cursor: "pointer" }}>
                    <Clock size={8} weight="duotone" /> {srs.overdue} просрочено
                  </span>
                </Link>
              )}
            </div>
          )}

          {/* Weak areas warning */}
          {data.weak_areas.length > 0 && (
            <div className="flex items-start gap-2 mb-3">
              <Warning
                size={12}
                weight="duotone"
                className="mt-0.5 flex-shrink-0"
                style={{ color: "var(--warning)" }}
              />
              <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
                Слабые темы:{" "}
                {data.weak_areas
                  .map((w) => {
                    const displayNames: Record<string, string> = {
                      eligibility: "Условия подачи",
                      procedure: "Процедура",
                      property: "Имущество",
                      consequences: "Последствия",
                      costs: "Стоимость",
                      creditors: "Кредиторы",
                      documents: "Документы",
                      timeline: "Сроки",
                      court: "Суд",
                      rights: "Права",
                    };
                    return displayNames[w] || w;
                  })
                  .join(", ")}
              </span>
            </div>
          )}

          {/* Recommendations */}
          {data.recommendations.length > 0 && (
            <div className="space-y-1.5 mb-4">
              {data.recommendations.slice(0, 2).map((rec, i) => (
                <div key={i} className="flex items-start gap-2">
                  <Lightbulb
                    size={11}
                    weight="duotone"
                    className="mt-0.5 flex-shrink-0"
                    style={{ color: PRIORITY_COLORS[rec.priority] || "var(--accent)" }}
                  />
                  <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
                    {rec.recommendation}
                  </span>
                </div>
              ))}
            </div>
          )}
        </>
      ) : (
        /* Empty state */
        <div className="text-center py-4">
          <BookOpen
            size={24}
            weight="duotone"
            className="mx-auto mb-2"
            style={{ color: "var(--text-muted)", opacity: 0.5 }}
          />
          <p className="text-xs" style={{ color: "var(--text-muted)" }}>
            Пройдите первый тест знаний по ФЗ-127
          </p>
        </div>
      )}

      {/* Action buttons */}
      <div className="flex gap-2">
        <Link href="/pvp?tab=knowledge" className="flex-1">
          <button
            className="w-full flex items-center justify-center gap-1.5 py-2 rounded text-xs font-medium transition-colors"
            style={{
              background: "var(--accent)",
              color: "var(--bg-primary)",
            }}
          >
            Пройти тест
            <ArrowRight size={12} />
          </button>
        </Link>
        <Link href="/pvp?tab=knowledge">
          <button
            className="flex items-center justify-center gap-1.5 px-3 py-2 rounded text-xs font-medium transition-colors"
            style={{
              border: "1px solid var(--border)",
              color: "var(--text-secondary)",
            }}
          >
            Арена
          </button>
        </Link>
      </div>
    </motion.div>
  );
}
