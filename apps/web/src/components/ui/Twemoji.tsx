"use client";

/**
 * Renders emoji as high-quality Twemoji SVG images instead of system emoji.
 * Uses Twemoji CDN — no npm dependency needed.
 */
export function Twemoji({ emoji, size = 20, className = "" }: { emoji: string; size?: number; className?: string }) {
  // Convert emoji character to codepoint for Twemoji CDN URL
  const codepoint = [...emoji]
    .map((char) => char.codePointAt(0)?.toString(16))
    .filter(Boolean)
    .join("-")
    .replace(/-fe0f$/, ""); // Remove trailing variation selector

  return (
    <img
      src={`https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/svg/${codepoint}.svg`}
      alt={emoji}
      width={size}
      height={size}
      className={`inline-block ${className}`}
      style={{ verticalAlign: "middle" }}
      draggable={false}
      loading="lazy"
    />
  );
}
