"use client";

import { useEffect, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  FileBarChart,
  Loader2,
  RefreshCw,
  TrendingUp,
  TrendingDown,
  Minus,
  Trophy,
  Target,
  Clock,
  Zap,
  Star,
  ChevronDown,
  ChevronUp,
  Award,
  AlertTriangle,
  Lightbulb,
  ArrowUp,
  ArrowDown,
  ShieldCheck,
} from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api";
import { scoreColor } from "@/lib/utils";
import { useAuth } from "@/hooks/useAuth";
import AuthLayout from "@/components/layout/AuthLayout";
import { BackButton } from "@/components/ui/BackButton";
import { CardSkeleton } from "@/components/ui/Skeleton";

/* ─── Types ─── */

interface WeeklyReport {
  id: string;
  user_id: string;
  week_start: string;
  week_end: string;
  sessions_completed: number;
  total_time_minutes: number;
  average_score: number | null;
  best_score: number | null;
  worst_score: number | null;
  score_trend: string | null;
  outcomes: Record<string, number>;
  win_rate: number | null;
  skills_snapshot: Record<string, number>;
  skills_change: Record<string, number>;
  xp_earned: number;
  level_at_start: number;
  level_at_end: number;
  new_achievements: { code: string; name: string; xp: number }[];
  weak_points: { skill: string; value: number; gap: number; priority: string }[];
  recommendations: string[];
  weekly_rank: number | null;
  rank_change: number | null;
  report_text: string | null;
  created_at: string;
}

/* ─── Constants ─── */

const SKILL_LABELS: Record<string, string> = {
  empathy: "Эмпатия",
  knowledge: "Знание продукта",
  objection_handling: "Возражения",
  stress_resistance: "Стрессоустойчивость",
  closing: "Закрытие",
  qualification: "Квалификация",
};

const OUTCOME_LABELS: Record<string, string> = {
  deal: "Сделка",
  refusal: "Отказ",
  callback: "Перезвон",
  thinking: "Думает",
  hangup: "Бросил трубку",
  escalation: "Эскалация",
};

/* ─── Helpers ─── */

function formatWeek(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
}

function trendIcon(trend: string | null) {
  if (trend === "growing") return <TrendingUp size={14} style={{ color: "#34D399" }} />;
  if (trend === "declining") return <TrendingDown size={14} style={{ color: "#F87171" }} />;
  return <Minus size={14} style={{ color: "#94A3B8" }} />;
}

/* ─── Skill Bar ─── */

function SkillBar({ name, value, change }: { name: string; value: number; change: number }) {
  const label = SKILL_LABELS[name] || name;
  const barColor = value >= 70 ? "var(--neon-green, #34D399)" : value >= 40 ? "var(--warning, #FBBF24)" : "var(--neon-red, #F87171)";
  return (
    <div className="mb-2.5">
      <div className="flex items-center justify-between text-xs">
        <span style={{ color: "var(--text-secondary)" }}>{label}</span>
        <span className="flex items-center gap-1">
          <span className="font-semibold" style={{ color: "var(--text-primary)" }}>{value}</span>
          {change !== 0 && (
            <span
              className="flex items-center gap-0.5 text-xs"
              style={{ color: change > 0 ? "var(--neon-green, #34D399)" : "var(--neon-red, #F87171)" }}
            >
              {change > 0 ? <ArrowUp size={10} /> : <ArrowDown size={10} />}
              {Math.abs(change)}
            </span>
          )}
        </span>
      </div>
      <div className="h-1.5 rounded-full overflow-hidden mt-1" style={{ background: "var(--input-bg)" }}>
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${value}%` }}
          transition={{ duration: 0.6, delay: 0.1 }}
          className="h-full rounded-full"
          style={{ background: barColor }}
        />
      </div>
    </div>
  );
}

/* ─── Report Card ─── */

function ReportCard({ report, index }: { report: WeeklyReport; index: number }) {
  const [expanded, setExpanded] = useState(index === 0);

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05 }}
      className="glass-panel rounded-xl overflow-hidden mb-3"
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-5 py-4"
        style={{ cursor: "pointer" }}
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-3">
          <div
            className="flex h-10 w-10 items-center justify-center rounded-lg"
            style={{
              background: report.sessions_completed > 0 ? "var(--accent)" : "var(--input-bg)",
              color: report.sessions_completed > 0 ? "#000" : "var(--text-muted)",
            }}
          >
            <FileBarChart size={18} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-base font-semibold" style={{ color: "var(--text-primary)" }}>
                {formatWeek(report.week_start)} — {formatWeek(report.week_end)}
              </span>
              {trendIcon(report.score_trend)}
            </div>
            <div className="flex items-center gap-3 text-xs" style={{ color: "var(--text-muted)" }}>
              <span>{report.sessions_completed} сессий</span>
              <span>·</span>
              <span>{report.total_time_minutes} мин</span>
              {report.average_score !== null && (
                <>
                  <span>·</span>
                  <span style={{ color: scoreColor(report.average_score), fontWeight: 500 }}>
                    {report.average_score.toFixed(0)} баллов
                  </span>
                </>
              )}
              {report.weekly_rank && (
                <>
                  <span>·</span>
                  <span className="flex items-center gap-0.5">
                    #{report.weekly_rank}
                    {report.rank_change !== null && report.rank_change !== 0 && (
                      <span className="text-xs" style={{ color: report.rank_change > 0 ? "var(--neon-green, #34D399)" : "var(--neon-red, #F87171)" }}>
                        {report.rank_change > 0 ? `+${report.rank_change}` : report.rank_change}
                      </span>
                    )}
                  </span>
                </>
              )}
            </div>
          </div>
        </div>

        <motion.div animate={{ rotate: expanded ? 180 : 0 }} style={{ color: "var(--text-muted)" }}>
          <ChevronDown size={18} />
        </motion.div>
      </div>

      {/* Expanded content */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25 }}
            style={{ overflow: "hidden" }}
          >
            <div style={{ padding: "0 20px 20px", borderTop: "1px solid var(--border-color)" }}>
              {/* Report text */}
              {report.report_text && (
                <p className="text-sm my-4 leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                  {report.report_text}
                </p>
              )}

              {/* Stats grid */}
              <div
                className="grid gap-3 mb-4"
                style={{ gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))" }}
              >
                <StatCard icon={Target} label="Ср. балл" value={report.average_score != null ? Number(report.average_score).toFixed(0) : "—"} color={scoreColor(report.average_score)} />
                <StatCard icon={Star} label="Лучший" value={report.best_score != null ? String(report.best_score) : "—"} color="#FFD700" />
                <StatCard icon={Trophy} label="Win rate" value={report.win_rate != null ? `${Number(report.win_rate).toFixed(0)}%` : "—"} color="#34D399" />
                <StatCard icon={Zap} label="XP" value={`+${report.xp_earned}`} color="var(--accent)" />
                <StatCard icon={Clock} label="Время" value={`${report.total_time_minutes} мин`} color="#60A5FA" />
                <StatCard
                  icon={TrendingUp}
                  label="Уровень"
                  value={report.level_at_start === report.level_at_end
                    ? `${report.level_at_end}`
                    : `${report.level_at_start} → ${report.level_at_end}`
                  }
                  color="#A78BFA"
                />
              </div>

              {/* Outcomes */}
              {Object.keys(report.outcomes).length > 0 && (
                <div className="mb-4">
                  <div className="text-xs font-semibold mb-2" style={{ color: "var(--text-primary)" }}>
                    Исходы
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(report.outcomes).map(([key, count]) => (
                      <span
                        key={key}
                        className="rounded-full px-3 py-1 text-xs font-medium"
                        style={{
                          background: key === "deal" ? "#34D39922" : "var(--input-bg)",
                          color: key === "deal" ? "#34D399" : "var(--text-secondary)",
                          border: `1px solid ${key === "deal" ? "#34D39944" : "var(--border-color)"}`,
                        }}
                      >
                        {OUTCOME_LABELS[key] || key}: {count}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Skills */}
              {Object.keys(report.skills_snapshot).length > 0 && (
                <div className="mb-4">
                  <div className="text-xs font-semibold mb-2" style={{ color: "var(--text-primary)" }}>
                    Навыки
                  </div>
                  <div className="grid gap-x-6" style={{ gridTemplateColumns: "1fr 1fr" }}>
                    {Object.entries(report.skills_snapshot).map(([skill, value]) => (
                      <SkillBar
                        key={skill}
                        name={skill}
                        value={value as number}
                        change={(report.skills_change[skill] as number) || 0}
                      />
                    ))}
                  </div>
                </div>
              )}

              {/* Achievements */}
              {report.new_achievements.length > 0 && (
                <div className="mb-4">
                  <div className="flex items-center gap-1.5 text-xs font-semibold mb-2" style={{ color: "var(--text-primary)" }}>
                    <Award size={13} /> Достижения недели
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {report.new_achievements.map((a) => (
                      <span
                        key={a.code}
                        className="rounded-full px-3 py-1 text-xs font-medium"
                        style={{ background: "#FFD70022", color: "#FFD700", border: "1px solid #FFD70044" }}
                      >
                        {a.name} (+{a.xp} XP)
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Weak points */}
              {report.weak_points.length > 0 && (
                <div className="mb-4">
                  <div className="flex items-center gap-1.5 text-xs font-semibold mb-2" style={{ color: "var(--text-primary)" }}>
                    <AlertTriangle size={13} /> Слабые места
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {report.weak_points.map((wp) => (
                      <span
                        key={wp.skill}
                        className="rounded-full px-3 py-1 text-xs"
                        style={{
                          background: wp.priority === "critical" ? "#F8717122" : "#FBBF2422",
                          color: wp.priority === "critical" ? "#F87171" : "#FBBF24",
                          border: `1px solid ${wp.priority === "critical" ? "#F8717144" : "#FBBF2444"}`,
                        }}
                      >
                        {SKILL_LABELS[wp.skill] || wp.skill}: {wp.value}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Recommendations */}
              {report.recommendations.length > 0 && (
                <div>
                  <div className="flex items-center gap-1.5 text-xs font-semibold mb-2" style={{ color: "var(--text-primary)" }}>
                    <Lightbulb size={13} /> Рекомендации
                  </div>
                  <div className="space-y-2">
                    {report.recommendations.map((rec, i) => (
                      <div
                        key={`rec-${i}-${rec.slice(0, 20)}`}
                        className="rounded-lg px-3 py-2 text-xs"
                        style={{ background: "var(--input-bg)", color: "var(--text-secondary)", lineHeight: 1.5 }}
                      >
                        {rec}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

/* ─── Stat Card ─── */

function StatCard({ icon: Icon, label, value, color }: { icon: typeof Target; label: string; value: string; color: string }) {
  return (
    <div
      className="rounded-lg px-3 py-2.5"
      style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)" }}
    >
      <div className="flex items-center gap-1.5 mb-1">
        <Icon size={12} style={{ color }} />
        <span className="text-xs" style={{ color: "var(--text-muted)" }}>{label}</span>
      </div>
      <span className="text-lg font-bold font-mono" style={{ color }}>
        {value}
      </span>
    </div>
  );
}

/* ─── Main Page ─── */

export default function ReportsPage() {
  const { user } = useAuth();
  const [reports, setReports] = useState<WeeklyReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchReports = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.get(`/reports/weekly/${user.id}?limit=12`);
      setReports(Array.isArray(data) ? data : []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Ошибка загрузки отчётов");
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    fetchReports();
  }, [fetchReports]);

  const handleGenerate = async () => {
    if (!user) return;
    setGenerating(true);
    setError(null);
    try {
      await api.post(`/reports/weekly/${user.id}/generate`, {});
      // Small delay to let backend finish writing
      await new Promise((r) => setTimeout(r, 1000));
      await fetchReports();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Ошибка генерации отчёта";
      setError(msg);
      // Don't crash — show error inline
    } finally {
      setGenerating(false);
    }
  };

  return (
    <AuthLayout>
      <div className="panel-grid-bg min-h-screen w-full">
        <div className="mx-auto" style={{ maxWidth: 800, padding: "24px 16px" }}>
        <BackButton href="/home" label="На главную" />
        {/* Header — compact */}
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-center justify-between flex-wrap gap-3 mb-6"
        >
          <p className="text-sm" style={{ color: "var(--text-muted)", margin: 0 }}>
            Прогресс, навыки, рекомендации
          </p>

          <div className="flex items-center gap-2">
            {user?.role === "admin" && (
              <Link
                href="/admin/audit-log"
                className="flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors"
                style={{
                  background: "var(--input-bg)",
                  color: "var(--text-secondary)",
                  border: "1px solid var(--border-color)",
                }}
              >
                <ShieldCheck size={15} />
                Журнал аудита
              </Link>
            )}
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={handleGenerate}
              disabled={generating}
              className="flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium"
              style={{
                background: "var(--accent)",
                color: "#000",
                border: "none",
                cursor: generating ? "wait" : "pointer",
                opacity: generating ? 0.7 : 1,
              }}
            >
              {generating ? (
                <Loader2 size={15} className="animate-spin" />
              ) : (
                <RefreshCw size={15} />
              )}
              {generating ? "Генерация..." : "Обновить отчёт"}
            </motion.button>
          </div>
        </motion.div>

        {/* Error */}
        {error && (
          <div
            className="glass-panel rounded-xl p-4 mb-4 text-center"
            style={{ color: "var(--neon-red, #F87171)" }}
          >
            {error}
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="grid gap-3 md:grid-cols-2">
            {[1, 2, 3, 4].map(i => <CardSkeleton key={i} />)}
          </div>
        )}

        {/* Reports list */}
        {!loading && reports.length === 0 && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="glass-panel rounded-xl p-12 text-center"
          >
            <FileBarChart size={40} style={{ margin: "0 auto 12px", color: "var(--text-muted)", opacity: 0.3 }} />
            <p style={{ color: "var(--text-muted)", margin: 0 }}>
              Отчётов пока нет. Нажмите «Обновить отчёт» чтобы сгенерировать первый.
            </p>
          </motion.div>
        )}

        {!loading && reports.map((report, i) => (
          <ReportCard key={report.id} report={report} index={i} />
        ))}
        </div>
      </div>
    </AuthLayout>
  );
}
