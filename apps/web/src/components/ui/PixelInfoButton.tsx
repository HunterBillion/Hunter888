"use client";

/**
 * PixelInfoButton — unified info "i" button for panel headers.
 *
 * Created 2026-04-18 to replace the three ad-hoc info buttons in /training,
 * /clients, /dashboard and add matching buttons to /home, /history,
 * /leaderboard, /pvp. Pixel-arcade 90s aesthetic matches project's existing
 * pixel-border / pixel-shadow / font-pixel utility classes.
 *
 * 2026-04-18 fix: modal now uses React Portal so it escapes framer-motion
 * transformed ancestors and `overflow:hidden` hero cards (was trapping the
 * modal underneath adjacent panels on /home).
 *
 * Usage:
 *   <PixelInfoButton
 *     title="Лидерборд"
 *     sections={[
 *       { icon: Trophy, label: "Рейтинг", text: "Общий рейтинг игроков..." },
 *       { icon: Crown, label: "Лига недели", text: "Группы по 20 человек..." },
 *     ]}
 *   />
 */

import { useEffect, useState, type ComponentType } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";
import { Info, X } from "lucide-react";

export interface PixelInfoSection {
  icon?: ComponentType<{ size?: number; className?: string; style?: React.CSSProperties }>;
  label: string;
  text: string;
}

interface PixelInfoButtonProps {
  title: string;
  sections: PixelInfoSection[];
  /** Optional short footer note (e.g., "Tip: press Space to restart") */
  footer?: string;
  /** Button aria-label override */
  ariaLabel?: string;
}

export function PixelInfoButton({
  title,
  sections,
  footer,
  ariaLabel = "Справка по панели",
}: PixelInfoButtonProps) {
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);

  // Track SSR/CSR boundary so createPortal only runs after hydration
  useEffect(() => {
    setMounted(true);
  }, []);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  // Prevent body scroll while modal open
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  return (
    <>
      {/* ═══ Pixel-arcade button ═══ */}
      <motion.button
        type="button"
        onClick={() => setOpen(true)}
        aria-label={ariaLabel}
        whileHover={{ y: -1, x: -1 }}
        whileTap={{ y: 2, x: 2 }}
        transition={{ type: "spring", stiffness: 600, damping: 30 }}
        className="relative inline-flex items-center justify-center"
        style={{
          width: 36,
          height: 36,
          background: "var(--bg-panel)",
          border: "2px solid var(--accent)",
          borderRadius: 0,
          color: "var(--accent)",
          boxShadow:
            "3px 3px 0 0 var(--accent), 3px 3px 0 2px rgba(0,0,0,0.15)",
          cursor: "pointer",
          transition: "box-shadow 120ms ease-out",
        }}
      >
        {/* Inner pulse dot — subtle 90s blink */}
        <motion.span
          aria-hidden
          className="absolute"
          style={{
            top: 3,
            right: 3,
            width: 4,
            height: 4,
            background: "var(--accent)",
            borderRadius: 0,
          }}
          animate={{ opacity: [0.2, 1, 0.2] }}
          transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
        />
        <Info size={18} />
      </motion.button>

      {/* ═══ Pixel modal (rendered via Portal to escape transformed ancestors) ═══ */}
      {mounted && createPortal(
        <AnimatePresence>
        {open && (
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label={title}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[9999] flex items-center justify-center p-4"
            style={{
              background:
                "radial-gradient(ellipse at center, rgba(0,0,0,0.65) 0%, rgba(0,0,0,0.85) 100%)",
              // Subtle pixel grid on backdrop (doesn't distract from content)
              backgroundImage: `
                radial-gradient(ellipse at center, rgba(0,0,0,0.65) 0%, rgba(0,0,0,0.88) 100%),
                repeating-linear-gradient(0deg, transparent 0, transparent 7px, rgba(255,255,255,0.02) 7px, rgba(255,255,255,0.02) 8px),
                repeating-linear-gradient(90deg, transparent 0, transparent 7px, rgba(255,255,255,0.02) 7px, rgba(255,255,255,0.02) 8px)
              `,
            }}
            onClick={() => setOpen(false)}
          >
            <motion.div
              role="document"
              initial={{ scale: 0.9, y: 8, opacity: 0 }}
              animate={{ scale: 1, y: 0, opacity: 1 }}
              exit={{ scale: 0.92, y: 4, opacity: 0 }}
              transition={{ type: "spring", stiffness: 320, damping: 26 }}
              className="relative w-full max-w-md"
              style={{
                background: "var(--bg-panel)",
                backdropFilter: "blur(8px)",
                WebkitBackdropFilter: "blur(8px)",
                border: "2px solid var(--accent)",
                borderRadius: 0,
                boxShadow:
                  "6px 6px 0 0 var(--accent), 6px 6px 0 2px rgba(0,0,0,0.25), 0 0 24px 0 var(--accent-glow)",
              }}
              onClick={(e) => e.stopPropagation()}
            >
              {/* Title bar with pixel-style corner brackets */}
              <div
                className="flex items-center justify-between px-4 py-3"
                style={{ borderBottom: "2px solid var(--accent)" }}
              >
                <h3
                  className="font-pixel text-sm uppercase tracking-wider"
                  style={{ color: "var(--text-primary)" }}
                >
                  {title}
                </h3>
                <motion.button
                  type="button"
                  onClick={() => setOpen(false)}
                  whileHover={{ scale: 1.1 }}
                  whileTap={{ scale: 0.92 }}
                  aria-label="Закрыть"
                  className="inline-flex items-center justify-center"
                  style={{
                    width: 24,
                    height: 24,
                    background: "transparent",
                    border: "2px solid var(--text-muted)",
                    borderRadius: 0,
                    color: "var(--text-muted)",
                  }}
                >
                  <X size={14} />
                </motion.button>
              </div>

              {/* Sections */}
              <div className="p-4 space-y-3">
                {sections.map((s, i) => (
                  <motion.div
                    key={s.label}
                    initial={{ opacity: 0, x: -6 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.04 * i, duration: 0.2 }}
                    className="flex gap-3 items-start"
                  >
                    {s.icon ? (
                      <div
                        className="shrink-0 flex items-center justify-center mt-0.5"
                        style={{
                          width: 22,
                          height: 22,
                          background: "var(--accent-muted)",
                          border: "1px solid var(--accent)",
                          color: "var(--accent)",
                          borderRadius: 0,
                        }}
                      >
                        <s.icon size={13} />
                      </div>
                    ) : (
                      <div
                        className="shrink-0 mt-1"
                        style={{
                          width: 6,
                          height: 6,
                          background: "var(--accent)",
                          borderRadius: 0,
                        }}
                      />
                    )}
                    <div className="text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                      <strong
                        className="font-medium"
                        style={{ color: "var(--text-primary)" }}
                      >
                        {s.label}
                      </strong>
                      {" — "}
                      {s.text}
                    </div>
                  </motion.div>
                ))}
              </div>

              {footer && (
                <div
                  className="px-4 py-3 text-xs"
                  style={{
                    borderTop: "2px solid var(--accent-muted)",
                    color: "var(--text-muted)",
                    background: "var(--accent-muted)",
                  }}
                >
                  {footer}
                </div>
              )}
            </motion.div>
          </motion.div>
        )}
        </AnimatePresence>,
        document.body
      )}
    </>
  );
}
