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
import { Loader2 } from "lucide-react";
import {
  Pulse,
  BookOpen,
  ChartPie,
  TrendUp,
  UsersThree,
} from "@phosphor-icons/react";
import type { WikiChartData } from "./types";
import { cssVar, getChartTheme } from "@/lib/chartTheme";

ChartJS.register(CategoryScale, LinearScale, BarElement, PointElement, LineElement, ArcElement, RadialLinearScale, Tooltip, Legend, Filler);

/* ─── Charts Section ─── */

function getChartOptions() {
  const theme = getChartTheme();
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: theme.defaults.plugins.tooltip,
    },
    scales: {
      x: {
        grid: { color: theme.defaults.scales.x.grid.color },
        ticks: { color: theme.colors.text, font: { size: 14 } },
        border: { color: "transparent" },
      },
      y: {
        grid: { color: theme.colors.grid },
        ticks: { color: theme.colors.text, font: { size: 14 } },
        border: { color: "transparent" },
        beginAtZero: true,
      },
    },
  };
}

function getCategoryColors(): Record<string, string> {
  return {
    weakness: cssVar("--danger", "#E5484D"),
    strength: cssVar("--success", "#3DDC84"),
    quirk: cssVar("--warning", "#E8A630"),
    misconception: cssVar("--accent", "#7C6AE8"),
    unknown: cssVar("--text-muted", "#807DA0"),
  };
}

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
      <div style={{ textAlign: "center", padding: "2rem", color: "var(--text-muted)" }}>
        <Loader2 size={24} style={{ animation: "spin 1s linear infinite", color: "var(--warning)", margin: "0 auto" }} />
        <p style={{ marginTop: "0.5rem", fontSize: "0.875rem" }}>Загрузка графиков...</p>
      </div>
    );
  }

  const categoryColors = getCategoryColors();
  const theme = getChartTheme();
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
        backgroundColor: "rgba(124, 106, 232, 0.7)",
        borderColor: "rgba(124, 106, 232, 1)",
        borderWidth: 1.5,
        borderRadius: 6,
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
        borderColor: theme.colors.accent,
        backgroundColor: "rgba(124, 106, 232, 0.22)",
        borderWidth: 3,
        fill: true,
        tension: 0.35,
        pointRadius: 5,
        pointHoverRadius: 7,
        pointBackgroundColor: theme.colors.accent,
      },
    ],
  };

  // Pattern distribution doughnut
  const patternDoughnutData = {
    labels: patternDist.map((p) => CATEGORY_LABELS_RU[p.category] || p.category),
    datasets: [
      {
        data: patternDist.map((p) => p.count),
        backgroundColor: patternDist.map((p) => categoryColors[p.category] || categoryColors.unknown),
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
        backgroundColor: "rgba(61, 220, 132, 0.7)",
        borderColor: "rgba(61, 220, 132, 1)",
        borderWidth: 1.5,
        borderRadius: 6,
      },
      {
        label: "Страниц создано",
        data: wikiActivity.map((d) => d.pages_created),
        backgroundColor: "rgba(232, 166, 48, 0.7)",
        borderColor: "rgba(232, 166, 48, 1)",
        borderWidth: 1.5,
        borderRadius: 6,
      },
    ],
  };

  const lineOptions = {
    ...getChartOptions(),
    plugins: {
      ...getChartOptions().plugins,
      legend: { display: false },
    },
  };

  const barOptions = {
    ...getChartOptions(),
    plugins: {
      ...getChartOptions().plugins,
      legend: { display: true, position: "top" as const, labels: { color: theme.colors.text, boxWidth: 14, font: { size: 14 }, padding: 12 } },
    },
  };

  const doughnutOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: "right" as const,
        labels: { color: theme.colors.text, boxWidth: 14, font: { size: 14 }, padding: 12 },
      },
      tooltip: getChartOptions().plugins.tooltip,
    },
  };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
      {/* Sessions per day */}
      <div style={{
        padding: "1rem",
        background: "var(--bg-secondary)",
        border: "1px solid var(--border-color)",
        borderRadius: 12,
      }}>
        <h4 style={{ margin: "0 0 0.75rem", color: "var(--text-secondary)", fontSize: "1rem", fontWeight: 600 }}>
          <Pulse size={15} weight="duotone" style={{ marginRight: 6, verticalAlign: "text-bottom", color: "var(--accent)" }} />
          Сессии по дням
        </h4>
        <div style={{ height: 200 }}>
          {dailySessions.length > 0 ? (
            <Bar data={sessionsBarData} options={getChartOptions() as any} />
          ) : (
            <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", textAlign: "center", paddingTop: "4rem" }}>Нет данных</p>
          )}
        </div>
      </div>

      {/* Score trend */}
      <div style={{
        padding: "1rem",
        background: "var(--bg-secondary)",
        border: "1px solid var(--border-color)",
        borderRadius: 12,
      }}>
        <h4 style={{ margin: "0 0 0.75rem", color: "var(--text-secondary)", fontSize: "1rem", fontWeight: 600 }}>
          <TrendUp size={15} weight="duotone" style={{ marginRight: 6, verticalAlign: "text-bottom", color: "var(--warning)" }} />
          Тренд среднего балла
        </h4>
        <div style={{ height: 200 }}>
          {dailySessions.length > 0 ? (
            <Line data={scoreTrendData} options={lineOptions as any} />
          ) : (
            <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", textAlign: "center", paddingTop: "4rem" }}>Нет данных</p>
          )}
        </div>
      </div>

      {/* Pattern distribution */}
      <div style={{
        padding: "1rem",
        background: "var(--bg-secondary)",
        border: "1px solid var(--border-color)",
        borderRadius: 12,
      }}>
        <h4 style={{ margin: "0 0 0.75rem", color: "var(--text-secondary)", fontSize: "1rem", fontWeight: 600 }}>
          <ChartPie size={15} weight="duotone" style={{ marginRight: 6, verticalAlign: "text-bottom", color: "var(--danger)" }} />
          Распределение паттернов
        </h4>
        <div style={{ height: 200 }}>
          {patternDist.length > 0 ? (
            <Doughnut data={patternDoughnutData} options={doughnutOptions as any} />
          ) : (
            <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", textAlign: "center", paddingTop: "4rem" }}>Паттерны не обнаружены</p>
          )}
        </div>
      </div>

      {/* Wiki activity */}
      <div style={{
        padding: "1rem",
        background: "var(--bg-secondary)",
        border: "1px solid var(--border-color)",
        borderRadius: 12,
      }}>
        <h4 style={{ margin: "0 0 0.75rem", color: "var(--text-secondary)", fontSize: "1rem", fontWeight: 600 }}>
          <BookOpen size={15} weight="duotone" style={{ marginRight: 6, verticalAlign: "text-bottom", color: "var(--success)" }} />
          Активность Wiki
        </h4>
        <div style={{ height: 200 }}>
          {wikiActivity.length > 0 ? (
            <Bar data={wikiActivityData} options={barOptions as any} />
          ) : (
            <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", textAlign: "center", paddingTop: "4rem" }}>Нет данных</p>
          )}
        </div>
      </div>

      {/* Top managers table */}
      {data.top_managers.length > 0 && (
        <div style={{
          gridColumn: "1 / -1",
          padding: "1rem",
          background: "var(--bg-secondary)",
          border: "1px solid var(--border-color)",
          borderRadius: 12,
        }}>
          <h4 style={{ margin: "0 0 0.75rem", color: "var(--text-secondary)", fontSize: "1rem", fontWeight: 600 }}>
            <UsersThree size={15} weight="duotone" style={{ marginRight: 6, verticalAlign: "text-bottom", color: "var(--accent)" }} />
            Топ менеджеров по паттернам
          </h4>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.875rem" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border-color)" }}>
                  <th style={{ textAlign: "left", padding: "0.5rem", color: "var(--text-muted)", fontWeight: 500 }}>Менеджер</th>
                  <th style={{ textAlign: "center", padding: "0.5rem", color: "var(--text-muted)", fontWeight: 500 }}>Сессии</th>
                  <th style={{ textAlign: "center", padding: "0.5rem", color: "var(--text-muted)", fontWeight: 500 }}>Паттерны</th>
                  <th style={{ textAlign: "center", padding: "0.5rem", color: "var(--text-muted)", fontWeight: 500 }}>Страницы</th>
                </tr>
              </thead>
              <tbody>
                {data.top_managers.map((m, i) => (
                  <tr key={m.manager_id} style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                    <td style={{ padding: "0.5rem", color: "var(--text-secondary)" }}>
                      <span style={{ color: "var(--text-muted)", marginRight: 8 }}>#{i + 1}</span>
                      {m.name}
                    </td>
                    <td style={{ textAlign: "center", padding: "0.5rem", color: "var(--warning)" }}>{m.sessions}</td>
                    <td style={{ textAlign: "center", padding: "0.5rem", color: "var(--danger)" }}>{m.patterns}</td>
                    <td style={{ textAlign: "center", padding: "0.5rem", color: "var(--success)" }}>{m.pages}</td>
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
