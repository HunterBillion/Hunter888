"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import {
  CheckCircle2,
  Zap,
  Globe,
  Handshake,
  Plus,
} from "lucide-react";
import { useLandingAuth } from "@/components/landing/LandingAuthContext";

/* ── Constants ────────────────────────────────────────────────────── */
const PRICING_TIERS = [
  {
    id: "scout",
    label: "Scout",
    name: "Разведчик",
    badge: "14 дней бесплатно",
    features: [
      "Базовые сценарии — холодные, тёплые, входящие",
      "Анализ темпа речи и пауз после каждого звонка",
      "Проверка по 5 ключевым параметрам",
      "Тест знаний по 127-ФЗ",
    ],
    cta: "Попробовать бесплатно",
    featured: false,
  },
  {
    id: "hunter",
    label: "Hunter",
    name: "Полный цикл",
    badge: "Самый популярный",
    features: [
      "Все 60 сценариев — давление, кризис, торги",
      "100 типов клиентов — от скептика до манипулятора",
      "Полная проверка по 10 параметрам + ловушки",
      "PvP-арена с рейтингом и голосовой режим",
    ],
    cta: "Начать тренировки",
    featured: true,
  },
  {
    id: "api",
    label: "Enterprise",
    name: "Для команд",
    badge: "Индивидуально",
    features: [
      "CRM-модуль — ведите клиентов прямо в платформе",
      "Создавайте свои сценарии под ваш бизнес",
      "Дашборд руководителя — видите прогресс команды",
      "Выделенный методолог и приоритетная поддержка",
    ],
    cta: "Связаться с нами",
    featured: false,
  },
] as const;

/* ── Partner SVG Logos (monochrome white) ─────────────────────────── */
const GCPLogo = () => (
  <svg width="40" height="40" viewBox="0 0 24 24" fill="currentColor">
    <path d="M12.19 2.38a9.344 9.344 0 0 0-9.234 6.893c.053-.02-.055.013 0 0-3.875 2.551-3.922 8.11-.247 10.941l.006-.007-.007.003a6.542 6.542 0 0 0 3.624 1.12h.984l.164-.001V18.59h-1.148a3.86 3.86 0 0 1-2.155-.657c-2.398-1.747-2.18-5.453.407-6.839l.756-.405.348-.762a6.66 6.66 0 0 1 6.501-4.272 6.672 6.672 0 0 1 4.213 1.755l1.28-1.275A9.343 9.343 0 0 0 12.19 2.38zm7.614 4.397c-.203.332-1.252 1.31-1.252 1.31.476.654.787 1.336 1.01 2.092l.032.141.103.323a6.697 6.697 0 0 1-.115 4.18l-.108.295-.159.378.383.746c2.507 1.498 2.453 5.031.15 6.738a3.862 3.862 0 0 1-2.37.746H15.23v2.73h2.248a6.553 6.553 0 0 0 4.044-1.414c3.55-2.755 3.68-8.108.277-10.653l-.003-.002.006.003a9.315 9.315 0 0 0-1.997-7.513zM8.088 12.25a3.913 3.913 0 1 0 7.826 0 3.913 3.913 0 0 0-7.826 0z" />
  </svg>
);
const AWSLogo = () => (
  <svg width="40" height="28" viewBox="0 0 60 36" fill="currentColor">
    <path d="M17.1 12.3c0 .8.1 1.4.3 1.9s.4.9.8 1.4c.1.1.1.3.1.4 0 .2-.1.3-.3.5l-1 .7c-.1.1-.3.1-.4.1-.2 0-.3-.1-.5-.2-.3-.4-.6-.7-.8-1.1-.2-.4-.4-.8-.7-1.3-1.7 2-3.8 3-6.4 3-1.8 0-3.3-.5-4.3-1.5S2.4 14 2.4 12.5c0-1.6.6-3 1.7-3.9 1.2-1 2.7-1.5 4.7-1.5.7 0 1.3 0 2 .1s1.4.2 2.1.4V6.2c0-1.4-.3-2.4-.9-3-.6-.6-1.6-.9-3.1-.9-.7 0-1.3.1-2 .2s-1.4.4-2 .6c-.3.1-.5.2-.6.2-.2 0-.2-.1-.2-.4V2c0-.2 0-.4.1-.5.1-.1.2-.2.4-.3.7-.3 1.5-.6 2.4-.8C8 .2 9 .1 10 .1c2.3 0 4 .5 5.1 1.6 1.1 1 1.6 2.6 1.6 4.7V12.3h.4zM7.8 15.4c.6 0 1.3-.1 2-.4.7-.2 1.3-.7 1.8-1.3.3-.4.5-.8.6-1.3.1-.5.2-1.1.2-1.8V9.7c-.5-.1-1.1-.2-1.7-.3-.6-.1-1.2-.1-1.8-.1-1.3 0-2.2.2-2.8.7-.7.5-1 1.2-1 2.2 0 .9.2 1.6.7 2.1.5.4 1.2.7 2 .7V15.4z" />
    <path d="M26.5 17.1c-.2 0-.4-.1-.5-.2-.1-.1-.2-.3-.3-.6L21 1.5c-.1-.3-.2-.5-.2-.6 0-.2.1-.4.4-.4h1.6c.3 0 .4.1.5.2.1.1.2.3.3.6l3.3 13.1L30.3 1.3c.1-.3.2-.5.3-.6.1-.1.3-.2.5-.2h1.3c.3 0 .4.1.5.2.1.1.2.3.3.6l3.5 13.3L40.1 1.3c.1-.3.2-.5.3-.6.1-.1.3-.2.5-.2h1.5c.2 0 .4.1.4.4 0 .1 0 .2-.1.3 0 .1-.1.2-.1.4l-4.9 14.8c-.1.3-.2.5-.3.6-.1.1-.3.2-.5.2h-1.4c-.2 0-.4-.1-.5-.2-.1-.1-.2-.3-.3-.6l-3.4-12.8-3.4 12.8c-.1.3-.2.5-.3.6-.1.1-.3.2-.5.2h-1.4l-.2-.1z" />
    <path d="M50.5 17.4c-1 0-2.1-.1-3-.4-1-.3-1.7-.6-2.2-1-.3-.2-.5-.4-.5-.6 0-.2.1-.4.2-.4.1-.1.2-.1.4-.1.1 0 .3 0 .5.1.9.4 1.8.7 2.7.9s1.7.3 2.6.3c1.4 0 2.4-.2 3.1-.7s1.1-1.2 1.1-2c0-.6-.2-1.1-.6-1.5-.4-.4-1.1-.7-2.2-1l-3.1-.8c-1.6-.4-2.8-1-3.5-1.8-.7-.8-1.1-1.7-1.1-2.8 0-.8.2-1.5.5-2.2.4-.6.8-1.2 1.4-1.6.6-.4 1.3-.8 2.1-1 .8-.2 1.7-.3 2.6-.3.5 0 .9 0 1.4.1.5.1.9.1 1.4.2.4.1.8.2 1.2.4.4.1.6.3.8.4.2.1.3.3.4.4.1.1.1.3.1.5v.8c0 .2-.1.4-.2.4-.1.1-.3.1-.5.1-.2 0-.5-.1-.8-.2-1.2-.5-2.5-.8-3.9-.8-1.2 0-2.2.2-2.8.6-.6.4-.9 1.1-.9 2 0 .6.2 1.1.7 1.5.4.4 1.2.8 2.4 1.1l3 .8c1.6.4 2.7 1 3.4 1.7.7.7 1 1.6 1 2.7 0 .8-.2 1.5-.5 2.2-.4.6-.8 1.2-1.4 1.6-.6.4-1.3.8-2.2 1-.9.2-1.8.4-2.8.4l-.1-.3z" />
    <path d="M56.7 28.2c-6.7 5-16.4 7.6-24.7 7.6-11.7 0-22.2-4.3-30.2-11.5-.6-.6-.1-1.3.7-.9 8.6 5 19.2 8 30.2 8 7.4 0 15.5-1.5 23-4.7 1.1-.5 2.1.7 1 1.5z" />
    <path d="M59.4 25.1c-.9-1.1-5.7-.5-7.8-.3-.7.1-.8-.5-.2-.9 3.9-2.7 10.2-1.9 10.9-1 .8.9-.2 7.2-3.8 10.2-.6.5-1.1.2-.9-.4.8-2.1 2.7-6.5 1.8-7.6z" />
  </svg>
);
const AzureLogo = () => (
  <svg width="40" height="40" viewBox="0 0 24 24" fill="currentColor">
    <path d="M5.483 6.063H12.3l-6.03 9.22-.005.015L3.21 21.188H.023L5.483 6.063zm3.315 5.98l5.12-5.98h5.103L9.74 21.188H3.463l5.335-9.145z" />
  </svg>
);
const CloudflareLogo = () => (
  <svg width="40" height="40" viewBox="0 0 24 24" fill="currentColor">
    <path d="M16.51 17.93l.36-1.25c.1-.34.07-.64-.08-.87-.14-.2-.37-.33-.64-.36l-8.36-.42a.18.18 0 0 1-.15-.1.18.18 0 0 1 .01-.18c.04-.06.1-.1.17-.11l8.45-.43c.68-.04 1.42-.58 1.68-1.24l.37-1.02a.33.33 0 0 0 .01-.2 5.82 5.82 0 0 0-11.2-.7A3.46 3.46 0 0 0 2.4 13.5 3.5 3.5 0 0 0 2.47 17h13.78c.1 0 .19-.03.26-.07z" />
    <path d="M19.34 12.04c-.08 0-.16 0-.24.01a.18.18 0 0 0-.15.13l-.25.87c-.1.34-.07.64.08.87.14.2.37.33.64.36l1.78.09c.07 0 .13.05.15.1a.18.18 0 0 1-.01.18c-.04.06-.1.1-.17.11l-1.86.1c-.68.03-1.42.57-1.68 1.23l-.1.3c-.03.08.02.17.11.17H22a2.51 2.51 0 0 0-2.66-4.42z" />
  </svg>
);
const MongoDBLogo = () => (
  <svg width="40" height="40" viewBox="0 0 24 24" fill="currentColor">
    <path d="M17.193 9.555c-1.264-5.58-4.252-7.414-4.573-8.115-.28-.394-.53-.954-.735-1.44-.036.495-.055.685-.523 1.184-.723.566-4.438 3.682-4.74 10.02-.282 5.912 4.27 9.435 4.888 9.884l.07.05A73.49 73.49 0 0 1 11.91 24h.481c.114-1.032.284-2.056.51-3.07.417-.296.604-.463.604-.463-.036-1.137-.003-2.97 1.693-5.963.835-1.468 1.86-3.37 1.995-4.949z" />
    <path d="M12.553 24c.054-.535.138-1.07.247-1.6l-.007-.025s-.083-.064-.222-.186c-.01-.008-.016-.019-.027-.027-.019-.017-.049-.034-.069-.051l.006.006-.003-.008A73.49 73.49 0 0 0 12.09 24h.463z" opacity=".6" />
  </svg>
);

const PARTNERS = [
  { name: "Google Cloud", Logo: GCPLogo },
  { name: "AWS", Logo: AWSLogo },
  { name: "Microsoft Azure", Logo: AzureLogo },
  { name: "Cloudflare", Logo: CloudflareLogo },
  { name: "MongoDB", Logo: MongoDBLogo },
] as const;

/* ── Comparison features ──────────────────────────────────────────── */
const COMPARISON = [
  { name: "Сценарии", scout: "20+", hunter: "Все 60", enterprise: "Кастомные" },
  { name: "Типы клиентов", scout: "Базовые", hunter: "Все 100", enterprise: "Все 100 + свои" },
  { name: "Параметров оценки", scout: "5", hunter: "10", enterprise: "10 + кастомные" },
  { name: "Голосовой режим", scout: "—", hunter: "Да", enterprise: "Да" },
  { name: "PvP-арена", scout: "—", hunter: "Да", enterprise: "Да" },
  { name: "CRM-модуль", scout: "—", hunter: "—", enterprise: "Да" },
  { name: "Дашборд руководителя", scout: "—", hunter: "—", enterprise: "Да" },
  { name: "Методолог", scout: "—", hunter: "—", enterprise: "Выделенный" },
] as const;

/* ── Pricing Section with billing toggle ─────────────────────────── */
function PricingSection({ openRegister }: { openRegister: () => void }) {
  const [annual, setAnnual] = useState(false);

  const prices = {
    scout: annual ? "3 900 ₽" : "4 900 ₽",
    hunter: annual ? "15 900 ₽" : "19 900 ₽",
  };

  return (
    <section className="px-5 sm:px-8 pb-24 sm:pb-32 max-w-7xl mx-auto">
      {/* Billing toggle */}
      <div className="flex items-center justify-center gap-4 mb-10">
        <span className="text-sm font-medium" style={{ color: annual ? "var(--text-muted)" : "var(--text-primary)" }}>Месяц</span>
        <button
          onClick={() => setAnnual(!annual)}
          className="relative w-14 h-7 rounded-full transition-colors"
          style={{ background: annual ? "var(--accent)" : "var(--border-color)" }}
        >
          <div
            className="absolute top-1 w-5 h-5 rounded-full bg-white transition-all"
            style={{ left: annual ? "calc(100% - 24px)" : "4px" }}
          />
        </button>
        <span className="text-sm font-medium" style={{ color: annual ? "var(--text-primary)" : "var(--text-muted)" }}>
          Год <span className="text-xs font-bold ml-1" style={{ color: "var(--neon-green)" }}>-20%</span>
        </span>
      </div>

      {/* Tier cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-16">
        {PRICING_TIERS.map((tier, i) => (
          <motion.div
            key={tier.id}
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.1, duration: 0.6 }}
            className={`group relative rounded-xl p-8 transition-all overflow-hidden ${tier.featured ? "md:scale-105 z-10" : ""}`}
            style={{
              background: tier.featured ? "var(--bg-tertiary)" : "var(--bg-panel)",
              border: tier.featured ? "1px solid var(--accent)" : "1px solid var(--border-color)",
            }}
          >
            {tier.featured && (
              <div className="absolute top-0 left-0 right-0 text-center py-1 text-xs font-bold uppercase tracking-wide" style={{ background: "var(--accent)", color: "white" }}>
                Самый популярный
              </div>
            )}

            <div className={`relative z-10 ${tier.featured ? "pt-4" : ""}`}>
              <h3 className="text-base font-bold tracking-wide uppercase mb-2" style={{ color: tier.featured ? "var(--accent)" : "var(--text-muted)" }}>
                {tier.label}
              </h3>

              {/* Price */}
              {tier.id !== "api" ? (
                <div className="mb-1">
                  <span className="text-3xl sm:text-4xl font-black" style={{ color: "var(--text-primary)" }}>
                    {tier.id === "scout" ? prices.scout : prices.hunter}
                  </span>
                  <span className="text-sm ml-1" style={{ color: "var(--text-muted)" }}>/мес</span>
                </div>
              ) : (
                <div className="text-2xl font-black mb-1" style={{ color: "var(--text-primary)" }}>По запросу</div>
              )}

              <div className={`text-sm mb-6 ${tier.featured ? "italic" : ""}`} style={{ color: "var(--text-muted)" }}>
                {tier.badge}
              </div>

              <ul className="space-y-3 mb-8">
                {tier.features.map((f) => (
                  <li key={f} className="flex items-start gap-3 text-sm sm:text-base" style={{ color: tier.featured ? "var(--text-primary)" : "var(--text-secondary)" }}>
                    {tier.featured
                      ? <Zap size={16} className="mt-1 flex-shrink-0" style={{ color: "var(--accent)" }} />
                      : <CheckCircle2 size={16} className="mt-1 flex-shrink-0" style={{ color: "var(--neon-green)" }} />
                    }
                    {f}
                  </li>
                ))}
              </ul>

              <motion.button
                className="w-full py-3.5 rounded-lg font-bold text-sm transition-all"
                style={tier.featured
                  ? { background: "var(--accent)", color: "white" }
                  : { background: "transparent", border: "1px solid var(--border-color)", color: "var(--text-primary)" }
                }
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                onClick={openRegister}
              >
                {tier.cta}
              </motion.button>
            </div>
          </motion.div>
        ))}
      </div>

      {/* Comparison table */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        className="rounded-xl overflow-hidden"
        style={{ background: "var(--bg-panel)", border: "1px solid var(--border-color)" }}
      >
        <div className="px-6 py-4" style={{ borderBottom: "1px solid var(--border-color)" }}>
          <h3 className="font-display font-bold text-lg" style={{ color: "var(--text-primary)" }}>Сравнение планов</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border-color)" }}>
                <th className="text-left px-6 py-3 font-medium" style={{ color: "var(--text-muted)" }}>Возможность</th>
                <th className="text-center px-4 py-3 font-bold" style={{ color: "var(--text-secondary)" }}>Scout</th>
                <th className="text-center px-4 py-3 font-bold" style={{ color: "var(--accent)" }}>Hunter</th>
                <th className="text-center px-4 py-3 font-bold" style={{ color: "var(--text-secondary)" }}>Enterprise</th>
              </tr>
            </thead>
            <tbody>
              {COMPARISON.map((row, i) => (
                <tr key={row.name} style={{ borderBottom: i < COMPARISON.length - 1 ? "1px solid var(--border-color)" : "none" }}>
                  <td className="px-6 py-3 font-medium" style={{ color: "var(--text-primary)" }}>{row.name}</td>
                  <td className="text-center px-4 py-3" style={{ color: String(row.scout) === "—" ? "var(--text-muted)" : "var(--text-secondary)" }}>{row.scout}</td>
                  <td className="text-center px-4 py-3 font-medium" style={{ color: String(row.hunter) === "—" ? "var(--text-muted)" : "var(--accent)" }}>{row.hunter}</td>
                  <td className="text-center px-4 py-3" style={{ color: String(row.enterprise) === "—" ? "var(--text-muted)" : "var(--text-secondary)" }}>{row.enterprise}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </motion.div>
    </section>
  );
}

/* ═══════════════════════════ PAGE ═════════════════════════════════ */
export default function PricingPage() {
  const { openRegister } = useLandingAuth();

  return (
    <div
      className="relative min-h-screen"
      style={{ background: "var(--bg-primary)", paddingTop: "96px" }}
    >
      {/* Geometric grid bg */}
      <div
        className="fixed inset-0 opacity-[0.02] pointer-events-none"
        style={{
          backgroundImage: `linear-gradient(to right, var(--text-muted) 1px, transparent 1px),
                            linear-gradient(to bottom, var(--text-muted) 1px, transparent 1px)`,
          backgroundSize: "40px 40px",
        }}
      />

      <div className="relative z-10">
        {/* ── Hero ─────────────────────────────────────────────── */}
        <section className="py-20 sm:py-28 px-5 sm:px-8 max-w-7xl mx-auto text-center">
          <motion.h1
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            className="font-display font-black tracking-tighter uppercase mb-6"
            style={{ fontSize: "clamp(2.5rem, 7vw, 5.5rem)", color: "var(--text-primary)" }}
          >
            Выберите <span className="italic" style={{ color: "var(--accent)" }}>свой</span> план
          </motion.h1>
          <motion.p
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="max-w-2xl mx-auto text-base sm:text-lg md:text-xl"
            style={{ color: "var(--text-secondary)" }}
          >
            Начните с бесплатных 14 дней. Никаких скрытых условий — отмена в любой момент.
            Выберите план, который подходит вашей команде.
          </motion.p>
        </section>

        {/* ── Pricing Grid ─────────────────────────────────────── */}
        <PricingSection openRegister={openRegister} />

        {/* ── Partners ─────────────────────────────────────────── */}
        <section className="py-20 sm:py-24" style={{ background: "var(--bg-secondary)", borderTop: "1px solid var(--border-color)", borderBottom: "1px solid var(--border-color)" }}>
          <div className="px-5 sm:px-8 max-w-7xl mx-auto">
            <div className="flex flex-col md:flex-row gap-12 md:gap-16 items-start">
              <div className="w-full md:w-1/3">
                <motion.h2
                  initial={{ opacity: 0, y: 20 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  className="font-display font-black tracking-tight uppercase mb-6"
                  style={{ fontSize: "clamp(1.8rem, 3vw, 2.5rem)", color: "var(--text-primary)" }}
                >
                  Инфраструктура
                </motion.h2>
                <p className="text-sm leading-relaxed mb-8" style={{ color: "var(--text-secondary)" }}>
                  X Hunter работает на ведущих облачных платформах.
                  Ваши данные защищены, сервис доступен 99.9% времени, серверы в нескольких регионах.
                </p>
                <div className="space-y-4">
                  <div className="p-4 rounded-lg flex gap-4" style={{ background: "var(--bg-panel)", border: "1px solid var(--border-color)" }}>
                    <Globe size={20} style={{ color: "var(--accent)", flexShrink: 0, marginTop: 2 }} />
                    <div>
                      <h4 className="font-bold text-sm uppercase" style={{ color: "var(--text-primary)" }}>Глобальный Доступ</h4>
                      <p className="text-xs" style={{ color: "var(--text-muted)" }}>Доступ к закрытым базам данных партнёров.</p>
                    </div>
                  </div>
                  <div className="p-4 rounded-lg flex gap-4" style={{ background: "var(--bg-panel)", border: "1px solid var(--border-color)" }}>
                    <Handshake size={20} style={{ color: "var(--accent)", flexShrink: 0, marginTop: 2 }} />
                    <div>
                      <h4 className="font-bold text-sm uppercase" style={{ color: "var(--text-primary)" }}>Реферальный Бонус</h4>
                      <p className="text-xs" style={{ color: "var(--text-muted)" }}>До 20% комиссии за каждого приглашённого клиента.</p>
                    </div>
                  </div>
                </div>
              </div>

              <div className="w-full md:w-2/3 grid grid-cols-2 md:grid-cols-3 gap-4">
                {PARTNERS.map(({ name, Logo }) => (
                  <div
                    key={name}
                    className="aspect-square rounded-xl flex flex-col items-center justify-center p-6 sm:p-8 group transition-all opacity-50 grayscale hover:opacity-100 hover:grayscale-0"
                    style={{ background: "var(--bg-panel)", border: "1px solid var(--border-color)", color: "var(--text-muted)" }}
                  >
                    <div className="mb-4 transition-colors group-hover:text-white">
                      <Logo />
                    </div>
                    <span className="text-[10px] font-bold tracking-widest uppercase text-center transition-colors group-hover:text-white">
                      {name}
                    </span>
                  </div>
                ))}
                <div
                  className="aspect-square rounded-xl flex flex-col items-center justify-center p-6 sm:p-8 cursor-pointer transition-all group hover:border-accent"
                  style={{ background: "var(--bg-panel)", border: "1px solid var(--accent-muted)" }}
                >
                  <Plus size={36} className="mb-2" style={{ color: "var(--accent)" }} />
                  <span className="text-[10px] font-bold tracking-widest text-center uppercase" style={{ color: "var(--accent)" }}>
                    Стать Партнёром
                  </span>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
