"use client";

import { motion } from "framer-motion";

/**
 * Morphing shape separator between X and HUNTER.
 * Smoothly transitions: circle → diamond → hexagon → circle.
 * Size is 1.5x smaller than surrounding text.
 */
interface Props {
  size?: number;
  color?: string;
}

// Border-radius keyframes for morphing:
// circle (50%) → diamond (4px rotated) → hexagon (30% corners) → circle
const MORPH_SHAPES = [
  "50%",         // circle
  "4px",         // diamond (rotated square)
  "25% 10%",     // hexagon-ish
  "50%",         // back to circle
];

const MORPH_ROTATIONS = [0, 45, 0, 0];
const MORPH_SCALES = [1, 0.85, 0.95, 1];

const centerAbsolute = { inset: 0, margin: "auto" } as const;

export function LogoSeparator({ size = 20, color = "var(--accent)" }: Props) {
  const s = Math.round(size * 0.66);

  return (
    <motion.span
      className="inline-flex items-center justify-center shrink-0 relative"
      style={{
        width: s,
        height: s,
        verticalAlign: "middle",
        marginLeft: "0.12em",
        marginRight: "0.12em",
      }}
    >
      {/* Morphing outer shape — centered */}
      <motion.span
        className="absolute"
        style={{
          ...centerAbsolute,
          width: s,
          height: s,
          border: `1.5px solid ${color}`,
          boxShadow: `0 0 ${s * 0.3}px ${color}40`,
        }}
        animate={{
          borderRadius: MORPH_SHAPES,
          rotate: MORPH_ROTATIONS,
          scale: MORPH_SCALES,
        }}
        transition={{
          duration: 4,
          repeat: Infinity,
          ease: "easeInOut",
          times: [0, 0.33, 0.66, 1],
        }}
      />

      {/* Second shape — offset phase, more transparent, centered */}
      <motion.span
        className="absolute"
        style={{
          ...centerAbsolute,
          width: s * 0.75,
          height: s * 0.75,
          border: `1px solid ${color}`,
          opacity: 0.3,
        }}
        animate={{
          borderRadius: [...MORPH_SHAPES.slice(2), ...MORPH_SHAPES.slice(0, 2)],
          rotate: [...MORPH_ROTATIONS.slice(2), ...MORPH_ROTATIONS.slice(0, 2)],
          scale: MORPH_SCALES.map((v) => v * 0.9),
        }}
        transition={{
          duration: 4,
          repeat: Infinity,
          ease: "easeInOut",
          times: [0, 0.33, 0.66, 1],
        }}
      />

      {/* Inner glow core — centered */}
      <motion.span
        className="absolute rounded-full"
        style={{
          ...centerAbsolute,
          width: s * 0.25,
          height: s * 0.25,
          background: color,
        }}
        animate={{
          boxShadow: [
            `0 0 ${s * 0.2}px ${color}`,
            `0 0 ${s * 0.5}px ${color}`,
            `0 0 ${s * 0.2}px ${color}`,
          ],
          scale: [1, 1.3, 1],
        }}
        transition={{
          duration: 2,
          repeat: Infinity,
          ease: "easeInOut",
        }}
      />
    </motion.span>
  );
}
