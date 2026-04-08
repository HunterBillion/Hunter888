"use client";

import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, ChevronUp, User, Landmark, Globe, Phone, Lock } from "lucide-react";
import { sanitizeText } from "@/lib/sanitize";
import type { ClientCardData } from "./ClientCard";

interface ClientCardMiniProps {
  clientCard: ClientCardData;
  isExpanded: boolean;
  onToggle: () => void;
}

const fmt = new Intl.NumberFormat("ru-RU");

function formatDebtCompact(v: number): string {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}М`;
  if (v >= 1_000) return `${Math.round(v / 1_000)}К`;
  return fmt.format(v);
}

export function ClientCardMini({ clientCard, isExpanded, onToggle }: ClientCardMiniProps) {
  return (
    <div className="z-30">
      {/* Collapsed bar */}
      <motion.button
        onClick={onToggle}
        aria-expanded={isExpanded}
        aria-label={isExpanded ? "Свернуть карточку клиента" : "Развернуть карточку клиента"}
        className="w-full flex items-center justify-between px-4 py-2 text-xs font-medium tracking-wide transition-colors"
        style={{
          background: "var(--glass-bg)",
          borderBottom: "1px solid var(--glass-border)",
          backdropFilter: "blur(20px)",
        }}
        whileTap={{ scale: 0.995 }}
      >
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5">
            <User size={12} style={{ color: "var(--accent)" }} />
            <span style={{ color: "var(--text-primary)" }}>
              {sanitizeText(clientCard.full_name)}, {clientCard.age}
            </span>
          </div>
          <span style={{ color: "var(--border-color)" }}>|</span>
          <div className="flex items-center gap-1.5">
            <Landmark size={12} style={{ color: "var(--neon-red, #FF3333)" }} />
            <span style={{ color: "var(--neon-red, #FF3333)" }}>
              Долг: {formatDebtCompact(clientCard.total_debt)} ₽
            </span>
          </div>
          <span className="hidden sm:inline" style={{ color: "var(--border-color)" }}>|</span>
          <div className="hidden sm:flex items-center gap-1.5">
            <Globe size={12} style={{ color: "var(--text-muted)" }} />
            <span style={{ color: "var(--text-muted)" }}>{clientCard.lead_source_label}</span>
          </div>
        </div>
        {isExpanded ? (
          <ChevronUp size={14} style={{ color: "var(--text-muted)" }} />
        ) : (
          <ChevronDown size={14} style={{ color: "var(--text-muted)" }} />
        )}
      </motion.button>

      {/* Expanded card */}
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease: "easeInOut" }}
            className="overflow-hidden"
            style={{
              background: "var(--glass-bg)",
              borderBottom: "1px solid var(--glass-border)",
              backdropFilter: "blur(20px)",
            }}
          >
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 p-4">
              {/* Profile summary */}
              <div className="space-y-1.5">
                <div className="text-xs font-semibold uppercase tracking-wide flex items-center gap-1" style={{ color: "var(--accent)" }}>
                  <User size={10} /> ПРОФИЛЬ
                </div>
                <div className="text-xs" style={{ color: "var(--text-secondary)" }}>
                  {clientCard.profession}, {clientCard.city}
                </div>
                <div className="text-xs" style={{ color: "var(--text-muted)" }}>
                  Источник: {clientCard.lead_source_label}
                </div>
              </div>

              {/* Finance summary */}
              <div className="space-y-1.5">
                <div className="text-xs font-semibold uppercase tracking-wide flex items-center gap-1" style={{ color: "var(--accent)" }}>
                  <Landmark size={10} /> ФИНАНСЫ
                </div>
                <div className="text-xs" style={{ color: "var(--text-secondary)" }}>
                  Долг: {fmt.format(clientCard.total_debt)} ₽
                </div>
                <div className="text-xs" style={{ color: "var(--text-muted)" }}>
                  Кредиторов: {clientCard.creditors.length} · Доход: {clientCard.income > 0 ? `${fmt.format(clientCard.income)} ₽` : "нет"}
                </div>
              </div>

              {/* Call history summary */}
              <div className="space-y-1.5">
                <div className="text-xs font-semibold uppercase tracking-wide flex items-center gap-1" style={{ color: "var(--accent)" }}>
                  <Phone size={10} /> ИСТОРИЯ
                </div>
                {clientCard.call_history.length > 0 ? (
                  <div className="text-xs" style={{ color: "var(--text-secondary)" }}>
                    Последний: {clientCard.call_history[0].date}
                    <div className="mt-0.5 truncate" style={{ color: "var(--text-muted)" }}>
                      {clientCard.call_history[0].note}
                    </div>
                  </div>
                ) : (
                  <div className="text-xs" style={{ color: "var(--text-muted)" }}>Первый контакт</div>
                )}
              </div>
            </div>

            {/* Hidden data reminder */}
            <div className="px-4 pb-3 flex items-center gap-2 text-xs" style={{ color: "var(--text-muted)" }}>
              <Lock size={10} />
              Психотип и ловушки скрыты
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
