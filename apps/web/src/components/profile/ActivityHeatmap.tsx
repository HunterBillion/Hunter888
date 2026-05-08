"use client";

/**
 * ActivityHeatmap — пиксельный GitHub-style heatmap активности по дням.
 *
 * 2026-05-08: добавлен в /profile-редизайн «★ ПРОФИЛЬ ОХОТНИКА ★».
 *
 * Источник: GET /users/me/activity?days=180 (новый endpoint, добавлен
 * в этом же PR). Возвращает только дни с ≥ 1 завершённой сессией +
 * streak counters; пустые дни рисуем клиентом (экономим 365×N байт
 * на wire).
 *
 * Геометрия:
 *   - 26 недель × 7 дней (≈ 6 месяцев истории)
 *   - каждый «пиксель» 12×12 px, gap 3px между клетками
 *   - 5 уровней интенсивности (0..4) — цвет от прозрачного до accent
 *   - подписи дней слева (Пн / Ср / Пт), месяцев сверху
 *   - tooltip при ховере: дата + sessions + avg_score
 */

import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Activity, Flame, Loader2, Trophy } from "lucide-react";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";

interface ActivityDay {
  date: string;
  sessions: number;
  avg_score: number | null;
}

interface ActivityResponse {
  days: ActivityDay[];
  total_days_active: number;
  total_sessions: number;
  streak_current: number;
  streak_best: number;
}

interface Props {
  /** Сколько дней назад от сегодня показывать. Default 180 ≈ 26 недель. */
  days?: number;
  /** Цвет акцента для самой плотной интенсивности. Default — текущий accent. */
  accent?: string;
}

const MONTH_LABELS = [
  "Янв", "Фев", "Мар", "Апр", "Май", "Июн",
  "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек",
];

const DAY_LABELS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

function intensityLevel(sessions: number): 0 | 1 | 2 | 3 | 4 {
  if (sessions <= 0) return 0;
  if (sessions === 1) return 1;
  if (sessions <= 2) return 2;
  if (sessions <= 4) return 3;
  return 4;
}

function levelColor(level: 0 | 1 | 2 | 3 | 4, accent: string): string {
  // Прозрачность от 0.08 до 1.0; 0 — почти невидимая клетка-плейсхолдер.
  const alphas = [0.08, 0.28, 0.48, 0.72, 1.0];
  return level === 0
    ? "rgba(255,255,255,0.06)"
    : `color-mix(in srgb, ${accent} ${Math.round(alphas[level] * 100)}%, transparent)`;
}

/** Сегодняшний день в UTC, как ISO. */
function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

/** Получить дату по offset от сегодня (0 = сегодня). */
function isoMinusDays(offset: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - offset);
  return d.toISOString().slice(0, 10);
}

/** Day-of-week в формате ISO (1 = Пн, 7 = Вс). */
function isoDayOfWeek(iso: string): number {
  const d = new Date(`${iso}T00:00:00Z`);
  const wd = d.getUTCDay(); // 0=Sun..6=Sat
  return wd === 0 ? 7 : wd;
}

export function ActivityHeatmap({ days = 180, accent = "var(--accent)" }: Props) {
  const [data, setData] = useState<ActivityResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hovered, setHovered] = useState<{ iso: string; sessions: number; avg: number | null } | null>(
    null,
  );

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .get<ActivityResponse>(`/users/me/activity?days=${days}`)
      .then((d) => {
        if (cancelled) return;
        setData(d);
      })
      .catch((e) => {
        logger.error("Activity fetch failed", e);
        if (cancelled) return;
        setError("Не удалось загрузить активность");
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [days]);

  /**
   * Заполняем сетку: для каждого из последних `days` дней — клетка.
   * Группируем по неделям (по 7 дней) — на сетке колонки = недели,
   * строки = дни недели.
   */
  const grid = useMemo(() => {
    if (!data) return null;
    const byDate = new Map<string, ActivityDay>();
    for (const d of data.days) byDate.set(d.date, d);

    // Якорим начало на ПРОШЛЫЙ понедельник, чтобы первая неделя
    // начиналась корректно.
    const today = todayIso();
    const todayDow = isoDayOfWeek(today); // 1..7
    // Сколько дней назад от сегодня нужно отсчитать чтобы попасть на
    // понедельник самой ранней недели в окне.
    const totalCells = days + (7 - todayDow); // дотягиваем сегодня до конца недели
    const weeksCount = Math.ceil(totalCells / 7);

    // Колонки = недели. GitHub-style: старые СЛЕВА, новые СПРАВА.
    // Цикл идёт от старейшей недели (w=N-1) к текущей (w=0). Каждая
    // неделя пушится в `cols` сразу в правильном хронологическом
    // порядке: cols[0] = oldest, cols[last] = current.
    //
    // 2026-05-08 BUG-FIX (heatmap reverse direction): раньше в конце
    // стоял `cols.reverse()` — что инвертировало готовый правильный
    // порядок и делал «справа налево». Скриншот пользователя показал
    // зелёные клетки в левом верхнем углу с лейблом «МАЙ АПР» (они
    // ещё и наезжали друг на друга, потому что были в первой колонке).
    // Удалили reverse — теперь как в GitHub.
    const cols: { iso: string; sessions: number; avg: number | null; level: 0 | 1 | 2 | 3 | 4 }[][] = [];

    for (let w = weeksCount - 1; w >= 0; w--) {
      const week: { iso: string; sessions: number; avg: number | null; level: 0 | 1 | 2 | 3 | 4 }[] = [];
      for (let dow = 1; dow <= 7; dow++) {
        // offset от сегодня в днях:
        const offset = w * 7 + (todayDow - dow);
        if (offset < 0 || offset >= days) {
          week.push({ iso: "", sessions: 0, avg: null, level: 0 });
          continue;
        }
        const iso = isoMinusDays(offset);
        const entry = byDate.get(iso);
        const sessions = entry?.sessions ?? 0;
        week.push({
          iso,
          sessions,
          avg: entry?.avg_score ?? null,
          level: intensityLevel(sessions),
        });
      }
      cols.push(week);
    }
    return cols;
  }, [data, days]);

  /**
   * Лейблы месяцев над сеткой. Один лейбл на колонку, в которой
   * начинается новый месяц (по понедельнику-первой-ячейке).
   *
   * 2026-05-08: добавлен min-gap 2 колонки (≥30 px) между лейблами,
   * чтобы соседние короткие месяцы (например, конец недели в апреле +
   * начало в мае) не наезжали друг на друга. На скриншоте пользователя
   * «МАЙ» и «АПР» были склеены в первой колонке.
   */
  const monthMarkers = useMemo(() => {
    if (!grid) return [];
    const markers: { col: number; label: string }[] = [];
    let lastMonth = -1;
    let lastMarkerCol = -10;
    const MIN_GAP = 2; // min-gap в колонках между соседними лейблами
    grid.forEach((week, col) => {
      const firstCell = week.find((c) => c.iso) ?? week[0];
      if (!firstCell.iso) return;
      const m = new Date(`${firstCell.iso}T00:00:00Z`).getUTCMonth();
      if (m !== lastMonth) {
        if (col - lastMarkerCol >= MIN_GAP) {
          markers.push({ col, label: MONTH_LABELS[m] });
          lastMarkerCol = col;
        }
        lastMonth = m;
      }
    });
    return markers;
  }, [grid]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-10">
        <Loader2 size={20} className="animate-spin" style={{ color: "var(--accent)" }} />
      </div>
    );
  }

  if (error || !data || !grid) {
    return (
      <div
        className="font-pixel uppercase tracking-widest text-center py-8"
        style={{ color: "var(--text-muted)", fontSize: 14 }}
      >
        {error || "Активности пока нет"}
      </div>
    );
  }

  const cellSize = 12;
  const cellGap = 3;

  return (
    <div className="space-y-4">
      {/* Заголовок секции с stat-блоками */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Activity size={16} style={{ color: "var(--accent)" }} />
          <span
            className="font-pixel uppercase tracking-widest"
            style={{ color: "var(--text-secondary)", fontSize: 14 }}
          >
            АКТИВНОСТЬ ЗА {days} ДНЕЙ
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Stat
            icon={<Flame size={14} />}
            label="ТЕКУЩИЙ СТРИК"
            value={`${data.streak_current}д`}
            color={data.streak_current > 0 ? "#fb923c" : "var(--text-muted)"}
          />
          <Stat
            icon={<Trophy size={14} />}
            label="ЛУЧШИЙ"
            value={`${data.streak_best}д`}
            color="#facc15"
          />
          <Stat
            icon={<Activity size={14} />}
            label="ДНЕЙ В ИГРЕ"
            value={`${data.total_days_active}`}
            color="var(--accent)"
          />
        </div>
      </div>

      {/* Heatmap */}
      <div
        className="rounded-md p-4 overflow-x-auto"
        style={{
          background: "rgba(8,5,18,0.45)",
          border: "1px dashed rgba(255,255,255,0.12)",
        }}
      >
        <div
          className="inline-block relative"
          style={{ minWidth: grid.length * (cellSize + cellGap) + 32 }}
        >
          {/* Месяцы сверху */}
          <div
            className="relative"
            style={{ height: 18, marginLeft: 28, marginBottom: 4 }}
          >
            {monthMarkers.map((m) => (
              <div
                key={`${m.col}-${m.label}`}
                className="absolute font-pixel uppercase tracking-widest"
                style={{
                  left: m.col * (cellSize + cellGap),
                  fontSize: 11,
                  color: "var(--text-muted)",
                }}
              >
                {m.label}
              </div>
            ))}
          </div>

          {/* Сетка: подписи дней слева + ячейки */}
          <div className="flex gap-1">
            {/* Колонка с подписями Пн/Ср/Пт */}
            <div
              className="flex flex-col"
              style={{ gap: cellGap, marginRight: 6 }}
            >
              {DAY_LABELS.map((dl, i) => (
                <div
                  key={dl}
                  className="font-pixel uppercase tracking-widest flex items-center"
                  style={{
                    height: cellSize,
                    fontSize: 10,
                    color: "var(--text-muted)",
                    opacity: i % 2 === 0 ? 1 : 0,
                    width: 22,
                  }}
                >
                  {dl}
                </div>
              ))}
            </div>

            {/* Колонки-недели */}
            {grid.map((week, col) => (
              <div
                key={col}
                className="flex flex-col"
                style={{ gap: cellGap }}
              >
                {week.map((cell, row) => {
                  const isToday = cell.iso === todayIso();
                  return (
                    <motion.button
                      key={row}
                      type="button"
                      tabIndex={cell.iso ? 0 : -1}
                      onMouseEnter={() =>
                        cell.iso &&
                        setHovered({
                          iso: cell.iso,
                          sessions: cell.sessions,
                          avg: cell.avg,
                        })
                      }
                      onMouseLeave={() => setHovered(null)}
                      onFocus={() =>
                        cell.iso &&
                        setHovered({
                          iso: cell.iso,
                          sessions: cell.sessions,
                          avg: cell.avg,
                        })
                      }
                      onBlur={() => setHovered(null)}
                      whileHover={{ scale: 1.18 }}
                      style={{
                        width: cellSize,
                        height: cellSize,
                        background: cell.iso
                          ? levelColor(cell.level, accent === "var(--accent)" ? "#a78bfa" : accent)
                          : "transparent",
                        border: isToday
                          ? `1px solid ${accent === "var(--accent)" ? "#a78bfa" : accent}`
                          : "1px solid rgba(255,255,255,0.05)",
                        borderRadius: 2,
                        cursor: cell.iso && cell.sessions > 0 ? "pointer" : "default",
                      }}
                      aria-label={
                        cell.iso
                          ? `${cell.iso}: ${cell.sessions} сессий`
                          : ""
                      }
                    />
                  );
                })}
              </div>
            ))}
          </div>

          {/* Легенда + tooltip */}
          <div className="flex items-center justify-between mt-4">
            <div
              className="font-pixel uppercase tracking-widest"
              style={{ fontSize: 11, color: "var(--text-muted)" }}
            >
              {hovered ? (
                <span>
                  {hovered.iso} ·{" "}
                  <span style={{ color: "var(--text-primary)" }}>
                    {hovered.sessions === 0
                      ? "ничего"
                      : `${hovered.sessions} ${declSessions(hovered.sessions)}`}
                  </span>
                  {hovered.avg !== null && hovered.avg > 0 && (
                    <span> · ср. {hovered.avg}</span>
                  )}
                </span>
              ) : (
                <span>наведи на квадрат — покажет день</span>
              )}
            </div>
            <div className="flex items-center gap-1.5">
              <span
                className="font-pixel uppercase tracking-widest"
                style={{ fontSize: 11, color: "var(--text-muted)" }}
              >
                меньше
              </span>
              {[0, 1, 2, 3, 4].map((lvl) => (
                <span
                  key={lvl}
                  style={{
                    width: cellSize,
                    height: cellSize,
                    background: levelColor(
                      lvl as 0 | 1 | 2 | 3 | 4,
                      accent === "var(--accent)" ? "#a78bfa" : accent,
                    ),
                    borderRadius: 2,
                    border: "1px solid rgba(255,255,255,0.05)",
                  }}
                />
              ))}
              <span
                className="font-pixel uppercase tracking-widest"
                style={{ fontSize: 11, color: "var(--text-muted)" }}
              >
                больше
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Stat({
  icon,
  label,
  value,
  color,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  color: string;
}) {
  return (
    <div className="flex items-center gap-2">
      <span style={{ color }}>{icon}</span>
      <div className="leading-tight">
        <div
          className="font-pixel uppercase tracking-widest"
          style={{ color: "var(--text-muted)", fontSize: 11 }}
        >
          {label}
        </div>
        <div
          className="font-pixel font-bold tabular-nums"
          style={{ color, fontSize: 16, lineHeight: 1.0 }}
        >
          {value}
        </div>
      </div>
    </div>
  );
}

function declSessions(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 14) return "сессий";
  if (mod10 === 1) return "сессия";
  if (mod10 >= 2 && mod10 <= 4) return "сессии";
  return "сессий";
}
