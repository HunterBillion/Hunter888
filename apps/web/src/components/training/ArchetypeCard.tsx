"use client";

import { motion } from "framer-motion";
import { ArrowRight, Loader2, BookOpen, Lock, Crown, Quote, Target, Zap, Phone, MessageCircle } from "lucide-react";
import { getDifficultyColor, getSkillLabel, ARCHETYPE_GROUPS } from "@/lib/archetypes";
import type { ArchetypeInfo } from "@/lib/archetypes";
import type { Scenario } from "@/types";
import { AvatarPreview } from "./AvatarPreview";
import { getDisplayV2 } from "@/lib/archetype_display_v2";

type CardSize = "compact" | "medium" | "full";

// Skill category → color mapping for badges
const SKILL_COLORS: Record<string, string> = {
  empathy: "var(--info)",
  objection_handling: "var(--danger, #ff5f57)",
  rapport: "var(--success)",
  closing: "var(--warning)",
  questioning: "#9a3bef",
  presentation: "var(--accent)",
  negotiation: "#d4a84b",
  active_listening: "var(--info)",
};

function getSkillColor(skill: string): string {
  return SKILL_COLORS[skill] ?? "var(--text-muted)";
}

// Pixel tier stars (1-4)
function TierStars({ tier, color }: { tier: number; color: string }) {
  return (
    <span className="font-pixel text-xs tracking-wider" style={{ color }}>
      {"★".repeat(tier)}{"☆".repeat(Math.max(0, 4 - tier))}
    </span>
  );
}

interface ArchetypeCardProps {
  arch: ArchetypeInfo;
  size: CardSize;
  selected?: boolean;
  onSelect?: () => void;
  scenario?: Scenario | null;
  isStarting?: boolean;
  onStart?: (id: string) => void;
  onStartStory?: (id: string, calls?: number) => void;
  // Phase F (2026-04-20): owner — «в CRM карточке должен быть выбор чат
  // или звонок». ArchetypeCard IS the CRM card (это персона-досье,
  // которую юзер видит в списке сценариев). Когда передан — рендерится
  // как split: [💬 Чат] [📞 Звонок] + Сюжет. Если не передан —
  // сохраняется старый двух-кнопочный layout.
  onStartCall?: (id: string) => void;
  storyCalls?: number;
}

export function ArchetypeCard({ arch, size, selected, onSelect, scenario, isStarting, onStart, onStartStory, onStartCall, storyCalls = 3 }: ArchetypeCardProps) {
  const accentColor = getDifficultyColor(arch.difficulty);
  const group = ARCHETYPE_GROUPS[arch.group];

  // 2026-04-19 Phase 4: curated display data without religion/mysticism
  // framing + extra elements (tagline, signature move, counter hint,
  // threat level) that higher-tier cards progressively reveal.
  const v2 = getDisplayV2(arch.code);
  const displayName = v2?.title ?? arch.name;
  const displayTagline = v2?.tagline ?? arch.subtitle;
  const displayPitch = v2?.pitch ?? arch.description;
  const signature = v2?.signature;
  const counter = v2?.counter;
  const threat = v2?.threat ?? Math.min(100, 25 + arch.tier * 20);
  const tierNum = arch.tier ?? 1; // 1..4

  // Progressive reveal — each tier adds elements without changing color.
  const showTagline = tierNum >= 2;        // T2+: italic catchphrase
  const showSignature = tierNum >= 3;      // T3+: ⚡ signature move
  const showThreatMeter = tierNum >= 3;    // T3+: threat progress bar
  const showCounter = tierNum >= 3;        // T3+: 💡 counter hint
  const isBoss = tierNum >= 4;             // T4: pulsing frame + BOSS badge

  if (size === "compact") {
    return (
      <motion.button
        onClick={onSelect}
        className={`pixel-border p-3 text-left relative overflow-hidden h-full ${selected ? "ring-1 ring-[var(--accent)]" : ""}`}
        style={{ "--pixel-border-color": accentColor, background: "var(--bg-panel)" } as React.CSSProperties}
        whileHover={{ y: -2, transition: { type: "tween", duration: 0.1 } }}
        whileTap={{ scale: 0.97 }}
      >
        <div className="flex items-center gap-2 mb-1">
          <AvatarPreview seed={arch.code} size={32} className="shrink-0 rounded-lg render-pixel" style={{ border: `2px solid ${accentColor}` }} />
          <div className="min-w-0">
            <div className="text-sm font-semibold truncate" style={{ color: "var(--text-primary)" }}>{arch.name}</div>
            <div className="text-xs truncate" style={{ color: "var(--text-muted)" }}>{arch.subtitle}</div>
          </div>
        </div>
        <p className="text-xs line-clamp-2 mt-1" style={{ color: "var(--text-secondary)" }}>{arch.description}</p>
        <div className="mt-2 flex items-center gap-2">
          <span className="text-xs" style={{ color: "var(--text-muted)" }}>{group?.label}</span>
          <span className="ml-auto"><TierStars tier={arch.tier} color={accentColor} /></span>
        </div>
      </motion.button>
    );
  }

  if (size === "medium") {
    // 2026-04-19 v2 tiered-reveal layout. Same accent colour across tiers
    // (user feedback: "не сам цвет, а элементы"); only the ELEMENTS added
    // to the card change:
    //   T1: header + pitch + tags
    //   T2: + italic tagline under the name (character catchphrase)
    //   T3: + signature move row + threat meter bar + counter hint
    //   T4: + pulsing boss aura + "BOSS" corner badge + thicker frame
    return (
      <motion.div
        className="pixel-border flex flex-col overflow-hidden relative"
        style={{
          "--pixel-border-color": isBoss
            ? accentColor
            : `color-mix(in srgb, ${accentColor} 40%, var(--border-color))`,
          background: "var(--bg-panel)",
          minHeight: "200px",
        } as React.CSSProperties}
        whileHover={{ y: -3, transition: { type: "tween", duration: 0.1 } }}
        animate={
          isBoss
            ? {
                boxShadow: [
                  `0 0 0 0 ${accentColor}33`,
                  `0 0 0 6px ${accentColor}00`,
                  `0 0 0 0 ${accentColor}00`,
                ],
              }
            : undefined
        }
        transition={isBoss ? { duration: 2.4, repeat: Infinity } : undefined}
      >
        {/* Top accent strip — thicker on boss */}
        <div
          className="shrink-0"
          style={{
            height: isBoss ? 4 : 3,
            background: isBoss
              ? `linear-gradient(90deg, ${accentColor} 0%, color-mix(in srgb, ${accentColor} 60%, white) 50%, ${accentColor} 100%)`
              : accentColor,
          }}
        />

        {/* BOSS corner badge (T4 only) */}
        {isBoss && (
          <div
            className="absolute top-2 right-2 flex items-center gap-1 rounded-full px-2 py-0.5 z-10 font-pixel text-[10px] tracking-wider"
            style={{
              background: accentColor,
              color: "#000",
              boxShadow: `0 0 12px ${accentColor}88`,
            }}
          >
            <Crown size={10} />
            BOSS
          </div>
        )}

        <div className="p-5 flex flex-col gap-3 flex-1">
          {/* Header row: avatar + name/tagline + tier stars */}
          <div className="flex items-start gap-3">
            <AvatarPreview
              seed={arch.code}
              size={isBoss ? 52 : 44}
              className="shrink-0 rounded-lg render-pixel"
              style={{
                border: `${isBoss ? 3 : 2}px solid ${accentColor}`,
                boxShadow: isBoss ? `0 0 10px ${accentColor}66` : undefined,
              }}
            />
            <div className="flex-1 min-w-0">
              <div
                className="font-semibold leading-tight truncate"
                style={{
                  color: "var(--text-primary)",
                  fontSize: isBoss ? "17px" : "16px",
                  letterSpacing: isBoss ? "0.01em" : undefined,
                }}
              >
                {displayName}
              </div>

              {/* T2+: italic catchphrase quote */}
              {showTagline && displayTagline && (
                <div
                  className="flex items-start gap-1 mt-0.5 text-sm italic leading-tight"
                  style={{ color: accentColor, fontWeight: 500 }}
                >
                  <Quote size={11} className="shrink-0 mt-0.5 opacity-70" />
                  <span className="truncate">«{displayTagline}»</span>
                </div>
              )}

              {/* T1 fallback: non-italic subtitle (legacy field) */}
              {!showTagline && arch.subtitle && (
                <div
                  className="text-sm leading-tight truncate mt-0.5"
                  style={{ color: "var(--text-secondary)", fontWeight: 500 }}
                >
                  {arch.subtitle}
                </div>
              )}

              {group?.label && (
                <span
                  className="inline-block mt-1.5 text-[11px] font-medium rounded px-1.5 py-0.5"
                  style={{
                    background: `color-mix(in srgb, ${accentColor} 12%, transparent)`,
                    color: accentColor,
                  }}
                >
                  {group.label}
                </span>
              )}
            </div>
            <TierStars tier={arch.tier} color={accentColor} />
          </div>

          {/* Pitch — concrete behaviour description */}
          <p
            className="text-sm leading-relaxed line-clamp-3"
            style={{ color: "var(--text-secondary)" }}
          >
            {displayPitch}
          </p>

          {/* T3+: Signature move — character's "you will always see this" behavior */}
          {showSignature && signature && (
            <div
              className="flex items-start gap-2 rounded-md px-2.5 py-1.5 text-xs"
              style={{
                background: `color-mix(in srgb, ${accentColor} 8%, var(--input-bg))`,
                borderLeft: `2px solid ${accentColor}`,
              }}
            >
              <Zap size={12} className="shrink-0 mt-0.5" style={{ color: accentColor }} />
              <div className="min-w-0">
                <div
                  className="font-semibold uppercase tracking-wider text-[9px] mb-0.5"
                  style={{ color: accentColor }}
                >
                  Фирменный приём
                </div>
                <div className="line-clamp-2" style={{ color: "var(--text-primary)" }}>
                  {signature}
                </div>
              </div>
            </div>
          )}

          {/* T3+: Threat meter — visual intensity indicator */}
          {showThreatMeter && (
            <div className="flex items-center gap-2 text-[10px]">
              <span
                className="font-pixel uppercase tracking-wider shrink-0"
                style={{ color: "var(--text-muted)" }}
              >
                Угроза
              </span>
              <div
                className="flex-1 h-1.5 rounded-full overflow-hidden"
                style={{ background: "var(--input-bg)" }}
              >
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${threat}%` }}
                  transition={{ duration: 0.8, ease: "easeOut" }}
                  className="h-full rounded-full"
                  style={{
                    background: `linear-gradient(90deg, ${accentColor}66, ${accentColor})`,
                    boxShadow: isBoss ? `0 0 6px ${accentColor}` : undefined,
                  }}
                />
              </div>
              <span
                className="font-mono tabular-nums"
                style={{ color: accentColor }}
              >
                {threat}
              </span>
            </div>
          )}

          {/* T3+: Counter hint */}
          {showCounter && counter && (
            <div
              className="flex items-start gap-2 rounded-md px-2.5 py-1.5 text-xs"
              style={{
                background: "color-mix(in srgb, var(--success) 8%, var(--input-bg))",
                borderLeft: "2px solid var(--success)",
              }}
            >
              <Target size={12} className="shrink-0 mt-0.5" style={{ color: "var(--success)" }} />
              <div className="min-w-0">
                <div
                  className="font-semibold uppercase tracking-wider text-[9px] mb-0.5"
                  style={{ color: "var(--success)" }}
                >
                  Контрприём
                </div>
                <div className="line-clamp-2" style={{ color: "var(--text-primary)" }}>
                  {counter}
                </div>
              </div>
            </div>
          )}

          {/* Skill badges — pushed to bottom for consistent grid alignment */}
          <div className="flex-1" />
          <div className="flex flex-wrap gap-1.5">
            {arch.counters.slice(0, tierNum >= 3 ? 4 : 3).map((skill) => (
              <span
                key={skill}
                className="font-pixel rounded-none px-2 py-0.5 text-xs pixel-shadow"
                style={{
                  background: `color-mix(in srgb, ${getSkillColor(skill)} 15%, var(--bg-tertiary))`,
                  color: getSkillColor(skill),
                  border: `1px solid color-mix(in srgb, ${getSkillColor(skill)} 25%, transparent)`,
                }}
              >
                {getSkillLabel(skill)}
              </span>
            ))}
          </div>
        </div>
      </motion.div>
    );
  }

  // size === "full" — redesigned 2026-04-17:
  //  - unified min-height so cards in the grid don't squash/stretch wildly
  //  - stronger typography, better contrast (text-secondary over text-muted)
  //  - buttons clearly differentiated: primary SOLID ▶ Начать on accent,
  //    secondary OUTLINE Сюжет with explicit label and smaller visual weight
  //  - gap between buttons increased to gap-3 so they don't visually merge
  return (
    <motion.div
      className="pixel-border flex flex-col overflow-hidden"
      style={{
        "--pixel-border-color": `color-mix(in srgb, ${accentColor} 40%, var(--border-color))`,
        background: "var(--bg-panel)",
        minHeight: "420px",
      } as React.CSSProperties}
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ y: -3, transition: { type: "tween", duration: 0.1 } }}
    >
      <div className="h-[3px] shrink-0" style={{ background: accentColor }} />
      <div className="p-5 flex flex-col flex-1 gap-3">
        {/* Row 1: Avatar + Name + Subtitle + group chip + Tier */}
        <div className="flex items-start gap-3">
          <AvatarPreview
            seed={arch.code}
            size={52}
            className="shrink-0 rounded-lg render-pixel"
            style={{ border: `2px solid ${accentColor}` }}
          />
          <div className="flex-1 min-w-0">
            <div
              className="font-semibold leading-tight truncate"
              style={{ color: "var(--text-primary)", fontSize: "17px" }}
            >
              {arch.name}
            </div>
            <div
              className="text-sm leading-tight truncate mt-0.5"
              style={{ color: "var(--text-secondary)", fontWeight: 500 }}
            >
              {arch.subtitle}
            </div>
            {group?.label && (
              <span
                className="inline-block mt-1.5 text-[11px] font-medium rounded px-1.5 py-0.5"
                style={{
                  background: `color-mix(in srgb, ${accentColor} 12%, transparent)`,
                  color: accentColor,
                }}
              >
                {group.label}
              </span>
            )}
          </div>
          <TierStars tier={arch.tier} color={accentColor} />
        </div>

        {/* Row 2: Description */}
        <p
          className="text-sm leading-relaxed line-clamp-3"
          style={{ color: "var(--text-secondary)", minHeight: "3.75rem" }}
        >
          {arch.description}
        </p>

        {/* Row 3: Weakness hint — higher contrast, separate block */}
        <div
          className="rounded-md px-3 py-2 text-sm"
          style={{
            background: "color-mix(in srgb, var(--danger, #ff5f57) 8%, var(--input-bg))",
            color: "var(--text-primary)",
            border: "1px solid color-mix(in srgb, var(--danger, #ff5f57) 20%, var(--border-color))",
          }}
        >
          <span
            className="font-pixel text-xs uppercase tracking-wider mr-1.5"
            style={{ color: "var(--danger, #ff5f57)" }}
          >
            ⚠ Слабое место:
          </span>
          <span className="line-clamp-2">{arch.weakness}</span>
        </div>

        <div className="flex-1" />

        {/* Row 4: Skill badges — color-coded */}
        <div className="flex flex-wrap gap-1.5">
          {arch.counters.slice(0, 3).map((skill) => (
            <span
              key={skill}
              className="font-pixel rounded-none px-2 py-0.5 text-xs pixel-shadow"
              style={{
                background: `color-mix(in srgb, ${getSkillColor(skill)} 15%, var(--bg-tertiary))`,
                color: getSkillColor(skill),
                border: `1px solid color-mix(in srgb, ${getSkillColor(skill)} 25%, transparent)`,
              }}
            >
              {getSkillLabel(skill)}
            </span>
          ))}
        </div>

        {/* Row 5: Action buttons. Phase F (2026-04-20): three buttons
            when `onStartCall` passed — [💬 Чат] [📞 Звонок] [Сюжет].
            Без onStartCall — legacy две кнопки [Начать] [Сюжет]. */}
        {scenario && onStart && onStartStory ? (
          <div className="flex flex-wrap gap-2 pt-2 mt-1 border-t" style={{ borderColor: "var(--border-color)" }}>
            <motion.button
              onClick={() => onStart(scenario.id)}
              disabled={isStarting}
              className="flex-1 min-w-[100px] flex items-center justify-center gap-1.5 rounded-none py-3 text-sm font-bold text-white font-pixel uppercase tracking-wider pixel-shadow"
              style={{
                background: accentColor,
                opacity: isStarting ? 0.6 : 1,
                letterSpacing: "0.08em",
              }}
              whileTap={{ scale: 0.97 }}
              title={onStartCall ? "Текстовый чат" : "Начать тренировку"}
            >
              {isStarting ? (
                <Loader2 size={16} className="animate-spin" />
              ) : onStartCall ? (
                <><MessageCircle size={14} /> <span>Чат</span></>
              ) : (
                <><span>▶ Начать</span><ArrowRight size={15} /></>
              )}
            </motion.button>
            {onStartCall && (
              <motion.button
                onClick={(e) => {
                  e.stopPropagation();
                  onStartCall(scenario.id);
                }}
                disabled={isStarting}
                className="flex-1 min-w-[100px] flex items-center justify-center gap-1.5 rounded-none py-3 text-sm font-bold font-pixel uppercase tracking-wider"
                style={{
                  background: "transparent",
                  border: `2px solid ${accentColor}`,
                  color: accentColor,
                  letterSpacing: "0.08em",
                  opacity: isStarting ? 0.4 : 1,
                }}
                whileTap={{ scale: 0.97 }}
                title="Голосовой звонок"
                aria-label="Позвонить клиенту"
              >
                <Phone size={14} /> <span>Звонок</span>
              </motion.button>
            )}
            <motion.button
              onClick={(e) => {
                e.stopPropagation();
                onStartStory(scenario.id, storyCalls);
              }}
              disabled={isStarting}
              title={`Запустить сюжетную серию из ${storyCalls} звонков подряд`}
              aria-label={`Сюжет из ${storyCalls} звонков`}
              className="flex-1 min-w-[100px] flex items-center justify-center gap-1.5 rounded-none py-3 text-xs font-bold font-pixel uppercase tracking-wider"
              style={{
                border: `2px solid ${accentColor}`,
                color: accentColor,
                background: "transparent",
                letterSpacing: "0.06em",
                opacity: isStarting ? 0.4 : 1,
              }}
              whileTap={{ scale: 0.97 }}
            >
              <BookOpen size={13} /> Сюжет ({storyCalls})
            </motion.button>
          </div>
        ) : !scenario ? (
          <div
            className="flex items-center justify-center gap-1.5 text-sm py-3 font-pixel pt-2 mt-1 border-t"
            style={{ color: "var(--text-muted)", borderColor: "var(--border-color)" }}
          >
            <Lock size={14} /> Загрузите сценарии
          </div>
        ) : null}
      </div>
    </motion.div>
  );
}
