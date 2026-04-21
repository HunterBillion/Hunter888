"use client";

import { useState } from "react";
import { ShieldCheck, ShieldOff, X, Loader2 } from "lucide-react";
import type { ClientConsent } from "@/types";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";
import { useNotificationStore } from "@/stores/useNotificationStore";

interface ConsentBadgeProps {
  consent: ClientConsent;
  onRevoked?: () => void;
}

const CONSENT_LABELS: Record<string, string> = {
  data_processing: "Обработка данных",
  contact_allowed: "Разрешение на связь",
  consultation_agreed: "Консультация",
  bfl_procedure: "Процедура БФЛ",
  marketing: "Маркетинг",
};

export function ConsentBadge({ consent, onRevoked }: ConsentBadgeProps) {
  const active = consent.is_active;
  const label = CONSENT_LABELS[consent.consent_type] || consent.consent_type;
  const [revoking, setRevoking] = useState(false);

  // Visible border colors — previously matched background so the border was
  // invisible. Separate accent color keeps the chip readable.
  const borderColor = active
    ? "color-mix(in srgb, var(--success, #22c55e) 38%, transparent)"
    : "color-mix(in srgb, var(--danger, #ef4444) 38%, transparent)";

  const handleRevoke = async () => {
    if (revoking) return;
    if (typeof window !== "undefined" && !window.confirm(`Отозвать согласие «${label}»?`)) return;
    setRevoking(true);
    try {
      await api.post(`/clients/${consent.client_id}/consents/${consent.id}/revoke`, {});
      useNotificationStore.getState().addToast({
        title: "Согласие отозвано",
        body: label,
        type: "success",
      });
      onRevoked?.();
    } catch (err) {
      logger.error("Revoke consent failed:", err);
      useNotificationStore.getState().addToast({
        title: "Не удалось отозвать согласие",
        body: err instanceof Error ? err.message : "Попробуйте ещё раз",
        type: "error",
      });
    } finally {
      setRevoking(false);
    }
  };

  return (
    <div
      className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-mono"
      style={{
        background: active ? "var(--success-muted)" : "var(--danger-muted)",
        border: `1px solid ${borderColor}`,
        color: active ? "var(--success, #22c55e)" : "var(--danger, #ef4444)",
      }}
    >
      {active ? <ShieldCheck size={12} /> : <ShieldOff size={12} />}
      {label}
      {consent.revoked_at && (
        <span className="text-xs opacity-60">
          (отозв. {new Date(consent.revoked_at).toLocaleDateString("ru-RU")})
        </span>
      )}
      {active && onRevoked && (
        <button
          onClick={handleRevoke}
          disabled={revoking}
          className="ml-1 rounded p-0.5 opacity-60 hover:opacity-100 transition-opacity disabled:opacity-40"
          style={{ color: "currentColor" }}
          title="Отозвать согласие"
          aria-label="Отозвать согласие"
        >
          {revoking ? <Loader2 size={10} className="animate-spin" /> : <X size={10} />}
        </button>
      )}
    </div>
  );
}
