"use client";

import { useMemo } from "react";
import { motion } from "framer-motion";
import { useReducedMotion } from "@/hooks/useReducedMotion";

interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
  color?: string;
  showDot?: boolean;
  className?: string;
}

/**
 * Minimal SVG sparkline chart for inline metric visualization.
 * Draws a smooth line with optional animated endpoint dot.
 */
export function Sparkline({
  data,
  width = 80,
  height = 24,
  color = "var(--accent)",
  showDot = true,
  className = "",
}: SparklineProps) {
  const reducedMotion = useReducedMotion();

  const { path, lastPoint, gradientId } = useMemo(() => {
    if (data.length < 2) return { path: "", lastPoint: { x: 0, y: 0 }, gradientId: "" };

    const id = `sparkline-${Math.random().toString(36).slice(2, 8)}`;
    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min || 1;
    const padding = 2;

    const points = data.map((v, i) => ({
      x: padding + (i / (data.length - 1)) * (width - padding * 2),
      y: padding + (1 - (v - min) / range) * (height - padding * 2),
    }));

    // Build smooth SVG path
    let d = `M ${points[0].x},${points[0].y}`;
    for (let i = 1; i < points.length; i++) {
      const prev = points[i - 1];
      const curr = points[i];
      const cpx = (prev.x + curr.x) / 2;
      d += ` C ${cpx},${prev.y} ${cpx},${curr.y} ${curr.x},${curr.y}`;
    }

    return {
      path: d,
      lastPoint: points[points.length - 1],
      gradientId: id,
    };
  }, [data, width, height]);

  if (data.length < 2) return null;

  // Area fill path
  const areaPath = `${path} L ${width - 2},${height} L 2,${height} Z`;

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={`overflow-visible ${className}`}
      aria-hidden="true"
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.2" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>

      {/* Area fill */}
      <path d={areaPath} fill={`url(#${gradientId})`} />

      {/* Line */}
      <motion.path
        d={path}
        fill="none"
        stroke={color}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        initial={reducedMotion ? {} : { pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={reducedMotion ? {} : { duration: 0.8, ease: "easeOut" }}
      />

      {/* Endpoint dot */}
      {showDot && (
        <motion.circle
          cx={lastPoint.x}
          cy={lastPoint.y}
          r={2.5}
          fill={color}
          initial={reducedMotion ? {} : { scale: 0 }}
          animate={{ scale: 1 }}
          transition={reducedMotion ? {} : { delay: 0.7, type: "spring", stiffness: 300 }}
        />
      )}
    </svg>
  );
}
