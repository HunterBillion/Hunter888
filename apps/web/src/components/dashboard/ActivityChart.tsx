"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Loader2 } from "lucide-react";
import { ChartBar } from "@phosphor-icons/react";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Tooltip,
} from "chart.js";
import { Bar } from "react-chartjs-2";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";
import { getChartTheme } from "@/lib/chartTheme";

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip);

interface DayData {
  date: string;
  sessions: number;
  managers_active: number;
}

export function ActivityChart() {
  const [data, setData] = useState<DayData[]>([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);

  useEffect(() => {
    api.get("/dashboard/rop/activity?days=14")
      .then((res: { days: DayData[]; total_sessions: number }) => {
        setData(res.days || []);
        setTotal(res.total_sessions || 0);
      })
      .catch((err) => logger.error("[ActivityChart] Failed to load activity:", err))
      .finally(() => setLoading(false));
  }, []);

  const theme = getChartTheme();

  const MONTHS_SHORT = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];

  const chartData = {
    labels: data.map((d) => {
      const date = new Date(d.date);
      return `${date.getDate()} ${MONTHS_SHORT[date.getMonth()]}`;
    }),
    datasets: [
      {
        label: "Сессии",
        data: data.map((d) => d.sessions),
        backgroundColor: theme.colors.bar1,
        borderRadius: 6,
        barThickness: 18,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false }, tooltip: theme.defaults.plugins.tooltip },
    scales: {
      x: {
        grid: { display: false },
        ticks: { color: theme.colors.text, font: { size: 14 } },
        border: { color: "transparent" },
      },
      y: {
        beginAtZero: true,
        grid: { color: theme.defaults.scales.y.grid.color },
        ticks: { color: theme.colors.text, font: { size: 14 }, stepSize: 1 },
        border: { color: "transparent" },
      },
    },
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.15 }}
      className="glass-panel rounded-xl p-5"
    >
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <ChartBar weight="duotone" size={18} style={{ color: "var(--accent)" }} />
          <span className="font-mono text-xs uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
            Активность (14 дней)
          </span>
        </div>
        <span className="font-mono text-xs" style={{ color: "var(--accent)" }}>
          {total} сессий
        </span>
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-32">
          <Loader2 size={20} className="animate-spin" style={{ color: "var(--accent)" }} />
        </div>
      ) : data.length > 0 ? (
        <div style={{ height: 180 }}>
          <Bar data={chartData} options={options} />
        </div>
      ) : (
        <div className="h-32 flex items-center justify-center text-xs" style={{ color: "var(--text-muted)" }}>
          Нет данных
        </div>
      )}
    </motion.div>
  );
}
