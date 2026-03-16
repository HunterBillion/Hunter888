"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";

interface SessionResult {
  session: {
    id: string;
    status: string;
    score_total: number | null;
    feedback_text: string | null;
  };
  messages: Array<{
    role: string;
    content: string;
    emotion_state: string | null;
  }>;
  score_breakdown: Record<string, number> | null;
}

export default function ResultsPage() {
  const params = useParams();
  const [result, setResult] = useState<SessionResult | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get(`/training/sessions/${params.id}`)
      .then(setResult)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [params.id]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-lg text-gray-500">Загрузка результатов...</div>
      </div>
    );
  }

  if (!result) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-lg text-red-500">Сессия не найдена</div>
      </div>
    );
  }

  const scoreLabels: Record<string, string> = {
    script_adherence: "Следование скрипту",
    objection_handling: "Работа с возражениями",
    communication: "Коммуникация",
    emotional: "Эмоциональный интеллект",
    result: "Результат",
  };

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <h1 className="text-2xl font-bold">Результаты тренировки</h1>

      {result.session.score_total !== null && (
        <div className="mt-6 rounded-lg bg-white p-6 shadow-sm">
          <div className="text-center">
            <div className="text-5xl font-bold text-primary-600">
              {Math.round(result.session.score_total)}
            </div>
            <div className="mt-1 text-gray-500">Общий балл</div>
          </div>

          {result.score_breakdown && (
            <div className="mt-6 space-y-3">
              {Object.entries(result.score_breakdown).map(([key, value]) => (
                <div key={key} className="flex items-center justify-between">
                  <span className="text-sm text-gray-600">
                    {scoreLabels[key] || key}
                  </span>
                  <div className="flex items-center gap-2">
                    <div className="h-2 w-32 rounded-full bg-gray-200">
                      <div
                        className="h-2 rounded-full bg-primary-500"
                        style={{ width: `${value}%` }}
                      />
                    </div>
                    <span className="text-sm font-medium">{Math.round(value)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {result.session.feedback_text && (
        <div className="mt-6 rounded-lg bg-white p-6 shadow-sm">
          <h2 className="font-semibold">Обратная связь</h2>
          <p className="mt-2 text-gray-700">{result.session.feedback_text}</p>
        </div>
      )}

      <div className="mt-6 rounded-lg bg-white p-6 shadow-sm">
        <h2 className="font-semibold">Диалог ({result.messages.length} сообщений)</h2>
        <div className="mt-4 space-y-3">
          {result.messages.map((msg, i) => (
            <div key={i} className="flex gap-3">
              <span className="w-24 shrink-0 text-sm font-medium text-gray-500">
                {msg.role === "user" ? "Вы" : "Клиент"}
              </span>
              <p className="text-sm">{msg.content}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-8 text-center">
        <Link
          href="/training"
          className="rounded-md bg-primary-600 px-6 py-2 text-white hover:bg-primary-700"
        >
          Новая тренировка
        </Link>
      </div>
    </div>
  );
}
