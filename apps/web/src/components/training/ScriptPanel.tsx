"use client";

/**
 * ScriptPanel — Sprint 3 / Zone 3 of plan moonlit-baking-crane.md
 *
 * Объединяет старый StageProgressBar (7 точек прогресса) с обучающим
 * контентом для текущего этапа: задача, примеры фраз, типичные ошибки,
 * длительность. Юзер-учащийся видит «что сейчас делать» постоянно.
 *
 * Layout:
 *   ┌────────────────────────────────┐
 *   │ 🎯 Этап 2/7 · КОНТАКТ      [▼] │  ← header (always)
 *   │ ◉─●─○─○─○─○─○                  │
 *   │ ✓1 ●2 ○3 ○4 ○5 ○6 ○7           │
 *   ├────────────────────────────────┤  ← expanded body
 *   │ 📋 Задача:                     │
 *   │ Установите раппорт...           │
 *   │                                 │
 *   │ 💬 Примеры (клик = копировать): │
 *   │ • «Как к вам обращаться?...» 📋│
 *   │ • «Понимаю, ситуация...» 📋    │
 *   │                                 │
 *   │ ⚠ Типичные ошибки:              │
 *   │ • Сразу спросили «Сколько...» │
 *   │                                 │
 *   │ ⏱ Обычно: 3–6 сообщений         │
 *   ├────────────────────────────────┤
 *   │ ⚠ Пропущен: Контакт            │  ← skip alert (when active)
 *   │ Вернитесь к рапorту            │
 *   └────────────────────────────────┘
 *
 * Replaces:
 *   - apps/web/src/components/training/StageProgress.tsx (deprecated)
 *
 * On mobile (sm-): the body collapses by default; tap header to expand.
 * The component is layout-agnostic — caller wraps it in their preferred
 * panel (sidebar card in chat, narrow column in call).
 */

import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Check,
  ChevronDown,
  ChevronUp,
  Copy,
  Target,
  AlertTriangle,
  Clock3,
} from "lucide-react";
import { useSessionStore } from "@/stores/useSessionStore";
import { guidanceFor, type StageGuidance } from "@/lib/script_guidance";
import { telemetry } from "@/lib/telemetry";

interface ScriptPanelProps {
  /** Hides the small «Этапы скрипта» header above the dots. Use when
   *  embedded in a parent that already labels the section. */
  compactHeader?: boolean;
  /** When true, the body is closed by default (header + dots only).
   *  Defaults to false on desktop, true on mobile (caller decides). */
  defaultCollapsed?: boolean;
  /** Optional callback when user clicks an example — useful for caller
   *  to write into the message input. If omitted, fallback is clipboard. */
  onCopyExample?: (text: string) => void;
}

export default function ScriptPanel({
  compactHeader = false,
  defaultCollapsed = false,
  onCopyExample,
}: ScriptPanelProps) {
  const currentStage = useSessionStore((s) => s.currentStage);
  const stagesCompleted = useSessionStore((s) => s.stagesCompleted);
  const totalStages = useSessionStore((s) => s.totalStages);
  const stageLabel = useSessionStore((s) => s.stageLabel);
  const skippedHint = useSessionStore((s) => s.skippedHint);
  const clearSkippedHint = useSessionStore((s) => s.clearSkippedHint);

  const [expanded, setExpanded] = useState(!defaultCollapsed);
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null);

  const stages = useMemo(
    () => Array.from({ length: totalStages }, (_, i) => i + 1),
    [totalStages],
  );
  const completedSet = useMemo(() => new Set(stagesCompleted), [stagesCompleted]);
  const guidance: StageGuidance | null = useMemo(
    () => guidanceFor(currentStage),
    [currentStage],
  );
  const progressPct = useMemo(
    () => (stagesCompleted.length / Math.max(1, totalStages)) * 100,
    [stagesCompleted.length, totalStages],
  );

  // 2026-04-23: auto-clear skip alert after 12s so it doesn't linger
  // forever after the user has noticeably moved past the issue.
  useEffect(() => {
    if (!skippedHint) return;
    const t = window.setTimeout(() => {
      clearSkippedHint();
    }, 12_000);
    return () => window.clearTimeout(t);
  }, [skippedHint, clearSkippedHint]);

  const handleCopy = (text: string, idx: number) => {
    if (onCopyExample) {
      onCopyExample(text);
    } else if (typeof navigator !== "undefined" && navigator.clipboard) {
      navigator.clipboard.writeText(text).catch(() => {/* non-fatal */});
    }
    setCopiedIdx(idx);
    telemetry.track("script_example_copied", {
      stage: currentStage,
      example_idx: idx,
    });
    window.setTimeout(() => setCopiedIdx((p) => (p === idx ? null : p)), 1400);
  };

  const handleToggle = () => {
    setExpanded((v) => {
      telemetry.track("script_panel_toggle", {
        stage: currentStage,
        open: !v,
      });
      return !v;
    });
  };

  return (
    <div className="flex flex-col">
      {!compactHeader && (
        <div
          className="text-sm font-semibold mb-2"
          style={{ color: "var(--text-secondary)" }}
        >
          Этапы скрипта
        </div>
      )}

      {/* Progress bar */}
      <div
        className="h-1 rounded-full overflow-hidden mb-2"
        style={{ background: "var(--input-bg)" }}
      >
        <motion.div
          className="h-full rounded-full"
          style={{
            background: "linear-gradient(90deg, var(--success), var(--accent))",
            boxShadow: "0 0 6px rgba(61,220,132,0.3)",
          }}
          animate={{ width: `${progressPct}%` }}
          transition={{ duration: 0.6, ease: "easeOut" }}
        />
      </div>

      {/* Header — clickable to toggle body */}
      <button
        type="button"
        onClick={handleToggle}
        className="flex items-center justify-between gap-2 -mx-1 px-1 py-1 rounded transition-colors hover:bg-white/5"
        aria-expanded={expanded}
      >
        <div className="flex items-center gap-2">
          <Target
            size={14}
            style={{ color: "var(--accent)" }}
            aria-hidden
          />
          <span
            className="text-xs font-semibold uppercase tracking-wider"
            style={{ color: "var(--text-primary)" }}
          >
            Этап {currentStage}/{totalStages}
            <span className="opacity-60"> · </span>
            <span style={{ color: "var(--text-secondary)" }}>
              {(guidance?.label_ru || stageLabel || "—").toUpperCase()}
            </span>
          </span>
        </div>
        {expanded ? (
          <ChevronUp size={14} style={{ color: "var(--text-muted)" }} />
        ) : (
          <ChevronDown size={14} style={{ color: "var(--text-muted)" }} />
        )}
      </button>

      {/* Stage dots */}
      <div className="flex items-center mt-2 mb-1">
        {stages.map((num, idx) => {
          const isCompleted = completedSet.has(num);
          const isCurrent = num === currentStage && !isCompleted;
          const prevCompleted = idx > 0 && completedSet.has(stages[idx - 1]);

          return (
            <div key={num} className="contents">
              {idx > 0 && (
                <div
                  className="flex-1 h-px"
                  style={{
                    background: prevCompleted
                      ? "var(--success, #00FF94)"
                      : "var(--border-color)",
                  }}
                />
              )}
              <AnimatePresence mode="wait">
                {isCompleted ? (
                  <motion.div
                    key={`done-${num}`}
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    transition={{ type: "spring", stiffness: 500, damping: 20 }}
                    className="flex items-center justify-center w-5 h-5 rounded-full"
                    style={{
                      background: "var(--success-muted)",
                      border: "1.5px solid var(--success, #00FF94)",
                    }}
                    aria-label={`Этап ${num} пройден`}
                  >
                    <Check size={10} strokeWidth={3} style={{ color: "#fff" }} />
                  </motion.div>
                ) : isCurrent ? (
                  <motion.div
                    key={`cur-${num}`}
                    animate={{
                      boxShadow: [
                        "0 0 0px rgba(107,77,199,0.3)",
                        "0 0 10px rgba(107,77,199,0.6)",
                        "0 0 0px rgba(107,77,199,0.3)",
                      ],
                    }}
                    transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
                    className="flex items-center justify-center w-5 h-5 rounded-full"
                    style={{
                      background: "var(--accent-muted)",
                      border: "1.5px solid var(--accent)",
                    }}
                    aria-label={`Этап ${num} текущий`}
                  >
                    <span
                      className="text-[10px] font-bold"
                      style={{ color: "var(--accent)" }}
                    >
                      {num}
                    </span>
                  </motion.div>
                ) : (
                  <motion.div
                    key={`pen-${num}`}
                    className="flex items-center justify-center w-5 h-5 rounded-full"
                    style={{
                      background: "transparent",
                      border: "1.5px solid var(--border-color)",
                    }}
                    aria-label={`Этап ${num} не начат`}
                  >
                    <span
                      className="text-[10px] font-bold"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {num}
                    </span>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          );
        })}
      </div>

      {/* Expanded body */}
      <AnimatePresence initial={false}>
        {expanded && guidance && (
          <motion.div
            key="body"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22, ease: "easeOut" }}
            className="overflow-hidden"
          >
            <div className="mt-3 space-y-3 text-xs leading-relaxed">
              {/* Task */}
              <div>
                <div
                  className="text-[10px] font-bold uppercase tracking-wider mb-1"
                  style={{ color: "var(--accent)" }}
                >
                  📋 Задача
                </div>
                <div style={{ color: "var(--text-primary)" }}>
                  {guidance.task_ru}
                </div>
              </div>

              {/* Examples */}
              {guidance.examples.length > 0 && (
                <div>
                  <div
                    className="text-[10px] font-bold uppercase tracking-wider mb-1"
                    style={{ color: "var(--accent)" }}
                  >
                    💬 Примеры фраз
                    <span
                      className="ml-1.5 normal-case font-normal opacity-60"
                      style={{ letterSpacing: 0 }}
                    >
                      (тап = вставить)
                    </span>
                  </div>
                  <ul className="space-y-1.5">
                    {guidance.examples.map((ex, i) => (
                      <li key={i}>
                        <button
                          type="button"
                          onClick={() => handleCopy(ex.text, i)}
                          className="w-full text-left flex items-start gap-2 rounded-md px-2 py-1.5 transition-colors hover:bg-white/5"
                          aria-label={`Скопировать пример ${i + 1}`}
                        >
                          <span
                            className="flex-1"
                            style={{ color: "var(--text-secondary)" }}
                          >
                            «{ex.text}»
                            {ex.label && (
                              <span
                                className="ml-1.5 text-[9px] font-semibold uppercase opacity-50"
                                style={{ letterSpacing: "0.05em" }}
                              >
                                {ex.label}
                              </span>
                            )}
                          </span>
                          <span
                            className="shrink-0 text-[10px] font-medium uppercase"
                            style={{
                              color: copiedIdx === i ? "var(--success)" : "var(--text-muted)",
                            }}
                          >
                            {copiedIdx === i ? (
                              <span className="inline-flex items-center gap-0.5">
                                <Check size={10} /> ОК
                              </span>
                            ) : (
                              <Copy size={10} aria-hidden />
                            )}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Common mistakes */}
              {guidance.common_mistakes.length > 0 && (
                <div>
                  <div
                    className="text-[10px] font-bold uppercase tracking-wider mb-1"
                    style={{ color: "var(--warning, #f59e0b)" }}
                  >
                    ⚠ Типичные ошибки
                  </div>
                  <ul
                    className="space-y-1 list-disc pl-4"
                    style={{ color: "var(--text-muted)" }}
                  >
                    {guidance.common_mistakes.map((m, i) => (
                      <li key={i}>{m}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Footer — duration */}
              <div
                className="flex items-center gap-1.5 pt-1 text-[11px]"
                style={{ color: "var(--text-muted)" }}
              >
                <Clock3 size={11} aria-hidden />
                Обычно занимает {guidance.typical_duration_messages} сообщ.
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Skip alert — yellow flash border + hint */}
      <AnimatePresence>
        {skippedHint && (
          <motion.div
            key="skip"
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.25 }}
            className="mt-3 rounded-lg p-2.5 text-xs"
            style={{
              background: "rgba(234,179,8,0.08)",
              border: "1px solid rgba(234,179,8,0.4)",
              color: "var(--text-primary)",
            }}
            role="alert"
          >
            <div className="flex items-start gap-2">
              <AlertTriangle
                size={14}
                style={{ color: "#EAB308", flexShrink: 0, marginTop: 1 }}
                aria-hidden
              />
              <div className="flex-1">
                <div className="font-semibold">
                  Пропущен: «{skippedHint.missedStageLabel}»
                </div>
                <div
                  className="mt-0.5"
                  style={{ color: "var(--text-secondary)" }}
                >
                  {skippedHint.hint}
                </div>
              </div>
              <button
                type="button"
                onClick={clearSkippedHint}
                aria-label="Скрыть"
                className="text-[10px] uppercase font-medium px-1 py-0.5 rounded hover:bg-white/5"
                style={{ color: "var(--text-muted)" }}
              >
                ✕
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
