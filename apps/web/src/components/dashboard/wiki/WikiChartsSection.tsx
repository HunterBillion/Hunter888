"use client";

import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  PointElement,
  LineElement,
  ArcElement,
  RadialLinearScale,
  Tooltip,
  Legend,
  Filler,
} from "chart.js";
import { Bar, Line, Doughnut } from "react-chartjs-2";
import {
  Activity,
  BookOpen,
  Loader2,
  PieChart,
  TrendingUp,
  Users,
} from "lucide-react";
import type { WikiChartData } from "./types";

ChartJS.register(CategoryScale, LinearScale, BarElement, PointElement, LineElement, ArcElement, RadialLinearScale, Tooltip, Legend, Filler);

/* ─── Charts Section ─── */

const CHART_COMMON_OPTIONS = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { display: false },
    tooltip: {
      backgroundColor: "rgba(17,24,39,0.95)",
      titleColor: "#f3f4f6",
      bodyColor: "#d1d5db",
      borderColor: "rgba(255,255,255,0.1)",
      borderWidth: 1,
      cornerRadius: 8,
      padding: 10,
    },
  },
  scales: {
    x: {
      grid: { color: "rgba(255,255,255,0.04)" },
      ticks: { color: "#6b7280", font: { size: 10 } },
    },
    y: {
      grid: { color: "rgba(255,255,255,0.04)" },
      ticks: { color: "#6b7280", font: { size: 10 } },
      beginAtZero: true,
    },
  },
};

const CATEGORY_COLORS: Record<string, string> = {
  weakness: "#ef4444",
  strength: "#22c55e",
  quirk: "#f59e0b",
  misconception: "#8b5cf6",
  unknown: "#6b7280",
};

const CATEGORY_LABELS_RU: Record<string, string> = {
  weakness: "Слабости",
  strength: "Сильные стороны",
  quirk: "Особенности",
  misconception: "Заблуждения",
  unknown: "Другое",
};

export function WikiChartsSection({ data }: { data: WikiChartData | null }) {
  if (!data) {
    return (
      <div style={{ textAlign: "center", padding: "2rem", color: "#6b7280" }}>
        <Loader2 size={24} style={{ animation: "spin 1s linear infinite", color: "#f59e0b", margin: "0 auto" }} />
        <p style={{ marginTop: "0.5rem", fontSize: "0.85rem" }}>Загрузка графиков...</p>
      </div>
    );
  }

  const dailySessions = data.daily_sessions;
  const patternDist = data.pattern_distribution;
  const wikiActivity = data.wiki_activity;

  // Sessions activity bar chart
  const sessionsBarData = {
    labels: dailySessions.map((d) => {
      const dt = new Date(d.date);
      return `${dt.getDate()}.${dt.getMonth() + 1}`;
    }),
    datasets: [
      {
        label: "Сессии",
        data: dailySessions.map((d) => d.sessions),
        backgroundColor: "rgba(99, 102, 241, 0.5)",
        borderColor: "rgba(99, 102, 241, 0.8)",
        borderWidth: 1,
        borderRadius: 4,
      },
    ],
  };

  // Score trend line chart
  const scoreTrendData = {
    labels: dailySessions.map((d) => {
      const dt = new Date(d.date);
      return `${dt.getDate()}.${dt.getMonth() + 1}`;
    }),
    datasets: [
      {
        label: "Средний балл",
        data: dailySessions.map((d) => d.avg_score),
        borderColor: "#f59e0b",
        backgroundColor: "rgba(245, 158, 11, 0.1)",
        borderWidth: 2,
        fill: true,
        tension: 0.4,
        pointRadius: 3,
        pointBackgroundColor: "#f59e0b",
      },
    ],
  };

  // Pattern distribution doughnut
  const patternDoughnutData = {
    labels: patternDist.map((p) => CATEGORY_LABELS_RU[p.category] || p.category),
    datasets: [
      {
        data: patternDist.map((p) => p.count),
        backgroundColor: patternDist.map((p) => CATEGORY_COLORS[p.category] || "#6b7280"),
        borderColor: "rgba(0,0,0,0.3)",
        borderWidth: 2,
      },
    ],
  };

  // Wiki activity (ingests + pages)
  const wikiActivityData = {
    labels: wikiActivity.map((d) => {
      const dt = new Date(d.date);
      return `${dt.getDate()}.${dt.getMonth() + 1}`;
    }),
    datasets: [
      {
        label: "Инжесты",
        data: wikiActivity.map((d) => d.ingests),
        backgroundColor: "rgba(34, 197, 94, 0.5)",
        borderColor: "rgba(34, 197, 94, 0.8)",
        borderWidth: 1,
        borderRadius: 4,
      },
      {
        label: "Страниц создано",
        data: wikiActivity.map((d) => d.pages_created),
        backgroundColor: "rgba(245, 158, 11, 0.5)",
        borderColor: "rgba(245, 158, 11, 0.8)",
        borderWidth: 1,
        borderRadius: 4,
      },
    ],
  };

  const lineOptions = {
    ...CHART_COMMON_OPTIONS,
    plugins: {
      ...CHART_COMMON_OPTIONS.plugins,
      legend: { display: false },
    },
  };

  const barOptions = {
    ...CHART_COMMON_OPTIONS,
    plugins: {
      ...CHART_COMMON_OPTIONS.plugins,
      legend: { display: true, position: "top" as const, labels: { color: "#9ca3af", boxWidth: 12, font: { size: 11 } } },
    },
  };

  const doughnutOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: "right" as const,
        labels: { color: "#d1d5db", boxWidth: 12, font: { size: 11 }, padding: 8 },
      },
      tooltip: CHART_COMMON_OPTIONS.plugins.tooltip,
    },
  };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
      {/* Sessions per day */}
      <div style={{
        padding: "1rem",
        background: "rgba(255,255,255,0.03)",
        border: "1px solid rgba(255,255,255,0.06)",
        borderRadius: 12,
      }}>
        <h4 style={{ margin: "0 0 0.75rem", color: "#e0e0e0", fontSize: "0.9rem", fontWeight: 600 }}>
          <Activity size={15} style={{ marginRight: 6, verticalAlign: "text-bottom", color: "#6366f1" }} />
          Сессии по дням
        </h4>
        <div style={{ height: 200 }}>
          {dailySessions.length > 0 ? (
            <Bar data={sessionsBarData} options={CHART_COMMON_OPTIONS as any} />
          ) : (
            <p style={{ color: "#6b7280", fontSize: "0.8rem", textAlign: "center", paddingTop: "4rem" }}>Нет данных</p>
          )}
        </div>
      </div>

      {/* Score trend */}
      <div style={{
        padding: "1rem",
        background: "rgba(255,255,255,0.03)",
        border: "1px solid rgba(255,255,255,0.06)",
        borderRadius: 12,
      }}>
        <h4 style={{ margin: "0 0 0.75rem", color: "#e0e0e0", fontSize: "0.9rem", fontWeight: 600 }}>
          <TrendingUp size={15} style={{ marginRight: 6, verticalAlign: "text-bottom", color: "#f59e0b" }} />
          Тренд среднего балла
        </h4>
        <div style={{ height: 200 }}>
          {dailySessions.length > 0 ? (
            <Line data={scoreTrendData} options={lineOptions as any} />
          ) : (
            <p style={{ color: "#6b7280", fontSize: "0.8rem", textAlign: "center", paddingTop: "4rem" }}>Нет данных</p>
          )}
        </div>
      </div>

      {/* Pattern distribution */}
      <div style={{
        padding: "1rem",
        background: "rgba(255,255,255,0.03)",
        border: "1px solid rgba(255,255,255,0.06)",
        borderRadius: 12,
      }}>
        <h4 style={{ margin: "0 0 0.75rem", color: "#e0e0e0", fontSize: "0.9rem", fontWeight: 600 }}>
          <PieChart size={15} style={{ marginRight: 6, verticalAlign: "text-bottom", color: "#ef4444" }} />
          Распределение паттернов
        </h4>
        <div style={{ height: 200 }}>
          {patternDist.length > 0 ? (
            <Doughnut data={patternDoughnutData} options={doughnutOptions as any} />
          ) : (
            <p style={{ color: "#6b7280", fontSize: "0.8rem", textAlign: "center", paddingTop: "4rem" }}>Паттерны не обнаружены</p>
          )}
        </div>
      </div>

      {/* Wiki activity */}
      <div style={{
        padding: "1rem",
        background: "rgba(255,255,255,0.03)",
        border: "1px solid rgba(255,255,255,0.06)",
        borderRadius: 12,
      }}>
        <h4 style={{ margin: "0 0 0.75rem", color: "#e0e0e0", fontSize: "0.9rem", fontWeight: 600 }}>
          <BookOpen size={15} style={{ marginRight: 6, verticalAlign: "text-bottom", color: "#22c55e" }} />
          Активность Wiki
        </h4>
        <div style={{ height: 200 }}>
          {wikiActivity.length > 0 ? (
            <Bar data={wikiActivityData} options={barOptions as any} />
          ) : (
            <p style={{ color: "#6b7280", fontSize: "0.8rem", textAlign: "center", paddingTop: "4rem" }}>Нет данных</p>
          )}
        </div>
      </div>

      {/* Top managers table */}
      {data.top_managers.length > 0 && (
        <div style={{
          gridColumn: "1 / -1",
          padding: "1rem",
          background: "rgba(255,255,255,0.03)",
          border: "1px solid rgba(255,255,255,0.06)",
          borderRadius: 12,
        }}>
          <h4 style={{ margin: "0 0 0.75rem", color: "#e0e0e0", fontSize: "0.9rem", fontWeight: 600 }}>
            <Users size={15} style={{ marginRight: 6, verticalAlign: "text-bottom", color: "#6366f1" }} />
            Топ менеджеров по паттернам
          </h4>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid rgba(255,255,255,0.08)" }}>
                  <th style={{ textAlign: "left", padding: "0.5rem", color: "#9ca3af", fontWeight: 500 }}>Менеджер</th>
                  <th style={{ textAlign: "center", padding: "0.5rem", color: "#9ca3af", fontWeight: 500 }}>Сессии</th>
                  <th style={{ textAlign: "center", padding: "0.5rem", color: "#9ca3af", fontWeight: 500 }}>Паттерны</th>
                  <th style={{ textAlign: "center", padding: "0.5rem", color: "#9ca3af", fontWeight: 500 }}>Страницы</th>
                </tr>
              </thead>
              <tbody>
                {data.top_managers.map((m, i) => (
                  <tr key={m.manager_id} style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                    <td style={{ padding: "0.5rem", color: "#e0e0e0" }}>
                      <span style={{ color: "#6b7280", marginRight: 8 }}>#{i + 1}</span>
                      {m.name}
                    </td>
                    <td style={{ textAlign: "center", padding: "0.5rem", color: "#f59e0b" }}>{m.sessions}</td>
                    <td style={{ textAlign: "center", padding: "0.5rem", color: "#ef4444" }}>{m.patterns}</td>
                    <td style={{ textAlign: "center", padding: "0.5rem", color: "#22c55e" }}>{m.pages}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
