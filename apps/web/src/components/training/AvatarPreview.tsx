"use client";

/**
 * AvatarPreview — pixel-art avatar for archetype cards.
 *
 * 2026-04-20: switched from DiceBear "notionists" (monochrome hand-sketched
 * style — read by the owner as "ugly black-and-white AI photos") to
 * "pixelArt" (colorful 16-bit RPG sprite style, aligned with the project's
 * pixel UI transformation plan). Each archetype still gets a unique, stable
 * portrait derived from its seed.
 *
 * If a more "NFT / CryptoPunks" vibe is ever wanted later, swap
 * `pixelArt` for `bottts` (robot heads) or `thumbs` (minimalist tokens).
 */

import { useMemo } from "react";
import { createAvatar } from "@dicebear/core";
import { pixelArt } from "@dicebear/collection";

interface AvatarPreviewProps {
  seed: string;
  size?: number;
  className?: string;
  style?: React.CSSProperties;
}

export function AvatarPreview({ seed, size = 48, className = "", style: cssStyle }: AvatarPreviewProps) {
  const svgDataUrl = useMemo(() => {
    const avatar = createAvatar(pixelArt, {
      seed: seed || "default",
      size: 128,
      backgroundColor: ["transparent"],
      // Slight saturation boost — the default palette looks washed-out on
      // dark-theme cards; these knobs give sharper, more readable portraits.
      scale: 90,
    });
    return `data:image/svg+xml;utf8,${encodeURIComponent(avatar.toString())}`;
  }, [seed]);

  return (
    <img
      src={svgDataUrl}
      alt="Avatar"
      width={size}
      height={size}
      // `render-pixel` applies image-rendering: pixelated + crisp-edges,
      // which is crucial for pixel-art — without it, browsers smooth the
      // sprite and it loses its 16-bit look.
      className={`render-pixel ${className}`.trim()}
      style={cssStyle}
      draggable={false}
    />
  );
}
