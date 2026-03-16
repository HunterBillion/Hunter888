"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";

interface ScoreLayer {
  label: string;
  value: number;
  weight: number;
  color: string;
}

interface EmotionEntry {
  state: string;
  timestamp: number;
}

interface SessionResult {
  session: {
    id: string;
    status: string;
    started_at: string;
    ended_at: string | null;
    duration_seconds: number | null;
    score_script_adherence: number | null;
    score_objection_handling: number | null;
    score_communication: number | null;
    score_emotional: number | null;
    score_result: number | null;
    score_total: number | null;
    scoring_details: Record<string, unknown> | null;
    emotion_timeline: EmotionEntry[] | null;
    feedback_text: string | null;
  };
  messages: Array<{
    id: string;
    role: string;
    content: string;
    emotion_state: string | null;
    sequence_number: number;
    created_at: string;
  }>;
  score_breakdown: Record<string, unknown> | null;
}

function ScoreCircle({ value, label }: { value: number; label: string }) {
  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (value / 100) * circumference;
  const color =
    value >= 70 ? "#22c55e" : value >= 40 ? "#f59e0b" : "#ef4444";

  return (
    <div className="flex flex-col items-center">
      <svg width="128" height="128" viewBox="0 0 128 128">
        <circle
          cx="64"
          cy="64"
          r={radius}
          fill="none"
          stroke="#e5e7eb"
          strokeWidth="8"
        />
        <circle
          cx="64"
          cy="64"
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth="8"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform="rotate(-90 64 64)"
          style={{ transition: "stroke-dashoffset 1s ease" }}
        />
        <text
          x="64"
          y="60"
          textAnchor="middle"
          className="fill-gray-900 text-3xl font-bold"
          fontSize="28"
          fontWeight="bold"
        >
          {Math.round(value)}
        </text>
        <text
          x="64"
          y="80"
          textAnchor="middle"
          className="fill-gray-400"
          fontSize="11"
        >
          из 100
        </text>
      </svg>
      <span className="mt-1 text-sm font-medium text-gray-600">{label}</span>
    </div>
  );
}

function ScoreBar({
  label,
  value,
  weight,
  color,
}: ScoreLayer) {
  const barColor =
    value >= 70 ? "bg-green-500" : value >= 40 ? "bg-yellow-500" : "bg-red-500";

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium text-gray-700">{label}</span>
        <span className="text-gray-500">
          {Math.round(value)} / 100
          <span className="ml-1 text-xs text-gray-400">
            (x{weight})
          </span>
        </span>
      </div>
      <div className="h-3 w-full rounded-full bg-gray-200">
        <div
          className={`h-3 rounded-full ${barColor}`}
          style={{ width: `${Math.min(value, 100)}%`, transition: "width 1s ease" }}
        />
      </div>
    </div>
  );
}

function EmotionTimeline({ timeline }: { timeline: EmotionEntry[] }) {
  if (!timeline || timeline.length === 0) return null;

  const emotionLabels: Record<string, string> = {
    cold: "Холодный",
    warming: "Теплеет",
    open: "Открытый",
  };
  const emotionColors: Record<string, string> = {
    cold: "bg-blue-400",
    warming: "bg-yellow-400",
    open: "bg-green-400",
  };

  return (
    <div className="rounded-lg bg-white p-6 shadow-sm">
      <h2 className="text-lg font-semibold">Динамика эмоций клиента</h2>
      <div className="mt-4 flex items-end gap-1">
        {timeline.map((entry, i) => {
          const height =
            entry.state === "open" ? "h-16" : entry.state === "warming" ? "h-10" : "h-5";
          return (
            <div key={i} className="flex flex-col items-center gap-1" style={{ flex: 1 }}>
              <div
                className={`w-full rounded-t ${emotionColors[entry.state] || "bg-gray-300"} ${height}`}
                style={{ transition: "height 0.3s ease", minWidth: 8 }}
                title={emotionLabels[entry.state] || entry.state}
              />
            </div>
          );
        })}
      </div>
      <div className="mt-2 flex justify-between text-xs text-gray-400">
        <span>Начало</span>
        <span>Конец</span>
      </div>
      <div className="mt-3 flex gap-4 text-xs">
        {Object.entries(emotionLabels).map(([key, label]) => (
          <div key={key} className="flex items-center gap-1">
            <div className={`h-3 w-3 rounded-full ${emotionColors[key]}`} />
            <span className="text-gray-500">{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function formatDuration(seconds: number | null): string {
  if (!seconds) return "—";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m > 0 ? `${m} мин ${s} сек` : `${s} сек`;
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

  const { session, messages } = result;

  const layers: ScoreLayer[] = [
    {
      label: "Следование скрипту",
      value: session.score_script_adherence ?? 0,
      weight: 0.25,
      color: "green",
    },
    {
      label: "Работа с возражениями",
      value: session.score_objection_handling ?? 0,
      weight: 0.20,
      color: "blue",
    },
    {
      label: "Коммуникация",
      value: session.score_communication ?? 0,
      weight: 0.20,
      color: "purple",
    },
    {
      label: "Эмоциональный интеллект",
      value: session.score_emotional ?? 0,
      weight: 0.15,
      color: "orange",
    },
    {
      label: "Результат",
      value: session.score_result ?? 0,
      weight: 0.20,
      color: "red",
    },
  ];

  const hasScores = session.score_total !== null;

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Результаты тренировки</h1>
        <span className="rounded-full bg-gray-100 px-3 py-1 text-sm text-gray-500">
          {formatDuration(session.duration_seconds)}
        </span>
      </div>

      {/* Total Score */}
      {hasScores && (
        <div className="mt-6 rounded-lg bg-white p-6 shadow-sm">
          <div className="flex flex-col items-center md:flex-row md:items-start md:gap-10">
            <ScoreCircle
              value={session.score_total ?? 0}
              label="Общий балл"
            />
            <div className="mt-6 w-full flex-1 space-y-4 md:mt-0">
              {layers.map((layer) => (
                <ScoreBar key={layer.label} {...layer} />
              ))}
            </div>
          </div>
        </div>
      )}

      {!hasScores && (
        <div className="mt-6 rounded-lg bg-yellow-50 p-4 text-sm text-yellow-700">
          Оценка ещё не рассчитана для этой сессии.
        </div>
      )}

      {/* Emotion Timeline */}
      {session.emotion_timeline && session.emotion_timeline.length > 0 && (
        <div className="mt-6">
          <EmotionTimeline timeline={session.emotion_timeline} />
        </div>
      )}

      {/* Feedback */}
      {session.feedback_text && (
        <div className="mt-6 rounded-lg bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold">Обратная связь</h2>
          <p className="mt-2 text-gray-700">{session.feedback_text}</p>
        </div>
      )}

      {/* Chat Transcript */}
      <div className="mt-6 rounded-lg bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold">
          Диалог ({messages.length} сообщений)
        </h2>
        <div className="mt-4 space-y-3 max-h-[600px] overflow-y-auto">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex gap-3 ${
                msg.role === "user" ? "" : "bg-gray-50 rounded-lg p-2"
              }`}
            >
              <span
                className={`w-20 shrink-0 text-sm font-medium ${
                  msg.role === "user" ? "text-primary-600" : "text-gray-500"
                }`}
              >
                {msg.role === "user" ? "Вы" : "Клиент"}
              </span>
              <div className="flex-1">
                <p className="text-sm">{msg.content}</p>
                {msg.emotion_state && (
                  <span className="mt-1 inline-block rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-400">
                    {msg.emotion_state}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Actions */}
      <div className="mt-8 flex justify-center gap-4">
        <Link
          href="/"
          className="rounded-md border border-gray-300 px-6 py-2 text-gray-700 hover:bg-gray-50"
        >
          На главную
        </Link>
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
