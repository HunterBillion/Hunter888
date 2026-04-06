"use client";

import { useCallback } from "react";

/**
 * Haptic feedback patterns for different interaction types.
 * Uses Vibration API on supported devices (mobile).
 *
 * Patterns (ms): [vibrate, pause, vibrate, ...]
 */
const HAPTIC_PATTERNS = {
  /** Light tap — button press, selection */
  tap: [15],
  /** Success — achievement unlocked, correct answer */
  success: [30, 50, 30],
  /** Error / trap triggered — warning vibration */
  error: [50, 30, 80],
  /** Level up — celebration pattern */
  levelUp: [30, 40, 30, 40, 60, 40, 100],
  /** PvP victory — strong celebration */
  victory: [40, 30, 40, 30, 40, 80, 120],
  /** PvP defeat — subtle disappointment */
  defeat: [80, 100, 40],
  /** Notification — gentle attention */
  notify: [20, 60, 20],
  /** Drag start — kanban/pipeline interaction */
  drag: [10],
  /** Impact — consequence toast, critical event */
  impact: [60, 20, 100],
  /** Streak — daily streak continuation */
  streak: [20, 30, 20, 30, 20, 30, 40],
} as const;

export type HapticPattern = keyof typeof HAPTIC_PATTERNS;

/**
 * Hook for haptic (vibration) feedback.
 *
 * Usage:
 *   const haptic = useHaptic();
 *   haptic("success");     // achievement
 *   haptic("error");       // trap triggered
 *   haptic("levelUp");     // level up
 */
export function useHaptic() {
  const vibrate = useCallback((pattern: HapticPattern) => {
    try {
      if (typeof navigator !== "undefined" && "vibrate" in navigator) {
        navigator.vibrate(HAPTIC_PATTERNS[pattern]);
      }
    } catch {
      // Vibration not available — silent fail
    }
  }, []);

  return vibrate;
}
