"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Lightbulb, Send, RefreshCw, Loader2, X } from "lucide-react";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";

/**
 * Script hints — 3 LLM-generated reply suggestions.
 *
 * 2026-04-20 redesign (owner feedback):
 *   Before: the panel lived as a sticky footer glued to the bottom of the
 *   chat. It competed with the text input for space, and the only way to
 *   turn it off was a toggle buried in the right-side WhisperPanel — so
 *   every session the user had to reach for the toggle if they wanted a
 *   clean chat view.
 *
 *   After: a floating lightbulb FAB sits in the bottom-right corner of the
 *   chat area (never overlapping the input, never mixed into the message
 *   stream). When new suggestions arrive after an AI reply, the FAB pulses
 *   with a small badge showing the count. Click it → compact popover
 *   expands above the button with the 3 cards. Pick one → popover auto-
 *   closes, reply is sent. Start typing your own reply → popover auto-
 *   closes on the next keystroke. Click outside or press Esc → popover
 *   closes. No per-turn on/off dance.
 *
 *   The `scriptHintsEnabled` store flag still kills the whole feature if
 *   the manager genuinely never wants hints — we just hide the FAB, which
 *   is the cleanest possible opt-out.
 */

export interface ScriptHint {
  text: string;
  label?: string;
}

interface ScriptHintsProps {
  sessionId: string;
  onSend: (text: string) => void;
  /** Refresh trigger — caller bumps this number to re-fetch hints. */
  refreshKey?: number;
  /** If true, popover auto-hides (user is composing their own reply). */
  userTyping?: boolean;
}

export default function ScriptHints({
  sessionId,
  onSend,
  refreshKey = 0,
  userTyping = false,
}: ScriptHintsProps) {
  const [hints, setHints] = useState<ScriptHint[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  // `unseen` = new suggestions arrived since the user last engaged with the
  // feature. Drives the pulse animation on the FAB so the user notices
  // without the panel forcing itself into view.
  const [unseen, setUnseen] = useState(false);
  const popRef = useRef<HTMLDivElement>(null);
  const fabRef = useRef<HTMLButtonElement>(null);

  const fetchHints = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    try {
      const resp = await api.post<{ hints: ScriptHint[] }>(
        `/training/sessions/${sessionId}/script-hints`,
        {},
      );
      setHints(resp.hints || []);
      setUnseen(true);
    } catch (err) {
      logger.warn("[ScriptHints] fetch failed:", err);
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  // Re-fetch when parent bumps refreshKey (after AI turn / stage / checkpoint).
  useEffect(() => {
    fetchHints();
  }, [fetchHints, refreshKey]);

  // Auto-close when user starts composing their own reply.
  useEffect(() => {
    if (userTyping && open) setOpen(false);
  }, [userTyping, open]);

  // Click-outside + Esc to dismiss.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (popRef.current?.contains(t)) return;
      if (fabRef.current?.contains(t)) return;
      setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const handlePick = (text: string) => {
    onSend(text);
    setOpen(false);
    setUnseen(false);
  };

  const toggle = () => {
    setOpen((v) => !v);
    setUnseen(false);
  };

  const count = hints.length;

  return (
    // `bottom: 100` clears the input bar (~80px) with a 20px buffer so the
    // FAB sits just above the textarea instead of overlapping the send
    // button. `right: 20` aligns it to the chat aside's right edge.
    <div
      className="absolute z-30 pointer-events-none"
      style={{ right: 20, bottom: 100 }}
    >
      {/* ── Popover (expands upward from FAB) ─────────────────────── */}
      <AnimatePresence>
        {open && (
          <motion.div
            ref={popRef}
            key="pop"
            initial={{ opacity: 0, y: 12, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.97 }}
            transition={{ duration: 0.18, ease: "easeOut" }}
            className="pointer-events-auto absolute right-0 bottom-14 w-[min(380px,calc(100vw-48px))] rounded-xl shadow-2xl"
            style={{
              background: "var(--bg-primary)",
              border: "1px solid var(--border-color)",
              boxShadow: "0 12px 40px rgba(0,0,0,0.6), 0 0 0 1px var(--border-color)",
            }}
            role="dialog"
            aria-label="Варианты ответа"
          >
            {/* Header */}
            <div
              className="flex items-center justify-between px-3 py-2.5"
              style={{ borderBottom: "1px solid var(--border-color)" }}
            >
              <div className="flex items-center gap-2">
                <Lightbulb size={14} style={{ color: "var(--accent)" }} />
                <span
                  className="font-mono text-[10px] uppercase tracking-widest"
                  style={{ color: "var(--text-muted)" }}
                >
                  Варианты ответа
                </span>
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={fetchHints}
                  disabled={loading}
                  className="flex items-center gap-1 text-[10px] font-mono uppercase tracking-wider transition-opacity hover:opacity-70 disabled:opacity-40"
                  style={{ color: "var(--text-muted)" }}
                  title="Сгенерировать новые"
                >
                  <RefreshCw size={10} className={loading ? "animate-spin" : ""} />
                  Обновить
                </button>
                <button
                  onClick={() => setOpen(false)}
                  className="opacity-60 hover:opacity-100 transition-opacity"
                  style={{ color: "var(--text-muted)" }}
                  aria-label="Закрыть"
                >
                  <X size={14} />
                </button>
              </div>
            </div>

            {/* Cards */}
            <div className="p-3 space-y-2 max-h-[360px] overflow-y-auto">
              {loading && hints.length === 0 ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2
                    size={18}
                    className="animate-spin"
                    style={{ color: "var(--accent)" }}
                  />
                </div>
              ) : hints.length === 0 ? (
                <div
                  className="text-center text-sm py-6"
                  style={{ color: "var(--text-muted)" }}
                >
                  Подсказок пока нет. Нажмите «Обновить».
                </div>
              ) : (
                hints.map((hint, i) => (
                  <motion.div
                    key={`${i}-${hint.text.slice(0, 20)}`}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.04 }}
                    className="rounded-lg p-2.5 flex items-start gap-2.5 transition-colors hover:bg-[var(--accent-muted)]/40 cursor-pointer"
                    style={{
                      border: "1px solid var(--border-color)",
                      background: "rgba(255,255,255,0.02)",
                    }}
                    onClick={() => handlePick(hint.text)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        handlePick(hint.text);
                      }
                    }}
                  >
                    <div className="min-w-0 flex-1">
                      <div
                        className="text-sm leading-relaxed"
                        style={{ color: "var(--text-primary)" }}
                      >
                        {hint.text}
                      </div>
                    </div>
                    <div
                      className="shrink-0 flex items-center justify-center rounded-md w-8 h-8"
                      style={{
                        background: "var(--accent)",
                        color: "#fff",
                      }}
                      aria-hidden
                    >
                      <Send size={13} />
                    </div>
                  </motion.div>
                ))
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Floating Action Button ────────────────────────────────── */}
      <motion.button
        ref={fabRef}
        onClick={toggle}
        className="pointer-events-auto relative flex items-center justify-center rounded-full shadow-lg transition-transform active:scale-95"
        style={{
          width: 48,
          height: 48,
          background: open ? "var(--accent)" : "var(--bg-primary)",
          color: open ? "#fff" : "var(--accent)",
          border: `1px solid ${open ? "var(--accent)" : "var(--border-color)"}`,
          boxShadow: open
            ? "0 6px 22px var(--accent-glow)"
            : "0 4px 16px rgba(0,0,0,0.45)",
        }}
        whileHover={{ scale: 1.05 }}
        aria-label={open ? "Скрыть варианты ответа" : "Показать варианты ответа"}
        aria-expanded={open}
      >
        <Lightbulb size={20} />
        {/* Pulse ring when unseen suggestions are available */}
        {unseen && !open && (
          <motion.span
            className="absolute inset-0 rounded-full pointer-events-none"
            style={{ border: "2px solid var(--accent)" }}
            initial={{ opacity: 0.6, scale: 1 }}
            animate={{ opacity: 0, scale: 1.5 }}
            transition={{ duration: 1.4, repeat: Infinity }}
          />
        )}
        {/* Count badge */}
        {count > 0 && !open && (
          <span
            className="absolute -top-1 -right-1 flex items-center justify-center text-[10px] font-mono font-bold rounded-full"
            style={{
              width: 18,
              height: 18,
              background: unseen ? "var(--accent)" : "var(--bg-secondary)",
              color: unseen ? "#fff" : "var(--text-muted)",
              border: "1.5px solid var(--bg-primary)",
            }}
          >
            {count}
          </span>
        )}
      </motion.button>
    </div>
  );
}
