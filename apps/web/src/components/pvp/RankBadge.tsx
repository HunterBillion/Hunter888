"use client";

import { motion } from "framer-motion";
import { Shield } from "lucide-react";
import { type PvPRankTier, PVP_RANK_COLORS, PVP_RANK_LABELS } from "@/types";
import { getDivision } from "./RatingCard";

interface Props {
  tier: PvPRankTier;
  rating?: number;
  size?: "sm" | "md" | "lg";
  showDivision?: boolean;
}

export function RankBadge({ tier, rating, size = "md", showDivision = true }: Props) {
  const color = PVP_RANK_COLORS[tier] ?? "#9CA3AF";
  const label = PVP_RANK_LABELS[tier] ?? tier;
  const division = showDivision && rating !== undefined ? getDivision(rating, tier) : "";

  const sizes = {
    sm: { icon: 12, text: "text-xs", px: "px-2 py-0.5", gap: "gap-1" },
    md: { icon: 16, text: "text-xs", px: "px-3 py-1.5", gap: "gap-1.5" },
    lg: { icon: 20, text: "text-sm", px: "px-4 py-2", gap: "gap-2" },
  };
  const s = sizes[size];

  const glowTiers = ["diamond", "master", "grandmaster"];

  return (
    <motion.div
      className={`inline-flex items-center ${s.gap} ${s.px} rounded-xl font-mono font-bold ${s.text} ${tier === "diamond" ? "rank-diamond" : ""}`}
      style={{
        background: `${color}15`,
        border: `1px solid ${color}40`,
        color,
        boxShadow: glowTiers.includes(tier) ? `0 0 15px ${color}30` : tier === "platinum" ? `0 0 8px ${color}20` : "none",
      }}
      whileHover={{ scale: 1.05 }}
    >
      <Shield size={s.icon} />
      <span>{label}{division ? ` ${division}` : ""}</span>
      {rating !== undefined && (
        <span style={{ opacity: 0.7 }}>{Math.round(rating)}</span>
      )}
    </motion.div>
  );
}
