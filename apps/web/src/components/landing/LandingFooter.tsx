"use client";

import Link from "next/link";
import { XHunterLogo } from "@/components/ui/XHunterLogo";
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
      <div
        className="mx-auto px-5 sm:px-8 md:px-12 pt-14 pb-10"
        style={{ maxWidth: "var(--app-shell-max)" }}
      >
        {/* Main grid — 5 columns on desktop, items-start for baseline alignment */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-10 md:gap-8 items-start">

          {/* ── Brand column ─────────────────────────────────── */}
          <div className="col-span-2 md:col-span-2">
            <Link href="/" className="inline-block mb-4 transition-opacity hover:opacity-85">
              <XHunterLogo size="lg" />
            </Link>
            <p className="text-sm leading-relaxed max-w-[280px] mb-5" style={{ color: "var(--text-secondary)" }}>
              AI-платформа обучения менеджеров через диалоговые симуляции с нейросетевыми клиентами.
              60 сценариев. 100 архетипов. 10 слоёв скоринга.
            </p>

            {/* Status */}
            <div className="flex items-center gap-1.5 mb-4">
              <div className="w-1.5 h-1.5 rounded-full" style={{ background: "var(--success)" }} />
              <span className="text-xs" style={{ color: "var(--text-muted)" }}>Все системы работают</span>
            </div>

            {/* Social links */}
            <div className="flex items-center gap-3">
              <a href="https://t.me/xhunter_platform" target="_blank" rel="noopener noreferrer" className="w-8 h-8 rounded-lg flex items-center justify-center transition-colors" style={{ background: "var(--input-bg)", color: "var(--text-muted)" }} aria-label="Telegram">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/></svg>
              </a>
              <a href="https://vk.com/xhunter_platform" target="_blank" rel="noopener noreferrer" className="w-8 h-8 rounded-lg flex items-center justify-center transition-colors" style={{ background: "var(--input-bg)", color: "var(--text-muted)" }} aria-label="VK">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M15.684 0H8.316C1.592 0 0 1.592 0 8.316v7.368C0 22.408 1.592 24 8.316 24h7.368C22.408 24 24 22.408 24 15.684V8.316C24 1.592 22.391 0 15.684 0zm3.692 17.123h-1.744c-.66 0-.862-.525-2.049-1.714-1.033-1.01-1.49-1.135-1.744-1.135-.356 0-.458.102-.458.593v1.575c0 .424-.135.678-1.253.678-1.846 0-3.896-1.118-5.335-3.202C4.624 10.857 4 8.555 4 8.15c0-.254.102-.491.593-.491h1.744c.44 0 .61.203.78.677.863 2.49 2.303 4.675 2.896 4.675.22 0 .322-.102.322-.66V9.721c-.068-1.186-.695-1.287-.695-1.71 0-.204.17-.407.44-.407h2.744c.373 0 .508.203.508.643v3.473c0 .372.17.508.271.508.22 0 .407-.136.813-.542 1.253-1.406 2.149-3.574 2.149-3.574.119-.254.322-.491.763-.491h1.744c.525 0 .644.27.525.643-.22 1.017-2.354 4.031-2.354 4.031-.186.305-.254.44 0 .78.186.254.796.779 1.203 1.253.745.847 1.32 1.558 1.473 2.049.17.49-.085.744-.576.744z"/></svg>
              </a>
            </div>
          </div>

          {/* ── Product column ────────────────────────────────── */}
          <div>
            <h4
              className="font-display text-xs font-bold tracking-wider uppercase mb-2 pb-2"
              style={{
                color: "var(--text-primary)",
                borderBottom: "2px solid var(--accent)",
                display: "inline-block",
              }}
            >
              Продукт
            </h4>
            <div className="h-3" />
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
            <h4
              className="font-display text-xs font-bold tracking-wider uppercase mb-2 pb-2"
              style={{
                color: "var(--text-primary)",
                borderBottom: "2px solid var(--accent)",
                display: "inline-block",
              }}
            >
              Компания
            </h4>
            <div className="h-3" />
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
            <h4
              className="font-display text-xs font-bold tracking-wider uppercase mb-2 pb-2"
              style={{
                color: "var(--text-primary)",
                borderBottom: "2px solid var(--accent)",
                display: "inline-block",
              }}
            >
              Документы
            </h4>
            <div className="h-3" />
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
                <span className="text-xs leading-tight" style={{ color: "var(--text-muted)" }}>
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
