"use client";

import { useEffect, useState } from "react";
import { Zap, TrendingDown } from "lucide-react";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";

interface DailyXPStatus {
  earned_today: number;
  tier1_limit: number;
  tier2_limit: number;
  current_rate: number;
  next_tier_at: number | null;
}

export function XPDailyProgress({ className = "" }: { className?: string }) {
  const [status, setStatus] = useState<DailyXPStatus | null>(null);

  useEffect(() => {
    api.get<DailyXPStatus>("/gamification/xp-daily")
      .then(setStatus)
      .catch((err) => logger.error("[XPDailyProgress] xp-daily fetch failed:", err));
  }, []);

  if (!status) return null;

  const { earned_today, tier1_limit, tier2_limit, current_rate } = status;

  const displayMax = tier2_limit;
  const pct = Math.min((earned_today / displayMax) * 100, 100);
  const tier1Pct = (tier1_limit / displayMax) * 100;

  const rateLabel =
    current_rate >= 1 ? "100%" : current_rate >= 0.5 ? "50%" : "25%";
  const isReduced = current_rate < 1;

  return (
    <div className={`rounded-xl p-4 ${className}`} style={{ background: "var(--glass-bg)", border: "1px solid var(--glass-border)" }}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Zap size={18} style={{ color: "var(--accent)" }} />
          <span className="text-sm font-semibold" style={{ color: "var(--text-secondary)" }}>
            XP сегодня
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          {isReduced && <TrendingDown size={16} style={{ color: "var(--warning)" }} />}
          <span
            className="font-mono text-sm font-bold tabular-nums"
            style={{ color: isReduced ? "var(--warning)" : "var(--accent)" }}
          >
            ×{rateLabel}
          </span>
        </div>
      </div>

      {/* Progress bar */}
      <div className="relative h-3 rounded-full overflow-hidden" style={{ background: "var(--input-bg)" }}>
        <div
          className="absolute top-0 bottom-0 w-px"
          style={{ left: `${tier1Pct}%`, background: "var(--text-muted)", opacity: 0.4 }}
        />
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{
            width: `${pct}%`,
            background: isReduced
              ? "linear-gradient(90deg, var(--accent), var(--warning))"
              : "var(--accent)",
          }}
        />
      </div>

      {/* Labels — min 14px */}
      <div className="flex items-center justify-between mt-2">
        <span className="font-mono text-sm font-semibold tabular-nums" style={{ color: "var(--text-primary)" }}>
          {earned_today.toLocaleString()} XP
        </span>
        {status.next_tier_at !== null && (
          <span className="text-sm" style={{ color: "var(--text-muted)" }}>
            ещё {status.next_tier_at.toLocaleString()} до снижения
          </span>
        )}
      </div>
    </div>
  );
}
