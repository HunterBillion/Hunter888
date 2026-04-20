"use client";

/**
 * HintBubble — compact overlay that shows the last returned hint.
 *
 * Sprint 4. Fades in from the bottom, auto-dismisses on click. Renders
 * a subtle gold accent since hint is the most "premium" lifeline.
 */

import { motion, AnimatePresence } from "framer-motion";
import { Lightbulb, X } from "lucide-react";

interface Props {
  open: boolean;
  text: string;
  article: string | null;
  confidence: number;
  onDismiss: () => void;
}

export function HintBubble({ open, text, article, confidence, onDismiss }: Props) {
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-x-0 bottom-24 z-50 flex justify-center px-4 pointer-events-none"
          initial={{ y: 40, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 20, opacity: 0 }}
          transition={{ type: "spring", stiffness: 320, damping: 26 }}
        >
          <div
            className="pointer-events-auto max-w-xl w-full rounded-2xl p-4 backdrop-blur-xl"
            style={{
              background: "rgba(20, 14, 32, 0.92)",
              border: "1px solid #facc1555",
              boxShadow: "0 20px 45px -15px #facc1566, 0 0 0 1px #facc1522 inset",
            }}
          >
            <div className="flex items-start gap-3">
              <div
                className="shrink-0 flex items-center justify-center w-9 h-9 rounded-xl"
                style={{ background: "#facc1520", color: "#facc15" }}
              >
                <Lightbulb size={18} />
              </div>
              <div className="flex-1 min-w-0">
                <div
                  className="text-[10px] font-semibold uppercase tracking-wider mb-1"
                  style={{ color: "#facc15" }}
                >
                  Подсказка
                  {confidence >= 0.6 && (
                    <span className="ml-2 opacity-70">· высокое соответствие</span>
                  )}
                  {confidence > 0 && confidence < 0.6 && (
                    <span className="ml-2 opacity-70">· подсказка общая</span>
                  )}
                </div>
                <div
                  className="text-[14px] leading-relaxed"
                  style={{ color: "#fef3c7" }}
                >
                  {text}
                </div>
                {article && (
                  <div
                    className="mt-2 inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-mono"
                    style={{
                      background: "#facc1518",
                      color: "#facc15",
                      border: "1px solid #facc1533",
                    }}
                  >
                    {article}
                  </div>
                )}
              </div>
              <button
                type="button"
                onClick={onDismiss}
                className="shrink-0 rounded-lg p-1 transition-colors hover:bg-white/10"
                aria-label="Закрыть подсказку"
                style={{ color: "#facc15" }}
              >
                <X size={16} />
              </button>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
