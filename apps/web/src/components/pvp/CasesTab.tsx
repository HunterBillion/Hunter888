"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { useRouter } from "next/navigation";
import {
  Briefcase,
  Lightning,
  Lock,
  ArrowRight,
  Scales,
  UserFocus,
  ShieldCheck,
} from "@phosphor-icons/react";
import { useGamificationStore } from "@/stores/useGamificationStore";

/* ── Case definitions ─────────────────────────────────────────────── */

interface CaseScenario {
  id: string;
  title: string;
  description: string;
  difficulty: 1 | 2 | 3;
  icon: any;
  tags: string[];
  mode: string;
  minLevel: number;
}

const CASES: CaseScenario[] = [
  {
    id: "case_bfl_basic",
    title: "Ипотечник в просрочке",
    description: "Клиент с ипотекой, 3 месяца просрочки. Определите: подходит ли под БФЛ, какие риски для имущества.",
    difficulty: 1,
    icon: Briefcase,
    tags: ["127-ФЗ", "ипотека", "единственное жильё"],
    mode: "case_study",
    minLevel: 6,
  },
  {
    id: "case_alimony",
    title: "Должник с алиментами",
    description: "Клиент платит алименты и имеет долги по кредитам. Как списать долги, не затронув алименты?",
    difficulty: 2,
    icon: Scales,
    tags: ["127-ФЗ", "алименты", "несписываемые долги"],
    mode: "case_study",
    minLevel: 6,
  },
  {
    id: "case_ip_bankruptcy",
    title: "ИП на грани банкротства",
    description: "Индивидуальный предприниматель с долгами перед контрагентами. Банкротство ФЛ или ИП?",
    difficulty: 2,
    icon: UserFocus,
    tags: ["127-ФЗ", "ИП", "субсидиарка"],
    mode: "case_study",
    minLevel: 6,
  },
  {
    id: "case_aggressive_creditor",
    title: "Агрессивный кредитор",
    description: "Коллекторы угрожают, банк подал в суд. Клиент в панике. Выстройте стратегию защиты.",
    difficulty: 3,
    icon: ShieldCheck,
    tags: ["230-ФЗ", "коллекторы", "судебная защита"],
    mode: "case_study",
    minLevel: 6,
  },
];

const DIFF_LABELS: Record<number, { label: string; color: string; emoji: string }> = {
  1: { label: "Базовый", color: "var(--success)", emoji: "🟢" },
  2: { label: "Средний", color: "var(--warning)", emoji: "🟡" },
  3: { label: "Сложный", color: "var(--danger, #ef4444)", emoji: "🔴" },
};

/* ── Component ────────────────────────────────────────────────────── */

export default function CasesTab() {
  const router = useRouter();
  const userLevel = useGamificationStore((s) => s.level);
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  const handleLaunch = (caseItem: CaseScenario) => {
    if (userLevel < caseItem.minLevel) return;
    router.push(`/pvp/quiz?mode=${caseItem.mode}&case=${caseItem.id}`);
  };

  return (
    <motion.div
      key="cases-tab"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.25 }}
      className="space-y-4"
    >
      {/* Header */}
      <div className="flex items-center gap-2 mb-2">
        <Briefcase weight="duotone" size={18} style={{ color: "var(--accent)" }} />
        <span
          className="font-pixel text-xs uppercase tracking-wider"
          style={{ color: "var(--text-muted)" }}
        >
          Разбери реальный кейс — прокачай навыки
        </span>
      </div>

      {/* Case cards grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {CASES.map((c) => {
          const diff = DIFF_LABELS[c.difficulty];
          const locked = userLevel < c.minLevel;
          const IconComp = c.icon;

          return (
            <motion.button
              key={c.id}
              onClick={() => handleLaunch(c)}
              onMouseEnter={() => setHoveredId(c.id)}
              onMouseLeave={() => setHoveredId(null)}
              disabled={locked}
              className="relative rounded-xl p-4 text-left transition-all"
              style={{
                background: locked ? "var(--input-bg)" : "var(--card-bg)",
                border: `1px solid ${hoveredId === c.id && !locked ? "var(--accent)" : "var(--input-bg)"}`,
                opacity: locked ? 0.5 : 1,
                cursor: locked ? "not-allowed" : "pointer",
              }}
              whileHover={locked ? {} : { scale: 1.02 }}
              whileTap={locked ? {} : { scale: 0.98 }}
            >
              {/* Top row: icon + difficulty */}
              <div className="flex items-center justify-between mb-2">
                <div
                  className="w-9 h-9 rounded-lg flex items-center justify-center"
                  style={{ background: "color-mix(in srgb, var(--accent) 10%, transparent)" }}
                >
                  {locked ? (
                    <Lock weight="duotone" size={18} style={{ color: "var(--text-muted)" }} />
                  ) : (
                    <IconComp weight="duotone" size={18} style={{ color: "var(--accent)" }} />
                  )}
                </div>
                <span
                  className="text-xs font-mono px-2 py-0.5 rounded-full"
                  style={{
                    color: diff.color,
                    background: `color-mix(in srgb, ${diff.color} 10%, transparent)`,
                  }}
                >
                  {diff.emoji} {diff.label}
                </span>
              </div>

              {/* Title */}
              <h4
                className="font-medium text-sm mb-1"
                style={{ color: locked ? "var(--text-muted)" : "var(--text-primary)" }}
              >
                {locked ? `🔒 Уровень ${c.minLevel}` : c.title}
              </h4>

              {/* Description */}
              <p
                className="text-xs mb-3 line-clamp-2"
                style={{ color: "var(--text-muted)" }}
              >
                {locked ? "Разблокируется при повышении уровня" : c.description}
              </p>

              {/* Tags */}
              {!locked && (
                <div className="flex flex-wrap gap-1.5 mb-2">
                  {c.tags.map((tag) => (
                    <span
                      key={tag}
                      className="text-[10px] px-1.5 py-0.5 rounded"
                      style={{
                        background: "var(--input-bg)",
                        color: "var(--text-muted)",
                      }}
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              )}

              {/* CTA */}
              {!locked && (
                <div
                  className="flex items-center gap-1 text-xs font-medium"
                  style={{ color: "var(--accent)" }}
                >
                  Начать разбор
                  <ArrowRight size={12} weight="bold" />
                </div>
              )}
            </motion.button>
          );
        })}
      </div>

      {/* Bottom hint */}
      <div
        className="flex items-center gap-2 text-xs px-3 py-2 rounded-lg"
        style={{
          background: "var(--input-bg)",
          color: "var(--text-muted)",
        }}
      >
        <Lightning weight="duotone" size={14} style={{ color: "var(--warning)" }} />
        Кейсы используют ИИ для генерации уникальных ситуаций каждый раз
      </div>
    </motion.div>
  );
}
