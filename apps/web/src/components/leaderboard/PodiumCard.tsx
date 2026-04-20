"use client";

import { motion } from "framer-motion";
import { Trophy, Medal, Award } from "lucide-react";
import { UserAvatar } from "@/components/ui/UserAvatar";

export interface PodiumEntry {
  user_id: string;
  full_name: string;
  avatar_url?: string | null;
  score: number;
  delta?: number | null;  // +/- since last period
  scoreUnit?: string;     // "TP" | "HS" | "pts"
}

interface PodiumCardProps {
  top3: PodiumEntry[];
  title?: string;
}

const PLACE_STYLES = [
  {
    icon: Trophy,
    color: "var(--rank-gold, #F7D154)",
    glow: "0 0 24px rgba(247,209,84,0.35)",
    border: "1.5px solid rgba(247,209,84,0.5)",
    height: 160,
  },
  {
    icon: Medal,
    color: "var(--rank-silver, #C8CDD3)",
    glow: "0 0 18px rgba(200,205,211,0.25)",
    border: "1.5px solid rgba(200,205,211,0.4)",
    height: 130,
  },
  {
    icon: Award,
    color: "var(--rank-bronze, #C88A56)",
    glow: "0 0 18px rgba(200,138,86,0.25)",
    border: "1.5px solid rgba(200,138,86,0.4)",
    height: 110,
  },
];

export function PodiumCard({ top3, title }: PodiumCardProps) {
  if (!top3.length) return null;

  // Display order: 2nd, 1st, 3rd (classic podium)
  const displayOrder = [top3[1], top3[0], top3[2]].filter(Boolean) as PodiumEntry[];
  const rankByDisplayIndex = [2, 1, 3];

  return (
    <div className="space-y-3">
      {title && (
        <div className="text-xs font-mono uppercase tracking-widest text-center" style={{ color: "var(--text-muted)" }}>
          {title}
        </div>
      )}
      <div className="flex items-end justify-center gap-3 md:gap-4 px-2">
        {displayOrder.map((entry, i) => {
          const rank = rankByDisplayIndex[i];
          const style = PLACE_STYLES[rank - 1];
          const Icon = style.icon;
          return (
            <motion.div
              key={entry.user_id}
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.08, duration: 0.4, ease: "easeOut" }}
              className="flex flex-col items-center flex-1 max-w-[180px]"
            >
              {/* Avatar */}
              <div
                className="relative mb-2 shrink-0"
                style={{
                  width: rank === 1 ? 68 : 56,
                  height: rank === 1 ? 68 : 56,
                  boxShadow: style.glow,
                  borderRadius: "9999px",
                  outline: style.border,
                  outlineOffset: 1,
                }}
              >
                <UserAvatar
                  avatarUrl={entry.avatar_url}
                  fullName={entry.full_name}
                  size={rank === 1 ? 68 : 56}
                />
                <div
                  className="absolute -top-2 -right-2 flex items-center justify-center rounded-full"
                  style={{
                    width: 24,
                    height: 24,
                    background: "var(--bg-secondary)",
                    border: style.border,
                  }}
                >
                  <Icon size={12} style={{ color: style.color }} />
                </div>
              </div>

              {/* Name */}
              <div
                className="font-display text-sm font-semibold text-center mb-1 truncate max-w-full px-1"
                style={{ color: "var(--text-primary)" }}
                title={entry.full_name}
              >
                {entry.full_name}
              </div>

              {/* Score bar */}
              <div
                className="w-full rounded-t-lg flex flex-col items-center justify-end py-2 px-2"
                style={{
                  background: `color-mix(in srgb, ${style.color} 10%, var(--input-bg))`,
                  border: style.border,
                  height: style.height,
                  boxShadow: style.glow,
                }}
              >
                <div className="font-mono text-[10px] uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                  #{rank}
                </div>
                <div className="font-display font-bold tabular-nums mt-auto" style={{
                  color: style.color,
                  fontSize: rank === 1 ? "1.75rem" : "1.3rem",
                  textShadow: `0 0 10px ${style.color}40`,
                }}>
                  {Math.round(entry.score)}
                </div>
                <div className="text-[10px] font-mono uppercase" style={{ color: "var(--text-muted)" }}>
                  {entry.scoreUnit ?? "TP"}
                </div>
                {entry.delta !== undefined && entry.delta !== null && entry.delta !== 0 && (
                  <div
                    className="text-[10px] font-mono mt-1"
                    style={{ color: entry.delta > 0 ? "var(--success, #22c55e)" : "var(--danger, #ef4444)" }}
                  >
                    {entry.delta > 0 ? "+" : ""}{entry.delta}
                  </div>
                )}
              </div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
