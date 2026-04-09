"use client";

import Link from "next/link";
import { ChevronRight } from "lucide-react";

interface BreadcrumbItem {
  label: string;
  href?: string;
}

export function Breadcrumb({ items }: { items: BreadcrumbItem[] }) {
  return (
    <nav aria-label="Навигация" className="flex items-center gap-1.5 text-sm mb-4" style={{ color: "var(--text-muted)" }}>
      {items.map((item, i) => (
        <span key={i} className="flex items-center gap-1.5">
          {i > 0 && <ChevronRight size={14} className="opacity-40" />}
          {item.href ? (
            <Link href={item.href} prefetch={true} className="hover:underline transition-colors" style={{ color: i === items.length - 1 ? "var(--text-primary)" : "var(--text-muted)" }}>
              {item.label}
            </Link>
          ) : (
            <span style={{ color: "var(--text-primary)" }}>{item.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}
