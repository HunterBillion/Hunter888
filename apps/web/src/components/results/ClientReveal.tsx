"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Eye, Brain, Heart, AlertTriangle, Target, Shield, ChevronDown } from "lucide-react";
import type { ClientProfile } from "@/types";

interface ClientRevealProps {
  clientCard: ClientProfile;
}

export default function ClientReveal({ clientCard }: ClientRevealProps) {
  const [revealed, setRevealed] = useState(false);

  if (!clientCard) return null;

  const hasHidden = clientCard.archetype_code || clientCard.fears?.length || clientCard.soft_spot || clientCard.breaking_point || clientCard.hidden_objections?.length;
  if (!hasHidden) return null;

  const revealItems = [
    { icon: Brain, label: "Архетип", value: clientCard.archetype_code, color: "var(--accent)" },
    { icon: AlertTriangle, label: "Страхи", value: clientCard.fears?.join(", "), color: "var(--neon-red, #FF2A6D)" },
    { icon: Heart, label: "Мягкая точка", value: clientCard.soft_spot, color: "var(--neon-green, #00FF94)" },
    { icon: Target, label: "Точка слома", value: clientCard.breaking_point, color: "var(--neon-amber, #FFD700)" },
    { icon: Shield, label: "Скрытые возражения", value: clientCard.hidden_objections?.join(", "), color: "var(--magenta, #E028CC)" },
  ].filter((item) => item.value);

  return (
    <div className="glass-panel rounded-2xl overflow-hidden">
      {/* Trigger button */}
      <motion.button
        onClick={() => setRevealed(!revealed)}
        className="w-full flex items-center justify-between p-6"
        whileTap={{ scale: 0.99 }}
      >
        <div className="flex items-center gap-2">
          <Eye size={16} style={{ color: "var(--accent)" }} />
          <span className="font-display text-sm tracking-widest" style={{ color: "var(--text-primary)" }}>
            РАСКРЫТИЕ КЛИЕНТА
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="font-mono text-[10px]" style={{ color: "var(--text-muted)" }}>
            {revealed ? "Скрыть" : "Показать скрытые данные"}
          </span>
          <motion.span
            animate={{ rotate: revealed ? 180 : 0 }}
            transition={{ duration: 0.3 }}
          >
            <ChevronDown size={14} style={{ color: "var(--text-muted)" }} />
          </motion.span>
        </div>
      </motion.button>

      {/* Reveal content with flip animation */}
      <AnimatePresence>
        {revealed && (
          <motion.div
            initial={{ height: 0, opacity: 0, rotateX: -15 }}
            animate={{ height: "auto", opacity: 1, rotateX: 0 }}
            exit={{ height: 0, opacity: 0, rotateX: 15 }}
            transition={{ duration: 0.5, ease: "easeOut" }}
            className="overflow-hidden"
            style={{ perspective: "800px" }}
          >
            <div
              className="px-6 pb-6 grid grid-cols-1 sm:grid-cols-2 gap-4"
              style={{ borderTop: "1px solid var(--border-color)" }}
            >
              {revealItems.map((item, i) => {
                const Icon = item.icon;
                return (
                  <motion.div
                    key={item.label}
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.1 + i * 0.1 }}
                    className="rounded-xl p-4 mt-4"
                    style={{
                      background: "var(--input-bg)",
                      borderLeft: `3px solid ${item.color}`,
                      boxShadow: `inset 0 0 30px ${item.color}08`,
                    }}
                  >
                    <div className="flex items-center gap-2 mb-2">
                      <Icon size={13} style={{ color: item.color }} />
                      <span className="font-mono text-[10px] uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
                        {item.label}
                      </span>
                    </div>
                    <p className="text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                      {item.value}
                    </p>
                  </motion.div>
                );
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
