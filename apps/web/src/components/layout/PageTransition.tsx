"use client";

import type { ReactNode } from "react";

interface PageTransitionProps {
  children: ReactNode;
}

/**
 * PageTransition — minimal wrapper.
 * No animation between pages — instant switch, no flicker, no artifacts.
 * Animations happen WITHIN pages (stagger-cascade, fade-in-up on sections).
 */
export function PageTransition({ children }: PageTransitionProps) {
  return <>{children}</>;
}
