"use client";

import { motion } from "framer-motion";
import { Shield } from "lucide-react";
import { type PvPRankTier, PVP_RANK_COLORS, PVP_RANK_LABELS } from "@/types";

interface Props {
  tier: PvPRankTier;
  rating?: number;
  size?: "sm" | "md" | "lg";
}

export function RankBadge({ tier, rating, size = "md" }: Props) {
  const color = PVP_RANK_COLORS[tier];
  const label = PVP_RANK_LABELS[tier];

  const sizes = {
    sm: { icon: 12, text: "text-[10px]", px: "px-2 py-0.5", gap: "gap-1" },
    md: { icon: 16, text: "text-xs", px: "px-3 py-1.5", gap: "gap-1.5" },
    lg: { icon: 20, text: "text-sm", px: "px-4 py-2", gap: "gap-2" },
  };
  const s = sizes[size];

  return (
    <motion.div
      className={`inline-flex items-center ${s.gap} ${s.px} rounded-xl font-mono font-bold ${s.text} ${tier === "diamond" ? "rank-diamond" : ""}`}
      style={{
        background: `${color}15`,
        border: `1px solid ${color}40`,
        color,
        boxShadow: tier === "diamond" ? `0 0 15px ${color}30` : tier === "platinum" ? `0 0 8px ${color}20` : "none",
      }}
      whileHover={{ scale: 1.05 }}
    >
      <Shield size={s.icon} />
      <span>{label}</span>
      {rating !== undefined && (
        <span style={{ opacity: 0.7 }}>{Math.round(rating)}</span>
      )}
    </motion.div>
  );
}
