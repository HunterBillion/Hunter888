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
  Award,
  AlertTriangle,
  Lightbulb,
  ArrowUp,
  ArrowDown,
  Users,
} from "lucide-react";
import { api } from "@/lib/api";
import { scoreColor } from "@/lib/utils";
import { useAuth } from "@/hooks/useAuth";

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

interface TeamMemberOption {
  id: string;
  name: string;
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
  if (trend === "growing") return <TrendingUp size={14} style={{ color: "var(--success)" }} />;
  if (trend === "declining") return <TrendingDown size={14} style={{ color: "var(--danger)" }} />;
  return <Minus size={14} style={{ color: "var(--text-muted)" }} />;
}

/* ─── Skill Bar ─── */

function SkillBar({ name, value, change }: { name: string; value: number; change: number }) {
  const label = SKILL_LABELS[name] || name;
  const barColor = value >= 70 ? "var(--success)" : value >= 40 ? "var(--warning)" : "var(--danger)";
  return (
    <div style={{ marginBottom: "0.6rem" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: "0.75rem" }}>
        <span style={{ color: "var(--text-muted)" }}>{label}</span>
        <span style={{ display: "flex", alignItems: "center", gap: "0.25rem" }}>
          <span style={{ fontWeight: 600, color: "var(--text-secondary)" }}>{value}</span>
          {change !== 0 && (
            <span style={{ display: "flex", alignItems: "center", gap: "2px", fontSize: "0.7rem", color: change > 0 ? "var(--success)" : "var(--danger)" }}>
              {change > 0 ? <ArrowUp size={10} /> : <ArrowDown size={10} />}
              {Math.abs(change)}
            </span>
          )}
        </span>
      </div>
      <div style={{ height: 6, borderRadius: 3, overflow: "hidden", marginTop: 4, background: "rgba(255,255,255,0.06)" }}>
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${value}%` }}
          transition={{ duration: 0.6, delay: 0.1 }}
          style={{ height: "100%", borderRadius: 3, background: barColor }}
        />
      </div>
    </div>
  );
}

/* ─── Stat Card ─── */

function StatCard({ icon: Icon, label, value, color }: { icon: typeof Target; label: string; value: string; color: string }) {
  return (
    <div style={{
      borderRadius: 10,
      padding: "0.5rem 0.75rem",
      background: "rgba(255,255,255,0.03)",
      border: "1px solid rgba(255,255,255,0.06)",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginBottom: "0.2rem" }}>
        <Icon size={12} style={{ color }} />
        <span style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>{label}</span>
      </div>
      <span style={{ fontSize: "1.1rem", fontWeight: 700, fontFamily: "monospace", color }}>
        {value}
      </span>
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
      style={{
        background: "rgba(255,255,255,0.03)",
        border: "1px solid rgba(255,255,255,0.06)",
        borderRadius: 12,
        overflow: "hidden",
        marginBottom: "0.75rem",
      }}
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0.85rem 1.25rem",
          cursor: "pointer",
        }}
        onClick={() => setExpanded(!expanded)}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <div style={{
            display: "flex",
            height: 40,
            width: 40,
            alignItems: "center",
            justifyContent: "center",
            borderRadius: 8,
            background: report.sessions_completed > 0 ? "rgba(245,158,11,0.15)" : "rgba(255,255,255,0.04)",
            color: report.sessions_completed > 0 ? "var(--warning)" : "var(--text-muted)",
          }}>
            <FileBarChart size={18} />
          </div>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <span style={{ fontSize: "0.95rem", fontWeight: 600, color: "var(--text-primary)" }}>
                {formatWeek(report.week_start)} — {formatWeek(report.week_end)}
              </span>
              {trendIcon(report.score_trend)}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.75rem", color: "var(--text-muted)" }}>
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
                  <span style={{ display: "flex", alignItems: "center", gap: "2px" }}>
                    #{report.weekly_rank}
                    {report.rank_change !== null && report.rank_change !== 0 && (
                      <span style={{ fontSize: "0.7rem", color: report.rank_change > 0 ? "var(--success)" : "var(--danger)" }}>
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
            <div style={{ padding: "0 20px 20px", borderTop: "1px solid rgba(255,255,255,0.06)" }}>
              {/* Report text */}
              {report.report_text && (
                <p style={{ fontSize: "0.85rem", margin: "1rem 0", lineHeight: 1.6, color: "var(--text-muted)" }}>
                  {report.report_text}
                </p>
              )}

              {/* Stats grid */}
              <div style={{ display: "grid", gap: "0.5rem", marginBottom: "1rem", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))" }}>
                <StatCard icon={Target} label="Ср. балл" value={report.average_score != null ? Number(report.average_score).toFixed(0) : "—"} color={scoreColor(report.average_score)} />
                <StatCard icon={Star} label="Лучший" value={report.best_score != null ? String(report.best_score) : "—"} color="var(--rank-gold)" />
                <StatCard icon={Trophy} label="Win rate" value={report.win_rate != null ? `${Number(report.win_rate).toFixed(0)}%` : "—"} color="var(--success)" />
                <StatCard icon={Zap} label="XP" value={`+${report.xp_earned}`} color="var(--warning)" />
                <StatCard icon={Clock} label="Время" value={`${report.total_time_minutes} мин`} color="var(--info)" />
                <StatCard
                  icon={TrendingUp}
                  label="Уровень"
                  value={report.level_at_start === report.level_at_end ? `${report.level_at_end}` : `${report.level_at_start} → ${report.level_at_end}`}
                  color="var(--accent-hover)"
                />
              </div>

              {/* Outcomes */}
              {Object.keys(report.outcomes).length > 0 && (
                <div style={{ marginBottom: "1rem" }}>
                  <div style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "0.5rem" }}>Исходы</div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
                    {Object.entries(report.outcomes)
                      .filter(([, v]) => typeof v === "number")
                      .map(([key, count]) => (
                        <span key={key} style={{
                          borderRadius: 20,
                          padding: "3px 10px",
                          fontSize: "0.75rem",
                          fontWeight: 500,
                          background: key === "deal" ? "rgba(52,211,153,0.1)" : "rgba(255,255,255,0.04)",
                          color: key === "deal" ? "var(--success)" : "var(--text-muted)",
                          border: `1px solid ${key === "deal" ? "rgba(52,211,153,0.25)" : "rgba(255,255,255,0.08)"}`,
                        }}>
                          {OUTCOME_LABELS[key] || key}: {count as number}
                        </span>
                      ))}
                  </div>
                </div>
              )}

              {/* Skills */}
              {Object.keys(report.skills_snapshot).length > 0 && (
                <div style={{ marginBottom: "1rem" }}>
                  <div style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "0.5rem" }}>Навыки</div>
                  <div style={{ display: "grid", gap: "0 1.5rem", gridTemplateColumns: "1fr 1fr" }}>
                    {Object.entries(report.skills_snapshot).map(([skill, value]) => (
                      <SkillBar key={skill} name={skill} value={value as number} change={(report.skills_change[skill] as number) || 0} />
                    ))}
                  </div>
                </div>
              )}

              {/* Achievements */}
              {report.new_achievements.length > 0 && (
                <div style={{ marginBottom: "1rem" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.75rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "0.5rem" }}>
                    <Award size={13} /> Достижения недели
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
                    {report.new_achievements.map((a) => (
                      <span key={a.code} style={{
                        borderRadius: 20,
                        padding: "3px 10px",
                        fontSize: "0.75rem",
                        fontWeight: 500,
                        background: "rgba(212,168,75,0.1)",
                        color: "var(--rank-gold)",
                        border: "1px solid rgba(212,168,75,0.25)",
                      }}>
                        {a.name} (+{a.xp} XP)
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Weak points */}
              {report.weak_points.length > 0 && (
                <div style={{ marginBottom: "1rem" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.75rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "0.5rem" }}>
                    <AlertTriangle size={13} /> Слабые места
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
                    {report.weak_points.map((wp) => (
                      <span key={wp.skill} style={{
                        borderRadius: 20,
                        padding: "3px 10px",
                        fontSize: "0.75rem",
                        background: wp.priority === "critical" ? "rgba(248,113,113,0.1)" : "rgba(251,191,36,0.1)",
                        color: wp.priority === "critical" ? "var(--danger)" : "var(--warning)",
                        border: `1px solid ${wp.priority === "critical" ? "rgba(248,113,113,0.25)" : "rgba(251,191,36,0.25)"}`,
                      }}>
                        {SKILL_LABELS[wp.skill] || wp.skill}: {wp.value}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Recommendations */}
              {report.recommendations.length > 0 && (
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.75rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "0.5rem" }}>
                    <Lightbulb size={13} /> Рекомендации
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                    {report.recommendations.map((rec, i) => (
                      <div key={`rec-${i}`} style={{
                        borderRadius: 8,
                        padding: "0.4rem 0.75rem",
                        fontSize: "0.75rem",
                        background: "rgba(255,255,255,0.03)",
                        color: "var(--text-muted)",
                        lineHeight: 1.5,
                      }}>
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

/* ═══════════════════════════════════════════════════════════════════════════
   MAIN COMPONENT — ReportsDashboard
   Props:
   - teamMode: if true, show team member selector (for ROP/admin)
   - teamMembers: list of team members to choose from (optional)
   ═══════════════════════════════════════════════════════════════════════════ */

export function ReportsDashboard({
  teamMode = false,
  teamMembers = [],
}: {
  teamMode?: boolean;
  teamMembers?: TeamMemberOption[];
}) {
  const { user } = useAuth();
  const [reports, setReports] = useState<WeeklyReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);

  // In team mode, default to first member; otherwise use self
  const activeUserId = teamMode ? (selectedUserId || teamMembers[0]?.id || user?.id) : user?.id;
  const activeName = teamMode
    ? teamMembers.find((m) => m.id === activeUserId)?.name || "—"
    : user?.full_name || user?.email || "—";

  const fetchReports = useCallback(async () => {
    if (!activeUserId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.get(`/reports/weekly/${activeUserId}?limit=12`);
      setReports(Array.isArray(data) ? data : []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Ошибка загрузки отчётов");
    } finally {
      setLoading(false);
    }
  }, [activeUserId]);

  useEffect(() => {
    fetchReports();
  }, [fetchReports]);

  const handleGenerate = async () => {
    if (!activeUserId) return;
    setGenerating(true);
    setError(null);
    try {
      await api.post(`/reports/weekly/${activeUserId}/generate`, {});
      await new Promise((r) => setTimeout(r, 1000));
      await fetchReports();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Ошибка генерации отчёта");
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div style={{ maxWidth: 900, margin: "0 auto" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "1.25rem", flexWrap: "wrap" }}>
        <FileBarChart size={24} style={{ color: "var(--warning)" }} />
        <div style={{ flex: 1 }}>
          <h2 style={{ fontSize: "1.3rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>
            {teamMode ? "Отчёты команды" : "Еженедельные отчёты"}
          </h2>
          <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", margin: 0 }}>
            {teamMode ? "Прогресс, навыки, рекомендации по каждому менеджеру" : "Прогресс, навыки, рекомендации"}
          </p>
        </div>
        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          onClick={handleGenerate}
          disabled={generating}
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.4rem",
            padding: "0.5rem 1rem",
            borderRadius: 8,
            border: "none",
            background: "rgba(245,158,11,0.15)",
            color: "var(--warning)",
            cursor: generating ? "wait" : "pointer",
            opacity: generating ? 0.7 : 1,
            fontSize: "0.85rem",
            fontWeight: 600,
          }}
        >
          {generating ? <Loader2 size={15} style={{ animation: "spin 1s linear infinite" }} /> : <RefreshCw size={15} />}
          {generating ? "Генерация..." : "Обновить отчёт"}
        </motion.button>
      </div>

      {/* Team member selector (ROP mode) */}
      {teamMode && teamMembers.length > 0 && (
        <div style={{
          display: "flex",
          alignItems: "center",
          gap: "0.75rem",
          padding: "0.75rem 1rem",
          marginBottom: "1rem",
          background: "rgba(124,106,232,0.06)",
          border: "1px solid rgba(124,106,232,0.15)",
          borderRadius: 10,
          flexWrap: "wrap",
        }}>
          <Users size={16} style={{ color: "var(--accent)" }} />
          <span style={{ color: "var(--accent-hover)", fontSize: "0.85rem" }}>Менеджер:</span>
          <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
            {teamMembers.map((m) => (
              <button
                key={m.id}
                onClick={() => setSelectedUserId(m.id)}
                style={{
                  padding: "0.3rem 0.75rem",
                  borderRadius: 8,
                  border: activeUserId === m.id ? "1px solid rgba(124,106,232,0.4)" : "1px solid rgba(255,255,255,0.08)",
                  background: activeUserId === m.id ? "rgba(124,106,232,0.15)" : "rgba(255,255,255,0.03)",
                  color: activeUserId === m.id ? "var(--accent-hover)" : "var(--text-muted)",
                  cursor: "pointer",
                  fontSize: "0.8rem",
                  fontWeight: activeUserId === m.id ? 600 : 400,
                  transition: "all 0.2s",
                }}
              >
                {m.name}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Current user label in team mode */}
      {teamMode && (
        <div style={{ fontSize: "0.85rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>
          Отчёты: <span style={{ color: "var(--warning)", fontWeight: 600 }}>{activeName}</span>
        </div>
      )}

      {/* Error */}
      {error && (
        <div style={{
          padding: "0.75rem 1rem",
          borderRadius: 10,
          marginBottom: "1rem",
          background: "rgba(239,68,68,0.1)",
          border: "1px solid rgba(239,68,68,0.2)",
          color: "var(--danger)",
          textAlign: "center",
          fontSize: "0.85rem",
        }}>
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div style={{ textAlign: "center", padding: "3rem" }}>
          <Loader2 size={32} style={{ animation: "spin 1s linear infinite", color: "var(--warning)" }} />
          <p style={{ color: "var(--text-muted)", marginTop: "0.75rem" }}>Загрузка отчётов...</p>
        </div>
      )}

      {/* Empty state */}
      {!loading && reports.length === 0 && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          style={{
            padding: "3rem",
            textAlign: "center",
            background: "rgba(255,255,255,0.03)",
            border: "1px solid rgba(255,255,255,0.06)",
            borderRadius: 12,
          }}
        >
          <FileBarChart size={40} style={{ margin: "0 auto 12px", color: "var(--text-muted)", opacity: 0.3 }} />
          <p style={{ color: "var(--text-muted)", margin: 0 }}>
            Отчётов пока нет. Нажмите «Обновить отчёт» чтобы сгенерировать первый.
          </p>
        </motion.div>
      )}

      {/* Reports list */}
      {!loading && reports.map((report, i) => (
        <ReportCard key={report.id} report={report} index={i} />
      ))}
    </div>
  );
}
