/**
 * Unified motion tokens for the entire platform.
 *
 * All components should import transitions from here instead of
 * defining inline spring/duration/ease values. This ensures:
 * - Consistent feel across pages
 * - Single source of truth for timing
 * - Easy global tuning
 *
 * Usage:
 *   import { MOTION, SCROLL_THRESHOLD, STAGGER_DELAY } from "@/lib/motion-tokens";
 *   <motion.div transition={MOTION.meso} />
 */

export const MOTION = {
  /** Hover, click, toggle — instant feedback */
  micro: { duration: 0.15, ease: [0.25, 0.1, 0.25, 1] as const },

  /** Cards, modals, drawers — snappy spring */
  meso: { type: "spring" as const, stiffness: 400, damping: 28 },

  /** Page transitions — smooth entrance */
  macro: { duration: 0.6, ease: [0.4, 0, 0.2, 1] as const },

  /** Toast, badge, unlock — celebratory pop */
  achievement: { type: "spring" as const, stiffness: 500, damping: 22 },

  /** Rank up — elastic overshoot */
  levelUp: { duration: 0.8, ease: [0.34, 1.56, 0.64, 1] as const },

  /** XP bar fill — fast decel */
  xpGain: { duration: 0.4, ease: "easeOut" as const },

  /** Trap fail, challenge — quick shake */
  shake: { intensity: 4, duration: 0.3 },

  /** Pixel-specific — snappy, instant feel (retro) */
  pixel: { duration: 0.1, ease: "easeOut" as const },

  /** Pixel hover — snappy instant response */
  pixelHover: { type: "tween" as const, duration: 0.1 },
} as const;

/** Unified IntersectionObserver threshold */
export const SCROLL_THRESHOLD = 0.3;

/** Unified stagger delay between list items */
export const STAGGER_DELAY = 0.08;

/** Fade-in-up preset for scroll-triggered content */
export const FADE_IN_UP = {
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0 },
  transition: MOTION.macro,
} as const;

/** Scale-in preset for modals/overlays */
export const SCALE_IN = {
  initial: { opacity: 0, scale: 0.95 },
  animate: { opacity: 1, scale: 1 },
  exit: { opacity: 0, scale: 0.95 },
  transition: MOTION.meso,
} as const;
