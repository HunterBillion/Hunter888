/**
 * Resolve the VT323 pixel font family from the CSS variable
 * set by Next.js Google Fonts in layout.tsx (--font-vt323).
 *
 * Canvas 2D cannot use CSS variables directly in ctx.font,
 * so we read the computed value at runtime.
 *
 * Returns the font-family string for use in canvas ctx.font.
 */

let _cached: string | null = null;

export function getPixelFontFamily(): string {
  if (typeof document === "undefined") return '"Courier New", monospace';
  if (_cached) return _cached;
  const val = getComputedStyle(document.documentElement)
    .getPropertyValue("--font-vt323")
    .trim();
  _cached = val || '"Courier New", monospace';
  return _cached;
}

/** Build a canvas-ready font string: `bold 32px <VT323>, monospace` */
export function pixelFont(size: number, weight: "normal" | "bold" = "bold"): string {
  return `${weight} ${size}px ${getPixelFontFamily()}, "Courier New", monospace`;
}
