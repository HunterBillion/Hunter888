"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Activity, Crosshair, Crown, TrendingUp, Award, Loader2 } from "lucide-react";
import { relativeTime } from "@/lib/time-utils";
import { scoreColor, colorAlpha } from "@/lib/utils";
import type { ActivityFeedItem, ActivityEventType } from "@/types";

const EVENT_CONFIG: Record<ActivityEventType, { icon: typeof Activity; color: string }> = {
  session_completed: { icon: Crosshair, color: "var(--accent)" },
  new_record: { icon: Crown, color: "#FFD700" },
  rank_change: { icon: TrendingUp, color: "var(--neon-green)" },
  achievement_unlocked: { icon: Award, color: "var(--magenta)" },
};

const AVATAR_COLORS = [
  "#6366F1", "#8B5CF6", "#EC4899", "#F43F5E", "#F97316",
  "#EAB308", "#22C55E", "#14B8A6", "#06B6D4", "#3B82F6",
];

function getColor(id: string): string {
  let hash = 0;
  for (let i = 0; i < id.length; i++) hash = ((hash << 5) - hash + id.charCodeAt(i)) | 0;
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
}

function getInitials(name: string): string {
  const trimmed = (name || "").trim();
  if (!trimmed) return "??";
  const parts = trimmed.split(/\s+/);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return trimmed.slice(0, 2).toUpperCase();
}

interface ActivityFeedProps {
  items: ActivityFeedItem[];
  loading?: boolean;
  className?: string;
}

export function ActivityFeed({ items, loading = false, className = "" }: ActivityFeedProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className={`glass-panel rounded-xl overflow-hidden ${className}`}
    >
      {/* Header */}
      <div className="p-5 border-b flex items-center gap-2" style={{ borderColor: "var(--border-color)", background: "var(--input-bg)" }}>
        <Activity size={16} style={{ color: "var(--accent)" }} />
        <span className="font-display text-sm font-bold tracking-widest uppercase" style={{ color: "var(--text-secondary)" }}>
          Активность команды
        </span>
        <span
          className="w-2 h-2 rounded-full animate-pulse ml-1"
          style={{ background: "var(--neon-green, #00FF94)" }}
        />
        <span className="ml-auto font-mono text-xs" style={{ color: "var(--text-muted)" }}>
          {items.length} событий
        </span>
      </div>

      {/* Content */}
      {loading ? (
        <div className="flex items-center justify-center h-24">
          <Loader2 size={16} className="animate-spin" style={{ color: "var(--accent)" }} />
        </div>
      ) : items.length === 0 ? (
        <div className="p-8 text-center">
          <Activity size={32} className="mx-auto animate-float-subtle" style={{ color: "var(--text-muted)", opacity: 0.4 }} />
          <p className="mt-3 text-sm" style={{ color: "var(--text-muted)" }}>
            Пока тихо... Начните тренировку!
          </p>
        </div>
      ) : (
        <div className="divide-y" style={{ borderColor: "var(--border-color)" }}>
          <AnimatePresence>
            {items.map((item, i) => {
              const config = EVENT_CONFIG[item.type] ?? EVENT_CONFIG.session_completed;
              const Icon = config.icon;
              const avatarColor = getColor(item.user_id);

              return (
                <motion.div
                  key={item.id}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.04 }}
                  className="flex items-center gap-4 px-5 py-4 transition-colors duration-200 hover:bg-[rgba(99,102,241,0.04)]"
                  style={{ borderColor: "var(--border-color)" }}
                >
                  {/* Avatar */}
                  <div
                    className="w-10 h-10 rounded-xl flex items-center justify-center text-xs font-bold text-white shrink-0"
                    style={{ background: `linear-gradient(135deg, ${avatarColor}, ${avatarColor}BB)`, boxShadow: `0 2px 8px ${avatarColor}30` }}
                  >
                    {getInitials(item.user_name)}
                  </div>

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm leading-snug" style={{ color: "var(--text-primary)" }}>
                      <span className="font-semibold">{item.user_name.split(" ")[0]}</span>
                      {" "}
                      <span style={{ color: "var(--text-secondary)" }}>{item.message}</span>
                    </p>
                  </div>

                  {/* Score */}
                  {item.score != null && (
                    <span
                      className="font-mono text-base font-bold shrink-0 px-2 py-0.5 rounded-lg"
                      style={{ color: scoreColor(item.score), background: `color-mix(in srgb, ${scoreColor(item.score)} 6%, transparent)` }}
                    >
                      {Math.round(item.score)}
                    </span>
                  )}

                  {/* Type icon + time */}
                  <div className="flex items-center gap-2 shrink-0">
                    <div className="w-6 h-6 rounded-md flex items-center justify-center" style={{ background: colorAlpha(config.color, 8) }}>
                      <Icon size={12} style={{ color: config.color }} />
                    </div>
                    <span className="font-mono text-xs" style={{ color: "var(--text-muted)" }}>
                      {relativeTime(item.created_at)}
                    </span>
                  </div>
                </motion.div>
              );
            })}
          </AnimatePresence>
        </div>
      )}
    </motion.div>
  );
}
