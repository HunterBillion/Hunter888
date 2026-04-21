"use client";

import { useMemo } from "react";
import { motion } from "framer-motion";
import { TrendUp, ChartBar } from "@phosphor-icons/react";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Tooltip,
  Filler,
  Legend,
} from "chart.js";
import { Chart } from "react-chartjs-2";
import { AnimatedChart } from "@/components/ui/AnimatedChart";
import { getChartTheme } from "@/lib/chartTheme";
import type { ProgressPoint } from "@/types";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, BarElement, Tooltip, Filler, Legend);

interface ProgressGraphProps {
  data: ProgressPoint[];
}

export function ProgressGraph({ data }: ProgressGraphProps) {
  const theme = getChartTheme();

  const chartData = useMemo(() => {
    if (data.length === 0) return null;

    const labels = data.map((p) => {
      const d = new Date(p.period_start);
      return `${d.getDate().toString().padStart(2, "0")}.${(d.getMonth() + 1).toString().padStart(2, "0")}`;
    });

    return {
      labels,
      datasets: [
        // ── Bar: sessions count (background layer) ──
        {
          type: "bar" as const,
          label: "Кол-во сессий",
          data: data.map((p) => p.sessions_count),
          backgroundColor: "rgba(139, 92, 246, 0.15)",
          borderColor: "rgba(139, 92, 246, 0.3)",
          borderWidth: 1,
          borderRadius: 4,
          barThickness: 20,
          yAxisID: "y1",
          order: 6,
        },
        // ── Line: avg total (main, solid, thick) ──
        {
          type: "line" as const,
          label: "Общий балл",
          data: data.map((p) => p.avg_total),
          borderColor: "#8b5cf6",
          backgroundColor: "rgba(139, 92, 246, 0.08)",
          fill: true,
          tension: 0.4,
          borderWidth: 3,
          pointRadius: 5,
          pointHoverRadius: 8,
          pointBackgroundColor: "#8b5cf6",
          pointBorderColor: "rgba(0,0,0,0.3)",
          pointBorderWidth: 1,
          yAxisID: "y",
          order: 1,
        },
        // ── Line: best score (dashed, green) ──
        {
          type: "line" as const,
          label: "Лучший результат",
          data: data.map((p) => p.best_score),
          borderColor: "#22c55e",
          backgroundColor: "transparent",
          borderDash: [8, 4],
          tension: 0.3,
          borderWidth: 2,
          pointRadius: 4,
          pointHoverRadius: 6,
          pointBackgroundColor: "#22c55e",
          pointBorderColor: "transparent",
          pointStyle: "triangle",
          yAxisID: "y",
          order: 2,
        },
        // ── Line: objection handling (dotted, orange) ──
        {
          type: "line" as const,
          label: "Возражения",
          data: data.map((p) => p.avg_objection),
          borderColor: "#f59e0b",
          backgroundColor: "transparent",
          borderDash: [3, 3],
          tension: 0.3,
          borderWidth: 2,
          pointRadius: 3,
          pointHoverRadius: 5,
          pointBackgroundColor: "#f59e0b",
          pointBorderColor: "transparent",
          pointStyle: "rect",
          yAxisID: "y",
          order: 3,
        },
        // ── Line: communication (thin, cyan) ──
        {
          type: "line" as const,
          label: "Коммуникация",
          data: data.map((p) => p.avg_communication),
          borderColor: "#06b6d4",
          backgroundColor: "transparent",
          tension: 0.3,
          borderWidth: 1.5,
          pointRadius: 3,
          pointHoverRadius: 5,
          pointBackgroundColor: "#06b6d4",
          pointBorderColor: "transparent",
          pointStyle: "circle",
          yAxisID: "y",
          order: 4,
        },
        // ── Line: script adherence (thin dashed, pink) ──
        {
          type: "line" as const,
          label: "Скрипт",
          data: data.map((p) => p.avg_script),
          borderColor: "#ec4899",
          backgroundColor: "transparent",
          borderDash: [6, 3],
          tension: 0.3,
          borderWidth: 1.5,
          pointRadius: 3,
          pointHoverRadius: 5,
          pointBackgroundColor: "#ec4899",
          pointBorderColor: "transparent",
          pointStyle: "rectRounded",
          yAxisID: "y",
          order: 5,
        },
      ],
    };
  }, [data, theme]);

  if (!chartData) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass-panel p-8 text-center"
      >
        <ChartBar weight="duotone" size={32} className="mx-auto animate-float-subtle" style={{ color: "var(--text-muted)", opacity: 0.4 }} />
        <p className="mt-3 text-sm" style={{ color: "var(--text-muted)" }}>
          Пройдите несколько тренировок для отображения прогресса
        </p>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-panel p-6"
    >
      <div className="flex items-center gap-2 mb-4">
        <TrendUp weight="duotone" size={18} style={{ color: "var(--accent)" }} />
        <span className="font-display text-base font-bold tracking-widest uppercase" style={{ color: "var(--text-secondary)" }}>
          Прогресс
        </span>
      </div>

      <AnimatedChart>
        {(isVisible) => isVisible ? <Chart
          type="bar"
          data={chartData}
          options={{
            responsive: true,
            maintainAspectRatio: true,
            aspectRatio: 1.5,
            interaction: { mode: "index", intersect: false },
            plugins: {
              tooltip: {
                ...theme.defaults.plugins.tooltip,
                callbacks: {
                  label: (ctx) => {
                    const v = ctx.parsed.y;
                    if (v == null || v === 0) return "";
                    if (ctx.dataset.yAxisID === "y1") return `${ctx.dataset.label}: ${v}`;
                    return `${ctx.dataset.label}: ${v.toFixed(1)}`;
                  },
                },
              },
              legend: {
                display: true,
                position: "bottom",
                labels: {
                  color: theme.colors.text,
                  font: { size: 11, family: "var(--font-mono, monospace)" },
                  padding: 14,
                  usePointStyle: true,
                  pointStyleWidth: 14,
                  filter: (item, chart) => {
                    // Hide datasets that are all zeros
                    const ds = chart.datasets[item.datasetIndex!];
                    return ds.data.some((v) => typeof v === "number" && v > 0);
                  },
                },
              },
            },
            scales: {
              x: {
                ticks: { color: theme.colors.text, font: { size: 13 } },
                grid: { color: theme.colors.grid },
                border: { color: "transparent" },
              },
              y: {
                position: "left",
                title: { display: true, text: "Баллы", color: theme.colors.text, font: { size: 13 } },
                min: 0,
                max: 100,
                ticks: { color: theme.colors.text, font: { size: 13 }, stepSize: 20 },
                grid: { color: theme.colors.grid },
                border: { color: "transparent" },
              },
              y1: {
                position: "right",
                title: { display: true, text: "Сессий", color: theme.colors.text, font: { size: 13 } },
                min: 0,
                ticks: { color: theme.colors.text, font: { size: 13 }, stepSize: 1 },
                grid: { display: false },
                border: { color: "transparent" },
              },
            },
          }}
        /> : null}
      </AnimatedChart>
    </motion.div>
  );
}
