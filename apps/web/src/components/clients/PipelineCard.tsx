"use client";

import { Phone, Calendar, DollarSign, AlertTriangle } from "lucide-react";
import Link from "next/link";
import type { CRMClient, UserRole } from "@/types";
import { CLIENT_STATUS_COLORS } from "@/types";

interface PipelineCardProps {
  client: CRMClient;
  userRole?: UserRole;
}

const formatDebt = (amount: number) => {
  if (amount >= 1_000_000) return `${(amount / 1_000_000).toFixed(1)}M`;
  if (amount >= 1_000) return `${(amount / 1_000).toFixed(0)}K`;
  return amount.toLocaleString("ru-RU");
};

const timeAgo = (iso: string | null) => {
  if (!iso) return null;
  const d = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const days = Math.floor(diffMs / 86_400_000);
  if (days === 0) return "Сегодня";
  if (days === 1) return "Вчера";
  return `${days} дн. назад`;
};

const isOverdue = (date: string | null) => {
  if (!date) return false;
  return new Date(date) < new Date();
};

export function PipelineCard({ client, userRole }: PipelineCardProps) {
  const color = CLIENT_STATUS_COLORS[client.status];
  const overdue = isOverdue(client.next_contact_at);
  const nextContactLabel = client.next_contact_at
    ? (() => {
        const d = new Date(client.next_contact_at);
        const now = new Date();
        const diff = d.getTime() - now.getTime();
        const days = Math.ceil(diff / 86_400_000);
        if (days === 0) return "Сегодня";
        if (days === 1) return "Завтра";
        if (days < 0) return `${Math.abs(days)} дн. просрочка`;
        return d.toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
      })()
    : null;

  return (
    <Link href={`/clients/${client.id}`} onClick={(e) => e.stopPropagation()}>
      <div
        className="rounded-lg p-3 transition-all duration-150 hover:brightness-110 group"
        style={{
          background: "var(--bg-primary)",
          border: `1px solid var(--border-color)`,
        }}
      >
        {/* Name + overdue indicator */}
        <div className="flex items-start justify-between gap-1">
          <span
            className="text-[13px] font-medium leading-tight truncate"
            style={{ color: "var(--text-primary)" }}
          >
            {client.full_name}
          </span>
          {overdue && (
            <AlertTriangle
              size={12}
              className="shrink-0 mt-0.5"
              style={{ color: "var(--neon-red, #FF3333)" }}
            />
          )}
        </div>

        {/* Meta row */}
        <div className="flex items-center gap-3 mt-2 flex-wrap">
          {(client.debt_amount ?? 0) > 0 && (
            <span
              className="flex items-center gap-0.5 text-[10px] font-mono"
              style={{ color: "var(--text-muted)" }}
            >
              <DollarSign size={10} />
              {formatDebt(client.debt_amount ?? 0)} ₽
            </span>
          )}
          {client.phone && (
            <span
              className="flex items-center gap-0.5 text-[10px] font-mono"
              style={{ color: "var(--text-muted)" }}
            >
              <Phone size={10} />
              {client.phone.replace(/(\d{1})\d{5}(\d{4})/, "$1•••••$2")}
            </span>
          )}
        </div>

        {/* Next contact */}
        {nextContactLabel && (
          <div className="mt-2 flex items-center gap-1">
            <Calendar size={10} style={{ color: overdue ? "var(--neon-red, #FF3333)" : color }} />
            <span
              className="text-[10px] font-mono"
              style={{ color: overdue ? "var(--neon-red, #FF3333)" : "var(--text-muted)" }}
            >
              {nextContactLabel}
            </span>
          </div>
        )}

        {/* Manager name for admin/rop */}
        {(userRole === "admin" || userRole === "rop") && client.manager_name && (
          <div className="mt-1.5">
            <span
              className="text-[9px] font-mono"
              style={{ color: "var(--text-muted)", opacity: 0.7 }}
            >
              {client.manager_name}
            </span>
          </div>
        )}

        {/* Updated time */}
        {client.updated_at && (
          <div className="mt-1.5">
            <span
              className="text-[9px] font-mono"
              style={{ color: "var(--text-muted)", opacity: 0.6 }}
            >
              Обновлён {timeAgo(client.updated_at)}
            </span>
          </div>
        )}
      </div>
    </Link>
  );
}
