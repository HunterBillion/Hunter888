"use client";

/**
 * LobbyMascot — wrapper around PixelMascot that animates between
 * registered DOM anchors via useMascotAnchorStore.
 *
 * Layered FE-only: lobby panels (HonestNavigator tiles, RatingCard,
 * history list) call useMascotAnchor("tile-duel") to publish their
 * bounding rects. setTarget("tile-duel") on hover/focus → mascot
 * animates to that rect (centred at the anchor's bottom-right corner)
 * via Framer Motion. setTarget(null) → mascot returns to its fixed
 * bottom-right home corner.
 *
 * State auto-derives walk/cheer/idle from queue lifecycle, but can be
 * overridden via the `forcedState` prop.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { PixelMascot } from "./PixelMascot";
import type { MascotState } from "./PixelMascotSprites";
import { useMascotAnchorStore } from "@/stores/useMascotAnchorStore";

interface LobbyMascotProps {
  /** Override auto-derived state. */
  forcedState?: MascotState;
  size?: number;
  /** Override accent (default var(--accent)). */
  accent?: string;
}

const HOME_OFFSET_PX = 24; // distance from viewport bottom-right edge
const MASCOT_SIZE_DEFAULT = 80;

export function LobbyMascot({ forcedState, size = MASCOT_SIZE_DEFAULT, accent }: LobbyMascotProps) {
  const target = useMascotAnchorStore((s) => s.target);
  const anchors = useMascotAnchorStore((s) => s.anchors);
  const reducedMotion = useReducedMotion();
  const [vp, setVp] = useState({ w: 0, h: 0 });

  // Track viewport size for the home position fallback.
  useEffect(() => {
    const sync = () => setVp({ w: window.innerWidth, h: window.innerHeight });
    sync();
    window.addEventListener("resize", sync);
    return () => window.removeEventListener("resize", sync);
  }, []);

  // Compute target xy. anchor.x/y are top-left of the anchor element.
  // We want the mascot centred at the bottom-right of the anchor (so it
  // looks like it "perched" on the tile). For home we use viewport edge.
  const targetXY = useMemo(() => {
    const homeX = vp.w - size - HOME_OFFSET_PX;
    const homeY = vp.h - size - HOME_OFFSET_PX;
    if (!target || target === "home") return { x: homeX, y: homeY };
    const a = anchors[target];
    if (!a) return { x: homeX, y: homeY };
    // Centre at bottom-right of anchor; clamp to viewport.
    const x = Math.min(Math.max(a.x + a.width - size / 2, 8), vp.w - size - 8);
    const y = Math.min(Math.max(a.y + a.height - size / 2, 8), vp.h - size - 8);
    return { x, y };
  }, [target, anchors, vp.w, vp.h, size]);

  // Derive auto state when no override:
  //   - walk while migrating to a non-home anchor (covered by tile hover)
  //   - cheer-overlay handled by parent (forcedState="cheer")
  //   - idle otherwise
  const autoState: MascotState = target && target !== "home" ? "walk" : "idle";
  const finalState = forcedState ?? autoState;

  // Don't animate on reduced-motion preference — just teleport.
  const transition = reducedMotion
    ? { duration: 0 }
    : { type: "spring" as const, stiffness: 220, damping: 24, mass: 0.8 };

  const initialRendered = useRef(false);
  useEffect(() => { initialRendered.current = true; }, []);

  return (
    <motion.div
      className="pointer-events-none fixed z-40 hidden md:block"
      style={{ top: 0, left: 0 }}
      initial={initialRendered.current ? false : { opacity: 0, x: targetXY.x, y: targetXY.y }}
      animate={{ opacity: 1, x: targetXY.x, y: targetXY.y }}
      transition={transition}
    >
      <PixelMascot state={finalState} size={size} accent={accent} />
    </motion.div>
  );
}
