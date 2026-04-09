"use client";

import { motion } from "framer-motion";
import { Phone, Calendar, DollarSign, ChevronRight } from "lucide-react";
import Link from "next/link";
import type { CRMClient, UserRole } from "@/types";
import { CLIENT_STATUS_LABELS, CLIENT_STATUS_COLORS } from "@/types";
import { sanitizeText } from "@/lib/sanitize";

interface ClientCardProps {
  client: CRMClient;
  compact?: boolean;
  userRole?: UserRole;
}

/** CRM client card — renamed to avoid collision with training/ClientCard */
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
    if (days < 0) return `${Math.abs(days)} дн. назад`;
    return d.toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
  };

  const isOverdue = client.next_contact_at && new Date(client.next_contact_at) < new Date();

  return (
    <Link href={`/clients/${client.id}`}>
      <motion.div
        className="glass-panel p-4 flex items-center gap-4 cursor-pointer group"
        whileHover={{ y: -1 }}
        transition={{ duration: 0.15 }}
      >
        {/* Status dot */}
        <div
          className="w-2.5 h-2.5 rounded-full shrink-0"
          style={{ background: statusColor, boxShadow: `0 0 8px ${statusColor}` }}
        />

        {/* Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium truncate" style={{ color: "var(--text-primary)" }}>
              {sanitizeText(client.full_name)}
            </span>
            <span
              className="text-xs font-mono px-1.5 py-0.5 rounded-full"
              style={{ background: `color-mix(in srgb, ${statusColor} 9%, transparent)`, color: statusColor, border: `1px solid color-mix(in srgb, ${statusColor} 19%, transparent)` }}
            >
              {statusLabel}
            </span>
          </div>

          {!compact && (
            <div className="flex items-center gap-4 mt-1.5">
              {client.phone && (
                <span className="flex items-center gap-1 text-xs" style={{ color: "var(--text-muted)" }}>
                  <Phone size={11} /> {client.phone}
                </span>
              )}
              <span className="flex items-center gap-1 text-xs" style={{ color: "var(--text-muted)" }}>
                <DollarSign size={11} /> {formatDebt(client.debt_amount ?? 0)} ₽
              </span>
              {client.next_contact_at && (
                <span
                  className="flex items-center gap-1 text-xs"
                  style={{ color: isOverdue ? "var(--danger)" : "var(--text-muted)" }}
                >
                  <Calendar size={11} /> {formatDate(client.next_contact_at)}
                </span>
              )}
              {(userRole === "admin" || userRole === "rop") && client.manager_name && (
                <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                  {sanitizeText(client.manager_name ?? "")}
                </span>
              )}
            </div>
          )}
        </div>

        {/* Arrow */}
        <ChevronRight
          size={16}
          className="shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
          style={{ color: "var(--text-muted)" }}
        />
      </motion.div>
    </Link>
  );
}
