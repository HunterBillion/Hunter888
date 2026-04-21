"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowRight, Menu, X as XIcon } from "lucide-react";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { XHunterLogo } from "@/components/ui/XHunterLogo";

const NAV_LINKS = [
  { href: "/", label: "ГЛАВНАЯ" },
  { href: "/product", label: "О ПРОДУКТЕ" },
  { href: "/pricing", label: "ТАРИФЫ" },
] as const;

interface LandingNavbarProps {
  onLogin: () => void;
  onRegister: () => void;
}

export function LandingNavbar({ onLogin, onRegister }: LandingNavbarProps) {
  const pathname = usePathname();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <header className="fixed top-0 left-0 right-0 z-[100]" role="banner">
      {/* Glass background — uses CSS var for light/dark adaptation */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background: "var(--header-bg)",
          backdropFilter: "blur(20px) saturate(1.6)",
          WebkitBackdropFilter: "blur(20px) saturate(1.6)",
          borderBottom: "1px solid var(--header-border)",
          boxShadow: "var(--header-shadow)",
        }}
      />

      {/* 3-zone grid — alignItems guarantees vertical centering.
          2026-04-20: убрано maxWidth на navbar. Было жалоба: на широких
          экранах логотип и CTA-кнопки "уходят в центр" вместе с контейнером.
          Теперь navbar растягивается на 100 % viewport — логотип у левого
          края, кнопки у правого. Центральные nav-links всё равно
          центрируются grid'ом. */}
      <div
        className="relative z-10 grid h-16 sm:h-[72px] w-full px-6 sm:px-10 lg:px-14"
        style={{
          gridTemplateColumns: "1fr auto 1fr",
          alignItems: "center",
        }}
      >
        {/* Left: Logo */}
        <div className="justify-self-start">
          <Link href="/" className="transition-opacity hover:opacity-85">
            <XHunterLogo size="lg" />
          </Link>
        </div>

        {/* Center: Nav links — perfectly centered (desktop) */}
        <nav
          className="hidden md:flex items-center gap-8 justify-self-center"
          aria-label="Основная навигация"
        >
          {NAV_LINKS.map(({ href, label }) => {
            const isActive = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                className="font-display text-[15px] font-semibold uppercase transition-colors duration-200"
                aria-current={isActive ? "page" : undefined}
                style={{
                  letterSpacing: "0.05em",
                  lineHeight: "1",
                  color: isActive ? "var(--accent)" : "var(--text-muted)",
                  borderBottom: isActive ? "2px solid var(--accent)" : "2px solid transparent",
                  paddingBottom: "4px",
                }}
              >
                {label}
              </Link>
            );
          })}
        </nav>

        {/* Center: mobile placeholder (keeps grid alignment) */}
        <div className="md:hidden" />

        {/* Right: Actions */}
        <div className="flex items-center justify-self-end gap-2 sm:gap-4">
          <ThemeToggle />
          <button
            onClick={onLogin}
            className="hidden sm:block text-[15px] font-semibold uppercase transition-colors"
            style={{ letterSpacing: "0.05em", color: "var(--text-muted)" }}
          >
            ВОЙТИ
          </button>
          <motion.button
            onClick={onRegister}
            className="hidden sm:flex px-5 sm:px-6 py-2 rounded-lg text-[15px] font-bold uppercase transition-transform items-center gap-1"
            style={{ letterSpacing: "0.05em", background: "var(--accent)", color: "white" }}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.95 }}
          >
            НАЧАТЬ <ArrowRight size={14} />
          </motion.button>

          {/* Mobile hamburger */}
          <button
            className="md:hidden w-10 h-10 flex items-center justify-center rounded-lg"
            style={{ background: "var(--bg-tertiary)", border: "1px solid var(--border-color)" }}
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            aria-label={mobileMenuOpen ? "Закрыть меню" : "Открыть меню"}
            aria-expanded={mobileMenuOpen}
          >
            {mobileMenuOpen ? <XIcon size={18} style={{ color: "var(--text-primary)" }} /> : <Menu size={18} style={{ color: "var(--text-primary)" }} />}
          </button>
        </div>
      </div>

      {/* Mobile menu dropdown */}
      <AnimatePresence>
        {mobileMenuOpen && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.2 }}
            className="md:hidden relative z-10 px-6 pb-6"
            style={{
              background: "var(--header-bg)",
              backdropFilter: "blur(20px) saturate(1.6)",
              WebkitBackdropFilter: "blur(20px) saturate(1.6)",
              borderBottom: "1px solid var(--header-border)",
            }}
          >
            <nav className="flex flex-col gap-1" aria-label="Мобильная навигация">
              {NAV_LINKS.map(({ href, label }) => {
                const isActive = pathname === href;
                return (
                  <Link
                    key={href}
                    href={href}
                    onClick={() => setMobileMenuOpen(false)}
                    className="font-display text-sm font-medium tracking-tight py-3 px-4 rounded-lg transition-colors"
                    aria-current={isActive ? "page" : undefined}
                    style={{
                      color: isActive ? "var(--accent)" : "var(--text-muted)",
                      background: isActive ? "var(--accent-muted)" : "transparent",
                    }}
                  >
                    {label}
                  </Link>
                );
              })}
              <div className="h-px my-2" style={{ background: "var(--border-color)" }} />
              <div className="flex gap-3">
                <button
                  onClick={() => { setMobileMenuOpen(false); onLogin(); }}
                  className="flex-1 py-3 rounded-lg text-sm font-medium"
                  style={{ border: "1px solid var(--border-color)", color: "var(--text-muted)" }}
                >
                  ВОЙТИ
                </button>
                <button
                  onClick={() => { setMobileMenuOpen(false); onRegister(); }}
                  className="flex-1 py-3 rounded-lg text-sm font-bold"
                  style={{ background: "var(--accent)", color: "white" }}
                >
                  НАЧАТЬ
                </button>
              </div>
            </nav>
          </motion.div>
        )}
      </AnimatePresence>
    </header>
  );
}
