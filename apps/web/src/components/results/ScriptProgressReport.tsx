"use client";

import { useState, type ReactNode } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { BookOpen, ChevronDown } from "lucide-react";
import { STAGE_GUIDANCE, type StageGuidance } from "@/lib/script_guidance";

interface ScriptProgressReportProps {
  stageProgress: {
    stages_completed?: number[];
    stage_scores?: Record<string, number>;
    skipped_stages?: number[];
    stage_durations_sec?: Record<string, number>;
    stage_message_counts?: Record<string, number>;
    final_stage?: number;
    total_stages?: number;
    call_outcome?: string;
  };
}

type StageStatus = "done" | "skipped" | "unreached";

interface StageRow {
  n: number;
  label: string;
  status: StageStatus;
  score: number | null;
  durationSec: number;
  advice: { text: string; color: string; tooltip?: string };
}

function formatDuration(seconds: number | undefined): string {
  if (!seconds || seconds <= 0) return "—";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function scoreColor(pct: number): string {
  if (pct >= 80) return "var(--success)";
  if (pct >= 60) return "var(--gf-xp)";
  return "var(--danger)";
}

const STATUS_META: Record<StageStatus, { char: string; color: string; title: string }> = {
  done: { char: "✓", color: "var(--success)", title: "Завершено" },
  skipped: { char: "✗", color: "var(--gf-xp)", title: "Пропущено" },
  unreached: { char: "❌", color: "var(--danger)", title: "Не дошёл" },
};

const GRID = "grid grid-cols-[1.6fr_auto_auto_auto_1.4fr_auto] gap-3";

function buildRow(
  n: number,
  guidance: StageGuidance | undefined,
  completed: Set<number>,
  skipped: Set<number>,
  effectiveFinal: number,
  scores: Record<string, number>,
  durations: Record<string, number>,
): StageRow {
  let status: StageStatus;
  if (skipped.has(n)) status = "skipped";
  else if (completed.has(n)) status = "done";
  else if (n > effectiveFinal) status = "unreached";
  else status = "skipped"; // advanced past but not matched

  const rawScore = scores[String(n)];
  const score = status === "done" && typeof rawScore === "number" ? rawScore : null;
  const durationSec = durations[String(n)] ?? 0;

  let advice: StageRow["advice"];
  if (status === "done" && score !== null && score >= 0.7) {
    const bonus = Math.min(10, Math.max(0, Math.round((score - 0.7) * 10)));
    advice = { text: `💡+${bonus}`, color: "var(--success)" };
  } else if (status === "done" && score !== null && score < 0.7) {
    const mistake = guidance?.common_mistakes?.[0] ?? "Низкое качество прохождения этапа";
    advice = { text: `⚠️ ${mistake}`, color: "var(--gf-xp)" };
  } else {
    const tooltip = status === "skipped" ? "Этап пропущен" : "До этого этапа не дошли";
    advice = { text: "⛔", color: "var(--danger)", tooltip };
  }

  return {
    n,
    label: guidance?.label_ru ?? `Этап ${n}`,
    status,
    score,
    durationSec,
    advice,
  };
}

const CAPTION = "font-mono text-[10px] uppercase tracking-widest mb-1";

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <div className={CAPTION} style={{ color: "var(--text-muted)" }}>
        {title}
      </div>
      {children}
    </div>
  );
}

function ExpandedPanel({ guidance }: { guidance: StageGuidance }) {
  return (
    <motion.div
      initial={{ height: 0, opacity: 0 }}
      animate={{ height: "auto", opacity: 1 }}
      exit={{ height: 0, opacity: 0 }}
      transition={{ duration: 0.22 }}
      style={{ overflow: "hidden" }}
    >
      <div
        className="px-4 py-4 text-sm space-y-3 border-b"
        style={{
          background: "rgba(255,255,255,0.02)",
          borderColor: "var(--border-color)",
          color: "var(--text-secondary)",
        }}
      >
        <Section title="Задача этапа">
          <p style={{ color: "var(--text-primary)" }}>{guidance.task_ru}</p>
        </Section>
        {guidance.signals_done.length > 0 && (
          <Section title="Сигналы готовности">
            <ul className="list-disc pl-5 space-y-0.5">
              {guidance.signals_done.map((s, i) => <li key={i}>{s}</li>)}
            </ul>
          </Section>
        )}
        {guidance.common_mistakes.length > 0 && (
          <Section title="Частые ошибки">
            <ul className="list-disc pl-5 space-y-0.5">
              {guidance.common_mistakes.map((m, i) => <li key={i}>{m}</li>)}
            </ul>
          </Section>
        )}
      </div>
    </motion.div>
  );
}

export default function ScriptProgressReport({ stageProgress }: ScriptProgressReportProps) {
  const [expanded, setExpanded] = useState<number | null>(null);

  const completedArr = stageProgress.stages_completed ?? [];
  const finalStage = stageProgress.final_stage;

  // Early return for legacy sessions
  if (completedArr.length === 0 && finalStage === undefined) return null;

  const total = stageProgress.total_stages ?? 7;
  const skipped = new Set(stageProgress.skipped_stages ?? []);
  const completed = new Set(completedArr);
  const scores = stageProgress.stage_scores ?? {};
  const durations = stageProgress.stage_durations_sec ?? {};
  const effectiveFinal =
    finalStage ?? (completedArr.length > 0 ? Math.max(...completedArr) : 0);

  const rows: StageRow[] = Array.from({ length: total }, (_, i) => i + 1).map((n) =>
    buildRow(n, STAGE_GUIDANCE[n - 1], completed, skipped, effectiveFinal, scores, durations),
  );
  const completedCount = rows.filter((r) => r.status === "done").length;

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-panel rounded-2xl p-6 md:p-8"
    >
      <h2
        className="font-display text-lg tracking-widest flex items-center gap-2 border-b pb-3 mb-4"
        style={{ color: "var(--text-primary)", borderColor: "var(--border-color)" }}
      >
        <BookOpen size={18} style={{ color: "var(--accent)" }} />
        ПРОГРЕСС ПО СКРИПТУ
      </h2>

      <div className="mb-4 text-sm font-mono" style={{ color: "var(--text-secondary)" }}>
        Завершено: <strong style={{ color: "var(--text-primary)" }}>{completedCount} / {total}</strong> этапов
      </div>

      {/* Header row */}
      <div
        className={`${GRID} px-3 py-2 text-[11px] font-mono uppercase tracking-widest border-b`}
        style={{ color: "var(--text-muted)", borderColor: "var(--border-color)" }}
      >
        <div>Этап</div>
        <div className="text-center w-10">Статус</div>
        <div className="text-right w-14">Качество</div>
        <div className="text-right w-12">Время</div>
        <div>Совет</div>
        <div className="w-4" />
      </div>

      {/* Rows */}
      {rows.map((row) => {
        const isOpen = expanded === row.n;
        const g = STATUS_META[row.status];
        const guidance = STAGE_GUIDANCE[row.n - 1];
        const scorePct = row.score !== null ? Math.round(row.score * 100) : null;
        const labelColor = row.status === "done" ? "var(--text-primary)" : "var(--text-secondary)";
        const scoreCol = scorePct !== null ? scoreColor(scorePct) : "var(--text-muted)";

        return (
          <div key={row.n}>
            <motion.button
              type="button"
              onClick={() => setExpanded(isOpen ? null : row.n)}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: row.n * 0.04 }}
              className={`${GRID} w-full px-3 py-3 text-sm text-left border-b hover:bg-white/[0.02] transition-colors`}
              style={{ borderColor: "var(--border-color)" }}
              aria-expanded={isOpen}
            >
              <div className="font-medium truncate" style={{ color: labelColor }}>
                <span className="font-mono text-xs mr-2" style={{ color: "var(--text-muted)" }}>
                  {row.n}.
                </span>
                {row.label}
              </div>
              <div className="text-center w-10 font-mono" style={{ color: g.color }} title={g.title}>
                {g.char}
              </div>
              <div className="text-right w-14 font-mono" style={{ color: scoreCol }}>
                {scorePct !== null ? `${scorePct}%` : "—"}
              </div>
              <div className="text-right w-12 font-mono" style={{ color: "var(--text-muted)" }}>
                {formatDuration(row.durationSec)}
              </div>
              <div
                className="text-xs truncate"
                style={{ color: row.advice.color }}
                title={row.advice.tooltip ?? row.advice.text}
              >
                {row.advice.text}
              </div>
              <div className="flex items-center justify-center w-4" style={{ color: "var(--text-muted)" }}>
                <motion.span
                  animate={{ rotate: isOpen ? 180 : 0 }}
                  transition={{ duration: 0.2 }}
                  style={{ display: "inline-flex" }}
                >
                  <ChevronDown size={14} />
                </motion.span>
              </div>
            </motion.button>

            <AnimatePresence initial={false}>
              {isOpen && guidance && <ExpandedPanel guidance={guidance} />}
            </AnimatePresence>
          </div>
        );
      })}

      {/* Legend */}
      <div
        className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs font-mono"
        style={{ color: "var(--text-muted)" }}
      >
        <span>
          <span style={{ color: "var(--success)" }}>✓</span> завершено
        </span>
        <span>
          <span style={{ color: "var(--gf-xp)" }}>✗</span> пропущено
        </span>
        <span>
          <span style={{ color: "var(--danger)" }}>❌</span> не дошёл
        </span>
      </div>
    </motion.div>
  );
}
