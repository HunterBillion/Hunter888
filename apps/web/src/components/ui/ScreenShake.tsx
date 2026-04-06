"use client";

import { createContext, useContext, useCallback, useState, useRef } from "react";
import { motion, useReducedMotion } from "framer-motion";

// ── Types ─────────────────────────────────────────────────
type ShakePreset = "light" | "medium" | "heavy" | "error" | "victory";

interface ShakeConfig {
  intensity: number;   // pixels displacement
  duration: number;    // ms
  vignette?: string;   // CSS color for edge flash (e.g. "rgba(255,0,0,0.3)")
}

const PRESETS: Record<ShakePreset, ShakeConfig> = {
  light:   { intensity: 2,  duration: 200 },
  medium:  { intensity: 4,  duration: 300, vignette: "rgba(99,102,241,0.15)" },
  heavy:   { intensity: 6,  duration: 400, vignette: "rgba(255,42,109,0.25)" },
  error:   { intensity: 5,  duration: 350, vignette: "rgba(255,42,109,0.3)" },
  victory: { intensity: 3,  duration: 500, vignette: "rgba(255,215,0,0.2)" },
};

// ── Context ───────────────────────────────────────────────
type ShakeFn = (preset: ShakePreset) => void;
const ShakeContext = createContext<ShakeFn>(() => {});

export const useScreenShake = () => useContext(ShakeContext);

// ── Provider ──────────────────────────────────────────────
export function ScreenShakeProvider({ children }: { children: React.ReactNode }) {
  const reducedMotion = useReducedMotion();
  const [shakeStyle, setShakeStyle] = useState({ x: 0, y: 0 });
  const [vignetteColor, setVignetteColor] = useState<string | null>(null);
  const rafRef = useRef<number>(0);
  const timeoutRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  const shake = useCallback((preset: ShakePreset) => {
    if (reducedMotion) return;

    const cfg = PRESETS[preset];
    const start = performance.now();

    // Show vignette
    if (cfg.vignette) {
      setVignetteColor(cfg.vignette);
    }

    // Clear previous
    cancelAnimationFrame(rafRef.current);
    if (timeoutRef.current) clearTimeout(timeoutRef.current);

    const animate = () => {
      const elapsed = performance.now() - start;
      if (elapsed > cfg.duration) {
        setShakeStyle({ x: 0, y: 0 });
        setVignetteColor(null);
        return;
      }

      const progress = elapsed / cfg.duration;
      const decay = 1 - progress;
      const freq = 25 + progress * 15; // increasing frequency for "settling" feel
      const x = Math.sin(elapsed * freq * 0.01) * cfg.intensity * decay;
      const y = Math.cos(elapsed * freq * 0.012 + 1) * cfg.intensity * decay * 0.6;

      setShakeStyle({ x, y });
      rafRef.current = requestAnimationFrame(animate);
    };

    rafRef.current = requestAnimationFrame(animate);

    // Safety cleanup
    timeoutRef.current = setTimeout(() => {
      setShakeStyle({ x: 0, y: 0 });
      setVignetteColor(null);
    }, cfg.duration + 50);
  }, [reducedMotion]);

  return (
    <ShakeContext.Provider value={shake}>
      <motion.div
        style={{ x: shakeStyle.x, y: shakeStyle.y }}
        className="min-h-screen"
      >
        {children}
      </motion.div>

      {/* Vignette overlay */}
      {vignetteColor && (
        <div
          className="fixed inset-0 pointer-events-none z-[250]"
          style={{
            background: `radial-gradient(ellipse at center, transparent 50%, ${vignetteColor} 100%)`,
            transition: "opacity 0.15s ease-out",
          }}
        />
      )}
    </ShakeContext.Provider>
  );
}
