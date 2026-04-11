"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Minus, Loader2 } from "lucide-react";
import { Flame, TrendUp, TrendDown } from "@phosphor-icons/react";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";

interface HeatmapCell {
  skill: string;
  score: number;
  trend: string;
}

interface HeatmapRow {
  user_id: string;
  full_name: string;
  avatar_url: string | null;
  skills: HeatmapCell[];
  avg_score: number;
  sessions_this_week: number;
}

interface HeatmapData {
  team_name: string;
  skill_names: string[];
  rows: HeatmapRow[];
  team_avg: Record<string, number>;
}

const SKILL_LABELS: Record<string, string> = {
  empathy: "Эмп",
  knowledge: "Зн",
  objection_handling: "Возр",
  stress_resistance: "Стр",
  closing: "Закр",
  qualification: "Кв",
};

function getScoreColor(score: number): string {
  if (score >= 80) return "rgba(34, 197, 94, 0.6)";
  if (score >= 60) return "rgba(234, 179, 8, 0.4)";
  if (score >= 40) return "rgba(249, 115, 22, 0.4)";
  return "rgba(239, 68, 68, 0.5)";
}

function TrendIcon({ trend }: { trend: string }) {
  if (trend === "improving") return <TrendUp size={10} weight="duotone" style={{ color: "var(--success)" }} />;
  if (trend === "declining") return <TrendDown size={10} weight="duotone" style={{ color: "var(--danger)" }} />;
  return <Minus size={10} style={{ color: "var(--text-muted)" }} />;
}

export function TeamHeatmap() {
  const [data, setData] = useState<HeatmapData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/dashboard/rop/heatmap")
      .then((res) => setData(res.data))
      .catch((err) => logger.error("[TeamHeatmap] Failed to load heatmap:", err))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex justify-center py-8">
        <Loader2 size={20} className="animate-spin" style={{ color: "var(--accent)" }} />
      </div>
    );
  }

  if (!data || data.rows.length === 0) {
    return (
      <div className="text-center py-6 text-sm" style={{ color: "var(--text-muted)" }}>
        Нет данных для отображения
      </div>
    );
  }

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="overflow-x-auto">
      <div className="flex items-center gap-2 mb-3">
        <Flame size={16} weight="duotone" style={{ color: "var(--accent)" }} />
        <h3 className="font-display text-sm font-bold tracking-wider" style={{ color: "var(--text-primary)" }}>
          ТЕПЛОВАЯ КАРТА НАВЫКОВ
        </h3>
      </div>

      <table className="w-full text-xs">
        <thead>
          <tr>
            <th className="text-left p-2 font-semibold" style={{ color: "var(--text-muted)" }}>Менеджер</th>
            {data.skill_names.map((s) => (
              <th key={s} className="p-2 text-center font-semibold" style={{ color: "var(--text-muted)" }}>
                {SKILL_LABELS[s] || s}
              </th>
            ))}
            <th className="p-2 text-center font-semibold" style={{ color: "var(--text-muted)" }}>Avg</th>
            <th className="p-2 text-center font-semibold" style={{ color: "var(--text-muted)" }}>Сес/нед</th>
          </tr>
        </thead>
        <tbody>
          {data.rows.map((row, i) => (
            <motion.tr
              key={row.user_id}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.05 }}
              className="border-b"
              style={{ borderColor: "var(--border-color)" }}
            >
              <td className="p-2 font-medium" style={{ color: "var(--text-primary)" }}>
                {row.full_name}
              </td>
              {row.skills.map((cell) => (
                <td
                  key={cell.skill}
                  className="p-2 text-center rounded"
                  style={{ background: getScoreColor(cell.score) }}
                >
                  <div className="flex items-center justify-center gap-1">
                    <span className="font-mono font-bold">{Math.round(cell.score)}</span>
                    <TrendIcon trend={cell.trend} />
                  </div>
                </td>
              ))}
              <td className="p-2 text-center font-mono font-bold" style={{ color: "var(--text-primary)" }}>
                {Math.round(row.avg_score)}
              </td>
              <td className="p-2 text-center font-mono" style={{ color: row.sessions_this_week === 0 ? "var(--danger)" : "var(--text-muted)" }}>
                {row.sessions_this_week}
              </td>
            </motion.tr>
          ))}
          {/* Team average row */}
          <tr style={{ borderTop: "2px solid var(--accent)" }}>
            <td className="p-2 font-bold" style={{ color: "var(--accent)" }}>Среднее</td>
            {data.skill_names.map((s) => (
              <td key={s} className="p-2 text-center font-mono font-bold" style={{ color: "var(--accent)" }}>
                {Math.round(data.team_avg[s] || 0)}
              </td>
            ))}
            <td colSpan={2} />
          </tr>
        </tbody>
      </table>
    </motion.div>
  );
}
