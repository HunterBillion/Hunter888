"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { clearTokens } from "@/lib/auth";

export default function ConsentPage() {
  const router = useRouter();
  const [accepted, setAccepted] = useState(false);
  const [declined, setDeclined] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleAccept = async () => {
    if (!accepted) return;
    setLoading(true);
    setError("");

    try {
      await api.post("/consent/", {
        consent_type: "personal_data_processing",
        version: "1.0",
      });
      router.replace("/training");
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Не удалось сохранить согласие";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  const handleDecline = () => {
    setDeclined(true);
  };

  const handleLogout = () => {
    clearTokens();
    router.replace("/login");
  };

  if (declined) {
    return (
      <div className="flex min-h-screen items-center justify-center px-4">
        <div className="glass-panel w-full max-w-lg p-8 space-y-6 text-center">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-vh-red/20">
            <svg
              className="h-8 w-8 text-vh-red"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth="1.5"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z"
              />
            </svg>
          </div>
          <h1 className="text-2xl font-display font-bold text-vh-red">
            СОГЛАСИЕ НЕОБХОДИМО
          </h1>
          <p className="text-gray-400">
            Для использования платформы VibeHunter необходимо дать согласие на
            обработку персональных данных в соответствии с Федеральным законом
            N 152-ФЗ.
          </p>
          <div className="flex justify-center gap-4">
            <button
              onClick={() => setDeclined(false)}
              className="vh-btn-outline"
            >
              Вернуться
            </button>
            <button
              onClick={handleLogout}
              className="rounded-lg bg-vh-red/20 border border-vh-red/40 px-6 py-2 text-sm font-medium text-vh-red hover:bg-vh-red/30 transition-colors"
            >
              Выйти
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-8">
      <div className="glass-panel w-full max-w-2xl p-8 space-y-6">
        <div className="text-center">
          <h1 className="text-2xl font-display font-bold text-vh-purple">
            СОГЛАСИЕ НА ОБРАБОТКУ ДАННЫХ
          </h1>
          <p className="mt-2 text-sm text-gray-400">
            В соответствии с Федеральным законом от 27.07.2006 N 152-ФЗ
            &laquo;О персональных данных&raquo;
          </p>
        </div>

        <div className="rounded-lg border border-white/10 bg-white/5 p-6">
          <div className="max-h-80 overflow-y-auto pr-2 text-sm leading-relaxed text-gray-300">
            <p className="mb-3">
              Настоящим я, субъект персональных данных, в соответствии с
              Федеральным законом от 27 июля 2006 года N 152-ФЗ &laquo;О
              персональных данных&raquo;, свободно, своей волей и в своем
              интересе даю согласие на обработку моих персональных данных
              оператору платформы VibeHunter (далее &mdash; Оператор).
            </p>

            <p className="mb-3 font-semibold text-gray-200">
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

            <p className="mb-3 font-semibold text-gray-200">Цели обработки:</p>
            <ul className="mb-3 list-inside list-disc space-y-1">
              <li>Проведение тренировочных сессий с AI-персонажами</li>
              <li>Распознавание речи и преобразование в текст</li>
              <li>Оценка качества коммуникации и формирование обратной связи</li>
              <li>Формирование статистики обучения и отчетов</li>
              <li>Улучшение качества работы платформы</li>
            </ul>

            <p className="mb-3">
              Согласие действует с момента его предоставления и до момента его
              отзыва. Отзыв согласия может быть осуществлен путем направления
              письменного заявления Оператору.
            </p>

            <p>
              Я подтверждаю, что ознакомлен(а) с правами субъекта персональных
              данных, предусмотренными главой 3 ФЗ N 152-ФЗ.
            </p>
          </div>
        </div>

        {error && (
          <div className="rounded-md bg-vh-red/10 border border-vh-red/30 p-3 text-sm text-vh-red">
            {error}
          </div>
        )}

        <div className="space-y-4">
          <label className="flex items-start gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={accepted}
              onChange={(e) => setAccepted(e.target.checked)}
              className="mt-0.5 h-5 w-5 rounded border-white/20 bg-white/10 text-vh-purple focus:ring-vh-purple"
            />
            <span className="text-sm text-gray-300">
              Я даю согласие на обработку персональных данных
            </span>
          </label>

          <div className="flex gap-4">
            <button
              onClick={handleAccept}
              disabled={!accepted || loading}
              className="vh-btn-primary flex-1"
            >
              {loading ? "Сохранение..." : "Подтвердить"}
            </button>
            <button
              onClick={handleDecline}
              className="vh-btn-outline flex-1"
            >
              Отклонить
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
