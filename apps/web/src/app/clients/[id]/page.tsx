"use client";

import { useState, useEffect, useRef } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { motion } from "framer-motion";
import {
  Phone, Mail, MapPin, DollarSign,
  Calendar, ShieldCheck, Loader2, Plus, Bell, Send,
  MessageSquare, PhoneCall, ArrowRight,
} from "lucide-react";
import { BackButton } from "@/components/ui/BackButton";
import { Breadcrumb } from "@/components/ui/Breadcrumb";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import AuthLayout from "@/components/layout/AuthLayout";
import { PageSkeleton } from "@/components/ui/Skeleton";
import { ClientTimeline } from "@/components/clients/ClientTimeline";
import { ClientAttachments } from "@/components/clients/ClientAttachments";
import { ClientMemorySection } from "@/components/clients/ClientMemorySection";
import { AIRemembersBanner } from "@/components/clients/AIRemembersBanner";
// 2026-04-23 Sprint 6 — «deja-vu» widget на CRM-карточке при открытии
// через ?retrain=...&from=... (пришёл с /results → "Повторить с клиентом").
import { RetrainWidget } from "@/components/clients/RetrainWidget";
import { ConsentBadge } from "@/components/clients/ConsentBadge";
import { ConsentForm } from "@/components/clients/ConsentForm";
import { StatusTransition } from "@/components/clients/StatusTransition";
import { InteractionCreateModal } from "@/components/clients/InteractionCreateModal";
import { ReminderCreateModal } from "@/components/clients/ReminderCreateModal";
import type { ClientAttachment, CRMClientDetail, ClientStatus } from "@/types";
import { CLIENT_STATUS_LABELS, CLIENT_STATUS_COLORS } from "@/types";
import { logger } from "@/lib/logger";

export default function ClientDetailPage() {
  const { user } = useAuth();
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const id = typeof params.id === "string" ? params.id : String(params.id ?? "");

  // 2026-04-23 Sprint 6 — retrain deja-vu. Query is shaped by
  // /results → «Повторить с клиентом»: ?retrain=call|chat&from=<sessionId>.
  const retrainModeRaw = searchParams.get("retrain");
  const retrainMode: "call" | "chat" | null =
    retrainModeRaw === "call" || retrainModeRaw === "chat" ? retrainModeRaw : null;
  const fromSessionId = searchParams.get("from");
  const historyRef = useRef<HTMLDivElement | null>(null);

  const isReadOnly = user?.role === "methodologist";

  const [client, setClient] = useState<CRMClientDetail | null>(null);
  const [attachments, setAttachments] = useState<ClientAttachment[]>([]);
  const [loading, setLoading] = useState(true);
  const [showConsentForm, setShowConsentForm] = useState(false);
  const [showInteractionModal, setShowInteractionModal] = useState(false);
  const [showReminderModal, setShowReminderModal] = useState(false);
  const [smsLoading, setSmsLoading] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  // 2026-04-20: "Тренировка с этим клиентом" — отделяет два входа
  // (чат / звонок), раньше выбор жил внутри самой страницы тренировки,
  // что путало пользователей ("зачем звонок в чате?").
  const [startingMode, setStartingMode] = useState<null | "chat" | "voice">(null);

  const fetchClient = async () => {
    try {
      const data: CRMClientDetail = await api.get(`/clients/${id}`);
      setClient(data);
    } catch (err) {
      logger.error("Failed to load client details:", err);
    }
  };

  const fetchAttachments = async () => {
    try {
      const data = await api.get<ClientAttachment[]>(`/clients/${id}/attachments`);
      setAttachments(Array.isArray(data) ? data : []);
    } catch (err) {
      logger.error("Failed to load client attachments:", err);
      setAttachments([]);
    }
  };

  useEffect(() => {
    setLoading(true);
    Promise.all([fetchClient(), fetchAttachments()]).finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // 2026-04-23 Sprint 6 — auto-scroll to history panel when the user lands
  // here via ?retrain=... so the RetrainWidget is front-and-centre.
  const showRetrain = !!(retrainMode && fromSessionId && client?.last_training_session);
  useEffect(() => {
    if (showRetrain && historyRef.current) {
      historyRef.current.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [showRetrain]);

  const dismissRetrain = () => {
    router.replace(`/clients/${id}`);
  };

  const handleStartTraining = async (mode: "chat" | "voice") => {
    if (!client || startingMode) return;
    setStartingMode(mode);
    setActionError(null);
    try {
      // Pick a fallback scenario — for v1 we don't persist a per-client
      // scenario mapping yet, we just need an active one to anchor the
      // session. The CharacterBuilder / archetype_code flow then drives
      // the roleplay personality via real_client_id.
      const scenariosRaw = await api.get("/scenarios/");
      const scenarios = Array.isArray(scenariosRaw)
        ? (scenariosRaw as Array<{ id: string; is_active?: boolean }>)
        : [];
      const active = scenarios.filter((s) => s.is_active !== false);
      if (!active.length) {
        throw new Error("Нет активных сценариев — попросите методолога создать.");
      }
      const scenario_id = active[0].id;

      // TZ-2 §6.2/6.3 — send canonical `mode` + `runtime_type` in addition
      // to the legacy `custom_session_mode`. Backend prefers the canonical
      // fields when present and falls back to the legacy field for older
      // FE callers. Once all start sites are migrated the legacy field
      // will be dropped.
      const canonicalMode = mode === "voice" ? "call" : "chat";
      const canonicalRuntimeType =
        mode === "voice" ? "crm_call" : "crm_chat";
      const session = await api.post<{ id: string }>(
        "/training/sessions",
        {
          scenario_id,
          real_client_id: client.id,
          mode: canonicalMode,
          runtime_type: canonicalRuntimeType,
          custom_session_mode: canonicalMode, // legacy compat
          // `source` — диагностический штамп: видно в аналитике, какие
          // сессии запущены из CRM-карточки и в каком режиме.
          source: mode === "voice" ? "crm_voice" : "crm_chat",
        },
      );
      if (!session?.id) throw new Error("Не удалось создать сессию");

      // Voice-mode lives at /training/[id]/call; chat-mode is the default
      // route. Split entry points = no more "зачем звонок в чате".
      if (mode === "voice") {
        router.push(`/training/${session.id}/call`);
      } else {
        router.push(`/training/${session.id}`);
      }
    } catch (err) {
      if (err instanceof ApiError && err.detail?.code === "profile_incomplete") {
        router.push("/onboarding");
        return;
      }
      const msg = err instanceof Error ? err.message : "Не удалось начать тренировку";
      setActionError(msg);
      logger.error("[ClientDetail] Start training failed:", err);
    } finally {
      // Keep mode set on success — page will redirect, so this only
      // matters if an error is surfaced and the user stays on the page.
      setStartingMode(null);
    }
  };

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

  const refreshClientArtifacts = async () => {
    await Promise.all([refreshClient(), fetchAttachments()]);
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
        <div className="flex min-h-[60vh] items-center justify-center p-6">
          <div className="glass-panel p-8 max-w-md text-center">
            <div className="flex justify-center mb-4">
              <div
                className="flex h-12 w-12 items-center justify-center rounded-full"
                style={{ background: "var(--accent-muted)" }}
              >
                <span className="font-mono text-lg" style={{ color: "var(--accent)" }}>404</span>
              </div>
            </div>
            <h2 className="font-display text-lg font-semibold mb-2" style={{ color: "var(--text-primary)" }}>
              Клиент не найден
            </h2>
            <p className="text-sm mb-5" style={{ color: "var(--text-muted)" }}>
              Клиент удалён или у вас нет доступа к карточке.
            </p>
            <Link
              href="/clients"
              className="inline-flex items-center gap-2 font-bold tracking-wide uppercase rounded-xl px-5 py-2.5 text-sm transition-all"
              style={{
                background: "var(--accent)",
                color: "#fff",
                boxShadow: "0 2px 12px var(--accent-glow)",
              }}
            >
              ← Вернуться к списку
            </Link>
          </div>
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
        {/* PR-A: «ИИ помнит этого клиента» — видимый сразу при открытии,
            до timeline. Это и есть user-visible эффект cross-session
            памяти: продажник до начала тренировки понимает, на какой
            контекст ИИ будет опираться. */}
        <AIRemembersBanner clientId={id} />
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
              background: "var(--danger-muted)",
              border: "1px solid var(--danger-muted)",
              color: "#FCA5A5",
            }}
          >
            <span>{actionError}</span>
            <button onClick={() => setActionError(null)} className="ml-3 text-xs opacity-60 hover:opacity-100">✕</button>
          </motion.div>
        )}

        {/* Hero stats row — high-value metrics at a glance */}
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25 }}
          className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-6"
        >
          {/* Debt */}
          <div className="glass-panel p-3.5">
            <div className="text-[10px] font-semibold uppercase tracking-wider mb-1" style={{ color: "var(--text-muted)" }}>
              Долг
            </div>
            <div className="font-display text-xl font-bold" style={{ color: "var(--text-primary)" }}>
              {formatDebt(client.debt_amount ?? 0)} <span className="text-xs font-normal" style={{ color: "var(--text-muted)" }}>₽</span>
            </div>
          </div>

          {/* Days since last contact */}
          <div className="glass-panel p-3.5">
            <div className="text-[10px] font-semibold uppercase tracking-wider mb-1" style={{ color: "var(--text-muted)" }}>
              Последний контакт
            </div>
            <div className="font-display text-xl font-bold" style={{
              color: (() => {
                const last = (client.interactions ?? [])[0]?.created_at;
                if (!last) return "var(--text-muted)";
                const days = Math.floor((Date.now() - new Date(last).getTime()) / 86_400_000);
                if (days > 14) return "var(--danger, #ef4444)";
                if (days > 7) return "var(--warning, #f59e0b)";
                return "var(--text-primary)";
              })(),
            }}>
              {(() => {
                const last = (client.interactions ?? [])[0]?.created_at;
                if (!last) return "—";
                const days = Math.floor((Date.now() - new Date(last).getTime()) / 86_400_000);
                if (days === 0) return "Сегодня";
                if (days === 1) return "Вчера";
                return `${days} дн.`;
              })()}
            </div>
          </div>

          {/* Total interactions */}
          <div className="glass-panel p-3.5">
            <div className="text-[10px] font-semibold uppercase tracking-wider mb-1" style={{ color: "var(--text-muted)" }}>
              Взаимодействий
            </div>
            <div className="font-display text-xl font-bold" style={{ color: "var(--text-primary)" }}>
              {client.interactions?.length ?? 0}
            </div>
          </div>

          {/* Active consents */}
          <div className="glass-panel p-3.5">
            <div className="text-[10px] font-semibold uppercase tracking-wider mb-1" style={{ color: "var(--text-muted)" }}>
              Согласия
            </div>
            <div className="font-display text-xl font-bold" style={{
              color: (client.active_consents?.length ?? 0) > 0 ? "var(--success, #22c55e)" : "var(--text-muted)",
            }}>
              {client.active_consents?.length ?? 0}
              <span className="text-xs font-normal ml-1" style={{ color: "var(--text-muted)" }}>
                / {client.consents?.length ?? 0}
              </span>
            </div>
          </div>
        </motion.div>

        {/* Main grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-6">
          {/* Left: Info + Consents */}
          <div className="md:col-span-1 space-y-4">
            {/* Financial */}
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}
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
                {(client.creditors?.length ?? 0) > 0 && (
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
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}
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
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}
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
                  <ConsentForm onSubmit={handleConsentSubmit} />
                </div>
              )}

              <div className="flex flex-wrap gap-2">
                {(client.consents?.length ?? 0) > 0 ? (
                  client.consents!.map((c) => (
                    <ConsentBadge key={c.id} consent={c} onRevoked={fetchClient} />
                  ))
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

            {/* 2026-04-20: Train with this client — two explicit entry
                points (chat / voice) живут ЗДЕСЬ на CRM-карточке, а не
                внутри training-страницы. Раньше пользователи не понимали
                зачем "живой звонок" показывается внутри чата — теперь
                выбор mode происходит ДО входа в сессию, как на реальном
                телефоне: «написать» или «позвонить». */}
            {!isReadOnly && (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.25 }}
                className="glass-panel p-4"
                style={{
                  borderLeft: "3px solid var(--accent)",
                }}
              >
                <div className="flex items-center justify-between mb-3">
                  <span
                    className="text-xs font-semibold uppercase tracking-wide"
                    style={{ color: "var(--accent)" }}
                  >
                    ТРЕНИРОВКА С КЛИЕНТОМ
                  </span>
                </div>
                <p
                  className="text-xs leading-relaxed mb-3"
                  style={{ color: "var(--text-muted)" }}
                >
                  Разыграйте диалог с <b style={{ color: "var(--text-primary)" }}>{client.full_name}</b> в двух режимах — как с реальным клиентом: написать в мессенджер или позвонить.
                </p>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  <motion.button
                    onClick={() => handleStartTraining("chat")}
                    disabled={!!startingMode}
                    className="group relative flex flex-col items-start gap-1 rounded-lg p-3 text-left transition disabled:opacity-40"
                    style={{
                      background: "var(--input-bg)",
                      border: "1px solid var(--border-color)",
                    }}
                    whileHover={{ y: -2, borderColor: "var(--accent)" } as any}
                    whileTap={{ scale: 0.98 }}
                  >
                    <div className="flex items-center gap-2 w-full">
                      {startingMode === "chat" ? (
                        <Loader2 size={16} className="animate-spin" style={{ color: "var(--accent)" }} />
                      ) : (
                        <MessageSquare size={16} style={{ color: "var(--accent)" }} />
                      )}
                      <span
                        className="text-sm font-semibold"
                        style={{ color: "var(--text-primary)" }}
                      >
                        Написать
                      </span>
                      <ArrowRight
                        size={12}
                        className="ml-auto opacity-50 group-hover:opacity-100 transition"
                        style={{ color: "var(--accent)" }}
                      />
                    </div>
                    <span
                      className="text-[11px] leading-snug"
                      style={{ color: "var(--text-muted)" }}
                    >
                      Чат-тренировка: текст + подсказки
                    </span>
                  </motion.button>

                  <motion.button
                    onClick={() => handleStartTraining("voice")}
                    disabled={!!startingMode}
                    className="group relative flex flex-col items-start gap-1 rounded-lg p-3 text-left transition disabled:opacity-40"
                    style={{
                      background:
                        "color-mix(in srgb, var(--success) 10%, var(--input-bg))",
                      border:
                        "1px solid color-mix(in srgb, var(--success) 35%, transparent)",
                    }}
                    whileHover={{ y: -2, borderColor: "var(--success)" } as any}
                    whileTap={{ scale: 0.98 }}
                  >
                    <div className="flex items-center gap-2 w-full">
                      {startingMode === "voice" ? (
                        <Loader2 size={16} className="animate-spin" style={{ color: "var(--success)" }} />
                      ) : (
                        <PhoneCall size={16} style={{ color: "var(--success)" }} />
                      )}
                      <span
                        className="text-sm font-semibold"
                        style={{ color: "var(--text-primary)" }}
                      >
                        Позвонить
                      </span>
                      <ArrowRight
                        size={12}
                        className="ml-auto opacity-50 group-hover:opacity-100 transition"
                        style={{ color: "var(--success)" }}
                      />
                    </div>
                    <span
                      className="text-[11px] leading-snug"
                      style={{ color: "var(--text-muted)" }}
                    >
                      Голосовой звонок: микрофон + AI-голос
                    </span>
                  </motion.button>
                </div>

                {actionError && (
                  <div
                    className="mt-2 text-xs rounded-md px-2 py-1.5"
                    style={{
                      background:
                        "color-mix(in srgb, var(--danger) 12%, transparent)",
                      color: "var(--danger)",
                    }}
                  >
                    {actionError}
                  </div>
                )}
              </motion.div>
            )}

            <ClientAttachments
              clientId={id}
              attachments={attachments}
              readOnly={isReadOnly}
              onUploaded={refreshClientArtifacts}
            />

            {/* TZ-4 §6.3 / §6.4 — persona memory + last snapshot +
                event counts. Self-hides when there's nothing to show
                (no lead anchor + no events) so the section doesn't
                clutter the layout for fresh clients. */}
            <ClientMemorySection clientId={id} />

            {/* Tags */}
            {(client.tags?.length ?? 0) > 0 && (
              <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}
                className="glass-panel p-4"
              >
                <span className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--accent)" }}>ТЕГИ</span>
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {client.tags!.map((tag) => (
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
            ref={historyRef}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25 }}
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
            {/* 2026-04-23 Sprint 6 — RetrainWidget shown above the timeline
                when /clients/[id] is opened via ?retrain=call|chat&from=<id>
                and backend returned last_training_session. */}
            {showRetrain && retrainMode && fromSessionId && client.last_training_session && (
              <RetrainWidget
                mode={retrainMode}
                fromSessionId={fromSessionId}
                lastSession={client.last_training_session}
                clientName={client.full_name}
                onDismiss={dismissRetrain}
              />
            )}
            <ClientTimeline interactions={client.interactions ?? []} />
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
