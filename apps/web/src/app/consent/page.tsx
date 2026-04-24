"use client";

import { useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { Shield, AlertTriangle, Check, X, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { api } from "@/lib/api";
import { clearTokens } from "@/lib/auth";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { toast } from "sonner";

export default function ConsentPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  // H6 (Roadmap Phase 0 §5.1): респектим ``?next=`` от register-флоу.
  // Safelist локальных путей — никаких внешних редиректов.
  const rawNext = searchParams?.get("next") ?? null;
  const nextPath = rawNext && rawNext.startsWith("/") && !rawNext.startsWith("//") ? rawNext : "/home";
  const [accepted, setAccepted] = useState(false);
  const [declined, setDeclined] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [checking, setChecking] = useState(true);
  // 2026-04-18: отдельное состояние "уже принято" — вместо мгновенного
  // router.replace("/home") показываем экран-подтверждение с кнопкой
  // "На главную". Раньше редирект был похож на "выбивает", плюс при
  // 401 на /consent/status api.ts иногда стартовал refresh-флоу, который
  // при неудаче чистил токены → middleware отправлял на /login. Теперь
  // страница НЕ делает никаких автоматических редиректов — решает юзер.
  const [alreadyAccepted, setAlreadyAccepted] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.get<{ all_accepted: boolean }>("/consent/status")
      .then((data) => {
        if (cancelled) return;
        if (data.all_accepted) {
          setAlreadyAccepted(true);
        }
        setChecking(false);
      })
      .catch(() => {
        // API error (401, 500 etc.) — показываем форму, пусть юзер попробует.
        // Если действительно нет сессии — middleware сам отправит на /login
        // при первом state-changing запросе. Но для GET /consent/status не
        // стоит делать никаких редиректов.
        if (!cancelled) setChecking(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleAccept = async () => {
    if (!accepted) return;
    setLoading(true);
    setError("");

    try {
      await api.post("/consent/", {
        consent_type: "personal_data_processing",
        version: "1.0",
      });
      router.replace(nextPath);
      toast.success("Согласие принято");
    } catch (err: unknown) {
      const raw = err instanceof Error ? err.message : "";
      const status = (err as { status?: number }).status;
      // 409 = consent already accepted — treat as success
      if (status === 409 || raw.toLowerCase().includes("already")) {
        toast.info("Согласие уже было принято");
        router.replace(nextPath);
        return;
      }
      // CSRF 403 — session expired, re-login needed
      if (raw.toLowerCase().includes("csrf") || status === 403) {
        toast.error("Сессия истекла. Пожалуйста, войдите заново.");
        setError("Сессия истекла. Пожалуйста, войдите заново.");
      } else if (status === 429) {
        toast.warning("Подождите перед повторной попыткой");
        setError("Слишком много запросов. Подождите.");
      } else {
        toast.error(raw || "Не удалось сохранить согласие");
        setError(raw || "Не удалось сохранить согласие");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleDecline = () => setDeclined(true);

  const handleLogout = () => {
    clearTokens();
    router.replace("/");
  };

  // Show nothing while checking consent status (prevents flash before redirect)
  if (checking) {
    return (
      <div className="flex min-h-screen items-center justify-center" style={{ background: "var(--bg-primary)" }}>
        <div className="animate-spin rounded-full h-8 w-8 border-2 border-transparent" style={{ borderTopColor: "var(--accent)" }} />
      </div>
    );
  }

  // 2026-04-18: явная view если согласие уже принято — не редиректим
  // автоматически. Юзер сам решает вернуться на /home или выйти. Это
  // убирает "feels like kicked out" UX при повторном визите админа.
  if (alreadyAccepted) {
    return (
      <div className="flex min-h-screen items-center justify-center px-4" style={{ background: "var(--bg-primary)" }}>
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="glass-panel w-full max-w-lg p-8 text-center"
        >
          <div
            className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl"
            style={{ background: "color-mix(in srgb, var(--success) 12%, transparent)" }}
          >
            <Check size={28} style={{ color: "var(--success)" }} />
          </div>
          <h1 className="font-display text-2xl font-bold" style={{ color: "var(--text-primary)" }}>
            Согласие уже принято
          </h1>
          <p className="mt-3 text-sm" style={{ color: "var(--text-secondary)" }}>
            Вы уже подтвердили согласие на обработку персональных данных.
            Дополнительных действий не требуется.
          </p>
          <div className="mt-6 flex justify-center gap-3">
            <Button onClick={() => router.push("/home")}>
              <ArrowRight size={16} className="mr-1.5" /> На главную
            </Button>
          </div>
        </motion.div>
      </div>
    );
  }

  if (declined) {
    return (
      <div className="flex min-h-screen items-center justify-center px-4" style={{ background: "var(--bg-primary)" }}>
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="glass-panel w-full max-w-lg p-8 text-center"
        >
          <div
            className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl"
            style={{ background: "var(--danger-muted, rgba(239, 68, 68, 0.1))" }}
          >
            <AlertTriangle size={28} style={{ color: "var(--danger)" }} />
          </div>
          <h1 className="font-display text-2xl font-bold" style={{ color: "var(--danger)" }}>
            СОГЛАСИЕ НЕОБХОДИМО
          </h1>
          <p className="mt-3 text-sm" style={{ color: "var(--text-secondary)" }}>
            Для использования платформы X Hunter необходимо дать согласие на
            обработку персональных данных в соответствии с ФЗ N 152-ФЗ.
          </p>
          <div className="mt-6 flex justify-center gap-3">
            <Button onClick={() => setDeclined(false)}>
              Вернуться
            </Button>
            <motion.button
              onClick={handleLogout}
              className="rounded-xl px-6 py-3 text-sm font-semibold transition-colors"
              style={{
                background: "var(--danger-muted, rgba(239, 68, 68, 0.1))",
                border: "1px solid var(--danger)",
                color: "var(--danger)",
              }}
              whileTap={{ scale: 0.97 }}
            >
              Выйти
            </motion.button>
          </div>
        </motion.div>
      </div>
    );
  }

  return (
    <div
      className="flex min-h-screen items-center justify-center px-4 py-8"
      style={{ background: "var(--bg-primary)" }}
    >
      <div className="absolute right-4 top-4">
        <ThemeToggle />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="glass-panel w-full max-w-2xl p-8"
      >
        <div className="mb-6 text-center">
          <motion.div
            initial={{ scale: 0.8 }}
            animate={{ scale: 1 }}
            transition={{ type: "spring", stiffness: 300, delay: 0.1 }}
            className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl"
            style={{ background: "var(--accent-muted)" }}
          >
            <Shield size={24} style={{ color: "var(--accent)" }} />
          </motion.div>
          <h1
            className="font-display text-2xl font-bold tracking-wider"
            style={{ color: "var(--text-primary)" }}
          >
            СОГЛАСИЕ НА ОБРАБОТКУ ДАННЫХ
          </h1>
          <p className="mt-1 text-sm" style={{ color: "var(--text-muted)" }}>
            В соответствии с Федеральным законом от 27.07.2006 N 152-ФЗ
          </p>
        </div>

        <div
          className="rounded-xl p-5"
          style={{
            background: "var(--input-bg)",
            border: "1px solid var(--border-color)",
          }}
        >
          <div
            className="max-h-72 overflow-y-auto pr-2 text-sm leading-relaxed"
            style={{ color: "var(--text-secondary)" }}
          >
            <p className="mb-3">
              Настоящим я, субъект персональных данных, в соответствии с
              Федеральным законом от 27 июля 2006 года N 152-ФЗ &laquo;О
              персональных данных&raquo;, свободно, своей волей и в своем
              интересе даю согласие на обработку моих персональных данных
              оператору платформы X Hunter (далее &mdash; Оператор).
            </p>

            <p className="mb-2 font-semibold" style={{ color: "var(--text-primary)" }}>
              Перечень персональных данных:
            </p>
            <ul className="mb-3 list-inside list-disc space-y-1">
              <li>Фамилия, имя, отчество</li>
              <li>Адрес электронной почты</li>
              <li>Записи голоса (аудиозаписи тренировок)</li>
              <li>Текстовые сообщения в рамках тренировочных сессий</li>
              <li>Результаты оценки и статистика обучения</li>
              <li>Сведения о должности и подразделении</li>
            </ul>

            <p className="mb-2 font-semibold" style={{ color: "var(--text-primary)" }}>
              Цели обработки:
            </p>
            <ul className="mb-3 list-inside list-disc space-y-1">
              <li>Проведение тренировочных сессий с AI-персонажами</li>
              <li>Распознавание речи и преобразование в текст</li>
              <li>Оценка качества коммуникации и формирование обратной связи</li>
              <li>Формирование статистики обучения и отчётов</li>
              <li>Улучшение качества работы платформы</li>
            </ul>

            <p className="mb-3">
              Согласие действует с момента его предоставления и до момента его
              отзыва. Отзыв согласия может быть осуществлён путём направления
              письменного заявления Оператору.
            </p>

            <p>
              Я подтверждаю, что ознакомлен(а) с правами субъекта персональных
              данных, предусмотренными главой 3 ФЗ N 152-ФЗ.
            </p>
          </div>
        </div>

        <AnimatePresence>
          {error && (
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              className="mt-4 flex items-center gap-2 rounded-xl p-3 text-sm"
              style={{
                background: "var(--danger-muted, rgba(239, 68, 68, 0.08))",
                border: "1px solid var(--danger)",
                color: "var(--danger)",
              }}
            >
              <AlertTriangle size={16} />
              {error}
            </motion.div>
          )}
        </AnimatePresence>

        <div className="mt-6 space-y-4">
          <label className="flex cursor-pointer items-start gap-3">
            <div className="relative mt-0.5">
              <input
                type="checkbox"
                checked={accepted}
                onChange={(e) => setAccepted(e.target.checked)}
                className="peer sr-only"
              />
              <div
                className="flex h-5 w-5 items-center justify-center rounded-md transition-all"
                style={{
                  background: accepted ? "var(--accent)" : "var(--input-bg)",
                  border: `1px solid ${accepted ? "var(--accent)" : "var(--border-color)"}`,
                }}
              >
                {accepted && <Check size={14} className="text-white" />}
              </div>
            </div>
            <span className="text-sm" style={{ color: "var(--text-secondary)" }}>
              Я даю согласие на обработку персональных данных
            </span>
          </label>

          <div className="flex gap-3">
            <motion.button
              onClick={handleDecline}
              className="rounded-xl px-6 py-3 text-sm font-medium flex-1 transition-colors"
              style={{
                background: "var(--input-bg)",
                border: "1px solid var(--border-color)",
                color: "var(--text-secondary)",
              }}
              whileTap={{ scale: 0.98 }}
            >
              Отклонить
            </motion.button>
            <Button variant="primary" loading={loading} disabled={!accepted} iconRight={<ArrowRight size={16} />} onClick={handleAccept} className="flex-1">
              Подтвердить
            </Button>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
