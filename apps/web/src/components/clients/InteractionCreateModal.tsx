"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, Loader2, MessageSquarePlus } from "lucide-react";
import { api } from "@/lib/api";

const INTERACTION_TYPES = [
  { value: "outbound_call", label: "Исходящий звонок" },
  { value: "inbound_call", label: "Входящий звонок" },
  { value: "meeting", label: "Встреча" },
  { value: "note", label: "Заметка" },
  { value: "sms_sent", label: "SMS" },
  { value: "whatsapp_sent", label: "WhatsApp" },
  { value: "email_sent", label: "Email" },
];

const CALL_TYPES = ["outbound_call", "inbound_call"];

interface InteractionCreateModalProps {
  open: boolean;
  clientId: string;
  initialType?: string;
  onClose: () => void;
  onCreated: () => void;
}

export function InteractionCreateModal({
  open,
  clientId,
  initialType = "outbound_call",
  onClose,
  onCreated,
}: InteractionCreateModalProps) {
  const [type, setType] = useState(initialType);
  const [content, setContent] = useState("");
  const [result, setResult] = useState("");
  const [durationMin, setDurationMin] = useState("");
  const [durationSec, setDurationSec] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isCall = CALL_TYPES.includes(type);

  useEffect(() => {
    if (open) {
      setType(initialType);
    }
  }, [initialType, open]);

  const resetForm = () => {
    setType(initialType);
    setContent("");
    setResult("");
    setDurationMin("");
    setDurationSec("");
    setError(null);
  };

  const handleClose = () => {
    resetForm();
    onClose();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);

    try {
      const body: Record<string, unknown> = {
        interaction_type: type,
      };
      if (content.trim()) body.content = content.trim();
      if (result.trim()) body.result = result.trim();
      if (isCall && (durationMin || durationSec)) {
        body.duration_seconds = (parseInt(durationMin || "0") * 60) + parseInt(durationSec || "0");
      }

      await api.post(`/clients/${clientId}/interactions`, body);
      onCreated();
      handleClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка сохранения");
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
            className="relative w-full max-w-md rounded-2xl p-6"
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
                <MessageSquarePlus size={18} style={{ color: "var(--accent)" }} />
                <h2 className="font-display text-lg font-bold" style={{ color: "var(--text-primary)" }}>
                  Запись взаимодействия
                </h2>
              </div>
              <motion.button onClick={handleClose} style={{ color: "var(--text-muted)" }} whileTap={{ scale: 0.9 }}>
                <X size={18} />
              </motion.button>
            </div>

            {error && (
              <div className="rounded-lg p-3 mb-4 text-xs" style={{ background: "rgba(255,68,68,0.1)", color: "var(--danger, #FF4444)" }}>
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-mono mb-1.5" style={{ color: "var(--text-muted)" }}>ТИП *</label>
                <select value={type} onChange={(e) => setType(e.target.value)} className="vh-input w-full">
                  {INTERACTION_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
                </select>
              </div>

              <div>
                <label className="block text-xs font-mono mb-1.5" style={{ color: "var(--text-muted)" }}>ОПИСАНИЕ</label>
                <textarea
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  placeholder="Что обсуждали, итог разговора..."
                  className="vh-input w-full"
                  rows={3}
                  style={{ resize: "vertical" }}
                />
              </div>

              <div>
                <label className="block text-xs font-mono mb-1.5" style={{ color: "var(--text-muted)" }}>РЕЗУЛЬТАТ</label>
                <input
                  type="text"
                  value={result}
                  onChange={(e) => setResult(e.target.value)}
                  placeholder="Перезвонить, записан на консультацию, отказ..."
                  className="vh-input w-full"
                />
              </div>

              {/* Duration for calls */}
              {isCall && (
                <div>
                  <label className="block text-xs font-mono mb-1.5" style={{ color: "var(--text-muted)" }}>ДЛИТЕЛЬНОСТЬ</label>
                  <div className="flex items-center gap-2">
                    <input
                      type="number"
                      value={durationMin}
                      onChange={(e) => setDurationMin(e.target.value)}
                      placeholder="0"
                      className="vh-input w-20 text-center"
                      min={0}
                    />
                    <span className="text-xs" style={{ color: "var(--text-muted)" }}>мин</span>
                    <input
                      type="number"
                      value={durationSec}
                      onChange={(e) => setDurationSec(e.target.value)}
                      placeholder="0"
                      className="vh-input w-20 text-center"
                      min={0}
                      max={59}
                    />
                    <span className="text-xs" style={{ color: "var(--text-muted)" }}>сек</span>
                  </div>
                </div>
              )}

              <motion.button
                type="submit"
                disabled={saving}
                className="vh-btn-primary w-full flex items-center justify-center gap-2 py-3"
                whileTap={{ scale: 0.97 }}
              >
                {saving ? <Loader2 size={16} className="animate-spin" /> : <MessageSquarePlus size={16} />}
                Сохранить
              </motion.button>
            </form>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
