"use client";

/**
 * /admin — admin hub.
 *
 * Shows what each admin tab actually does, so the panel doesn't feel like
 * an empty landing. Tiles point to the SAME tabs as the layout's tab bar
 * (no methodologist redirects, no orphan routes, no "Скоро" placeholders
 * that aren't backed by code).
 */

import Link from "next/link";
import {
  Users,
  Activity,
  ListChecks,
  BookOpen,
} from "lucide-react";

type IconComp = React.ComponentType<{ size?: number; style?: React.CSSProperties }>;

interface Tile {
  href: string;
  label: string;
  sub: string;
  icon: IconComp;
}

const TILES: Tile[] = [
  {
    href: "/admin/users",
    label: "Пользователи",
    sub: "Список менеджеров, РОПов, методологов · фильтр по роли",
    icon: Users,
  },
  {
    href: "/admin/client-domain",
    label: "Клиентский домен",
    sub: "Здоровье · парити · self-test · репейр · §12 follow-ups",
    icon: Activity,
  },
  {
    href: "/admin/audit-log",
    label: "Журнал аудита",
    sub: "152-ФЗ: кто/что/когда менял в CRM",
    icon: ListChecks,
  },
  {
    href: "/admin/wiki",
    label: "Wiki менеджеров",
    sub: "Дашборд статей и черновиков",
    icon: BookOpen,
  },
];

export default function AdminHubPage() {
  return (
    <div className="max-w-4xl">
      <p
        className="text-sm mb-5 max-w-2xl"
        style={{ color: "var(--text-muted)" }}
      >
        Полный доступ ко всему: 152-ФЗ аудит, реестр пользователей, операционная
        консоль клиентского домена. Эти разделы видны только роли{" "}
        <code>admin</code>.
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {TILES.map((t) => {
          const Icon = t.icon;
          return (
            <Link
              key={t.href}
              href={t.href}
              className="rounded-xl p-4 transition-all hover:-translate-y-0.5 hover:shadow-lg"
              style={{
                background: "var(--bg-panel)",
                border: "1px solid #fbbf2433",
              }}
            >
              <div className="flex items-center gap-3 mb-2">
                <div
                  className="flex h-10 w-10 items-center justify-center rounded-xl"
                  style={{
                    background: "#fbbf2418",
                    color: "#fbbf24",
                    border: "1px solid #fbbf2444",
                  }}
                >
                  <Icon size={18} />
                </div>
                <div className="flex-1 min-w-0">
                  <div
                    className="text-[13px] font-semibold"
                    style={{ color: "var(--text-primary)" }}
                  >
                    {t.label}
                  </div>
                </div>
              </div>
              <p
                className="text-[12px] leading-relaxed"
                style={{ color: "var(--text-muted)" }}
              >
                {t.sub}
              </p>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
