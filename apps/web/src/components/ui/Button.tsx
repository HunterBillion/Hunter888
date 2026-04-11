"use client";

import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { motion, type HTMLMotionProps } from "framer-motion";
import { Loader2 } from "lucide-react";
import Link from "next/link";

type Variant = "primary" | "secondary" | "danger" | "ghost" | "success";
type Size = "sm" | "md" | "lg" | "xl";

interface ButtonBaseProps {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: ReactNode;
  iconRight?: ReactNode;
  /** Render as Next.js Link */
  href?: string;
  /** Full-width */
  fluid?: boolean;
}

type ButtonProps = ButtonBaseProps &
  Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> & {
    children?: ReactNode;
  };

const SIZE_CLASSES: Record<Size, string> = {
  sm: "px-3 py-1.5 text-xs gap-1.5",
  md: "px-5 py-2.5 text-sm gap-2",
  lg: "px-7 py-3 text-sm gap-2",
  xl: "px-8 py-4 text-base gap-3",
};

function variantStyles(variant: Variant) {
  switch (variant) {
    case "primary":
      return {
        background: "var(--accent)",
        color: "#fff",
        border: "1px solid var(--accent)",
        "--btn-hover-bg": "var(--accent)",
        "--btn-hover-shadow": "0 0 20px var(--accent-glow)",
      } as React.CSSProperties;
    case "secondary":
      return {
        background: "var(--glass-bg)",
        color: "var(--text-primary)",
        border: "1px solid var(--accent)",
        backdropFilter: "blur(12px)",
        "--btn-hover-bg": "var(--accent-muted)",
        "--btn-hover-shadow": "0 0 20px var(--accent-glow)",
      } as React.CSSProperties;
    case "danger":
      return {
        background: "var(--glass-bg)",
        color: "var(--danger)",
        border: "1px solid var(--danger)",
        backdropFilter: "blur(12px)",
        "--btn-hover-bg": "rgba(229, 72, 77, 0.12)",
        "--btn-hover-shadow": "0 0 20px rgba(229, 72, 77, 0.25)",
      } as React.CSSProperties;
    case "success":
      return {
        background: "var(--glass-bg)",
        color: "var(--success)",
        border: "1px solid var(--success)",
        backdropFilter: "blur(12px)",
        "--btn-hover-bg": "rgba(61, 220, 132, 0.12)",
        "--btn-hover-shadow": "0 0 20px rgba(61, 220, 132, 0.25)",
      } as React.CSSProperties;
    case "ghost":
      return {
        background: "transparent",
        color: "var(--text-muted)",
        border: "1px solid transparent",
        "--btn-hover-bg": "var(--input-bg)",
        "--btn-hover-shadow": "none",
      } as React.CSSProperties;
  }
}

/**
 * Unified Button component for the entire platform.
 *
 * Replaces all `btn-neon` / `btn-neon--danger` / `btn-neon--green` usages.
 *
 * Variants:
 *   primary   — filled accent (CTA, submit, start)
 *   secondary — outlined accent (default, most buttons)
 *   danger    — outlined red (delete, abort)
 *   success   — outlined green (confirm, save)
 *   ghost     — transparent (cancel, dismiss, tertiary actions)
 *
 * Usage:
 *   <Button variant="primary" icon={<Sparkles size={16} />}>Начать</Button>
 *   <Button variant="danger" loading={deleting}>Удалить</Button>
 *   <Button href="/training" variant="secondary">К тренировкам</Button>
 */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = "secondary",
    size = "md",
    loading = false,
    icon,
    iconRight,
    href,
    fluid = false,
    disabled,
    className = "",
    children,
    style,
    ...rest
  },
  ref
) {
  const baseClass = [
    "inline-flex items-center justify-center font-bold tracking-wide uppercase rounded-xl",
    "transition-all duration-200 cursor-pointer select-none",
    "disabled:opacity-40 disabled:cursor-not-allowed disabled:pointer-events-none",
    SIZE_CLASSES[size],
    fluid ? "w-full" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  const mergedStyle = { ...variantStyles(variant), ...style };

  const content = (
    <>
      {loading ? <Loader2 size={size === "sm" ? 14 : 16} className="animate-spin" /> : icon}
      {children}
      {!loading && iconRight}
    </>
  );

  // Link variant
  if (href && !disabled && !loading) {
    return (
      <Link href={href} className={baseClass} style={mergedStyle}>
        {content}
      </Link>
    );
  }

  return (
    <motion.button
      ref={ref as React.Ref<HTMLButtonElement>}
      className={baseClass}
      style={mergedStyle}
      disabled={disabled || loading}
      whileHover={!disabled && !loading ? { scale: 1.02, boxShadow: (mergedStyle as Record<string, string>)["--btn-hover-shadow"] } : undefined}
      whileTap={!disabled && !loading ? { scale: 0.97 } : undefined}
      {...(rest as HTMLMotionProps<"button">)}
    >
      {content}
    </motion.button>
  );
});
