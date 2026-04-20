"use client";

/**
 * Pixel-art decoration primitives for ChapterMap.
 *
 * Everything is inline SVG with shape-rendering=crispEdges so it stays
 * pixel-crisp at any zoom level. Each epoch gets its own palette & prop
 * (see EPOCH_PALETTES). We intentionally avoid raster assets so the map
 * stays a single component file and renders instantly.
 */

export type EpochId = 1 | 2 | 3 | 4;

export const EPOCH_PALETTES: Record<
  EpochId,
  { sky: string; ground: string; accent: string; prop: "tree" | "pine" | "stone" | "obelisk" }
> = {
  1: { sky: "#A4E4A6", ground: "#5FA861", accent: "#FFD700", prop: "tree" },       // spring meadow
  2: { sky: "#7FBB8E", ground: "#2D6A3E", accent: "#FF9500", prop: "pine" },       // deep forest
  3: { sky: "#9AA6B8", ground: "#5C6A7D", accent: "#D4AF37", prop: "stone" },      // mountain pass
  4: { sky: "#5B3A7E", ground: "#2F1E4D", accent: "#A855F7", prop: "obelisk" },    // mystical dusk
};

/** 16×24 deciduous tree (crown + trunk) — Эпоха I. */
function Tree({ size = 24 }: { size?: number }) {
  return (
    <svg
      viewBox="0 0 16 24"
      width={size}
      height={(size * 24) / 16}
      shapeRendering="crispEdges"
      aria-hidden
    >
      {/* crown */}
      <rect x="4" y="1" width="8" height="2" fill="#3B8F3E" />
      <rect x="2" y="3" width="12" height="3" fill="#4CAF50" />
      <rect x="1" y="6" width="14" height="4" fill="#66BB6A" />
      <rect x="2" y="10" width="12" height="3" fill="#4CAF50" />
      <rect x="4" y="13" width="8" height="2" fill="#3B8F3E" />
      {/* highlights */}
      <rect x="5" y="5" width="2" height="2" fill="#A5D6A7" />
      <rect x="9" y="7" width="2" height="2" fill="#A5D6A7" />
      {/* trunk */}
      <rect x="7" y="15" width="2" height="6" fill="#6D4C2E" />
      <rect x="6" y="21" width="4" height="2" fill="#4E342E" />
    </svg>
  );
}

/** 14×24 pine — Эпоха II. */
function Pine({ size = 24 }: { size?: number }) {
  return (
    <svg viewBox="0 0 14 24" width={size} height={(size * 24) / 14} shapeRendering="crispEdges" aria-hidden>
      <rect x="6" y="0" width="2" height="2" fill="#2E5E34" />
      <rect x="5" y="2" width="4" height="2" fill="#2E5E34" />
      <rect x="4" y="4" width="6" height="2" fill="#3B7F3F" />
      <rect x="3" y="6" width="8" height="2" fill="#3B7F3F" />
      <rect x="2" y="8" width="10" height="2" fill="#4CAF50" />
      <rect x="4" y="10" width="6" height="2" fill="#2E5E34" />
      <rect x="3" y="12" width="8" height="2" fill="#3B7F3F" />
      <rect x="1" y="14" width="12" height="2" fill="#4CAF50" />
      <rect x="5" y="16" width="4" height="2" fill="#2E5E34" />
      <rect x="6" y="18" width="2" height="4" fill="#6D4C2E" />
      <rect x="5" y="22" width="4" height="2" fill="#4E342E" />
    </svg>
  );
}

/** 16×14 rock — Эпоха III. */
function Stone({ size = 22 }: { size?: number }) {
  return (
    <svg viewBox="0 0 16 14" width={size} height={(size * 14) / 16} shapeRendering="crispEdges" aria-hidden>
      <rect x="3" y="5" width="10" height="2" fill="#788393" />
      <rect x="2" y="7" width="12" height="3" fill="#8893A3" />
      <rect x="1" y="10" width="14" height="3" fill="#5C6A7D" />
      <rect x="5" y="7" width="2" height="2" fill="#A0AEC0" />
      <rect x="10" y="8" width="2" height="2" fill="#A0AEC0" />
      <rect x="0" y="13" width="16" height="1" fill="#3B4554" />
    </svg>
  );
}

/** 10×26 mystical obelisk — Эпоха IV. */
function Obelisk({ size = 26 }: { size?: number }) {
  return (
    <svg viewBox="0 0 10 26" width={(size * 10) / 26} height={size} shapeRendering="crispEdges" aria-hidden>
      <rect x="4" y="0" width="2" height="2" fill="#E9D5FF" />
      <rect x="3" y="2" width="4" height="18" fill="#7E3AF2" />
      <rect x="4" y="2" width="1" height="18" fill="#B282FF" />
      <rect x="5" y="2" width="1" height="18" fill="#5B21B6" />
      <rect x="2" y="20" width="6" height="2" fill="#5B21B6" />
      <rect x="1" y="22" width="8" height="2" fill="#3D1470" />
      <rect x="0" y="24" width="10" height="2" fill="#2F1E4D" />
      <rect x="4" y="6" width="2" height="2" fill="#E9D5FF" />
      <rect x="4" y="12" width="2" height="2" fill="#E9D5FF" />
    </svg>
  );
}

/** Small 6×8 flower — can be sprinkled anywhere on grass. */
function Flower({ size = 10, color = "#FFD700" }: { size?: number; color?: string }) {
  return (
    <svg viewBox="0 0 6 8" width={size} height={(size * 8) / 6} shapeRendering="crispEdges" aria-hidden>
      <rect x="2" y="0" width="2" height="2" fill={color} />
      <rect x="0" y="2" width="2" height="2" fill={color} />
      <rect x="4" y="2" width="2" height="2" fill={color} />
      <rect x="2" y="2" width="2" height="2" fill="#FFFFFF" />
      <rect x="2" y="4" width="2" height="4" fill="#3B8F3E" />
    </svg>
  );
}

interface DecorProps {
  epoch: EpochId;
  locked?: boolean;
}

/**
 * Decor row for an epoch section — paints the ground as a CSS gradient
 * plus a handful of pixel props scattered along the horizon. Absolute-
 * positioned so it never interferes with the chapter cards' layout.
 */
export default function ChapterMapDecor({ epoch, locked = false }: DecorProps) {
  const palette = EPOCH_PALETTES[epoch];
  const Prop =
    palette.prop === "tree"
      ? Tree
      : palette.prop === "pine"
      ? Pine
      : palette.prop === "stone"
      ? Stone
      : Obelisk;

  // Fixed positions so layout stays deterministic between renders.
  const leftProps = [
    { top: 10, size: 22 },
    { top: 120, size: 26 },
    { top: 240, size: 20 },
  ];
  const rightProps = [
    { top: 60, size: 24 },
    { top: 180, size: 22 },
  ];
  const flowers = [
    { top: 50, left: "30%", color: palette.accent },
    { top: 140, left: "65%", color: palette.accent },
    { top: 220, left: "22%", color: "#FFFFFF" },
  ];

  return (
    <div
      aria-hidden
      className="pointer-events-none absolute inset-0 overflow-hidden"
      style={{
        opacity: locked ? 0.2 : 0.55,
      }}
    >
      {/* sky → ground band at the bottom of the section */}
      <div
        className="absolute inset-x-0 bottom-0"
        style={{
          height: "48%",
          background: `linear-gradient(180deg, transparent 0%, color-mix(in srgb, ${palette.sky} 40%, transparent) 20%, color-mix(in srgb, ${palette.ground} 55%, transparent) 100%)`,
        }}
      />
      {/* horizon line */}
      <div
        className="absolute inset-x-0"
        style={{
          bottom: "42%",
          height: 2,
          background: `color-mix(in srgb, ${palette.ground} 60%, transparent)`,
        }}
      />

      {leftProps.map((p, i) => (
        <div
          key={`l-${i}`}
          className="absolute"
          style={{ top: p.top, left: 4 + (i % 2) * 10, filter: locked ? "grayscale(0.7)" : "none" }}
        >
          <Prop size={p.size} />
        </div>
      ))}

      {rightProps.map((p, i) => (
        <div
          key={`r-${i}`}
          className="absolute"
          style={{ top: p.top, right: 4 + (i % 2) * 10, filter: locked ? "grayscale(0.7)" : "none" }}
        >
          <Prop size={p.size} />
        </div>
      ))}

      {epoch <= 2 &&
        flowers.map((f, i) => (
          <div
            key={`f-${i}`}
            className="absolute"
            style={{ top: f.top, left: f.left, filter: locked ? "grayscale(0.7)" : "none" }}
          >
            <Flower color={f.color} />
          </div>
        ))}
    </div>
  );
}
