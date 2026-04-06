"use client";

import { useCallback, useRef, type CSSProperties, type RefObject } from "react";
import { useReducedMotion } from "@/hooks/useReducedMotion";

interface UseTiltOptions {
  /** Max rotation in degrees (default 3) */
  maxDeg?: number;
  /** Perspective distance in px (default 800) */
  perspective?: number;
}

/**
 * Subtle mouse-position-aware 3D tilt effect for cards.
 *
 * Returns a ref to attach to the element and event handlers for mouse tracking.
 * Clamps rotation to ±maxDeg. Uses only CSS transforms (GPU composited).
 * Falls back to identity transform when prefers-reduced-motion is active.
 *
 * Usage:
 *   const { ref, handlers } = useTiltEffect();
 *   <div ref={ref} {...handlers} />
 */
export function useTiltEffect<T extends HTMLElement = HTMLDivElement>(
  options: UseTiltOptions = {},
) {
  const { maxDeg = 3, perspective = 800 } = options;
  const ref = useRef<T>(null);
  const reducedMotion = useReducedMotion();
  const rafRef = useRef<number>(0);

  const resetTransform = useCallback(() => {
    if (ref.current) {
      ref.current.style.transform = `perspective(${perspective}px) rotateX(0deg) rotateY(0deg)`;
    }
  }, [perspective]);

  const onMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (reducedMotion || !ref.current) return;
      cancelAnimationFrame(rafRef.current);

      rafRef.current = requestAnimationFrame(() => {
        const el = ref.current;
        if (!el) return;
        const rect = el.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        const hw = rect.width / 2;
        const hh = rect.height / 2;

        // Normalize to -1..1, then scale to maxDeg
        const rotateY = ((x - hw) / hw) * maxDeg;
        const rotateX = -((y - hh) / hh) * maxDeg;

        el.style.transform = `perspective(${perspective}px) rotateX(${rotateX.toFixed(2)}deg) rotateY(${rotateY.toFixed(2)}deg)`;
      });
    },
    [maxDeg, perspective, reducedMotion],
  );

  const onMouseLeave = useCallback(() => {
    cancelAnimationFrame(rafRef.current);
    resetTransform();
  }, [resetTransform]);

  const baseStyle: CSSProperties = {
    transition: "transform 0.3s ease-out",
    transformStyle: "preserve-3d" as const,
  };

  return {
    ref: ref as RefObject<T>,
    handlers: {
      onMouseMove,
      onMouseLeave,
    },
    style: baseStyle,
  };
}
