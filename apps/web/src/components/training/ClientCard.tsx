"use client";

import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { sanitizeText } from "@/lib/sanitize";
import {
  User,
  MapPin,
  Briefcase,
  Globe,
  Landmark,
  Wallet,
  Home,
  Phone,
  StickyNote,
  Lock,
  ChevronLeft,
  ArrowRight,
  Loader2,
  DollarSign,
  Building2,
} from "lucide-react";

export interface ClientCardData {
  full_name: string;
  age: number;
  gender: "male" | "female";
  city: string;
  profession: string;
  lead_source: string;
  lead_source_label: string;
  total_debt: number;
  creditors: Array<{ name: string; amount: number }>;
  income: number;
  income_type: "white" | "gray" | "black" | "none";
  property: Array<{ type: string; status: string }>;
  call_history: Array<{ date: string; note: string }>;
  crm_notes: string;
  /** Dynamic trust level from AI engine (0-100) */
  trust_level?: number;
  /** Dynamic resistance level from AI engine (0-100) */
  resistance_level?: number;
}

interface ClientCardProps {
  clientCard: ClientCardData;
  scenarioTitle: string;
  onStart: () => void;
  onBack: () => void;
  loading?: boolean;
}

const fmt = new Intl.NumberFormat("ru-RU");

const incomeTypeLabels: Record<string, string> = {
  white: "Белый",
  gray: "Серый",
  black: "Чёрный",
  none: "Нет дохода",
};

const propertyStatusLabels: Record<string, string> = {
  owned: "В собственности",
  mortgaged: "В ипотеке",
  pledged: "В залоге",
  rented: "Аренда",
};

function CountUp({ value, duration = 1500 }: { value: number; duration?: number }) {
  const [display, setDisplay] = useState(0);
  const startTime = useRef<number | null>(null);
  const rafRef = useRef<number>(0);

  useEffect(() => {
    startTime.current = null;
    const animate = (ts: number) => {
      if (!startTime.current) startTime.current = ts;
      const progress = Math.min((ts - startTime.current) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
      setDisplay(Math.round(eased * value));
      if (progress < 1) {
        rafRef.current = requestAnimationFrame(animate);
      }
    };
    rafRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(rafRef.current);
  }, [value, duration]);

  return <>{fmt.format(display)}</>;
}

function formatDebtShort(v: number): string {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}М`;
  if (v >= 1_000) return `${Math.round(v / 1_000)}К`;
  return fmt.format(v);
}

export function ClientCard({ clientCard, scenarioTitle, onStart, onBack, loading }: ClientCardProps) {
  const creditors = clientCard?.creditors ?? [];
  const property = clientCard?.property ?? [];
  const callHistory = clientCard?.call_history ?? [];
  const maxCreditor = creditors.length > 0 ? Math.max(...creditors.map((c) => c.amount), 1) : 1;

  const container = {
    hidden: { opacity: 0 },
    show: { opacity: 1, transition: { staggerChildren: 0.08 } },
  };
  const item = {
    hidden: { opacity: 0, y: 16 },
    show: { opacity: 1, y: 0 },
  };

  return (
    <div className="flex min-h-screen items-center justify-center p-4 md:p-8" style={{ background: "var(--bg-primary)" }}>
      <motion.div
        variants={container}
        initial="hidden"
        animate="show"
        className="w-full max-w-4xl"
      >
        {/* Header */}
        <motion.div variants={item} className="mb-6">
          <div className="text-xs font-semibold uppercase tracking-wide mb-1" style={{ color: "var(--accent)" }}>
            CRM-КАРТОЧКА КЛИЕНТА
          </div>
          <h1 className="font-display text-2xl md:text-3xl font-bold tracking-wider" style={{ color: "var(--text-primary)" }}>
            {scenarioTitle}
          </h1>
        </motion.div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Profile */}
          <motion.div variants={item} className="glass-panel p-5 md:p-6">
            <h2 className="font-display text-sm font-semibold tracking-widest mb-4 flex items-center gap-2" style={{ color: "var(--text-primary)" }}>
              <User size={16} style={{ color: "var(--accent)" }} />
              ПРОФИЛЬ
            </h2>
            <div className="space-y-3">
              {[
                { icon: User, label: "Имя", value: `${sanitizeText(clientCard.full_name)}, ${clientCard.age} лет` },
                { icon: MapPin, label: "Город", value: clientCard.city },
                { icon: Briefcase, label: "Профессия", value: clientCard.profession },
                { icon: Globe, label: "Источник", value: clientCard.lead_source_label },
              ].map((row) => {
                const Icon = row.icon;
                return (
                  <div key={row.label} className="flex items-center gap-3">
                    <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg" style={{ background: "var(--accent-muted)" }}>
                      <Icon size={12} style={{ color: "var(--accent)" }} />
                    </div>
                    <div>
                      <div className="text-xs font-medium uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>{row.label}</div>
                      <div className="text-sm break-words" style={{ color: "var(--text-primary)" }}>{row.value}</div>
                    </div>
                  </div>
                );
              })}
            </div>
          </motion.div>

          {/* Finances */}
          <motion.div variants={item} className="glass-panel p-5 md:p-6">
            <h2 className="font-display text-sm font-semibold tracking-widest mb-4 flex items-center gap-2" style={{ color: "var(--text-primary)" }}>
              <Landmark size={16} style={{ color: "var(--accent)" }} />
              ФИНАНСЫ
            </h2>

            {/* Total debt */}
            <div className="rounded-xl p-4 mb-4" style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)" }}>
              <div className="text-xs font-semibold uppercase tracking-wide mb-1" style={{ color: "var(--text-muted)" }}>ОБЩИЙ ДОЛГ</div>
              <div className="font-display text-3xl font-bold" style={{ color: "var(--danger)" }}>
                <CountUp value={clientCard.total_debt} /> <span className="text-sm font-normal" style={{ color: "var(--text-muted)" }}>₽</span>
              </div>
            </div>

            {/* Creditors bar chart */}
            {creditors.length > 0 && (
              <div className="mb-4">
                <div className="text-xs font-semibold uppercase tracking-wide mb-2" style={{ color: "var(--text-muted)" }}>КРЕДИТОРЫ</div>
                <div className="space-y-2">
                  {creditors.map((c, i) => (
                    <div key={i}>
                      <div className="flex justify-between text-xs mb-0.5">
                        <span style={{ color: "var(--text-secondary)" }}>{c.name}</span>
                        <span className="font-mono" style={{ color: "var(--text-muted)" }}>{formatDebtShort(c.amount)} ₽</span>
                      </div>
                      <div className="h-1.5 rounded-full overflow-hidden" style={{ background: "var(--input-bg)" }}>
                        <motion.div
                          className="h-full rounded-full"
                          style={{ background: i === 0 ? "var(--accent)" : i === 1 ? "var(--magenta)" : "var(--warning)" }}
                          initial={{ width: 0 }}
                          animate={{ width: `${(c.amount / maxCreditor) * 100}%` }}
                          transition={{ duration: 0.8, delay: 0.3 + i * 0.1 }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Income & Property */}
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-lg p-3" style={{ background: "var(--input-bg)" }}>
                <div className="flex items-center gap-1.5 mb-1">
                  <Wallet size={12} style={{ color: "var(--accent)" }} />
                  <span className="text-xs font-medium uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>Доход</span>
                </div>
                <div className="text-sm font-bold" style={{ color: "var(--text-primary)" }}>
                  {clientCard.income > 0 ? `${fmt.format(clientCard.income)} ₽` : "Нет"}
                </div>
                <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
                  {incomeTypeLabels[clientCard.income_type] || clientCard.income_type}
                </div>
              </div>
              <div className="rounded-lg p-3" style={{ background: "var(--input-bg)" }}>
                <div className="flex items-center gap-1.5 mb-1">
                  <Building2 size={12} style={{ color: "var(--accent)" }} />
                  <span className="text-xs font-medium uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>Имущество</span>
                </div>
                {property.length > 0 ? (
                  <div className="space-y-0.5">
                    {property.map((p, i) => (
                      <div key={i} className="text-xs" style={{ color: "var(--text-primary)" }}>
                        {p.type} <span className="text-xs" style={{ color: "var(--text-muted)" }}>({propertyStatusLabels[p.status] || p.status})</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-sm" style={{ color: "var(--text-muted)" }}>Нет</div>
                )}
              </div>
            </div>
          </motion.div>

          {/* Call History */}
          <motion.div variants={item} className="glass-panel p-5 md:p-6">
            <h2 className="font-display text-sm font-semibold tracking-widest mb-4 flex items-center gap-2" style={{ color: "var(--text-primary)" }}>
              <Phone size={16} style={{ color: "var(--accent)" }} />
              ИСТОРИЯ ЗВОНКОВ
            </h2>
            {callHistory.length > 0 ? (
              <div className="relative pl-4">
                {/* Timeline line */}
                <div className="absolute left-0 top-1 bottom-1 w-px" style={{ background: "var(--border-color)" }} />
                <div className="space-y-3">
                  {callHistory.map((call, i) => (
                    <div key={i} className="relative">
                      <div className="absolute -left-4 top-1.5 w-2 h-2 rounded-full" style={{ background: "var(--accent)", boxShadow: "0 0 6px var(--accent-glow)" }} />
                      <div className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>{call.date}</div>
                      <div className="text-sm mt-0.5" style={{ color: "var(--text-secondary)" }}>{sanitizeText(call.note)}</div>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <p className="text-sm" style={{ color: "var(--text-muted)" }}>Первый контакт</p>
            )}
          </motion.div>

          {/* CRM Notes */}
          <motion.div variants={item} className="glass-panel p-5 md:p-6">
            <h2 className="font-display text-sm font-semibold tracking-widest mb-4 flex items-center gap-2" style={{ color: "var(--text-primary)" }}>
              <StickyNote size={16} style={{ color: "var(--accent)" }} />
              ЗАМЕТКИ CRM
            </h2>
            {clientCard.crm_notes ? (
              <p className="text-sm leading-relaxed whitespace-pre-line break-words" style={{ color: "var(--text-secondary)" }}>
                {clientCard.crm_notes}
              </p>
            ) : (
              <p className="text-sm" style={{ color: "var(--text-muted)" }}>Заметок нет</p>
            )}

            {/* Hidden psychotype block */}
            <div
              className="mt-4 rounded-xl p-4 flex items-center gap-3"
              style={{
                background: "var(--input-bg)",
                border: "1px dashed var(--border-color)",
              }}
            >
              <Lock size={16} style={{ color: "var(--text-muted)" }} />
              <div>
                <div className="text-xs font-medium" style={{ color: "var(--text-muted)" }}>
                  Психотип, страхи и ловушки
                </div>
                <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)", opacity: 0.6 }}>
                  Скрыты — определите в процессе тренировки
                </div>
              </div>
            </div>
          </motion.div>
        </div>

        {/* Actions */}
        <motion.div variants={item} className="mt-6 flex flex-col sm:flex-row justify-center gap-3">
          <motion.button
            onClick={onBack}
            className="btn-neon flex items-center justify-center gap-2"
            whileTap={{ scale: 0.97 }}
          >
            <ChevronLeft size={16} /> Назад
          </motion.button>
          <motion.button
            onClick={onStart}
            disabled={loading}
            className="btn-neon flex items-center justify-center gap-2 text-lg px-8 py-4"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
          >
            {loading ? (
              <Loader2 size={20} className="animate-spin" />
            ) : (
              <>
                НАЧАТЬ ТРЕНИРОВКУ <ArrowRight size={18} />
              </>
            )}
          </motion.button>
        </motion.div>
      </motion.div>
    </div>
  );
}
