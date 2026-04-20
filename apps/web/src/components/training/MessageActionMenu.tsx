"use client";

/**
 * MessageActionMenu — Telegram-style context action popup for chat bubbles.
 *
 * 2026-04-18: replaces the always-visible hover Pin button.
 * Behavior: user taps/clicks a message → this popup appears above the bubble
 * with 3 actions: Ответить (quote in input), Закрепить (toggle pin), Скопировать.
 *
 * Closes on:
 *   - click outside
 *   - Escape
 *   - after an action fires
 *
 * Positioned `fixed` relative to anchor element's bounding rect (not portal
 * inside bubble — avoids transform/overflow ancestor clipping).
 */

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Reply, Pin, Copy, Check, X } from "lucide-react";

interface Anchor {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface MessageActionMenuProps {
  open: boolean;
  anchor: Anchor | null;
  isPinned: boolean;
  onReply: () => void;
  onTogglePin: () => void;
  onCopy: () => void;
  onClose: () => void;
}

export function MessageActionMenu({
  open,
  anchor,
  isPinned,
  onReply,
  onTogglePin,
  onCopy,
  onClose,
}: MessageActionMenuProps) {
  const [copied, setCopied] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Click outside + Escape closes
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    // Defer to next tick so the opening click doesn't close us immediately
    const t = setTimeout(() => {
      document.addEventListener("mousedown", onDoc);
      document.addEventListener("keydown", onKey);
    }, 0);
    return () => {
      clearTimeout(t);
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, onClose]);

  useEffect(() => {
    if (!open) setCopied(false);
  }, [open]);

  if (!open || !anchor) return null;

  // Position: prefer ABOVE anchor with 8px gap. Flip below if anchor is near the top.
  const menuWidth = 220;
  const menuHeight = 160;
  const preferAbove = anchor.y > menuHeight + 12;
  const top = preferAbove ? anchor.y - menuHeight - 8 : anchor.y + anchor.height + 8;
  // Clamp left so it doesn't overflow viewport
  let left = anchor.x + anchor.width / 2 - menuWidth / 2;
  const margin = 10;
  if (typeof window !== "undefined") {
    left = Math.max(margin, Math.min(left, window.innerWidth - menuWidth - margin));
  }

  const handleCopy = () => {
    onCopy();
    setCopied(true);
    setTimeout(() => {
      setCopied(false);
      onClose();
    }, 700);
  };

  return (
    <AnimatePresence>
      <motion.div
        ref={menuRef}
        initial={{ opacity: 0, y: preferAbove ? 6 : -6, scale: 0.96 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, scale: 0.96 }}
        transition={{ duration: 0.14, ease: "easeOut" }}
        role="menu"
        aria-label="Действия с сообщением"
        className="fixed z-[200]"
        style={{
          top,
          left,
          width: menuWidth,
          // 2026-04-18: fully opaque — user complaint "меню сливается с сообщениями"
          background: "var(--bg-secondary)",
          backdropFilter: "none",
          WebkitBackdropFilter: "none",
          border: "2px solid var(--accent)",
          borderRadius: 0,
          boxShadow:
            "4px 4px 0 0 var(--accent), 4px 4px 0 2px rgba(0,0,0,0.45), 0 8px 32px rgba(0,0,0,0.55), 0 0 18px var(--accent-glow)",
        }}
      >
        {/* Reply */}
        <ActionRow
          icon={<Reply size={16} />}
          label="Ответить"
          onClick={() => { onReply(); onClose(); }}
        />
        {/* Pin / Unpin */}
        <ActionRow
          icon={<Pin size={16} style={{ transform: isPinned ? "rotate(-20deg)" : undefined }} />}
          label={isPinned ? "Открепить" : "Закрепить"}
          accent={isPinned ? "var(--accent)" : undefined}
          onClick={() => { onTogglePin(); onClose(); }}
        />
        {/* Copy */}
        <ActionRow
          icon={copied ? <Check size={16} style={{ color: "var(--success)" }} /> : <Copy size={16} />}
          label={copied ? "Скопировано" : "Скопировать"}
          onClick={handleCopy}
          disableHover={copied}
        />
        {/* Divider + Close */}
        <div style={{ height: 1, background: "var(--border-color)", margin: "0" }} />
        <ActionRow
          icon={<X size={14} />}
          label="Закрыть"
          muted
          onClick={onClose}
        />
      </motion.div>
    </AnimatePresence>
  );
}

interface ActionRowProps {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  accent?: string;
  muted?: boolean;
  disableHover?: boolean;
}

function ActionRow({ icon, label, onClick, accent, muted, disableHover }: ActionRowProps) {
  return (
    <button
      type="button"
      role="menuitem"
      onClick={onClick}
      className="flex items-center gap-3 w-full px-4 py-3 text-left transition-colors"
      style={{
        color: accent || (muted ? "var(--text-muted)" : "var(--text-primary)"),
        // 2026-04-18: solid bg tied to parent menu surface (not transparent)
        background: "var(--bg-secondary)",
        borderBottom: "1px solid var(--border-color)",
        fontSize: 14,
        cursor: disableHover ? "default" : "pointer",
      }}
      onMouseEnter={(e) => {
        if (disableHover) return;
        (e.currentTarget as HTMLButtonElement).style.background = "var(--accent-muted)";
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLButtonElement).style.background = "var(--bg-secondary)";
      }}
    >
      <span className="shrink-0 flex items-center justify-center" style={{ width: 20 }}>{icon}</span>
      <span className="font-medium">{label}</span>
    </button>
  );
}
