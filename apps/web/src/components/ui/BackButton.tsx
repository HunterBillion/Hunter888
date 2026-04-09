"use client";

import Link from "next/link";
import { ChevronLeft } from "lucide-react";

interface BackButtonProps {
  href: string;
  label?: string;
}

/**
 * Standardized back navigation button used across all detail/sub-pages.
 * Uses ChevronLeft icon consistently. Place at top-left of page content.
 */
export function BackButton({ href, label = "Назад" }: BackButtonProps) {
  return (
    <Link
      href={href}
      prefetch={true}
      className="inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-sm font-medium transition-all duration-200"
      style={{
        color: "var(--text-muted)",
        background: "transparent",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.color = "var(--text-primary)";
        e.currentTarget.style.background = "var(--header-btn-bg)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.color = "var(--text-muted)";
        e.currentTarget.style.background = "transparent";
      }}
    >
      <ChevronLeft size={16} />
      {label}
    </Link>
  );
}
