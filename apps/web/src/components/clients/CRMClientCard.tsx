"use client";

import { motion } from "framer-motion";
import { Phone, Calendar, AlertCircle, User } from "lucide-react";
import Link from "next/link";
import type { CRMClient, UserRole } from "@/types";
import { CLIENT_STATUS_LABELS, CLIENT_STATUS_COLORS } from "@/types";
import { sanitizeText } from "@/lib/sanitize";

interface ClientCardProps {
  client: CRMClient;
  compact?: boolean;
  userRole?: UserRole;
}

/**
 * CRM client card — unified with platform glass-panel aesthetic.
 * Replaces the legacy macOS-Terminal style that clashed with the rest
 * of the product (home / training / dashboard all use glass + accent glow).
 *
 * Dense 2-column layout: left = identity + status, right = key metrics.
 */
export function CRMClientCard({ client, compact, userRole }: ClientCardProps) {
  const statusColor = CLIENT_STATUS_COLORS[client.status];
  const statusLabel = CLIENT_STATUS_LABELS[client.status];

  const formatDebt = (amount: number) => {
    if (amount >= 1_000_000) return `${(amount / 1_000_000).toFixed(1)}M`;
    if (amount >= 1_000) return `${(amount / 1_000).toFixed(0)}K`;
    return amount.toLocaleString("ru-RU");
  };

  const formatDate = (iso: string) => {
    const d = new Date(iso);
    const now = new Date();
    const diff = d.getTime() - now.getTime();
    const days = Math.ceil(diff / 86_400_000);
    if (days === 0) return "Сегодня";
    if (days === 1) return "Завтра";
    if (days < 0) return `Просрочено ${Math.abs(days)} дн.`;
    if (days <= 7) return `Через ${days} дн.`;
    return d.toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
  };

  const isOverdue = client.next_contact_at && new Date(client.next_contact_at) < new Date();

  // Initials for avatar fallback
  const initials = (client.full_name || "")
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((n) => n[0]?.toUpperCase() ?? "")
    .join("") || "?";

  return (
    <Link href={`/clients/${client.id}`}>
      <motion.div
        whileHover={{ y: -2, boxShadow: "0 6px 24px rgba(107,77,199,0.18)" }}
        transition={{ duration: 0.15, ease: "easeOut" }}
        className="glass-panel p-4 cursor-pointer relative overflow-hidden"
        style={{
          borderLeft: `3px solid ${statusColor}`,
        }}
      >
        {/* Overdue corner badge */}
        {isOverdue && (
          <div
            className="absolute top-0 right-0 flex items-center gap-1 px-2 py-0.5 text-[10px] font-medium"
            style={{
              background: "var(--danger-muted, rgba(239,68,68,0.12))",
              color: "var(--danger, #ef4444)",
              borderBottomLeftRadius: 8,
            }}
          >
            <AlertCircle size={10} />
            ПРОСРОЧЕНО
          </div>
        )}

        <div className="flex items-start gap-3">
          {/* Avatar */}
          <div
            className="shrink-0 flex items-center justify-center w-10 h-10 rounded-full font-semibold text-sm"
            style={{
              background: `color-mix(in srgb, ${statusColor} 15%, transparent)`,
              color: statusColor,
              border: `1px solid color-mix(in srgb, ${statusColor} 30%, transparent)`,
            }}
            aria-hidden
          >
            {initials}
          </div>

          <div className="min-w-0 flex-1">
            {/* Name + status */}
            <div className="flex items-center justify-between gap-2 mb-1">
              <h3
                className="font-display font-semibold truncate text-[15px]"
                style={{ color: "var(--text-primary)" }}
              >
                {sanitizeText(client.full_name)}
              </h3>
              <span
                className="shrink-0 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide rounded-full"
                style={{
                  background: `color-mix(in srgb, ${statusColor} 14%, transparent)`,
                  color: statusColor,
                  border: `1px solid color-mix(in srgb, ${statusColor} 28%, transparent)`,
                }}
              >
                {statusLabel}
              </span>
            </div>

            {!compact && (
              <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
                {/* Phone */}
                {client.phone && (
                  <div className="flex items-center gap-1.5 min-w-0">
                    <Phone size={11} style={{ color: "var(--text-muted)" }} className="shrink-0" />
                    <span className="truncate" style={{ color: "var(--text-secondary)" }}>
                      {client.phone}
                    </span>
                  </div>
                )}

                {/* Debt */}
                <div className="flex items-center gap-1.5 min-w-0">
                  <span className="font-mono text-[10px]" style={{ color: "var(--text-muted)" }}>
                    ДОЛГ
                  </span>
                  <span
                    className="font-mono font-semibold truncate"
                    style={{ color: "var(--text-primary)" }}
                  >
                    {formatDebt(client.debt_amount ?? 0)} ₽
                  </span>
                </div>

                {/* Next contact */}
                {client.next_contact_at && (
                  <div className="flex items-center gap-1.5 min-w-0 col-span-2">
                    <Calendar
                      size={11}
                      style={{ color: isOverdue ? "var(--danger)" : "var(--text-muted)" }}
                      className="shrink-0"
                    />
                    <span
                      className="truncate"
                      style={{ color: isOverdue ? "var(--danger)" : "var(--text-secondary)" }}
                    >
                      {formatDate(client.next_contact_at)}
                    </span>
                  </div>
                )}

                {/* Manager */}
                {(userRole === "admin" || userRole === "rop") && client.manager_name && (
                  <div className="flex items-center gap-1.5 min-w-0 col-span-2">
                    <User size={11} style={{ color: "var(--text-muted)" }} className="shrink-0" />
                    <span className="truncate text-[11px]" style={{ color: "var(--text-muted)" }}>
                      {sanitizeText(client.manager_name ?? "")}
                    </span>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </motion.div>
    </Link>
  );
}
