"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, Loader2, Bell } from "lucide-react";
import { api } from "@/lib/api";
import { useFocusTrap } from "@/hooks/useFocusTrap";

interface ReminderCreateModalProps {
  open: boolean;
  clientId: string;
  clientName: string;
  onClose: () => void;
  onCreated: () => void;
}

export function ReminderCreateModal({ open, clientId, clientName, onClose, onCreated }: ReminderCreateModalProps) {
  const focusTrapRef = useFocusTrap(open, onClose);
  const [remindAt, setRemindAt] = useState("");
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const resetForm = () => {
    setRemindAt("");
    setMessage("");
    setError(null);
  };

  const handleClose = () => {
    resetForm();
    onClose();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!remindAt) {
      setError("Выберите дату и время");
      return;
    }
    const dt = new Date(remindAt);
    if (dt <= new Date()) {
      setError("Время должно быть в будущем");
      return;
    }
    if (message.length > 500) {
      setError("Сообщение не более 500 символов");
      return;
    }

    setSaving(true);
    setError(null);
    try {
      await api.post("/reminders", {
        client_id: clientId,
        remind_at: dt.toISOString(),
        message: message.trim() || undefined,
      });
      onCreated();
      handleClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка создания");
    } finally {
      setSaving(false);
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[100] flex items-center justify-center p-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <motion.div
            className="absolute inset-0"
            style={{ background: "rgba(0,0,0,0.6)", backdropFilter: "blur(4px)" }}
            onClick={handleClose}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          />

          <motion.div
            ref={focusTrapRef}
            role="dialog"
            aria-modal="true"
            aria-label="Создание напоминания"
            className="relative w-full max-w-sm rounded-2xl p-6"
            style={{
              background: "var(--bg-secondary, var(--bg-primary))",
              border: "1px solid var(--border-color)",
              boxShadow: "0 24px 80px rgba(0,0,0,0.4)",
            }}
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            transition={{ duration: 0.2, ease: [0.4, 0, 0.2, 1] }}
          >
            <div className="flex items-center justify-between mb-5">
              <div className="flex items-center gap-2">
                <Bell size={18} style={{ color: "var(--accent)" }} />
                <h2 className="font-display text-lg font-bold" style={{ color: "var(--text-primary)" }}>
                  Напоминание
                </h2>
              </div>
              <motion.button onClick={handleClose} aria-label="Закрыть" style={{ color: "var(--text-muted)" }} whileTap={{ scale: 0.9 }}>
                <X size={18} />
              </motion.button>
            </div>

            <div className="text-xs mb-4 px-3 py-2 rounded-lg" style={{ background: "var(--input-bg)", color: "var(--text-secondary)" }}>
              Клиент: <span style={{ color: "var(--text-primary)" }}>{clientName}</span>
            </div>

            {error && (
              <div className="rounded-lg p-3 mb-4 text-xs" style={{ background: "rgba(255,68,68,0.1)", color: "var(--danger, #FF4444)" }}>
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-mono mb-1.5" style={{ color: "var(--text-muted)" }}>КОГДА *</label>
                <input
                  type="datetime-local"
                  aria-label="Дата и время напоминания"
                  value={remindAt}
                  onChange={(e) => setRemindAt(e.target.value)}
                  className="vh-input w-full"
                  required
                />
              </div>

              <div>
                <label className="block text-xs font-mono mb-1.5" style={{ color: "var(--text-muted)" }}>
                  СООБЩЕНИЕ <span className="text-[9px]" style={{ color: "var(--text-muted)" }}>({message.length}/500)</span>
                </label>
                <textarea
                  aria-label="Сообщение напоминания"
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  placeholder="О чём напомнить..."
                  className="vh-input w-full"
                  rows={3}
                  maxLength={500}
                  style={{ resize: "vertical" }}
                />
              </div>

              <motion.button
                type="submit"
                disabled={saving}
                className="vh-btn-primary w-full flex items-center justify-center gap-2 py-3"
                whileTap={{ scale: 0.97 }}
              >
                {saving ? <Loader2 size={16} className="animate-spin" /> : <Bell size={16} />}
                Создать напоминание
              </motion.button>
            </form>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
