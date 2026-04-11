"use client";

interface XHunterLogoProps {
  size?: "sm" | "md" | "lg";
  className?: string;
}

const SIZES = {
  sm: { x: "text-2xl", hunter: "text-[0.6rem]", gap: "gap-1" },
  md: { x: "text-4xl", hunter: "text-sm", gap: "gap-1.5" },
  lg: { x: "text-5xl", hunter: "text-base", gap: "gap-2" },
};

export function XHunterLogo({ size = "md", className = "" }: XHunterLogoProps) {
  const s = SIZES[size];
  return (
    <span className={`inline-flex items-baseline ${s.gap} ${className}`}>
      <span
        className={`font-display font-black leading-none ${s.x}`}
        style={{ color: "var(--brand-deep)" }}
      >
        X
      </span>
      <span
        className={`font-display font-extrabold leading-none tracking-[0.10em] uppercase ${s.hunter}`}
        style={{ color: "var(--text-primary)" }}
      >
        HUNTER
      </span>
    </span>
  );
}
