"use client";

import { useRef } from "react";
import { motion, useInView } from "framer-motion";

/**
 * Wrapper that animates children into view when they enter the viewport.
 *
 * Variants:
 * - "fade-up"   — fade + slide up (default, good for cards and text)
 * - "fade-scale" — fade + scale from 0.85 (good for charts and graphs)
 * - "slide-right" — slide in from the left (good for timeline items)
 * - "count-up"  — opacity only, for number counters that animate themselves
 *
 * Usage:
 *   <RevealOnScroll variant="fade-scale" delay={0.1}>
 *     <MyChart />
 *   </RevealOnScroll>
 */

type Variant = "fade-up" | "fade-scale" | "slide-right" | "count-up";

interface Props {
  children: React.ReactNode;
  variant?: Variant;
  delay?: number;
  duration?: number;
  /** Trigger when this fraction of the element is visible (0..1) */
  threshold?: number;
  /** Only animate once */
  once?: boolean;
  className?: string;
  style?: React.CSSProperties;
}

const VARIANTS: Record<Variant, { hidden: Record<string, number>; visible: Record<string, number> }> = {
  "fade-up": {
    hidden: { opacity: 0, y: 30 },
    visible: { opacity: 1, y: 0 },
  },
  "fade-scale": {
    hidden: { opacity: 0, scale: 0.85 },
    visible: { opacity: 1, scale: 1 },
  },
  "slide-right": {
    hidden: { opacity: 0, x: -40 },
    visible: { opacity: 1, x: 0 },
  },
  "count-up": {
    hidden: { opacity: 0 },
    visible: { opacity: 1 },
  },
};

export function RevealOnScroll({
  children,
  variant = "fade-up",
  delay = 0,
  duration = 0.5,
  threshold = 0.15,
  once = true,
  className,
  style,
}: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const isInView = useInView(ref, {
    once,
    amount: threshold,
  });

  const v = VARIANTS[variant];

  return (
    <motion.div
      ref={ref}
      initial={v.hidden}
      animate={isInView ? v.visible : v.hidden}
      transition={{
        duration,
        delay,
        ease: [0.25, 0.46, 0.45, 0.94],
      }}
      className={className}
      style={style}
    >
      {children}
    </motion.div>
  );
}

/**
 * Staggered reveal for a list of items.
 * Each child gets an incremental delay.
 *
 * Usage:
 *   <StaggerReveal baseDelay={0.1} stagger={0.06}>
 *     <Card />
 *     <Card />
 *     <Card />
 *   </StaggerReveal>
 */
interface StaggerProps {
  children: React.ReactNode[];
  variant?: Variant;
  baseDelay?: number;
  stagger?: number;
  duration?: number;
  className?: string;
}

export function StaggerReveal({
  children,
  variant = "fade-up",
  baseDelay = 0,
  stagger = 0.06,
  duration = 0.45,
  className,
}: StaggerProps) {
  return (
    <div className={className}>
      {children.map((child, i) => (
        <RevealOnScroll
          key={i}
          variant={variant}
          delay={baseDelay + i * stagger}
          duration={duration}
        >
          {child}
        </RevealOnScroll>
      ))}
    </div>
  );
}
