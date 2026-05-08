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

// 2026-05-08 (полировка): подняты размеры аватара, плашек, типографики.
// Дуолинго-style: крупная карточка с явной иерархией, имя 16px (было 14),
// score 32-40px (было 21-28), круглый аватар 88/72 (было 68/56). Высота
// плашек тоже подросла, чтобы был «трон» эффект.
const PLACE_STYLES = [
  {
    icon: Trophy,
    color: "var(--rank-gold, #F7D154)",
    glow: "0 0 28px rgba(247,209,84,0.5)",
    border: "2px solid rgba(247,209,84,0.7)",
    height: 200,
  },
  {
    icon: Medal,
    color: "var(--rank-silver, #C8CDD3)",
    glow: "0 0 22px rgba(200,205,211,0.4)",
    border: "2px solid rgba(200,205,211,0.55)",
    height: 165,
  },
  {
    icon: Award,
    color: "var(--rank-bronze, #C88A56)",
    glow: "0 0 22px rgba(200,138,86,0.4)",
    border: "2px solid rgba(200,138,86,0.55)",
    height: 140,
  },
];

export function PodiumCard({ top3, title }: PodiumCardProps) {
  if (!top3.length) return null;

  // Display order: 2nd, 1st, 3rd (classic podium)
  const displayOrder = [top3[1], top3[0], top3[2]].filter(Boolean) as PodiumEntry[];
  const rankByDisplayIndex = [2, 1, 3];

  return (
    <div className="space-y-4">
      {title && (
        <div
          className="font-pixel uppercase tracking-widest text-center"
          style={{ color: "var(--text-muted)", fontSize: 14 }}
        >
          ▰ {title} ▰
        </div>
      )}
      <div className="flex items-end justify-center gap-4 md:gap-6 px-2">
        {displayOrder.map((entry, i) => {
          const rank = rankByDisplayIndex[i];
          const style = PLACE_STYLES[rank - 1];
          const Icon = style.icon;
          // 1-е место — самый крупный аватар, 2/3 чуть меньше.
          const avatarSize = rank === 1 ? 88 : 72;
          return (
            <motion.div
              key={entry.user_id}
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.08, duration: 0.4, ease: "easeOut" }}
              className="flex flex-col items-center flex-1 max-w-[200px]"
            >
              {/* Аватар с короной/медалью */}
              <div
                className="relative mb-3 shrink-0"
                style={{
                  width: avatarSize,
                  height: avatarSize,
                  boxShadow: style.glow,
                  borderRadius: "9999px",
                  outline: style.border,
                  outlineOffset: 2,
                }}
              >
                <UserAvatar
                  avatarUrl={entry.avatar_url}
                  fullName={entry.full_name}
                  size={avatarSize}
                />
                <div
                  className="absolute -top-2 -right-2 flex items-center justify-center rounded-full"
                  style={{
                    width: rank === 1 ? 32 : 28,
                    height: rank === 1 ? 32 : 28,
                    background: "var(--bg-secondary)",
                    border: style.border,
                    boxShadow: style.glow,
                  }}
                >
                  <Icon size={rank === 1 ? 16 : 14} style={{ color: style.color }} />
                </div>
              </div>

              {/*
                Имя — крупное, на 2 строки если длинное (line-clamp-2 вместо
                truncate). Жирное, читаемое. Дуолинго-style.
              */}
              <div
                className="font-display font-bold text-center mb-2 px-1 leading-tight"
                style={{
                  color: "var(--text-primary)",
                  fontSize: rank === 1 ? 18 : 16,
                  display: "-webkit-box",
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: "vertical",
                  overflow: "hidden",
                  minHeight: rank === 1 ? "2.5em" : "2.3em",
                }}
                title={entry.full_name}
              >
                {entry.full_name}
              </div>

              {/* Плашка-«трон» с местом и баллами */}
              <div
                className="w-full rounded-t-lg flex flex-col items-center justify-end py-3 px-2"
                style={{
                  background: `color-mix(in srgb, ${style.color} 12%, var(--input-bg))`,
                  border: style.border,
                  borderBottom: "none",
                  height: style.height,
                  boxShadow: style.glow,
                }}
              >
                <div
                  className="font-pixel uppercase tracking-widest"
                  style={{ color: style.color, fontSize: 14 }}
                >
                  #{rank}
                </div>
                <div
                  className="font-display font-black tabular-nums mt-auto"
                  style={{
                    color: style.color,
                    fontSize: rank === 1 ? 40 : 32,
                    lineHeight: 1.0,
                    textShadow: `0 0 14px ${style.color}66`,
                  }}
                >
                  {Math.round(entry.score)}
                </div>
                <div
                  className="font-pixel uppercase tracking-widest mt-1"
                  style={{ color: "var(--text-muted)", fontSize: 13 }}
                >
                  {entry.scoreUnit ?? "TP"}
                </div>
                {entry.delta !== undefined && entry.delta !== null && entry.delta !== 0 && (
                  <div
                    className="font-mono font-semibold mt-1"
                    style={{
                      color: entry.delta > 0 ? "var(--success, #22c55e)" : "var(--danger, #ef4444)",
                      fontSize: 14,
                    }}
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
