"use client";

/**
 * Renders emoji as high-quality Twemoji SVG images from CDN.
 * Replaces ugly system emoji with consistent Twitter-style artwork.
 * CDN: cdn.jsdelivr.net (whitelisted in CSP img-src)
 */

function emojiToCodepoint(emoji: string): string {
  const codepoints: string[] = [];
  for (const char of emoji) {
    const cp = char.codePointAt(0);
    if (cp !== undefined && cp !== 0xfe0f) { // skip variation selector
      codepoints.push(cp.toString(16));
    }
  }
  return codepoints.join("-");
}

export function Twemoji({
  emoji,
  size = 20,
  className = "",
}: {
  emoji: string;
  size?: number;
  className?: string;
}) {
  const codepoint = emojiToCodepoint(emoji);

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={`https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/svg/${codepoint}.svg`}
      alt={emoji}
      width={size}
      height={size}
      className={`inline-block shrink-0 ${className}`}
      style={{ verticalAlign: "middle" }}
      draggable={false}
      loading="lazy"
      onError={(e) => {
        // Fallback: show raw emoji if SVG not found
        const span = document.createElement("span");
        span.textContent = emoji;
        span.style.fontSize = `${size}px`;
        span.style.lineHeight = "1";
        (e.target as HTMLElement).replaceWith(span);
      }}
    />
  );
}
