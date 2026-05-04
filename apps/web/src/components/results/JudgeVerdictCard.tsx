"use client";

import { motion } from "framer-motion";
import { Gavel } from "lucide-react";
import type { JudgeVerdictData } from "@/types";

interface JudgeVerdictCardProps {
  judge: JudgeVerdictData;
}

interface VerdictMeta {
  emoji: string;
  label: string;
  color: string;
  bg: string;
  border: string;
}

function getVerdictMeta(verdict: JudgeVerdictData["verdict"]): VerdictMeta {
  switch (verdict) {
    case "excellent":
      return {
        emoji: "🟢",
        label: "Отличный звонок",
        color: "var(--success)",
        bg: "rgba(61,220,132,0.12)",
        border: "rgba(61,220,132,0.45)",
      };
    case "good":
      return {
        emoji: "🟢",
        label: "Хороший звонок",
        color: "var(--success)",
        bg: "rgba(61,220,132,0.10)",
        border: "rgba(61,220,132,0.35)",
      };
    case "mixed":
      return {
        emoji: "🟡",
        label: "Смешанный результат",
        color: "var(--warning)",
        bg: "rgba(255,184,0,0.10)",
        border: "rgba(255,184,0,0.35)",
      };
    case "poor":
      return {
        emoji: "🔴",
        label: "Слабый звонок",
        color: "var(--danger)",
        bg: "rgba(239,68,68,0.10)",
        border: "rgba(239,68,68,0.35)",
      };
    case "red_flag":
      return {
        emoji: "⛔",
        label: "Критические ошибки",
        color: "var(--danger)",
        bg: "rgba(239,68,68,0.18)",
        border: "rgba(239,68,68,0.55)",
      };
    default:
      return {
        emoji: "⚪",
        label: String(verdict),
        color: "var(--text-secondary)",
        bg: "rgba(255,255,255,0.05)",
        border: "var(--border-color)",
      };
  }
}

function formatAdjust(n: number): string {
  if (n > 0) return `+${n}`;
  return String(n);
}

export default function JudgeVerdictCard({ judge }: JudgeVerdictCardProps) {
  const meta = getVerdictMeta(judge.verdict);
  const adjust = Number(judge.score_adjust ?? 0);
  const adjustColor = adjust >= 0 ? "var(--success)" : "var(--danger)";

  const strengths = Array.isArray(judge.strengths) ? judge.strengths : [];
  const redFlags = Array.isArray(judge.red_flags) ? judge.red_flags : [];

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.12 }}
      className="glass-panel rounded-2xl p-6 md:p-7 relative overflow-hidden"
    >
      <div
        className="absolute top-0 left-0 right-0 h-[2px]"
        style={{ background: `linear-gradient(90deg, transparent, ${meta.color}, transparent)` }}
      />

      <h2
        className="font-display text-lg tracking-widest flex items-center gap-2 border-b pb-3 mb-5"
        style={{ color: "var(--text-primary)", borderColor: "var(--border-color)" }}
      >
        <Gavel size={18} style={{ color: meta.color }} /> ВЕРДИКТ AI-СУДЬИ
      </h2>

      {/* Top row: verdict badge + score adjust */}
      <div className="flex flex-wrap items-center justify-between gap-4 mb-4">
        <div
          className="inline-flex items-center gap-2 rounded-xl px-4 py-2 font-display text-base md:text-lg tracking-wide"
          style={{ background: meta.bg, border: `1px solid ${meta.border}`, color: meta.color }}
        >
          <span aria-hidden>{meta.emoji}</span>
          <span>«{meta.label}»</span>
        </div>
        <div className="flex flex-col items-end">
          <span
            className="font-mono text-[11px] uppercase tracking-widest"
            style={{ color: "var(--text-muted)" }}
          >
            Корректировка
          </span>
          <span
            className="font-display text-3xl font-bold"
            style={{ color: adjustColor, textShadow: `0 0 10px ${adjustColor}` }}
          >
            {formatAdjust(adjust)}
          </span>
        </div>
      </div>

      {/* Rationale */}
      {judge.rationale_ru && (
        <p
          className="italic text-base md:text-lg leading-relaxed mb-6"
          style={{ color: "var(--text-secondary)" }}
        >
          {judge.rationale_ru}
        </p>
      )}

      {/* Two columns: strengths / red flags */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        <div>
          <div
            className="font-mono text-xs uppercase tracking-widest mb-2"
            style={{ color: "var(--success)" }}
          >
            Сильные стороны
          </div>
          {strengths.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {strengths.map((s, i) => (
                <span
                  key={`strength-${i}`}
                  className="inline-flex items-center rounded-full px-3 py-1 text-xs font-mono"
                  style={{
                    background: "rgba(61,220,132,0.10)",
                    border: "1px solid rgba(61,220,132,0.35)",
                    color: "var(--success)",
                  }}
                >
                  {s}
                </span>
              ))}
            </div>
          ) : (
            <span className="text-xs" style={{ color: "var(--text-muted)" }}>
              —
            </span>
          )}
        </div>

        <div>
          <div
            className="font-mono text-xs uppercase tracking-widest mb-2"
            style={{ color: "var(--danger)" }}
          >
            Что улучшить
          </div>
          {redFlags.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {redFlags.map((f, i) => (
                <span
                  key={`flag-${i}`}
                  className="inline-flex items-center rounded-full px-3 py-1 text-xs font-mono"
                  style={{
                    background: "rgba(239,68,68,0.10)",
                    border: "1px solid rgba(239,68,68,0.35)",
                    color: "var(--danger)",
                  }}
                >
                  {f}
                </span>
              ))}
            </div>
          ) : (
            <span className="text-xs" style={{ color: "var(--text-muted)" }}>
              —
            </span>
          )}
        </div>
      </div>

      {/* Footer */}
      {(judge.model_used || typeof judge.latency_ms === "number") && (
        <div
          className="mt-5 pt-3 border-t font-mono text-[11px] uppercase tracking-widest text-right"
          style={{ borderColor: "var(--border-color)", color: "var(--text-muted)" }}
        >
          Оценка от {judge.model_used ?? "AI"}
          {typeof judge.latency_ms === "number" ? ` · ${judge.latency_ms} мс` : ""}
        </div>
      )}
    </motion.div>
  );
}
