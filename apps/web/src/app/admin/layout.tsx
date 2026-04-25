"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import {
  LayoutGrid,
  ListChecks,
  ArrowLeft,
  Activity,
  BookOpen,
  Users,
  Loader2,
  ShieldAlert,
} from "lucide-react";
import AuthLayout from "@/components/layout/AuthLayout";
import { useAuth } from "@/hooks/useAuth";
import { isAdmin } from "@/lib/guards";

const TABS = [
  { href: "/admin", label: "Обзор", icon: LayoutGrid, exact: true },
  { href: "/admin/users", label: "Пользователи", icon: Users, exact: false },
  { href: "/admin/client-domain", label: "Клиентский домен", icon: Activity, exact: false },
  { href: "/admin/audit-log", label: "Журнал аудита", icon: ListChecks, exact: false },
  { href: "/admin/wiki", label: "Wiki", icon: BookOpen, exact: false },
] as const;

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, loading } = useAuth();

  return (
    <AuthLayout>
      <div className="app-page">
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

        {/* Centralized role-guard. Children no longer need their own guard
            — the layout shows ONE consistent denial UI for the whole admin
            section instead of three different patterns scattered across
            /admin/wiki, /admin/audit-log, and /admin/client-domain. */}
        {loading ? (
          <div className="flex items-center gap-2 p-6" style={{ color: "var(--text-muted)" }}>
            <Loader2 size={16} className="animate-spin" />
            Проверка прав…
          </div>
        ) : !user || !isAdmin(user) ? (
          <div
            className="rounded-xl p-6 flex items-start gap-3"
            style={{
              background: "var(--bg-panel)",
              border: "1px solid rgba(239,68,68,0.35)",
            }}
          >
            <ShieldAlert size={20} style={{ color: "#ef4444" }} />
            <div>
              <div className="font-semibold" style={{ color: "var(--text-primary)" }}>
                Доступ ограничен
              </div>
              <div className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
                Эти разделы доступны только роли <code>admin</code>.
              </div>
            </div>
          </div>
        ) : (
          children
        )}
      </div>
    </AuthLayout>
  );
}
