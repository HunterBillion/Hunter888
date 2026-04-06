"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { TrendingUp, Loader2 } from "lucide-react";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Filler,
} from "chart.js";
import { Line } from "react-chartjs-2";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Filler);

interface WeekData {
  week: string;
  sessions_count: number;
  avg_score: number;
  active_managers: number;
}

type Period = "week" | "month" | "all";

export function TeamTrendChart() {
  const [data, setData] = useState<WeekData[]>([]);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState<Period>("month");

  useEffect(() => {
    setLoading(true);
    api.get(`/dashboard/rop/trends?period=${period}`)
      .then((res: { weeks: WeekData[] }) => setData(res.weeks || []))
      .catch((err) => logger.error("[TeamTrendChart] Failed to load trends:", err))
      .finally(() => setLoading(false));
  }, [period]);

  const chartData = {
    labels: data.map((d) => {
      const date = new Date(d.week);
      return `${date.getDate()}.${date.getMonth() + 1}`;
    }),
    datasets: [
      {
        label: "Средний балл",
        data: data.map((d) => d.avg_score),
        borderColor: "#6366F1",
        backgroundColor: "rgba(139, 92, 246, 0.1)",
        fill: true,
        tension: 0.4,
        pointRadius: 3,
        pointBackgroundColor: "#6366F1",
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      x: {
        grid: { color: "rgba(255,255,255,0.05)" },
        ticks: { color: "rgba(255,255,255,0.4)", font: { size: 10 } },
      },
      y: {
        min: 0,
        max: 100,
        grid: { color: "rgba(255,255,255,0.05)" },
        ticks: { color: "rgba(255,255,255,0.4)", font: { size: 10 } },
      },
    },
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.1 }}
      className="glass-panel rounded-xl p-5"
    >
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <TrendingUp size={16} style={{ color: "var(--accent)" }} />
          <span className="font-mono text-xs uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
            Тренд команды
          </span>
        </div>
        <div className="flex gap-1">
          {(["week", "month", "all"] as Period[]).map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className="px-2 py-0.5 rounded text-xs font-mono uppercase transition-colors"
              style={{
                background: period === p ? "var(--accent)" : "rgba(255,255,255,0.05)",
                color: period === p ? "#fff" : "var(--text-muted)",
              }}
            >
              {p === "week" ? "4 нед" : p === "month" ? "12 нед" : "Всё"}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-40">
          <Loader2 size={20} className="animate-spin" style={{ color: "var(--accent)" }} />
        </div>
      ) : data.length > 0 ? (
        <div style={{ height: 180 }}>
          <Line data={chartData} options={options} />
        </div>
      ) : (
        <div className="h-40 flex items-center justify-center text-xs" style={{ color: "var(--text-muted)" }}>
          Нет данных за период
        </div>
      )}
    </motion.div>
  );
}
