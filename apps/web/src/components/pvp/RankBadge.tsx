"use client";

import { motion } from "framer-motion";
import { Shield } from "@phosphor-icons/react";
import { type PvPRankTier, PVP_RANK_COLORS, PVP_RANK_LABELS, normalizeRankTier } from "@/types";
import { getDivision } from "./RatingCard";
import { colorAlpha } from "@/lib/utils";

interface Props {
  tier: PvPRankTier | string;
  rating?: number;
  size?: "sm" | "md" | "lg";
  showDivision?: boolean;
}

export function RankBadge({ tier: rawTier, rating, size = "md", showDivision = true }: Props) {
  const tier = normalizeRankTier(rawTier);
  const color = PVP_RANK_COLORS[tier] ?? "var(--text-muted)";
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
        background: colorAlpha(color, 8),
        border: `1px solid ${colorAlpha(color, 25)}`,
        color,
        boxShadow: glowTiers.includes(tier) ? `0 0 15px ${colorAlpha(color, 18)}` : tier === "platinum" ? `0 0 8px ${colorAlpha(color, 12)}` : "none",
      }}
      whileHover={{ scale: 1.05 }}
    >
      <Shield weight="duotone" size={s.icon} />
      <span>{label}{division ? ` ${division}` : ""}</span>
      {rating !== undefined && (
        <span style={{ opacity: 0.7 }}>{Math.round(rating)}</span>
      )}
    </motion.div>
  );
}
