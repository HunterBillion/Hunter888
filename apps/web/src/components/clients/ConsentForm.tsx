"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { ShieldPlus, Loader2 } from "lucide-react";

interface ConsentFormProps {
  clientId: string;
  onSubmit: (data: { consent_type: string; channel: string }) => Promise<void>;
}

const CONSENT_TYPES = [
  { value: "data_processing", label: "Обработка персональных данных" },
  { value: "contact_allowed", label: "Разрешение на контакт" },
  { value: "consultation_agreed", label: "Согласие на консультацию" },
  { value: "bfl_procedure", label: "Процедура БФЛ" },
  { value: "marketing", label: "Маркетинговые коммуникации" },
];

const CHANNELS = [
  { value: "phone_call", label: "Устно (звонок)" },
  { value: "in_person", label: "Лично (встреча)" },
  { value: "sms_link", label: "SMS-ссылка" },
  { value: "whatsapp", label: "WhatsApp" },
  { value: "email_link", label: "Email" },
  { value: "web_form", label: "Веб-форма" },
];

export function ConsentForm({ onSubmit }: ConsentFormProps) {
  const [consentType, setConsentType] = useState(CONSENT_TYPES[0].value);
  const [channel, setChannel] = useState(CHANNELS[0].value);
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await onSubmit({ consent_type: consentType, channel });
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block text-xs font-mono mb-1.5" style={{ color: "var(--text-muted)" }}>
          Тип согласия
        </label>
        <select
          value={consentType}
          onChange={(e) => setConsentType(e.target.value)}
          className="vh-input w-full"
        >
          {CONSENT_TYPES.map((t) => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>
      </div>

      <div>
        <label className="block text-xs font-mono mb-1.5" style={{ color: "var(--text-muted)" }}>
          Канал получения
        </label>
        <select
          value={channel}
          onChange={(e) => setChannel(e.target.value)}
          className="vh-input w-full"
        >
          {CHANNELS.map((c) => (
            <option key={c.value} value={c.value}>{c.label}</option>
          ))}
        </select>
      </div>

      <motion.button
        type="submit"
        disabled={saving}
        className="btn-neon flex items-center gap-2 w-full justify-center"
        whileTap={{ scale: 0.97 }}
      >
        {saving ? <Loader2 size={14} className="animate-spin" /> : <ShieldPlus size={14} />}
        Зафиксировать согласие
      </motion.button>
    </form>
  );
}
