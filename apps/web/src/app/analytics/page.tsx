"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Activity,
  AlertTriangle,
  ArrowDown,
  ArrowRight,
  ArrowUp,
  BarChart3,
  Brain,
  ChevronDown,
  Crown,
  Flame,
  Lightbulb,
  Loader2,
  Minus,
  Radar,
  ShieldAlert,
  Sparkles,
  Target,
  TrendingDown,
  TrendingUp,
  Zap,
} from "lucide-react";
import { api } from "@/lib/api";
import { scoreColor } from "@/lib/utils";
import { useAuth } from "@/hooks/useAuth";
import AuthLayout from "@/components/layout/AuthLayout";
import { BackButton } from "@/components/ui/BackButton";
import { AnalyticsSkeleton } from "@/components/ui/Skeleton";
import { logger } from "@/lib/logger";
import type {
  WeakSpot,
  ProgressPoint,
  ArchetypeScore,
  Recommendation,
  AnalyticsSnapshot,
} from "@/types";

interface Snapshot extends AnalyticsSnapshot {
  meta: AnalyticsSnapshot["meta"] & {
    total_sessions: number;
    avg_score: number;
    days_active: number;
    analysis_window_sessions: number;
  };
}

// ── Constants ───────────────────────────────────────────────────────────────

const SKILL_LABELS: Record<string, string> = {
  script_adherence: "Скрипт",
  objection_handling: "Возражения",
  communication: "Коммуникация",
  anti_patterns: "Антипаттерны",
  result: "Результат",
};

const SKILL_COLORS: Record<string, string> = {
  script_adherence: "var(--accent, #8A2BE2)",
  objection_handling: "var(--info)",
  communication: "var(--success)",
  anti_patterns: "var(--danger)",
  result: "var(--warning)",
};

const MASTERY_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  untrained: { label: "Не тренирован", color: "var(--text-muted)", bg: "var(--input-bg)" },
  beginner: { label: "Новичок", color: "var(--info)", bg: "rgba(59,130,246,0.12)" },
  intermediate: { label: "Средний", color: "#FFD700", bg: "rgba(212,168,75,0.12)" },
  advanced: { label: "Продвинутый", color: "#BF55EC", bg: "rgba(191,85,236,0.12)" },
  mastered: { label: "Мастер", color: "#00FF94", bg: "rgba(61,220,132,0.12)" },
};

const SUB_SKILL_LABELS: Record<string, string> = {
  heard: "Услышать возражение",
  acknowledged: "Присоединиться",
  clarified: "Уточнить причину",
  argued: "Аргументировать",
  checked: "Проверить снятие",
};

// ── Helpers ──────────────────────────────────────────────────────────────────

function TrendIcon({ trend }: { trend: string }) {
  if (trend === "improving") return <TrendingUp size={14} style={{ color: "var(--success)" }} />;
  if (trend === "declining") return <TrendingDown size={14} style={{ color: "var(--danger)" }} />;
  return <Minus size={14} style={{ color: "var(--text-muted)" }} />;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
}

function daysAgo(iso: string | null): string {
  if (!iso) return "никогда";
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
  if (diff === 0) return "сегодня";
  if (diff === 1) return "вчера";
  if (diff < 7) return `${diff} дн. назад`;
  return `${Math.floor(diff / 7)} нед. назад`;
}

// ── Mini bar chart (CSS-only) ───────────────────────────────────────────────

function MiniBar({ value, max, color }: { value: number; max: number; color: string }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div className="h-1.5 w-full rounded-full overflow-hidden" style={{ background: "var(--input-bg)" }}>
      <motion.div
        className="h-full rounded-full"
        style={{ background: color }}
        initial={{ width: 0 }}
        animate={{ width: `${pct}%` }}
        transition={{ duration: 0.8, ease: "easeOut" }}
      />
    </div>
  );
}

// ── Sparkline (CSS-only progress bars) ──────────────────────────────────────

function Sparkline({ points }: { points: ProgressPoint[] }) {
  const active = points.filter((p) => p.sessions_count > 0);
  if (active.length < 2) return <p className="text-xs" style={{ color: "var(--text-muted)" }}>Недостаточно данных</p>;

  const maxVal = Math.max(...active.map((p) => p.avg_total), 1);

  return (
    <div className="flex items-end gap-1 h-20">
      {points.map((p, i) => {
        const h = p.sessions_count > 0 ? Math.max(4, (p.avg_total / maxVal) * 100) : 0;
        return (
          <motion.div
            key={i}
            className="flex-1 rounded-t group relative"
            style={{
              background: p.sessions_count > 0
                ? `linear-gradient(to top, ${scoreColor(p.avg_total)}, transparent)`
                : "var(--input-bg)",
              minWidth: 4,
            }}
            initial={{ height: 0 }}
            animate={{ height: `${h}%` }}
            transition={{ duration: 0.6, delay: i * 0.04 }}
          >
            {p.sessions_count > 0 && (
              <div className="absolute -top-8 left-1/2 -translate-x-1/2 hidden group-hover:block z-10 glass-panel px-2 py-1 text-xs font-mono whitespace-nowrap"
                style={{ color: "var(--text-primary)" }}>
                {p.avg_total.toFixed(0)} ({p.sessions_count} сес.)
              </div>
            )}
          </motion.div>
        );
      })}
    </div>
  );
}

// ── Main page ───────────────────────────────────────────────────────────────

export default function AnalyticsPage() {
  const { user } = useAuth();
  const [data, setData] = useState<Snapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedArch, setExpandedArch] = useState<string | null>(null);

  // Fetch analytics from separate endpoints in parallel
  useEffect(() => {
    Promise.all([
      api.get("/analytics/me/weak-spots").catch((err) => { logger.warn("analytics/weak-spots failed:", err); return []; }),
      api.get("/analytics/me/progress").catch((err) => { logger.warn("analytics/progress failed:", err); return []; }),
      api.get("/analytics/me/archetype-scores").catch((err) => { logger.warn("analytics/archetype-scores failed:", err); return []; }),
      api.get("/analytics/me/recommendations").catch((err) => { logger.warn("analytics/recommendations failed:", err); return []; }),
      api.get("/analytics/me/insights").catch((err) => { logger.warn("analytics/insights failed:", err); return []; }),
    ])
      .then(([weakSpots, progress, archetypeScores, recommendations, insights]) => {
        // Combine into snapshot-like structure for backward compat
        const totalSessions = progress.reduce?.((sum: number, p: ProgressPoint) => sum + (p.sessions_count || 0), 0) || 0;
        const avgScores = progress.filter?.((p: ProgressPoint) => p.sessions_count > 0).map?.((p: ProgressPoint) => p.avg_total) || [];
        const avgScore = avgScores.length > 0 ? Math.round(avgScores.reduce((a: number, b: number) => a + b, 0) / avgScores.length) : 0;

        setData({
          weak_spots: weakSpots || [],
          progress: progress || [],
          archetype_scores: archetypeScores || [],
          recommendations: recommendations || [],
          insights: insights || [],
          meta: {
            total_sessions: totalSessions,
            avg_score: avgScore,
            days_active: progress?.length || 0,
            analysis_window_sessions: 15,
          },
        });
      })
      .catch((err) => setError(err.message || "Ошибка загрузки аналитики"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <AuthLayout>
        <div className="relative panel-grid-bg min-h-screen">
          <AnalyticsSkeleton />
        </div>
      </AuthLayout>
    );
  }

  if (error || !data) {
    return (
      <AuthLayout>
        <div className="flex flex-col items-center justify-center min-h-[60vh]">
          <ShieldAlert size={40} style={{ color: "var(--danger)" }} />
          <p className="mt-3 text-sm" style={{ color: "var(--danger)" }}>{error || "Нет данных"}</p>
        </div>
      </AuthLayout>
    );
  }

  const { weak_spots, progress, archetype_scores, recommendations, insights, meta } = data;

  return (
    <AuthLayout>
      <div className="relative panel-grid-bg min-h-screen">
        <div className="app-page">
          <BackButton href="/home" label="На главную" />

          {/* ── Header ── */}
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
            <div className="flex items-center gap-2">
              <BarChart3 size={20} style={{ color: "var(--accent)" }} />
              <h1 className="font-display text-2xl font-bold tracking-wider" style={{ color: "var(--text-primary)" }}>
                АНАЛИТИКА
              </h1>
            </div>
            <p className="mt-1 font-mono text-xs tracking-wider" style={{ color: "var(--text-muted)" }}>
              {meta.total_sessions} сессий &middot; средний балл {meta.avg_score} &middot; {meta.days_active} дней активности
            </p>
          </motion.div>

          {/* ── Insights (top banner) ── */}
          {insights.length > 0 && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 }}
              className="mt-6 glass-panel p-4"
            >
              <div className="flex items-center gap-2 mb-3">
                <Lightbulb size={16} style={{ color: "var(--warning)" }} />
                <span className="font-mono text-xs uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
                  Инсайты
                </span>
              </div>
              <div className="space-y-2">
                {insights.map((insight, i) => (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.15 + i * 0.05 }}
                    className="flex items-start gap-2 text-sm"
                    style={{ color: "var(--text-secondary)" }}
                  >
                    <Sparkles size={14} className="mt-0.5 shrink-0" style={{ color: "var(--accent)" }} />
                    <span>{insight}</span>
                  </motion.div>
                ))}
              </div>
            </motion.div>
          )}

          <div className="mt-6 grid grid-cols-1 lg:grid-cols-2 gap-6">

            {/* ── Progress chart ── */}
            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
              className="glass-panel p-5"
            >
              <div className="flex items-center gap-2 mb-4">
                <Activity size={16} style={{ color: "var(--accent)" }} />
                <span className="font-mono text-xs uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
                  Прогресс по неделям
                </span>
              </div>
              <Sparkline points={progress} />
              <div className="mt-3 flex justify-between text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                <span>{progress.length > 0 ? formatDate(progress[0].period_start) : ""}</span>
                <span>{progress.length > 0 ? formatDate(progress[progress.length - 1].period_end) : ""}</span>
              </div>

              {/* Layer breakdown for last active week */}
              {(() => {
                const lastActive = [...progress].reverse().find((p) => p.sessions_count > 0);
                if (!lastActive) return null;
                return (
                  <div className="mt-4 space-y-2">
                    <span className="font-mono text-xs" style={{ color: "var(--text-muted)" }}>
                      ПОСЛЕДНЯЯ НЕДЕЛЯ
                    </span>
                    {[
                      { label: "Скрипт", value: lastActive.avg_script, max: 30, color: SKILL_COLORS.script_adherence },
                      { label: "Возражения", value: lastActive.avg_objection, max: 25, color: SKILL_COLORS.objection_handling },
                      { label: "Коммуникация", value: lastActive.avg_communication, max: 20, color: SKILL_COLORS.communication },
                      { label: "Результат", value: lastActive.avg_result, max: 10, color: SKILL_COLORS.result },
                    ].map((s) => (
                      <div key={s.label} className="flex items-center gap-3">
                        <span className="w-24 text-xs font-mono truncate" style={{ color: "var(--text-muted)" }}>
                          {s.label}
                        </span>
                        <div className="flex-1">
                          <MiniBar value={s.value} max={s.max} color={s.color} />
                        </div>
                        <span className="w-10 text-right text-xs font-mono" style={{ color: s.color }}>
                          {s.value.toFixed(0)}/{s.max}
                        </span>
                      </div>
                    ))}
                  </div>
                );
              })()}
            </motion.div>

            {/* ── Weak spots ── */}
            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.25 }}
              className="glass-panel p-5"
            >
              <div className="flex items-center gap-2 mb-4">
                <Target size={16} style={{ color: "var(--danger)" }} />
                <span className="font-mono text-xs uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
                  Зоны роста
                </span>
              </div>

              {weak_spots.length === 0 ? (
                <div className="flex flex-col items-center py-8">
                  <Crown size={28} style={{ color: "#00FF94" }} />
                  <p className="mt-2 text-sm" style={{ color: "var(--text-secondary)" }}>
                    Слабых мест не обнаружено!
                  </p>
                </div>
              ) : (
                <div className="space-y-3 max-h-80 overflow-y-auto pr-1">
                  {weak_spots.slice(0, 6).map((ws, i) => (
                    <motion.div
                      key={`${ws.skill}-${ws.sub_skill}-${ws.archetype}`}
                      initial={{ opacity: 0, x: -8 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: 0.3 + i * 0.05 }}
                      className="p-3 rounded-lg"
                      style={{ background: "var(--input-bg)" }}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <div
                            className="w-2 h-2 rounded-full"
                            style={{ background: SKILL_COLORS[ws.skill] || "var(--accent)" }}
                          />
                          <span className="text-xs font-medium" style={{ color: "var(--text-primary)" }}>
                            {ws.sub_skill ? SUB_SKILL_LABELS[ws.sub_skill] || ws.sub_skill : SKILL_LABELS[ws.skill] || ws.skill}
                          </span>
                          {ws.archetype && (
                            <span className="text-xs px-1.5 py-0.5 rounded-full font-mono"
                              style={{ background: "var(--accent-muted)", color: "var(--accent)" }}>
                              {ws.archetype}
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-mono font-bold" style={{ color: scoreColor(ws.pct) }}>
                            {ws.pct.toFixed(0)}%
                          </span>
                          <TrendIcon trend={ws.trend} />
                        </div>
                      </div>
                      <p className="mt-1.5 text-xs leading-relaxed" style={{ color: "var(--text-muted)" }}>
                        {ws.recommendation}
                      </p>
                    </motion.div>
                  ))}
                </div>
              )}
            </motion.div>
          </div>

          {/* ── Archetype mastery ── */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.35 }}
            className="mt-6 glass-panel p-5"
          >
            <div className="flex items-center gap-2 mb-4">
              <Radar size={16} style={{ color: "var(--accent)" }} />
              <span className="font-mono text-xs uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
                Владение архетипами
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {archetype_scores.map((arch, i) => {
                const mastery = MASTERY_CONFIG[arch.mastery_level] || MASTERY_CONFIG.untrained;
                const isExpanded = expandedArch === arch.archetype_slug;

                return (
                  <motion.div
                    key={arch.archetype_slug}
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: 0.4 + i * 0.05 }}
                    className="rounded-lg p-4 cursor-pointer transition-all"
                    style={{
                      background: "var(--input-bg)",
                      border: `1px solid ${isExpanded ? mastery.color : "transparent"}`,
                    }}
                    onClick={() => setExpandedArch(isExpanded ? null : arch.archetype_slug)}
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <span className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                          {arch.archetype_name}
                        </span>
                        <div className="flex items-center gap-2 mt-1">
                          <span
                            className="text-xs px-1.5 py-0.5 rounded-full font-mono"
                            style={{ background: mastery.bg, color: mastery.color }}
                          >
                            {mastery.label}
                          </span>
                          <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                            {arch.sessions_count} сес.
                          </span>
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="font-display text-xl font-bold" style={{ color: scoreColor(arch.sessions_count > 0 ? arch.avg_score : null) }}>
                          {arch.sessions_count > 0 ? arch.avg_score.toFixed(0) : "—"}
                        </div>
                        <ChevronDown
                          size={14}
                          style={{
                            color: "var(--text-muted)",
                            transform: isExpanded ? "rotate(180deg)" : "rotate(0)",
                            transition: "transform 0.2s",
                          }}
                        />
                      </div>
                    </div>

                    <AnimatePresence>
                      {isExpanded && arch.sessions_count > 0 && (
                        <motion.div
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: "auto", opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          transition={{ duration: 0.2 }}
                          className="overflow-hidden"
                        >
                          <div className="mt-3 pt-3 space-y-1.5" style={{ borderTop: "1px solid var(--border-color)" }}>
                            {[
                              { label: "Скрипт", val: arch.avg_script, max: 30, color: SKILL_COLORS.script_adherence },
                              { label: "Возражения", val: arch.avg_objection, max: 25, color: SKILL_COLORS.objection_handling },
                              { label: "Коммуникация", val: arch.avg_communication, max: 20, color: SKILL_COLORS.communication },
                              { label: "Результат", val: arch.avg_result, max: 10, color: SKILL_COLORS.result },
                            ].map((s) => (
                              <div key={s.label} className="flex items-center gap-2">
                                <span className="w-20 text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                                  {s.label}
                                </span>
                                <div className="flex-1"><MiniBar value={s.val} max={s.max} color={s.color} /></div>
                                <span className="text-xs font-mono w-8 text-right" style={{ color: s.color }}>
                                  {s.val.toFixed(0)}
                                </span>
                              </div>
                            ))}
                            <div className="flex justify-between mt-2 text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                              <span>Лучший: {arch.best_score.toFixed(0)}</span>
                              <span>Худший: {arch.worst_score.toFixed(0)}</span>
                              <span>{daysAgo(arch.last_played)}</span>
                            </div>
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </motion.div>
                );
              })}
            </div>
          </motion.div>

          {/* ── Recommendations ── */}
          {recommendations.length > 0 && (
            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.45 }}
              className="mt-6 glass-panel p-5"
            >
              <div className="flex items-center gap-2 mb-4">
                <Zap size={16} style={{ color: "var(--warning)" }} />
                <span className="font-mono text-xs uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
                  Рекомендации
                </span>
              </div>

              <div className="space-y-3">
                {recommendations.map((rec, i) => (
                  <motion.a
                    key={rec.scenario_id}
                    href={`/training?scenario=${rec.scenario_id}`}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.5 + i * 0.05 }}
                    className="flex items-center gap-4 p-3 rounded-lg transition-all group"
                    style={{ background: "var(--input-bg)" }}
                    whileHover={{ x: 4 }}
                  >
                    <div
                      className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 font-display text-sm font-bold"
                      style={{
                        background: rec.priority <= 2 ? "rgba(229,72,77,0.12)" : "var(--accent-muted)",
                        color: rec.priority <= 2 ? "var(--danger)" : "var(--accent)",
                      }}
                    >
                      {rec.priority}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium truncate" style={{ color: "var(--text-primary)" }}>
                        {rec.scenario_title}
                      </div>
                      <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
                        {rec.reason}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <div className="flex gap-0.5">
                        {Array.from({ length: 10 }, (_, j) => (
                          <div
                            key={j}
                            className="w-1 h-3 rounded-full"
                            style={{
                              background: j < rec.difficulty ? "var(--accent)" : "var(--input-bg)",
                            }}
                          />
                        ))}
                      </div>
                      <ArrowRight size={14} className="opacity-0 group-hover:opacity-100 transition-opacity" style={{ color: "var(--accent)" }} />
                    </div>
                  </motion.a>
                ))}
              </div>
            </motion.div>
          )}

        </div>
      </div>
    </AuthLayout>
  );
}
