"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  Crosshair,
  User,
  Users,
  LayoutDashboard,
  LogOut,
  Menu,
  X,
  Trophy,
  History,
  Home,
  Settings,
  ChevronDown,
  Swords,
  ShieldCheck,
  FileBarChart,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { sanitizeText } from "@/lib/sanitize";
import { useAuth } from "@/hooks/useAuth";
import { useGamificationStore } from "@/stores/useGamificationStore";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { XPBar } from "@/components/gamification/XPBar";
import { StreakCounter } from "@/components/gamification/StreakCounter";
import { NotificationBell } from "@/components/layout/NotificationBell";
import { UserAvatar } from "@/components/ui/UserAvatar";
import type { UserRole } from "@/types";

type NavItem = { href: string; label: string; icon: typeof Home; roles?: UserRole[] };
type OpenPanel = "none" | "user" | "notifications" | "mobile";

const NAV_ITEMS: NavItem[] = [
  { href: "/home", label: "Центр", icon: Home },
  { href: "/training", label: "Тренировка", icon: Crosshair },
  { href: "/clients", label: "Клиенты", icon: Users, roles: ["admin", "rop", "manager"] },
  { href: "/history", label: "История", icon: History },
  { href: "/leaderboard", label: "Лидерборд", icon: Trophy },
  { href: "/pvp", label: "Арена", icon: Swords },
  { href: "/reports", label: "Отчёты", icon: FileBarChart },
  { href: "/dashboard", label: "Панель РОП", icon: LayoutDashboard, roles: ["rop", "admin"] },
  { href: "/admin/audit-log", label: "Аудит", icon: ShieldCheck, roles: ["admin"] },
];

export default function Header() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuth();
  const [openPanel, setOpenPanel] = useState<OpenPanel>("none");
  const shellRef = useRef<HTMLDivElement>(null);

  const isActive = (href: string) => pathname === href || pathname.startsWith(`${href}/`);
  const userRole = user?.role as UserRole | undefined;
  const navItems = NAV_ITEMS.filter((item) => !item.roles || (userRole && item.roles.includes(userRole)));
  const { level, currentXP, nextLevelXP, streak, fetchProgress } = useGamificationStore();

  useEffect(() => {
    if (user) fetchProgress();
  }, [user, fetchProgress]);

  useEffect(() => {
    setOpenPanel("none");
  }, [pathname]);

  useEffect(() => {
    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (shellRef.current && !shellRef.current.contains(target)) {
        setOpenPanel("none");
      }
    };
    const handleScroll = () => setOpenPanel("none");
    document.addEventListener("mousedown", handlePointerDown);
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      window.removeEventListener("scroll", handleScroll);
    };
  }, []);

  const displayName = sanitizeText(user?.full_name || "Пользователь");
  const roleLabel = user?.role === "admin" ? "Администратор" : user?.role === "rop" ? "РОП" : "Менеджер";
  const userMenuOpen = openPanel === "user";
  const notificationOpen = openPanel === "notifications";
  const mobileOpen = openPanel === "mobile";

  return (
    <header className="sticky top-0 z-30 px-3 py-3 sm:px-4">
      <div
        ref={shellRef}
        className="mx-auto max-w-[1600px] overflow-visible rounded-[30px] border px-4 py-4 sm:px-5"
        style={{
          background: "linear-gradient(180deg, rgba(3,3,6,0.98), rgba(7,7,10,0.94))",
          borderColor: "rgba(255,255,255,0.08)",
          boxShadow: "0 20px 60px rgba(0,0,0,0.42), inset 0 1px 0 rgba(255,255,255,0.04)",
          backdropFilter: "blur(28px)",
          WebkitBackdropFilter: "blur(28px)",
        }}
      >
        <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 lg:grid-cols-[minmax(260px,1fr)_auto_minmax(260px,1fr)]">
          <div className="relative z-20 flex min-w-0 items-center gap-3">
            <div className="relative">
              <motion.button
                onClick={() => setOpenPanel(userMenuOpen ? "none" : "user")}
                className="flex max-w-full items-center gap-2 rounded-[20px] border px-3 py-2"
                style={{
                  borderColor: userMenuOpen ? "rgba(144,92,237,0.45)" : "rgba(255,255,255,0.08)",
                  background: userMenuOpen ? "rgba(144,92,237,0.12)" : "rgba(255,255,255,0.04)",
                }}
                whileTap={{ scale: 0.98 }}
              >
                <UserAvatar avatarUrl={user?.avatar_url} fullName={displayName} size={34} />
                <div className="hidden min-w-0 text-left sm:block">
                  <div className="truncate text-sm font-medium" style={{ color: "#F5F7FB" }}>{displayName}</div>
                  <div className="text-[10px] font-mono uppercase tracking-[0.16em]" style={{ color: "rgba(255,255,255,0.48)" }}>
                    {roleLabel}
                  </div>
                </div>
                <motion.span animate={{ rotate: userMenuOpen ? 180 : 0 }} className="hidden sm:block">
                  <ChevronDown size={14} style={{ color: "rgba(255,255,255,0.62)" }} />
                </motion.span>
              </motion.button>

              <AnimatePresence>
                {userMenuOpen && (
                  <motion.div
                    initial={{ opacity: 0, y: -8, scale: 0.97 }}
                    animate={{ opacity: 1, y: 10, scale: 1 }}
                    exit={{ opacity: 0, y: -8, scale: 0.97 }}
                    transition={{ duration: 0.18 }}
                    className="absolute left-0 top-full z-[80] mt-2 w-[310px] max-w-[calc(100vw-2rem)] overflow-hidden rounded-[24px] border"
                    style={{
                      background: "linear-gradient(180deg, rgba(8,8,12,0.99), rgba(14,16,22,0.97))",
                      borderColor: "rgba(255,255,255,0.08)",
                      boxShadow: "0 24px 60px rgba(0,0,0,0.5)",
                    }}
                  >
                    <div className="px-5 py-4" style={{ borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
                      <div className="flex items-center gap-3">
                        <UserAvatar avatarUrl={user?.avatar_url} fullName={displayName} size={42} />
                        <div className="min-w-0">
                          <div className="truncate text-sm font-semibold" style={{ color: "#F5F7FB" }}>{displayName}</div>
                          <div className="mt-0.5 text-[11px]" style={{ color: "rgba(255,255,255,0.5)" }}>{roleLabel}</div>
                        </div>
                      </div>
                    </div>

                    <div className="px-3 py-3">
                      <motion.button
                        onClick={() => { setOpenPanel("none"); router.push("/profile"); }}
                        className="flex w-full items-center gap-3 rounded-[18px] px-4 py-3 text-sm"
                        style={{ color: "rgba(255,255,255,0.82)" }}
                        whileHover={{ background: "rgba(255,255,255,0.06)" }}
                      >
                        <User size={15} />
                        Профиль
                      </motion.button>
                      <motion.button
                        onClick={() => { setOpenPanel("none"); router.push("/settings"); }}
                        className="mt-1 flex w-full items-center gap-3 rounded-[18px] px-4 py-3 text-sm"
                        style={{ color: "rgba(255,255,255,0.82)" }}
                        whileHover={{ background: "rgba(255,255,255,0.06)" }}
                      >
                        <Settings size={15} />
                        Настройки
                      </motion.button>
                    </div>

                    <div className="px-3 pb-3">
                      <motion.button
                        onClick={() => { setOpenPanel("none"); logout(); }}
                        className="flex w-full items-center gap-3 rounded-[18px] px-4 py-3 text-sm"
                        style={{ color: "#FF889B", background: "rgba(255,42,109,0.08)" }}
                        whileHover={{ background: "rgba(255,42,109,0.14)" }}
                      >
                        <LogOut size={15} />
                        Выйти
                      </motion.button>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>

          <div className="flex items-center justify-center lg:justify-self-center">
            <Link href="/home" className="flex items-end justify-center rounded-[20px] px-2 py-1 text-center">
              <span className="translate-y-[1px] text-[2rem] font-display font-black leading-none sm:text-[2.35rem] lg:text-[2.55rem]" style={{ color: "#B685FF" }}>
                X
              </span>
              <span className="ml-1.5 text-[1.08rem] font-display font-black leading-none tracking-[0.18em] sm:text-[1.28rem] lg:text-[1.45rem]" style={{ color: "#F5F7FB" }}>
                HUNTER
              </span>
            </Link>
          </div>

          <div className="relative z-20 flex items-center justify-end gap-2 sm:gap-3">
            <div className="hidden xl:block w-32">
              <XPBar level={level} currentXP={currentXP} nextLevelXP={nextLevelXP} />
            </div>

            <div className="hidden md:block">
              <StreakCounter streak={streak} />
            </div>

            <div className="flex items-center gap-1 rounded-[20px] border px-2 py-1.5" style={{ borderColor: "rgba(255,255,255,0.07)", background: "rgba(255,255,255,0.03)" }}>
              <ThemeToggle />
              <NotificationBell
                open={notificationOpen}
                onOpenChange={(next) => setOpenPanel(next ? "notifications" : "none")}
              />
            </div>

            <motion.button
              className="xl:hidden flex h-11 w-11 items-center justify-center rounded-[18px] border"
              onClick={() => setOpenPanel(mobileOpen ? "none" : "mobile")}
              style={{ borderColor: "rgba(255,255,255,0.08)", color: "#F5F7FB", background: "rgba(255,255,255,0.03)" }}
              whileTap={{ scale: 0.94 }}
            >
              <AnimatePresence mode="wait">
                {mobileOpen ? (
                  <motion.div key="close" initial={{ rotate: -90, opacity: 0 }} animate={{ rotate: 0, opacity: 1 }} exit={{ rotate: 90, opacity: 0 }}>
                    <X size={20} />
                  </motion.div>
                ) : (
                  <motion.div key="menu" initial={{ rotate: 90, opacity: 0 }} animate={{ rotate: 0, opacity: 1 }} exit={{ rotate: -90, opacity: 0 }}>
                    <Menu size={20} />
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.button>
          </div>
        </div>

        <div className="mt-4 hidden xl:flex items-center justify-center">
          <nav className="flex max-w-full flex-wrap items-center justify-center gap-1 rounded-[24px] border px-2 py-2" style={{ borderColor: "rgba(255,255,255,0.07)", background: "linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.02))" }}>
            {navItems.map((item) => {
              const Icon = item.icon;
              const active = isActive(item.href);
              return (
                <Link key={item.href} href={item.href}>
                  <motion.div
                    className="relative flex items-center gap-2 rounded-[18px] px-4 py-2.5 text-sm font-medium"
                    style={{ color: active ? "#F5F7FB" : "rgba(255,255,255,0.58)" }}
                    whileHover={{ y: -1, color: "#F5F7FB" }}
                    whileTap={{ scale: 0.97 }}
                  >
                    {active && (
                      <motion.div
                        layoutId="nav-active-pill"
                        className="absolute inset-0 rounded-[18px]"
                        style={{
                          background: "linear-gradient(135deg, rgba(144,92,237,0.26), rgba(84,120,255,0.12))",
                          boxShadow: "inset 0 1px 0 rgba(255,255,255,0.04)",
                        }}
                      />
                    )}
                    <span className="relative z-10"><Icon size={16} /></span>
                    <span className="relative z-10">{item.label}</span>
                  </motion.div>
                </Link>
              );
            })}
          </nav>
        </div>
      </div>

      <AnimatePresence>
        {mobileOpen && (
          <motion.nav
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.18 }}
            className="mx-auto mt-3 max-w-[1600px] overflow-hidden rounded-[28px] border xl:hidden"
            style={{
              background: "linear-gradient(180deg, rgba(5,5,8,0.98), rgba(10,12,18,0.96))",
              borderColor: "rgba(255,255,255,0.08)",
              boxShadow: "0 24px 54px rgba(0,0,0,0.42)",
            }}
          >
            <div className="px-4 pb-4 pt-3">
              <div className="mb-3 xl:hidden">
                <XPBar level={level} currentXP={currentXP} nextLevelXP={nextLevelXP} />
              </div>
              {navItems.map((item, index) => {
                const Icon = item.icon;
                const active = isActive(item.href);
                return (
                  <motion.div
                    key={item.href}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: index * 0.03 }}
                  >
                    <Link
                      href={item.href}
                      onClick={() => setOpenPanel("none")}
                      className="mt-1 flex items-center gap-3 rounded-[18px] px-4 py-3 text-sm font-medium"
                      style={{
                        color: active ? "#F5F7FB" : "rgba(255,255,255,0.66)",
                        background: active ? "rgba(144,92,237,0.18)" : "transparent",
                      }}
                    >
                      <Icon size={16} />
                      {item.label}
                    </Link>
                  </motion.div>
                );
              })}
            </div>
          </motion.nav>
        )}
      </AnimatePresence>
    </header>
  );
}
