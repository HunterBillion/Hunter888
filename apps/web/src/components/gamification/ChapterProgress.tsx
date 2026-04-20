"use client";

/**
 * ChapterProgress — story arc progress widget for the home page.
 * Shows current chapter, epoch, and progress toward next chapter.
 */

import { useState, useEffect, useCallback } from "react";
import { BookOpen, Lock, ChevronRight, Star, Trophy, Map } from "lucide-react";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";
import ChapterMap from "./ChapterMap";

interface StoryProgressData {
  current_chapter: number;
  current_epoch: number;
  chapter_name: string;
  epoch_name: string;
  epoch_tagline: string;
  chapter_intro: string;
  chapter_sessions: number;
  chapter_avg_score: number;
  chapter_best_score: number;
  specialization: string | null;
  next_chapter: number | null;
  next_unlock_level: number | null;
  next_unlock_sessions: number | null;
  next_unlock_score: number | null;
  manager_level: number;
  progress_pct: number;
  epochs_completed: number[];
}

const EPOCH_ICONS = ["", "I", "II", "III", "IV"];
const EPOCH_COLORS = [
  "",
  "var(--success)",      // Epoch I  — green
  "var(--warning)",      // Epoch II — amber
  "var(--accent)",       // Epoch III — accent
  "#A855F7",             // Epoch IV — purple
];

export default function ChapterProgress() {
  const [data, setData] = useState<StoryProgressData | null>(null);
  const [loading, setLoading] = useState(true);
  // 2026-04-20: `expanded` kept for the inline stats block (ёмкая справка
  // по текущей главе). Click on the header NOW opens the full map drawer
  // — users said they "не понимают градации на главы", карта закрывает эту
  // дыру. Inline expand triggered only by the small chevron icon.
  const [expanded, setExpanded] = useState(false);
  const [mapOpen, setMapOpen] = useState(false);

  const fetchProgress = useCallback(async () => {
    try {
      const d = await api.get<StoryProgressData>("/story/progress");
      setData(d);
    } catch (err) {
      logger.error("Failed to fetch story progress:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchProgress();
  }, [fetchProgress]);

  if (loading || !data) {
    return null;
  }

  const epochColor = EPOCH_COLORS[data.current_epoch] || "var(--text-secondary)";
  const isMaxChapter = data.current_chapter >= 12;

  return (
    <div
      // 2026-04-20: панель раньше сливалась с соседними карточками. Теперь:
      //   – бордер в цвете эпохи (40% alpha) вместо дефолтного --border-color
      //   – фон с лёгким градиентом из цвета эпохи (8% alpha → transparent)
      //   – на hover бордер усиливается до 70% alpha
      //   – иконка "карта" справа — явный affordance "здесь кликать"
      className="rounded-xl border p-4 cursor-pointer transition-all group mb-4"
      style={{
        borderColor: `color-mix(in srgb, ${epochColor} 40%, transparent)`,
        background: `linear-gradient(135deg, color-mix(in srgb, ${epochColor} 8%, var(--bg-secondary)) 0%, var(--bg-secondary) 70%)`,
      }}
      onMouseEnter={(e) =>
        (e.currentTarget.style.borderColor = `color-mix(in srgb, ${epochColor} 70%, transparent)`)
      }
      onMouseLeave={(e) =>
        (e.currentTarget.style.borderColor = `color-mix(in srgb, ${epochColor} 40%, transparent)`)
      }
      onClick={() => setMapOpen(true)}
      role="button"
      aria-label={`Глава ${data.current_chapter}: ${data.chapter_name}. Нажмите чтобы открыть карту глав`}
    >
      {/* Header row */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <span
            className="flex-shrink-0 flex items-center justify-center w-11 h-11 rounded-lg text-base font-bold text-white"
            style={{
              background: `linear-gradient(135deg, ${epochColor} 0%, color-mix(in srgb, ${epochColor} 60%, #000) 100%)`,
              boxShadow: `0 0 12px color-mix(in srgb, ${epochColor} 45%, transparent)`,
            }}
          >
            {EPOCH_ICONS[data.current_epoch]}
          </span>
          <div className="min-w-0">
            <div
              className="text-[10px] font-pixel uppercase tracking-wider mb-0.5"
              style={{ color: epochColor, letterSpacing: "0.14em" }}
            >
              Эпоха {EPOCH_ICONS[data.current_epoch]} · {data.epoch_name}
            </div>
            <div
              className="font-bold truncate"
              style={{
                color: "var(--text-primary)",
                fontSize: "16px",
                lineHeight: "1.2",
              }}
            >
              Глава {data.current_chapter}: {data.chapter_name}
            </div>
          </div>
        </div>
        <div className="flex-shrink-0 flex items-center gap-2">
          {/* Affordance to open the full chapter map drawer */}
          <div
            className="flex items-center gap-1 text-[10px] uppercase tracking-wider transition-opacity opacity-70 group-hover:opacity-100"
            style={{ color: epochColor, letterSpacing: "0.14em" }}
          >
            <Map size={14} />
            <span className="hidden sm:inline">Путь</span>
          </div>
          {/* Small chevron — toggles the inline stats WITHOUT opening the map */}
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setExpanded((v) => !v);
            }}
            aria-expanded={expanded}
            aria-label={expanded ? "Скрыть статистику" : "Показать статистику"}
            className="p-1 rounded hover:bg-[var(--bg-tertiary)] transition"
            style={{ color: "var(--text-muted)" }}
          >
            <ChevronRight
              size={14}
              className={`transition-transform ${expanded ? "rotate-90" : ""}`}
            />
          </button>
        </div>
      </div>

      {/* Progress bar */}
      {!isMaxChapter && (
        <div className="mt-2">
          <div className="flex items-center justify-between text-xs text-[var(--text-muted)] mb-1">
            <span>До Главы {(data.next_chapter || 0)}</span>
            <span>{data.progress_pct}%</span>
          </div>
          <div className="w-full h-1.5 rounded-full bg-[var(--bg-tertiary)] overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{
                width: `${Math.min(data.progress_pct, 100)}%`,
                backgroundColor: epochColor,
              }}
            />
          </div>
        </div>
      )}

      {/* Expanded details */}
      {expanded && (
        <div className="mt-3 pt-3 border-t border-[var(--border-color)] space-y-2">
          <p className="text-xs text-[var(--text-secondary)] italic leading-relaxed">
            {data.chapter_intro}
          </p>

          {/* Stats row */}
          <div className="flex gap-3 text-xs">
            <div className="flex items-center gap-1 text-[var(--text-muted)]">
              <BookOpen size={12} />
              <span>{data.chapter_sessions} сессий</span>
            </div>
            <div className="flex items-center gap-1 text-[var(--text-muted)]">
              <Star size={12} />
              <span>ср. {data.chapter_avg_score}</span>
            </div>
            {data.chapter_best_score > 0 && (
              <div className="flex items-center gap-1 text-[var(--text-muted)]">
                <Trophy size={12} />
                <span>лучш. {data.chapter_best_score}</span>
              </div>
            )}
          </div>

          {/* Unlock conditions */}
          {!isMaxChapter && data.next_unlock_level && (
            <div className="text-xs text-[var(--text-muted)] space-y-0.5">
              <div className="font-medium text-[var(--text-secondary)]">Условия разблокировки:</div>
              <div className="flex items-center gap-1">
                {data.manager_level >= data.next_unlock_level ? "\u2705" : <Lock size={10} />}
                <span>Уровень {data.next_unlock_level} (текущий: {data.manager_level})</span>
              </div>
              {data.next_unlock_sessions != null && (
                <div className="flex items-center gap-1">
                  {data.chapter_sessions >= data.next_unlock_sessions ? "\u2705" : <Lock size={10} />}
                  <span>{data.next_unlock_sessions} сессий (выполнено: {data.chapter_sessions})</span>
                </div>
              )}
              {data.next_unlock_score != null && (
                <div className="flex items-center gap-1">
                  {data.chapter_avg_score >= data.next_unlock_score ? "\u2705" : <Lock size={10} />}
                  <span>Средний балл {data.next_unlock_score}+ (текущий: {data.chapter_avg_score})</span>
                </div>
              )}
            </div>
          )}

          {/* Epoch progress */}
          <div className="flex gap-1 pt-1">
            {[1, 2, 3, 4].map((eid) => (
              <div
                key={eid}
                className="flex-1 h-1 rounded-full"
                style={{
                  backgroundColor: data.epochs_completed.includes(eid)
                    ? EPOCH_COLORS[eid]
                    : eid === data.current_epoch
                    ? `${EPOCH_COLORS[eid]}80`
                    : "var(--bg-tertiary)",
                }}
              />
            ))}
          </div>
        </div>
      )}

      {/* Full-viewport chapter map drawer (opens when the card itself is clicked) */}
      <ChapterMap open={mapOpen} onClose={() => setMapOpen(false)} />
    </div>
  );
}
