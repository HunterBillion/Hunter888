"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowRight, Loader2, ChevronDown } from "lucide-react";
import type { ClientStatus } from "@/types";
import { CLIENT_STATUS_LABELS, CLIENT_STATUS_COLORS, ALLOWED_TRANSITIONS } from "@/types";

interface StatusTransitionProps {
  currentStatus: ClientStatus;
  onTransition: (newStatus: ClientStatus, reason?: string) => Promise<void>;
}

export function StatusTransition({ currentStatus, onTransition }: StatusTransitionProps) {
  const [open, setOpen] = useState(false);
  const [transitioning, setTransitioning] = useState(false);

  const allowed = ALLOWED_TRANSITIONS[currentStatus] || [];
  if (!allowed.length) return null;

  const handleSelect = async (status: ClientStatus) => {
    setTransitioning(true);
    setOpen(false);
    try {
      let reason: string | undefined;
      if (status === "lost" || status === "consent_revoked") {
        const value = window.prompt("Укажите причину перехода")?.trim();
        if (!value) {
          setTransitioning(false);
          return;
        }
        reason = value;
      }
      await onTransition(status, reason);
    } finally {
      setTransitioning(false);
    }
  };

  return (
    <div className="relative">
      <motion.button
        onClick={() => setOpen(!open)}
        disabled={transitioning}
        className="flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-mono transition-colors"
        style={{
          background: "var(--accent-muted)",
          border: "1px solid var(--accent)",
          color: "var(--accent)",
        }}
        whileTap={{ scale: 0.97 }}
      >
        {transitioning ? <Loader2 size={12} className="animate-spin" /> : <ArrowRight size={12} />}
        Сменить статус
        <ChevronDown size={12} className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </motion.button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.95 }}
            className="absolute top-full mt-1 left-0 z-20 rounded-xl overflow-hidden min-w-[180px]"
            style={{
              background: "var(--glass-bg)",
              backdropFilter: "blur(16px)",
              border: "1px solid var(--border-color)",
              boxShadow: "var(--shadow-lg)",
            }}
          >
            {allowed.map((s) => {
              const color = CLIENT_STATUS_COLORS[s];
              return (
                <motion.button
                  key={s}
                  onClick={() => handleSelect(s)}
                  className="w-full flex items-center gap-2 px-3 py-2 text-xs text-left transition-colors"
                  style={{ color: "var(--text-primary)" }}
                  whileHover={{ background: "var(--bg-tertiary)" }}
                >
                  <div
                    className="w-2 h-2 rounded-full shrink-0"
                    style={{ background: color }}
                  />
                  {CLIENT_STATUS_LABELS[s]}
                </motion.button>
              );
            })}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
