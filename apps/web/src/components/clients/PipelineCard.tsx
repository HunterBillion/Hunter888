"use client";

import { useState } from "react";
import { Bell, Calendar, DollarSign, ExternalLink, MessageSquarePlus, Phone, AlertTriangle } from "lucide-react";
import Link from "next/link";
import { sanitizeText } from "@/lib/sanitize";
import type { CRMClient, UserRole } from "@/types";
import { CLIENT_STATUS_COLORS } from "@/types";

export type PipelineCardField =
  | "phone"
  | "debt"
  | "next_contact"
  | "manager"
  | "updated"
  | "source";

interface PipelineCardProps {
  client: CRMClient;
  userRole?: UserRole;
  readOnly?: boolean;
  onQuickNote?: (client: CRMClient) => void;
  onReminder?: (client: CRMClient) => void;
  onInlineNoteSubmit?: (client: CRMClient, text: string) => Promise<void>;
  visibleFields?: PipelineCardField[];
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

export function PipelineCard({
  client,
  userRole,
  readOnly = false,
  onQuickNote,
  onReminder,
  onInlineNoteSubmit,
  visibleFields = ["debt", "phone", "next_contact", "updated"],
}: PipelineCardProps) {
  const color = CLIENT_STATUS_COLORS[client.status];
  const showField = (field: PipelineCardField) => visibleFields.includes(field);
  const [composerOpen, setComposerOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
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

  const handleInlineSave = async () => {
    const text = draft.trim();
    if (!text || !onInlineNoteSubmit) return;
    setSaving(true);
    try {
      await onInlineNoteSubmit(client, text);
      setDraft("");
      setComposerOpen(false);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="rounded-lg transition-all duration-150 hover:brightness-110"
      style={{
        background: "var(--bg-primary)",
        border: "1px solid var(--border-color)",
      }}
    >
      <Link href={`/clients/${client.id}`} onClick={(e) => e.stopPropagation()} className="group block p-3">
        {/* Name + overdue indicator */}
        <div className="flex items-start justify-between gap-1">
          <span
            className="text-[13px] font-medium leading-tight truncate"
            style={{ color: "var(--text-primary)" }}
          >
            {sanitizeText(client.full_name)}
          </span>
          <div className="flex items-center gap-1">
            {overdue && (
              <AlertTriangle
                size={12}
                className="shrink-0 mt-0.5"
                style={{ color: "var(--danger)" }}
              />
            )}
            <ExternalLink size={12} className="opacity-0 transition-opacity group-hover:opacity-100" style={{ color: "var(--text-muted)" }} />
          </div>
        </div>

        {/* Meta row */}
        <div className="mt-2 flex items-center gap-3 flex-wrap">
          {showField("debt") && (client.debt_amount ?? 0) > 0 && (
            <span
              className="flex items-center gap-0.5 text-xs font-mono"
              style={{ color: "var(--text-muted)" }}
            >
              <DollarSign size={10} />
              {formatDebt(client.debt_amount ?? 0)} ₽
            </span>
          )}
          {showField("phone") && client.phone && (
            <span
              className="flex items-center gap-0.5 text-xs font-mono"
              style={{ color: "var(--text-muted)" }}
            >
              <Phone size={10} />
              {client.phone.replace(/(\d{1})\d{5}(\d{4})/, "$1•••••$2")}
            </span>
          )}
          {showField("source") && client.source && (
            <span
              className="text-xs font-mono"
              style={{ color: "var(--text-muted)" }}
            >
              {client.source}
            </span>
          )}
        </div>

        {/* Next contact */}
        {showField("next_contact") && nextContactLabel && (
          <div className="mt-2 flex items-center gap-1">
            <Calendar size={10} style={{ color: overdue ? "var(--danger)" : color }} />
            <span
              className="text-xs font-mono"
              style={{ color: overdue ? "var(--danger)" : "var(--text-muted)" }}
            >
              {nextContactLabel}
            </span>
          </div>
        )}

        {/* Manager name for admin/rop */}
        {showField("manager") && (userRole === "admin" || userRole === "rop") && client.manager_name && (
          <div className="mt-1.5">
            <span
              className="text-xs font-mono"
              style={{ color: "var(--text-muted)", opacity: 0.7 }}
            >
              {client.manager_name}
            </span>
          </div>
        )}

        {/* Updated time */}
        {showField("updated") && client.updated_at && (
          <div className="mt-1.5">
            <span
              className="text-xs font-mono"
              style={{ color: "var(--text-muted)", opacity: 0.6 }}
            >
              Обновлён {timeAgo(client.updated_at)}
            </span>
          </div>
        )}
      </Link>

      {!readOnly && (onQuickNote || onReminder) && (
        <div
          className="flex items-center gap-2 border-t px-3 py-2"
          style={{ borderColor: "var(--border-color)" }}
        >
          {onInlineNoteSubmit && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                setComposerOpen((prev) => !prev);
              }}
              className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-mono"
              style={{ background: "var(--accent-muted)", color: "var(--accent)" }}
            >
              <MessageSquarePlus size={11} />
              Написать
            </button>
          )}
          {onQuickNote && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onQuickNote(client);
              }}
              className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-mono"
              style={{ background: "var(--input-bg)", color: "var(--text-secondary)" }}
            >
              <MessageSquarePlus size={11} />
              Заметка
            </button>
          )}
          {onReminder && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onReminder(client);
              }}
              className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-mono"
              style={{ background: "var(--input-bg)", color: "var(--text-secondary)" }}
            >
              <Bell size={11} />
              Напомнить
            </button>
          )}
        </div>
      )}

      {!readOnly && composerOpen && onInlineNoteSubmit && (
        <div
          className="border-t px-3 py-3"
          style={{ borderColor: "var(--border-color)", background: "rgba(255,255,255,0.02)" }}
        >
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Быстрая заметка по клиенту прямо из канбана..."
            className="vh-input w-full text-xs"
            rows={3}
            style={{ resize: "vertical" }}
          />
          <div className="mt-2 flex items-center justify-between gap-2">
            <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
              {draft.length}/1000
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => {
                  setComposerOpen(false);
                  setDraft("");
                }}
                className="rounded-lg px-2.5 py-1 text-xs font-mono"
                style={{ background: "var(--input-bg)", color: "var(--text-muted)" }}
              >
                Скрыть
              </button>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  void handleInlineSave();
                }}
                disabled={!draft.trim() || saving}
                className="rounded-lg px-2.5 py-1 text-xs font-mono"
                style={{
                  background: draft.trim() ? "var(--accent)" : "var(--input-bg)",
                  color: draft.trim() ? "#050505" : "var(--text-muted)",
                  opacity: saving ? 0.7 : 1,
                }}
              >
                {saving ? "Сохраняю..." : "Сохранить"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
