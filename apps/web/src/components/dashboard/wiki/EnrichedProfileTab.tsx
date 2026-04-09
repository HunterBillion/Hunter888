"use client";

import {
  Activity,
  BookOpen,
  Brain,
  Calendar,
  Clock,
  Lightbulb,
  Target,
  TrendingUp,
  Zap,
} from "lucide-react";
import { Line, Radar } from "react-chartjs-2";
import type { EnrichedProfile } from "./types";

export function EnrichedProfileTab({ profile }: { profile: EnrichedProfile | null }) {
  if (!profile) {
    return (
      <div style={{ textAlign: "center", padding: "3rem", color: "#6b7280" }}>
        <Activity size={36} style={{ margin: "0 auto 1rem", opacity: 0.4 }} />
        <p>Профиль загружается...</p>
      </div>
    );
  }

  const glassCard: React.CSSProperties = {
    background: "rgba(255,255,255,0.03)",
    border: "1px solid rgba(255,255,255,0.06)",
    borderRadius: 12,
    padding: "1rem",
  };

  const SKILL_LABELS: Record<string, string> = {
    empathy: "Эмпатия",
    knowledge: "Знания",
    objection_handling: "Возражения",
    stress_resistance: "Стрессоуст.",
    closing: "Закрытие",
    qualification: "Квалификация",
  };

  const skillKeys = Object.keys(SKILL_LABELS);
  const skillValues = skillKeys.map((k) => profile.skills[k] || 0);

  // Skills radar
  const skillRadarData = {
    labels: Object.values(SKILL_LABELS),
    datasets: [
      {
        label: profile.name,
        data: skillValues,
        borderColor: "#f59e0b",
        backgroundColor: "rgba(245,158,11,0.15)",
        pointBackgroundColor: "#f59e0b",
        borderWidth: 2,
      },
    ],
  };

  const radarOpts: any = {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      r: {
        beginAtZero: true,
        max: 100,
        ticks: { color: "#6b7280", backdropColor: "transparent", font: { size: 10 }, stepSize: 25 },
        grid: { color: "rgba(255,255,255,0.06)" },
        pointLabels: { color: "#9ca3af", font: { size: 11 } },
      },
    },
    plugins: { legend: { display: false } },
  };

  // Score trend line chart
  const trend = profile.training.score_trend || [];
  const trendData = {
    labels: trend.map((t) => new Date(t.date).toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" })),
    datasets: [
      {
        label: "Балл",
        data: trend.map((t) => t.score),
        borderColor: "#6366f1",
        backgroundColor: "rgba(99,102,241,0.1)",
        fill: true,
        tension: 0.3,
        pointRadius: 4,
        pointBackgroundColor: "#6366f1",
      },
    ],
  };

  const trendOpts: any = {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      x: { ticks: { color: "#6b7280", font: { size: 10 } }, grid: { display: false } },
      y: { beginAtZero: true, ticks: { color: "#6b7280" }, grid: { color: "rgba(255,255,255,0.04)" } },
    },
    plugins: { legend: { display: false } },
  };

  const t = profile.training;
  const scoreDelta = t.recent_14d_sessions > 0 && t.total_sessions > t.recent_14d_sessions
    ? t.recent_14d_avg_score - t.avg_score
    : null;

  return (
    <div>
      {/* KPI Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "0.75rem", marginBottom: "1rem" }}>
        {[
          { label: "Всего сессий", value: t.total_sessions, color: "#f59e0b", icon: Target },
          { label: "Средний балл", value: t.avg_score.toFixed(1), color: "#22c55e", icon: TrendingUp },
          { label: "Лучший балл", value: t.best_score.toFixed(1), color: "#6366f1", icon: Zap },
          { label: "Часов практики", value: t.total_hours.toFixed(1), color: "#ec4899", icon: Clock },
        ].map((kpi) => (
          <div key={kpi.label} style={glassCard}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginBottom: "0.3rem" }}>
              <kpi.icon size={14} style={{ color: kpi.color }} />
              <span style={{ fontSize: "0.75rem", color: "#6b7280" }}>{kpi.label}</span>
            </div>
            <div style={{ fontSize: "1.4rem", fontWeight: 700, color: kpi.color }}>{kpi.value}</div>
          </div>
        ))}
      </div>

      {/* 14-day trend badge */}
      <div style={{
        display: "flex",
        gap: "0.75rem",
        marginBottom: "1rem",
        padding: "0.75rem 1rem",
        ...glassCard,
        flexWrap: "wrap",
        alignItems: "center",
      }}>
        <Calendar size={16} style={{ color: "#6366f1" }} />
        <span style={{ color: "#9ca3af", fontSize: "0.85rem" }}>Последние 14 дней:</span>
        <span style={{ color: "#f59e0b", fontWeight: 600 }}>{t.recent_14d_sessions} сессий</span>
        <span style={{ color: "#9ca3af" }}>|</span>
        <span style={{ color: "#22c55e", fontWeight: 600 }}>Ср. балл: {t.recent_14d_avg_score.toFixed(1)}</span>
        {scoreDelta !== null && (
          <span style={{
            padding: "2px 8px",
            borderRadius: 8,
            fontSize: "0.75rem",
            fontWeight: 600,
            background: scoreDelta >= 0 ? "rgba(34,197,94,0.12)" : "rgba(239,68,68,0.12)",
            color: scoreDelta >= 0 ? "#22c55e" : "#ef4444",
          }}>
            {scoreDelta >= 0 ? "↑" : "↓"} {Math.abs(scoreDelta).toFixed(1)} vs всё время
          </span>
        )}
      </div>

      {/* Charts row */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem", marginBottom: "1rem" }}>
        {/* Score trend */}
        <div style={glassCard}>
          <div style={{ color: "#9ca3af", fontSize: "0.8rem", fontWeight: 600, marginBottom: "0.5rem" }}>
            <TrendingUp size={14} style={{ display: "inline", verticalAlign: "middle", marginRight: 4 }} />
            Динамика баллов
          </div>
          <div style={{ height: 200 }}>
            {trend.length > 0 ? (
              <Line data={trendData} options={trendOpts} />
            ) : (
              <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "#6b7280", fontSize: "0.85rem" }}>
                Нет данных
              </div>
            )}
          </div>
        </div>

        {/* Skills radar */}
        <div style={glassCard}>
          <div style={{ color: "#9ca3af", fontSize: "0.8rem", fontWeight: 600, marginBottom: "0.5rem" }}>
            <Activity size={14} style={{ display: "inline", verticalAlign: "middle", marginRight: 4 }} />
            Навыки
            {profile.skills.level !== undefined && (
              <span style={{ marginLeft: 8, color: "#f59e0b", fontSize: "0.75rem" }}>
                Ур. {profile.skills.level} | XP: {profile.skills.total_xp} | Hunter: {profile.skills.hunter_score}
              </span>
            )}
          </div>
          <div style={{ height: 200 }}>
            <Radar data={skillRadarData} options={radarOpts} />
          </div>
        </div>
      </div>

      {/* Patterns & Techniques summary */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem", marginBottom: "1rem" }}>
        {/* Patterns summary */}
        <div style={glassCard}>
          <div style={{ color: "#9ca3af", fontSize: "0.8rem", fontWeight: 600, marginBottom: "0.75rem" }}>
            <Brain size={14} style={{ display: "inline", verticalAlign: "middle", marginRight: 4 }} />
            Паттерны ({profile.patterns_summary.total})
            <span style={{ marginLeft: 8 }}>
              <span style={{ color: "#ef4444" }}>⚠ {profile.patterns_summary.weaknesses}</span>
              {" / "}
              <span style={{ color: "#22c55e" }}>✓ {profile.patterns_summary.strengths}</span>
            </span>
          </div>
          {profile.patterns_summary.top_weaknesses.length > 0 && (
            <div style={{ marginBottom: "0.5rem" }}>
              <div style={{ fontSize: "0.7rem", color: "#ef4444", fontWeight: 600, marginBottom: "0.25rem" }}>Основные слабости:</div>
              {profile.patterns_summary.top_weaknesses.map((p) => (
                <div key={p.code} style={{ fontSize: "0.75rem", color: "#d1d5db", padding: "2px 0", display: "flex", justifyContent: "space-between" }}>
                  <span>{p.description || p.code}</span>
                  <span style={{ color: "#6b7280" }}>{p.sessions} сес.</span>
                </div>
              ))}
            </div>
          )}
          {profile.patterns_summary.top_strengths.length > 0 && (
            <div>
              <div style={{ fontSize: "0.7rem", color: "#22c55e", fontWeight: 600, marginBottom: "0.25rem" }}>Сильные стороны:</div>
              {profile.patterns_summary.top_strengths.map((p) => (
                <div key={p.code} style={{ fontSize: "0.75rem", color: "#d1d5db", padding: "2px 0", display: "flex", justifyContent: "space-between" }}>
                  <span>{p.description || p.code}</span>
                  <span style={{ color: "#6b7280" }}>{p.sessions} сес.</span>
                </div>
              ))}
            </div>
          )}
          {profile.patterns_summary.total === 0 && (
            <div style={{ fontSize: "0.8rem", color: "#6b7280", fontStyle: "italic" }}>Паттерны ещё не обнаружены</div>
          )}
        </div>

        {/* Techniques summary */}
        <div style={glassCard}>
          <div style={{ color: "#9ca3af", fontSize: "0.8rem", fontWeight: 600, marginBottom: "0.75rem" }}>
            <Lightbulb size={14} style={{ display: "inline", verticalAlign: "middle", marginRight: 4 }} />
            Техники ({profile.techniques_summary.total})
          </div>
          {profile.techniques_summary.best.length > 0 ? (
            profile.techniques_summary.best.map((t) => (
              <div key={t.code} style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                fontSize: "0.8rem",
                padding: "0.3rem 0",
                borderBottom: "1px solid rgba(255,255,255,0.04)",
              }}>
                <span style={{ color: "#d1d5db" }}>{t.name}</span>
                <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                  <span style={{ color: "#6b7280", fontSize: "0.7rem" }}>{t.attempts} попыток</span>
                  <span style={{
                    padding: "1px 8px",
                    borderRadius: 8,
                    fontSize: "0.7rem",
                    fontWeight: 600,
                    background: t.success_rate >= 0.7 ? "rgba(34,197,94,0.12)" : t.success_rate >= 0.4 ? "rgba(245,158,11,0.12)" : "rgba(239,68,68,0.12)",
                    color: t.success_rate >= 0.7 ? "#22c55e" : t.success_rate >= 0.4 ? "#f59e0b" : "#ef4444",
                  }}>
                    {Math.round(t.success_rate * 100)}%
                  </span>
                </div>
              </div>
            ))
          ) : (
            <div style={{ fontSize: "0.8rem", color: "#6b7280", fontStyle: "italic" }}>Техники ещё не обнаружены</div>
          )}
        </div>
      </div>

      {/* Wiki summary */}
      <div style={glassCard}>
        <div style={{ color: "#9ca3af", fontSize: "0.8rem", fontWeight: 600, marginBottom: "0.5rem" }}>
          <BookOpen size={14} style={{ display: "inline", verticalAlign: "middle", marginRight: 4 }} />
          Wiki статус
        </div>
        <div style={{ display: "flex", gap: "2rem", fontSize: "0.85rem", flexWrap: "wrap" }}>
          <div>
            <span style={{ color: "#6b7280" }}>Статус: </span>
            <span style={{ color: profile.wiki.exists ? "#22c55e" : "#ef4444", fontWeight: 600 }}>
              {profile.wiki.exists ? "Активна" : "Не создана"}
            </span>
          </div>
          <div>
            <span style={{ color: "#6b7280" }}>Страниц: </span>
            <span style={{ color: "#f59e0b", fontWeight: 600 }}>{profile.wiki.pages_count}</span>
          </div>
          <div>
            <span style={{ color: "#6b7280" }}>Проанализировано сессий: </span>
            <span style={{ color: "#6366f1", fontWeight: 600 }}>{profile.wiki.sessions_ingested}</span>
          </div>
          <div>
            <span style={{ color: "#6b7280" }}>Обнаружено паттернов: </span>
            <span style={{ color: "#ef4444", fontWeight: 600 }}>{profile.wiki.patterns_discovered}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
