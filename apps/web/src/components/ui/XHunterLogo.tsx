"use client";

interface XHunterLogoProps {
  size?: "sm" | "md" | "lg";
  className?: string;
}

const SIZES = {
  sm: { x: "text-2xl", hunter: "text-[0.875rem]", gap: "gap-1" },
  md: { x: "text-[3.375rem]", hunter: "text-[1.3rem]", gap: "gap-2" },
  lg: { x: "text-5xl", hunter: "text-[1.4rem]", gap: "gap-2" },
};

export function XHunterLogo({ size = "md", className = "" }: XHunterLogoProps) {
  const s = SIZES[size];
  return (
    <span className={`inline-flex items-baseline ${s.gap} ${className}`}>
      <span
        className={`font-display font-black leading-none ${s.x}`}
        style={{
          color: "var(--accent)",
          textShadow: "0 0 20px var(--accent-glow), 0 0 40px rgba(107, 77, 199, 0.15)",
          WebkitTextStroke: "0.5px rgba(255, 255, 255, 0.08)",
        }}
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
