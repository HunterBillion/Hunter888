"use client";

/**
 * KnowledgeReviewQueue — TZ-4 §8.3 admin review feed.
 *
 * Polls ``GET /admin/knowledge/queue`` for items in
 * ``knowledge_status='needs_review'`` (sorted by ``expires_at`` ASC,
 * NULLs last) and lets the operator transition each item via
 * ``POST /admin/knowledge/{id}/review`` — the only sanctioned path to
 * the ``outdated`` value per spec §8.3.1.
 *
 * Why not real-time WS yet:
 * The five ``knowledge_item.*`` events emitted by D4 are pre-registered
 * in the canonical event log but the WS fan-out for admin surfaces
 * isn't wired yet. Polling every 60s is fine for the volume — the
 * production ``legal_knowledge_chunks`` table has 375 rows total and
 * the queue starts at zero (no TTLs assigned yet through this UI).
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Flag,
  Loader2,
  RefreshCw,
  Shield,
  XCircle,
} from "lucide-react";
import { ApiError, api } from "@/lib/api";
import { sanitizeText } from "@/lib/sanitize";
import { logger } from "@/lib/logger";
import { formatDateFull } from "@/lib/utils";
import type {
  KnowledgeReviewActionResponse,
  KnowledgeReviewQueueItem,
} from "@/types";

const POLL_MS = 60_000;

type TargetStatus = "actual" | "disputed" | "outdated" | "needs_review";

const TARGET_LABELS: Record<TargetStatus, string> = {
  actual: "Актуально",
  disputed: "Спорно",
  outdated: "Устарело",
  needs_review: "На ревью (вернуть)",
};

const TARGET_ICONS: Record<TargetStatus, React.ReactNode> = {
  actual: <CheckCircle2 size={12} />,
  disputed: <AlertTriangle size={12} />,
  outdated: <XCircle size={12} />,
  needs_review: <Clock size={12} />,
};

const TARGET_TONES: Record<TargetStatus, string> = {
  actual: "var(--success)",
  disputed: "var(--warning)",
  outdated: "var(--danger)",
  needs_review: "var(--info)",
};

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return formatDateFull(iso);
  } catch {
    return iso;
  }
}

function staleDays(expires_at: string | null): number | null {
  if (!expires_at) return null;
  try {
    const ms = Date.now() - new Date(expires_at).getTime();
    return Math.floor(ms / 86_400_000);
  } catch {
    return null;
  }
}

type SourceFilter = "all" | "ttl" | "user_report";

export function KnowledgeReviewQueue() {
  const [items, setItems] = useState<KnowledgeReviewQueueItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actingOn, setActingOn] = useState<string | null>(null);
  const [drawerId, setDrawerId] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  // PR-6: source filter ("all" | "ttl" | "user_report").
  const [source, setSource] = useState<SourceFilter>("all");

  const load = useCallback(async () => {
    try {
      const rows = await api.get<KnowledgeReviewQueueItem[]>(
        `/admin/knowledge/queue?limit=50&source=${source}`,
      );
      setItems(Array.isArray(rows) ? rows : []);
      setError(null);
    } catch (err) {
      const msg =
        err instanceof ApiError || err instanceof Error
          ? err.message
          : "Не удалось загрузить очередь ревью";
      logger.error("[KnowledgeReviewQueue] fetch failed:", err);
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [source]);

  useEffect(() => {
    void load();
    const id = window.setInterval(() => {
      void load();
    }, POLL_MS);
    return () => window.clearInterval(id);
  }, [load]);

  // PR-6: resolve a user report (accept/reject). Separate from review
  // because a single report may reference multiple chunks; methodologist
  // still uses per-chunk review for status flips.
  const resolveReport = useCallback(
    async (reportId: string, decision: "accepted" | "rejected") => {
      if (actingOn) return;
      setActingOn(reportId);
      try {
        await api.post(`/admin/knowledge/reports/${reportId}/resolve`, {
          decision,
          note: reason.trim() || null,
        });
        setReason("");
        setDrawerId(null);
        await load();
      } catch (err) {
        const msg =
          err instanceof ApiError || err instanceof Error
            ? err.message
            : "Не удалось обработать жалобу";
        logger.error("[KnowledgeReviewQueue] resolve failed:", err);
        setError(msg);
      } finally {
        setActingOn(null);
      }
    },
    [actingOn, reason, load],
  );

  const handleReview = useCallback(
    async (chunkId: string, target: TargetStatus) => {
      if (actingOn) return;
      setActingOn(chunkId);
      try {
        await api.post<KnowledgeReviewActionResponse>(
          `/admin/knowledge/${chunkId}/review`,
          {
            new_status: target,
            reason: reason.trim() || null,
          },
        );
        setDrawerId(null);
        setReason("");
        await load();
      } catch (err) {
        const msg =
          err instanceof ApiError || err instanceof Error
            ? err.message
            : "Не удалось применить ревью";
        logger.error("[KnowledgeReviewQueue] review failed:", err);
        setError(msg);
      } finally {
        setActingOn(null);
      }
    },
    [actingOn, load, reason],
  );

  const queue = useMemo(() => items ?? [], [items]);

  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.18 }}
      className="space-y-4"
    >
      <header className="flex items-center justify-between">
        <div>
          <h2
            className="text-lg font-semibold flex items-center gap-2"
            style={{ color: "var(--text-primary)" }}
          >
            <Shield size={18} style={{ color: "var(--accent)" }} />
            Ревью знаний (TTL)
          </h2>
          <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
            Записи с статусом <code>needs_review</code>. Cron автоматически
            переводит сюда истёкшие <code>actual</code> элементы; перевод в
            <code className="mx-1">outdated</code> возможен ТОЛЬКО через эту очередь
            (спец. §8.3.1).
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="text-xs flex items-center gap-1.5 px-3 py-1.5 rounded-lg"
          style={{
            background: "var(--input-bg)",
            border: "1px solid var(--border-color)",
            color: "var(--text-muted)",
          }}
        >
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
          Обновить
        </button>
      </header>

      {/* PR-6: source filter pills */}
      <div className="flex items-center gap-1.5 text-xs" role="tablist" aria-label="Источник">
        {([
          { id: "all", label: "Все" },
          { id: "ttl", label: "TTL" },
          { id: "user_report", label: "Жалобы" },
        ] as { id: SourceFilter; label: string }[]).map((s) => {
          const active = source === s.id;
          return (
            <button
              key={s.id}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setSource(s.id)}
              className="px-2.5 py-1 rounded-md"
              style={{
                background: active ? "var(--accent)" : "var(--input-bg)",
                color: active ? "#fff" : "var(--text-muted)",
                border: `1px solid ${active ? "var(--accent)" : "var(--border-color)"}`,
              }}
            >
              {s.label}
            </button>
          );
        })}
      </div>

      {error && (
        <div
          className="rounded-lg px-3 py-2 text-sm flex items-start gap-2"
          style={{
            background: "color-mix(in srgb, var(--danger) 14%, transparent)",
            color: "var(--danger)",
          }}
        >
          <AlertTriangle size={14} className="mt-0.5 shrink-0" />
          <span>{sanitizeText(error)}</span>
        </div>
      )}

      {loading && queue.length === 0 ? (
        <div className="flex items-center gap-2 text-sm" style={{ color: "var(--text-muted)" }}>
          <Loader2 size={14} className="animate-spin" />
          Загружаем очередь…
        </div>
      ) : queue.length === 0 ? (
        <div
          className="rounded-lg p-6 text-center text-sm"
          style={{
            background: "var(--input-bg)",
            border: "1px dashed var(--border-color)",
            color: "var(--text-muted)",
          }}
        >
          Очередь пуста. Все законы и документы с TTL проверены или ещё актуальны.
        </div>
      ) : (
        <ul className="space-y-2">
          {queue.map((item) => {
            const stale = staleDays(item.expires_at);
            const isOpen = drawerId === item.id;
            // PR-6: user_report items have a different layout (Q+A+reason)
            // and a different action (resolve report, not chunk-status flip).
            if (item.source_kind === "user_report") {
              return (
                <li
                  key={item.id}
                  className="rounded-lg p-3"
                  style={{
                    background: "color-mix(in srgb, var(--warning) 6%, var(--glass-bg))",
                    border: "1px solid color-mix(in srgb, var(--warning) 30%, var(--glass-border))",
                  }}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <Flag size={13} style={{ color: "var(--warning)" }} />
                        <span
                          className="rounded px-1.5 py-0.5 text-[10px] font-mono"
                          style={{
                            background: "color-mix(in srgb, var(--warning) 14%, transparent)",
                            color: "var(--warning)",
                          }}
                        >
                          жалоба пользователя
                        </span>
                        {item.reported_at && (
                          <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                            {formatDate(item.reported_at)}
                          </span>
                        )}
                      </div>
                      <div className="mt-2 text-sm" style={{ color: "var(--text-primary)" }}>
                        <strong>Жалоба:</strong> «{sanitizeText(item.report_reason ?? "")}»
                      </div>
                      {item.answer_question && (
                        <div className="mt-2 text-[12px]" style={{ color: "var(--text-secondary)" }}>
                          <span style={{ color: "var(--text-muted)" }}>Вопрос: </span>
                          {sanitizeText(item.answer_question)}
                        </div>
                      )}
                      {item.answer_user_text && (
                        <div className="mt-1 text-[12px]" style={{ color: "var(--text-secondary)" }}>
                          <span style={{ color: "var(--text-muted)" }}>Ответ юзера: </span>
                          {sanitizeText(item.answer_user_text)}
                        </div>
                      )}
                      {item.answer_explanation && (
                        <div className="mt-1 text-[12px]" style={{ color: "var(--text-secondary)" }}>
                          <span style={{ color: "var(--text-muted)" }}>Вердикт AI: </span>
                          {sanitizeText(item.answer_explanation)}
                        </div>
                      )}
                      {item.linked_chunk_ids && item.linked_chunk_ids.length > 0 && (
                        <div className="mt-1 text-[11px]" style={{ color: "var(--text-muted)" }}>
                          AI цитировал чанки:{" "}
                          {item.linked_chunk_ids.map((c) => c.slice(0, 8)).join(", ")}
                          {" "}— используйте «Применить ревью» на нужном чанке отдельно.
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="mt-3 pt-3 border-t flex flex-wrap gap-2 items-center" style={{ borderColor: "var(--border-color)" }}>
                    <input
                      type="text"
                      value={drawerId === item.id ? reason : ""}
                      onChange={(e) => { setDrawerId(item.id); setReason(e.target.value); }}
                      maxLength={500}
                      placeholder="Комментарий методолога (опционально)"
                      className="flex-1 rounded-md p-1.5 text-sm"
                      style={{
                        background: "var(--input-bg)",
                        border: "1px solid var(--border-color)",
                        color: "var(--text-primary)",
                      }}
                    />
                    {item.report_id && (
                      <>
                        <button
                          type="button"
                          disabled={actingOn === item.report_id}
                          onClick={() => void resolveReport(item.report_id!, "accepted")}
                          className="text-xs flex items-center gap-1 px-3 py-1.5 rounded-lg disabled:opacity-50"
                          style={{
                            background: "color-mix(in srgb, var(--success) 14%, transparent)",
                            color: "var(--success)",
                            border: "1px solid var(--success)",
                          }}
                        >
                          <CheckCircle2 size={12} /> Принять
                        </button>
                        <button
                          type="button"
                          disabled={actingOn === item.report_id}
                          onClick={() => void resolveReport(item.report_id!, "rejected")}
                          className="text-xs flex items-center gap-1 px-3 py-1.5 rounded-lg disabled:opacity-50"
                          style={{
                            background: "color-mix(in srgb, var(--danger) 14%, transparent)",
                            color: "var(--danger)",
                            border: "1px solid var(--danger)",
                          }}
                        >
                          <XCircle size={12} /> Отклонить
                        </button>
                      </>
                    )}
                  </div>
                </li>
              );
            }
            return (
              <li
                key={item.id}
                className="rounded-lg p-3"
                style={{
                  background: "var(--glass-bg)",
                  border: "1px solid var(--glass-border)",
                }}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span
                        className="text-sm font-medium truncate"
                        style={{ color: "var(--text-primary)" }}
                      >
                        {sanitizeText(item.title ?? "(без названия)")}
                      </span>
                      <span
                        className="rounded px-1.5 py-0.5 text-[10px] font-mono"
                        style={{
                          background: "color-mix(in srgb, var(--info) 14%, transparent)",
                          color: "var(--info)",
                        }}
                      >
                        needs_review
                      </span>
                      {stale !== null && stale > 0 && (
                        <span
                          className="rounded px-1.5 py-0.5 text-[10px]"
                          style={{
                            background:
                              "color-mix(in srgb, var(--warning) 14%, transparent)",
                            color: "var(--warning)",
                          }}
                          title={`Истёк ${stale} дн. назад`}
                        >
                          истёк {stale}д
                        </span>
                      )}
                    </div>
                    <div
                      className="mt-1 text-[11px] flex items-center gap-3"
                      style={{ color: "var(--text-muted)" }}
                    >
                      <span>
                        TTL: {formatDate(item.expires_at)}
                      </span>
                      {item.reviewed_at && (
                        <span>Прошлое ревью: {formatDate(item.reviewed_at)}</span>
                      )}
                      {item.source_ref && (
                        <span className="truncate" title={item.source_ref}>
                          Источник: {sanitizeText(item.source_ref)}
                        </span>
                      )}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      setDrawerId(isOpen ? null : item.id);
                      setReason("");
                    }}
                    className="text-xs px-3 py-1.5 rounded-lg shrink-0"
                    style={{
                      background: "var(--accent-muted)",
                      color: "var(--accent)",
                      border: "1px solid var(--accent)",
                    }}
                  >
                    {isOpen ? "Свернуть" : "Применить ревью"}
                  </button>
                </div>

                {isOpen && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    transition={{ duration: 0.18 }}
                    className="mt-3 pt-3 border-t"
                    style={{ borderColor: "var(--border-color)" }}
                  >
                    <label
                      className="text-xs block mb-1.5"
                      style={{ color: "var(--text-muted)" }}
                    >
                      Комментарий (попадает в audit log + DomainEvent payload):
                    </label>
                    <textarea
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                      maxLength={2000}
                      rows={2}
                      className="w-full rounded-md p-2 text-sm"
                      style={{
                        background: "var(--input-bg)",
                        border: "1px solid var(--border-color)",
                        color: "var(--text-primary)",
                      }}
                      placeholder="Например: «закон редакция от 2020 утратила силу»"
                    />
                    <div className="mt-2.5 flex flex-wrap gap-2">
                      {(["actual", "disputed", "outdated"] as const).map((t) => (
                        <button
                          key={t}
                          type="button"
                          disabled={actingOn === item.id}
                          onClick={() => void handleReview(item.id, t)}
                          className="text-xs flex items-center gap-1 px-3 py-1.5 rounded-lg disabled:opacity-50"
                          style={{
                            background: "var(--input-bg)",
                            border: `1px solid ${TARGET_TONES[t]}`,
                            color: TARGET_TONES[t],
                          }}
                        >
                          {actingOn === item.id ? (
                            <Loader2 size={12} className="animate-spin" />
                          ) : (
                            TARGET_ICONS[t]
                          )}
                          {TARGET_LABELS[t]}
                        </button>
                      ))}
                    </div>
                    <p
                      className="mt-2 text-[10px]"
                      style={{ color: "var(--text-muted)" }}
                    >
                      «Устарело» — терминальное состояние; элемент исключается из RAG /
                      рекомендаций. «Актуально» — возвращает в общий пул.
                    </p>
                  </motion.div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </motion.section>
  );
}
