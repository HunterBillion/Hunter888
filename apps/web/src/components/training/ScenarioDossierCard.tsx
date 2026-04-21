"use client";

import { motion } from "framer-motion";
import { Clock, ArrowRight, Loader2, BookOpen, User, Phone, MessageCircle } from "lucide-react";
import { findArchetype, findArchetypeFromTitle, ARCHETYPE_GROUPS, getDifficultyColor } from "@/lib/archetypes";
import { getScenarioTypeConfig } from "@/lib/scenario-utils";
import type { Scenario } from "@/types";

// Phase F (2026-04-20): owner writes «в CRM карточке должен быть выбор
// чат или звонок». Card теперь несёт три действия: Чат / Звонок / Сюжет.
// onStartCall — optional (для обратной совместимости), если не передан
// кнопка «Позвонить» скрывается.
interface ScenarioDossierCardProps {
  scenario: Scenario;
  index: number;
  isStarting: boolean;
  onStart: (id: string) => void;
  onStartStory: (id: string, calls?: number) => void;
  onStartCall?: (id: string) => void;
  storyCalls: number;
}

export function ScenarioDossierCard({ scenario, index, isStarting, onStart, onStartStory, onStartCall, storyCalls }: ScenarioDossierCardProps) {
  const archetype = findArchetype(scenario.character_name) ?? findArchetypeFromTitle(scenario.title);
  const group = archetype ? ARCHETYPE_GROUPS[archetype.group] : null;
  const accentColor = getDifficultyColor(scenario.difficulty);
  const typeConfig = getScenarioTypeConfig(scenario.scenario_type);

  const rawName = scenario.character_name ?? "";
  const clientBrief = rawName.length > 2
    ? rawName.length > 100 ? rawName.slice(0, 100) + "..." : rawName
    : null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.04, duration: 0.3 }}
      className="glass-panel flex flex-col h-full overflow-hidden"
      style={{ borderColor: `color-mix(in srgb, ${accentColor} 20%, transparent)` }}
    >
      {/* Accent top bar — thin, clean */}
      <div className="h-[3px] shrink-0" style={{ background: accentColor }} />

      {/* Content — fixed structure for alignment */}
      <div className="p-5 flex flex-col flex-1 gap-3">

        {/* Row 1: Icon + Name — fixed height */}
        <div className="flex items-center gap-3">
          <div
            className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0 text-white font-bold text-sm"
            style={{ background: accentColor }}
          >
            {archetype ? archetype.name[0] : <User size={18} />}
          </div>
          <div className="flex-1 min-w-0">
            <div className="font-semibold text-base truncate" style={{ color: "var(--text-primary)" }}>
              {archetype?.name ?? scenario.title}
            </div>
            {archetype && (
              <div className="text-sm truncate" style={{ color: "var(--text-muted)" }}>
                {scenario.title}
              </div>
            )}
          </div>
        </div>

        {/* Row 2: Description — fixed 2 lines */}
        <div className="text-sm leading-relaxed line-clamp-2 min-h-[2.5rem]" style={{ color: "var(--text-secondary)" }}>
          {archetype?.description ?? clientBrief ?? scenario.description}
        </div>

        {/* Row 3: Client brief — optional, fixed height slot */}
        {clientBrief && archetype && (
          <div className="rounded-lg px-3 py-2 text-sm line-clamp-2" style={{ background: "var(--input-bg)", color: "var(--text-secondary)" }}>
            {clientBrief}
          </div>
        )}

        {/* Spacer — pushes everything below to bottom */}
        <div className="flex-1" />

        {/* Row 4: Badges — always at same position */}
        <div className="flex items-center gap-2 flex-wrap">
          <span
            className="rounded-md px-2.5 py-1 text-xs font-semibold uppercase tracking-wide"
            style={{ background: typeConfig.bg, color: typeConfig.color }}
          >
            {typeConfig.label}
          </span>
          {group && (
            <span
              className="rounded-md px-2.5 py-1 text-xs font-semibold uppercase tracking-wide"
              style={{ background: `color-mix(in srgb, ${accentColor} 12%, transparent)`, color: accentColor }}
            >
              {group.label}
            </span>
          )}
          <span className="flex items-center gap-1 text-xs ml-auto" style={{ color: "var(--text-muted)" }}>
            <Clock size={12} />
            ~{scenario.estimated_duration_minutes} мин
          </span>
        </div>

        {/* Row 5: Buttons — Phase F (2026-04-20). Три действия: Чат / Звонок /
            Сюжет. Звонок показывается только если передан `onStartCall` —
            для обратной совместимости со старыми местами использования. */}
        <div className={onStartCall ? "grid grid-cols-3 gap-2 pt-1" : "grid grid-cols-[1.2fr_0.8fr] gap-2 pt-1"}>
          <motion.button
            onClick={() => onStart(scenario.id)}
            disabled={isStarting}
            className="flex items-center justify-center gap-1.5 rounded-lg py-2.5 text-sm font-semibold text-white transition-all"
            style={{
              background: accentColor,
              opacity: isStarting ? 0.6 : 1,
            }}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.97 }}
            title="Начать текстовый чат"
          >
            {isStarting ? (
              <Loader2 size={16} className="animate-spin" />
            ) : onStartCall ? (
              <><MessageCircle size={14} /><span>Чат</span></>
            ) : (
              <><span>Начать</span><ArrowRight size={14} /></>
            )}
          </motion.button>
          {onStartCall && (
            <motion.button
              onClick={() => onStartCall(scenario.id)}
              disabled={isStarting}
              className="flex items-center justify-center gap-1.5 rounded-lg py-2.5 text-sm font-semibold transition-all"
              style={{
                background: "transparent",
                border: `2px solid ${accentColor}`,
                color: accentColor,
                opacity: isStarting ? 0.4 : 1,
              }}
              whileHover={{
                scale: 1.02,
                backgroundColor: `color-mix(in srgb, ${accentColor} 12%, transparent)`,
              }}
              whileTap={{ scale: 0.97 }}
              title="Позвонить клиенту голосом"
            >
              <Phone size={14} />
              <span>Звонок</span>
            </motion.button>
          )}
          <motion.button
            onClick={() => onStartStory(scenario.id, storyCalls)}
            disabled={isStarting}
            className="flex items-center justify-center gap-1.5 rounded-lg py-2.5 text-sm font-medium transition-all"
            style={{
              border: `1px solid color-mix(in srgb, ${accentColor} 30%, transparent)`,
              color: accentColor,
              opacity: isStarting ? 0.4 : 1,
              backgroundColor: "rgba(0,0,0,0)",
            }}
            whileHover={{ backgroundColor: `color-mix(in srgb, ${accentColor} 8%, rgba(0,0,0,0))` }}
            whileTap={{ scale: 0.97 }}
          >
            <BookOpen size={13} />
            {storyCalls}x
          </motion.button>
        </div>
      </div>
    </motion.div>
  );
}
