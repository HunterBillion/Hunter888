"use client";

import { useState, useEffect } from "react";
import { createPortal } from "react-dom";
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
  const [reasonTarget, setReasonTarget] = useState<ClientStatus | null>(null);
  const [reason, setReason] = useState("");
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);
  useEffect(() => { if (reasonTarget) setReason(""); }, [reasonTarget]);

  const allowed = ALLOWED_TRANSITIONS[currentStatus] || [];
  if (!allowed.length) return null;

  const handleSelect = async (status: ClientStatus) => {
    setOpen(false);
    if (status === "lost" || status === "consent_revoked") {
      setReasonTarget(status);
      return;
    }
    setTransitioning(true);
    try {
      await onTransition(status);
    } finally {
      setTransitioning(false);
    }
  };

  const handleReasonConfirm = async () => {
    const trimmed = reason.trim();
    if (!trimmed || !reasonTarget) return;
    setReasonTarget(null);
    setTransitioning(true);
    try {
      await onTransition(reasonTarget, trimmed);
    } finally {
      setTransitioning(false);
    }
  };

  const reasonLabel =
    reasonTarget === "lost"
      ? "Причина потери клиента"
      : "Причина отзыва согласия";

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

      {/* Reason modal for lost / consent_revoked */}
      {mounted && createPortal(
        <AnimatePresence>
          {reasonTarget && (
            <motion.div
              className="fixed inset-0 z-[100] flex items-center justify-center"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
            >
              <motion.div
                className="absolute inset-0"
                style={{ background: "var(--overlay-bg, rgba(0,0,0,0.4))" }}
                onClick={() => setReasonTarget(null)}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
              />
              <motion.div
                role="dialog"
                aria-modal="true"
                aria-label={reasonLabel}
                className="relative z-10 w-full max-w-md rounded-2xl p-6"
                style={{
                  background: "var(--surface-card, var(--bg-secondary))",
                  border: "1px solid var(--border-color)",
                  boxShadow: "0 8px 30px rgba(0,0,0,0.3)",
                }}
                initial={{ scale: 0.95, y: 16 }}
                animate={{ scale: 1, y: 0 }}
                exit={{ scale: 0.95, y: 16 }}
                transition={{ duration: 0.2 }}
              >
                <h3
                  className="text-sm font-semibold uppercase tracking-wide mb-4"
                  style={{ color: "var(--text-primary)" }}
                >
                  {reasonLabel}
                </h3>
                <textarea
                  autoFocus
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      void handleReasonConfirm();
                    }
                  }}
                  placeholder="Опишите причину..."
                  rows={4}
                  maxLength={500}
                  className="w-full text-sm font-mono rounded-lg px-3 py-2 outline-none"
                  style={{
                    background: "var(--input-bg)",
                    border: "1px solid var(--border-color)",
                    color: "var(--text-primary)",
                    resize: "vertical",
                  }}
                />
                <div className="flex items-center justify-end gap-2 mt-4">
                  <button
                    type="button"
                    onClick={() => setReasonTarget(null)}
                    className="rounded-lg px-4 py-2 text-sm font-medium"
                    style={{
                      background: "var(--input-bg)",
                      border: "1px solid var(--border-color)",
                      color: "var(--text-muted)",
                    }}
                  >
                    Отмена
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleReasonConfirm()}
                    disabled={!reason.trim()}
                    className="rounded-lg px-4 py-2 text-sm font-semibold"
                    style={{
                      background: reason.trim() ? "var(--danger)" : "var(--input-bg)",
                      color: reason.trim() ? "#fff" : "var(--text-muted)",
                      border: `1px solid ${reason.trim() ? "var(--danger)" : "var(--border-color)"}`,
                      opacity: reason.trim() ? 1 : 0.6,
                    }}
                  >
                    Подтвердить
                  </button>
                </div>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>,
        document.body,
      )}
    </div>
  );
}
