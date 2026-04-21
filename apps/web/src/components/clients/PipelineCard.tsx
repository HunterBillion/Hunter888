"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Bell,
  Calendar,
  Check,
  Clock,
  DollarSign,
  ExternalLink,
  Loader2,
  MessageSquarePlus,
  Pencil,
  Phone,
  AlertTriangle,
  X,
} from "lucide-react";
import Link from "next/link";
import { sanitizeText } from "@/lib/sanitize";
import type { CRMClient, UserRole, ClientStatus } from "@/types";
import { CLIENT_STATUS_COLORS, CLIENT_STATUS_LABELS } from "@/types";

/** Max days in a status before it is flagged as "stuck". */
const STUCK_THRESHOLDS: Partial<Record<ClientStatus, number>> = {
  new: 3,
  contacted: 5,
  thinking: 21,
  consultation: 7,
};
const STUCK_DEFAULT_DAYS = 14;

function getDaysInStatus(client: CRMClient): number | null {
  const ref = client.last_status_change_at || client.updated_at;
  if (!ref) return null;
  const diffMs = Date.now() - new Date(ref).getTime();
  return Math.floor(diffMs / 86_400_000);
}

function isStuck(client: CRMClient): { stuck: boolean; days: number } {
  const days = getDaysInStatus(client);
  if (days === null) return { stuck: false, days: 0 };
  const threshold = STUCK_THRESHOLDS[client.status] ?? STUCK_DEFAULT_DAYS;
  return { stuck: days > threshold, days };
}

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
  onInlineEdit?: (clientId: string, patch: Partial<CRMClient>) => Promise<void>;
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
  onInlineEdit,
  visibleFields = ["debt", "phone", "next_contact", "updated"],
}: PipelineCardProps) {
  const color = CLIENT_STATUS_COLORS[client.status];
  const statusLabel = CLIENT_STATUS_LABELS[client.status];
  const showField = (field: PipelineCardField) => visibleFields.includes(field);

  // Inline note composer
  const [composerOpen, setComposerOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);

  // Inline editing state
  const [editingField, setEditingField] = useState<"name" | "notes" | null>(null);
  const [editValue, setEditValue] = useState("");
  const [editSaving, setEditSaving] = useState(false);
  const editInputRef = useRef<HTMLInputElement | HTMLTextAreaElement>(null);

  const stuckInfo = isStuck(client);
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

  // Focus input when editing starts
  useEffect(() => {
    if (editingField && editInputRef.current) {
      editInputRef.current.focus();
      if (editInputRef.current instanceof HTMLInputElement) {
        editInputRef.current.select();
      }
    }
  }, [editingField]);

  const startEdit = useCallback(
    (field: "name" | "notes", e: React.MouseEvent) => {
      if (readOnly || !onInlineEdit) return;
      e.preventDefault();
      e.stopPropagation();
      setEditingField(field);
      setEditValue(field === "name" ? client.full_name : client.notes || "");
    },
    [readOnly, onInlineEdit, client.full_name, client.notes],
  );

  const cancelEdit = useCallback(() => {
    setEditingField(null);
    setEditValue("");
  }, []);

  const saveEdit = useCallback(async () => {
    if (!onInlineEdit || !editingField) return;
    const trimmed = editValue.trim();
    if (editingField === "name" && !trimmed) return; // name cannot be empty

    const patch: Partial<CRMClient> =
      editingField === "name"
        ? { full_name: trimmed }
        : { notes: trimmed || null };

    // Check if actually changed
    const current = editingField === "name" ? client.full_name : (client.notes || "");
    if (trimmed === current.trim()) {
      cancelEdit();
      return;
    }

    setEditSaving(true);
    try {
      await onInlineEdit(client.id, patch);
      cancelEdit();
    } finally {
      setEditSaving(false);
    }
  }, [onInlineEdit, editingField, editValue, client, cancelEdit]);

  const handleEditKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Escape") {
        cancelEdit();
      } else if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        void saveEdit();
      }
    },
    [cancelEdit, saveEdit],
  );

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
    <motion.div
      className="rounded-lg group/card"
      style={{
        background: "var(--bg-primary)",
        border: stuckInfo.stuck
          ? "1px solid var(--warning, #f59e0b)"
          : "1px solid var(--border-color)",
      }}
      whileHover={{
        y: -2,
        boxShadow: `0 4px 16px rgba(0,0,0,0.15), 0 0 0 1px ${color}25`,
        borderColor: `color-mix(in srgb, ${color} 30%, var(--border-color))`,
      }}
      transition={{ duration: 0.15 }}
    >
      {/* Status indicator bar */}
      <div
        className="h-[3px] rounded-t-lg"
        style={{ background: color, opacity: 0.7 }}
      />

      <div className="p-3">
        {/* Name — editable on click */}
        <div className="flex items-start justify-between gap-1">
          {editingField === "name" ? (
            <div className="flex-1 flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
              <input
                ref={editInputRef as React.RefObject<HTMLInputElement>}
                type="text"
                value={editValue}
                onChange={(e) => setEditValue(e.target.value)}
                onKeyDown={handleEditKeyDown}
                onBlur={() => void saveEdit()}
                disabled={editSaving}
                className="flex-1 text-sm font-medium rounded px-1.5 py-0.5 outline-none"
                style={{
                  background: "var(--input-bg)",
                  border: "1px solid var(--accent)",
                  color: "var(--text-primary)",
                  fontFamily: "inherit",
                }}
                maxLength={200}
              />
              {editSaving && (
                <Loader2 size={12} className="animate-spin shrink-0" style={{ color: "var(--accent)" }} />
              )}
            </div>
          ) : (
            <div className="flex items-center gap-1 flex-1 min-w-0">
              <span
                className="text-sm font-medium leading-tight truncate cursor-default"
                style={{ color: "var(--text-primary)" }}
                onDoubleClick={(e) => startEdit("name", e)}
                title="Двойной клик для редактирования"
              >
                {sanitizeText(client.full_name)}
              </span>
              {!readOnly && onInlineEdit && (
                <button
                  type="button"
                  onClick={(e) => startEdit("name", e)}
                  className="opacity-0 group-hover/card:opacity-60 hover:!opacity-100 transition-opacity shrink-0"
                  title="Редактировать имя"
                >
                  <Pencil size={10} style={{ color: "var(--text-muted)" }} />
                </button>
              )}
            </div>
          )}
          <div className="flex items-center gap-1 shrink-0">
            {overdue && (
              <AlertTriangle
                size={12}
                className="shrink-0 mt-0.5"
                style={{ color: "var(--danger)" }}
              />
            )}
            <Link
              href={`/clients/${client.id}`}
              onClick={(e) => e.stopPropagation()}
              className="opacity-0 group-hover/card:opacity-60 hover:!opacity-100 transition-opacity"
              title="Открыть карточку"
            >
              <ExternalLink size={12} style={{ color: "var(--text-muted)" }} />
            </Link>
          </div>
        </div>

        {/* Status badge */}
        <div className="mt-1.5 flex items-center gap-1.5 flex-wrap">
          <span
            className="inline-flex items-center gap-1 text-xs font-mono font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded"
            style={{
              background: `color-mix(in srgb, ${color} 15%, transparent)`,
              color: color,
              border: `1px solid color-mix(in srgb, ${color} 25%, transparent)`,
            }}
          >
            <span
              className="w-1.5 h-1.5 rounded-full shrink-0"
              style={{ background: color }}
            />
            {statusLabel}
          </span>
          {stuckInfo.stuck && (
            <span
              className="inline-flex items-center gap-1 text-xs font-mono font-semibold px-1.5 py-0.5 rounded"
              style={{
                background: "rgba(245,158,11,0.15)",
                color: "var(--warning, #f59e0b)",
                border: "1px solid rgba(245,158,11,0.3)",
              }}
              title={`Клиент в этом статусе ${stuckInfo.days} дн.`}
            >
              <Clock size={10} />
              {stuckInfo.days}д в статусе
            </span>
          )}
        </div>

        {/* Meta row */}
        <div className="mt-2 flex items-center gap-3 flex-wrap">
          {showField("debt") && (client.debt_amount ?? 0) > 0 && (
            <span
              className="flex items-center gap-0.5 text-xs font-mono"
              style={{ color: "var(--text-muted)" }}
            >
              <DollarSign size={10} />
              {formatDebt(client.debt_amount ?? 0)} &#8381;
            </span>
          )}
          {showField("phone") && client.phone && (
            <span
              className="flex items-center gap-0.5 text-xs font-mono"
              style={{ color: "var(--text-muted)" }}
            >
              <Phone size={10} />
              {client.phone.replace(/(\d{1})\d{5}(\d{4})/, "$1*****$2")}
            </span>
          )}
          {showField("source") && client.source && (
            <span
              className="text-xs font-mono px-1 py-0.5 rounded"
              style={{
                color: "var(--text-muted)",
                background: "var(--input-bg)",
              }}
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

        {/* Notes — editable */}
        {client.notes ? (
          <div className="mt-2">
            {editingField === "notes" ? (
              <div onClick={(e) => e.stopPropagation()}>
                <textarea
                  ref={editInputRef as React.RefObject<HTMLTextAreaElement>}
                  value={editValue}
                  onChange={(e) => setEditValue(e.target.value)}
                  onKeyDown={handleEditKeyDown}
                  disabled={editSaving}
                  className="w-full text-xs font-mono rounded px-1.5 py-1 outline-none"
                  style={{
                    background: "var(--input-bg)",
                    border: "1px solid var(--accent)",
                    color: "var(--text-secondary)",
                    resize: "vertical",
                    minHeight: "48px",
                  }}
                  rows={3}
                  maxLength={1000}
                />
                <div className="flex items-center justify-end gap-1 mt-1">
                  <button
                    type="button"
                    onClick={cancelEdit}
                    className="rounded px-1.5 py-0.5 text-xs font-mono"
                    style={{ color: "var(--text-muted)" }}
                  >
                    <X size={10} />
                  </button>
                  <button
                    type="button"
                    onClick={() => void saveEdit()}
                    disabled={editSaving}
                    className="rounded px-1.5 py-0.5 text-xs font-mono"
                    style={{ color: "var(--accent)" }}
                  >
                    {editSaving ? <Loader2 size={10} className="animate-spin" /> : <Check size={10} />}
                  </button>
                </div>
              </div>
            ) : (
              <p
                className="text-xs font-mono leading-relaxed line-clamp-2 cursor-default"
                style={{ color: "var(--text-muted)", opacity: 0.8 }}
                onDoubleClick={(e) => startEdit("notes", e)}
                title="Двойной клик для редактирования заметки"
              >
                {sanitizeText(client.notes)}
              </p>
            )}
          </div>
        ) : !readOnly && onInlineEdit && editingField !== "notes" ? (
          <button
            type="button"
            onClick={(e) => startEdit("notes", e)}
            className="mt-2 w-full text-left text-xs font-mono py-1.5 px-2 rounded border border-dashed transition-colors"
            style={{
              borderColor: "var(--border-color)",
              color: "var(--text-muted)",
              opacity: 0.5,
            }}
            onMouseEnter={(e) => {
              (e.currentTarget.style.borderColor as string) = "var(--accent)";
              e.currentTarget.style.opacity = "0.8";
            }}
            onMouseLeave={(e) => {
              (e.currentTarget.style.borderColor as string) = "var(--border-color)";
              e.currentTarget.style.opacity = "0.5";
            }}
          >
            + Добавить заметку...
          </button>
        ) : editingField === "notes" ? (
          <div className="mt-2" onClick={(e) => e.stopPropagation()}>
            <textarea
              ref={editInputRef as React.RefObject<HTMLTextAreaElement>}
              value={editValue}
              onChange={(e) => setEditValue(e.target.value)}
              onKeyDown={handleEditKeyDown}
              disabled={editSaving}
              placeholder="Заметка по клиенту..."
              className="w-full text-xs font-mono rounded px-1.5 py-1 outline-none"
              style={{
                background: "var(--input-bg)",
                border: "1px solid var(--accent)",
                color: "var(--text-secondary)",
                resize: "vertical",
                minHeight: "48px",
              }}
              rows={3}
              maxLength={1000}
            />
            <div className="flex items-center justify-end gap-1 mt-1">
              <button
                type="button"
                onClick={cancelEdit}
                className="rounded px-1.5 py-0.5 text-xs font-mono"
                style={{ color: "var(--text-muted)" }}
              >
                <X size={10} />
              </button>
              <button
                type="button"
                onClick={() => void saveEdit()}
                disabled={editSaving}
                className="rounded px-1.5 py-0.5 text-xs font-mono"
                style={{ color: "var(--accent)" }}
              >
                {editSaving ? <Loader2 size={10} className="animate-spin" /> : <Check size={10} />}
              </button>
            </div>
          </div>
        ) : null}

        {/* Updated time */}
        {showField("updated") && client.updated_at && (
          <div className="mt-1.5">
            <span
              className="text-xs font-mono"
              style={{ color: "var(--text-muted)", opacity: 0.5 }}
            >
              {timeAgo(client.updated_at)}
            </span>
          </div>
        )}
      </div>

      {/* Action buttons */}
      {!readOnly && (onQuickNote || onReminder || onInlineNoteSubmit) && (
        <div
          className="flex items-center gap-1.5 border-t px-3 py-2"
          style={{ borderColor: "var(--border-color)" }}
        >
          {onInlineNoteSubmit && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                setComposerOpen((prev) => !prev);
              }}
              className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-mono transition-colors"
              style={{
                background: composerOpen ? "var(--accent)" : "var(--accent-muted)",
                color: composerOpen ? "var(--bg-primary)" : "var(--accent)",
              }}
            >
              <MessageSquarePlus size={10} />
              {composerOpen ? "Скрыть" : "Написать"}
            </button>
          )}
          {onQuickNote && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onQuickNote(client);
              }}
              className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-mono"
              style={{ background: "var(--input-bg)", color: "var(--text-secondary)" }}
            >
              <MessageSquarePlus size={10} />
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
              className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-mono"
              style={{ background: "var(--input-bg)", color: "var(--text-secondary)" }}
            >
              <Bell size={10} />
            </button>
          )}
        </div>
      )}

      {/* Inline note composer */}
      <AnimatePresence>
        {!readOnly && composerOpen && onInlineNoteSubmit && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="overflow-hidden"
          >
            <div
              className="border-t px-3 py-3"
              style={{ borderColor: "var(--border-color)", background: "rgba(255,255,255,0.02)" }}
            >
              <textarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="Быстрая заметка по клиенту..."
                className="w-full text-xs font-mono rounded-md px-2 py-1.5 outline-none"
                style={{
                  background: "var(--input-bg)",
                  border: "1px solid var(--border-color)",
                  color: "var(--text-secondary)",
                  resize: "vertical",
                }}
                rows={3}
                maxLength={1000}
              />
              <div className="mt-2 flex items-center justify-between gap-2">
                <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                  {draft.length}/1000
                </span>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    void handleInlineSave();
                  }}
                  disabled={!draft.trim() || saving}
                  className="rounded-md px-2.5 py-1 text-xs font-mono font-semibold transition-colors"
                  style={{
                    background: draft.trim() ? "var(--accent)" : "var(--input-bg)",
                    color: draft.trim() ? "var(--bg-primary)" : "var(--text-muted)",
                    opacity: saving ? 0.7 : 1,
                  }}
                >
                  {saving ? "..." : "Сохранить"}
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
