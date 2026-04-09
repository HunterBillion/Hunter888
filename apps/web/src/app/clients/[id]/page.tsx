"use client";

import { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import { motion } from "framer-motion";
import {
  Phone, Mail, MapPin, DollarSign,
  Calendar, ShieldCheck, Loader2, Plus, Bell, Send,
} from "lucide-react";
import { BackButton } from "@/components/ui/BackButton";
import { Breadcrumb } from "@/components/ui/Breadcrumb";
import { api } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import AuthLayout from "@/components/layout/AuthLayout";
import { PageSkeleton } from "@/components/ui/Skeleton";
import { ClientTimeline } from "@/components/clients/ClientTimeline";
import { ConsentBadge } from "@/components/clients/ConsentBadge";
import { ConsentForm } from "@/components/clients/ConsentForm";
import { StatusTransition } from "@/components/clients/StatusTransition";
import { InteractionCreateModal } from "@/components/clients/InteractionCreateModal";
import { ReminderCreateModal } from "@/components/clients/ReminderCreateModal";
import type { CRMClientDetail, ClientStatus } from "@/types";
import { CLIENT_STATUS_LABELS, CLIENT_STATUS_COLORS } from "@/types";
import { logger } from "@/lib/logger";

export default function ClientDetailPage() {
  const { user } = useAuth();
  const params = useParams();
  const id = typeof params.id === "string" ? params.id : String(params.id ?? "");

  const isReadOnly = user?.role === "methodologist";

  const [client, setClient] = useState<CRMClientDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [showConsentForm, setShowConsentForm] = useState(false);
  const [showInteractionModal, setShowInteractionModal] = useState(false);
  const [showReminderModal, setShowReminderModal] = useState(false);
  const [smsLoading, setSmsLoading] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    api.get(`/clients/${id}`)
      .then((data: CRMClientDetail) => setClient(data))
      .catch((err) => { logger.error("Failed to load client details:", err); })
      .finally(() => setLoading(false));
  }, [id]);

  const handleStatusChange = async (newStatus: ClientStatus, reason?: string) => {
    setActionError(null);
    try {
      await api.patch(`/clients/${id}/status`, {
        new_status: newStatus,
        reason: reason || undefined,
      });
      setClient((prev) => prev ? { ...prev, status: newStatus } : prev);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Не удалось сменить статус";
      setActionError(msg);
      logger.error("[ClientDetail] Status change failed:", err);
    }
  };

  const handleConsentSubmit = async (data: { consent_type: string; channel: string }) => {
    setActionError(null);
    try {
      await api.post(`/clients/${id}/consents`, data);
      const updated: CRMClientDetail = await api.get(`/clients/${id}`);
      setClient(updated);
      setShowConsentForm(false);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Не удалось сохранить согласие";
      setActionError(msg);
      logger.error("[ClientDetail] Consent submit failed:", err);
    }
  };

  const refreshClient = async () => {
    try {
      const updated: CRMClientDetail = await api.get(`/clients/${id}`);
      setClient(updated);
    } catch (err) {
      logger.error("[ClientDetail] Refresh failed:", err);
    }
  };

  const handleSendSmsLink = async (consentType: string) => {
    setActionError(null);
    setSmsLoading(true);
    try {
      await api.post(`/clients/${id}/consents/send-link?consent_type=${consentType}`, {});
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Не удалось отправить SMS";
      setActionError(msg);
      logger.error("[ClientDetail] SMS link failed:", err);
    }
    setSmsLoading(false);
  };

  const formatDebt = (amount: number) => amount.toLocaleString("ru-RU") + " ₽";

  if (loading) {
    return (
      <AuthLayout>
        <PageSkeleton />
      </AuthLayout>
    );
  }

  if (!client) {
    return (
      <AuthLayout>
        <div className="text-center py-16">
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>Клиент не найден</p>
        </div>
      </AuthLayout>
    );
  }

  const statusColor = CLIENT_STATUS_COLORS[client.status];

  return (
    <AuthLayout>
      <div className="panel-grid-bg min-h-screen">
        <div className="app-page max-w-4xl">
        <Breadcrumb items={[{ label: "Клиенты", href: "/clients" }, { label: client.full_name }]} />
        {/* Back + status */}
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
          <div className="mb-4">
            <BackButton href="/clients" label="К клиентам" />
          </div>

          <div className="flex items-start justify-between">
            <div>
              <div className="flex items-center gap-3">
                <h1 className="font-display text-2xl font-bold" style={{ color: "var(--text-primary)" }}>
                  {client.full_name}
                </h1>
                <span
                  className="text-xs font-medium px-2 py-1 rounded-full"
                  style={{ background: `color-mix(in srgb, ${statusColor} 9%, transparent)`, color: statusColor, border: `1px solid color-mix(in srgb, ${statusColor} 19%, transparent)` }}
                >
                  {CLIENT_STATUS_LABELS[client.status]}
                </span>
              </div>

              {/* Contact info */}
              <div className="flex flex-wrap items-center gap-4 mt-2">
                {client.phone && (
                  <span className="flex items-center gap-1.5 text-sm" style={{ color: "var(--text-muted)" }}>
                    <Phone size={13} /> {client.phone}
                  </span>
                )}
                {client.email && (
                  <span className="flex items-center gap-1.5 text-sm" style={{ color: "var(--text-muted)" }}>
                    <Mail size={13} /> {client.email}
                  </span>
                )}
                {client.city && (
                  <span className="flex items-center gap-1.5 text-sm" style={{ color: "var(--text-muted)" }}>
                    <MapPin size={13} /> {client.city}
                  </span>
                )}
              </div>
            </div>

            {!isReadOnly && (
              <StatusTransition currentStatus={client.status} onTransition={handleStatusChange} />
            )}
          </div>
        </motion.div>

        {/* Action error banner */}
        {actionError && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            className="mt-4 rounded-xl px-4 py-3 text-sm flex items-center justify-between"
            style={{
              background: "rgba(239,68,68,0.12)",
              border: "1px solid rgba(239,68,68,0.2)",
              color: "#FCA5A5",
            }}
          >
            <span>{actionError}</span>
            <button onClick={() => setActionError(null)} className="ml-3 text-xs opacity-60 hover:opacity-100">✕</button>
          </motion.div>
        )}

        {/* Main grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-8">
          {/* Left: Info + Consents */}
          <div className="md:col-span-1 space-y-4">
            {/* Financial */}
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
              className="glass-panel p-4"
            >
              <h3 className="text-xs font-semibold uppercase tracking-wide mb-3" style={{ color: "var(--accent)" }}>ФИНАНСЫ</h3>
              <div className="space-y-2">
                <div className="flex justify-between">
                  <span className="text-xs" style={{ color: "var(--text-muted)" }}>Общий долг</span>
                  <span className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                    <DollarSign size={11} className="inline" /> {formatDebt(client.debt_amount ?? 0)}
                  </span>
                </div>
                {client.income && (
                  <div className="flex justify-between">
                    <span className="text-xs" style={{ color: "var(--text-muted)" }}>Доход</span>
                    <span className="text-sm" style={{ color: "var(--text-primary)" }}>{formatDebt(client.income)}</span>
                  </div>
                )}
                {client.creditors.length > 0 && (
                  <div className="mt-2 pt-2 border-t" style={{ borderColor: "var(--border-color)" }}>
                    <span className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>КРЕДИТОРЫ</span>
                    {client.creditors.map((cr, i) => (
                      <div key={i} className="flex justify-between mt-1">
                        <span className="text-xs truncate" style={{ color: "var(--text-secondary)" }}>{cr.name}</span>
                        <span className="text-xs" style={{ color: "var(--text-muted)" }}>{formatDebt(cr.amount)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </motion.div>

            {/* Next contact + Reminder */}
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}
              className="glass-panel p-4"
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <Calendar size={14} style={{ color: "var(--accent)" }} />
                  <span className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--accent)" }}>СЛЕДУЮЩИЙ КОНТАКТ</span>
                </div>
                {!isReadOnly && (
                  <motion.button
                    onClick={() => setShowReminderModal(true)}
                    className="text-xs flex items-center gap-1"
                    style={{ color: "var(--accent)" }}
                    whileTap={{ scale: 0.95 }}
                  >
                    <Bell size={12} /> Напомнить
                  </motion.button>
                )}
              </div>
              {client.next_contact_at ? (
                <p className="text-sm" style={{ color: "var(--text-primary)" }}>
                  {new Date(client.next_contact_at).toLocaleDateString("ru-RU", {
                    weekday: "short", day: "numeric", month: "long", hour: "2-digit", minute: "2-digit",
                  })}
                </p>
              ) : (
                <p className="text-xs" style={{ color: "var(--text-muted)" }}>Не назначен</p>
              )}
            </motion.div>

            {/* Consents */}
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}
              className="glass-panel p-4"
            >
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <ShieldCheck size={14} style={{ color: "var(--accent)" }} />
                  <span className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--accent)" }}>СОГЛАСИЯ</span>
                </div>
                {!isReadOnly && (
                  <motion.button
                    onClick={() => setShowConsentForm(!showConsentForm)}
                    className="text-xs flex items-center gap-1"
                    style={{ color: "var(--accent)" }}
                    whileTap={{ scale: 0.95 }}
                  >
                    <Plus size={12} /> Добавить
                  </motion.button>
                )}
              </div>

              {!isReadOnly && showConsentForm && (
                <div className="mb-3 pb-3 border-b" style={{ borderColor: "var(--border-color)" }}>
                  <ConsentForm clientId={id} onSubmit={handleConsentSubmit} />
                </div>
              )}

              <div className="flex flex-wrap gap-2">
                {client.consents.length > 0 ? (
                  client.consents.map((c) => <ConsentBadge key={c.id} consent={c} />)
                ) : (
                  <span className="text-xs" style={{ color: "var(--text-muted)" }}>Нет согласий</span>
                )}
              </div>

              {/* SMS consent link */}
              {!isReadOnly && client.phone && (
                <motion.button
                  onClick={() => handleSendSmsLink("data_processing")}
                  disabled={smsLoading}
                  className="mt-3 w-full flex items-center justify-center gap-1.5 text-xs py-2 rounded-lg transition-colors"
                  style={{
                    background: "var(--input-bg)",
                    color: "var(--text-secondary)",
                    border: "1px solid var(--border-color)",
                  }}
                  whileTap={{ scale: 0.97 }}
                >
                  {smsLoading ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />}
                  Отправить SMS-ссылку на согласие
                </motion.button>
              )}
            </motion.div>

            {/* Tags */}
            {client.tags.length > 0 && (
              <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 }}
                className="glass-panel p-4"
              >
                <span className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--accent)" }}>ТЕГИ</span>
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {client.tags.map((tag) => (
                    <span
                      key={tag}
                      className="text-xs font-medium px-2 py-0.5 rounded-full"
                      style={{ background: "var(--input-bg)", color: "var(--text-muted)", border: "1px solid var(--border-color)" }}
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </motion.div>
            )}
          </div>

          {/* Right: Timeline */}
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.15 }}
            className="md:col-span-2 glass-panel p-5"
          >
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--accent)" }}>
                ИСТОРИЯ ВЗАИМОДЕЙСТВИЙ
              </h3>
              {!isReadOnly && (
                <motion.button
                  onClick={() => setShowInteractionModal(true)}
                  className="text-xs flex items-center gap-1"
                  style={{ color: "var(--accent)" }}
                  whileTap={{ scale: 0.95 }}
                >
                  <Plus size={12} /> Записать
                </motion.button>
              )}
            </div>
            <ClientTimeline interactions={client.interactions} />
          </motion.div>
        </div>
      </div>

      {!isReadOnly && (
        <InteractionCreateModal
          open={showInteractionModal}
          clientId={id}
          onClose={() => setShowInteractionModal(false)}
          onCreated={() => { setShowInteractionModal(false); refreshClient(); }}
        />
      )}

      {!isReadOnly && (
        <ReminderCreateModal
          open={showReminderModal}
          clientId={id}
          clientName={client.full_name}
          onClose={() => setShowReminderModal(false)}
          onCreated={refreshClient}
        />
      )}
      </div>
    </AuthLayout>
  );
}
