"use client";

/**
 * QuizAnswerCard — Arcade-Stage answer chip (Phase 1).
 *
 * Заменяет inline answer-chip render в quiz/[sessionId]/page.tsx.
 * Стиль: glass-tile rounded-xl + circular letter-badge цветной + текст
 * (sans 14px) + keyboard-shortcut hint (font-mono kbd-style).
 *
 * States:
 *   default     — glass background, soft border (badge color × 25%)
 *   hover       — y: -2 lift + boxShadow tier-color glow
 *   picked      — accent bg + accent border + checkmark badge + scale 0.99
 *   locked-out  — opacity 0.35 + blur(0.5px), pointer-events: none
 */

import { motion } from "framer-motion";
import { Check } from "lucide-react";

const BADGE_COLORS = [
  "var(--accent)",                    // A — фиолетовый
  "var(--success, #22c55e)",          // B — зелёный
  "var(--gf-xp, #facc15)",            // C — золотой
  "var(--magenta, #d946ef)",          // D — мажента
  "var(--warning, #f97316)",          // E — оранжевый
];

interface QuizAnswerCardProps {
  index: number;          // 0..4
  text: string;
  picked: boolean;
  locked: boolean;        // any choice is picked → disable others
  disabled?: boolean;     // store.status !== "active"
  onPick: (idx: number) => void;
}

export function QuizAnswerCard({
  index,
  text,
  picked,
  locked,
  disabled,
  onPick,
}: QuizAnswerCardProps) {
  const badgeColor = BADGE_COLORS[index % BADGE_COLORS.length];
  const letter = String.fromCharCode(65 + index);
  const dim = locked && !picked;
  const interactive = !locked && !disabled;

  return (
    <motion.button
      type="button"
      onClick={() => interactive && onPick(index)}
      disabled={!interactive}
      initial={{ opacity: 0, x: -16 }}
      animate={{ opacity: dim ? 0.35 : 1, x: 0 }}
      transition={{ delay: index * 0.04, duration: 0.22 }}
      whileHover={interactive ? { y: -2 } : undefined}
      whileTap={interactive ? { scale: 0.98 } : undefined}
      className="group relative w-full flex items-center gap-3 text-left rounded-xl overflow-hidden"
      style={{
        padding: "18px 20px",
        background: picked
          ? `linear-gradient(135deg, color-mix(in srgb, ${badgeColor} 18%, var(--glass-bg, rgba(255,255,255,0.04))) 0%, color-mix(in srgb, ${badgeColor} 8%, var(--glass-bg, rgba(255,255,255,0.04))) 100%)`
          : "linear-gradient(135deg, rgba(255,255,255,0.05) 0%, rgba(255,255,255,0.02) 100%)",
        border: `1px solid ${picked ? badgeColor : `color-mix(in srgb, ${badgeColor} 28%, transparent)`}`,
        boxShadow: picked
          ? `0 0 0 3px color-mix(in srgb, ${badgeColor} 18%, transparent), 0 12px 32px color-mix(in srgb, ${badgeColor} 26%, transparent), inset 0 1px 0 rgba(255,255,255,0.06)`
          : `0 4px 14px rgba(0,0,0,0.22), inset 0 1px 0 rgba(255,255,255,0.05)`,
        backdropFilter: "blur(20px) saturate(1.2)",
        WebkitBackdropFilter: "blur(20px) saturate(1.2)",
        cursor: interactive ? "pointer" : "default",
        transition: "background 200ms, border-color 200ms, box-shadow 240ms, transform 160ms",
      }}
      aria-pressed={picked}
      aria-label={`Вариант ${letter}: ${text}`}
    >
      {/* hover-glow stripe (left edge) */}
      <span
        aria-hidden
        className="absolute left-0 top-0 bottom-0 transition-all"
        style={{
          width: picked ? 4 : 3,
          background: badgeColor,
          opacity: picked ? 1 : 0.55,
          boxShadow: picked ? `0 0 12px ${badgeColor}` : "none",
        }}
      />

      {/* letter badge — circular с inset highlight для объёма */}
      <span
        className="font-display font-bold shrink-0 flex items-center justify-center select-none relative"
        style={{
          width: 48,
          height: 48,
          borderRadius: "50%",
          background: `radial-gradient(circle at 30% 25%, color-mix(in srgb, ${badgeColor} 100%, white 22%) 0%, ${badgeColor} 70%)`,
          color: "#0a0810",
          fontSize: 24,
          letterSpacing: "0.02em",
          boxShadow: picked
            ? `0 0 20px ${badgeColor}, inset 0 1px 0 rgba(255,255,255,0.4), inset 0 -2px 4px rgba(0,0,0,0.18)`
            : `0 4px 10px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.32), inset 0 -1px 4px rgba(0,0,0,0.2)`,
          transition: "box-shadow 220ms, transform 220ms",
          textShadow: "0 1px 0 rgba(255,255,255,0.18)",
        }}
      >
        {letter}
      </span>

      {/* answer text */}
      <span
        className="flex-1 leading-snug"
        style={{
          color: "var(--text-primary)",
          fontSize: 17,
          fontWeight: 500,
          lineHeight: 1.45,
        }}
      >
        {text}
      </span>

      {/* keyboard hint (md+) — kbd-style */}
      {interactive && (
        <kbd
          className="hidden md:inline-flex items-center justify-center font-mono shrink-0 select-none"
          style={{
            minWidth: 32,
            height: 32,
            padding: "0 8px",
            borderRadius: 8,
            background: "var(--input-bg)",
            border: "1px solid var(--border-color)",
            color: "var(--text-secondary)",
            fontSize: 14,
            fontWeight: 700,
            letterSpacing: "0.02em",
          }}
        >
          {letter}
        </kbd>
      )}

      {/* picked checkmark */}
      {picked && (
        <motion.span
          initial={{ scale: 0, rotate: -90 }}
          animate={{ scale: 1, rotate: 0 }}
          transition={{ type: "spring", stiffness: 360, damping: 18 }}
          className="shrink-0 flex items-center justify-center"
          style={{
            width: 32,
            height: 32,
            borderRadius: "50%",
            background: badgeColor,
            color: "#0a0810",
            boxShadow: `0 0 14px ${badgeColor}`,
          }}
          aria-hidden
        >
          <Check size={18} strokeWidth={3} />
        </motion.span>
      )}
    </motion.button>
  );
}
