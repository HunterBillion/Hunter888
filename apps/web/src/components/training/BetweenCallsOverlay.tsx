"use client";

import { motion } from "framer-motion";
import { ArrowRight, CalendarClock, Sparkles, TriangleAlert } from "lucide-react";

interface BetweenCallEvent {
  event_type: string;
  title: string;
  content: string;
  severity: number | null;
}

interface Props {
  callNumber: number;
  totalCalls: number;
  events: BetweenCallEvent[];
  onContinue: () => void;
}

export function BetweenCallsOverlay({ callNumber, totalCalls, events, onContinue }: Props) {
  return (
    <div className="fixed inset-0 z-[145] flex items-center justify-center" style={{ background: "rgba(0,0,0,0.82)" }}>
      <motion.div
        initial={{ scale: 0.96, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        className="glass-panel mx-4 w-full max-w-3xl overflow-hidden"
      >
        <div
          className="flex items-center justify-between px-6 py-4"
          style={{ borderBottom: "1px solid var(--border-color)", background: "rgba(0,0,0,0.3)" }}
        >
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl" style={{ background: "rgba(139,92,246,0.16)" }}>
              <CalendarClock size={18} style={{ color: "var(--accent)" }} />
            </div>
            <div>
              <div className="font-display font-bold" style={{ color: "var(--text-primary)" }}>
                МЕЖДУ ЗВОНКАМИ
              </div>
              <div className="font-mono text-[10px] tracking-widest" style={{ color: "var(--text-muted)" }}>
                ПЕРЕХОД К ЗВОНКУ {callNumber} ИЗ {totalCalls}
              </div>
            </div>
          </div>
          <div className="font-mono text-[10px] uppercase tracking-widest" style={{ color: "var(--accent)" }}>
            AI STORY CONTINUITY
          </div>
        </div>

        <div className="space-y-4 p-6">
          <p className="text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
            Клиент прожил события между контактами. Эти изменения уже влияют на следующий разговор.
          </p>

          <div className="grid gap-3">
            {events.map((event, index) => {
              const isHigh = (event.severity ?? 0) >= 0.7;
              return (
                <motion.div
                  key={`${event.event_type}-${index}`}
                  initial={{ opacity: 0, x: -12 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: index * 0.06 }}
                  className="rounded-xl p-4"
                  style={{
                    background: isHigh ? "rgba(255,51,51,0.08)" : "rgba(255,255,255,0.03)",
                    border: `1px solid ${isHigh ? "rgba(255,51,51,0.2)" : "var(--border-color)"}`,
                  }}
                >
                  <div className="flex items-start gap-3">
                    <div className="mt-0.5">
                      {isHigh ? (
                        <TriangleAlert size={16} style={{ color: "var(--neon-red, #FF3333)" }} />
                      ) : (
                        <Sparkles size={16} style={{ color: "var(--accent)" }} />
                      )}
                    </div>
                    <div className="flex-1">
                      <div className="font-mono text-[10px] uppercase tracking-widest" style={{ color: isHigh ? "var(--neon-red, #FF3333)" : "var(--accent)" }}>
                        {event.title}
                      </div>
                      <div className="mt-1 text-sm" style={{ color: "var(--text-primary)" }}>
                        {event.content}
                      </div>
                    </div>
                  </div>
                </motion.div>
              );
            })}
          </div>
        </div>

        <div className="flex justify-end px-6 py-4" style={{ borderTop: "1px solid var(--border-color)" }}>
          <motion.button
            onClick={onContinue}
            className="vh-btn-primary flex items-center gap-2 px-7 py-3"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
          >
            К брифингу звонка <ArrowRight size={16} />
          </motion.button>
        </div>
      </motion.div>
    </div>
  );
}
