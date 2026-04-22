"use client";

/**
 * ScriptDrawer — mobile bottom sheet wrapper around ScriptPanel.
 * 2026-04-23 Sprint 3 (Zone 3 of plan moonlit-baking-crane.md).
 *
 * On screens narrower than `lg` the chat sidebar is hidden — there's no
 * room for an always-visible ScriptPanel. Instead this drawer:
 *   - Renders a small floating chip «📋 N/7 · Этап» fixed to the bottom
 *     of the viewport (above the input bar).
 *   - Tap chip → drawer slides up showing the full ScriptPanel content.
 *   - Auto-opens for ~2.5s on every stage.update (briefly highlights the
 *     new stage, then auto-closes).
 *   - Auto-opens AND stays open on stage.skipped (alert keeps showing
 *     the skip warning until user dismisses).
 *
 * Caller mounts <ScriptDrawer /> at the page root — no special parent
 * wrapper needed; positioning is fixed.
 */

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, Target } from "lucide-react";
import { useSessionStore } from "@/stores/useSessionStore";
import ScriptPanel from "@/components/training/ScriptPanel";
import { telemetry } from "@/lib/telemetry";

interface ScriptDrawerProps {
  /** Optional callback when user taps an example — caller writes into the
   *  message input. Forwarded to ScriptPanel. */
  onCopyExample?: (text: string) => void;
}

export default function ScriptDrawer({ onCopyExample }: ScriptDrawerProps) {
  const currentStage = useSessionStore((s) => s.currentStage);
  const totalStages = useSessionStore((s) => s.totalStages);
  const stageLabel = useSessionStore((s) => s.stageLabel);
  const skippedHint = useSessionStore((s) => s.skippedHint);

  const [open, setOpen] = useState(false);
  // Track stage to detect transitions (auto-open on change).
  const prevStageRef = useRef(currentStage);
  // Auto-close timer handle.
  const autoCloseRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Auto-open on stage transition.
  useEffect(() => {
    if (currentStage === prevStageRef.current) return;
    prevStageRef.current = currentStage;
    setOpen(true);
    telemetry.track("script_drawer_auto_open", {
      stage: currentStage,
      trigger: "stage_update",
    });
    if (autoCloseRef.current) clearTimeout(autoCloseRef.current);
    autoCloseRef.current = setTimeout(() => setOpen(false), 2500);
    return () => {
      if (autoCloseRef.current) clearTimeout(autoCloseRef.current);
    };
  }, [currentStage]);

  // Auto-open on skip — user MUST see this. No auto-close.
  useEffect(() => {
    if (!skippedHint) return;
    setOpen(true);
    telemetry.track("script_drawer_auto_open", {
      stage: currentStage,
      trigger: "stage_skipped",
    });
    if (autoCloseRef.current) clearTimeout(autoCloseRef.current);
  }, [skippedHint, currentStage]);

  return (
    <>
      {/* Floating chip — visible only on <lg, anchored above input bar */}
      {!open && (
        <motion.button
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          onClick={() => {
            setOpen(true);
            if (autoCloseRef.current) clearTimeout(autoCloseRef.current);
            telemetry.track("script_panel_toggle", {
              stage: currentStage,
              open: true,
            });
          }}
          type="button"
          className="lg:hidden fixed left-3 bottom-24 z-30 flex items-center gap-1.5 rounded-full px-3 py-2 text-xs font-semibold backdrop-blur-md transition active:scale-95"
          style={{
            background: skippedHint
              ? "rgba(234,179,8,0.16)"
              : "rgba(0,0,0,0.55)",
            color: "rgba(255,255,255,0.9)",
            border: skippedHint
              ? "1px solid rgba(234,179,8,0.45)"
              : "1px solid rgba(255,255,255,0.12)",
            boxShadow: "0 6px 20px rgba(0,0,0,0.35)",
          }}
          aria-label="Открыть скрипт"
        >
          <Target size={13} />
          <span>
            {currentStage}/{totalStages}
            {stageLabel && (
              <span className="ml-1 opacity-70">· {stageLabel}</span>
            )}
          </span>
          {skippedHint && (
            <span
              className="ml-1 inline-block w-2 h-2 rounded-full animate-pulse"
              style={{ background: "#EAB308" }}
              aria-hidden
            />
          )}
        </motion.button>
      )}

      {/* Bottom sheet */}
      <AnimatePresence>
        {open && (
          <>
            {/* Backdrop */}
            <motion.div
              key="backdrop"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.18 }}
              className="lg:hidden fixed inset-0 z-40 bg-black/40"
              onClick={() => setOpen(false)}
              aria-hidden
            />
            {/* Sheet */}
            <motion.div
              key="sheet"
              initial={{ y: "100%" }}
              animate={{ y: 0 }}
              exit={{ y: "100%" }}
              transition={{ type: "spring", damping: 30, stiffness: 280 }}
              drag="y"
              dragConstraints={{ top: 0, bottom: 0 }}
              dragElastic={0.2}
              onDragEnd={(_, info) => {
                if (info.offset.y > 80 || info.velocity.y > 500) {
                  setOpen(false);
                }
              }}
              className="lg:hidden fixed inset-x-0 bottom-0 z-50 max-h-[78vh] overflow-y-auto rounded-t-2xl px-5 pt-3 pb-6"
              style={{
                background: "var(--bg-secondary, #16161f)",
                borderTop: "1px solid var(--border-color)",
                boxShadow: "0 -16px 48px rgba(0,0,0,0.6)",
              }}
            >
              {/* Drag handle */}
              <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-white/15" />

              {/* Close button */}
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="absolute right-4 top-3 p-1 rounded-full hover:bg-white/5"
                aria-label="Закрыть"
              >
                <ChevronDown size={18} style={{ color: "var(--text-muted)" }} />
              </button>

              <ScriptPanel
                compactHeader={false}
                defaultCollapsed={false}
                onCopyExample={(text) => {
                  onCopyExample?.(text);
                  setOpen(false);  // close drawer after example pick
                }}
              />
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
