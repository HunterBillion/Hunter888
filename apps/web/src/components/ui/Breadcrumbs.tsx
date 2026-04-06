"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronRight, Home } from "lucide-react";

/**
 * Route → Russian label mapping.
 * Supports static and dynamic segments.
 */
const ROUTE_LABELS: Record<string, string> = {
  home: "Главная",
  training: "Тренировка",
  dashboard: "Панель управления",
  analytics: "Аналитика",
  clients: "Клиенты",
  leaderboard: "Рейтинг",
  history: "История",
  settings: "Настройки",
  profile: "Профиль",
  notifications: "Уведомления",
  reports: "Отчёты",
  pvp: "PvP Арена",
  admin: "Администрирование",
  onboarding: "Онбординг",
  results: "Результаты",
  duplicates: "Дубликаты",
  pipeline: "Воронка",
  graph: "Граф связей",
  "audit-log": "Журнал аудита",
  knowledge: "База знаний",
};

function getLabel(segment: string): string {
  return ROUTE_LABELS[segment] || decodeURIComponent(segment);
}

interface BreadcrumbsProps {
  className?: string;
}

/**
 * Auto-generated breadcrumbs from URL path.
 * Renders Home icon → segment links → current page (non-clickable).
 */
export function Breadcrumbs({ className = "" }: BreadcrumbsProps) {
  const pathname = usePathname();

  // Don't show on root pages
  if (!pathname || pathname === "/" || pathname === "/home") return null;

  const segments = pathname.split("/").filter(Boolean);
  if (segments.length === 0) return null;

  // Build crumbs: [{href, label}]
  const crumbs = segments.map((seg, i) => ({
    href: "/" + segments.slice(0, i + 1).join("/"),
    label: getLabel(seg),
    isLast: i === segments.length - 1,
    // UUIDs and IDs — show shortened version
    isId: /^[0-9a-f-]{8,}$/i.test(seg),
  }));

  return (
    <nav
      aria-label="Навигация"
      className={`flex items-center gap-1 font-mono text-xs overflow-hidden ${className}`}
    >
      <Link
        href="/home"
        className="shrink-0 p-0.5 rounded transition-colors"
        style={{ color: "var(--text-muted)" }}
        aria-label="Главная"
      >
        <Home size={12} />
      </Link>

      {crumbs.map((crumb) => (
        <span key={crumb.href} className="flex items-center gap-1 min-w-0">
          <ChevronRight size={10} className="shrink-0" style={{ color: "var(--border-color)" }} />
          {crumb.isLast ? (
            <span
              className="truncate"
              style={{ color: "var(--text-primary)" }}
              aria-current="page"
            >
              {crumb.isId ? `#${crumb.label.slice(0, 8)}` : crumb.label}
            </span>
          ) : (
            <Link
              href={crumb.href}
              className="truncate transition-colors"
              style={{ color: "var(--text-muted)" }}
            >
              {crumb.isId ? `#${crumb.label.slice(0, 8)}` : crumb.label}
            </Link>
          )}
        </span>
      ))}
    </nav>
  );
}
