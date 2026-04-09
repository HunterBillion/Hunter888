"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ChevronDown,
  MessageCircle,
  FileText,
  Shield,
  MessageSquare,
  AlertOctagon,
  Target,
  Link2,
  Crosshair,
  Heart,
  BookOpen,
  Scale,
} from "lucide-react";
import { colorAlpha } from "@/lib/utils";

interface LayerScore {
  key: string;
  label: string;
  shortLabel: string;
  description: string;
  value: number;
  maxValue: number;
  isModifier?: boolean;
  icon: React.ComponentType<{ size: number; style?: React.CSSProperties }>;
}

export interface LayerExplanation {
  layer: string;
  label: string;
  score: number;
  max_score: number;
  percentage: number;
  summary: string;
  highlights: {
    message_index: number;
    role: string;
    excerpt: string;
    impact: string;
    delta: number;
  }[];
}

const LAYER_DEFS: LayerScore[] = [
  { key: "score_script_adherence", label: "Следование скрипту", shortLabel: "L1 Скрипт", description: "Насколько точно вы следовали этапам продажи", value: 0, maxValue: 22.5, icon: FileText },
  { key: "score_objection_handling", label: "Обработка возражений", shortLabel: "L2 Возражения", description: "Качество работы с возражениями клиента", value: 0, maxValue: 18.75, icon: Shield },
  { key: "score_communication", label: "Коммуникация", shortLabel: "L3 Коммуникация", description: "Тон, эмпатия и стиль общения", value: 0, maxValue: 15, icon: MessageSquare },
  { key: "score_anti_patterns", label: "Антипаттерны (штраф)", shortLabel: "L4 Антипаттерны", description: "Штрафы за перебивание, давление, грубость", value: 0, maxValue: 11.25, isModifier: true, icon: AlertOctagon },
  { key: "score_result", label: "Результат", shortLabel: "L5 Результат", description: "Удалось ли достичь цели звонка", value: 0, maxValue: 7.5, icon: Target },
  { key: "score_chain_traversal", label: "Цепочки возражений", shortLabel: "L6 Цепочки", description: "Глубина проработки серии возражений", value: 0, maxValue: 7.5, icon: Link2 },
  { key: "score_trap_handling", label: "Ловушки", shortLabel: "L7 Ловушки", description: "Как вы справились с ловушками клиента", value: 0, maxValue: 7.5, isModifier: true, icon: Crosshair },
  { key: "score_human_factor", label: "Человеческий фактор", shortLabel: "L8 Человечность", description: "Учёт эмоций, усталости и давления", value: 0, maxValue: 15, isModifier: true, icon: Heart },
  { key: "score_narrative", label: "Нарративная прогрессия", shortLabel: "L9 Нарратив", description: "Развитие истории между звонками", value: 0, maxValue: 10, isModifier: true, icon: BookOpen },
  { key: "score_legal", label: "Юридическая точность", shortLabel: "L10 Юр.точность", description: "Корректность ссылок на 127-ФЗ", value: 0, maxValue: 5, isModifier: true, icon: Scale },
];

function getBarColor(pct: number, isModifier: boolean): string {
  if (isModifier) return "var(--accent, #6366f1)";
  if (pct >= 80) return "var(--success)";
  if (pct >= 60) return "var(--warning, #FFD700)";
  if (pct >= 40) return "var(--danger)";
  return "var(--danger)";
}

function getGradeLabel(pct: number): { label: string; color: string } {
  if (pct >= 90) return { label: "Отлично", color: "var(--success)" };
  if (pct >= 70) return { label: "Хорошо", color: "#22c55e" };
  if (pct >= 50) return { label: "Средне", color: "var(--warning, #FFD700)" };
  if (pct >= 25) return { label: "Слабо", color: "#F59E0B" };
  return { label: "Критично", color: "var(--danger)" };
}

interface Props {
  scoreBreakdown: Record<string, number>;
  totalScore: number;
  layerExplanations?: LayerExplanation[];
}

export default function ScoreLayersBreakdown({ scoreBreakdown, totalScore, layerExplanations }: Props) {
  const [expanded, setExpanded] = useState<string | null>(null);

  // Build explanation lookup
  const explanationMap: Record<string, LayerExplanation> = {};
  if (layerExplanations) {
    for (const ex of layerExplanations) {
      explanationMap[ex.layer] = ex;
    }
  }

  // Calculate grade
  const totalGrade = getGradeLabel(totalScore);

  return (
    <div className="cyber-card rounded-2xl p-5 md:p-6 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-base font-display font-bold tracking-wide" style={{ color: "var(--text-primary)" }}>
            Детальный скоринг
          </h3>
          <p className="mt-0.5 text-sm" style={{ color: "var(--text-muted)" }}>
            10 уровней анализа вашей сессии
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm font-medium" style={{ color: totalGrade.color }}>
            {totalGrade.label}
          </span>
          <div className="flex items-center gap-1 rounded-xl px-3 py-1.5" style={{ background: "rgba(99,102,241,0.1)", border: "1px solid rgba(99,102,241,0.2)" }}>
            <span className="text-lg font-bold font-mono" style={{ color: "var(--accent)" }}>{Math.round(totalScore)}</span>
            <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>/100</span>
          </div>
        </div>
      </div>

      {/* Score Layers */}
      <div className="space-y-2">
        {LAYER_DEFS.map((layer, i) => {
          const raw = scoreBreakdown[layer.key] ?? 0;
          const value = layer.isModifier ? raw : Math.round(raw);
          const pct = layer.isModifier
            ? Math.max(0, Math.min(100, ((raw + (layer.key === "score_legal" ? 5 : 0)) / (layer.maxValue * 2)) * 100))
            : Math.max(0, Math.min(100, (raw / layer.maxValue) * 100));

          const layerKey = `L${i + 1}`;
          const explanation = explanationMap[layerKey];
          const isExpanded = expanded === layerKey;
          const hasExplanation = explanation && (explanation.summary || explanation.highlights.length > 0);
          const barColor = getBarColor(pct, !!layer.isModifier);
          const Icon = layer.icon;

          return (
            <motion.div
              key={layer.key}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.04 }}
              className="rounded-xl overflow-hidden"
              style={{ background: isExpanded ? "rgba(99,102,241,0.04)" : "transparent" }}
            >
              <button
                type="button"
                className="w-full text-left px-3 py-2.5 rounded-xl transition-colors hover:bg-white/[0.03]"
                onClick={() => hasExplanation ? setExpanded(isExpanded ? null : layerKey) : undefined}
                style={{ cursor: hasExplanation ? "pointer" : "default" }}
              >
                <div className="flex items-center gap-3 mb-1.5">
                  <div className="flex items-center justify-center w-7 h-7 rounded-lg shrink-0" style={{ background: colorAlpha(barColor, 8), border: `1px solid ${colorAlpha(barColor, 18)}` }}>
                    <Icon size={14} style={{ color: barColor }} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-medium flex items-center gap-1.5" style={{ color: "var(--text-primary)" }}>
                        {layer.shortLabel}
                        {hasExplanation && (
                          <ChevronDown
                            size={12}
                            className="transition-transform"
                            style={{
                              transform: isExpanded ? "rotate(180deg)" : "rotate(0deg)",
                              color: "var(--text-muted)",
                            }}
                          />
                        )}
                      </span>
                      <span className="text-sm font-mono font-semibold shrink-0" style={{ color: barColor }}>
                        {layer.isModifier ? (
                          <span>
                            {value >= 0 ? "+" : ""}{typeof value === "number" ? value.toFixed(1) : value}
                          </span>
                        ) : (
                          <span>
                            {value}<span className="text-xs font-normal" style={{ color: "var(--text-muted)" }}>/{layer.maxValue}</span>
                          </span>
                        )}
                      </span>
                    </div>
                    <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>{layer.description}</p>
                  </div>
                </div>
                <div className="ml-10 h-2 rounded-full" style={{ background: "var(--input-bg)" }}>
                  <motion.div
                    className="h-full rounded-full"
                    initial={{ width: 0 }}
                    animate={{ width: `${pct}%` }}
                    transition={{ duration: 0.6, delay: i * 0.05 }}
                    style={{
                      background: barColor,
                      boxShadow: `0 0 6px ${colorAlpha(barColor, 25)}`,
                    }}
                  />
                </div>
              </button>

              {/* Expandable explanation */}
              <AnimatePresence>
                {isExpanded && explanation && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.25 }}
                    className="overflow-hidden"
                  >
                    <div
                      className="mx-3 mb-3 rounded-xl px-4 py-3 space-y-2.5"
                      style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)" }}
                    >
                      {/* Summary */}
                      <p className="text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                        {explanation.summary}
                      </p>

                      {/* Highlights — specific message references */}
                      {explanation.highlights.length > 0 && (
                        <div className="space-y-1.5">
                          <span className="text-xs font-mono uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                            Ключевые моменты
                          </span>
                          {explanation.highlights.map((h, hi) => (
                            <div
                              key={hi}
                              className="flex items-start gap-2.5 rounded-lg px-3 py-2"
                              style={{
                                background: h.delta < 0 ? "rgba(255,42,109,0.06)" : h.delta > 0 ? "rgba(0,255,148,0.06)" : "rgba(255,255,255,0.02)",
                                borderLeft: h.delta !== 0
                                  ? `3px solid ${h.delta < 0 ? "var(--danger)" : "var(--success)"}`
                                  : "3px solid var(--border-color)",
                              }}
                            >
                              <MessageCircle size={12} className="mt-0.5 shrink-0" style={{ color: "var(--text-muted)" }} />
                              <div className="min-w-0 flex-1">
                                <p className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                                  {h.message_index >= 0 ? `#${h.message_index + 1} ${h.role === "user" ? "Менеджер" : "Клиент"}` : ""}
                                </p>
                                {h.excerpt && (
                                  <p className="text-sm mt-0.5 italic" style={{ color: "var(--text-secondary)" }}>
                                    &ldquo;{h.excerpt}&rdquo;
                                  </p>
                                )}
                                <p className="text-sm mt-1" style={{ color: h.delta < 0 ? "var(--danger)" : h.delta > 0 ? "var(--success)" : "var(--text-secondary)" }}>
                                  {h.impact}
                                  {h.delta !== 0 && (
                                    <span className="ml-2 font-mono font-bold">
                                      {h.delta > 0 ? "+" : ""}{h.delta.toFixed(1)}
                                    </span>
                                  )}
                                </p>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          );
        })}
      </div>

      {/* Legend */}
      <div className="pt-3 border-t" style={{ borderColor: "var(--border-color)" }}>
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          <span className="text-xs" style={{ color: "var(--text-muted)" }}>
            <span className="font-semibold" style={{ color: "var(--text-secondary)" }}>L1–L7</span> базовые (75 pts)
          </span>
          <span className="text-xs" style={{ color: "var(--text-muted)" }}>
            <span className="font-semibold" style={{ color: "var(--text-secondary)" }}>L8</span> человечность (+15)
          </span>
          <span className="text-xs" style={{ color: "var(--text-muted)" }}>
            <span className="font-semibold" style={{ color: "var(--text-secondary)" }}>L9</span> нарратив (+10)
          </span>
          <span className="text-xs" style={{ color: "var(--text-muted)" }}>
            <span className="font-semibold" style={{ color: "var(--text-secondary)" }}>L10</span> юр.точность ({"\u00B1"}5)
          </span>
        </div>
        {layerExplanations && (
          <p className="mt-1.5 text-xs" style={{ color: "var(--accent)" }}>
            Нажмите на любой слой для подробного анализа с цитатами из диалога
          </p>
        )}
      </div>
    </div>
  );
}
