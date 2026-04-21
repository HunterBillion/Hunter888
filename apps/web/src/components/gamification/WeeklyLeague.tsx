"use client";

/**
 * WeeklyLeague — compact inline league display.
 * Shows: tier badge, rank, weekly XP, zone indicator.
 * Designed to be embedded inside the mission panel, not as a standalone card.
 */

import { useState, useEffect, useCallback } from "react";
import { Trophy, ChevronUp, ChevronDown, Minus } from "lucide-react";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";

interface LeagueData {
  tier: number;
  tier_name: string;
  group_size: number;
  rank: number;
  weekly_xp: number;
  standings: Array<{
    user_id: string;
    full_name: string;
    weekly_xp: number;
    rank: number;
    is_me: boolean;
  }>;
  promotion_zone: number;
  demotion_zone: number;
  days_remaining: number;
}

const TIER_COLORS: Record<number, string> = {
  0: "var(--text-muted)",
  1: "var(--success)",
  2: "var(--accent)",
  3: "var(--warning)",
  4: "#FF4500",
};

export default function WeeklyLeague() {
  const [data, setData] = useState<LeagueData | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchLeague = useCallback(async () => {
    try {
      const d = await api.get<LeagueData>("/gamification/league/me");
      setData(d);
    } catch (err) {
      logger.error("Failed to fetch league:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchLeague();
  }, [fetchLeague]);

  if (loading) {
    return <span className="inline-flex items-center gap-1 text-xs text-[var(--text-muted)]"><Trophy size={12} /> ...</span>;
  }

  if (!data || data.group_size === 0) {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-[var(--text-muted)]">
        <Trophy size={12} />
        Лига формируется в понедельник
      </span>
    );
  }

  const tierColor = TIER_COLORS[data.tier] || "var(--text-muted)";
  const isPromoZone = data.rank > 0 && data.rank <= data.promotion_zone;
  const isDemoZone = data.rank >= data.demotion_zone;

  const zoneLabel = isPromoZone ? "Повышение" : isDemoZone ? "Понижение" : "";
  const zoneColor = isPromoZone ? "var(--success)" : isDemoZone ? "var(--danger)" : "var(--text-muted)";
  const ZoneIcon = isPromoZone ? ChevronUp : isDemoZone ? ChevronDown : Minus;

  return (
    <div className="flex items-center gap-3 flex-wrap">
      <div className="flex items-center gap-1.5">
        <Trophy size={14} style={{ color: tierColor }} />
        <span className="text-xs font-semibold" style={{ color: tierColor }}>{data.tier_name}</span>
      </div>
      <span className="text-lg font-black font-display" style={{ color: tierColor }}>#{data.rank}</span>
      <span className="text-xs text-[var(--text-muted)]">/ {data.group_size}</span>
      <span className="text-xs font-mono text-[var(--text-muted)]">{data.weekly_xp} XP</span>
      {zoneLabel && (
        <span className="inline-flex items-center gap-0.5 text-[10px] font-medium" style={{ color: zoneColor }}>
          <ZoneIcon size={10} /> {zoneLabel}
        </span>
      )}
    </div>
  );
}
