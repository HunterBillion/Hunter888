"use client";

import { motion } from "framer-motion";
import { Clock, ArrowRight, Loader2, BookOpen, User } from "lucide-react";
import { findArchetype, findArchetypeFromTitle, ARCHETYPE_GROUPS, getDifficultyColor } from "@/lib/archetypes";
import { getScenarioTypeConfig } from "@/lib/scenario-utils";
import type { Scenario } from "@/types";

interface ScenarioDossierCardProps {
  scenario: Scenario;
  index: number;
  isStarting: boolean;
  onStart: (id: string) => void;
  onStartStory: (id: string, calls?: number) => void;
  storyCalls: number;
}

export function ScenarioDossierCard({ scenario, index, isStarting, onStart, onStartStory, storyCalls }: ScenarioDossierCardProps) {
  const archetype = findArchetype(scenario.character_name) ?? findArchetypeFromTitle(scenario.title);
  const group = archetype ? ARCHETYPE_GROUPS[archetype.group] : null;
  // FIX-3: Card color reflects difficulty, not archetype group
  const groupColor = getDifficultyColor(scenario.difficulty);
  const typeConfig = getScenarioTypeConfig(scenario.scenario_type);

  const rawName = scenario.character_name ?? "";
  const clientBrief = rawName.length > 2
    ? rawName.length > 100 ? rawName.slice(0, 100) + "..." : rawName
    : null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05, duration: 0.4 }}
      className="relative overflow-hidden rounded-2xl transition-all duration-300 flex flex-col"
      style={{
        background: "var(--glass-bg)",
        border: `1px solid ${groupColor}25`,
        backdropFilter: "blur(24px) saturate(1.5)",
      }}
      whileHover={{
        y: -6,
        boxShadow: `0 20px 60px ${groupColor}20, 0 0 0 1px ${groupColor}40`,
        borderColor: `${groupColor}50`,
      }}
    >
      {/* Top accent bar */}
      <div className="relative h-1.5 shrink-0">
        <div className="absolute inset-0" style={{ background: `linear-gradient(90deg, transparent 5%, ${groupColor} 50%, transparent 95%)` }} />
        <div className="absolute inset-0" style={{ background: `linear-gradient(90deg, transparent 20%, ${groupColor}60 50%, transparent 80%)`, filter: "blur(6px)" }} />
      </div>

      {/* Corner glow */}
      <div className="absolute -top-12 -right-12 w-32 h-32 rounded-full pointer-events-none" style={{ background: `radial-gradient(circle, ${groupColor}12 0%, transparent 70%)` }} />

      {/* Content area — flex-1 pushes buttons to bottom */}
      <div className="p-6 flex flex-col flex-1">

        {/* Row 1: Avatar + archetype */}
        <div className="flex items-start gap-4 mb-4">
          <div
            className="w-14 h-14 rounded-2xl flex items-center justify-center shrink-0"
            style={{
              background: `linear-gradient(135deg, ${groupColor}, ${groupColor}BB)`,
              boxShadow: `0 8px 24px ${groupColor}40, inset 0 1px 0 rgba(255,255,255,0.2)`,
            }}
          >
            <span className="text-xl font-bold text-white">
              {archetype ? archetype.name[0] : <User size={24} />}
            </span>
          </div>

          <div className="flex-1 min-w-0">
            {archetype ? (
              <>
                <div className="font-display text-xl font-bold tracking-wide" style={{ color: groupColor, textShadow: `0 0 20px ${groupColor}30` }}>
                  {archetype.name}
                </div>
                <div className="text-sm mt-1 leading-relaxed line-clamp-2" style={{ color: "var(--text-secondary)" }}>
                  {archetype.description}
                </div>
              </>
            ) : (
              <div className="font-display text-xl font-bold leading-tight" style={{ color: "var(--text-primary)" }}>
                {scenario.title}
              </div>
            )}
          </div>
        </div>

        {/* Row 2: Scenario title */}
        {archetype && (
          <h3 className="font-display text-base font-semibold leading-snug mb-3" style={{ color: "var(--text-primary)" }}>
            {scenario.title}
          </h3>
        )}

        {/* Row 3: Client brief — fixed height with line-clamp */}
        {clientBrief && (
          <div
            className="rounded-xl px-4 py-3 mb-4 relative overflow-hidden"
            style={{ background: `linear-gradient(135deg, ${groupColor}08, transparent)`, border: `1px solid ${groupColor}15` }}
          >
            <div className="absolute left-0 top-0 bottom-0 w-[3px]" style={{ background: groupColor, opacity: 0.5 }} />
            <div className="flex items-center gap-2 mb-1">
              <User size={12} style={{ color: groupColor, opacity: 0.7 }} />
              <span className="font-mono text-sm tracking-[0.15em]" style={{ color: groupColor, opacity: 0.7 }}>Клиент</span>
            </div>
            <p className="text-sm leading-relaxed line-clamp-2" style={{ color: "var(--text-secondary)" }}>{clientBrief}</p>
          </div>
        )}

        {/* Row 4: Description fallback */}
        {!clientBrief && !archetype && (
          <p className="text-sm leading-relaxed mb-4 line-clamp-2" style={{ color: "var(--text-secondary)" }}>
            {scenario.description}
          </p>
        )}

        {/* Spacer — pushes badges and buttons to bottom */}
        <div className="flex-1" />

        {/* Row 5: Meta badges */}
        <div className="flex items-center gap-2 flex-wrap mb-5">
          <span
            className="rounded-lg px-3 py-1.5 text-xs font-mono font-bold uppercase tracking-wider"
            style={{ background: typeConfig.bg, border: `1px solid ${typeConfig.border}`, color: typeConfig.color, boxShadow: `0 2px 8px ${typeConfig.color}15` }}
          >
            {typeConfig.label}
          </span>
          {group && (
            <span
              className="rounded-lg px-3 py-1.5 text-xs font-mono font-bold uppercase tracking-wider"
              style={{ background: `${groupColor}12`, border: `1px solid ${groupColor}25`, color: groupColor }}
            >
              {group.label}
            </span>
          )}
          <span className="flex items-center gap-1 text-xs font-mono ml-auto" style={{ color: "var(--text-muted)" }}>
            <Clock size={12} />
            ~{scenario.estimated_duration_minutes} мин
          </span>
        </div>

        {/* Row 6: Action buttons — always at bottom */}
        <div className="grid grid-cols-[1.2fr_0.8fr] gap-3">
          <motion.button
            onClick={() => onStart(scenario.id)}
            disabled={isStarting}
            className="relative overflow-hidden flex items-center justify-center gap-2 rounded-xl py-3.5 text-sm font-bold uppercase tracking-wider transition-all"
            style={{
              background: `linear-gradient(135deg, ${groupColor}, ${groupColor}CC)`,
              color: "white",
              boxShadow: `0 4px 16px ${groupColor}40`,
              opacity: isStarting ? 0.6 : 1,
            }}
            whileHover={{ boxShadow: `0 8px 32px ${groupColor}50`, scale: 1.02 }}
            whileTap={{ scale: 0.97 }}
          >
            {isStarting ? <Loader2 size={16} className="animate-spin" /> : <><span>Начать</span><ArrowRight size={16} /></>}
          </motion.button>
          <motion.button
            onClick={() => onStartStory(scenario.id, storyCalls)}
            disabled={isStarting}
            className="flex items-center justify-center gap-2 rounded-xl py-3.5 text-sm font-medium transition-all"
            style={{
              border: `1px solid ${groupColor}30`,
              background: `${groupColor}08`,
              color: groupColor,
              opacity: isStarting ? 0.4 : 1,
              pointerEvents: isStarting ? "none" : "auto",
            }}
            whileHover={{ background: `${groupColor}15`, borderColor: `${groupColor}50` }}
            whileTap={{ scale: 0.97 }}
          >
            <BookOpen size={14} />
            История {storyCalls}x
          </motion.button>
        </div>
      </div>
    </motion.div>
  );
}
