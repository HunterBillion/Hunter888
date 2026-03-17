"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import PentagramChart from "@/components/results/PentagramChart";
import EmotionTimeline from "@/components/results/EmotionTimeline";
import InsightCard from "@/components/results/InsightCard";

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
    score_anti_patterns: number | null;
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

function formatDuration(seconds: number | null): string {
  if (!seconds) return "--:--";
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
        <div className="text-lg text-gray-500 animate-pulse">Загрузка результатов...</div>
      </div>
    );
  }

  if (!result) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-lg text-vh-red">Сессия не найдена</div>
      </div>
    );
  }

  const { session, messages } = result;

  const totalScore = session.score_total ?? 0;
  const hasScores = session.score_total !== null;

  // Score color
  const scoreColor =
    totalScore >= 70 ? "text-vh-green" : totalScore >= 40 ? "text-yellow-400" : "text-vh-red";

  // Pentagram data
  const scoreItems = [
    { label: "Скрипт", value: session.score_script_adherence ?? 0, max: 30 },
    { label: "Возражения", value: session.score_objection_handling ?? 0, max: 25 },
    { label: "Коммуникация", value: session.score_communication ?? 0, max: 20 },
    { label: "Антипаттерны", value: Math.max(0, 15 + (session.score_anti_patterns ?? 0)), max: 15 },
    { label: "Результат", value: session.score_result ?? 0, max: 10 },
  ];

  const pentagramData = {
    labels: scoreItems.map((s) => s.label),
    values: scoreItems.map((s) => s.max > 0 ? (s.value / s.max) * 100 : 0),
  };

  // Find critical drops and key recoveries in emotion timeline
  const timeline = session.emotion_timeline || [];
  let criticalDrop: { from: string; to: string; index: number } | null = null;
  let keyRecovery: { from: string; to: string; index: number } | null = null;
  const stateValues: Record<string, number> = { cold: 0, warming: 1, open: 2 };

  for (let i = 1; i < timeline.length; i++) {
    const prev = stateValues[timeline[i - 1].state] ?? 0;
    const curr = stateValues[timeline[i].state] ?? 0;
    if (curr < prev && !criticalDrop) {
      criticalDrop = { from: timeline[i - 1].state, to: timeline[i].state, index: i };
    }
    if (curr > prev && !keyRecovery) {
      keyRecovery = { from: timeline[i - 1].state, to: timeline[i].state, index: i };
    }
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs font-mono text-vh-purple tracking-widest">POST-FLIGHT REPORT</p>
          <h1 className="text-2xl font-display font-bold text-gray-100 tracking-wider mt-1">
            РЕЗУЛЬТАТЫ ТРЕНИРОВКИ
          </h1>
        </div>
        <span className="rounded-lg bg-white/5 border border-white/10 px-3 py-1 text-sm font-mono text-gray-400">
          {formatDuration(session.duration_seconds)}
        </span>
      </div>

      {/* Total Score + Pentagram */}
      {hasScores && (
        <div className="mt-6 glass-panel p-6">
          <div className="flex flex-col items-center md:flex-row md:items-start md:gap-10">
            {/* Total score circle */}
            <div className="flex flex-col items-center">
              <p className="text-xs font-mono text-gray-500 tracking-widest mb-2">TOTAL SCORE</p>
              <div className="relative w-32 h-32">
                <svg width="128" height="128" viewBox="0 0 128 128">
                  <circle cx="64" cy="64" r="54" fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="8" />
                  <circle
                    cx="64" cy="64" r="54"
                    fill="none"
                    stroke={totalScore >= 70 ? "#00FF66" : totalScore >= 40 ? "#f59e0b" : "#FF3333"}
                    strokeWidth="8"
                    strokeDasharray={2 * Math.PI * 54}
                    strokeDashoffset={2 * Math.PI * 54 * (1 - totalScore / 100)}
                    strokeLinecap="round"
                    transform="rotate(-90 64 64)"
                    style={{ transition: "stroke-dashoffset 1s ease" }}
                  />
                  <text x="64" y="60" textAnchor="middle" className={`${scoreColor} font-bold`} fontSize="28" fontWeight="bold" fill="currentColor">
                    {Math.round(totalScore)}
                  </text>
                  <text x="64" y="80" textAnchor="middle" fill="#6b7280" fontSize="11">
                    из 100
                  </text>
                </svg>
              </div>
            </div>

            {/* Pentagram chart */}
            <div className="mt-6 w-full flex-1 md:mt-0">
              <p className="text-xs font-mono text-gray-500 tracking-widest mb-3">PENTAGRAM OF MASTERY</p>
              <PentagramChart data={pentagramData} />
            </div>
          </div>

          {/* Score bars */}
          <div className="mt-6 space-y-3">
            {scoreItems.map((item) => {
              const pct = item.max > 0 ? (item.value / item.max) * 100 : 0;
              const barColor = pct >= 70 ? "bg-vh-green" : pct >= 40 ? "bg-yellow-400" : "bg-vh-red";
              return (
                <div key={item.label} className="space-y-1">
                  <div className="flex items-center justify-between text-sm">
                    <span className="font-medium text-gray-300">{item.label}</span>
                    <span className="text-gray-500 font-mono text-xs">
                      {Math.round(item.value)} / {item.max}
                    </span>
                  </div>
                  <div className="h-2 w-full rounded-full bg-white/10">
                    <div
                      className={`h-2 rounded-full ${barColor}`}
                      style={{ width: `${Math.min(pct, 100)}%`, transition: "width 1s ease" }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {!hasScores && (
        <div className="mt-6 glass-panel p-4 text-sm text-yellow-400 border-yellow-500/30">
          Оценка ещё не рассчитана для этой сессии.
        </div>
      )}

      {/* Insights */}
      {(criticalDrop || keyRecovery) && (
        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          {criticalDrop && (
            <InsightCard
              type="drop"
              title="CRITICAL DROP"
              description={`Эмоция клиента упала: ${criticalDrop.from} → ${criticalDrop.to}`}
            />
          )}
          {keyRecovery && (
            <InsightCard
              type="recovery"
              title="KEY RECOVERY"
              description={`Восстановление: ${keyRecovery.from} → ${keyRecovery.to}`}
            />
          )}
        </div>
      )}

      {/* Emotion Timeline */}
      {timeline.length > 0 && (
        <div className="mt-6 glass-panel p-6">
          <p className="text-xs font-mono text-gray-500 tracking-widest mb-3">EMOTION TIMELINE</p>
          <EmotionTimeline timeline={timeline} />
        </div>
      )}

      {/* Feedback */}
      {session.feedback_text && (
        <div className="mt-6 glass-panel p-6">
          <p className="text-xs font-mono text-gray-500 tracking-widest mb-2">AI FEEDBACK</p>
          <p className="text-gray-300 text-sm">{session.feedback_text}</p>
        </div>
      )}

      {/* Chat Transcript */}
      <div className="mt-6 glass-panel p-6">
        <p className="text-xs font-mono text-gray-500 tracking-widest mb-3">
          TRANSCRIPT ({messages.length} MESSAGES)
        </p>
        <div className="space-y-3 max-h-[600px] overflow-y-auto">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex gap-3 ${msg.role !== "user" ? "bg-white/5 rounded-lg p-2" : ""}`}
            >
              <span className={`w-16 shrink-0 text-xs font-mono ${msg.role === "user" ? "text-vh-purple" : "text-gray-500"}`}>
                {msg.role === "user" ? "YOU" : "CLIENT"}
              </span>
              <div className="flex-1">
                <p className="text-sm text-gray-300">{msg.content}</p>
                {msg.emotion_state && (
                  <span className="mt-1 inline-block rounded-full bg-white/5 px-2 py-0.5 text-xs text-gray-500">
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
        <Link href="/" className="vh-btn-outline">
          На главную
        </Link>
        <Link href="/training" className="vh-btn-primary">
          Новая тренировка
        </Link>
      </div>
    </div>
  );
}
