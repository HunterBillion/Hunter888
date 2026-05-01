"use client";

/**
 * FighterCard — карточка бойца (свой/соперник) для сцены дуэли.
 *
 * 2026-04-29 (Фаза 3): объединяет PixelAvatar (60×60), имя, тир-бэйдж
 * и HPBar. Зеркально слева/справа.
 *
 * Аватар — тот же 16×16 спрайт, что в DuelChat. Здесь увеличиваем до
 * 60×60 для лучшей видимости. Tier-цвет используется на outline аватара,
 * рамке самой карточки, badge ранга и full-state HP.
 */

import * as React from "react";
import { motion } from "framer-motion";
import {
  type PvPRankTier,
  PVP_RANK_COLORS,
  PVP_RANK_LABELS,
  normalizeRankTier,
} from "@/types";
import { HPBar } from "./HPBar";
// 2026-05-01: 12-portrait library заменила локальные SPRITE_MANAGER/CLIENT.
// PixelPortrait сам читает спрайт по коду + применяет tier для player-литералов.
import { PixelPortrait, type PixelAvatarCode } from "./PixelAvatarLibrary";

function tierColorOf(tier?: PvPRankTier | string): string {
  if (!tier) return "var(--text-muted)";
  const norm = normalizeRankTier(typeof tier === "string" ? tier : tier);
  return PVP_RANK_COLORS[norm] ?? "var(--text-muted)";
}

function tierLabelOf(tier?: PvPRankTier | string): string {
  if (!tier) return "Без ранга";
  const norm = normalizeRankTier(typeof tier === "string" ? tier : tier);
  return PVP_RANK_LABELS[norm] ?? norm;
}

interface Props {
  side: "left" | "right";
  /** Имя бойца — если undefined, показываем «БОЕЦ». */
  name?: string;
  /** Тир — рамка/HP/badge (player) или ТОЛЬКО рамка (client). */
  tier?: PvPRankTier | string;
  /**
   * 2026-05-01: вместо `role` теперь явный `avatar` код из 12-portrait library.
   * Backwards-compat: если передан старый `role`, маппится на operator/grandma.
   */
  avatar?: PixelAvatarCode;
  role?: "seller" | "client"; // legacy; держится для существующих call-сайтов
  /** HP 0..100. По умолчанию 100. */
  hp?: number;
  /** Bot? Лейбл BOT под именем вместо реального ника. */
  isBot?: boolean;
  /** Подсветка карточки — если боец сейчас «активен» (его очередь говорить). */
  active?: boolean;
}

export function FighterCard({
  side,
  name,
  tier,
  avatar,
  role,
  hp = 100,
  isBot = false,
  active = false,
}: Props) {
  const accent = tierColorOf(tier);
  // Resolve avatar:
  // 1) explicit `avatar` prop wins
  // 2) legacy `role` prop maps to neutral defaults (operator / grandma)
  // 3) fallback operator
  const avatarCode: PixelAvatarCode =
    avatar ?? (role === "seller" ? "operator" : role === "client" ? "grandma" : "operator");
  const display = name || (isBot ? "AI-БОТ" : "БОЕЦ");
  const tierLabel = tierLabelOf(tier);

  return (
    <motion.div
      animate={{
        y: active ? -2 : 0,
        boxShadow: active
          ? `4px 4px 0 0 ${accent}, 0 0 16px ${accent}`
          : `3px 3px 0 0 ${accent}`,
      }}
      transition={{ type: "spring", stiffness: 400, damping: 25 }}
      className={`flex items-center gap-3 p-3 ${side === "right" ? "flex-row-reverse" : "flex-row"}`}
      style={{
        background: "var(--bg-panel)",
        outline: `2px solid ${accent}`,
        outlineOffset: -2,
        borderRadius: 0,
        minWidth: 240,
      }}
    >
      {/* Avatar */}
      <div
        className="shrink-0 relative overflow-hidden"
        style={{
          width: 64,
          height: 64,
          outline: `3px solid ${accent}`,
          outlineOffset: -3,
          background: `color-mix(in srgb, ${accent} 18%, var(--bg-panel))`,
          backgroundImage: `repeating-linear-gradient(
            0deg,
            transparent 0,
            transparent 3px,
            color-mix(in srgb, ${accent} 14%, transparent) 3px,
            color-mix(in srgb, ${accent} 14%, transparent) 4px
          )`,
        }}
      >
        <PixelPortrait code={avatarCode} tier={tier} size={64} />
      </div>

      {/* Right side — name, tier, HP */}
      <div className={`flex flex-col gap-1 flex-1 ${side === "right" ? "items-end" : "items-start"}`}>
        <div className="flex items-baseline gap-2 flex-wrap">
          <span
            className="font-pixel"
            style={{
              color: "var(--text-primary)",
              fontSize: 16,
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              lineHeight: 1.1,
            }}
          >
            {display}
          </span>
          {isBot && (
            <span
              className="font-pixel"
              style={{
                fontSize: 10,
                letterSpacing: "0.18em",
                color: "var(--text-muted)",
                background: "var(--bg-tertiary)",
                padding: "1px 6px",
                border: "1px solid var(--border-color)",
              }}
            >
              BOT
            </span>
          )}
        </div>
        <span
          className="font-pixel"
          style={{
            color: accent,
            fontSize: 11,
            letterSpacing: "0.18em",
            textTransform: "uppercase",
          }}
        >
          {tierLabel}
        </span>
        <HPBar
          value={hp}
          tierColor={accent}
          direction={side === "right" ? "rtl" : "ltr"}
          width={170}
          height={10}
          segments={18}
        />
      </div>
    </motion.div>
  );
}
