"use client";

import { motion } from "framer-motion";

interface CompassIconProps {
  size?: number;
  /** Accent colour for the north needle and glow ring */
  accentColor?: string;
  /** RGB string for glow (e.g. "144,92,237") — avoids broken hex suffix */
  accentRgb?: string;
  /** Extra className on the root svg wrapper */
  className?: string;
  /** Continuous slow spin: rotations per minute (default 2 rpm) */
  rpm?: number;
  /** Needle oscillates gently (true) vs spins continuously (false, default) */
  oscillate?: boolean;
}

/**
 * Animated SVG compass.
 *
 * Ring + tick marks rotate slowly (continuous).
 * North needle (red/accent) oscillates ±12° to simulate "seeking north".
 */
export function CompassIcon({
  size = 56,
  accentColor = "var(--accent)",
  accentRgb = "144,92,237",
  className = "",
  rpm = 1.8,
  oscillate = true,
}: CompassIconProps) {
  const duration = 60 / rpm; // seconds per full rotation

  return (
    <motion.div
      className={`relative flex items-center justify-center ${className}`}
      style={{ width: size, height: size }}
    >
      {/* Outer pulsing glow ring */}
      <motion.div
        className="absolute rounded-full pointer-events-none"
        style={{
          width: size * 1.45,
          height: size * 1.45,
          background: `radial-gradient(circle, rgba(${accentRgb},0.13) 0%, transparent 70%)`,
        }}
        animate={{ scale: [1, 1.12, 1], opacity: [0.6, 1, 0.6] }}
        transition={{ duration: 3.2, repeat: Infinity, ease: "easeInOut" }}
      />

      {/* Main SVG */}
      <svg
        width={size}
        height={size}
        viewBox="0 0 56 56"
        fill="none"
        style={{ position: "relative", zIndex: 1 }}
      >
        {/* ── Outer bezel ── */}
        <circle cx="28" cy="28" r="27" stroke={accentColor} strokeWidth="0.8" strokeOpacity="0.25" />

        {/* ── Rotating tick ring ── */}
        <motion.g
          style={{ transformOrigin: "28px 28px" }}
          animate={{ rotate: 360 }}
          transition={{ duration, repeat: Infinity, ease: "linear" }}
        >
          {/* 36 ticks — every 10° */}
          {Array.from({ length: 36 }, (_, i) => {
            const angle = (i * 10 * Math.PI) / 180;
            const major = i % 9 === 0; // N/E/S/W ticks slightly longer
            const r1 = major ? 21 : 22.5;
            const r2 = 24;
            return (
              <line
                key={i}
                x1={28 + r1 * Math.sin(angle)}
                y1={28 - r1 * Math.cos(angle)}
                x2={28 + r2 * Math.sin(angle)}
                y2={28 - r2 * Math.cos(angle)}
                stroke={major ? accentColor : "currentColor"}
                strokeWidth={major ? 1.4 : 0.7}
                strokeOpacity={major ? 0.9 : 0.35}
              />
            );
          })}
        </motion.g>

        {/* ── Inner compass disc ── */}
        <circle cx="28" cy="28" r="18" fill="var(--bg-primary)" fillOpacity="0.7" />
        <circle cx="28" cy="28" r="18" stroke={accentColor} strokeWidth="0.6" strokeOpacity="0.3" />

        {/* ── Cross hairs ── */}
        <line x1="28" y1="11" x2="28" y2="45" stroke={accentColor} strokeWidth="0.4" strokeOpacity="0.15" />
        <line x1="11" y1="28" x2="45" y2="28" stroke={accentColor} strokeWidth="0.4" strokeOpacity="0.15" />

        {/* ── Oscillating needle ── */}
        <motion.g
          style={{ transformOrigin: "28px 28px" }}
          animate={
            oscillate
              ? { rotate: [0, 12, -8, 14, -6, 10, 0] }
              : { rotate: 360 }
          }
          transition={
            oscillate
              ? { duration: 7, repeat: Infinity, ease: "easeInOut", times: [0, 0.2, 0.4, 0.55, 0.7, 0.85, 1] }
              : { duration: duration * 0.5, repeat: Infinity, ease: "linear" }
          }
        >
          {/* North needle (accent) */}
          <polygon
            points="28,12 31,28 28,26 25,28"
            fill={accentColor}
            opacity="0.95"
            style={{ filter: `drop-shadow(0 0 3px rgba(${accentRgb},0.6))` }}
          />
          {/* South needle (muted) */}
          <polygon
            points="28,44 31,28 28,30 25,28"
            fill="currentColor"
            opacity="0.25"
          />
        </motion.g>

        {/* ── Centre pivot ── */}
        <circle cx="28" cy="28" r="2.5" fill={accentColor} opacity="0.9" />
        <circle cx="28" cy="28" r="1.2" fill="var(--bg-primary)" />

        {/* ── Cardinal letters (static) ── */}
        <text x="28" y="9.5" textAnchor="middle" fontSize="4.2" fontWeight="700"
          fill={accentColor} fillOpacity="0.85" fontFamily="var(--font-mono, monospace)"
          letterSpacing="0">N</text>
        <text x="28" y="51" textAnchor="middle" fontSize="3.6" fontWeight="400"
          fill="currentColor" fillOpacity="0.3" fontFamily="var(--font-mono, monospace)">S</text>
        <text x="47.5" y="29.2" textAnchor="middle" fontSize="3.6" fontWeight="400"
          fill="currentColor" fillOpacity="0.3" fontFamily="var(--font-mono, monospace)">E</text>
        <text x="8.5" y="29.2" textAnchor="middle" fontSize="3.6" fontWeight="400"
          fill="currentColor" fillOpacity="0.3" fontFamily="var(--font-mono, monospace)">W</text>
      </svg>
    </motion.div>
  );
}
