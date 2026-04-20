"use client";

/**
 * Admin section layout — adds a shared tab bar above /admin and
 * /admin/audit-log so they feel like two tabs of one "panel" (the way
 * the "КОМАНДА" section already does on /dashboard).
 *
 * The tabs live HERE, not inside each page, so both pages keep their
 * original content untouched. Adding a new admin page is just a matter
 * of adding one line to TABS below.
 *
 * Back-to-team link: admins often flip between team analytics and
 * admin actions — the "← К команде" affordance in the top-right keeps
 * that flow one click.
 */

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { LayoutGrid, ListChecks, ArrowLeft } from "lucide-react";
import AuthLayout from "@/components/layout/AuthLayout";

const TABS = [
  { href: "/admin", label: "Разделы", icon: LayoutGrid, exact: true },
  { href: "/admin/audit-log", label: "Журнал аудита", icon: ListChecks, exact: false },
] as const;

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();

  return (
    <AuthLayout>
      <div className="app-page">
        {/* Section header + tab bar */}
        <div className="mb-6">
          <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
            <div>
              <div
                className="text-[11px] font-pixel uppercase tracking-wider mb-1"
                style={{ color: "var(--accent)", letterSpacing: "0.16em" }}
              >
                Администрирование
              </div>
              <h1
                className="font-display font-bold"
                style={{
                  fontSize: "clamp(1.4rem, 3vw, 1.8rem)",
                  color: "var(--text-primary)",
                }}
              >
                Панель управления
              </h1>
            </div>
            <button
              onClick={() => router.push("/dashboard?tab=team")}
              className="inline-flex items-center gap-1.5 text-xs font-medium uppercase tracking-wider px-3 py-1.5 rounded-md transition hover:bg-[var(--bg-secondary)]"
              style={{
                border: "1px solid var(--border-color)",
                color: "var(--text-secondary)",
              }}
            >
              <ArrowLeft size={13} /> К команде
            </button>
          </div>

          {/* Tab bar — same visual weight as dashboard's tabs so users read
              them as the same pattern. */}
          <div
            className="flex items-center gap-1 rounded-lg p-1 overflow-x-auto"
            style={{
              background: "var(--bg-secondary)",
              border: "1px solid var(--border-color)",
            }}
            role="tablist"
            aria-label="Разделы администрирования"
          >
            {TABS.map(({ href, label, icon: Icon, exact }) => {
              const active = exact
                ? pathname === href
                : pathname === href || pathname.startsWith(`${href}/`);
              return (
                <Link
                  key={href}
                  href={href}
                  role="tab"
                  aria-selected={active}
                  className="relative inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-md whitespace-nowrap transition"
                  style={{
                    color: active ? "white" : "var(--text-secondary)",
                    background: active ? "var(--accent)" : "transparent",
                  }}
                >
                  {active && (
                    <motion.span
                      layoutId="admin-tab-active"
                      className="absolute inset-0 rounded-md"
                      style={{ background: "var(--accent)", zIndex: -1 }}
                      transition={{ type: "spring", stiffness: 400, damping: 30 }}
                    />
                  )}
                  <Icon size={14} />
                  <span>{label}</span>
                </Link>
              );
            })}
          </div>
        </div>

        {/* Active tab content */}
        {children}
      </div>
    </AuthLayout>
  );
}
