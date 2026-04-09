"use client";

import { motion } from "framer-motion";
import { Users, Brain, Lightbulb, X } from "lucide-react";
import { Bar, Radar } from "react-chartjs-2";
import type { CompareManager } from "./types";
import { CATEGORY_CONFIG } from "./types";

const COMPARE_COLORS = ["var(--warning)", "var(--accent)", "var(--success)", "var(--danger)", "#ec4899"];

export function CompareResultsPanel({ data, onClose }: { data: CompareManager[]; onClose: () => void }) {
  const LAYER_LABELS: Record<string, string> = {
    script_adherence: "Скрипт",
    objection_handling: "Возражения",
    communication: "Коммуникация",
    anti_patterns: "Анти-паттерны",
    result: "Результат",
  };

  const SKILL_LABELS: Record<string, string> = {
    empathy: "Эмпатия",
    knowledge: "Знания",
    objection_handling: "Возражения",
    stress_resistance: "Стресс",
    closing: "Закрытие",
    qualification: "Квалификация",
  };

  const glassCard: React.CSSProperties = {
    background: "rgba(255,255,255,0.03)",
    border: "1px solid rgba(255,255,255,0.06)",
    borderRadius: 12,
    padding: "1rem",
  };

  // Radar chart for score layers
  const radarData = {
    labels: Object.values(LAYER_LABELS),
    datasets: data.map((m, i) => ({
      label: m.name,
      data: Object.keys(LAYER_LABELS).map((k) => m.score_layers[k] || 0),
      borderColor: COMPARE_COLORS[i],
      backgroundColor: COMPARE_COLORS[i] + "20",
      pointBackgroundColor: COMPARE_COLORS[i],
      borderWidth: 2,
    })),
  };

  // Radar for skills
  const skillKeys = Object.keys(SKILL_LABELS);
  const skillRadar = {
    labels: Object.values(SKILL_LABELS),
    datasets: data.map((m, i) => ({
      label: m.name,
      data: skillKeys.map((k) => m.skills[k] || 0),
      borderColor: COMPARE_COLORS[i],
      backgroundColor: COMPARE_COLORS[i] + "20",
      pointBackgroundColor: COMPARE_COLORS[i],
      borderWidth: 2,
    })),
  };

  const radarOpts: any = {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      r: {
        beginAtZero: true,
        ticks: { color: "var(--text-muted)", backdropColor: "transparent", font: { size: 10 } },
        grid: { color: "rgba(255,255,255,0.06)" },
        pointLabels: { color: "var(--text-muted)", font: { size: 11 } },
      },
    },
    plugins: { legend: { labels: { color: "var(--text-muted)", font: { size: 11 } } } },
  };

  // Bar chart for avg scores
  const barData = {
    labels: data.map((m) => m.name),
    datasets: [
      {
        label: "Средний балл",
        data: data.map((m) => m.avg_score),
        backgroundColor: data.map((_, i) => COMPARE_COLORS[i] + "80"),
        borderColor: data.map((_, i) => COMPARE_COLORS[i]),
        borderWidth: 1,
        borderRadius: 6,
      },
      {
        label: "Лучший балл",
        data: data.map((m) => m.best_score),
        backgroundColor: data.map((_, i) => COMPARE_COLORS[i] + "30"),
        borderColor: data.map((_, i) => COMPARE_COLORS[i]),
        borderWidth: 1,
        borderRadius: 6,
        borderDash: [3, 3],
      },
    ],
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      style={{ marginTop: "1.5rem" }}
    >
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "1rem" }}>
        <Users size={22} style={{ color: "var(--accent)" }} />
        <h2 style={{ fontSize: "1.3rem", fontWeight: 700, color: "#fff", margin: 0 }}>
          Сравнение менеджеров
        </h2>
        <div style={{ flex: 1 }} />
        <button
          onClick={onClose}
          style={{
            padding: "0.4rem",
            background: "rgba(255,255,255,0.04)",
            border: "1px solid rgba(255,255,255,0.08)",
            borderRadius: 8,
            color: "var(--text-muted)",
            cursor: "pointer",
          }}
        >
          <X size={18} />
        </button>
      </div>

      {/* Summary cards */}
      <div style={{ display: "grid", gridTemplateColumns: `repeat(${data.length}, 1fr)`, gap: "0.75rem", marginBottom: "1rem" }}>
        {data.map((m, i) => (
          <div key={m.manager_id + i} style={{
            ...glassCard,
            borderTop: `3px solid ${COMPARE_COLORS[i]}`,
          }}>
            <div style={{ fontWeight: 700, color: "#fff", fontSize: "1rem", marginBottom: "0.5rem" }}>{m.name}</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.3rem", fontSize: "0.8rem" }}>
              <div><span style={{ color: "var(--text-muted)" }}>Сессий: </span><span style={{ color: "var(--warning)", fontWeight: 600 }}>{m.sessions_total}</span></div>
              <div><span style={{ color: "var(--text-muted)" }}>Ср. балл: </span><span style={{ color: "var(--success)", fontWeight: 600 }}>{m.avg_score}</span></div>
              <div><span style={{ color: "var(--text-muted)" }}>Лучший: </span><span style={{ color: "#a5b4fc", fontWeight: 600 }}>{m.best_score}</span></div>
              <div><span style={{ color: "var(--text-muted)" }}>Худший: </span><span style={{ color: "var(--danger)", fontWeight: 600 }}>{m.worst_score}</span></div>
              <div><span style={{ color: "var(--text-muted)" }}>Паттернов: </span><span style={{ color: "var(--warning)", fontWeight: 600 }}>{m.patterns_total}</span></div>
              <div><span style={{ color: "var(--text-muted)" }}>Техник: </span><span style={{ color: "var(--success)", fontWeight: 600 }}>{m.techniques_total}</span></div>
            </div>
          </div>
        ))}
      </div>

      {/* Charts row */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0.75rem", marginBottom: "1rem" }}>
        {/* Score comparison bar */}
        <div style={glassCard}>
          <div style={{ color: "var(--text-muted)", fontSize: "0.8rem", fontWeight: 600, marginBottom: "0.5rem" }}>Баллы</div>
          <div style={{ height: 220 }}>
            <Bar data={barData} options={{
              responsive: true,
              maintainAspectRatio: false,
              scales: {
                x: { ticks: { color: "var(--text-muted)", font: { size: 10 } }, grid: { display: false } },
                y: { beginAtZero: true, ticks: { color: "var(--text-muted)" }, grid: { color: "rgba(255,255,255,0.04)" } },
              },
              plugins: { legend: { labels: { color: "var(--text-muted)", font: { size: 10 } } } },
            }} />
          </div>
        </div>

        {/* Score layers radar */}
        <div style={glassCard}>
          <div style={{ color: "var(--text-muted)", fontSize: "0.8rem", fontWeight: 600, marginBottom: "0.5rem" }}>Слои оценки</div>
          <div style={{ height: 220 }}>
            <Radar data={radarData} options={radarOpts} />
          </div>
        </div>

        {/* Skills radar */}
        <div style={glassCard}>
          <div style={{ color: "var(--text-muted)", fontSize: "0.8rem", fontWeight: 600, marginBottom: "0.5rem" }}>Навыки</div>
          <div style={{ height: 220 }}>
            <Radar data={skillRadar} options={radarOpts} />
          </div>
        </div>
      </div>

      {/* Patterns & Techniques tables */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
        {/* Patterns */}
        <div style={glassCard}>
          <div style={{ color: "var(--text-muted)", fontSize: "0.8rem", fontWeight: 600, marginBottom: "0.75rem" }}>
            <Brain size={14} style={{ display: "inline", verticalAlign: "middle", marginRight: 4 }} />
            Паттерны по категориям
          </div>
          <table style={{ width: "100%", fontSize: "0.8rem", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid rgba(255,255,255,0.08)" }}>
                <th style={{ textAlign: "left", padding: "4px 8px", color: "var(--text-muted)", fontWeight: 500 }}>Категория</th>
                {data.map((m, i) => (
                  <th key={m.manager_id + i} style={{ textAlign: "center", padding: "4px 8px", color: COMPARE_COLORS[i], fontWeight: 600 }}>
                    {m.name.split(" ")[0]}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {["weakness", "strength", "quirk", "misconception"].map((cat) => (
                <tr key={cat} style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                  <td style={{ padding: "4px 8px", color: CATEGORY_CONFIG[cat]?.color || "var(--text-muted)" }}>
                    {CATEGORY_CONFIG[cat]?.label || cat}
                  </td>
                  {data.map((m, i) => (
                    <td key={m.manager_id + i} style={{ textAlign: "center", padding: "4px 8px", color: "#e0e0e0" }}>
                      {m.patterns_by_category[cat] || 0}
                    </td>
                  ))}
                </tr>
              ))}
              <tr style={{ fontWeight: 600 }}>
                <td style={{ padding: "4px 8px", color: "var(--text-muted)" }}>Всего</td>
                {data.map((m, i) => (
                  <td key={m.manager_id + i} style={{ textAlign: "center", padding: "4px 8px", color: COMPARE_COLORS[i] }}>
                    {m.patterns_total}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>

        {/* Techniques */}
        <div style={glassCard}>
          <div style={{ color: "var(--text-muted)", fontSize: "0.8rem", fontWeight: 600, marginBottom: "0.75rem" }}>
            <Lightbulb size={14} style={{ display: "inline", verticalAlign: "middle", marginRight: 4 }} />
            Лучшие техники
          </div>
          {data.map((m, i) => (
            <div key={m.manager_id + i} style={{ marginBottom: "0.5rem" }}>
              <div style={{ fontSize: "0.75rem", fontWeight: 600, color: COMPARE_COLORS[i], marginBottom: "0.25rem" }}>{m.name}</div>
              {m.techniques.length === 0 ? (
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", fontStyle: "italic" }}>Нет техник</div>
              ) : (
                m.techniques.slice(0, 3).map((t) => (
                  <div key={t.code} style={{ display: "flex", justifyContent: "space-between", fontSize: "0.75rem", color: "var(--text-muted)", padding: "2px 0" }}>
                    <span>{t.name}</span>
                    <span style={{ color: t.success_rate >= 0.7 ? "var(--success)" : t.success_rate >= 0.4 ? "var(--warning)" : "var(--danger)" }}>
                      {Math.round(t.success_rate * 100)}%
                    </span>
                  </div>
                ))
              )}
            </div>
          ))}
        </div>
      </div>
    </motion.div>
  );
}
