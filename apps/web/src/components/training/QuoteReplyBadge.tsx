"use client";

/**
 * QuoteReplyBadge (Phase 2.6, 2026-04-19)
 *
 * Shows above the input textarea when the user has tapped "Ответить" on an
 * older bubble. Displays a compact preview of the quoted content and an "x"
 * button to cancel the quote. Non-interactive otherwise — the bubble itself
 * owns the "click to navigate" action; this badge is just for pending state.
 *
 * Sits directly above the input so users see exactly what they're replying
 * to before they type and send.
 */

import { motion, AnimatePresence } from "framer-motion";
import { Quote, X } from "lucide-react";

interface Props {
  /** The preview text to show; null means no quote active. */
  preview: string | null;
  /** Click handler on the x button; caller should clear pending quote. */
  onCancel: () => void;
}

export function QuoteReplyBadge({ preview, onCancel }: Props) {
  return (
    <AnimatePresence>
      {preview && (
        <motion.div
          initial={{ opacity: 0, y: 6, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 6, scale: 0.98 }}
          transition={{ duration: 0.15 }}
          className="mb-2 flex items-start gap-2 rounded-lg px-3 py-2"
          style={{
            background: "var(--accent-muted)",
            borderLeft: "3px solid var(--accent)",
          }}
          aria-live="polite"
        >
          <Quote size={14} className="mt-0.5 shrink-0" style={{ color: "var(--accent)" }} />
          <div className="min-w-0 flex-1">
            <div
              className="text-[10px] uppercase tracking-wider font-semibold mb-0.5"
              style={{ color: "var(--accent)" }}
            >
              Ответ на сообщение
            </div>
            <div
              className="text-sm truncate"
              style={{ color: "var(--text-secondary)" }}
              title={preview}
            >
              {preview}
            </div>
          </div>
          <button
            type="button"
            onClick={onCancel}
            aria-label="Отменить цитирование"
            className="shrink-0 rounded-full p-1 transition-colors hover:bg-black/10"
            style={{ color: "var(--text-muted)" }}
          >
            <X size={14} />
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
