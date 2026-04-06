"use client";

import { motion } from "framer-motion";
import { Clock, Mic, UserCheck, AlertTriangle, MessageSquare, BarChart3 } from "lucide-react";
import type { SoftSkillsResult } from "@/types";

/** @deprecated Use SoftSkillsResult from @/types instead */
export type SoftSkills = SoftSkillsResult;

interface SoftSkillsCardProps {
  skills: SoftSkillsResult;
}

type Rating = "good" | "ok" | "bad";

interface MetricConfig {
  label: string;
  icon: React.ComponentType<{ size: number; style?: React.CSSProperties }>;
  value: string;
  rating: Rating;
  pct: number;
}

function getRatingColor(r: Rating): string {
  if (r === "good") return "var(--neon-green, #00FF94)";
  if (r === "ok") return "var(--neon-amber, #FFD700)";
  return "var(--neon-red, #FF2A6D)";
}

function getRatingLabel(r: Rating): string {
  if (r === "good") return "Хорошо";
  if (r === "ok") return "Норм";
  return "Плохо";
}

function buildMetrics(s: SoftSkillsResult): MetricConfig[] {
  // Response time: < 5s = good, 5-10 = ok, > 10 = bad
  const rtRating: Rating = s.avg_response_time_sec < 5 ? "good" : s.avg_response_time_sec < 10 ? "ok" : "bad";
  const rtPct = Math.min(100, Math.max(0, 100 - (s.avg_response_time_sec / 15) * 100));

  // Talk ratio: 0.35-0.45 = good, 0.25-0.6 = ok
  const tr = s.talk_listen_ratio;
  const trRating: Rating = tr >= 0.35 && tr <= 0.45 ? "good" : tr >= 0.25 && tr <= 0.6 ? "ok" : "bad";
  const trPct = tr <= 0.45 ? Math.min(100, (1 - Math.abs(tr - 0.4) / 0.4) * 100) : Math.max(0, (1 - (tr - 0.45) / 0.55) * 100);

  // Name usage: >= 3 = good, 1-2 = ok, 0 = bad
  const nuRating: Rating = s.name_usage_count >= 3 ? "good" : s.name_usage_count >= 1 ? "ok" : "bad";
  const nuPct = Math.min(100, (s.name_usage_count / 5) * 100);

  // Interruptions: <= 1 = good, 2-3 = ok, > 3 = bad
  const intRating: Rating = s.interruptions <= 1 ? "good" : s.interruptions <= 3 ? "ok" : "bad";
  const intPct = Math.max(0, 100 - (s.interruptions / 6) * 100);

  // Message length: 50-150 = good, 30-200 = ok
  const ml = s.avg_message_length;
  const mlRating: Rating = ml >= 50 && ml <= 150 ? "good" : ml >= 30 && ml <= 200 ? "ok" : "bad";
  const mlPct = ml <= 150 ? Math.min(100, (1 - Math.abs(ml - 100) / 100) * 100) : Math.max(0, (1 - (ml - 150) / 150) * 100);

  return [
    { label: "Время ответа", icon: Clock, value: `${s.avg_response_time_sec.toFixed(1)}с`, rating: rtRating, pct: rtPct },
    { label: "Говорю/Слушаю", icon: Mic, value: `${Math.round(tr * 100)}/${Math.round((1 - tr) * 100)}`, rating: trRating, pct: trPct },
    { label: "Обращение по имени", icon: UserCheck, value: `${s.name_usage_count} раз`, rating: nuRating, pct: nuPct },
    { label: "Перебивания", icon: AlertTriangle, value: `${s.interruptions}`, rating: intRating, pct: intPct },
    { label: "Длина сообщений", icon: MessageSquare, value: `~${Math.round(ml)} симв.`, rating: mlRating, pct: mlPct },
  ];
}

export default function SoftSkillsCard({ skills }: SoftSkillsCardProps) {
  if (!skills) return null;

  const metrics = buildMetrics(skills);

  const container = {
    hidden: { opacity: 0 },
    show: { opacity: 1, transition: { staggerChildren: 0.08 } },
  };
  const item = {
    hidden: { opacity: 0, y: 8 },
    show: { opacity: 1, y: 0 },
  };

  return (
    <motion.div
      variants={container}
      initial="hidden"
      animate="show"
      className="glass-panel rounded-2xl p-6"
    >
      <h3 className="font-display text-base tracking-widest flex items-center gap-2 mb-4" style={{ color: "var(--text-primary)" }}>
        <BarChart3 size={16} style={{ color: "var(--accent)" }} />
        НАВЫКИ ОБЩЕНИЯ
      </h3>

      <div className="space-y-3">
        {metrics.map((m) => {
          const Icon = m.icon;
          const color = getRatingColor(m.rating);
          return (
            <motion.div key={m.label} variants={item}>
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <Icon size={14} style={{ color: "var(--text-muted)" }} />
                  <span className="text-sm" style={{ color: "var(--text-secondary)" }}>{m.label}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sm" style={{ color }}>{m.value}</span>
                  <span
                    className="rounded-full px-2 py-0.5 text-sm font-mono"
                    style={{ background: `color-mix(in srgb, ${color} 8%, transparent)`, color }}
                  >
                    {getRatingLabel(m.rating)}
                  </span>
                </div>
              </div>
              <div className="h-1 rounded-full overflow-hidden" style={{ background: "var(--input-bg)" }}>
                <motion.div
                  className="h-full rounded-full"
                  style={{ background: color, boxShadow: `0 0 4px ${color}` }}
                  initial={{ width: 0 }}
                  animate={{ width: `${Math.max(5, m.pct)}%` }}
                  transition={{ duration: 0.8 }}
                />
              </div>
            </motion.div>
          );
        })}
      </div>
    </motion.div>
  );
}
