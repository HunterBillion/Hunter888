"use client";

import { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import { Check } from "lucide-react";
import { getApiBaseUrl } from "@/lib/public-origin";
import { AppIcon } from "@/components/ui/AppIcon";

/**
 * Consent Verification Page — PUBLIC (без авторизации).
 * Клиент переходит по SMS-ссылке и подтверждает/отзывает согласие.
 *
 * ТЗ v2: Task X2
 * - Mobile-first дизайн
 * - CSRF protection (token одноразовый, HMAC-SHA256)
 * - Rate limit: 5 попыток/мин на IP (на стороне API)
 * - Юридический текст согласия
 * - Кнопки: Подтверждаю / Отзываю
 */

interface ConsentData {
  client_name: string;
  consent_type: string;
  legal_text: string;
  status: string; // "pending" | "confirmed" | "expired" | "used"
}

type PageState = "loading" | "ready" | "confirmed" | "revoked" | "expired" | "error";

const CONSENT_TYPE_LABELS: Record<string, string> = {
  data_processing: "Обработка персональных данных",
  contact_allowed: "Связь с менеджером",
  consultation_agreed: "Бесплатная консультация",
  bfl_procedure: "Процедура банкротства физических лиц",
  marketing: "Информационные рассылки",
};

export default function ConsentVerifyPage() {
  const params = useParams();
  const token = typeof params.token === "string" ? params.token : String(params.token ?? "");

  const [state, setState] = useState<PageState>("loading");
  const [consent, setConsent] = useState<ConsentData | null>(null);
  const [error, setError] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);

  // ── Загрузка данных согласия ──
  useEffect(() => {
    if (!token) return;

    const controller = new AbortController();

    fetch(`${getApiBaseUrl()}/api/clients/consents/verify/${token}`, {
      signal: controller.signal,
    })
      .then(async (res) => {
        if (controller.signal.aborted) return;
        if (res.status === 410) {
          setState("expired");
          return;
        }
        if (!res.ok) {
          setState("error");
          setError("Не удалось загрузить данные");
          return;
        }
        const data: ConsentData = await res.json();
        if (data.status === "confirmed") {
          setState("confirmed");
        } else {
          setConsent(data);
          setState("ready");
        }
      })
      .catch((err) => {
        if (err?.name === "AbortError") return;
        setState("error");
        setError("Ошибка соединения с сервером");
      });

    return () => controller.abort();
  }, [token]);

  // ── Подтвердить согласие ──
  const handleConfirm = async () => {
    if (submitting) return;
    setSubmitting(true);

    try {
      const res = await fetch(`${getApiBaseUrl()}/api/clients/consents/verify/${token}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });

      if (res.status === 410) {
        setState("expired");
      } else if (res.ok) {
        setState("confirmed");
      } else {
        const data = await res.json().catch(() => ({}));
        setError(data.detail || "Ошибка подтверждения");
        setState("error");
      }
    } catch {
      setError("Ошибка соединения");
      setState("error");
    } finally {
      setSubmitting(false);
    }
  };

  // ── Рендер ──
  return (
    <div
      style={{
        minHeight: "100vh",
        background: "linear-gradient(135deg, #0a0a0a 0%, #1a1a2e 50%, #0a0a0a 100%)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "16px",
        fontFamily: "'Space Grotesk', -apple-system, sans-serif",
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: "480px",
          background: "rgba(255,255,255,0.03)",
          border: "1px solid rgba(255,255,255,0.08)",
          borderRadius: "20px",
          padding: "32px 24px",
          backdropFilter: "blur(20px)",
        }}
      >
        {/* Логотип */}
        <div style={{ textAlign: "center", marginBottom: "24px" }}>
          <div
            style={{
              width: "56px",
              height: "56px",
              borderRadius: "16px",
              background: "linear-gradient(135deg, #3b82f6, #6366F1)",
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: "24px",
              marginBottom: "12px",
            }}
          >
            <AppIcon emoji="🛡️" size={24} />
          </div>
          <h1
            style={{
              color: "#fff",
              fontSize: "20px",
              fontWeight: 600,
              margin: "0 0 4px 0",
            }}
          >
            Подтверждение согласия
          </h1>
          <p style={{ color: "rgba(255,255,255,0.5)", fontSize: "14px", margin: 0 }}>
            Hunter888 · Защита ваших данных
          </p>
        </div>

        {/* ── LOADING ── */}
        {state === "loading" && (
          <div style={{ textAlign: "center", padding: "40px 0" }}>
            <div
              style={{
                width: "40px",
                height: "40px",
                border: "3px solid rgba(255,255,255,0.1)",
                borderTopColor: "var(--info)",
                borderRadius: "50%",
                animation: "spin 1s linear infinite",
                margin: "0 auto 16px",
              }}
            />
            <p style={{ color: "rgba(255,255,255,0.5)", fontSize: "14px" }}>
              Загрузка данных...
            </p>
            <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
          </div>
        )}

        {/* ── READY — форма подтверждения ── */}
        {state === "ready" && consent && (
          <>
            {/* Имя клиента */}
            <div
              style={{
                background: "rgba(59,130,246,0.08)",
                border: "1px solid rgba(59,130,246,0.15)",
                borderRadius: "12px",
                padding: "16px",
                marginBottom: "20px",
              }}
            >
              <p style={{ color: "rgba(255,255,255,0.5)", fontSize: "12px", margin: "0 0 4px 0" }}>
                Клиент
              </p>
              <p style={{ color: "#fff", fontSize: "16px", fontWeight: 500, margin: 0 }}>
                {consent.client_name}
              </p>
            </div>

            {/* Тип согласия */}
            <div
              style={{
                background: "rgba(124,106,232,0.08)",
                border: "1px solid rgba(124,106,232,0.15)",
                borderRadius: "12px",
                padding: "16px",
                marginBottom: "20px",
              }}
            >
              <p style={{ color: "rgba(255,255,255,0.5)", fontSize: "12px", margin: "0 0 4px 0" }}>
                Вы даёте согласие на
              </p>
              <p style={{ color: "#fff", fontSize: "16px", fontWeight: 500, margin: 0 }}>
                {CONSENT_TYPE_LABELS[consent.consent_type] || consent.consent_type}
              </p>
            </div>

            {/* Юридический текст */}
            <div
              style={{
                background: "rgba(255,255,255,0.02)",
                border: "1px solid rgba(255,255,255,0.06)",
                borderRadius: "12px",
                padding: "16px",
                marginBottom: "24px",
                maxHeight: "200px",
                overflowY: "auto",
              }}
            >
              <p style={{ color: "rgba(255,255,255,0.4)", fontSize: "11px", margin: "0 0 8px 0", textTransform: "uppercase", letterSpacing: "0.5px" }}>
                Текст согласия
              </p>
              <p style={{ color: "rgba(255,255,255,0.7)", fontSize: "13px", lineHeight: 1.6, margin: 0 }}>
                В соответствии с Федеральным законом №152-ФЗ «О персональных данных»,
                я даю согласие на обработку моих персональных данных (ФИО, номер телефона,
                адрес электронной почты, сведения о задолженности) в целях оказания
                юридических услуг по процедуре банкротства физических лиц.
              </p>
              <p style={{ color: "rgba(255,255,255,0.7)", fontSize: "13px", lineHeight: 1.6, margin: "12px 0 0 0" }}>
                Согласие может быть отозвано в любой момент путём направления
                уведомления оператору. Срок обработки отзыва — 30 дней.
              </p>
            </div>

            {/* Кнопки */}
            <button
              onClick={handleConfirm}
              disabled={submitting}
              style={{
                width: "100%",
                padding: "16px",
                borderRadius: "12px",
                border: "none",
                background: submitting
                  ? "rgba(59,130,246,0.3)"
                  : "linear-gradient(135deg, #3b82f6, #2563eb)",
                color: "#fff",
                fontSize: "16px",
                fontWeight: 600,
                cursor: submitting ? "not-allowed" : "pointer",
                marginBottom: "12px",
                transition: "all 0.2s",
              }}
            >
              {submitting ? "Подтверждение..." : <><Check size={16} className="inline" /> Подтверждаю согласие</>}
            </button>

            <p
              style={{
                color: "rgba(255,255,255,0.3)",
                fontSize: "12px",
                textAlign: "center",
                margin: "16px 0 0 0",
                lineHeight: 1.5,
              }}
            >
              Нажимая «Подтверждаю», вы соглашаетесь с условиями обработки ПДн.
              Вы можете отозвать согласие в любой момент, связавшись с вашим менеджером.
            </p>
          </>
        )}

        {/* ── CONFIRMED ── */}
        {state === "confirmed" && (
          <div style={{ textAlign: "center", padding: "20px 0" }}>
            <div
              style={{
                width: "64px",
                height: "64px",
                borderRadius: "50%",
                background: "rgba(34,197,94,0.1)",
                border: "2px solid rgba(34,197,94,0.3)",
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                marginBottom: "16px",
              }}
            >
              <Check size={28} />
            </div>
            <h2 style={{ color: "var(--success)", fontSize: "18px", fontWeight: 600, margin: "0 0 8px 0" }}>
              Согласие подтверждено
            </h2>
            <p style={{ color: "rgba(255,255,255,0.5)", fontSize: "14px", lineHeight: 1.5, margin: 0 }}>
              Спасибо! Ваш менеджер получил уведомление.
              Вы можете закрыть эту страницу.
            </p>
          </div>
        )}

        {/* ── EXPIRED ── */}
        {state === "expired" && (
          <div style={{ textAlign: "center", padding: "20px 0" }}>
            <div
              style={{
                width: "64px",
                height: "64px",
                borderRadius: "50%",
                background: "rgba(245,158,11,0.1)",
                border: "2px solid rgba(245,158,11,0.3)",
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: "28px",
                marginBottom: "16px",
              }}
            >
              ⏰
            </div>
            <h2 style={{ color: "var(--warning)", fontSize: "18px", fontWeight: 600, margin: "0 0 8px 0" }}>
              Ссылка недействительна
            </h2>
            <p style={{ color: "rgba(255,255,255,0.5)", fontSize: "14px", lineHeight: 1.5, margin: 0 }}>
              Эта ссылка уже была использована или срок её действия истёк.
              Обратитесь к вашему менеджеру для получения новой ссылки.
            </p>
          </div>
        )}

        {/* ── ERROR ── */}
        {state === "error" && (
          <div style={{ textAlign: "center", padding: "20px 0" }}>
            <div
              style={{
                width: "64px",
                height: "64px",
                borderRadius: "50%",
                background: "rgba(239,68,68,0.1)",
                border: "2px solid rgba(239,68,68,0.3)",
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: "28px",
                marginBottom: "16px",
              }}
            >
              ✕
            </div>
            <h2 style={{ color: "var(--danger)", fontSize: "18px", fontWeight: 600, margin: "0 0 8px 0" }}>
              Ошибка
            </h2>
            <p style={{ color: "rgba(255,255,255,0.5)", fontSize: "14px", lineHeight: 1.5, margin: 0 }}>
              {error || "Произошла ошибка. Попробуйте позже."}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
