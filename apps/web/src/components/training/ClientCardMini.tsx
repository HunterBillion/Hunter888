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
        className="w-full flex items-center justify-between gap-3 px-4 text-sm font-medium tracking-wide transition-colors"
        style={{
          minHeight: 48,
          paddingTop: 10,
          paddingBottom: 10,
          background: "var(--glass-bg)",
          borderBottom: "1px solid var(--glass-border)",
          backdropFilter: "blur(20px)",
        }}
        whileTap={{ scale: 0.995 }}
      >
        <div className="flex items-center gap-4 min-w-0">
          <div className="flex items-center gap-2">
            <User size={16} style={{ color: "var(--accent)" }} />
            <span className="truncate" style={{ color: "var(--text-primary)", fontSize: 15 }}>
              {sanitizeText(clientCard.full_name) || "Клиент"}{clientCard.age ? `, ${clientCard.age}` : ""}
            </span>
          </div>
          <span style={{ color: "var(--border-color)" }}>│</span>
          <div className="flex items-center gap-2">
            <Landmark size={16} style={{ color: "var(--danger)" }} />
            <span style={{ color: "var(--danger)", fontSize: 15 }}>
              {formatDebtCompact(clientCard.total_debt)} ₽
            </span>
          </div>
          <span className="hidden sm:inline" style={{ color: "var(--border-color)" }}>│</span>
          <div className="hidden sm:flex items-center gap-2 min-w-0">
            <Globe size={16} style={{ color: "var(--text-muted)" }} />
            <span className="truncate" style={{ color: "var(--text-muted)", fontSize: 14 }}>{clientCard.lead_source_label}</span>
          </div>
        </div>
        {/* 2026-04-18: bigger chevron as per user feedback "кнопка маленькая" */}
        <div
          className="shrink-0 flex items-center justify-center"
          style={{
            width: 36, height: 36,
            border: "1px solid var(--border-color)",
            borderRadius: 0,
            background: "var(--input-bg)",
            color: "var(--accent)",
          }}
        >
          {isExpanded ? <ChevronUp size={22} /> : <ChevronDown size={22} />}
        </div>
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
              {/* Profile summary — 2026-04-18 fixes:
                  • full_name + age on top (was hidden — caused ", Владимир" bug when profession empty)
                  • Join non-empty pieces (no leading/trailing comma)
                  • Bumped to text-sm for middle-aged readability */}
              <div className="space-y-2">
                <div className="text-sm font-semibold uppercase tracking-wide flex items-center gap-1.5" style={{ color: "var(--accent)" }}>
                  <User size={12} /> ПРОФИЛЬ
                </div>
                <div className="text-base font-medium" style={{ color: "var(--text-primary)" }}>
                  {sanitizeText(clientCard.full_name) || "Клиент"}
                  {clientCard.age ? `, ${clientCard.age} лет` : ""}
                </div>
                {(clientCard.profession || clientCard.city) && (
                  <div className="text-sm" style={{ color: "var(--text-secondary)" }}>
                    {[clientCard.profession, clientCard.city].filter(Boolean).join(" · ")}
                  </div>
                )}
                {clientCard.lead_source_label && (
                  <div className="text-sm" style={{ color: "var(--text-muted)" }}>
                    Источник: {clientCard.lead_source_label}
                  </div>
                )}
              </div>

              {/* Finance summary */}
              <div className="space-y-2">
                <div className="text-sm font-semibold uppercase tracking-wide flex items-center gap-1.5" style={{ color: "var(--accent)" }}>
                  <Landmark size={12} /> ФИНАНСЫ
                </div>
                <div className="text-base font-medium" style={{ color: "var(--danger)" }}>
                  {fmt.format(clientCard.total_debt)} ₽
                </div>
                <div className="text-sm" style={{ color: "var(--text-secondary)" }}>
                  Кредиторов: <strong>{(clientCard.creditors || []).length}</strong>
                </div>
                <div className="text-sm" style={{ color: "var(--text-muted)" }}>
                  Доход: {clientCard.income > 0 ? `${fmt.format(clientCard.income)} ₽` : "не указан"}
                </div>
              </div>

              {/* Call history summary */}
              <div className="space-y-2">
                <div className="text-sm font-semibold uppercase tracking-wide flex items-center gap-1.5" style={{ color: "var(--accent)" }}>
                  <Phone size={12} /> ИСТОРИЯ
                </div>
                {(clientCard.call_history || []).length > 0 ? (
                  <div className="text-sm" style={{ color: "var(--text-secondary)" }}>
                    Последний: <strong>{clientCard.call_history[0].date}</strong>
                    <div className="mt-1 truncate" style={{ color: "var(--text-muted)" }}>
                      {clientCard.call_history[0].note}
                    </div>
                  </div>
                ) : (
                  <div className="text-sm" style={{ color: "var(--text-muted)" }}>Первый контакт</div>
                )}
              </div>
            </div>

            {/* Hidden data reminder */}
            <div className="px-4 pb-3 flex items-center gap-2 text-sm" style={{ color: "var(--text-muted)" }}>
              <Lock size={12} />
              Психотип и ловушки скрыты
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
