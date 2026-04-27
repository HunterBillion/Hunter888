"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import {
  Phone,
  PhoneIncoming,
  Mail,
  MessageSquare,
  Users,
  FileText,
  ArrowRightLeft,
  Shield,
  ShieldCheck,
  Settings,
  Clock,
  Copy,
  Paperclip,
  Target,
  RotateCcw,
  Loader2,
} from "lucide-react";
import type { ClientInteraction, InteractionType, ClientStatus } from "@/types";
import { CLIENT_STATUS_LABELS } from "@/types";
import { sanitizeText } from "@/lib/sanitize";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";

/** Translate raw status code → Russian label; fall through unknown codes. */
function statusLabel(code: string | null): string {
  if (!code) return "";
  return CLIENT_STATUS_LABELS[code as ClientStatus] ?? code;
}

const ICON_MAP: Record<InteractionType, typeof Phone> = {
  outbound_call: Phone,
  inbound_call: PhoneIncoming,
  sms_sent: MessageSquare,
  whatsapp_sent: MessageSquare,
  email_sent: Mail,
  meeting: Users,
  status_change: ArrowRightLeft,
  consent_event: Shield,
  note: FileText,
  system: Settings,
};

const TYPE_LABELS: Record<InteractionType, string> = {
  outbound_call: "Исходящий",
  inbound_call: "Входящий",
  sms_sent: "SMS",
  whatsapp_sent: "WhatsApp",
  email_sent: "Email",
  meeting: "Встреча",
  status_change: "Смена статуса",
  consent_event: "Согласие",
  note: "Заметка",
  system: "Система",
};

interface ClientTimelineProps {
  interactions: ClientInteraction[];
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}с`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return s > 0 ? `${m}м ${s}с` : `${m}м`;
}

/** Group interactions into buckets: Today, Yesterday, This week, Older. */
function groupByBucket(interactions: ClientInteraction[]): { label: string; items: ClientInteraction[] }[] {
  const now = new Date();
  const todayKey = now.toISOString().slice(0, 10);
  const yesterday = new Date(now.getTime() - 86_400_000);
  const yesterdayKey = yesterday.toISOString().slice(0, 10);
  const weekAgo = new Date(now.getTime() - 7 * 86_400_000);

  const buckets: Record<string, ClientInteraction[]> = {
    today: [],
    yesterday: [],
    week: [],
    older: [],
  };

  for (const item of interactions) {
    const itemDate = new Date(item.created_at);
    const itemKey = itemDate.toISOString().slice(0, 10);
    if (itemKey === todayKey) buckets.today.push(item);
    else if (itemKey === yesterdayKey) buckets.yesterday.push(item);
    else if (itemDate > weekAgo) buckets.week.push(item);
    else buckets.older.push(item);
  }

  const out: { label: string; items: ClientInteraction[] }[] = [];
  if (buckets.today.length) out.push({ label: "Сегодня", items: buckets.today });
  if (buckets.yesterday.length) out.push({ label: "Вчера", items: buckets.yesterday });
  if (buckets.week.length) out.push({ label: "На этой неделе", items: buckets.week });
  if (buckets.older.length) out.push({ label: "Ранее", items: buckets.older });
  return out;
}

export function ClientTimeline({ interactions }: ClientTimelineProps) {
  // 2026-04-23 Sprint 6 — replay mini-button state per row. Key = interaction id.
  const router = useRouter();
  const [replayingId, setReplayingId] = useState<string | null>(null);

  const handleReplay = async (
    interactionId: string,
    trainingSessionId: string,
    sessionMode: "call" | "chat",
  ) => {
    if (replayingId) return;
    setReplayingId(interactionId);
    try {
      const session = await api.post<{ id: string }>("/training/sessions", {
        clone_from_session_id: trainingSessionId,
      });
      if (!session?.id) throw new Error("Сервер не вернул id сессии");
      if (sessionMode === "call") {
        router.push(`/training/${session.id}/call`);
      } else {
        router.push(`/training/${session.id}`);
      }
    } catch (err) {
      logger.error("[ClientTimeline] replay failed:", err);
      setReplayingId(null);
    }
  };

  if (!interactions.length) {
    return (
      <div className="text-center py-8">
        <span className="text-sm" style={{ color: "var(--text-muted)" }}>Нет взаимодействий</span>
      </div>
    );
  }

  const grouped = groupByBucket(interactions);

  return (
    <div className="space-y-5">
      {grouped.map((bucket) => (
        <div key={bucket.label}>
          <div
            className="text-[10px] font-semibold uppercase tracking-widest mb-3 pb-1 border-b"
            style={{ color: "var(--text-muted)", borderColor: "var(--border-color)" }}
          >
            {bucket.label} · {bucket.items.length}
          </div>

          <div className="relative pl-6">
            {/* Vertical line */}
            <div
              className="absolute left-[9px] top-2 bottom-2 w-px"
              style={{ background: "var(--border-color)" }}
            />

            {bucket.items.map((item, i) => {
              // 2026-04-23 Sprint 6 — training interactions stamp
              // metadata.training_session_id; we detect them here so the
              // row can show a Target icon + «Повторить» mini-button.
              const trainingSessionId = item.metadata?.training_session_id;
              const isTraining = !!trainingSessionId;
              const trainingMode: "call" | "chat" =
                item.metadata?.session_mode === "call" ? "call" : "chat";
              const declined = item.metadata?.declined === true;

              // TZ-4 §13.4.1 — attachment system rows carry
              // `metadata.attachment_id` (set by `attachment_pipeline.
              // ingest_upload`). Detect them so the row can render
              // a Paperclip + filename + duplicate/verified chip
              // instead of a generic ⚙ Settings icon.
              const attachmentId =
                typeof item.metadata?.attachment_id === "string"
                  ? (item.metadata.attachment_id as string)
                  : null;
              const isAttachment = !!attachmentId;
              const attachmentFilename =
                typeof item.metadata?.filename === "string"
                  ? (item.metadata.filename as string)
                  : null;
              const isDuplicate = item.metadata?.duplicate_of != null;

              const Icon = isAttachment
                ? Paperclip
                : isTraining
                  ? Target
                  : ICON_MAP[item.interaction_type] || FileText;
              const dateStr = new Date(item.created_at).toLocaleTimeString("ru-RU", {
                hour: "2-digit",
                minute: "2-digit",
              });
              const isStatusChange =
                item.interaction_type === "status_change" && item.old_status && item.new_status;
              const hasDuration =
                (item.interaction_type === "outbound_call" || item.interaction_type === "inbound_call") &&
                item.duration_seconds &&
                item.duration_seconds > 0;

              const typeLabel = isAttachment
                ? isDuplicate
                  ? "Документ (повтор)"
                  : "Документ"
                : isTraining
                  ? declined
                    ? "Отклонён звонок"
                    : trainingMode === "call"
                      ? "Тренировка (звонок)"
                      : "Тренировка (чат)"
                  : TYPE_LABELS[item.interaction_type];

              return (
                <motion.div
                  key={item.id}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.03 }}
                  className="relative pb-4 last:pb-0"
                >
                  {/* Dot */}
                  <div
                    className="absolute -left-6 top-1 w-[18px] h-[18px] rounded-full flex items-center justify-center"
                    style={{ background: "var(--bg-secondary)", border: "2px solid var(--accent)" }}
                  >
                    <Icon size={9} style={{ color: "var(--accent)" }} />
                  </div>

                  {/* Content */}
                  <div className="ml-2">
                    <div className="flex items-center flex-wrap gap-2">
                      <span className="text-xs font-mono" style={{ color: "var(--accent)" }}>
                        {typeLabel}
                      </span>
                      <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                        {dateStr}
                      </span>
                      {hasDuration && (
                        <span className="inline-flex items-center gap-1 text-[10px] font-mono px-1.5 py-0.5 rounded" style={{
                          background: "var(--input-bg)",
                          color: "var(--text-muted)",
                        }}>
                          <Clock size={9} /> {formatDuration(item.duration_seconds!)}
                        </span>
                      )}
                    </div>

                    {isStatusChange ? (
                      <p className="text-sm mt-0.5 flex items-center gap-1.5 flex-wrap" style={{ color: "var(--text-primary)" }}>
                        <span className="px-1.5 py-0.5 rounded text-[11px]" style={{ background: "var(--input-bg)", color: "var(--text-muted)" }}>
                          {statusLabel(item.old_status)}
                        </span>
                        <ArrowRightLeft size={10} style={{ color: "var(--accent)" }} />
                        <span className="px-1.5 py-0.5 rounded text-[11px]" style={{ background: "var(--accent-muted)", color: "var(--accent)" }}>
                          {statusLabel(item.new_status)}
                        </span>
                        {item.content && (
                          <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                            — {sanitizeText(item.content)}
                          </span>
                        )}
                      </p>
                    ) : (
                      <p className="text-sm mt-0.5" style={{ color: "var(--text-primary)" }}>
                        {sanitizeText(item.content ?? "")}
                      </p>
                    )}

                    {item.result && (
                      <p className="text-xs mt-0.5 italic" style={{ color: "var(--text-muted)" }}>
                        Результат: {sanitizeText(item.result)}
                      </p>
                    )}

                    {/* TZ-4 §13.4.1 — attachment row badges. Render
                        the filename + dedup/verification chips so the
                        manager can scan the timeline without opening
                        the attachments panel. */}
                    {isAttachment && (
                      <div className="mt-1 flex flex-wrap gap-1.5 text-[10px]">
                        {attachmentFilename && (
                          <span
                            className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 font-mono"
                            style={{ background: "var(--input-bg)", color: "var(--text-muted)" }}
                            title={attachmentFilename}
                          >
                            <FileText size={9} />
                            {sanitizeText(attachmentFilename)}
                          </span>
                        )}
                        {isDuplicate && (
                          <span
                            className="inline-flex items-center gap-1 rounded px-1.5 py-0.5"
                            style={{
                              background: "color-mix(in srgb, var(--warning) 14%, transparent)",
                              color: "var(--warning)",
                            }}
                            title="Файл с тем же sha256 уже был получен ранее"
                          >
                            <Copy size={9} />
                            дубликат
                          </span>
                        )}
                        {item.metadata?.verification_status === "verified" && (
                          <span
                            className="inline-flex items-center gap-1 rounded px-1.5 py-0.5"
                            style={{
                              background: "color-mix(in srgb, var(--success) 14%, transparent)",
                              color: "var(--success)",
                            }}
                          >
                            <ShieldCheck size={9} />
                            проверен
                          </span>
                        )}
                      </div>
                    )}

                    {item.manager_name && (
                      <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                        {sanitizeText(item.manager_name)}
                      </span>
                    )}

                    {/* 2026-04-23 Sprint 6 — replay mini-chip for training
                        interactions. Disabled when the source session was
                        declined (abandoned) — nothing to clone usefully. */}
                    {isTraining && trainingSessionId && (
                      <div className="mt-1.5">
                        <motion.button
                          type="button"
                          onClick={() => handleReplay(item.id, trainingSessionId, trainingMode)}
                          disabled={declined || replayingId === item.id}
                          whileTap={{ scale: 0.96 }}
                          className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-1 rounded-md transition disabled:opacity-40 disabled:cursor-not-allowed"
                          style={{
                            color: "var(--accent)",
                            background: "color-mix(in srgb, var(--accent) 10%, transparent)",
                            border: "1px solid color-mix(in srgb, var(--accent) 35%, transparent)",
                          }}
                          title={
                            declined
                              ? "Сессия была отклонена — повтор недоступен"
                              : "Повторить с теми же параметрами"
                          }
                        >
                          {replayingId === item.id ? (
                            <Loader2 size={10} className="animate-spin" />
                          ) : (
                            <RotateCcw size={10} />
                          )}
                          Повторить
                        </motion.button>
                      </div>
                    )}
                  </div>
                </motion.div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
