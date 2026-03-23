"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { Crosshair, TrendingDown, ArrowRight, Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

interface LossPattern {
  pattern: string;
  count: number;
  scenario_id: string;
  scenario_title: string;
}

interface RecommendationsResponse {
  patterns: LossPattern[];
}

interface TrainingRecommendationsProps {
  managerId?: string;
}

export function TrainingRecommendations({ managerId }: TrainingRecommendationsProps) {
  const router = useRouter();
  const [data, setData] = useState<LossPattern[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const endpoint = managerId
      ? `/clients/recommendations/${managerId}`
      : "/clients/recommendations/my";

    api.get(endpoint)
      .then((resp: RecommendationsResponse) => setData(resp.patterns || []))
      .catch((err) => { console.error("Failed to load training recommendations:", err); })
      .finally(() => setLoading(false));
  }, [managerId]);

  if (loading) {
    return (
      <div className="glass-panel p-5 flex items-center justify-center py-8">
        <Loader2 size={18} className="animate-spin" style={{ color: "var(--accent)" }} />
      </div>
    );
  }

  if (data.length === 0) return null;

  return (
    <div className="glass-panel p-5">
      <div className="flex items-center gap-2 mb-4">
        <Crosshair size={16} style={{ color: "var(--accent)" }} />
        <h3 className="text-xs font-mono tracking-wider" style={{ color: "var(--accent)" }}>
          РЕКОМЕНДАЦИИ ТРЕНИРОВОК
        </h3>
      </div>

      <div className="space-y-2">
        {data.slice(0, 5).map((item, i) => (
          <motion.div
            key={item.scenario_id}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.05 }}
            className="flex items-center gap-3 rounded-lg p-3 cursor-pointer transition-all"
            style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)" }}
            onClick={async () => {
              try {
                const session = await api.post("/training/sessions", { scenario_id: item.scenario_id });
                router.push(`/training/${session.id}`);
              } catch { /* ignore */ }
            }}
          >
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg" style={{ background: "rgba(255,51,51,0.08)" }}>
              <TrendingDown size={14} style={{ color: "var(--neon-red, #FF3333)" }} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-xs font-medium truncate" style={{ color: "var(--text-primary)" }}>
                {item.scenario_title}
              </div>
              <div className="text-[10px] mt-0.5" style={{ color: "var(--text-muted)" }}>
                {item.pattern} ({item.count} потерь)
              </div>
            </div>
            <ArrowRight size={14} style={{ color: "var(--text-muted)" }} />
          </motion.div>
        ))}
      </div>
    </div>
  );
}
