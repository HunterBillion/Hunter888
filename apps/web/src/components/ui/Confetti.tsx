"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useReducedMotion } from "@/hooks/useReducedMotion";

interface Particle {
  id: number;
  x: number;
  color: string;
  size: number;
  rotation: number;
  delay: number;
}

const COLORS = [
  "var(--accent)", // violet
  "#FFD700", // gold
  "#00FF66", // green
  "#FF6B6B", // red
  "var(--info)", // blue
  "var(--warning)", // amber
  "#EC4899", // pink
];

/**
 * Confetti burst animation. Triggered by `trigger` prop change.
 * Respects prefers-reduced-motion — shows a simple glow flash instead.
 */
export function Confetti({ trigger }: { trigger: number }) {
  const [particles, setParticles] = useState<Particle[]>([]);
  const idRef = useRef(0);
  const reducedMotion = useReducedMotion();

  useEffect(() => {
    if (trigger <= 0) return;

    if (reducedMotion) {
      // Simple flash for reduced motion
      setParticles([{ id: ++idRef.current, x: 50, color: "#FFD700", size: 100, rotation: 0, delay: 0 }]);
      const timer = setTimeout(() => setParticles([]), 600);
      return () => clearTimeout(timer);
    }

    // Generate particles
    const count = 40;
    const newParticles: Particle[] = Array.from({ length: count }, (_, i) => ({
      id: ++idRef.current,
      x: 30 + Math.random() * 40,
      color: COLORS[i % COLORS.length],
      size: 4 + Math.random() * 6,
      rotation: Math.random() * 720 - 360,
      delay: Math.random() * 0.3,
    }));

    setParticles(newParticles);
    const timer = setTimeout(() => setParticles([]), 2500);
    return () => clearTimeout(timer);
  }, [trigger, reducedMotion]);

  if (reducedMotion && particles.length > 0) {
    return (
      <motion.div
        className="fixed inset-0 z-[250] pointer-events-none"
        initial={{ opacity: 0 }}
        animate={{ opacity: [0, 0.3, 0] }}
        transition={{ duration: 0.6 }}
        style={{ background: "radial-gradient(circle, rgba(255,215,0,0.2), transparent 60%)" }}
      />
    );
  }

  return (
    <div className="fixed inset-0 z-[250] pointer-events-none overflow-hidden">
      <AnimatePresence>
        {particles.map((p) => (
          <motion.div
            key={p.id}
            className="absolute"
            style={{
              left: `${p.x}%`,
              top: "30%",
              width: p.size,
              height: p.size * (0.6 + Math.random() * 0.8),
              background: p.color,
              borderRadius: Math.random() > 0.5 ? "50%" : "2px",
            }}
            initial={{ y: 0, opacity: 1, scale: 0, rotate: 0 }}
            animate={{
              y: [0, -100 - Math.random() * 200, 400 + Math.random() * 300],
              x: [0, (Math.random() - 0.5) * 300],
              opacity: [0, 1, 1, 0],
              scale: [0, 1, 1, 0.5],
              rotate: p.rotation,
            }}
            exit={{ opacity: 0 }}
            transition={{
              duration: 1.8 + Math.random() * 0.5,
              delay: p.delay,
              ease: [0.25, 0.46, 0.45, 0.94],
            }}
          />
        ))}
      </AnimatePresence>
    </div>
  );
}
