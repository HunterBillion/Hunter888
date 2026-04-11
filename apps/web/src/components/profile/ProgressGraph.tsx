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
} from "chart.js";
import { Chart } from "react-chartjs-2";
import { AnimatedChart } from "@/components/ui/AnimatedChart";
import { getChartTheme } from "@/lib/chartTheme";
import type { ProgressPoint } from "@/types";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, BarElement, Tooltip, Filler);

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
        {
          type: "line" as const,
          label: "Средний балл",
          data: data.map((p) => p.avg_total),
          borderColor: theme.colors.line,
          backgroundColor: theme.colors.fill,
          fill: true,
          tension: 0.4,
          borderWidth: 3,
          pointRadius: 5,
          pointHoverRadius: 7,
          pointBackgroundColor: theme.colors.line,
          pointBorderColor: "transparent",
          yAxisID: "y",
          order: 1,
        },
        {
          type: "bar" as const,
          label: "Сессий",
          data: data.map((p) => p.sessions_count),
          backgroundColor: theme.colors.bar2,
          borderRadius: 6,
          barThickness: 18,
          yAxisID: "y1",
          order: 2,
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
        <span className="font-display text-sm font-bold tracking-widest uppercase" style={{ color: "var(--text-secondary)" }}>
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
            aspectRatio: 2.2,
            interaction: { mode: "index", intersect: false },
            plugins: {
              tooltip: theme.defaults.plugins.tooltip,
              legend: {
                display: true,
                labels: theme.defaults.plugins.legend.labels,
              },
            },
            scales: {
              x: {
                ticks: { color: theme.colors.text, font: { size: 14 } },
                grid: { color: theme.colors.grid },
                border: { color: "transparent" },
              },
              y: {
                position: "left",
                min: 0,
                max: 100,
                ticks: { color: theme.colors.text, font: { size: 14 } },
                grid: { color: theme.colors.grid },
                border: { color: "transparent" },
              },
              y1: {
                position: "right",
                min: 0,
                ticks: { color: theme.colors.text, font: { size: 14 } },
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
