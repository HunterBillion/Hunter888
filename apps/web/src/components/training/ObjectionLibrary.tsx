"use client";

/**
 * Objection Library — visual tree of objection handling chains.
 * Each node = client objection, branches = good/bad responses.
 * Links to wiki pages with best practices.
 */

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  MessageSquare,
  ChevronRight,
  ChevronDown,
  CheckCircle2,
  XCircle,
  BookOpen,
} from "lucide-react";

interface ObjectionStep {
  order: number;
  objection_text: string;
  recommended_responses: string[];
  on_good_response: number | string;
  on_bad_response: number | string;
}

interface ObjectionChain {
  id: string;
  name: string;
  difficulty: number;
  steps: ObjectionStep[];
  archetypes: string[];
}

interface ObjectionLibraryProps {
  chains: ObjectionChain[];
  onViewWiki?: (chainId: string, stepOrder: number) => void;
}

export default function ObjectionLibrary({ chains, onViewWiki }: ObjectionLibraryProps) {
  const [expandedChain, setExpandedChain] = useState<string | null>(null);
  const [expandedStep, setExpandedStep] = useState<number | null>(null);

  if (chains.length === 0) {
    return (
      <div className="rounded-xl bg-[var(--bg-secondary)] p-8 text-center">
        <MessageSquare size={40} className="mx-auto mb-3 text-[var(--text-muted)] opacity-30" />
        <p className="text-sm text-[var(--text-muted)]">Библиотека возражений пока пуста</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {chains.map((chain) => {
        const isExpanded = expandedChain === chain.id;
        return (
          <div key={chain.id} className="rounded-xl bg-[var(--bg-secondary)] overflow-hidden">
            {/* Chain header */}
            <button
              onClick={() => {
                setExpandedChain(isExpanded ? null : chain.id);
                setExpandedStep(null);
              }}
              className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-[var(--bg-tertiary)] transition-colors"
            >
              {isExpanded ? (
                <ChevronDown size={16} className="shrink-0 text-[var(--accent)]" />
              ) : (
                <ChevronRight size={16} className="shrink-0 text-[var(--text-muted)]" />
              )}
              <div className="flex-1">
                <p className="text-sm font-medium text-[var(--text-primary)]">{chain.name}</p>
                <p className="text-xs text-[var(--text-muted)]">
                  {chain.steps.length} шагов | Сложность {chain.difficulty}/10
                  {chain.archetypes.length > 0 && ` | ${chain.archetypes.join(", ")}`}
                </p>
              </div>
            </button>

            {/* Steps */}
            <AnimatePresence>
              {isExpanded && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  className="border-t border-[var(--border)]"
                >
                  <div className="p-4 space-y-2">
                    {chain.steps.map((step) => {
                      const isStepExpanded = expandedStep === step.order;
                      return (
                        <div key={step.order} className="rounded-lg bg-[var(--bg-tertiary)] overflow-hidden">
                          {/* Step header */}
                          <button
                            onClick={() => setExpandedStep(isStepExpanded ? null : step.order)}
                            className="flex w-full items-center gap-2 px-3 py-2 text-left"
                          >
                            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--accent)]/20 text-xs font-bold text-[var(--accent)]">
                              {step.order}
                            </span>
                            <p className="flex-1 text-sm text-[var(--text-primary)]">
                              {step.objection_text}
                            </p>
                            {isStepExpanded ? (
                              <ChevronDown size={14} className="text-[var(--text-muted)]" />
                            ) : (
                              <ChevronRight size={14} className="text-[var(--text-muted)]" />
                            )}
                          </button>

                          {/* Step details */}
                          <AnimatePresence>
                            {isStepExpanded && (
                              <motion.div
                                initial={{ height: 0 }}
                                animate={{ height: "auto" }}
                                exit={{ height: 0 }}
                                className="border-t border-[var(--border)] px-3 py-3 space-y-3"
                              >
                                {/* Recommended responses */}
                                <div>
                                  <p className="mb-1.5 text-xs font-medium text-[var(--text-muted)]">Рекомендуемые ответы:</p>
                                  {step.recommended_responses.map((resp, i) => (
                                    <div key={i} className="flex items-start gap-2 mb-1">
                                      <CheckCircle2 size={12} className="mt-0.5 shrink-0 text-[var(--success)]" />
                                      <p className="text-xs text-[var(--text-secondary)]">{resp}</p>
                                    </div>
                                  ))}
                                </div>

                                {/* Branching */}
                                <div className="flex gap-4 text-xs">
                                  <div className="flex items-center gap-1 text-[var(--success)]">
                                    <CheckCircle2 size={12} />
                                    <span>
                                      Хороший ответ → {typeof step.on_good_response === "number" ? `Шаг ${step.on_good_response}` : step.on_good_response}
                                    </span>
                                  </div>
                                  <div className="flex items-center gap-1 text-[var(--danger)]">
                                    <XCircle size={12} />
                                    <span>
                                      Плохой ответ → {typeof step.on_bad_response === "number" ? `Шаг ${step.on_bad_response}` : step.on_bad_response}
                                    </span>
                                  </div>
                                </div>

                                {/* Wiki link */}
                                {onViewWiki && (
                                  <button
                                    onClick={() => onViewWiki(chain.id, step.order)}
                                    className="flex items-center gap-1.5 text-xs text-[var(--accent)] hover:underline"
                                  >
                                    <BookOpen size={12} />
                                    Подробнее в базе знаний
                                  </button>
                                )}
                              </motion.div>
                            )}
                          </AnimatePresence>
                        </div>
                      );
                    })}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        );
      })}
    </div>
  );
}
