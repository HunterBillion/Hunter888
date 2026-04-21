"use client";

/**
 * ChapterProgress — story arc progress widget for the home page.
 * Shows current chapter, epoch, and progress toward next chapter.
 */

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { BookOpen, ChevronRight, Star, Trophy, Map } from "lucide-react";
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
            {/* Epoch line: monospace for "Эпоха", different weight for name.
                Wider tracking + 9px makes it look like a chapter subtitle in
                a book (small caps vibe). */}
            <div
              className="text-[10px] font-mono uppercase mb-1 flex items-center gap-1.5"
              style={{ color: epochColor, letterSpacing: "0.2em" }}
            >
              <span style={{ opacity: 0.7 }}>Эпоха</span>
              <span className="font-bold">{EPOCH_ICONS[data.current_epoch]}</span>
              <span style={{ opacity: 0.5 }}>·</span>
              <span style={{ opacity: 0.85 }}>{data.epoch_name}</span>
            </div>
            {/* Chapter title: display font (Geist), generous size, serif-y
                feel for the book metaphor. letterSpacing slightly tighter for
                a confident editorial title look. */}
            <div
              className="font-display font-bold truncate"
              style={{
                color: "var(--text-primary)",
                fontSize: "18px",
                lineHeight: "1.15",
                letterSpacing: "-0.01em",
              }}
            >
              <span style={{ color: epochColor, fontWeight: 500 }}>Глава {data.current_chapter}.</span>{" "}
              {data.chapter_name}
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

      {/* Expanded details — richer content when shutter raised */}
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            key="expanded"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
            className="overflow-hidden"
          >
            <div className="mt-4 pt-4 border-t space-y-4"
              style={{ borderColor: `color-mix(in srgb, ${epochColor} 25%, var(--border-color))` }}
            >
              {/* Epoch tagline — what this epoch is about (new — larger text) */}
              {data.epoch_tagline && (
                <div>
                  <div className="text-[10px] font-mono uppercase mb-1.5" style={{ color: epochColor, letterSpacing: "0.2em", opacity: 0.75 }}>
                    Об эпохе
                  </div>
                  <p className="text-sm leading-relaxed" style={{ color: "var(--text-primary)", fontWeight: 500 }}>
                    {data.epoch_tagline}
                  </p>
                </div>
              )}

              {/* Chapter narrative — book-style pull-quote with accent border */}
              {data.chapter_intro && (
                <div className="relative pl-4" style={{ borderLeft: `3px solid ${epochColor}` }}>
                  <div className="text-[10px] font-mono uppercase mb-1" style={{ color: epochColor, letterSpacing: "0.2em", opacity: 0.75 }}>
                    Сюжет главы
                  </div>
                  <p className="text-sm leading-relaxed" style={{ color: "var(--text-secondary)", fontStyle: "italic" }}>
                    «{data.chapter_intro}»
                  </p>
                </div>
              )}

              {/* Specialization hint if set — "ты выбрал недвижимость" */}
              {data.specialization && (
                <div className="text-xs" style={{ color: "var(--text-muted)" }}>
                  Специализация: <span style={{ color: "var(--text-secondary)", fontWeight: 500 }}>{data.specialization}</span>
                </div>
              )}

              {/* Stats — session count + avg score + best */}
              <div>
                <div className="text-[10px] font-mono uppercase mb-1.5" style={{ color: "var(--text-muted)", letterSpacing: "0.2em" }}>
                  В этой главе
                </div>
                <div className="flex flex-wrap gap-3 text-xs">
                  <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md" style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)" }}>
                    <BookOpen size={12} style={{ color: epochColor }} />
                    <span style={{ color: "var(--text-secondary)" }}>{data.chapter_sessions}</span>
                    <span style={{ color: "var(--text-muted)" }}>сессий</span>
                  </div>
                  <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md" style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)" }}>
                    <Star size={12} style={{ color: epochColor }} />
                    <span style={{ color: "var(--text-secondary)" }}>{data.chapter_avg_score.toFixed(1)}</span>
                    <span style={{ color: "var(--text-muted)" }}>ср. балл</span>
                  </div>
                  {data.chapter_best_score > 0 && (
                    <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md" style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)" }}>
                      <Trophy size={12} style={{ color: epochColor }} />
                      <span style={{ color: "var(--text-secondary)" }}>{data.chapter_best_score}</span>
                      <span style={{ color: "var(--text-muted)" }}>рекорд</span>
                    </div>
                  )}
                </div>
              </div>

              {/* Unlock conditions — presented as checklist */}
              {!isMaxChapter && data.next_unlock_level && (
                <div>
                  <div className="text-[10px] font-mono uppercase mb-1.5" style={{ color: "var(--text-muted)", letterSpacing: "0.2em" }}>
                    Чтобы открыть главу {data.next_chapter}
                  </div>
                  <div className="space-y-1.5 text-xs">
                    <div className="flex items-center gap-2">
                      <span style={{ color: data.manager_level >= data.next_unlock_level ? "var(--success, #10b981)" : "var(--text-muted)" }}>
                        {data.manager_level >= data.next_unlock_level ? "✓" : "○"}
                      </span>
                      <span style={{ color: "var(--text-secondary)" }}>
                        Уровень <b style={{ color: "var(--text-primary)" }}>{data.next_unlock_level}</b>
                        <span style={{ color: "var(--text-muted)" }}> (твой: {data.manager_level})</span>
                      </span>
                    </div>
                    {data.next_unlock_sessions != null && (
                      <div className="flex items-center gap-2">
                        <span style={{ color: data.chapter_sessions >= data.next_unlock_sessions ? "var(--success, #10b981)" : "var(--text-muted)" }}>
                          {data.chapter_sessions >= data.next_unlock_sessions ? "✓" : "○"}
                        </span>
                        <span style={{ color: "var(--text-secondary)" }}>
                          <b style={{ color: "var(--text-primary)" }}>{data.next_unlock_sessions}</b> сессий в главе
                          <span style={{ color: "var(--text-muted)" }}> (выполнено: {data.chapter_sessions})</span>
                        </span>
                      </div>
                    )}
                    {data.next_unlock_score != null && (
                      <div className="flex items-center gap-2">
                        <span style={{ color: data.chapter_avg_score >= data.next_unlock_score ? "var(--success, #10b981)" : "var(--text-muted)" }}>
                          {data.chapter_avg_score >= data.next_unlock_score ? "✓" : "○"}
                        </span>
                        <span style={{ color: "var(--text-secondary)" }}>
                          Средний балл <b style={{ color: "var(--text-primary)" }}>{data.next_unlock_score}+</b>
                          <span style={{ color: "var(--text-muted)" }}> (твой: {data.chapter_avg_score.toFixed(1)})</span>
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Epoch progress timeline — all 4 epochs */}
              <div>
                <div className="text-[10px] font-mono uppercase mb-1.5" style={{ color: "var(--text-muted)", letterSpacing: "0.2em" }}>
                  Путь охотника
                </div>
                <div className="flex gap-1.5 items-center">
                  {[1, 2, 3, 4].map((eid) => {
                    const done = data.epochs_completed.includes(eid);
                    const current = eid === data.current_epoch;
                    return (
                      <div key={eid} className="flex-1 flex flex-col gap-1">
                        <div
                          className="h-1.5 rounded-full transition-all"
                          style={{
                            background: done ? EPOCH_COLORS[eid] : current ? `${EPOCH_COLORS[eid]}80` : "var(--bg-tertiary)",
                            boxShadow: current ? `0 0 8px ${EPOCH_COLORS[eid]}66` : "none",
                          }}
                        />
                        <div
                          className="text-[9px] font-mono uppercase text-center"
                          style={{
                            color: current ? EPOCH_COLORS[eid] : done ? EPOCH_COLORS[eid] : "var(--text-muted)",
                            opacity: done || current ? 1 : 0.5,
                            letterSpacing: "0.1em",
                          }}
                        >
                          {EPOCH_ICONS[eid]}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* CTA — open full chapter map */}
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  setMapOpen(true);
                }}
                className="w-full flex items-center justify-center gap-2 py-2 rounded-lg text-xs font-semibold uppercase tracking-wider transition-all hover:scale-[1.01]"
                style={{
                  background: `color-mix(in srgb, ${epochColor} 12%, transparent)`,
                  border: `1px solid color-mix(in srgb, ${epochColor} 35%, transparent)`,
                  color: epochColor,
                }}
              >
                <Map size={14} />
                Открыть полную карту глав
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Full-viewport chapter map drawer (opens when the card itself is clicked) */}
      <ChapterMap open={mapOpen} onClose={() => setMapOpen(false)} />
    </div>
  );
}
