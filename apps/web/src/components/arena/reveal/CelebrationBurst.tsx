"use client";

/**
 * CelebrationBurst — 1.2-second confetti burst fired on correct answer.
 *
 * Sprint 1 (2026-04-20). Pure CSS+framer-motion — no heavy confetti lib.
 * Renders 18 coloured particles radiating from a point on the screen
 * with trailing opacity fade. Plugs into Arena match page after a
 * correct verdict along with the SFX "correct" play.
 */

import { motion, AnimatePresence } from "framer-motion";

interface Props {
  /** When flipping to true, triggers a single burst then auto-dismisses. */
  trigger: boolean;
  /** Viewport coordinates of the burst origin (falls back to centre). */
  originX?: number;
  originY?: number;
  /** Palette — first few colours used for the particles. */
  colors?: string[];
}

const DEFAULT_COLORS = [
  "#22c55e",
  "#facc15",
  "#a78bfa",
  "#f472b6",
  "#60a5fa",
  "#fb923c",
];

export function CelebrationBurst({
  trigger,
  originX,
  originY,
  colors = DEFAULT_COLORS,
}: Props) {
  const particles = Array.from({ length: 18 });
  return (
    <AnimatePresence>
      {trigger && (
        <motion.div
          key={`burst-${trigger}`}
          className="pointer-events-none fixed inset-0 z-[300]"
          initial={{ opacity: 1 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.3 }}
        >
          {particles.map((_, i) => {
            const angle = (i / particles.length) * Math.PI * 2;
            const distance = 160 + Math.random() * 60;
            const color = colors[i % colors.length];
            const size = 8 + Math.random() * 6;
            const x0 = originX ?? (typeof window !== "undefined" ? window.innerWidth / 2 : 0);
            const y0 = originY ?? (typeof window !== "undefined" ? window.innerHeight / 2 : 0);
            const dx = Math.cos(angle) * distance;
            const dy = Math.sin(angle) * distance;
            return (
              <motion.span
                key={i}
                className="absolute rounded-sm"
                style={{
                  width: size,
                  height: size * 0.4,
                  background: color,
                  left: x0,
                  top: y0,
                  boxShadow: `0 0 8px ${color}`,
                }}
                initial={{ x: 0, y: 0, scale: 0, rotate: 0, opacity: 1 }}
                animate={{
                  x: dx,
                  y: dy + 40, // gravity
                  scale: 1,
                  rotate: Math.random() * 720 - 360,
                  opacity: 0,
                }}
                transition={{
                  duration: 1.1 + Math.random() * 0.3,
                  ease: [0.2, 0.7, 0.4, 1],
                  delay: Math.random() * 0.08,
                }}
              />
            );
          })}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
