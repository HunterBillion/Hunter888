"use client";

/**
 * /dev/avatars-preview — каталог 12 пиксельных портретов БФЛ-арены.
 *
 * 2026-05-01: создана для художника + ревью разработчиком. Сетка 4×3:
 * сверху 4 player-аватара, снизу 8 client-аватаров (5 средневозрастных + 3 senior).
 * Tier-toggle меняет цвет рамки у всех (имитация разных рангов соперников).
 *
 * Художнику: открыть локально или на проде, увидеть все 12 в одном кадре,
 * проверить что портреты различимы в 56×56, заменить любые спрайты в
 * apps/web/src/components/pvp/PixelAvatarSprites.ts → перерендер автомат.
 */

import * as React from "react";
import { motion } from "framer-motion";
import { ArenaBackground } from "@/components/pvp/ArenaBackground";
import {
  PixelPortrait,
  ALL_AVATAR_CODES,
  AVATAR_LABELS,
  isPlayerAvatar,
  type PixelAvatarCode,
} from "@/components/pvp/PixelAvatarLibrary";
import {
  type PvPRankTier,
  PVP_RANK_COLORS,
  PVP_RANK_LABELS,
  normalizeRankTier,
} from "@/types";

const TIERS: PvPRankTier[] = [
  "iron",
  "bronze",
  "silver",
  "gold",
  "platinum",
  "diamond",
  "master",
  "grandmaster",
];

const SIZES = [56, 96, 32] as const;

export default function AvatarsPreviewPage() {
  const [tier, setTier] = React.useState<PvPRankTier>("gold");
  const [size, setSize] = React.useState<(typeof SIZES)[number]>(56);

  const players = ALL_AVATAR_CODES.filter(isPlayerAvatar);
  const clients = ALL_AVATAR_CODES.filter((c) => !isPlayerAvatar(c));

  return (
    <ArenaBackground tier={tier} className="min-h-screen px-4 py-6 sm:px-8 sm:py-10">
      <div className="relative mx-auto max-w-5xl space-y-6">
        <header>
          <h1
            className="font-pixel"
            style={{
              color: "var(--text-primary)",
              fontSize: 32,
              letterSpacing: "0.18em",
              textTransform: "uppercase",
              lineHeight: 1.05,
            }}
          >
            12 Аватаров — Превью
          </h1>
          <p
            className="mt-2 font-pixel"
            style={{ color: "var(--text-muted)", fontSize: 14, letterSpacing: "0.1em" }}
          >
            4 player (карьера БФЛ) + 8 client (реальные демографии должников). Tier меняет рамку.
          </p>
        </header>

        {/* Controls */}
        <div
          className="space-y-4 p-5"
          style={{
            background: "var(--bg-panel)",
            outline: "2px solid var(--accent)",
            outlineOffset: -2,
            boxShadow: "4px 4px 0 0 var(--accent)",
          }}
        >
          <ChipGroup
            label="Тир (цвет рамки)"
            value={tier}
            options={TIERS}
            renderLabel={(t) => PVP_RANK_LABELS[normalizeRankTier(t)] ?? t}
            onChange={(v) => setTier(v as PvPRankTier)}
          />
          <ChipGroup
            label="Размер"
            value={String(size)}
            options={SIZES.map(String)}
            renderLabel={(s) => `${s}px`}
            onChange={(v) => setSize(Number(v) as (typeof SIZES)[number])}
          />
        </div>

        {/* Players */}
        <Section
          title="▸ PLAYER (4) — карьера БФЛ-менеджера"
          subtitle="rookie → operator → senior → lead. Tier-color на бейдже/гарнитуре/орденской планке."
        >
          {players.map((code) => (
            <AvatarCard
              key={code}
              code={code}
              tier={tier}
              size={size}
              variant="player"
            />
          ))}
        </Section>

        {/* Clients middle-aged */}
        <Section
          title="▸ CLIENT — средний возраст (5)"
          subtitle="Должники 28-55 лет. Tier-color ТОЛЬКО на рамке, внутри спрайта — бытовые цвета."
        >
          {clients.slice(0, 5).map((code) => (
            <AvatarCard
              key={code}
              code={code}
              tier={tier}
              size={size}
              variant="client"
            />
          ))}
        </Section>

        {/* Clients senior */}
        <Section
          title="▸ CLIENT — пожилые 60+ (3)"
          subtitle="35-40% всех должников БФЛ по статистике АРБ 2024. grandma + grandpa_worker + vet."
        >
          {clients.slice(5).map((code) => (
            <AvatarCard
              key={code}
              code={code}
              tier={tier}
              size={size}
              variant="client"
            />
          ))}
        </Section>
      </div>
    </ArenaBackground>
  );
}

/* ── UI helpers ──────────────────────────────────────── */

function Section({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  return (
    <section
      className="p-5 space-y-4"
      style={{
        background: "var(--bg-panel)",
        outline: "2px solid var(--border-color)",
        outlineOffset: -2,
        boxShadow: "3px 3px 0 0 var(--border-color)",
      }}
    >
      <div>
        <h2
          className="font-pixel"
          style={{
            color: "var(--text-primary)",
            fontSize: 16,
            letterSpacing: "0.18em",
            textTransform: "uppercase",
          }}
        >
          {title}
        </h2>
        <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
          {subtitle}
        </p>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">{children}</div>
    </section>
  );
}

function AvatarCard({
  code,
  tier,
  size,
  variant,
}: {
  code: PixelAvatarCode;
  tier: PvPRankTier;
  size: number;
  variant: "player" | "client";
}) {
  const label = AVATAR_LABELS[code];
  // Tier color resolves the same way DuelChat does (just for outline).
  const tierColor = tier ? `var(--accent)` : "var(--text-muted)";
  // For demo we use accent regardless of tier mapping — rely on outline only.
  // For real tier-color in outline, FighterCard wraps PixelPortrait separately.

  return (
    <motion.div
      whileHover={{ x: -1, y: -1 }}
      className="flex flex-col items-center gap-2 p-3"
      style={{
        background: "var(--bg-secondary)",
        outline: `2px solid ${variant === "player" ? "var(--accent)" : "var(--text-muted)"}`,
        outlineOffset: -2,
        boxShadow: `3px 3px 0 0 ${variant === "player" ? "var(--accent)" : "var(--text-muted)"}`,
      }}
    >
      {/* Avatar with tier-color frame (like FighterCard does) */}
      <DemoFrame size={size} tier={tier}>
        <PixelPortrait code={code} tier={tier} size={size} />
      </DemoFrame>

      {/* Code in latin */}
      <div
        className="font-pixel"
        style={{
          color: "var(--text-muted)",
          fontSize: 10,
          letterSpacing: "0.18em",
          textTransform: "uppercase",
        }}
      >
        {code}
      </div>

      {/* Russian name */}
      <div
        className="font-pixel text-center"
        style={{
          color: "var(--text-primary)",
          fontSize: 13,
          letterSpacing: "0.08em",
          lineHeight: 1.15,
        }}
      >
        {label.name}
      </div>

      {/* Subtitle / age / story */}
      <div
        className="text-center text-[11px]"
        style={{
          color: "var(--text-muted)",
          lineHeight: 1.3,
          minHeight: "2.4em",
        }}
      >
        {label.subtitle}
      </div>
    </motion.div>
  );
}

/** Имитация фрейма из FighterCard — outline + box-shadow + stippled bg. */
function DemoFrame({
  size,
  tier,
  children,
}: {
  size: number;
  tier: PvPRankTier;
  children: React.ReactNode;
}) {
  // Реальный tier-color рамки — как в FighterCard.tsx (tierColorOf):
  // нормализуем "gold_2" → "gold" и берём hex из PVP_RANK_COLORS.
  const color = PVP_RANK_COLORS[normalizeRankTier(tier)] ?? "var(--text-muted)";
  return (
    <div
      style={{
        width: size,
        height: size,
        outline: `3px solid ${color}`,
        outlineOffset: -3,
        background: `color-mix(in srgb, ${color} 18%, var(--bg-panel))`,
        backgroundImage: `repeating-linear-gradient(
          0deg,
          transparent 0,
          transparent 3px,
          color-mix(in srgb, ${color} 14%, transparent) 3px,
          color-mix(in srgb, ${color} 14%, transparent) 4px
        )`,
        boxShadow: `3px 3px 0 0 ${color}`,
        overflow: "hidden",
      }}
    >
      {children}
    </div>
  );
}

function ChipGroup({
  label,
  value,
  options,
  renderLabel,
  onChange,
}: {
  label: string;
  value: string;
  options: readonly string[];
  renderLabel: (v: string) => string;
  onChange: (v: string) => void;
}) {
  return (
    <div>
      <div
        className="font-pixel mb-2"
        style={{
          color: "var(--text-muted)",
          fontSize: 12,
          letterSpacing: "0.18em",
          textTransform: "uppercase",
        }}
      >
        {label}
      </div>
      <div className="flex flex-wrap gap-2">
        {options.map((opt) => {
          const active = opt === value;
          return (
            <motion.button
              key={opt}
              type="button"
              onClick={() => onChange(opt)}
              whileHover={active ? {} : { x: -1, y: -1 }}
              whileTap={{ x: 2, y: 2 }}
              className="font-pixel"
              style={{
                padding: "6px 12px",
                background: active ? "var(--accent)" : "var(--bg-secondary)",
                color: active ? "#fff" : "var(--text-primary)",
                border: `2px solid ${active ? "var(--accent)" : "var(--border-color)"}`,
                borderRadius: 0,
                fontSize: 12,
                letterSpacing: "0.12em",
                textTransform: "uppercase",
                boxShadow: active
                  ? "3px 3px 0 0 #000, 0 0 12px var(--accent-glow)"
                  : "2px 2px 0 0 var(--border-color)",
                cursor: "pointer",
              }}
            >
              {renderLabel(opt)}
            </motion.button>
          );
        })}
      </div>
    </div>
  );
}
