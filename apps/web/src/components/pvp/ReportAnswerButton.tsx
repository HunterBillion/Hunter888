"use client";

/**
 * ReportAnswerButton — кнопка «Пожаловаться» в verdict-bubble + модалка
 * жалобы на ответ AI. PR-14 redesign (2026-05-07): полная переработка
 * после фидбека пилота — кнопка стала заметной, модалка читаемой,
 * добавлены success-state, ESC, и понятный текст в disabled-варианте.
 *
 * Flow:
 *   click → modal opens
 *   user types reason 3..500 chars
 *   submit → POST /api/knowledge/answers/{id}/report
 *   success → modal shows ✓ confirmation 1.5s → closes
 *   error → toast + button stays clickable (idempotent backend)
 *
 * Idempotent: backend дедуплицирует по (answer, reporter), второй POST
 * возвращает первую запись. UI после первого успеха блокирует кнопку
 * («✓ Жалоба отправлена») чтобы не плодить click-noise.
 */

import { useState, useCallback, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Flag, X, Loader2, CheckCircle2 } from "lucide-react";
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
  const [success, setSuccess] = useState(false);

  // ESC closes the modal (PR-14 fix). Was a frequent UX complaint —
  // mobile users tap outside but desktop users want ESC.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !submitting) setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, submitting]);

  // Reset reason when modal closes
  useEffect(() => {
    if (!open) {
      // small delay so the closing animation doesn't show empty state
      const t = setTimeout(() => {
        if (!success) setReason("");
        setSuccess(false);
      }, 250);
      return () => clearTimeout(t);
    }
  }, [open, success]);

  const submit = useCallback(async () => {
    const trimmed = reason.trim();
    if (trimmed.length < 3 || submitting) return;
    setSubmitting(true);
    try {
      await api.post(`/knowledge/answers/${answerId}/report`, {
        reason: trimmed.slice(0, 500),
      });
      setSubmitted(true);
      setSuccess(true);
      // Show ✓ confirmation inside the modal for 1.5s, then close.
      setTimeout(() => setOpen(false), 1500);
      useNotificationStore.getState().addToast({
        title: "Жалоба отправлена",
        body: "Методолог получил вашу жалобу.",
        type: "info",
      });
    } catch (e) {
      logger.error("Report answer failed:", e);
      useNotificationStore.getState().addToast({
        title: "Не удалось отправить",
        body: "Проверьте подключение и попробуйте ещё раз.",
        type: "error",
      });
    } finally {
      setSubmitting(false);
    }
  }, [answerId, reason, submitting]);

  // ── Кнопка ──────────────────────────────────────────────────────────
  // PR-14: была мелкая невидимая dashed-полоска. Теперь — выраженный
  // оранжевый chip с иконкой и текстом. Привлекает внимание ровно столько,
  // сколько нужно (нерекламно), но юзер сразу видит что есть.
  const buttonContent = submitted
    ? (
      <>
        <CheckCircle2 size={14} />
        <span>Жалоба отправлена</span>
      </>
    )
    : (
      <>
        <Flag size={14} />
        <span>Пожаловаться на ответ AI</span>
      </>
    );

  return (
    <>
      <motion.button
        type="button"
        onClick={() => setOpen(true)}
        disabled={disabled || submitted}
        whileHover={!disabled && !submitted ? { x: -1, y: -1 } : undefined}
        whileTap={!disabled && !submitted ? { x: 1, y: 1 } : undefined}
        className="mt-3 inline-flex items-center gap-2 px-3 py-2 font-pixel uppercase text-[11px]"
        style={{
          color: submitted ? "var(--success)" : "var(--warning)",
          background: submitted
            ? "color-mix(in srgb, var(--success) 12%, transparent)"
            : "color-mix(in srgb, var(--warning) 12%, transparent)",
          border: `2px solid ${submitted ? "var(--success)" : "var(--warning)"}`,
          borderRadius: 0,
          letterSpacing: "0.12em",
          boxShadow: submitted
            ? "2px 2px 0 0 var(--success)"
            : "2px 2px 0 0 var(--warning)",
          cursor: disabled || submitted ? "default" : "pointer",
          opacity: disabled ? 0.4 : 1,
          transition: "background 120ms",
        }}
        title={
          submitted
            ? "Жалоба уже отправлена методологу"
            : "Открыть форму жалобы — если ответ AI неверный или вне закона"
        }
      >
        {buttonContent}
      </motion.button>

      {/* ── Модалка ────────────────────────────────────────────────── */}
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4"
            style={{ background: "rgba(0,0,0,0.7)", backdropFilter: "blur(2px)" }}
            onClick={() => !submitting && setOpen(false)}
            role="dialog"
            aria-modal="true"
            aria-labelledby="report-modal-title"
          >
            <motion.div
              initial={{ scale: 0.94, y: 16, opacity: 0 }}
              animate={{ scale: 1, y: 0, opacity: 1 }}
              exit={{ scale: 0.96, y: 8, opacity: 0 }}
              transition={{ type: "spring", stiffness: 300, damping: 24 }}
              onClick={(e) => e.stopPropagation()}
              className="w-full max-w-lg overflow-hidden"
              style={{
                background: "var(--bg-panel)",
                border: "2px solid var(--accent)",
                boxShadow: "6px 6px 0 0 #000, 0 0 24px var(--accent-glow)",
                borderRadius: 0,
              }}
            >
              {/* Header */}
              <div
                className="flex items-center justify-between px-5 py-3"
                style={{
                  background: "color-mix(in srgb, var(--warning) 12%, var(--bg-panel))",
                  borderBottom: "2px solid var(--warning)",
                }}
              >
                <h3
                  id="report-modal-title"
                  className="flex items-center gap-2 font-pixel uppercase tracking-widest"
                  style={{ color: "var(--warning)", fontSize: 13, letterSpacing: "0.18em" }}
                >
                  <Flag size={16} />
                  Жалоба на ответ AI
                </h3>
                <button
                  type="button"
                  onClick={() => !submitting && setOpen(false)}
                  disabled={submitting}
                  className="flex items-center justify-center w-8 h-8 transition-colors"
                  style={{
                    color: "var(--text-muted)",
                    background: "transparent",
                    border: "1px solid var(--border-color)",
                    borderRadius: 0,
                  }}
                  title="Закрыть (ESC)"
                  aria-label="Закрыть"
                >
                  <X size={16} />
                </button>
              </div>

              {/* Body — либо форма, либо success-state ────────────── */}
              {success ? (
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="flex flex-col items-center text-center gap-3 px-6 py-10"
                >
                  <CheckCircle2 size={48} style={{ color: "var(--success)" }} />
                  <h4 className="font-pixel uppercase text-base tracking-widest" style={{ color: "var(--success)" }}>
                    Жалоба отправлена
                  </h4>
                  <p className="text-sm leading-relaxed max-w-sm" style={{ color: "var(--text-secondary)" }}>
                    Методолог получил жалобу и проверит вопрос. Спасибо что помогаете улучшать AI.
                  </p>
                </motion.div>
              ) : (
                <div className="px-5 py-4">
                  <p className="text-sm leading-relaxed mb-3" style={{ color: "var(--text-primary)" }}>
                    Опишите что не так с ответом AI:
                  </p>
                  <ul className="text-xs mb-3 space-y-1" style={{ color: "var(--text-muted)" }}>
                    <li>• AI цитирует неверную статью закона</li>
                    <li>• Ответ противоречит ФЗ-127</li>
                    <li>• Не учитывает важный нюанс</li>
                    <li>• Сам вопрос некорректный или устаревший</li>
                  </ul>
                  <textarea
                    value={reason}
                    onChange={(e) => setReason(e.target.value.slice(0, 500))}
                    placeholder="Например: AI назвал ст. 213.3 п. 5, но в актуальной редакции этого пункта нет — есть только пункты 1-4"
                    rows={5}
                    disabled={submitting}
                    autoFocus
                    className="w-full px-3 py-2 text-sm leading-relaxed"
                    style={{
                      background: "var(--bg-secondary, var(--input-bg))",
                      color: "var(--text-primary)",
                      border: "2px solid var(--border-color)",
                      borderRadius: 0,
                      resize: "vertical",
                      minHeight: 100,
                      fontFamily: "system-ui, -apple-system, sans-serif",
                      lineHeight: 1.5,
                      outline: "none",
                    }}
                    onFocus={(e) => {
                      e.currentTarget.style.borderColor = "var(--accent)";
                    }}
                    onBlur={(e) => {
                      e.currentTarget.style.borderColor = "var(--border-color)";
                    }}
                  />
                  <div className="mt-2 flex items-center justify-between">
                    <span
                      className="font-pixel text-[11px] uppercase tracking-wider"
                      style={{ color: reason.length < 3 ? "var(--text-muted)" : "var(--success)" }}
                    >
                      {reason.length} / 500 символов{reason.length > 0 && reason.length < 3 ? " (минимум 3)" : ""}
                    </span>
                    <span className="font-pixel text-[10px] uppercase" style={{ color: "var(--text-muted)", letterSpacing: "0.14em" }}>
                      ESC чтобы закрыть
                    </span>
                  </div>
                </div>
              )}

              {/* Footer actions — скрываем когда success-state ─────── */}
              {!success && (
                <div
                  className="flex gap-2 justify-end px-5 py-3"
                  style={{ borderTop: "1px solid var(--border-color)" }}
                >
                  <motion.button
                    type="button"
                    onClick={() => !submitting && setOpen(false)}
                    disabled={submitting}
                    whileHover={!submitting ? { x: -1, y: -1 } : undefined}
                    whileTap={!submitting ? { x: 1, y: 1 } : undefined}
                    className="px-4 py-2 font-pixel uppercase text-xs tracking-widest"
                    style={{
                      background: "transparent",
                      color: "var(--text-secondary)",
                      border: "2px solid var(--border-color)",
                      borderRadius: 0,
                      cursor: submitting ? "not-allowed" : "pointer",
                      letterSpacing: "0.16em",
                    }}
                  >
                    Отмена
                  </motion.button>
                  <motion.button
                    type="button"
                    onClick={submit}
                    disabled={submitting || reason.trim().length < 3}
                    whileHover={!submitting && reason.trim().length >= 3 ? { x: -1, y: -1 } : undefined}
                    whileTap={!submitting && reason.trim().length >= 3 ? { x: 1, y: 1 } : undefined}
                    className="inline-flex items-center gap-2 px-5 py-2 font-pixel uppercase text-xs tracking-widest"
                    style={{
                      background: reason.trim().length >= 3 ? "var(--warning)" : "var(--bg-secondary, rgba(0,0,0,0.4))",
                      color: reason.trim().length >= 3 ? "#000" : "var(--text-muted)",
                      border: `2px solid ${reason.trim().length >= 3 ? "var(--warning)" : "var(--border-color)"}`,
                      borderRadius: 0,
                      cursor: submitting || reason.trim().length < 3 ? "not-allowed" : "pointer",
                      boxShadow: reason.trim().length >= 3 ? "3px 3px 0 0 #000" : undefined,
                      letterSpacing: "0.16em",
                    }}
                  >
                    {submitting
                      ? <Loader2 size={14} className="animate-spin" />
                      : <Flag size={14} />}
                    {submitting ? "Отправляем..." : "Отправить жалобу"}
                  </motion.button>
                </div>
              )}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
