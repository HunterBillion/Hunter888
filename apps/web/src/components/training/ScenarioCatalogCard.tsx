"use client";

/**
 * ScenarioCatalogCard — redesigned 2026-05-05.
 *
 * Replaces the «full»-size ArchetypeCard on `/training` (Сценарии tab)
 * after user feedback: «всё одинаковое — ничего не понятно, дизайн просто
 * ужас». Three things changed vs the old card:
 *
 *   1. Visual rhythm by SCENARIO TYPE, not just by difficulty. Cold
 *      calls get an icy blue accent, warm calls — amber, incoming —
 *      green, special — violet, etc. The grid stops looking like a
 *      stamped row of clones.
 *   2. Single dominant action — «Чат» is the primary button. «Звонок»
 *      and «Сюжет» become compact icon-buttons next to it. The user
 *      always knows what the default click does.
 *   3. «Слабое место» moves into a hover/expand affordance instead of
 *      a permanent loud red box on every card. The fact that EVERY
 *      card screamed «warning» trained the eye to ignore them all.
 *
 * The component is purpose-built for the catalog grid and does NOT
 * replace ArchetypeCard size="medium" / "compact" used in the archetype
 * gallery and constructor preview.
 */

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowRight,
  Loader2,
  BookOpen,
  Phone,
  MessageCircle,
  AlertTriangle,
  Snowflake,
  Flame,
  PhoneIncoming,
  Sparkles,
  RotateCcw,
  Skull,
  Scale,
  Users,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { AvatarPreview } from "./AvatarPreview";
import { ARCHETYPE_GROUPS, getSkillLabel } from "@/lib/archetypes";
import type { ArchetypeInfo } from "@/lib/archetypes";
import type { Scenario } from "@/types";
import { getDisplayV2 } from "@/lib/archetype_display_v2";

// ─── Type-driven palette ─────────────────────────────────────────────────────
//
// Each scenario_type maps to a distinct accent + icon. The palette is
// loud enough to give every card its own identity in a 3-column grid
// but stays inside the existing dark theme — no new tokens.

interface TypeStyle {
  accent: string;        // CSS color literal — used for borders, primary CTA
  glow: string;          // softer shade for backgrounds (rgba)
  label: string;         // human-readable badge label
  Icon: LucideIcon;
}

const TYPE_STYLES: Record<string, TypeStyle> = {
  cold: {
    accent: "#5db4ff",
    glow: "rgba(93, 180, 255, 0.12)",
    label: "Холодный",
    Icon: Snowflake,
  },
  warm: {
    accent: "#ff9f43",
    glow: "rgba(255, 159, 67, 0.12)",
    label: "Тёплый",
    Icon: Flame,
  },
  in: {
    accent: "#3ddc84",
    glow: "rgba(61, 220, 132, 0.12)",
    label: "Входящий",
    Icon: PhoneIncoming,
  },
  special: {
    accent: "#a878ff",
    glow: "rgba(168, 120, 255, 0.14)",
    label: "Особый",
    Icon: Sparkles,
  },
  follow_up: {
    accent: "#5fd6ce",
    glow: "rgba(95, 214, 206, 0.12)",
    label: "Повторный",
    Icon: RotateCcw,
  },
  crisis: {
    accent: "#ff5f57",
    glow: "rgba(255, 95, 87, 0.14)",
    label: "Кризис",
    Icon: Skull,
  },
  compliance: {
    accent: "#d4a84b",
    glow: "rgba(212, 168, 75, 0.12)",
    label: "Комплаенс",
    Icon: Scale,
  },
  multi_party: {
    accent: "#ec6cd0",
    glow: "rgba(236, 108, 208, 0.12)",
    label: "Мультипарти",
    Icon: Users,
  },
};

const FALLBACK_TYPE: TypeStyle = TYPE_STYLES.cold;

// Real scenario_type values from the backend enum carry a sub-channel
// suffix: cold_ad / cold_referral / warm_callback / in_website / etc.
// We match on the high-level prefix so a freshly added cold_* sub-type
// auto-inherits the cold palette without a code change here. The order
// is chosen so the longest prefix wins (multi_party before any «multi»
// future, follow_up before a hypothetical «follow»).
const TYPE_PREFIX_RULES: Array<[string, keyof typeof TYPE_STYLES]> = [
  ["multi_party", "multi_party"],
  ["follow_up", "follow_up"],
  ["compliance", "compliance"],
  ["crisis", "crisis"],
  ["special", "special"],
  ["cold", "cold"],
  ["warm", "warm"],
  ["in_", "in"],
  ["incoming", "in"],
  ["objection", "warm"], // existing seed uses objection_handling — closest semantic match
];

function styleFor(scenarioType: string): TypeStyle {
  const t = (scenarioType || "").toLowerCase();
  if (TYPE_STYLES[t]) return TYPE_STYLES[t];
  for (const [prefix, key] of TYPE_PREFIX_RULES) {
    if (t === prefix || t.startsWith(prefix)) {
      return TYPE_STYLES[key] ?? FALLBACK_TYPE;
    }
  }
  return FALLBACK_TYPE;
}

// ─── Difficulty meter ─────────────────────────────────────────────────────────
//
// 10 thin bars instead of a number — the user reads "where does it stop"
// faster than "what's the digit". Coloured by tier so a 9 feels visibly
// different from a 4 even before reading the label.

interface DifficultyMeterProps {
  level: number; // 1..10
}

function DifficultyMeter({ level }: DifficultyMeterProps) {
  const clamped = Math.max(1, Math.min(10, Math.round(level)));
  const tier = clamped <= 3 ? "easy" : clamped <= 6 ? "med" : clamped <= 8 ? "hard" : "boss";
  const colors: Record<typeof tier, string> = {
    easy: "var(--success, #3ddc84)",
    med: "var(--warning, #f59e0b)",
    hard: "var(--danger, #ff5f57)",
    boss: "#ff0055",
  };
  const labels: Record<typeof tier, string> = {
    easy: "Легко",
    med: "Средне",
    hard: "Сложно",
    boss: "Босс",
  };
  return (
    <div className="flex items-center gap-2">
      <div className="flex gap-[2px]">
        {Array.from({ length: 10 }).map((_, i) => (
          <span
            key={i}
            className="h-3 w-[3px] rounded-sm transition-opacity"
            style={{
              background: i < clamped ? colors[tier] : "rgba(255,255,255,0.08)",
            }}
          />
        ))}
      </div>
      <span
        className="text-[11px] font-semibold uppercase tracking-wider"
        style={{ color: colors[tier] }}
      >
        {labels[tier]} · {clamped}/10
      </span>
    </div>
  );
}

// ─── Card ─────────────────────────────────────────────────────────────────────

interface ScenarioCatalogCardProps {
  scenario: Scenario;
  arch: ArchetypeInfo;
  isStarting?: boolean;
  onStart: (id: string) => void;
  onStartCall?: (id: string) => void;
  onStartStory: (id: string, calls?: number) => void;
  storyCalls?: number;
}

export function ScenarioCatalogCard({
  scenario,
  arch,
  isStarting,
  onStart,
  onStartCall,
  onStartStory,
  storyCalls = 3,
}: ScenarioCatalogCardProps) {
  const ts = styleFor(scenario.scenario_type);
  const TypeIcon = ts.Icon;
  const [showWeakness, setShowWeakness] = useState(false);

  // Pull the curated v2 display name/pitch when available — the v2
  // catalogue strips religion/mysticism framing the original copy had.
  const v2 = getDisplayV2(arch.code);
  const displayName = v2?.title ?? arch.name;
  const tagline = v2?.tagline ?? arch.subtitle;

  const groupLabel = ARCHETYPE_GROUPS[arch.group]?.label;

  return (
    // PR-D: pilot users said the cards looked «хлипкие» — 1px borders +
    // text-sm copy made each card feel paper-thin in a 3-column grid on
    // a dark background. Bumped border to 2px, raised body copy a step,
    // gave the card a bit more breathing room (p-4 → p-5) so the visual
    // weight matches the Конструктор cards.
    <motion.div
      className="relative flex flex-col overflow-hidden rounded-2xl"
      style={{
        background: `linear-gradient(180deg, ${ts.glow} 0%, var(--bg-panel) 60%)`,
        border: `2px solid color-mix(in srgb, ${ts.accent} 35%, var(--border-color))`,
        minHeight: "320px",
      }}
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ y: -3, boxShadow: `0 8px 28px -8px ${ts.accent}66` }}
      transition={{ type: "tween", duration: 0.18 }}
    >
      {/* Top accent ribbon — instant type-identifier, no reading needed */}
      <div
        className="flex items-center gap-2 px-4 py-2"
        style={{
          background: `linear-gradient(90deg, ${ts.accent} 0%, transparent 70%)`,
          borderBottom: `1px solid color-mix(in srgb, ${ts.accent} 22%, transparent)`,
        }}
      >
        <TypeIcon size={14} style={{ color: "#ffffff" }} />
        <span className="text-[11px] font-bold uppercase tracking-[0.14em] text-white">
          {ts.label}
        </span>
        {groupLabel && (
          <span
            className="ml-auto text-[10px] font-semibold uppercase tracking-wider"
            style={{ color: "rgba(255,255,255,0.78)" }}
          >
            {groupLabel}
          </span>
        )}
      </div>

      <div className="flex flex-col gap-3.5 p-5 flex-1">
        {/* Hero row — bigger avatar, name, tagline */}
        <div className="flex items-start gap-3.5">
          <div className="relative shrink-0">
            <AvatarPreview
              seed={arch.code}
              size={72}
              className="rounded-xl render-pixel"
              style={{
                border: `2px solid ${ts.accent}`,
                boxShadow: `0 0 0 3px color-mix(in srgb, ${ts.accent} 18%, transparent)`,
              }}
            />
            {/* Tier crown stamp for boss-tier archetypes */}
            {arch.tier >= 4 && (
              <span
                className="absolute -top-2 -right-2 rounded-full px-1.5 py-0.5 text-[9px] font-bold uppercase"
                style={{ background: "#ff0055", color: "#fff" }}
              >
                BOSS
              </span>
            )}
          </div>
          <div className="min-w-0 flex-1">
            <div
              className="text-lg font-bold leading-tight truncate"
              style={{ color: "var(--text-primary)" }}
            >
              {displayName}
            </div>
            {tagline && (
              <div
                className="mt-1 text-sm italic truncate"
                style={{ color: "var(--text-muted)" }}
              >
                «{tagline}»
              </div>
            )}
            <div className="mt-2">
              <DifficultyMeter level={scenario.difficulty} />
            </div>
          </div>
        </div>

        {/* Scenario title — the actual training topic, not the archetype */}
        {scenario.title && scenario.title !== displayName && (
          <div
            className="text-base font-semibold leading-snug line-clamp-2"
            style={{ color: "var(--text-primary)" }}
          >
            {scenario.title}
          </div>
        )}

        {/* Description — short, kept */}
        <p
          className="text-sm leading-relaxed line-clamp-2"
          style={{ color: "var(--text-secondary)" }}
        >
          {scenario.description || arch.description}
        </p>

        {/* Skill chips — what the trainee will practice */}
        {arch.counters && arch.counters.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {arch.counters.slice(0, 3).map((skill) => (
              <span
                key={skill}
                className="rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider"
                style={{
                  background: "var(--bg-tertiary)",
                  color: "var(--text-secondary)",
                  border: "1px solid var(--border-color)",
                }}
              >
                {getSkillLabel(skill)}
              </span>
            ))}
          </div>
        )}

        {/* Weakness — collapsible. Default closed: keeps the card
            uncluttered; click reveals the hint when the user actually
            wants to read it. The toggle button only renders when there
            IS a weakness — otherwise we'd have a control that does
            nothing on click, which reads as a UI bug. */}
        {arch.weakness && (
          <>
            <button
              type="button"
              onClick={() => setShowWeakness((v) => !v)}
              aria-expanded={showWeakness}
              className="flex items-center gap-1.5 text-[11px] font-semibold transition-colors w-fit"
              style={{ color: "var(--text-muted)" }}
            >
              <AlertTriangle size={12} style={{ color: "var(--danger, #ff5f57)" }} />
              <span>{showWeakness ? "Скрыть подсказку" : "Слабое место →"}</span>
            </button>
            <AnimatePresence initial={false}>
              {showWeakness && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  className="overflow-hidden"
                >
                  <div
                    className="rounded-lg px-2.5 py-2 text-xs leading-relaxed"
                    style={{
                      background: "rgba(255, 95, 87, 0.08)",
                      borderLeft: "2px solid var(--danger, #ff5f57)",
                      color: "var(--text-primary)",
                    }}
                  >
                    {arch.weakness}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </>
        )}

        <div className="flex-1" />

        {/* Actions — clear hierarchy.
            PR-D: bumped button height (py-2.5 → py-3) and the icon-only
            secondary buttons now carry text labels («Звонок» / «×N»)
            so they stop reading as decoration. The primary «Чат» button
            still dominates via gradient + arrow + flex-1 — hierarchy
            preserved, secondaries just no longer mute themselves into
            invisibility. */}
        <div className="flex items-stretch gap-2 pt-2">
          <motion.button
            onClick={() => onStart(scenario.id)}
            disabled={isStarting}
            whileTap={{ scale: 0.97 }}
            className="flex-1 min-w-0 flex items-center justify-center gap-2 rounded-xl py-3 text-sm font-bold text-white"
            style={{
              background: `linear-gradient(135deg, ${ts.accent} 0%, color-mix(in srgb, ${ts.accent} 70%, #000) 100%)`,
              boxShadow: `0 4px 14px -4px ${ts.accent}80`,
              opacity: isStarting ? 0.6 : 1,
            }}
          >
            {isStarting ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <>
                <MessageCircle size={16} />
                <span>Чат</span>
                <ArrowRight size={14} className="opacity-80" />
              </>
            )}
          </motion.button>
          {onStartCall && (
            <motion.button
              onClick={(e) => {
                e.stopPropagation();
                onStartCall(scenario.id);
              }}
              disabled={isStarting}
              whileTap={{ scale: 0.97 }}
              title="Голосовой звонок"
              aria-label="Голосовой звонок"
              className="flex items-center justify-center gap-1.5 rounded-xl px-3 py-3 text-xs font-semibold"
              style={{
                background: "transparent",
                border: `2px solid ${ts.accent}`,
                color: ts.accent,
                opacity: isStarting ? 0.4 : 1,
              }}
            >
              <Phone size={15} />
              <span className="hidden sm:inline">Звонок</span>
            </motion.button>
          )}
          <motion.button
            onClick={(e) => {
              e.stopPropagation();
              onStartStory(scenario.id, storyCalls);
            }}
            disabled={isStarting}
            whileTap={{ scale: 0.97 }}
            title={`Сюжет из ${storyCalls} звонков подряд`}
            aria-label={`Сюжет из ${storyCalls} звонков`}
            className="flex items-center justify-center gap-1.5 rounded-xl px-3 py-3 text-xs font-semibold"
            style={{
              background: "transparent",
              border: `2px solid ${ts.accent}`,
              color: ts.accent,
              opacity: isStarting ? 0.4 : 1,
            }}
          >
            <BookOpen size={15} />
            <span className="font-bold">×{storyCalls}</span>
          </motion.button>
        </div>
      </div>
    </motion.div>
  );
}
