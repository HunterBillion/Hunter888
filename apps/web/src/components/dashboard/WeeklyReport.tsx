"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Minus, Loader2 } from "lucide-react";
import { Calendar, TrendUp, TrendDown, Medal, BookOpen } from "@phosphor-icons/react";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";

interface WeeklyReportData {
  id?: string;
  week_start: string;
  week_end: string;
  sessions_completed: number;
  total_time_minutes: number;
  average_score: number | null;
  best_score: number | null;
  worst_score: number | null;
  score_trend: string | null;
  skills_snapshot: Record<string, number>;
  skills_change: Record<string, number>;
  weak_points: Array<{ skill: string; score: number; gap: number }>;
  recommendations: string[];
  report_text: string | null;
  weekly_rank: number | null;
  xp_earned: number;
  message?: string;
}

const SKILL_LABELS: Record<string, string> = {
  empathy: "Эмпатия",
  knowledge: "Знания",
  objection_handling: "Работа с возражениями",
  stress_resistance: "Стрессоустойчивость",
  closing: "Закрытие",
  qualification: "Квалификация",
};

function TrendBadge({ trend }: { trend: string | null }) {
  if (trend === "improving") {
    return (
      <span className="flex items-center gap-1 rounded-lg px-2 py-0.5 text-xs font-bold"
        style={{ background: "var(--success-muted)", color: "var(--success)" }}>
        <TrendUp size={10} weight="duotone" /> Рост
      </span>
    );
  }
  if (trend === "declining") {
    return (
      <span className="flex items-center gap-1 rounded-lg px-2 py-0.5 text-xs font-bold"
        style={{ background: "var(--danger-muted)", color: "var(--danger)" }}>
        <TrendDown size={10} weight="duotone" /> Спад
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1 rounded-lg px-2 py-0.5 text-xs"
      style={{ background: "var(--input-bg)", color: "var(--text-muted)" }}>
      <Minus size={10} /> Стабильно
    </span>
  );
}

export function WeeklyReport() {
  const [data, setData] = useState<WeeklyReportData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/dashboard/weekly-report")
      .then((res) => setData(res))
      .catch((err) => logger.error("[WeeklyReport] Failed to load report:", err))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex justify-center py-8">
        <Loader2 size={20} className="animate-spin" style={{ color: "var(--accent)" }} />
      </div>
    );
  }

  if (!data || data.message) {
    return (
      <div className="rounded-xl p-4 text-center" style={{ background: "var(--glass-bg)", border: "1px solid var(--glass-border)" }}>
        <BookOpen size={24} weight="duotone" style={{ color: "var(--text-muted)", margin: "0 auto 8px" }} />
        <p className="text-sm" style={{ color: "var(--text-muted)" }}>
          {data?.message || "Нет отчётов. Первый отчёт будет сгенерирован в понедельник."}
        </p>
      </div>
    );
  }

  const weekLabel = new Date(data.week_start).toLocaleDateString("ru-RU", {
    day: "numeric", month: "short",
  }) + " — " + new Date(data.week_end).toLocaleDateString("ru-RU", {
    day: "numeric", month: "short",
  });

  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Calendar size={16} weight="duotone" style={{ color: "var(--accent)" }} />
          <h3 className="font-display text-sm font-bold tracking-wider" style={{ color: "var(--text-primary)" }}>
            НЕДЕЛЬНЫЙ ОТЧЁТ
          </h3>
        </div>
        <span className="text-xs font-medium" style={{ color: "var(--text-muted)" }}>
          {weekLabel}
        </span>
      </div>

      <div className="rounded-xl p-4" style={{ background: "var(--glass-bg)", border: "1px solid var(--glass-border)" }}>
        {/* Stats row */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
          <div className="text-center">
            <div className="font-display text-xl font-bold" style={{ color: "var(--accent)" }}>
              {data.sessions_completed}
            </div>
            <div className="text-xs" style={{ color: "var(--text-muted)" }}>Сессий</div>
          </div>
          <div className="text-center">
            <div className="font-display text-xl font-bold" style={{ color: "var(--text-primary)" }}>
              {data.average_score ? Math.round(data.average_score) : "—"}
            </div>
            <div className="text-xs" style={{ color: "var(--text-muted)" }}>Средний балл</div>
          </div>
          <div className="text-center">
            <div className="font-display text-xl font-bold" style={{ color: "var(--text-primary)" }}>
              +{data.xp_earned}
            </div>
            <div className="text-xs" style={{ color: "var(--text-muted)" }}>XP</div>
          </div>
          <div className="text-center">
            <TrendBadge trend={data.score_trend} />
            {data.weekly_rank && (
              <div className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
                #{data.weekly_rank} в команде
              </div>
            )}
          </div>
        </div>

        {/* Skills change */}
        {Object.keys(data.skills_change).length > 0 && (
          <div className="mb-3">
            <div className="text-xs font-bold mb-1" style={{ color: "var(--text-muted)" }}>
              ИЗМЕНЕНИЯ НАВЫКОВ
            </div>
            <div className="flex flex-wrap gap-2">
              {Object.entries(data.skills_change).map(([skill, delta]) => (
                <span
                  key={skill}
                  className="rounded-md px-2 py-0.5 text-xs font-mono"
                  style={{
                    background: delta > 0 ? "var(--success-muted)" : delta < 0 ? "var(--danger-muted)" : "var(--input-bg)",
                    color: delta > 0 ? "var(--success)" : delta < 0 ? "var(--danger)" : "var(--text-muted)",
                  }}
                >
                  {SKILL_LABELS[skill] || skill}: {delta > 0 ? "+" : ""}{delta}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Report text */}
        {data.report_text && (
          <p className="text-xs leading-relaxed" style={{ color: "var(--text-secondary)" }}>
            {data.report_text}
          </p>
        )}

        {/* Recommendations */}
        {data.recommendations.length > 0 && (
          <div className="mt-3 pt-3" style={{ borderTop: "1px solid var(--border-color)" }}>
            <div className="text-xs font-bold mb-1" style={{ color: "var(--text-muted)" }}>
              РЕКОМЕНДАЦИИ
            </div>
            <ul className="space-y-1">
              {data.recommendations.map((rec, i) => (
                <li key={i} className="text-xs flex items-start gap-1" style={{ color: "var(--text-secondary)" }}>
                  <Medal size={10} weight="duotone" className="mt-0.5 flex-shrink-0" style={{ color: "var(--accent)" }} />
                  {rec}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </motion.div>
  );
}
