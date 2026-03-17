"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import type { UserRole } from "@/types";

const NAV_ITEMS = [
  { href: "/training", label: "Тренировка" },
  { href: "/profile", label: "Профиль" },
];

const ADMIN_NAV = { href: "/dashboard", label: "Панель РОП" };
const ADMIN_ROLES: UserRole[] = ["rop", "admin"];

export default function Header() {
  const pathname = usePathname();
  const { user, logout } = useAuth();

  const isActive = (href: string) =>
    pathname === href || pathname.startsWith(href + "/");

  const showAdminNav =
    user?.role && ADMIN_ROLES.includes(user.role as UserRole);

  return (
    <header className="border-b border-white/10 bg-vh-black/90 backdrop-blur-sm">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4 sm:px-6">
        <div className="flex items-center gap-8">
          <Link href="/training" className="text-lg font-display font-bold text-vh-purple tracking-wider">
            VIBEHUNTER
          </Link>

          <nav className="hidden items-center gap-1 sm:flex">
            {NAV_ITEMS.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                  isActive(item.href)
                    ? "bg-vh-purple/20 text-vh-purple"
                    : "text-gray-400 hover:bg-white/5 hover:text-gray-200"
                }`}
              >
                {item.label}
              </Link>
            ))}
            {showAdminNav && (
              <Link
                href={ADMIN_NAV.href}
                className={`rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                  isActive(ADMIN_NAV.href)
                    ? "bg-vh-purple/20 text-vh-purple"
                    : "text-gray-400 hover:bg-white/5 hover:text-gray-200"
                }`}
              >
                {ADMIN_NAV.label}
              </Link>
            )}
          </nav>
        </div>

        <div className="flex items-center gap-4">
          {user && (
            <span className="hidden text-sm text-gray-400 sm:block">
              {user.full_name}
            </span>
          )}
          <button
            onClick={logout}
            className="rounded-md px-3 py-1.5 text-sm font-medium text-gray-400 hover:bg-white/5 hover:text-gray-200 transition-colors"
          >
            Выйти
          </button>
        </div>
      </div>

      {/* Mobile nav */}
      <nav className="flex border-t border-white/5 px-4 sm:hidden">
        {NAV_ITEMS.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`flex-1 py-2 text-center text-xs font-medium ${
              isActive(item.href)
                ? "border-b-2 border-vh-purple text-vh-purple"
                : "text-gray-500"
            }`}
          >
            {item.label}
          </Link>
        ))}
        {showAdminNav && (
          <Link
            href={ADMIN_NAV.href}
            className={`flex-1 py-2 text-center text-xs font-medium ${
              isActive(ADMIN_NAV.href)
                ? "border-b-2 border-vh-purple text-vh-purple"
                : "text-gray-500"
            }`}
          >
            {ADMIN_NAV.label}
          </Link>
        )}
      </nav>
    </header>
  );
}
