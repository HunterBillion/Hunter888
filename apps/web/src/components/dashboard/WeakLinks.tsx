"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Loader2, XCircle } from "lucide-react";
import { Warning, Clock, TrendDown } from "@phosphor-icons/react";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";

interface WeakLinkEntry {
  user_id: string;
  full_name: string;
  reasons: string[];
  avg_score: number;
  trend: string;
  sessions_this_week: number;
  last_session_at: string | null;
}

interface WeakLinksData {
  needs_attention: WeakLinkEntry[];
  total_team: number;
  attention_count: number;
}

export function WeakLinks() {
  const [data, setData] = useState<WeakLinksData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/dashboard/rop/weak-links")
      .then((res) => setData(res.data))
      .catch((err) => logger.error("[WeakLinks] Failed to load weak links:", err))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex justify-center py-6">
        <Loader2 size={20} className="animate-spin" style={{ color: "var(--accent)" }} />
      </div>
    );
  }

  if (!data || data.needs_attention.length === 0) {
    return (
      <div className="rounded-xl p-4 text-center" style={{ background: "rgba(34, 197, 94, 0.06)", border: "1px solid rgba(34, 197, 94, 0.2)" }}>
        <span className="text-sm" style={{ color: "var(--success)" }}>
          Все менеджеры в норме
        </span>
      </div>
    );
  }

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
      <div className="flex items-center gap-2 mb-3">
        <Warning size={16} weight="duotone" style={{ color: "var(--warning)" }} />
        <h3 className="font-display text-sm font-bold tracking-wider" style={{ color: "var(--text-primary)" }}>
          ТРЕБУЮТ ВНИМАНИЯ ({data.attention_count}/{data.total_team})
        </h3>
      </div>

      <div className="space-y-2">
        {data.needs_attention.map((entry, i) => (
          <motion.div
            key={entry.user_id}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
            className="rounded-xl p-3"
            style={{
              background: "rgba(239, 68, 68, 0.04)",
              border: "1px solid rgba(239, 68, 68, 0.15)",
            }}
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                {entry.full_name}
              </span>
              <span className="font-mono text-xs" style={{ color: "var(--text-muted)" }}>
                avg {Math.round(entry.avg_score)}
              </span>
            </div>
            <div className="flex flex-wrap gap-1">
              {entry.reasons.map((reason, j) => (
                <span
                  key={j}
                  className="rounded-md px-2 py-0.5 text-xs"
                  style={{
                    background: "rgba(239, 68, 68, 0.1)",
                    color: "var(--danger)",
                  }}
                >
                  {reason}
                </span>
              ))}
            </div>
          </motion.div>
        ))}
      </div>
    </motion.div>
  );
}
