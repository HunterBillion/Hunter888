"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { BarChart3, Loader2 } from "lucide-react";
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

  const chartData = {
    labels: data.map((d) => {
      const date = new Date(d.date);
      return `${date.getDate()}.${date.getMonth() + 1}`;
    }),
    datasets: [
      {
        label: "Сессии",
        data: data.map((d) => d.sessions),
        backgroundColor: "rgba(139, 92, 246, 0.5)",
        borderRadius: 4,
        barThickness: 12,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      x: {
        grid: { display: false },
        ticks: { color: "rgba(255,255,255,0.4)", font: { size: 9 } },
      },
      y: {
        beginAtZero: true,
        grid: { color: "rgba(255,255,255,0.05)" },
        ticks: { color: "rgba(255,255,255,0.4)", font: { size: 10 }, stepSize: 1 },
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
          <BarChart3 size={16} style={{ color: "var(--accent)" }} />
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
        <div style={{ height: 140 }}>
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
