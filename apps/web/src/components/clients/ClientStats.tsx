"use client";

import { motion } from "framer-motion";
import { Users, TrendingUp, Timer, ArrowRightLeft } from "lucide-react";
import type { PipelineStats } from "@/types";
import { CLIENT_STATUS_LABELS, CLIENT_STATUS_COLORS, PIPELINE_STATUSES } from "@/types";

interface ClientStatsProps {
  stats: PipelineStats[];
}

export function ClientStats({ stats }: ClientStatsProps) {
  const totalInPipeline = stats
    .filter((s) => PIPELINE_STATUSES.includes(s.status))
    .reduce((sum, s) => sum + s.count, 0);

  const contractSigned = stats.find((s) => s.status === "contract_signed")?.count || 0;
  const completed = stats.find((s) => s.status === "completed")?.count || 0;
  const lost = stats.find((s) => s.status === "lost")?.count || 0;
  const successCount = contractSigned + completed;
  const conversionRate = successCount + lost > 0
    ? ((successCount / (successCount + lost)) * 100).toFixed(0)
    : "—";

  const cards = [
    { label: "В воронке", value: totalInPipeline, icon: Users, color: "var(--accent)" },
    { label: "Конверсия", value: `${conversionRate}%`, icon: TrendingUp, color: "var(--success)" },
    { label: "Договоры", value: contractSigned, icon: ArrowRightLeft, color: "var(--success)" },
    { label: "Потеряны", value: lost, icon: Timer, color: "var(--danger)" },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      {cards.map((card, i) => {
        const Icon = card.icon;
        return (
          <motion.div
            key={card.label}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
            className="glass-panel p-4"
          >
            <Icon size={16} style={{ color: card.color }} />
            <div className="text-2xl font-bold mt-2" style={{ color: "var(--text-primary)" }}>
              {card.value}
            </div>
            <div className="text-xs font-mono tracking-wider mt-0.5" style={{ color: "var(--text-muted)" }}>
              {card.label.toUpperCase()}
            </div>
          </motion.div>
        );
      })}

      {/* Mini pipeline bar */}
      <div className="col-span-2 md:col-span-4 glass-panel p-3">
        <div className="flex h-3 rounded-full overflow-hidden" style={{ background: "var(--input-bg)" }}>
          {PIPELINE_STATUSES.map((status) => {
            const s = stats.find((st) => st.status === status);
            if (!s || !s.count) return null;
            const pct = (s.count / Math.max(totalInPipeline, 1)) * 100;
            return (
              <div
                key={status}
                className="h-full transition-all"
                style={{ width: `${pct}%`, background: CLIENT_STATUS_COLORS[status], minWidth: pct > 0 ? 4 : 0 }}
                title={`${CLIENT_STATUS_LABELS[status]}: ${s.count}`}
              />
            );
          })}
        </div>
        <div className="flex gap-3 mt-2 flex-wrap">
          {PIPELINE_STATUSES.map((status) => {
            const s = stats.find((st) => st.status === status);
            if (!s || !s.count) return null;
            return (
              <span key={status} className="flex items-center gap-1 text-xs" style={{ color: "var(--text-muted)" }}>
                <div className="w-1.5 h-1.5 rounded-full" style={{ background: CLIENT_STATUS_COLORS[status] }} />
                {CLIENT_STATUS_LABELS[status]} ({s.count})
              </span>
            );
          })}
        </div>
      </div>
    </div>
  );
}
