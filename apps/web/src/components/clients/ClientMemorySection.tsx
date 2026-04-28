"use client";

/**
 * ClientMemorySection — TZ-4 §6.3 / §6.4 read-only card on the
 * client detail page.
 *
 * Shows three blocks:
 *   1. MemoryPersona row (cross-session identity facts +
 *      do-not-ask-again slot list).
 *   2. Latest SessionPersonaSnapshot (immutable per-session frozen
 *      identity) + its mutation_blocked_count counter — non-zero =
 *      runtime tried to drift mid-session and was blocked.
 *   3. Persona event counts over a rolling 30d window.
 *
 * Read-only — writes happen via session start / D5 audit hook /
 * future admin "edit persona" actions; this card is the manager's
 * window into what the AI thinks it knows about the client.
 *
 * Self-hides when the client has no lead_client_id yet (TZ-1
 * dual-write phase) — the section is meaningless without a
 * canonical anchor and we don't want to clutter the FE for clients
 * that haven't been bound yet.
 */

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  Brain,
  CheckCircle2,
  Loader2,
  Lock,
  ShieldAlert,
  ShieldCheck,
  User as UserIcon,
} from "lucide-react";
import { ApiError, api } from "@/lib/api";
import { sanitizeText } from "@/lib/sanitize";
import { logger } from "@/lib/logger";
import type { ClientPersonaMemoryResponse } from "@/types";

interface Props {
  clientId: string;
}

const SLOT_LABELS: Record<string, string> = {
  full_name: "ФИО",
  phone: "Телефон",
  email: "Email",
  city: "Город",
  age: "Возраст",
  gender: "Пол",
  role_title: "Роль",
  total_debt: "Сумма долга",
  creditors: "Кредиторы",
  income: "Доход",
  income_type: "Тип дохода",
  family_status: "Семейный статус",
  children_count: "Дети",
  property_status: "Имущество",
  consent_124fz: "Согласие 152-ФЗ",
  next_contact_at: "Сл. контакт",
  lost_reason: "Причина потери",
};

const ADDRESS_FORM_LABEL: Record<string, string> = {
  "вы": "На «вы»",
  "ты": "На «ты»",
  formal: "Формально",
  informal: "Неформально",
  auto: "Авто",
};

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("ru-RU", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

export function ClientMemorySection({ clientId }: Props) {
  const [data, setData] = useState<ClientPersonaMemoryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const resp = await api.get<ClientPersonaMemoryResponse>(
          `/clients/${clientId}/persona-memory`,
        );
        if (!cancelled) {
          setData(resp);
          setError(null);
        }
      } catch (err) {
        if (cancelled) return;
        const msg =
          err instanceof ApiError || err instanceof Error
            ? err.message
            : "Не удалось загрузить память клиента";
        logger.error("[ClientMemorySection] fetch failed:", err);
        setError(msg);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [clientId]);

  // While loading, show a small placeholder so the layout doesn't
  // jump when the data lands. After load: self-hide when there's
  // genuinely nothing to show (no lead anchor yet AND no events).
  if (loading) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.18 }}
        className="glass-panel p-4 flex items-center gap-2 text-xs"
        style={{ color: "var(--text-muted)" }}
      >
        <Loader2 size={12} className="animate-spin" />
        Память клиента загружается…
      </motion.div>
    );
  }

  if (error) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass-panel p-4 text-xs"
        style={{ color: "var(--danger)" }}
      >
        {sanitizeText(error)}
      </motion.div>
    );
  }

  if (!data) return null;
  const hasAnything =
    data.persona ||
    data.last_snapshot ||
    Object.values(data.event_counts).some((n) => n > 0);
  if (!hasAnything) return null;

  const persona = data.persona;
  const snap = data.last_snapshot;
  const counts = data.event_counts;
  const conflictPresent = counts.conflict_detected > 0 || (snap?.mutation_blocked_count ?? 0) > 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.18 }}
      className="glass-panel p-4 space-y-3"
    >
      <div className="flex items-center gap-2">
        <Brain size={14} style={{ color: "var(--accent)" }} />
        <span
          className="text-xs font-semibold uppercase tracking-wide"
          style={{ color: "var(--accent)" }}
        >
          ПАМЯТЬ КЛИЕНТА
        </span>
        {conflictPresent && (
          <span
            className="ml-auto inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px]"
            style={{
              background: "color-mix(in srgb, var(--warning) 14%, transparent)",
              color: "var(--warning)",
            }}
            title="Зафиксированы попытки сменить идентичность"
          >
            <ShieldAlert size={10} />
            конфликт
          </span>
        )}
      </div>

      {/* MemoryPersona row */}
      {persona ? (
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-sm" style={{ color: "var(--text-primary)" }}>
            <UserIcon size={13} style={{ color: "var(--text-muted)" }} />
            <span className="font-medium truncate">{sanitizeText(persona.full_name)}</span>
            <span
              className="rounded px-1.5 py-0.5 text-[10px]"
              style={{
                background: "var(--input-bg)",
                color: "var(--text-muted)",
              }}
              title="Форма обращения"
            >
              {ADDRESS_FORM_LABEL[persona.address_form] ?? persona.address_form}
            </span>
            <span
              className="rounded px-1.5 py-0.5 text-[10px] font-mono"
              style={{
                background: "var(--input-bg)",
                color: "var(--text-muted)",
              }}
              title={`Версия записи (optimistic concurrency, TZ-4 §9.2.5)`}
            >
              v{persona.version}
            </span>
          </div>

          {/* Confirmed slots — quick scan of what AI considers locked */}
          {persona.do_not_ask_again_slots.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {persona.do_not_ask_again_slots.map((slot) => {
                const fact = persona.confirmed_facts[slot];
                const value = fact && typeof fact === "object" ? fact.value : null;
                const tooltip = value != null ? `${slot}: ${String(value)}` : `${slot} зафиксирован`;
                return (
                  <span
                    key={slot}
                    className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px]"
                    style={{
                      background: "color-mix(in srgb, var(--success) 14%, transparent)",
                      color: "var(--success)",
                    }}
                    title={tooltip}
                  >
                    <Lock size={10} />
                    {SLOT_LABELS[slot] ?? slot}
                  </span>
                );
              })}
            </div>
          )}

          <div
            className="text-[11px] flex items-center gap-3"
            style={{ color: "var(--text-muted)" }}
          >
            <span>Подтверждено: {formatDate(persona.last_confirmed_at)}</span>
            <span>· Обновлено: {formatDate(persona.updated_at)}</span>
          </div>
        </div>
      ) : (
        <div className="text-xs leading-relaxed" style={{ color: "var(--text-muted)" }}>
          Пока пусто — AI начнёт собирать факты после первой сессии.
        </div>
      )}

      {/* Last snapshot strip */}
      {snap && (
        <div
          className="rounded-lg p-2.5 flex items-center justify-between gap-3"
          style={{
            background: "var(--input-bg)",
            border: "1px solid var(--border-color)",
          }}
        >
          <div className="flex items-center gap-2 min-w-0">
            <ShieldCheck
              size={12}
              style={{
                color:
                  snap.mutation_blocked_count > 0
                    ? "var(--warning)"
                    : "var(--success)",
              }}
            />
            <span
              className="text-[11px] truncate"
              style={{ color: "var(--text-secondary)" }}
            >
              Последний snapshot · {snap.captured_from} · {formatDate(snap.captured_at)}
            </span>
          </div>
          {snap.mutation_blocked_count > 0 && (
            <span
              className="rounded px-1.5 py-0.5 text-[10px] font-mono shrink-0"
              style={{
                background: "color-mix(in srgb, var(--warning) 14%, transparent)",
                color: "var(--warning)",
              }}
              title="Сколько раз runtime пытался сменить идентичность мид-сессии"
            >
              блокировок: {snap.mutation_blocked_count}
            </span>
          )}
        </div>
      )}

      {/* Event counts — only when there's something to show */}
      {(counts.snapshot_captured + counts.updated + counts.slot_locked + counts.conflict_detected) >
        0 && (
        <div
          className="rounded-lg p-2.5 grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px]"
          style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)" }}
        >
          <div>
            <span style={{ color: "var(--text-muted)" }}>snapshot</span>
            <div className="font-mono" style={{ color: "var(--text-primary)" }}>
              {counts.snapshot_captured}
            </div>
          </div>
          <div>
            <span style={{ color: "var(--text-muted)" }}>updated</span>
            <div className="font-mono" style={{ color: "var(--text-primary)" }}>
              {counts.updated}
            </div>
          </div>
          <div>
            <span style={{ color: "var(--text-muted)" }}>slots locked</span>
            <div
              className="font-mono"
              style={{
                color:
                  counts.slot_locked > 0
                    ? "var(--success)"
                    : "var(--text-primary)",
              }}
            >
              {counts.slot_locked}
            </div>
          </div>
          <div>
            <span style={{ color: "var(--text-muted)" }}>conflicts</span>
            <div
              className="font-mono"
              style={{
                color:
                  counts.conflict_detected > 0
                    ? "var(--warning)"
                    : "var(--text-primary)",
              }}
            >
              {counts.conflict_detected}
            </div>
          </div>
        </div>
      )}

      <div
        className="text-[10px] flex items-center gap-1"
        style={{ color: "var(--text-muted)" }}
      >
        <CheckCircle2 size={9} />
        За последние {data.event_counts_window_days} дн.
      </div>
    </motion.div>
  );
}
