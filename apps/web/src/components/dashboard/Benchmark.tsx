"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Loader2 } from "lucide-react";
import { ChartBar } from "@phosphor-icons/react";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";

interface BenchmarkSkill {
  skill: string;
  team_avg: number;
  platform_avg: number;
  percentile: number;
}

interface BenchmarkData {
  team_name: string;
  skills: BenchmarkSkill[];
  team_sessions_per_week: number;
  platform_sessions_per_week: number;
  team_avg_score: number;
  platform_avg_score: number;
}

const SKILL_LABELS: Record<string, string> = {
  empathy: "Эмпатия",
  knowledge: "Знания",
  objection_handling: "Возражения",
  stress_resistance: "Стрессоуст.",
  closing: "Закрытие",
  qualification: "Квалификация",
};

export function Benchmark() {
  const [data, setData] = useState<BenchmarkData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/dashboard/benchmark")
      .then((res) => setData(res.data))
      .catch((err) => logger.error("[Benchmark] Failed to load benchmark:", err))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex justify-center py-8">
        <Loader2 size={20} className="animate-spin" style={{ color: "var(--accent)" }} />
      </div>
    );
  }

  if (!data || data.skills.length === 0) {
    return null;
  }

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
      <div className="flex items-center gap-2 mb-3">
        <ChartBar size={16} weight="duotone" style={{ color: "var(--accent)" }} />
        <h3 className="font-display text-sm font-bold tracking-wider" style={{ color: "var(--text-primary)" }}>
          BENCHMARK vs ПЛАТФОРМА
        </h3>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-2 gap-3 mb-4">
        <div className="rounded-xl p-3 text-center" style={{ background: "var(--glass-bg)", border: "1px solid var(--glass-border)" }}>
          <div className="text-xs" style={{ color: "var(--text-muted)" }}>Средний балл команды</div>
          <div className="font-display text-xl font-bold" style={{ color: "var(--accent)" }}>
            {Math.round(data.team_avg_score)}
          </div>
          <div className="text-xs" style={{ color: "var(--text-muted)" }}>
            платформа: {Math.round(data.platform_avg_score)}
          </div>
        </div>
        <div className="rounded-xl p-3 text-center" style={{ background: "var(--glass-bg)", border: "1px solid var(--glass-border)" }}>
          <div className="text-xs" style={{ color: "var(--text-muted)" }}>Сессий/неделю</div>
          <div className="font-display text-xl font-bold" style={{ color: "var(--text-primary)" }}>
            {data.team_sessions_per_week}
          </div>
          <div className="text-xs" style={{ color: "var(--text-muted)" }}>
            платформа: {data.platform_sessions_per_week}
          </div>
        </div>
      </div>

      {/* Skill bars */}
      <div className="space-y-3">
        {data.skills.map((skill) => {
          const maxVal = Math.max(skill.team_avg, skill.platform_avg, 1);
          const teamPct = (skill.team_avg / 100) * 100;
          const platformPct = (skill.platform_avg / 100) * 100;
          const isAbove = skill.team_avg >= skill.platform_avg;

          return (
            <div key={skill.skill}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs" style={{ color: "var(--text-primary)" }}>
                  {SKILL_LABELS[skill.skill] || skill.skill}
                </span>
                <span className="font-mono text-xs" style={{ color: isAbove ? "var(--success)" : "var(--danger)" }}>
                  {isAbove ? "+" : ""}{Math.round(skill.team_avg - skill.platform_avg)}
                  <span style={{ color: "var(--text-muted)" }}> · p{skill.percentile}</span>
                </span>
              </div>
              <div className="relative h-4 rounded-full overflow-hidden" style={{ background: "var(--input-bg)" }}>
                {/* Platform avg (gray) */}
                <div
                  className="absolute top-0 left-0 h-full rounded-full"
                  style={{
                    width: `${platformPct}%`,
                    background: "rgba(148, 163, 184, 0.3)",
                  }}
                />
                {/* Team avg (colored) */}
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${teamPct}%` }}
                  transition={{ duration: 0.6, delay: 0.1 }}
                  className="absolute top-0 left-0 h-full rounded-full"
                  style={{
                    background: isAbove
                      ? "linear-gradient(90deg, rgba(34,197,94,0.6), rgba(34,197,94,0.8))"
                      : "linear-gradient(90deg, rgba(239,68,68,0.5), rgba(239,68,68,0.7))",
                  }}
                />
                {/* Labels */}
                <div className="absolute inset-0 flex items-center px-2 justify-between">
                  <span className="text-xs font-mono font-bold" style={{ color: "var(--text-primary)", textShadow: "0 1px 2px rgba(0,0,0,0.5)" }}>
                    {Math.round(skill.team_avg)}
                  </span>
                  <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                    avg {Math.round(skill.platform_avg)}
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </motion.div>
  );
}
