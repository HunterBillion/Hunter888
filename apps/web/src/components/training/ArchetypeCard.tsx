"use client";

import { motion } from "framer-motion";
import { ArrowRight, Loader2, BookOpen, Lock } from "lucide-react";
import { getDifficultyColor, getSkillLabel, ARCHETYPE_GROUPS } from "@/lib/archetypes";
import { GROUP_ICONS } from "@/lib/groupIcons";
import type { ArchetypeInfo } from "@/lib/archetypes";
import type { Scenario } from "@/types";

type CardSize = "compact" | "medium" | "full";

interface ArchetypeCardProps {
  arch: ArchetypeInfo;
  size: CardSize;
  selected?: boolean;
  onSelect?: () => void;
  // For "full" size with action buttons
  scenario?: Scenario | null;
  isStarting?: boolean;
  onStart?: (id: string) => void;
  onStartStory?: (id: string, calls?: number) => void;
  storyCalls?: number;
}

export function ArchetypeCard({ arch, size, selected, onSelect, scenario, isStarting, onStart, onStartStory, storyCalls = 3 }: ArchetypeCardProps) {
  const accentColor = getDifficultyColor(arch.difficulty);
  const group = ARCHETYPE_GROUPS[arch.group];

  if (size === "compact") {
    return (
      <motion.button
        onClick={onSelect}
        className={`glass-panel p-3 text-left transition-all relative overflow-hidden rounded-xl h-full ${selected ? "ring-1 ring-[var(--accent)]" : ""}`}
        whileHover={{ y: -2 }}
        whileTap={{ scale: 0.97 }}
      >
        <div className="h-[2px] absolute top-0 left-0 right-0" style={{ background: selected ? accentColor : "transparent" }} />
        <div className="flex items-center gap-2 mb-1">
          <div className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0" style={{ background: `color-mix(in srgb, ${accentColor} 18%, transparent)` }}>
            {(() => { const I = group?.icon ? GROUP_ICONS[group.icon] : null; return I ? <I size={16} weight="duotone" style={{ color: accentColor }} /> : <span className="text-xs font-bold" style={{ color: accentColor }}>{arch.name[0]}</span>; })()}
          </div>
          <div className="min-w-0">
            <div className="text-sm font-semibold truncate" style={{ color: "var(--text-primary)" }}>{arch.name}</div>
            <div className="text-xs truncate" style={{ color: "var(--text-muted)" }}>{arch.subtitle}</div>
          </div>
        </div>
        <p className="text-xs line-clamp-2 mt-1" style={{ color: "var(--text-secondary)" }}>{arch.description}</p>
        <div className="mt-2 flex items-center gap-2">
          <span className="text-xs" style={{ color: "var(--text-muted)" }}>{group?.label}</span>
          <span className="text-xs font-medium ml-auto" style={{ color: accentColor }}>Ур. {arch.tier}</span>
        </div>
      </motion.button>
    );
  }

  if (size === "medium") {
    return (
      <motion.div
        className="glass-panel flex flex-col h-full overflow-hidden"
        style={{ borderColor: `color-mix(in srgb, ${accentColor} 15%, transparent)` }}
        whileHover={{ y: -3 }}
      >
        <div className="h-[3px] shrink-0" style={{ background: accentColor }} />
        <div className="p-5 flex flex-col flex-1 gap-2">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0" style={{ background: `color-mix(in srgb, ${accentColor} 18%, transparent)` }}>
              {(() => { const I = group?.icon ? GROUP_ICONS[group.icon] : null; return I ? <I size={20} weight="duotone" style={{ color: accentColor }} /> : <span className="text-sm font-bold" style={{ color: accentColor }}>{arch.name[0]}</span>; })()}
            </div>
            <div className="flex-1 min-w-0">
              <div className="font-semibold text-base truncate" style={{ color: "var(--text-primary)" }}>{arch.name}</div>
              <div className="text-sm truncate" style={{ color: "var(--text-muted)" }}>{arch.subtitle}</div>
            </div>
            <span className="text-xs font-medium shrink-0 rounded-md px-2 py-0.5" style={{ background: `color-mix(in srgb, ${accentColor} 12%, transparent)`, color: accentColor }}>
              Ур. {arch.tier}
            </span>
          </div>
          <p className="text-sm leading-relaxed line-clamp-2" style={{ color: "var(--text-secondary)" }}>{arch.description}</p>
          <div className="flex-1" />
          <div className="flex flex-wrap gap-1.5">
            {arch.counters.slice(0, 3).map((skill) => (
              <span key={skill} className="rounded-md px-2 py-0.5 text-xs" style={{ background: "var(--input-bg)", color: "var(--text-muted)" }}>
                {getSkillLabel(skill)}
              </span>
            ))}
          </div>
        </div>
      </motion.div>
    );
  }

  // size === "full"
  return (
    <motion.div
      className="glass-panel flex flex-col h-full overflow-hidden"
      style={{ borderColor: `color-mix(in srgb, ${accentColor} 15%, transparent)` }}
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ y: -3 }}
    >
      <div className="h-[3px] shrink-0" style={{ background: accentColor }} />
      <div className="p-5 flex flex-col flex-1 gap-3">
        {/* Row 1: Avatar + Name */}
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0" style={{ background: `color-mix(in srgb, ${accentColor} 18%, transparent)` }}>
            {(() => { const I = group?.icon ? GROUP_ICONS[group.icon] : null; return I ? <I size={22} weight="duotone" style={{ color: accentColor }} /> : <span className="text-sm font-bold" style={{ color: accentColor }}>{arch.name[0]}</span>; })()}
          </div>
          <div className="flex-1 min-w-0">
            <div className="font-semibold text-base truncate" style={{ color: "var(--text-primary)" }}>{arch.name}</div>
            <div className="text-sm truncate" style={{ color: "var(--text-muted)" }}>{arch.subtitle}</div>
          </div>
          <span className="text-xs font-medium shrink-0 rounded-md px-2 py-0.5" style={{ background: `color-mix(in srgb, ${accentColor} 12%, transparent)`, color: accentColor }}>
            Ур. {arch.tier}
          </span>
        </div>

        {/* Row 2: Description */}
        <p className="text-sm leading-relaxed line-clamp-2 min-h-[2.5rem]" style={{ color: "var(--text-secondary)" }}>{arch.description}</p>

        {/* Row 3: Weakness hint */}
        <div className="rounded-lg px-3 py-2 text-sm line-clamp-2" style={{ background: "var(--input-bg)", color: "var(--text-secondary)" }}>
          <span className="font-medium" style={{ color: "var(--text-muted)" }}>Слабое место: </span>
          {arch.weakness}
        </div>

        {/* Spacer */}
        <div className="flex-1" />

        {/* Row 4: Skill badges */}
        <div className="flex flex-wrap gap-1.5">
          {arch.counters.slice(0, 3).map((skill) => (
            <span key={skill} className="rounded-md px-2 py-0.5 text-xs" style={{ background: "var(--input-bg)", color: "var(--text-muted)" }}>
              {getSkillLabel(skill)}
            </span>
          ))}
        </div>

        {/* Row 5: Action buttons */}
        {scenario && onStart && onStartStory ? (
          <div className="flex flex-wrap gap-2 pt-1">
            <motion.button
              onClick={() => onStart(scenario.id)}
              disabled={isStarting}
              className="flex-1 min-w-[120px] flex items-center justify-center gap-2 rounded-lg py-2.5 text-sm font-semibold text-white"
              style={{ background: accentColor, opacity: isStarting ? 0.6 : 1 }}
              whileTap={{ scale: 0.97 }}
            >
              {isStarting ? <Loader2 size={14} className="animate-spin" /> : <><span>Начать</span><ArrowRight size={14} /></>}
            </motion.button>
            <motion.button
              onClick={() => onStartStory(scenario.id, storyCalls)}
              disabled={isStarting}
              className="min-w-[80px] flex items-center justify-center gap-1.5 rounded-lg py-2.5 text-sm font-medium"
              style={{ border: `1px solid color-mix(in srgb, ${accentColor} 30%, transparent)`, color: accentColor }}
              whileTap={{ scale: 0.97 }}
            >
              <BookOpen size={13} /> {storyCalls}x
            </motion.button>
          </div>
        ) : !scenario ? (
          <div className="flex items-center justify-center gap-1.5 text-sm py-2.5" style={{ color: "var(--text-muted)" }}>
            <Lock size={14} /> Загрузите сценарии
          </div>
        ) : null}
      </div>
    </motion.div>
  );
}
