"use client";

import { useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { usePathname } from "next/navigation";
import { useReducedMotion } from "@/hooks/useReducedMotion";
import { EASE_STANDARD } from "@/lib/constants";
import type { ReactNode } from "react";

interface PageTransitionProps {
  children: ReactNode;
}

/**
 * Navigation depth map — determines slide direction on route change.
 * Deeper page → slide from right, shallower → slide from left, same level → y-slide.
 */
const NAV_DEPTH: Record<string, number> = {
  "/home": 0,
  "/training": 1,
  "/clients": 1,
  "/history": 1,
  "/leaderboard": 1,
  "/pvp": 1,
  "/reports": 1,
  "/dashboard": 1,
  "/settings": 1,
  "/notifications": 1,
  "/analytics": 2,
  "/results": 2,
  "/knowledge": 2,
};

function getDepth(path: string): number {
  // Exact match first
  if (path in NAV_DEPTH) return NAV_DEPTH[path];
  // Prefix match for dynamic routes (e.g. /results/[id], /training/[id])
  const segments = path.split("/").filter(Boolean);
  for (let i = segments.length; i > 0; i--) {
    const prefix = "/" + segments.slice(0, i).join("/");
    if (prefix in NAV_DEPTH) return NAV_DEPTH[prefix] + (segments.length - i);
  }
  return 1; // default depth
}

/**
 * Direction-aware page transition.
 * - Going deeper → slide from right
 * - Going back   → slide from left
 * - Same level   → subtle y-slide (original behaviour)
 * Respects prefers-reduced-motion.
 */
export function PageTransition({ children }: PageTransitionProps) {
  const pathname = usePathname();
  const reducedMotion = useReducedMotion();
  const prevPathRef = useRef(pathname);
  const prevDepthRef = useRef(getDepth(pathname));
  const directionRef = useRef<{ x: number; y: number }>({ x: 0, y: 6 });

  const currentDepth = getDepth(pathname);

  // Compute direction only when pathname actually changes — store in ref
  // to avoid mutating refs during render (React 18 Strict Mode safe).
  useEffect(() => {
    if (prevPathRef.current === pathname) return;
    const prevDepth = prevDepthRef.current;
    if (currentDepth > prevDepth) {
      directionRef.current = { x: 24, y: 0 };
    } else if (currentDepth < prevDepth) {
      directionRef.current = { x: -24, y: 0 };
    } else {
      directionRef.current = { x: 0, y: 6 };
    }
    prevPathRef.current = pathname;
    prevDepthRef.current = currentDepth;
  }, [pathname, currentDepth]);

  const { x: initialX, y: initialY } = directionRef.current;

  if (reducedMotion) {
    return <>{children}</>;
  }

  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={pathname}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{
          duration: 0.15,
          ease: EASE_STANDARD,
        }}
        style={{
          position: "relative",
          zIndex: 1,
          willChange: "opacity",
        }}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  );
}
