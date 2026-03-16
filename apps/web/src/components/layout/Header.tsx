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
    <header className="border-b border-gray-200 bg-white">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4 sm:px-6">
        <div className="flex items-center gap-8">
          <Link href="/training" className="text-lg font-bold text-gray-900">
            AI Тренажер
          </Link>

          <nav className="hidden items-center gap-1 sm:flex">
            {NAV_ITEMS.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                  isActive(item.href)
                    ? "bg-blue-50 text-blue-700"
                    : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
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
                    ? "bg-blue-50 text-blue-700"
                    : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
                }`}
              >
                {ADMIN_NAV.label}
              </Link>
            )}
          </nav>
        </div>

        <div className="flex items-center gap-4">
          {user && (
            <span className="hidden text-sm text-gray-600 sm:block">
              {user.full_name}
            </span>
          )}
          <button
            onClick={logout}
            className="rounded-md px-3 py-1.5 text-sm font-medium text-gray-600 hover:bg-gray-100 hover:text-gray-900"
          >
            Выйти
          </button>
        </div>
      </div>

      {/* Mobile nav */}
      <nav className="flex border-t border-gray-100 px-4 sm:hidden">
        {NAV_ITEMS.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`flex-1 py-2 text-center text-xs font-medium ${
              isActive(item.href)
                ? "border-b-2 border-blue-600 text-blue-700"
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
                ? "border-b-2 border-blue-600 text-blue-700"
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
