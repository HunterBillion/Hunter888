"use client";

import { useEffect, useState } from "react";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
  type ChartOptions,
} from "chart.js";
import { Line } from "react-chartjs-2";
import { type EmotionState, EMOTION_MAP } from "@/types";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Filler, Tooltip);

interface EmotionEntry {
  state: string;
  timestamp: number | string;
  is_fake?: boolean;
  rollback?: boolean;
  triggers?: string[];
  energy_before?: number | null;
  energy_after?: number | null;
  previous_state?: string | null;
  message_index?: number | null;
}

interface JourneySummary {
  total_transitions?: number;
  rollback_count?: number;
  peak_state?: string;
  fake_count?: number;
  turning_points?: {
    message_index?: number | null;
    from_state: string;
    to_state: string;
    direction: string;
    triggers?: string[];
  }[];
}

function useIsDark() {
  const [isDark, setIsDark] = useState(true);
  useEffect(() => {
    const check = () => setIsDark(document.documentElement.classList.contains("dark"));
    check();
    const obs = new MutationObserver(check);
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);
  return isDark;
}

const TICK_LABELS: Record<number, string> = {
  0: "Враждебный",
  5: "Холодный",
  20: "Настороже",
  25: "Проверяет",
  40: "Любопытен",
  45: "Перезвонит",
  60: "Обдумывает",
  75: "Торгуется",
  95: "Сделка",
};

const TRIGGER_LABELS: Record<string, string> = {
  empathy: "Эмпатия",
  facts: "Факты",
  pressure: "Давление",
  bad_response: "Плохой ответ",
  acknowledge: "Признание",
  hook: "Зацепка",
  challenge: "Вызов",
  insult: "Оскорбление",
  calm_response: "Спокойный ответ",
  boundary: "Граница",
  resolve_fear: "Снятие страха",
  expert_answer: "Экспертный ответ",
  wrong_answer: "Неверный ответ",
  flexible_offer: "Гибкое предложение",
  counter_aggression: "Ответная агрессия",
  name_use: "Имя клиента",
  motivator: "Мотиватор",
  speed: "Скорость",
  personal: "Личное",
  silence: "Молчание",
};

interface Props {
  timeline: EmotionEntry[];
  journeySummary?: JourneySummary;
  /** Called when user clicks a turning point with a message_index — opens Replay Mode */
  onReplayMessage?: (messageIndex: number) => void;
}

export default function EmotionTimeline({ timeline, journeySummary, onReplayMessage }: Props) {
  const isDark = useIsDark();

  if (timeline.length === 0) return null;

  const gridColor = isDark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.06)";
  const tickColor = isDark ? "rgba(255,255,255,0.5)" : "rgba(0,0,0,0.5)";
  const tooltipBg = isDark ? "rgba(5,5,5,0.9)" : "rgba(255,255,255,0.95)";
  const tooltipText = isDark ? "#fff" : "#1a1a1a";

  const labels = timeline.map((e, i) => {
    if (i === 0) return "Начало";
    if (i === timeline.length - 1) return "Конец";
    // Handle both number timestamps and ISO strings
    const ts = typeof e.timestamp === "number" ? e.timestamp : 0;
    const m = Math.floor(ts / 60);
    const s = Math.floor(ts % 60);
    return `${m}:${s.toString().padStart(2, "0")}`;
  });

  const dataValues = timeline.map((e) => EMOTION_MAP[e.state as EmotionState]?.value ?? 30);
  const pointColors = timeline.map((e) => {
    if (e.is_fake) return "#FF2A6D"; // neon red for fake
    if (e.rollback) return "var(--warning)"; // amber for rollback
    return EMOTION_MAP[e.state as EmotionState]?.color ?? "var(--accent)";
  });

  // Point styling: larger for fakes/rollbacks, dashed border for fakes
  const pointRadii = timeline.map((e) => (e.is_fake || e.rollback ? 7 : 5));
  const pointBorderWidths = timeline.map((e) => (e.is_fake ? 3 : 2));
  const pointBorderColors = timeline.map((e) => {
    if (e.is_fake) return "#FF2A6D";
    if (e.rollback) return "var(--warning)";
    return isDark ? "#fff" : "#1a1a1a";
  });
  const pointStyles = timeline.map((e) => {
    if (e.is_fake) return "rectRot" as const; // diamond for fake
    if (e.rollback) return "triangle" as const; // triangle for rollback
    return "circle" as const;
  });

  const chartData = {
    labels,
    datasets: [
      {
        label: "Vibe",
        data: dataValues,
        borderColor: "var(--magenta)",
        backgroundColor: (ctx: { chart: { ctx: CanvasRenderingContext2D } }) => {
          const g = ctx.chart.ctx.createLinearGradient(0, 0, 0, 300);
          g.addColorStop(0, "rgba(224, 40, 204, 0.4)");
          g.addColorStop(1, "rgba(139, 92, 246, 0.0)");
          return g;
        },
        borderWidth: 3,
        fill: true,
        tension: 0.4,
        pointBackgroundColor: pointColors,
        pointBorderColor: pointBorderColors,
        pointBorderWidth: pointBorderWidths,
        pointRadius: pointRadii,
        pointHoverRadius: pointRadii.map((r) => r + 2),
        pointStyle: pointStyles,
      },
    ],
  };

  const options: ChartOptions<"line"> = {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      y: {
        min: 0,
        max: 100,
        grid: { color: gridColor },
        ticks: {
          font: { family: "JetBrains Mono", size: 10 },
          color: tickColor,
          callback: (value: number | string) => TICK_LABELS[Number(value)] || "",
        },
      },
      x: {
        grid: { display: false },
        ticks: { font: { family: "JetBrains Mono", size: 10 }, color: tickColor },
      },
    },
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: tooltipBg,
        titleColor: tooltipText,
        bodyColor: tooltipText,
        borderColor: "var(--magenta)",
        borderWidth: 1,
        callbacks: {
          title: (items: { dataIndex: number }[]) => {
            const idx = items[0]?.dataIndex;
            if (idx == null) return "";
            const entry = timeline[idx];
            const em = EMOTION_MAP[entry.state as EmotionState];
            let title = em?.label || entry.state;
            if (entry.is_fake) title += " [ФЕЙК]";
            if (entry.rollback) title += " [ОТКАТ]";
            return title;
          },
          label: (ctx: { dataIndex: number; raw: unknown }) => {
            const entry = timeline[ctx.dataIndex];
            const lines: string[] = [];
            // Triggers
            if (entry.triggers && entry.triggers.length > 0) {
              const triggerNames = entry.triggers.map((t) => TRIGGER_LABELS[t] || t);
              lines.push(`Триггеры: ${triggerNames.join(", ")}`);
            }
            // Energy
            if (entry.energy_before != null && entry.energy_after != null) {
              const delta = entry.energy_after - entry.energy_before;
              const sign = delta >= 0 ? "+" : "";
              lines.push(`Энергия: ${entry.energy_before.toFixed(2)} → ${entry.energy_after.toFixed(2)} (${sign}${delta.toFixed(2)})`);
            }
            if (lines.length === 0) {
              const val = Number(ctx.raw);
              lines.push(TICK_LABELS[val] || `${val}%`);
            }
            return lines;
          },
        },
      },
    },
  };

  // Build emotion legend from unique states
  const uniqueStates = [...new Set(timeline.map((e) => e.state))];
  const hasFakes = timeline.some((e) => e.is_fake);
  const hasRollbacks = timeline.some((e) => e.rollback);

  return (
    <div className="relative w-full space-y-3">
      <div className="relative" style={{ minHeight: 250 }}>
        <Line data={chartData} options={options} />
      </div>

      {/* Emotion legend with dot indicators */}
      <div className="flex flex-wrap gap-2 px-1">
        {uniqueStates.map((state) => {
          const em = EMOTION_MAP[state as EmotionState];
          if (!em) return null;
          return (
            <span
              key={state}
              className="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-mono uppercase tracking-wider"
              style={{
                background: em.color + "1A",
                color: em.color,
                border: `1px solid ${em.color}33`,
              }}
            >
              <span
                className={`emotion-dot emotion-dot--${state}`}
                style={{ width: 5, height: 5 }}
              />
              {em.label}
            </span>
          );
        })}
        {/* Marker legend for fake/rollback */}
        {hasFakes && (
          <span
            className="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-mono uppercase tracking-wider"
            style={{ background: "rgba(255,42,109,0.1)", color: "#FF2A6D", border: "1px solid rgba(255,42,109,0.2)" }}
          >
            <span style={{ width: 7, height: 7, transform: "rotate(45deg)", background: "#FF2A6D", display: "inline-block" }} />
            Фейк
          </span>
        )}
        {hasRollbacks && (
          <span
            className="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-mono uppercase tracking-wider"
            style={{ background: "rgba(245,158,11,0.1)", color: "var(--warning)", border: "1px solid rgba(245,158,11,0.2)" }}
          >
            <span style={{ width: 0, height: 0, display: "inline-block", borderLeft: "4px solid transparent", borderRight: "4px solid transparent", borderBottom: "7px solid #f59e0b" }} />
            Откат
          </span>
        )}
      </div>

      {/* Journey summary stats */}
      {journeySummary && (journeySummary.total_transitions || journeySummary.fake_count || journeySummary.rollback_count) && (
        <div className="flex flex-wrap gap-3 px-1 pt-1">
          {journeySummary.total_transitions != null && journeySummary.total_transitions > 0 && (
            <span className="stat-chip">
              <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>Переходов</span>
              <span className="text-xs font-mono font-bold" style={{ color: "var(--text-primary)" }}>{journeySummary.total_transitions}</span>
            </span>
          )}
          {journeySummary.peak_state && (
            <span className="stat-chip">
              <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>Пик</span>
              <span className="text-xs font-mono font-bold" style={{ color: EMOTION_MAP[journeySummary.peak_state as EmotionState]?.color || "var(--text-primary)" }}>
                {EMOTION_MAP[journeySummary.peak_state as EmotionState]?.label || journeySummary.peak_state}
              </span>
            </span>
          )}
          {journeySummary.rollback_count != null && journeySummary.rollback_count > 0 && (
            <span className="stat-chip">
              <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>Откатов</span>
              <span className="text-xs font-mono font-bold" style={{ color: "var(--warning)" }}>{journeySummary.rollback_count}</span>
            </span>
          )}
          {journeySummary.fake_count != null && journeySummary.fake_count > 0 && (
            <span className="stat-chip">
              <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>Фейков</span>
              <span className="text-xs font-mono font-bold" style={{ color: "#FF2A6D" }}>{journeySummary.fake_count}</span>
            </span>
          )}
        </div>
      )}

      {/* Turning points */}
      {journeySummary?.turning_points && journeySummary.turning_points.length > 0 && (
        <div className="space-y-1 px-1">
          <span className="text-xs font-mono tracking-wider" style={{ color: "var(--text-muted)" }}>
            ПОВОРОТНЫЕ МОМЕНТЫ
          </span>
          {journeySummary.turning_points.map((tp, i) => {
            const fromEm = EMOTION_MAP[tp.from_state as EmotionState];
            const toEm = EMOTION_MAP[tp.to_state as EmotionState];
            const isForward = tp.direction === "forward";
            return (
              <div
                key={i}
                className={`flex items-center gap-2 rounded px-2 py-1 text-xs font-mono ${
                  onReplayMessage && tp.message_index != null ? "cursor-pointer hover:ring-1 hover:ring-[var(--accent)]" : ""
                }`}
                style={{
                  background: isForward ? "rgba(0,255,148,0.06)" : "rgba(255,42,109,0.06)",
                  borderLeft: `2px solid ${isForward ? "var(--success)" : "var(--danger)"}`,
                }}
                onClick={() => {
                  if (onReplayMessage && tp.message_index != null) {
                    onReplayMessage(tp.message_index);
                  }
                }}
                title={onReplayMessage && tp.message_index != null ? "Нажмите для Replay Mode" : undefined}
              >
                {tp.message_index != null && (
                  <span className="shrink-0 opacity-50" style={{ color: "var(--accent)" }}>#{tp.message_index + 1}</span>
                )}
                <span style={{ color: fromEm?.color || "var(--text-muted)" }}>{fromEm?.label || tp.from_state}</span>
                <span style={{ color: "var(--text-muted)" }}>{isForward ? "\u2192" : "\u2190"}</span>
                <span style={{ color: toEm?.color || "var(--text-muted)" }}>{toEm?.label || tp.to_state}</span>
                {tp.triggers && tp.triggers.length > 0 && (
                  <span style={{ color: "var(--text-muted)" }}>
                    ({tp.triggers.map((t) => TRIGGER_LABELS[t] || t).join(", ")})
                  </span>
                )}
                {onReplayMessage && tp.message_index != null && (
                  <span className="ml-auto opacity-40 hover:opacity-100 transition-opacity" style={{ color: "var(--accent)" }}>
                    ✨ Replay
                  </span>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
