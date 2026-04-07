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
  FileBarChart,
  ShieldCheck,
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
  { href: "/clients", label: "Клиенты", icon: Users, roles: ["admin", "rop", "manager", "methodologist"] },
  { href: "/history", label: "История", icon: History },
  { href: "/leaderboard", label: "Лидерборд", icon: Trophy },
  { href: "/pvp", label: "Арена", icon: Swords },
  { href: "/reports", label: "Отчёты", icon: FileBarChart },
  { href: "/dashboard", label: "Панель РОП", icon: LayoutDashboard, roles: ["rop", "admin"] },
  { href: "/admin/wiki", label: "Админ", icon: ShieldCheck, roles: ["admin"] },
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

  // Close panels on outside click (scroll close moved to scroll-shrink listener to reduce listeners)
  useEffect(() => {
    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (shellRef.current && !shellRef.current.contains(target)) {
        setOpenPanel("none");
      }
    };
    document.addEventListener("mousedown", handlePointerDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
    };
  }, []);

  const displayName = sanitizeText(user?.full_name || "Пользователь");
  const roleLabel =
    user?.role === "admin"
      ? "Администратор"
      : user?.role === "rop"
        ? "РОП"
        : user?.role === "methodologist"
          ? "Методолог"
          : "Менеджер";
  const userMenuOpen = openPanel === "user";
  const notificationOpen = openPanel === "notifications";
  const mobileOpen = openPanel === "mobile";

  // Single scroll listener: shrink header + close open panels
  const scrolledRef = useRef(false);
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    let ticking = false;
    const onScroll = () => {
      if (!ticking) {
        ticking = true;
        requestAnimationFrame(() => {
          const isScrolled = window.scrollY > 40;
          if (scrolledRef.current !== isScrolled) {
            scrolledRef.current = isScrolled;
            setScrolled(isScrolled);
          }
          // Close any open panel on scroll
          setOpenPanel("none");
          ticking = false;
        });
      }
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className="sticky top-0 z-30"
      style={{
        paddingTop: scrolled ? "0.375rem" : "0.75rem",
        paddingBottom: scrolled ? "0.375rem" : "0.75rem",
        transition: "padding 0.35s cubic-bezier(0.4,0,0.2,1)",
        willChange: "padding",
      }}
    >
      <div
        ref={shellRef}
        className="app-shell overflow-visible rounded-[30px] border header-inner"
        style={{
          background: "var(--header-bg)",
          borderColor: "var(--header-border)",
          boxShadow: scrolled ? "var(--header-shadow)" : "none",
          backdropFilter: "blur(28px) saturate(1.4)",
          WebkitBackdropFilter: "blur(28px) saturate(1.4)",
          paddingTop: scrolled ? "0.625rem" : "0.875rem",
          paddingBottom: scrolled ? "0.625rem" : "0.875rem",
          transition: "padding 0.35s cubic-bezier(0.4,0,0.2,1), box-shadow 0.35s ease",
          willChange: "padding",
        }}
      >
        <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 lg:grid-cols-[minmax(260px,1fr)_auto_minmax(260px,1fr)]">
          <div className="relative z-20 flex min-w-0 items-center gap-3">
            <div className="relative">
              <motion.button
                onClick={() => setOpenPanel(userMenuOpen ? "none" : "user")}
                className="flex max-w-full items-center gap-2 rounded-[20px] border px-3 py-2 transition-colors duration-200"
                style={{
                  borderColor: userMenuOpen ? "var(--border-hover)" : "var(--header-btn-border)",
                  background: userMenuOpen ? "var(--header-btn-bg)" : "var(--header-btn-bg)",
                  boxShadow: userMenuOpen ? "0 0 0 1px var(--accent-muted)" : undefined,
                }}
                whileTap={{ scale: 0.98 }}
                aria-label="Меню пользователя"
                aria-expanded={userMenuOpen}
              >
                <UserAvatar avatarUrl={user?.avatar_url} fullName={displayName} size={34} />
                <div className="hidden min-w-0 text-left sm:block">
                  <div className="truncate text-sm font-medium" style={{ color: "var(--header-text)" }}>{displayName}</div>
                  <div className="text-xs font-mono uppercase tracking-[0.16em]" style={{ color: "var(--header-text-muted)" }}>
                    {roleLabel}
                  </div>
                </div>
                <motion.span animate={{ rotate: userMenuOpen ? 180 : 0 }} className="hidden sm:block">
                  <ChevronDown size={14} style={{ color: "var(--header-text-muted)" }} />
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
                      background: "var(--header-bg)",
                      borderColor: "var(--header-border)",
                      boxShadow: "var(--header-shadow)",
                      backdropFilter: "blur(28px) saturate(1.4)",
                      WebkitBackdropFilter: "blur(28px) saturate(1.4)",
                    }}
                  >
                    <div className="px-5 py-4" style={{ borderBottom: "1px solid var(--header-border)" }}>
                      <div className="flex items-center gap-3">
                        <UserAvatar avatarUrl={user?.avatar_url} fullName={displayName} size={42} />
                        <div className="min-w-0">
                          <div className="truncate text-sm font-semibold" style={{ color: "var(--header-text)" }}>{displayName}</div>
                          <div className="mt-0.5 text-xs" style={{ color: "var(--header-text-muted)" }}>{roleLabel}</div>
                        </div>
                      </div>
                    </div>

                    <div className="px-3 py-3">
                      <motion.button
                        onClick={() => { setOpenPanel("none"); router.push("/profile"); }}
                        className="flex w-full items-center gap-3 rounded-[18px] px-4 py-3 text-sm"
                        style={{ color: "var(--header-text)" }}
                        whileHover={{ background: "var(--header-btn-bg)" }}
                      >
                        <User size={15} />
                        Профиль
                      </motion.button>
                      <motion.button
                        onClick={() => { setOpenPanel("none"); router.push("/settings"); }}
                        className="mt-1 flex w-full items-center gap-3 rounded-[18px] px-4 py-3 text-sm"
                        style={{ color: "var(--header-text)" }}
                        whileHover={{ background: "var(--header-btn-bg)" }}
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
            <Link
              href="/home"
              className="group flex items-center gap-0 rounded-[20px] px-3 py-1.5 transition-opacity duration-200 hover:opacity-85"
              aria-label="X·HUNTER — Главная"
            >
              {/* X — accent */}
              <span
                className="font-display font-black leading-none tracking-tight"
                style={{
                  fontSize: "clamp(1.6rem, 2.8vw, 2.15rem)",
                  color: "var(--accent)",
                  textShadow: "0 0 28px var(--accent-glow)",
                  lineHeight: 1,
                }}
              >
                X
              </span>
              {/* Separator dot */}
              <span
                className="mx-[3px] font-display font-black"
                style={{
                  fontSize: "clamp(0.9rem, 1.4vw, 1.2rem)",
                  color: "var(--accent)",
                  opacity: 0.6,
                  lineHeight: 1,
                  marginBottom: "1px",
                }}
              >
                ·
              </span>
              {/* HUNTER */}
              <span
                className="font-display font-black leading-none tracking-[0.16em]"
                style={{
                  fontSize: "clamp(1.05rem, 1.8vw, 1.45rem)",
                  color: "var(--header-text)",
                  lineHeight: 1,
                }}
              >
                HUNTER
              </span>
            </Link>
          </div>

          <div className="relative z-20 flex items-center justify-end gap-2 sm:gap-3">
            <div className="hidden lg:block w-32">
              <XPBar level={level} currentXP={currentXP} nextLevelXP={nextLevelXP} />
            </div>

            <div className="hidden md:block">
              <StreakCounter streak={streak} />
            </div>

            <div
              className="flex items-center gap-1 rounded-[20px] border px-2 py-1.5"
              style={{ borderColor: "var(--header-btn-border)", background: "var(--header-btn-bg)" }}
            >
              <ThemeToggle />
              <NotificationBell
                open={notificationOpen}
                onOpenChange={(next) => setOpenPanel(next ? "notifications" : "none")}
              />
            </div>

            <motion.button
              className="lg:hidden flex h-11 w-11 items-center justify-center rounded-[18px] border"
              onClick={() => setOpenPanel(mobileOpen ? "none" : "mobile")}
              style={{ borderColor: "var(--header-btn-border)", color: "var(--header-text)", background: "var(--header-btn-bg)" }}
              whileTap={{ scale: 0.94 }}
              aria-label="Меню навигации"
              aria-expanded={mobileOpen}
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

        <div className="mt-3 hidden lg:flex items-center justify-center">
          <nav
            className="flex max-w-full items-center justify-center gap-1 rounded-[22px] border px-2 py-1.5 overflow-visible"
            style={{
              borderColor: "var(--header-btn-border)",
              background: "var(--header-btn-bg)",
            }}
          >
            {navItems.map((item) => {
              const Icon = item.icon;
              const active = isActive(item.href);
              return (
                <Link key={item.href} href={item.href} prefetch aria-current={active ? "page" : undefined}>
                  <div
                    className="relative flex items-center gap-2 rounded-[16px] px-4 xl:px-5 py-2.5 text-[13px] font-medium whitespace-nowrap transition-colors duration-200"
                    style={{
                      color: active ? "var(--header-text-active)" : "var(--header-text-muted)",
                    }}
                    onMouseEnter={(e) => {
                      if (!active) e.currentTarget.style.color = "var(--header-text-active)";
                    }}
                    onMouseLeave={(e) => {
                      if (!active) e.currentTarget.style.color = "var(--header-text-muted)";
                    }}
                  >
                    {active && (
                      <>
                        <motion.div
                          layoutId="nav-active-pill"
                          className="absolute inset-0 rounded-[16px]"
                          transition={{ type: "spring", stiffness: 400, damping: 35, mass: 0.6 }}
                          style={{
                            background: "var(--header-nav-active-bg)",
                            boxShadow: "var(--header-nav-active-shadow)",
                          }}
                        />
                        <motion.div
                          layoutId="nav-active-glow"
                          className="absolute rounded-full"
                          transition={{ type: "spring", stiffness: 400, damping: 35, mass: 0.6 }}
                          style={{
                            bottom: -4,
                            left: "25%",
                            right: "25%",
                            height: 2,
                            background: "var(--accent)",
                            boxShadow: "0 2px 12px var(--accent-glow)",
                            borderRadius: 1,
                          }}
                        />
                      </>
                    )}
                    <span className="relative z-10 opacity-70 flex items-center"><Icon size={15} /></span>
                    <span className="relative z-10 leading-none">{item.label}</span>
                  </div>
                </Link>
              );
            })}
          </nav>
        </div>
      </div>

      <AnimatePresence>
        {mobileOpen && (
          <>
            {/* Backdrop */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-[28] lg:hidden"
              style={{ background: "rgba(0,0,0,0.3)", backdropFilter: "blur(4px)" }}
              onClick={() => setOpenPanel("none")}
            />
            <motion.nav
              initial={{ opacity: 0, y: -16, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -10, scale: 0.98 }}
              transition={{ type: "spring", stiffness: 400, damping: 30 }}
              className="app-shell mx-auto mt-3 overflow-hidden rounded-[24px] border lg:hidden relative z-[29]"
              style={{
                background: "var(--header-bg)",
                borderColor: "var(--header-border)",
                boxShadow: "var(--header-shadow)",
                backdropFilter: "blur(28px) saturate(1.4)",
                WebkitBackdropFilter: "blur(28px) saturate(1.4)",
              }}
            >
              <div className="px-4 pb-4 pt-3">
                <div className="mb-3 lg:hidden">
                  <XPBar level={level} currentXP={currentXP} nextLevelXP={nextLevelXP} />
                </div>
                <div className="grid grid-cols-2 gap-1.5">
                  {navItems.map((item, index) => {
                    const Icon = item.icon;
                    const active = isActive(item.href);
                    return (
                      <motion.div
                        key={item.href}
                        initial={{ opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: index * 0.025 }}
                      >
                        <Link
                          href={item.href}
                          onClick={() => setOpenPanel("none")}
                          aria-current={active ? "page" : undefined}
                          className="flex items-center gap-2.5 rounded-[16px] px-3.5 py-3 text-[13px] font-medium transition-all duration-200"
                          style={{
                            color: active ? "var(--header-text-active)" : "var(--header-text-muted)",
                            background: active ? "var(--accent-muted)" : "transparent",
                            border: active ? "1px solid rgba(99,102,241,0.2)" : "1px solid transparent",
                          }}
                        >
                          <Icon size={16} style={{ opacity: active ? 1 : 0.6 }} />
                          {item.label}
                        </Link>
                      </motion.div>
                    );
                  })}
                </div>
              </div>
            </motion.nav>
          </>
        )}
      </AnimatePresence>
    </header>
  );
}
