"use client";

import { motion } from "framer-motion";
import { ArrowRight, BarChart3, Brain, FileText, PhoneCall } from "lucide-react";

interface StoryCallReportOverlayProps {
  callNumber: number;
  totalCalls: number;
  score: number;
  keyMoments: string[];
  memoriesCreated: number;
  consequences: Array<{
    call: number;
    type: string;
    severity: number;
    detail: string;
  }>;
  isFinal: boolean;
  onContinue: () => void;
}

export function StoryCallReportOverlay({
  callNumber,
  totalCalls,
  score,
  keyMoments,
  memoriesCreated,
  consequences,
  isFinal,
  onContinue,
}: StoryCallReportOverlayProps) {
  return (
    <div className="fixed inset-0 z-[155] flex items-center justify-center" style={{ background: "rgba(0,0,0,0.86)" }}>
      <motion.div
        initial={{ scale: 0.94, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        className="glass-panel mx-4 w-full max-w-3xl overflow-hidden"
      >
        <div
          className="flex items-center justify-between px-6 py-4"
          style={{ borderBottom: "1px solid var(--border-color)", background: "rgba(0,0,0,0.28)" }}
        >
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl" style={{ background: "var(--accent-muted)" }}>
              <FileText size={18} style={{ color: "var(--accent)" }} />
            </div>
            <div>
              <div className="font-display text-lg font-bold" style={{ color: "var(--text-primary)" }}>
                ОТЧЁТ ПО ЗВОНКУ
              </div>
              <div className="font-mono text-xs tracking-widest" style={{ color: "var(--text-muted)" }}>
                ЗВОНОК {callNumber} ИЗ {totalCalls}
              </div>
            </div>
          </div>

          <div className="rounded-xl px-4 py-2 text-right" style={{ background: "var(--accent-muted)", border: "1px solid var(--accent-glow)" }}>
            <div className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
              SCORE
            </div>
            <div className="font-display text-2xl font-bold" style={{ color: "var(--accent)" }}>
              {Math.round(score)}
            </div>
          </div>
        </div>

        <div className="grid gap-5 p-6 lg:grid-cols-[1.15fr_0.85fr]">
          <div className="space-y-5">
            <div>
              <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
                <Brain size={12} /> ключевые моменты
              </div>
              {keyMoments.length > 0 ? (
                <div className="space-y-2">
                  {keyMoments.slice(0, 5).map((moment, index) => (
                    <div
                      key={`${index}-${moment}`}
                      className="rounded-xl px-3 py-2 text-sm"
                      style={{ background: "rgba(255,255,255,0.03)", border: "1px solid var(--border-color)", color: "var(--text-secondary)" }}
                    >
                      {moment}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="rounded-xl px-3 py-3 text-sm" style={{ background: "rgba(255,255,255,0.03)", border: "1px solid var(--border-color)", color: "var(--text-muted)" }}>
                  Система не выделила отдельные ключевые моменты.
                </div>
              )}
            </div>

            {consequences.length > 0 && (
              <div>
                <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--warning)" }}>
                  <BarChart3 size={12} /> последствия истории
                </div>
                <div className="space-y-2">
                  {consequences.slice(-4).map((item, index) => (
                    <div
                      key={`${index}-${item.type}-${item.detail}`}
                      className="rounded-xl px-3 py-2 text-sm"
                      style={{
                        background: item.severity >= 0.7 ? "var(--danger-muted)" : "var(--warning-muted)",
                        border: `1px solid ${item.severity >= 0.7 ? "rgba(229,72,77,0.2)" : "rgba(245,158,11,0.2)"}`,
                        color: "var(--text-secondary)",
                      }}
                    >
                      {item.detail || item.type}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="space-y-4">
            <div className="rounded-2xl p-4" style={{ background: "rgba(255,255,255,0.03)", border: "1px solid var(--border-color)" }}>
              <div className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
                память клиента
              </div>
              <div className="mt-2 font-display text-3xl font-bold" style={{ color: "var(--text-primary)" }}>
                {memoriesCreated}
              </div>
              <div className="mt-1 text-sm" style={{ color: "var(--text-secondary)" }}>
                новых эпизодических воспоминаний зафиксировано после разговора
              </div>
            </div>

            <div className="rounded-2xl p-4" style={{ background: "var(--accent-muted)", border: "1px solid var(--accent-muted)" }}>
              <div className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--accent)" }}>
                следующий шаг
              </div>
              <div className="mt-2 text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                {isFinal
                  ? "История клиента завершена. Откроется CRM-панель с полной сводкой."
                  : "Подготовьте следующий контакт: клиент сохранит контекст, последствия и накопленные факторы."}
              </div>
            </div>
          </div>
        </div>

        <div className="flex justify-end px-6 py-4" style={{ borderTop: "1px solid var(--border-color)" }}>
          <motion.button
            onClick={onContinue}
            className="btn-neon flex items-center gap-2 px-7 py-3"
            whileTap={{ scale: 0.98 }}
          >
            {isFinal ? <><PhoneCall size={16} /> Открыть финал</> : <><ArrowRight size={16} /> К следующему звонку</>}
          </motion.button>
        </div>
      </motion.div>
    </div>
  );
}
