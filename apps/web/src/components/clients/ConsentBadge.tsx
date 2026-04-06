"use client";

import { ShieldCheck, ShieldOff } from "lucide-react";
import type { ClientConsent } from "@/types";

interface ConsentBadgeProps {
  consent: ClientConsent;
}

const CONSENT_LABELS: Record<string, string> = {
  data_processing: "Обработка данных",
  contact_allowed: "Разрешение на связь",
  consultation_agreed: "Консультация",
  bfl_procedure: "Процедура БФЛ",
  marketing: "Маркетинг",
};

export function ConsentBadge({ consent }: ConsentBadgeProps) {
  const active = consent.is_active;
  const label = CONSENT_LABELS[consent.consent_type] || consent.consent_type;

  return (
    <div
      className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-mono"
      style={{
        background: active ? "rgba(0,255,102,0.08)" : "rgba(255,51,51,0.08)",
        border: `1px solid ${active ? "rgba(0,255,102,0.2)" : "rgba(255,51,51,0.2)"}`,
        color: active ? "var(--neon-green, #00FF66)" : "var(--neon-red, #FF3333)",
      }}
    >
      {active ? <ShieldCheck size={12} /> : <ShieldOff size={12} />}
      {label}
      {consent.revoked_at && (
        <span className="text-xs opacity-60">
          (отозв. {new Date(consent.revoked_at).toLocaleDateString("ru-RU")})
        </span>
      )}
    </div>
  );
}
