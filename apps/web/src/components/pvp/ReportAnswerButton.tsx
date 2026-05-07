"use client";

/**
 * ReportAnswerButton — small Flag button + modal for the quiz verdict bubble.
 *
 * PR-6 (Issue: AI «тупит / уходит от закона»). User reads an AI verdict
 * in /pvp/quiz, disagrees, clicks Flag, types reason → POST
 * /api/knowledge/answers/{answerId}/report. The report lands in the
 * methodologist KnowledgeReviewQueue (Variant B) under the
 * `source=user_report` filter.
 *
 * Idempotent on the backend: a second click for the same (answer, user)
 * returns the existing record. We still UI-disable after first POST
 * to give clear "uже отправлено" feedback.
 */

import { useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Flag, X, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";
import { useNotificationStore } from "@/stores/useNotificationStore";

interface Props {
  answerId: string;
  /** Disable when missing — older verdict events don't carry answer_id. */
  disabled?: boolean;
}

export function ReportAnswerButton({ answerId, disabled }: Props) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const submit = useCallback(async () => {
    if (!reason.trim() || submitting) return;
    setSubmitting(true);
    try {
      await api.post(`/knowledge/answers/${answerId}/report`, {
        reason: reason.trim().slice(0, 500),
      });
      setSubmitted(true);
      setOpen(false);
      useNotificationStore.getState().addToast({
        title: "Жалоба отправлена",
        body: "Методолог разберёт. Спасибо за обратную связь.",
        type: "info",
      });
    } catch (e) {
      logger.error("Report answer failed:", e);
      useNotificationStore.getState().addToast({
        title: "Ошибка",
        body: "Не удалось отправить жалобу. Попробуйте позже.",
        type: "error",
      });
    } finally {
      setSubmitting(false);
    }
  }, [answerId, reason, submitting]);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        disabled={disabled || submitted}
        title={submitted ? "Жалоба отправлена" : "Пожаловаться на ответ AI"}
        className="mt-2 inline-flex items-center gap-1.5 px-2 py-1 font-pixel text-[11px] uppercase tracking-wider transition-opacity"
        style={{
          color: submitted ? "var(--text-muted)" : "var(--text-muted)",
          background: "transparent",
          border: "1px dashed var(--border-color)",
          borderRadius: 0,
          cursor: disabled || submitted ? "default" : "pointer",
          opacity: disabled ? 0.4 : 1,
        }}
      >
        <Flag size={11} />
        {submitted ? "Жалоба отправлена" : "Пожаловаться"}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4"
            style={{ background: "rgba(0,0,0,0.6)" }}
            onClick={() => !submitting && setOpen(false)}
          >
            <motion.div
              initial={{ scale: 0.96, y: 8 }}
              animate={{ scale: 1, y: 0 }}
              exit={{ scale: 0.96, y: 8 }}
              transition={{ duration: 0.15 }}
              onClick={(e) => e.stopPropagation()}
              className="w-full max-w-md p-5"
              style={{
                background: "var(--bg-panel)",
                outline: "2px solid var(--accent)",
                outlineOffset: -2,
                boxShadow: "4px 4px 0 0 var(--accent)",
                borderRadius: 0,
              }}
            >
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-pixel uppercase tracking-widest" style={{ color: "var(--text-primary)", fontSize: 14 }}>
                  ▸ Пожаловаться на ответ
                </h3>
                <button
                  type="button"
                  onClick={() => !submitting && setOpen(false)}
                  className="p-1"
                  style={{ color: "var(--text-muted)" }}
                  aria-label="Закрыть"
                >
                  <X size={16} />
                </button>
              </div>
              <p className="text-sm mb-3" style={{ color: "var(--text-secondary)" }}>
                Что не так с ответом AI? (3–500 символов)
              </p>
              <textarea
                value={reason}
                onChange={(e) => setReason(e.target.value.slice(0, 500))}
                placeholder="Например: цитирует не ту статью / не учитывает поправки / противоречит ФЗ-127"
                rows={4}
                disabled={submitting}
                className="w-full p-2 font-mono text-sm"
                style={{
                  background: "var(--input-bg)",
                  color: "var(--text-primary)",
                  border: "1px solid var(--border-color)",
                  borderRadius: 0,
                  resize: "vertical",
                }}
              />
              <div className="mt-2 flex items-center justify-between text-[11px] font-pixel uppercase" style={{ color: "var(--text-muted)" }}>
                <span>{reason.length}/500</span>
                <span>отправляется методологу</span>
              </div>
              <div className="mt-4 flex gap-2 justify-end">
                <button
                  type="button"
                  onClick={() => !submitting && setOpen(false)}
                  disabled={submitting}
                  className="px-3 py-2 font-pixel uppercase text-[12px]"
                  style={{
                    background: "transparent",
                    color: "var(--text-secondary)",
                    border: "2px solid var(--border-color)",
                    borderRadius: 0,
                    cursor: submitting ? "not-allowed" : "pointer",
                  }}
                >
                  Отмена
                </button>
                <button
                  type="button"
                  onClick={submit}
                  disabled={submitting || reason.trim().length < 3}
                  className="px-4 py-2 font-pixel uppercase text-[12px] inline-flex items-center gap-2"
                  style={{
                    background: reason.trim().length < 3 ? "var(--bg-secondary)" : "var(--accent)",
                    color: reason.trim().length < 3 ? "var(--text-muted)" : "#fff",
                    border: `2px solid ${reason.trim().length < 3 ? "var(--border-color)" : "var(--accent)"}`,
                    borderRadius: 0,
                    cursor: submitting || reason.trim().length < 3 ? "not-allowed" : "pointer",
                    boxShadow: reason.trim().length < 3 ? undefined : "3px 3px 0 0 #000",
                  }}
                >
                  {submitting ? <Loader2 size={14} className="animate-spin" /> : <Flag size={14} />}
                  Отправить
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
