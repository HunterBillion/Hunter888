"use client";

import Link from "next/link";
import {
  Brain,
  Swords,
  BarChart3,
  Users,
  BookOpen,
  Shield,
  FileText,
  Mail,
  ExternalLink,
} from "lucide-react";

const PRODUCT_LINKS = [
  { href: "/product", label: "ИИ-Тренировки", icon: Brain },
  { href: "/product", label: "10-слойный скоринг", icon: BarChart3 },
  { href: "/product", label: "PvP-Арена", icon: Swords },
  { href: "/product", label: "CRM-модуль", icon: Users },
  { href: "/product", label: "База знаний 127-ФЗ", icon: BookOpen },
] as const;

const COMPANY_LINKS = [
  { href: "/pricing", label: "Тарифы" },
  { href: "/product", label: "О платформе" },
  { href: "mailto:support@xhunter.io", label: "Поддержка", external: true },
] as const;

const LEGAL_LINKS = [
  { href: "/consent", label: "Согласие на обработку данных" },
] as const;

export function LandingFooter() {
  return (
    <footer
      className="relative z-10 border-t"
      style={{ borderColor: "var(--border-color)", background: "var(--bg-secondary)" }}
    >
      <div className="max-w-7xl mx-auto px-5 sm:px-8 md:px-12 pt-14 pb-10">
        {/* Main grid — 5 columns on desktop */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-10 md:gap-8">

          {/* ── Brand column ─────────────────────────────────── */}
          <div className="col-span-2 md:col-span-2">
            <Link href="/" className="inline-flex items-center gap-1 mb-4 group">
              <span className="font-display font-black text-2xl" style={{ color: "var(--accent)" }}>X</span>
              <span className="font-display font-black text-sm tracking-[0.16em]" style={{ color: "var(--text-primary)" }}> HUNTER</span>
            </Link>
            <p className="text-sm leading-relaxed max-w-[280px] mb-5" style={{ color: "var(--text-secondary)" }}>
              AI-платформа обучения менеджеров через диалоговые симуляции с нейросетевыми клиентами.
              60 сценариев. 100 архетипов. 10 слоёв скоринга.
            </p>

            {/* Status */}
            <div className="flex items-center gap-1.5">
              <div className="w-1.5 h-1.5 rounded-full" style={{ background: "var(--success)" }} />
              <span className="text-xs" style={{ color: "var(--text-muted)" }}>Все системы работают</span>
            </div>
          </div>

          {/* ── Product column ────────────────────────────────── */}
          <div>
            <h4 className="font-display text-xs font-bold tracking-[0.2em] uppercase mb-5" style={{ color: "var(--text-primary)" }}>
              Продукт
            </h4>
            <ul className="space-y-3">
              {PRODUCT_LINKS.map(({ href, label, icon: Icon }) => (
                <li key={label}>
                  <Link
                    href={href}
                    className="flex items-center gap-2 text-sm transition-colors hover:text-[var(--accent)]"
                    style={{ color: "var(--text-muted)" }}
                  >
                    <Icon size={13} className="flex-shrink-0 opacity-50" />
                    {label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* ── Company column ────────────────────────────────── */}
          <div>
            <h4 className="font-display text-xs font-bold tracking-[0.2em] uppercase mb-5" style={{ color: "var(--text-primary)" }}>
              Компания
            </h4>
            <ul className="space-y-3">
              {COMPANY_LINKS.map(({ href, label, ...rest }) => {
                const isExternal = "external" in rest && rest.external;
                return (
                  <li key={label}>
                    {isExternal ? (
                      <a
                        href={href}
                        className="flex items-center gap-1.5 text-sm transition-colors hover:text-[var(--accent)]"
                        style={{ color: "var(--text-muted)" }}
                      >
                        {label}
                        <ExternalLink size={10} className="opacity-40" />
                      </a>
                    ) : (
                      <Link
                        href={href}
                        className="text-sm transition-colors hover:text-[var(--accent)]"
                        style={{ color: "var(--text-muted)" }}
                      >
                        {label}
                      </Link>
                    )}
                  </li>
                );
              })}
            </ul>

            {/* Contact */}
            <div className="mt-6 pt-4" style={{ borderTop: "1px solid var(--border-color)" }}>
              <a
                href="mailto:hello@xhunter.io"
                className="flex items-center gap-2 text-sm transition-colors hover:text-[var(--accent)]"
                style={{ color: "var(--text-muted)" }}
              >
                <Mail size={13} className="opacity-50" />
                hello@xhunter.io
              </a>
            </div>
          </div>

          {/* ── Legal column ──────────────────────────────────── */}
          <div>
            <h4 className="font-display text-xs font-bold tracking-[0.2em] uppercase mb-5" style={{ color: "var(--text-primary)" }}>
              Документы
            </h4>
            <ul className="space-y-3">
              {LEGAL_LINKS.map(({ href, label }) => (
                <li key={label}>
                  <Link
                    href={href}
                    className="flex items-center gap-2 text-sm transition-colors hover:text-[var(--accent)]"
                    style={{ color: "var(--text-muted)" }}
                  >
                    <FileText size={13} className="flex-shrink-0 opacity-50" />
                    {label}
                  </Link>
                </li>
              ))}
            </ul>

            {/* Security badge */}
            <div className="mt-6 pt-4" style={{ borderTop: "1px solid var(--border-color)" }}>
              <div className="flex items-center gap-2">
                <Shield size={14} style={{ color: "var(--success)", opacity: 0.7 }} />
                <span className="text-[10px] leading-tight" style={{ color: "var(--text-muted)" }}>
                  152-ФЗ / 127-ФЗ<br />Compliance
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* ── Bottom bar ─────────────────────────────────────── */}
        <div
          className="mt-12 pt-6 flex flex-col sm:flex-row items-center justify-between gap-4 border-t"
          style={{ borderColor: "var(--border-color)" }}
        >
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            © {new Date().getFullYear()} X Hunter. Все права защищены.
          </p>
        </div>
      </div>
    </footer>
  );
}
