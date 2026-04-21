"use client";

import { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";
import { X, UserPlus } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { api } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { useFocusTrap } from "@/hooks/useFocusTrap";
import { DuplicateWarning } from "./DuplicateWarning";
import { logger } from "@/lib/logger";
import { CLIENT_STATUS_LABELS, type ClientStatus } from "@/types";

const SOURCES = [
  { value: "cold_call", label: "Холодный звонок" },
  { value: "referral", label: "Рекомендация" },
  { value: "website", label: "Сайт" },
  { value: "social_media", label: "Соцсети" },
  { value: "other", label: "Другое" },
];

const CONSENT_TYPES = [
  { value: "", label: "— Без согласия —" },
  { value: "data_processing", label: "Обработка персональных данных" },
  { value: "contact_allowed", label: "Разрешение на связь" },
];

const CONSENT_CHANNELS = [
  { value: "phone_call", label: "Телефонный звонок" },
  { value: "in_person", label: "Лично" },
  { value: "sms_link", label: "SMS-ссылка" },
];

interface ClientCreateModalProps {
  open: boolean;
  onClose: () => void;
  onCreated: (clientId: string) => void;
  /** Pre-select pipeline column when opened from a kanban column button */
  initialStatus?: ClientStatus;
}

interface ManagerOption {
  id: string;
  full_name: string;
}

interface CreateResponse {
  client: {
    id: string;
  };
  duplicate_warning?: string | null;
  duplicate_ids?: string[] | null;
}

export function ClientCreateModal({ open, onClose, onCreated, initialStatus = "new" }: ClientCreateModalProps) {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const focusTrapRef = useFocusTrap(open, onClose);

  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [debtAmount, setDebtAmount] = useState("");
  const [source, setSource] = useState("cold_call");
  const [notes, setNotes] = useState("");
  const [nextContact, setNextContact] = useState("");
  const [consentType, setConsentType] = useState("");
  const [consentChannel, setConsentChannel] = useState("phone_call");
  const [managerId, setManagerId] = useState("");
  const [managers, setManagers] = useState<ManagerOption[]>([]);

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dupWarning, setDupWarning] = useState<{ message: string; duplicate_ids: string[] } | null>(null);

  // Load managers for admin
  useEffect(() => {
    if (!isAdmin || !open) return;
    api.get("/users?role=manager&limit=100")
      .then((data: ManagerOption[]) => setManagers(Array.isArray(data) ? data : []))
      .catch((err) => { logger.error("Failed to load managers for client creation:", err); });
  }, [isAdmin, open]);

  const resetForm = () => {
    setFullName("");
    setPhone("");
    setEmail("");
    setDebtAmount("");
    setSource("cold_call");
    setNotes("");
    setNextContact("");
    setConsentType("");
    setConsentChannel("phone_call");
    setManagerId("");
    setError(null);
    setDupWarning(null);
  };

  const handleClose = () => {
    resetForm();
    onClose();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!fullName.trim()) {
      setError("Имя обязательно");
      return;
    }
    if (phone && !/^\+?[0-9\s\-()]{7,20}$/.test(phone)) {
      setError("Неверный формат телефона");
      return;
    }
    if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      setError("Неверный формат email");
      return;
    }
    if (debtAmount) {
      const parsed = parseFloat(debtAmount);
      if (Number.isNaN(parsed) || parsed < 0) {
        setError("Некорректная сумма долга");
        return;
      }
    }

    setSaving(true);
    setError(null);
    try {
      const body: Record<string, unknown> = {
        full_name: fullName.trim(),
        source,
        status: initialStatus,
      };
      if (phone) body.phone = phone.trim();
      if (email) body.email = email.trim();
      if (debtAmount) {
        const debt = parseFloat(debtAmount);
        if (!Number.isNaN(debt)) body.debt_amount = debt;
      }
      if (notes) body.notes = notes.trim();
      if (nextContact) body.next_contact_at = new Date(nextContact).toISOString();
      if (consentType) {
        body.initial_consent_type = consentType;
        body.initial_consent_channel = consentChannel;
      }
      const resp: CreateResponse = await api.post("/clients", body);

      if (resp.duplicate_warning) {
        setDupWarning({
          message: resp.duplicate_warning,
          duplicate_ids: resp.duplicate_ids || [],
        });
      }

      onCreated(resp.client.id);
      resetForm();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка создания");
    } finally {
      setSaving(false);
    }
  };

  // Portal: render to document.body to escape <main overflow="clip">
  if (typeof document === "undefined") return null;

  const statusLabel = CLIENT_STATUS_LABELS[initialStatus] || "Новый";

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[100]"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
        >
          {/* Backdrop — semi-transparent, kanban visible behind */}
          <motion.div
            className="absolute inset-0"
            style={{ background: "var(--overlay-bg, rgba(0,0,0,0.4))" }}
            onClick={handleClose}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          />

          {/* Slide-in Drawer from right */}
          <motion.div
            ref={focusTrapRef}
            role="dialog"
            aria-modal="true"
            aria-label="Создание клиента"
            className="fixed top-0 right-0 h-full w-full max-w-[440px] flex flex-col"
            style={{
              background: "var(--surface-card, var(--bg-secondary))",
              borderLeft: "1px solid var(--border-color)",
              boxShadow: "-8px 0 30px rgba(0,0,0,0.3)",
            }}
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
          >
            {/* Header — sticky */}
            <div
              className="flex items-center justify-between px-6 py-4 shrink-0"
              style={{ borderBottom: "1px solid var(--border-color)" }}
            >
              <div className="flex items-center gap-3">
                <div
                  className="flex h-9 w-9 items-center justify-center rounded-xl"
                  style={{ background: "var(--accent-muted)" }}
                >
                  <UserPlus size={18} style={{ color: "var(--accent)" }} />
                </div>
                <div>
                  <h2 className="font-display text-base font-bold" style={{ color: "var(--text-primary)" }}>
                    Новый клиент
                  </h2>
                  {initialStatus !== "new" && (
                    <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
                      Колонка: <span style={{ color: "var(--accent)" }}>{statusLabel}</span>
                    </p>
                  )}
                </div>
              </div>
              <motion.button
                onClick={handleClose}
                aria-label="Закрыть"
                className="flex h-8 w-8 items-center justify-center rounded-lg transition-colors"
                style={{ color: "var(--text-muted)", background: "var(--input-bg)" }}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
              >
                <X size={16} />
              </motion.button>
            </div>

            {/* Scrollable content */}
            <div className="flex-1 overflow-y-auto px-6 py-5">
              {dupWarning && (
                <DuplicateWarning
                  message={dupWarning.message}
                  duplicateIds={dupWarning.duplicate_ids}
                  onDismiss={() => setDupWarning(null)}
                />
              )}

              {error && (
                <div className="rounded-lg p-3 mb-4 text-xs" style={{ background: "color-mix(in srgb, var(--danger) 10%, transparent)", color: "var(--danger)" }}>
                  {error}
                </div>
              )}

              <form id="create-client-form" onSubmit={handleSubmit} className="space-y-4">
                {/* Full name */}
                <div>
                  <label className="block text-xs font-medium tracking-wide mb-1.5" style={{ color: "var(--text-muted)" }}>
                    ИМЯ *
                  </label>
                  <input
                    type="text"
                    aria-label="ИМЯ"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    placeholder="Иванов Иван Иванович"
                    className="vh-input w-full"
                    autoFocus
                    required
                  />
                </div>

                {/* Phone + Email row */}
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium tracking-wide mb-1.5" style={{ color: "var(--text-muted)" }}>ТЕЛЕФОН</label>
                    <input
                      type="tel"
                      aria-label="ТЕЛЕФОН"
                      value={phone}
                      onChange={(e) => setPhone(e.target.value)}
                      placeholder="+7 999 123-45-67"
                      className="vh-input w-full"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium tracking-wide mb-1.5" style={{ color: "var(--text-muted)" }}>EMAIL</label>
                    <input
                      type="email"
                      aria-label="EMAIL"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="client@mail.ru"
                      className="vh-input w-full"
                    />
                  </div>
                </div>

                {/* Debt + Source row */}
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium tracking-wide mb-1.5" style={{ color: "var(--text-muted)" }}>СУММА ДОЛГА, ₽</label>
                    <input
                      type="number"
                      aria-label="СУММА ДОЛГА, ₽"
                      value={debtAmount}
                      onChange={(e) => setDebtAmount(e.target.value)}
                      placeholder="500000"
                      className="vh-input w-full"
                      min={0}
                      step={1000}
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium tracking-wide mb-1.5" style={{ color: "var(--text-muted)" }}>ИСТОЧНИК *</label>
                    <select aria-label="ИСТОЧНИК" value={source} onChange={(e) => setSource(e.target.value)} className="vh-input w-full">
                      {SOURCES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
                    </select>
                  </div>
                </div>

                {/* Admin: assign manager */}
                {isAdmin && managers.length > 0 && (
                  <div>
                    <label className="block text-xs font-medium tracking-wide mb-1.5" style={{ color: "var(--text-muted)" }}>НАЗНАЧИТЬ МЕНЕДЖЕРУ</label>
                    <select aria-label="НАЗНАЧИТЬ МЕНЕДЖЕРУ" value={managerId} onChange={(e) => setManagerId(e.target.value)} className="vh-input w-full">
                      <option value="">— Мне —</option>
                      {managers.map((m) => <option key={m.id} value={m.id}>{m.full_name}</option>)}
                    </select>
                  </div>
                )}

                {/* Next contact */}
                <div>
                  <label className="block text-xs font-medium tracking-wide mb-1.5" style={{ color: "var(--text-muted)" }}>СЛЕДУЮЩИЙ КОНТАКТ</label>
                  <input
                    type="datetime-local"
                    aria-label="СЛЕДУЮЩИЙ КОНТАКТ"
                    value={nextContact}
                    onChange={(e) => setNextContact(e.target.value)}
                    className="vh-input w-full"
                  />
                </div>

                {/* Initial consent */}
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium tracking-wide mb-1.5" style={{ color: "var(--text-muted)" }}>НАЧАЛЬНОЕ СОГЛАСИЕ</label>
                    <select aria-label="НАЧАЛЬНОЕ СОГЛАСИЕ" value={consentType} onChange={(e) => setConsentType(e.target.value)} className="vh-input w-full">
                      {CONSENT_TYPES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
                    </select>
                  </div>
                  {consentType && (
                    <div>
                      <label className="block text-xs font-medium tracking-wide mb-1.5" style={{ color: "var(--text-muted)" }}>КАНАЛ</label>
                      <select aria-label="КАНАЛ" value={consentChannel} onChange={(e) => setConsentChannel(e.target.value)} className="vh-input w-full">
                        {CONSENT_CHANNELS.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
                      </select>
                    </div>
                  )}
                </div>

                {/* Notes */}
                <div>
                  <label className="block text-xs font-medium tracking-wide mb-1.5" style={{ color: "var(--text-muted)" }}>ЗАМЕТКИ</label>
                  <textarea
                    aria-label="ЗАМЕТКИ"
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    placeholder="Дополнительная информация..."
                    className="vh-input w-full"
                    rows={3}
                    style={{ resize: "vertical" }}
                  />
                </div>
              </form>
            </div>

            {/* Footer — sticky submit */}
            <div
              className="shrink-0 px-6 py-4"
              style={{ borderTop: "1px solid var(--border-color)" }}
            >
              <Button type="submit" form="create-client-form" variant="primary" fluid loading={saving} icon={<UserPlus size={16} />}>
                Создать клиента
              </Button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
