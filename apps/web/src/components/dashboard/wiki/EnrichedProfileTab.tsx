"use client";

import { CheckCircle } from "lucide-react";
import {
  Pulse,
  Warning,
  BookOpen,
  Brain,
  Calendar,
  Clock,
  Lightbulb,
  Target,
  TrendUp,
  Lightning,
} from "@phosphor-icons/react";
import { Line, Radar } from "react-chartjs-2";
import { cssVar } from "@/lib/chartTheme";
import type { EnrichedProfile } from "./types";

export function EnrichedProfileTab({ profile }: { profile: EnrichedProfile | null }) {
  if (!profile) {
    return (
      <div style={{ textAlign: "center", padding: "3rem", color: "var(--text-muted)" }}>
        <Pulse size={36} weight="duotone" style={{ margin: "0 auto 1rem", opacity: 0.4 }} />
        <p>Профиль загружается...</p>
      </div>
    );
  }

  const glassCard: React.CSSProperties = {
    background: "var(--bg-secondary)",
    border: "1px solid var(--border-color)",
    borderRadius: 12,
    padding: "1.25rem",
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
  const accentHex = cssVar("--accent", "#6B4DC7");
  const chartText = cssVar("--chart-text", "#D0CDE0");
  const chartGrid = cssVar("--chart-grid", "rgba(255,255,255,0.12)");
  const textSec = cssVar("--text-secondary", "#B8B5CC");

  const skillRadarData = {
    labels: Object.values(SKILL_LABELS),
    datasets: [
      {
        label: profile.name,
        data: skillValues,
        borderColor: accentHex,
        backgroundColor: "rgba(107,77,199,0.25)",
        pointBackgroundColor: accentHex,
        borderWidth: 2.5,
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
        ticks: { color: chartText, backdropColor: "transparent", font: { size: 13 }, stepSize: 25 },
        grid: { color: chartGrid },
        pointLabels: { color: textSec, font: { size: 14, weight: 500 as const } },
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
        borderColor: accentHex,
        backgroundColor: "rgba(107,77,199,0.2)",
        fill: true,
        tension: 0.35,
        pointRadius: 5,
        pointBackgroundColor: accentHex,
        borderWidth: 2.5,
      },
    ],
  };

  const trendOpts: any = {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      x: { ticks: { color: textSec, font: { size: 12 } }, grid: { display: false }, border: { color: "transparent" } },
      y: { beginAtZero: true, ticks: { color: textSec, font: { size: 12 } }, grid: { color: "rgba(107,77,199,0.08)" }, border: { color: "transparent" } },
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
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        {[
          { label: "Всего сессий", value: t.total_sessions, color: "var(--warning)", icon: Target },
          { label: "Средний балл", value: t.avg_score.toFixed(1), color: "var(--success)", icon: TrendUp },
          { label: "Лучший балл", value: t.best_score.toFixed(1), color: "var(--accent)", icon: Lightning },
          { label: "Часов практики", value: t.total_hours.toFixed(1), color: "var(--magenta)", icon: Clock },
        ].map((kpi) => (
          <div key={kpi.label} style={glassCard}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
              <kpi.icon size={16} weight="duotone" style={{ color: kpi.color }} />
              <span style={{ fontSize: "0.875rem", color: "var(--text-secondary)", fontWeight: 500 }}>{kpi.label}</span>
            </div>
            <div style={{ fontSize: "1.75rem", fontWeight: 800, color: kpi.color, fontFamily: "var(--font-geist-mono), monospace" }}>{kpi.value}</div>
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
        <Calendar size={16} weight="duotone" style={{ color: "var(--accent)" }} />
        <span style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Последние 14 дней:</span>
        <span style={{ color: "var(--warning)", fontWeight: 600 }}>{t.recent_14d_sessions} сессий</span>
        <span style={{ color: "var(--text-muted)" }}>|</span>
        <span style={{ color: "var(--success)", fontWeight: 600 }}>Ср. балл: {t.recent_14d_avg_score.toFixed(1)}</span>
        {scoreDelta !== null && (
          <span style={{
            padding: "2px 8px",
            borderRadius: 8,
            fontSize: "0.875rem",
            fontWeight: 600,
            background: scoreDelta >= 0 ? "var(--success-muted)" : "var(--danger-muted)",
            color: scoreDelta >= 0 ? "var(--success)" : "var(--danger)",
          }}>
            {scoreDelta >= 0 ? "↑" : "↓"} {Math.abs(scoreDelta).toFixed(1)} vs всё время
          </span>
        )}
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
        {/* Score trend */}
        <div style={glassCard}>
          <div style={{ color: "var(--text-muted)", fontSize: "0.875rem", fontWeight: 600, marginBottom: "0.5rem" }}>
            <TrendUp size={14} weight="duotone" style={{ display: "inline", verticalAlign: "middle", marginRight: 4 }} />
            Динамика баллов
          </div>
          <div style={{ height: 200 }}>
            {trend.length > 0 ? (
              <Line data={trendData} options={trendOpts} />
            ) : (
              <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "var(--text-muted)", fontSize: "0.875rem" }}>
                Нет данных
              </div>
            )}
          </div>
        </div>

        {/* Skills radar */}
        <div style={glassCard}>
          <div style={{ color: "var(--text-muted)", fontSize: "0.875rem", fontWeight: 600, marginBottom: "0.5rem" }}>
            <Pulse size={14} weight="duotone" style={{ display: "inline", verticalAlign: "middle", marginRight: 4 }} />
            Навыки
            {profile.skills.level !== undefined && (
              <span style={{ marginLeft: 8, color: "var(--warning)", fontSize: "0.875rem" }}>
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
          <div style={{ color: "var(--text-muted)", fontSize: "0.875rem", fontWeight: 600, marginBottom: "0.75rem" }}>
            <Brain size={14} weight="duotone" style={{ display: "inline", verticalAlign: "middle", marginRight: 4 }} />
            Паттерны ({profile.patterns_summary.total})
            <span style={{ marginLeft: 8 }}>
              <span style={{ color: "var(--danger)" }}><Warning size={12} weight="duotone" style={{ display: "inline", verticalAlign: "middle", marginRight: 2 }} /> {profile.patterns_summary.weaknesses}</span>
              {" / "}
              <span style={{ color: "var(--success)" }}><CheckCircle size={12} style={{ display: "inline", verticalAlign: "middle", marginRight: 2 }} /> {profile.patterns_summary.strengths}</span>
            </span>
          </div>
          {profile.patterns_summary.top_weaknesses.length > 0 && (
            <div style={{ marginBottom: "0.5rem" }}>
              <div style={{ fontSize: "0.875rem", color: "var(--danger)", fontWeight: 600, marginBottom: "0.25rem" }}>Основные слабости:</div>
              {profile.patterns_summary.top_weaknesses.map((p) => (
                <div key={p.code} style={{ fontSize: "0.875rem", color: "var(--text-muted)", padding: "2px 0", display: "flex", justifyContent: "space-between" }}>
                  <span>{p.description || p.code}</span>
                  <span style={{ color: "var(--text-muted)" }}>{p.sessions} сес.</span>
                </div>
              ))}
            </div>
          )}
          {profile.patterns_summary.top_strengths.length > 0 && (
            <div>
              <div style={{ fontSize: "0.875rem", color: "var(--success)", fontWeight: 600, marginBottom: "0.25rem" }}>Сильные стороны:</div>
              {profile.patterns_summary.top_strengths.map((p) => (
                <div key={p.code} style={{ fontSize: "0.875rem", color: "var(--text-muted)", padding: "2px 0", display: "flex", justifyContent: "space-between" }}>
                  <span>{p.description || p.code}</span>
                  <span style={{ color: "var(--text-muted)" }}>{p.sessions} сес.</span>
                </div>
              ))}
            </div>
          )}
          {profile.patterns_summary.total === 0 && (
            <div style={{ fontSize: "0.875rem", color: "var(--text-muted)", fontStyle: "italic" }}>Паттерны ещё не обнаружены</div>
          )}
        </div>

        {/* Techniques summary */}
        <div style={glassCard}>
          <div style={{ color: "var(--text-muted)", fontSize: "0.875rem", fontWeight: 600, marginBottom: "0.75rem" }}>
            <Lightbulb size={14} weight="duotone" style={{ display: "inline", verticalAlign: "middle", marginRight: 4 }} />
            Техники ({profile.techniques_summary.total})
          </div>
          {profile.techniques_summary.best.length > 0 ? (
            profile.techniques_summary.best.map((t) => (
              <div key={t.code} style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                fontSize: "0.875rem",
                padding: "0.3rem 0",
                borderBottom: "1px solid rgba(255,255,255,0.04)",
              }}>
                <span style={{ color: "var(--text-muted)" }}>{t.name}</span>
                <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                  <span style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>{t.attempts} попыток</span>
                  <span style={{
                    padding: "1px 8px",
                    borderRadius: 8,
                    fontSize: "0.875rem",
                    fontWeight: 600,
                    background: t.success_rate >= 0.7 ? "var(--success-muted)" : t.success_rate >= 0.4 ? "var(--warning-muted)" : "var(--danger-muted)",
                    color: t.success_rate >= 0.7 ? "var(--success)" : t.success_rate >= 0.4 ? "var(--warning)" : "var(--danger)",
                  }}>
                    {Math.round(t.success_rate * 100)}%
                  </span>
                </div>
              </div>
            ))
          ) : (
            <div style={{ fontSize: "0.875rem", color: "var(--text-muted)", fontStyle: "italic" }}>Техники ещё не обнаружены</div>
          )}
        </div>
      </div>

      {/* Wiki summary */}
      <div style={glassCard}>
        <div style={{ color: "var(--text-muted)", fontSize: "0.875rem", fontWeight: 600, marginBottom: "0.5rem" }}>
          <BookOpen size={14} weight="duotone" style={{ display: "inline", verticalAlign: "middle", marginRight: 4 }} />
          Wiki статус
        </div>
        <div style={{ display: "flex", gap: "2rem", fontSize: "0.875rem", flexWrap: "wrap" }}>
          <div>
            <span style={{ color: "var(--text-muted)" }}>Статус: </span>
            <span style={{ color: profile.wiki.exists ? "var(--success)" : "var(--danger)", fontWeight: 600 }}>
              {profile.wiki.exists ? "Активна" : "Не создана"}
            </span>
          </div>
          <div>
            <span style={{ color: "var(--text-muted)" }}>Страниц: </span>
            <span style={{ color: "var(--warning)", fontWeight: 600 }}>{profile.wiki.pages_count}</span>
          </div>
          <div>
            <span style={{ color: "var(--text-muted)" }}>Проанализировано сессий: </span>
            <span style={{ color: "var(--accent)", fontWeight: 600 }}>{profile.wiki.sessions_ingested}</span>
          </div>
          <div>
            <span style={{ color: "var(--text-muted)" }}>Обнаружено паттернов: </span>
            <span style={{ color: "var(--danger)", fontWeight: 600 }}>{profile.wiki.patterns_discovered}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
