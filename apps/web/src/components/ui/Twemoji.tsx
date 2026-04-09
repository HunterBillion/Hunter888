"use client";

/**
 * Renders emoji with consistent cross-platform styling.
 * Uses "Noto Color Emoji" web font for high-quality rendering,
 * with system emoji as fallback.
 */
export function Twemoji({ emoji, size = 20, className = "" }: { emoji: string; size?: number; className?: string }) {
  return (
    <span
      className={`inline-flex items-center justify-center shrink-0 ${className}`}
      style={{
        width: size,
        height: size,
        fontSize: size * 0.85,
        lineHeight: 1,
        fontFamily: "'Noto Color Emoji', 'Apple Color Emoji', 'Segoe UI Emoji', sans-serif",
        textAlign: "center",
      }}
      role="img"
      aria-label={emoji}
    >
      {emoji}
    </span>
  );
}
