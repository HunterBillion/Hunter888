"use client";

import { motion } from "framer-motion";
import { FileText, AlertTriangle, Brain, ArrowRight, Phone } from "lucide-react";
import type { PreCallBrief } from "@/types/story";
import { HumanFactorIcons } from "./HumanFactorIcons";

interface Props {
  brief: PreCallBrief;
  onStart: () => void;
}

export function PreCallBriefOverlay({ brief, onStart }: Props) {
  return (
    <div className="fixed inset-0 z-[150] flex items-center justify-center" style={{ background: "rgba(0,0,0,0.85)" }}>
      <motion.div
        initial={{ scale: 0.9, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        className="glass-panel max-w-2xl w-full mx-4 overflow-hidden"
      >
        {/* Header */}
        <div
          className="px-6 py-4 flex items-center justify-between"
          style={{ borderBottom: "1px solid var(--border-color)", background: "rgba(0,0,0,0.3)" }}
        >
          <div className="flex items-center gap-3">
            <div
              className="flex h-10 w-10 items-center justify-center rounded-xl"
              style={{ background: "var(--accent-muted)" }}
            >
              <FileText size={18} style={{ color: "var(--accent)" }} />
            </div>
            <div>
              <div className="font-display font-bold" style={{ color: "var(--text-primary)" }}>
                БРИФИНГ ПЕРЕД ЗВОНКОМ
              </div>
              <div className="font-mono text-xs tracking-wider" style={{ color: "var(--text-muted)" }}>
                ЗВОНОК {brief.call_number} ИЗ {brief.total_calls} · {brief.client_name}
              </div>
            </div>
          </div>
          <div className="font-mono text-xs px-3 py-1 rounded-lg" style={{ background: "var(--accent-muted)", color: "var(--accent)" }}>
            {brief.scenario_title}
          </div>
        </div>

        {/* Content */}
        <div className="p-6 space-y-5">
          {/* Context */}
          <div>
            <div className="font-mono text-xs tracking-widest uppercase mb-2" style={{ color: "var(--text-muted)" }}>
              КОНТЕКСТ ЗВОНКА
            </div>
            <p className="text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
              {brief.context}
            </p>
          </div>

          {/* Active Human Factors */}
          {brief.active_factors.length > 0 && (
            <div>
              <div className="font-mono text-xs tracking-widest uppercase mb-2" style={{ color: "var(--text-muted)" }}>
                АКТИВНЫЕ ФАКТОРЫ КЛИЕНТА
              </div>
              <HumanFactorIcons factors={brief.active_factors} />
            </div>
          )}

          {/* Previous Consequences */}
          {brief.previous_consequences.length > 0 && (
            <div>
              <div className="font-mono text-xs tracking-widest uppercase mb-2 flex items-center gap-1.5" style={{ color: "var(--warning)" }}>
                <AlertTriangle size={12} /> ПОСЛЕДСТВИЯ ПРОШЛЫХ ЗВОНКОВ
              </div>
              <div className="space-y-1.5">
                {brief.previous_consequences.map((c, i) => (
                  <div
                    key={i}
                    className="text-xs px-3 py-2 rounded-lg flex items-center gap-2"
                    style={{
                      background: c.severity >= 0.7 ? "rgba(255,51,51,0.08)" : "rgba(245,158,11,0.08)",
                      border: `1px solid ${c.severity >= 0.7 ? "rgba(255,51,51,0.2)" : "rgba(245,158,11,0.2)"}`,
                      color: "var(--text-secondary)",
                    }}
                  >
                    <span className="font-mono text-xs" style={{ color: "var(--text-muted)" }}>#{c.call}</span>
                    {c.detail}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Suggested Approach */}
          {brief.suggested_approach && (
            <div>
              <div className="font-mono text-xs tracking-widest uppercase mb-2 flex items-center gap-1.5" style={{ color: "var(--accent)" }}>
                <Brain size={12} /> РЕКОМЕНДУЕМЫЙ ПОДХОД
              </div>
              <p className="text-sm italic" style={{ color: "var(--text-secondary)" }}>
                {brief.suggested_approach}
              </p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 flex justify-end" style={{ borderTop: "1px solid var(--border-color)" }}>
          <motion.button
            onClick={onStart}
            className="btn-neon flex items-center gap-2 text-lg px-8 py-3"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
          >
            <Phone size={18} /> Начать звонок <ArrowRight size={16} />
          </motion.button>
        </div>
      </motion.div>
    </div>
  );
}
