"use client";

/**
 * PinnedMessagesBar — compact bar above the chat listing user-pinned messages.
 *
 * 2026-04-18: new feature per user request — "нужно сделать прикрепление
 * сообщений, чтобы была возможность как ИИ-клиенту, так и нашему пользователю
 * вернуться в процессе этого чата".
 *
 * Behavior:
 *   - Collapsed: shows "📌 N закреплено" button (top-right of chat)
 *   - Expanded: shows list of pinned messages; click → smooth-scroll to the
 *     message element in chat via document.getElementById(`msg-${id}`).
 *   - User pins/unpins via the pin-button inside each ChatMessage bubble.
 */

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Pin, X } from "lucide-react";
import type { ChatBubble } from "@/types";

interface PinnedMessagesBarProps {
  messages: ChatBubble[];
  onUnpin: (id: string) => void;
  /** Optional id of the scroll container — scrollIntoView fires inside it */
  containerId?: string;
}

export function PinnedMessagesBar({ messages, onUnpin }: PinnedMessagesBarProps) {
  const pinned = messages.filter((m) => m.pinned);
  const [open, setOpen] = useState(false);

  // Close expanded panel with Escape
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  if (pinned.length === 0) return null;

  const jumpTo = (id: string) => {
    const el = document.getElementById(`msg-${id}`);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      // Flash highlight so user sees where we landed
      el.style.transition = "box-shadow 300ms ease-out";
      el.style.boxShadow = "0 0 0 3px var(--accent)";
      setTimeout(() => { el.style.boxShadow = ""; }, 1400);
    }
    setOpen(false);
  };

  return (
    <div className="sticky top-0 z-30 flex justify-end px-3 pt-2">
      {/* Toggle button */}
      <motion.button
        onClick={() => setOpen((v) => !v)}
        whileHover={{ y: -1 }}
        whileTap={{ y: 1 }}
        className="flex items-center gap-2 font-pixel uppercase tracking-wider"
        style={{
          height: 36,
          padding: "0 12px",
          background: "var(--accent-muted)",
          border: "2px solid var(--accent)",
          borderRadius: 0,
          color: "var(--accent)",
          boxShadow: "2px 2px 0 0 var(--accent)",
          fontSize: 13,
          cursor: "pointer",
        }}
        aria-label={open ? "Закрыть список закреплённых" : "Открыть закреплённые"}
      >
        <Pin size={14} />
        <span>{pinned.length} закреплено</span>
      </motion.button>

      {/* Expanded panel */}
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.18, ease: "easeOut" }}
            className="absolute top-12 right-3 max-w-sm w-full"
            style={{
              background: "var(--bg-panel)",
              border: "2px solid var(--accent)",
              borderRadius: 0,
              boxShadow: "4px 4px 0 0 var(--accent-muted), 0 0 18px var(--accent-glow)",
            }}
          >
            <div className="flex items-center justify-between px-4 py-3" style={{ borderBottom: "2px solid var(--accent)" }}>
              <div className="font-pixel uppercase tracking-wider" style={{ color: "var(--accent)", fontSize: 13 }}>
                📌 ЗАКРЕПЛЁННЫЕ · {pinned.length}
              </div>
              <button onClick={() => setOpen(false)} aria-label="Закрыть" style={{ color: "var(--text-muted)" }}>
                <X size={16} />
              </button>
            </div>
            <div className="max-h-80 overflow-y-auto">
              {pinned.map((m) => (
                <div
                  key={m.id}
                  className="group flex items-start gap-3 px-4 py-3 cursor-pointer transition-colors"
                  style={{ borderBottom: "1px solid var(--border-color)", background: "transparent" }}
                  onClick={() => jumpTo(m.id)}
                  onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.background = "var(--accent-muted)"; }}
                  onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.background = "transparent"; }}
                >
                  <div
                    className="shrink-0 font-pixel"
                    style={{
                      fontSize: 10,
                      color: m.role === "user" ? "var(--accent)" : "var(--success)",
                      minWidth: 40,
                      letterSpacing: "0.1em",
                    }}
                  >
                    {m.role === "user" ? "ВЫ" : "КЛИЕНТ"}
                  </div>
                  <div
                    className="flex-1 min-w-0 text-sm line-clamp-2"
                    style={{ color: "var(--text-primary)" }}
                  >
                    {m.content.slice(0, 180)}
                    {m.content.length > 180 ? "…" : ""}
                  </div>
                  <button
                    onClick={(e) => { e.stopPropagation(); onUnpin(m.id); }}
                    className="shrink-0 opacity-60 hover:opacity-100"
                    aria-label="Открепить"
                    style={{ color: "var(--text-muted)", padding: 4 }}
                  >
                    <X size={14} />
                  </button>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
