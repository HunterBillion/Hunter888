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
import { Sparkles } from "lucide-react";
import { cssVar } from "@/lib/chartTheme";
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

  // 2026-04-20: the backend (services/emotion.py::set_emotion_state) writes
  // `timestamp` as an ISO-8601 string (`datetime.now(utc).isoformat()`), but
  // the previous code treated any non-number as `0`, so every label on the
  // X-axis rendered as "0:00" regardless of when the transition happened.
  // Normalise every entry to epoch-ms, then show each tick as elapsed time
  // (m:ss) relative to the first entry — that matches the "Начало"/"Конец"
  // bookends and is actually useful to the coach reading the report.
  const toMs = (t: number | string | undefined | null): number | null => {
    if (typeof t === "number") {
      // Heuristic: numbers < 10^12 are already "seconds since session start",
      // anything larger is epoch-ms. Either way we can normalise.
      return t < 1e12 ? t * 1000 : t;
    }
    if (typeof t === "string" && t.length > 0) {
      const parsed = Date.parse(t);
      return Number.isFinite(parsed) ? parsed : null;
    }
    return null;
  };
  const msValues = timeline.map((e) => toMs(e.timestamp));
  const firstValidMs = msValues.find((v): v is number => v != null) ?? null;
  const labels = timeline.map((e, i) => {
    if (i === 0) return "Начало";
    if (i === timeline.length - 1) return "Конец";
    const ms = msValues[i];
    if (ms == null || firstValidMs == null) return "—";
    const elapsedSec = Math.max(0, Math.round((ms - firstValidMs) / 1000));
    const m = Math.floor(elapsedSec / 60);
    const s = elapsedSec % 60;
    return `${m}:${s.toString().padStart(2, "0")}`;
  });

  const dangerHex = cssVar("--danger", "#E5484D");
  const warningHex = cssVar("--warning", "#E8A630");
  const accentHex = cssVar("--accent", "#6B4DC7");
  const magentaHex = cssVar("--magenta", "#D926B8");

  const dataValues = timeline.map((e) => EMOTION_MAP[e.state as EmotionState]?.value ?? 30);
  const pointColors = timeline.map((e) => {
    if (e.is_fake) return dangerHex;
    if (e.rollback) return warningHex;
    // EMOTION_MAP colors may contain var() — resolve them
    const raw = EMOTION_MAP[e.state as EmotionState]?.color ?? accentHex;
    if (raw.startsWith("var(")) return accentHex;
    return raw;
  });

  // Point styling: larger for fakes/rollbacks, dashed border for fakes
  const pointRadii = timeline.map((e) => (e.is_fake || e.rollback ? 7 : 5));
  const pointBorderWidths = timeline.map((e) => (e.is_fake ? 3 : 2));
  const pointBorderColors = timeline.map((e) => {
    if (e.is_fake) return dangerHex;
    if (e.rollback) return warningHex;
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
        label: "Настроение",
        data: dataValues,
        borderColor: magentaHex,
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
    layout: { padding: { left: 4, right: 8, top: 8, bottom: 4 } },
    scales: {
      y: {
        min: 0,
        max: 100,
        grid: { color: gridColor },
        // Force all 9 labeled states to appear — Chart.js otherwise auto-hides
        // neighbours that are close together (e.g. Враждебный@0 + Холодный@5)
        // which is why some words looked "dropped" into empty space.
        afterBuildTicks: (axis) => {
          axis.ticks = Object.keys(TICK_LABELS).map((v) => ({ value: Number(v) }));
        },
        ticks: {
          // 2026-04-20: bumped from 13 → 15 + stronger weight. Previous size
          // was subjectively "AI-ish / unreadable" at real screen density,
          // especially for compound labels ("Холодный / Враждебный").
          font: { family: "JetBrains Mono", size: 15, weight: 600 },
          color: tickColor,
          autoSkip: false,
          padding: 10,
          callback: (value: number | string) => TICK_LABELS[Number(value)] || "",
        },
      },
      x: {
        grid: { display: false },
        ticks: {
          // 2026-04-20: bumped from 13 → 14 for readability; limited tick
          // count so labels don't cram into each other on dense timelines.
          font: { family: "JetBrains Mono", size: 14, weight: 500 },
          color: tickColor,
          padding: 8,
          maxRotation: 0,
          autoSkip: true,
          maxTicksLimit: 8,
        },
      },
    },
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: tooltipBg,
        titleColor: tooltipText,
        bodyColor: tooltipText,
        borderColor: magentaHex,
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

  // ── Recommendations derived from journey ──────────────────────
  const tips: Array<{ tone: "warn" | "good" | "info"; title: string; body: string }> = [];
  if (journeySummary) {
    const total = journeySummary.total_transitions ?? 0;
    const rollbacks = journeySummary.rollback_count ?? 0;
    const fakes = journeySummary.fake_count ?? 0;
    const peakValue = journeySummary.peak_state
      ? EMOTION_MAP[journeySummary.peak_state as EmotionState]?.value ?? 0
      : 0;

    if (peakValue < 40) {
      tips.push({
        tone: "warn",
        title: "Клиент не дошёл до интереса",
        body: "Пик разговора остановился на защитной эмоции. Пробуй раньше выходить на боль клиента и зацеплять конкретикой.",
      });
    } else if (peakValue >= 60 && peakValue < 95) {
      tips.push({
        tone: "info",
        title: "Клиент на «Обдумывает», но не на сделке",
        body: "Был близок к решению — не хватило финального хода. Чаще используй closing-вопросы и фиксируй договорённости сразу.",
      });
    } else if (peakValue >= 95) {
      tips.push({
        tone: "good",
        title: "Довёл до сделки — молодец",
        body: "Удерживай этот паттерн: раннее эмоциональное попадание + конкретика + чёткое закрытие.",
      });
    }

    if (rollbacks >= 3) {
      tips.push({
        tone: "warn",
        title: "Много откатов по эмоциям",
        body: `${rollbacks} раз продвинулся и откатился обратно. Следи, какие фразы ломают рапорт — чаще всего это давление после прогресса.`,
      });
    } else if (rollbacks === 1 || rollbacks === 2) {
      tips.push({
        tone: "info",
        title: "Один-два отката",
        body: "В целом рапорт стабильный. Посмотри поворотные моменты ниже — там точки, где слегка провалился.",
      });
    }

    if (fakes > 0) {
      tips.push({
        tone: "warn",
        title: "Клиент давал ложные сигналы",
        body: `${fakes} фейковых перехода: клиент делал вид, что согласен, а на самом деле сопротивлялся. Проверяй реальный интерес уточняющими вопросами.`,
      });
    }

    if (total >= 6 && rollbacks === 0) {
      tips.push({
        tone: "good",
        title: "Плавное движение без откатов",
        body: "Удержал рапорт на всей дистанции. Эмоции клиента стабильно двигались вперёд — такой паттерн стоит закрепить.",
      });
    }

    if (tips.length === 0 && total > 0) {
      tips.push({
        tone: "info",
        title: "Эмоциональный путь нейтральный",
        body: "Большого движения по эмоциям не было. Экспериментируй с разными триггерами — эмпатия, факты, личный тон.",
      });
    }
  }

  return (
    <div className="relative w-full space-y-4">
      <div className="relative" style={{ minHeight: 360 }}>
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
              className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-sm font-mono uppercase tracking-wider"
              style={{
                background: em.color + "1A",
                color: em.color,
                border: `1px solid ${em.color}33`,
              }}
            >
              <span
                className={`emotion-dot emotion-dot--${state}`}
                style={{ width: 6, height: 6 }}
              />
              {em.label}
            </span>
          );
        })}
        {/* Marker legend for fake/rollback */}
        {hasFakes && (
          <span
            className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-sm font-mono uppercase tracking-wider"
            style={{ background: "var(--danger-muted)", color: "var(--danger)", border: "1px solid var(--danger-muted)" }}
          >
            <span style={{ width: 7, height: 7, transform: "rotate(45deg)", background: "var(--danger)", display: "inline-block" }} />
            Фейк
          </span>
        )}
        {hasRollbacks && (
          <span
            className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-sm font-mono uppercase tracking-wider"
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
              <span className="text-sm font-mono" style={{ color: "var(--text-muted)" }}>Переходов</span>
              <span className="text-sm font-mono font-bold" style={{ color: "var(--text-primary)" }}>{journeySummary.total_transitions}</span>
            </span>
          )}
          {journeySummary.peak_state && (
            <span className="stat-chip">
              <span className="text-sm font-mono" style={{ color: "var(--text-muted)" }}>Пик</span>
              <span className="text-sm font-mono font-bold" style={{ color: EMOTION_MAP[journeySummary.peak_state as EmotionState]?.color || "var(--text-primary)" }}>
                {EMOTION_MAP[journeySummary.peak_state as EmotionState]?.label || journeySummary.peak_state}
              </span>
            </span>
          )}
          {journeySummary.rollback_count != null && journeySummary.rollback_count > 0 && (
            <span className="stat-chip">
              <span className="text-sm font-mono" style={{ color: "var(--text-muted)" }}>Откатов</span>
              <span className="text-sm font-mono font-bold" style={{ color: "var(--warning)" }}>{journeySummary.rollback_count}</span>
            </span>
          )}
          {journeySummary.fake_count != null && journeySummary.fake_count > 0 && (
            <span className="stat-chip">
              <span className="text-sm font-mono" style={{ color: "var(--text-muted)" }}>Фейков</span>
              <span className="text-sm font-mono font-bold" style={{ color: "var(--danger)" }}>{journeySummary.fake_count}</span>
            </span>
          )}
        </div>
      )}

      {/* Turning points */}
      {journeySummary?.turning_points && journeySummary.turning_points.length > 0 && (
        <div className="space-y-1 px-1">
          <span className="text-sm font-mono tracking-wider" style={{ color: "var(--text-muted)" }}>
            ПОВОРОТНЫЕ МОМЕНТЫ
          </span>
          {journeySummary.turning_points.map((tp, i) => {
            const fromEm = EMOTION_MAP[tp.from_state as EmotionState];
            const toEm = EMOTION_MAP[tp.to_state as EmotionState];
            const isForward = tp.direction === "forward";
            return (
              <div
                key={i}
                className={`flex items-center gap-2 rounded px-2.5 py-1.5 text-sm font-mono ${
                  onReplayMessage && tp.message_index != null ? "cursor-pointer hover:ring-1 hover:ring-[var(--accent)]" : ""
                }`}
                style={{
                  background: isForward ? "var(--success-muted)" : "var(--danger-muted)",
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
                    <Sparkles size={12} style={{ display: "inline", verticalAlign: "middle", marginRight: 3 }} /> Replay
                  </span>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Recommendations derived from the journey */}
      {tips.length > 0 && (
        <div className="space-y-2 px-1 pt-1">
          <span className="text-sm font-mono tracking-wider" style={{ color: "var(--text-muted)" }}>
            РЕКОМЕНДАЦИИ
          </span>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {tips.map((tip, i) => {
              const palette =
                tip.tone === "good"
                  ? { border: "var(--success)", bg: "var(--success-muted)", icon: "✔" }
                  : tip.tone === "warn"
                  ? { border: "var(--warning)", bg: "rgba(245,158,11,0.1)", icon: "!" }
                  : { border: "var(--accent)", bg: "var(--accent-muted)", icon: "→" };
              return (
                <div
                  key={i}
                  className="rounded px-3 py-2.5 text-sm"
                  style={{ background: palette.bg, borderLeft: `3px solid ${palette.border}` }}
                >
                  <div
                    className="font-mono font-bold tracking-wide mb-1"
                    style={{ color: palette.border, fontSize: 14 }}
                  >
                    <span className="mr-1.5">{palette.icon}</span>
                    {tip.title}
                  </div>
                  <div style={{ color: "var(--text-secondary)", lineHeight: 1.5 }}>{tip.body}</div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
