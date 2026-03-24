"use client";

import { useState, useEffect } from "react";

/**
 * Detects user's prefers-reduced-motion setting.
 * Returns true when the user prefers reduced motion.
 *
 * Usage:
 *   const reduced = useReducedMotion();
 *   <motion.div animate={reduced ? {} : { y: [0, -10, 0] }} />
 */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    const mql = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mql.matches);

    const handler = (e: MediaQueryListEvent) => setReduced(e.matches);
    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, []);

  return reduced;
}
