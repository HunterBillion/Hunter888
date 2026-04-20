"use client";

/**
 * ChapterMap — right-side drawer (~50% viewport) showing the full 12-chapter
 * journey as a board-game-style vertical path. Opens from ChapterProgress.
 *
 * Data source: GET /api/story/chapters — returns all 12 chapters with
 * per-user flags (is_current / is_completed / is_locked). Epoch grouping is
 * derived from chapter.epoch. We DON'T invent state on the client — every
 * lock / unlock / current marker comes from the backend, so the map is
 * always in sync with the actual game progress.
 */

import { useEffect, useState, useCallback } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import { X, Lock, Check, MapPin, BookOpen, Star, Sword } from "lucide-react";
import { api } from "@/lib/api";
import ChapterMapDecor, { EPOCH_PALETTES, type EpochId } from "./ChapterMapDecor";

type MapChapter = {
  id: number;
  epoch: number;
  epoch_name: string;
  code: string;
  name: string;
  narrative_intro: string;
  is_current: boolean;
  is_completed: boolean;
  is_locked: boolean;
  unlock_level: number;
  unlock_sessions: number;
  unlock_score_threshold: number;
  unlocked_archetypes: string[];
  unlocked_features: string[];
  max_difficulty: number;
};

const EPOCH_COLORS: Record<number, string> = {
  1: "var(--success)",
  2: "var(--warning)",
  3: "var(--accent)",
  4: "#A855F7",
};

const EPOCH_ROMAN: Record<number, string> = {
  1: "I",
  2: "II",
  3: "III",
  4: "IV",
};

interface ChapterMapProps {
  open: boolean;
  onClose: () => void;
}

export default function ChapterMap({ open, onClose }: ChapterMapProps) {
  const [chapters, setChapters] = useState<MapChapter[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeChapter, setActiveChapter] = useState<number | null>(null);

  // Fetch once on first open, then keep the data around (chapters rarely
  // change mid-session — only on advancement, which triggers a reload via
  // the parent card's re-render).
  useEffect(() => {
    if (!open || chapters) return;
    let cancelled = false;
    api
      .get<{ chapters: MapChapter[] }>("/story/chapters")
      .then((data) => {
        if (cancelled) return;
        setChapters(data.chapters);
        const curr = data.chapters.find((c) => c.is_current);
        if (curr) setActiveChapter(curr.id);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "Не удалось загрузить карту");
      });
    return () => {
      cancelled = true;
    };
  }, [open, chapters]);

  // Close on Esc.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  // Prevent body scroll while drawer is open.
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  const handleBackdrop = useCallback(
    (e: React.MouseEvent) => {
      if (e.target === e.currentTarget) onClose();
    },
    [onClose],
  );

  if (typeof document === "undefined") return null;

  // Group chapters by epoch for visual sections.
  const byEpoch = new Map<number, MapChapter[]>();
  if (chapters) {
    for (const c of chapters) {
      const arr = byEpoch.get(c.epoch) ?? [];
      arr.push(c);
      byEpoch.set(c.epoch, arr);
    }
  }
  const active = chapters?.find((c) => c.id === activeChapter) ?? null;

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          key="chapter-map-backdrop"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
          onClick={handleBackdrop}
          className="fixed inset-0 z-[80] flex justify-end"
          style={{ background: "rgba(0,0,0,0.55)", backdropFilter: "blur(3px)" }}
        >
          <motion.aside
            key="chapter-map-panel"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "tween", ease: "easeOut", duration: 0.35 }}
            className="h-full w-full md:w-[50vw] max-w-[720px] flex flex-col"
            style={{
              background: "var(--bg-primary)",
              borderLeft: "1px solid var(--border-color)",
              boxShadow: "-8px 0 32px rgba(0,0,0,0.4)",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div
              className="flex items-center justify-between p-4 border-b"
              style={{ borderColor: "var(--border-color)" }}
            >
              <div>
                <div
                  className="text-[14px] font-pixel uppercase tracking-wider"
                  style={{ color: "var(--accent)", letterSpacing: "0.18em" }}
                >
                  Путь Охотника
                </div>
                <div
                  className="text-xl font-bold mt-0.5"
                  style={{ color: "var(--text-primary)" }}
                >
                  Карта глав
                </div>
              </div>
              <button
                onClick={onClose}
                aria-label="Закрыть карту"
                className="p-2 rounded-md hover:bg-[var(--bg-secondary)] transition"
                style={{ color: "var(--text-muted)" }}
              >
                <X size={18} />
              </button>
            </div>

            {/* Body */}
            <div className="flex-1 overflow-y-auto">
              {error && (
                <div className="p-6 text-sm" style={{ color: "var(--danger, #ff5f57)" }}>
                  {error}
                </div>
              )}
              {!chapters && !error && (
                <div
                  className="p-6 text-sm text-center"
                  style={{ color: "var(--text-muted)" }}
                >
                  Загружаю карту…
                </div>
              )}
              {chapters && (
                <div className="flex flex-col">
                  {[1, 2, 3, 4].map((eid) => {
                    const chs = byEpoch.get(eid) ?? [];
                    if (chs.length === 0) return null;
                    const color = EPOCH_COLORS[eid];
                    const epochName = chs[0].epoch_name;
                    const epochCompleted = chs.every((c) => c.is_completed);
                    const epochLocked = chs.every((c) => c.is_locked);

                    const palette = EPOCH_PALETTES[eid as EpochId];
                    return (
                      <section
                        key={eid}
                        className="relative px-6 py-6"
                        style={{
                          minHeight: 280,
                          background: epochLocked
                            ? `linear-gradient(180deg, color-mix(in srgb, var(--bg-secondary) 90%, transparent) 0%, var(--bg-primary) 100%)`
                            : `linear-gradient(180deg, color-mix(in srgb, ${palette.sky} 14%, var(--bg-primary)) 0%, color-mix(in srgb, ${palette.ground} 12%, var(--bg-primary)) 100%)`,
                        }}
                      >
                        {/* Pixel-art landscape backdrop (trees/stones/obelisks
                            per epoch palette). Absolute, behind content. */}
                        <ChapterMapDecor
                          epoch={eid as EpochId}
                          locked={epochLocked}
                        />
                        <div className="relative">
                        {/* Epoch divider */}
                        <div className="flex items-center gap-3 mb-4">
                          <span
                            className="w-10 h-10 rounded-lg flex items-center justify-center font-bold text-white text-base flex-shrink-0"
                            style={{
                              background: epochLocked
                                ? "var(--bg-tertiary)"
                                : `linear-gradient(135deg, ${color} 0%, color-mix(in srgb, ${color} 60%, #000) 100%)`,
                              boxShadow: epochLocked
                                ? "none"
                                : `0 0 12px color-mix(in srgb, ${color} 40%, transparent)`,
                              opacity: epochLocked ? 0.4 : 1,
                            }}
                          >
                            {EPOCH_ROMAN[eid]}
                          </span>
                          <div className="flex-1">
                            <div
                              className="text-[13px] font-pixel uppercase tracking-wider"
                              style={{
                                color: epochLocked ? "var(--text-muted)" : color,
                                letterSpacing: "0.18em",
                              }}
                            >
                              Эпоха {EPOCH_ROMAN[eid]}
                            </div>
                            <div
                              className="text-base font-bold mt-0.5"
                              style={{
                                color: epochLocked
                                  ? "var(--text-muted)"
                                  : "var(--text-primary)",
                              }}
                            >
                              {epochName}
                            </div>
                          </div>
                          {epochCompleted && (
                            <span
                              className="text-[11px] font-bold uppercase tracking-wider rounded px-2 py-1"
                              style={{
                                background: "color-mix(in srgb, var(--success) 15%, transparent)",
                                color: "var(--success)",
                              }}
                            >
                              Пройдена
                            </span>
                          )}
                          {epochLocked && (
                            <span
                              className="text-[11px] font-bold uppercase tracking-wider rounded px-2 py-1 flex items-center gap-1"
                              style={{
                                background: "var(--bg-secondary)",
                                color: "var(--text-muted)",
                              }}
                            >
                              <Lock size={11} /> Закрыта
                            </span>
                          )}
                        </div>

                        {/* Path: dashed vertical line + circular nodes */}
                        <ol className="relative pl-6">
                          <span
                            aria-hidden
                            className="absolute left-[13px] top-3 bottom-3 border-l-2 border-dashed"
                            style={{
                              borderColor: epochLocked
                                ? "var(--bg-tertiary)"
                                : `color-mix(in srgb, ${color} 35%, transparent)`,
                            }}
                          />
                          {chs.map((c) => {
                            const isActive = c.id === activeChapter;
                            return (
                              <li key={c.id} className="relative mb-3 last:mb-0">
                                {/* Node marker */}
                                <span
                                  aria-hidden
                                  className="absolute -left-6 top-2 w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-bold"
                                  style={{
                                    background: c.is_completed
                                      ? color
                                      : c.is_current
                                      ? `radial-gradient(circle, ${color} 0%, color-mix(in srgb, ${color} 60%, #000) 100%)`
                                      : "var(--bg-secondary)",
                                    border: `2px solid ${
                                      c.is_locked
                                        ? "var(--bg-tertiary)"
                                        : color
                                    }`,
                                    color: c.is_locked
                                      ? "var(--text-muted)"
                                      : c.is_completed || c.is_current
                                      ? "white"
                                      : color,
                                    boxShadow: c.is_current
                                      ? `0 0 0 4px color-mix(in srgb, ${color} 20%, transparent), 0 0 14px color-mix(in srgb, ${color} 60%, transparent)`
                                      : "none",
                                  }}
                                >
                                  {c.is_completed ? (
                                    <Check size={12} strokeWidth={3} />
                                  ) : c.is_locked ? (
                                    <Lock size={11} />
                                  ) : (
                                    c.id
                                  )}
                                </span>

                                {/* Current-chapter indicator */}
                                {c.is_current && (
                                  <div
                                    className="absolute -left-8 -top-5 text-[12px] font-pixel uppercase tracking-wider flex items-center gap-1"
                                    style={{ color, letterSpacing: "0.16em" }}
                                  >
                                    <MapPin size={13} />
                                    Ты здесь
                                  </div>
                                )}

                                {/* Clickable chapter card */}
                                <button
                                  onClick={() => setActiveChapter(c.id)}
                                  disabled={c.is_locked}
                                  className="w-full text-left rounded-lg border p-3 transition disabled:cursor-not-allowed"
                                  style={{
                                    background: isActive
                                      ? `color-mix(in srgb, ${color} 10%, var(--bg-secondary))`
                                      : "var(--bg-secondary)",
                                    borderColor: isActive
                                      ? color
                                      : c.is_locked
                                      ? "var(--bg-tertiary)"
                                      : "var(--border-color)",
                                    opacity: c.is_locked ? 0.55 : 1,
                                  }}
                                >
                                  <div className="flex items-baseline justify-between gap-2">
                                    <div
                                      className="text-[15px] font-semibold truncate"
                                      style={{
                                        color: c.is_locked
                                          ? "var(--text-muted)"
                                          : "var(--text-primary)",
                                      }}
                                    >
                                      Глава {c.id}: {c.name}
                                    </div>
                                    {c.is_current && (
                                      <span
                                        className="text-[12px] font-pixel uppercase tracking-wider shrink-0"
                                        style={{ color, letterSpacing: "0.16em" }}
                                      >
                                        Текущая
                                      </span>
                                    )}
                                  </div>
                                  {!c.is_locked && c.narrative_intro && (
                                    <div
                                      className="mt-1 text-xs leading-relaxed line-clamp-2"
                                      style={{ color: "var(--text-secondary)" }}
                                    >
                                      {c.narrative_intro}
                                    </div>
                                  )}
                                  {c.is_locked && (
                                    <div
                                      className="mt-1 text-xs"
                                      style={{ color: "var(--text-muted)" }}
                                    >
                                      Откроется на уровне {c.unlock_level}
                                      {c.unlock_sessions > 0 &&
                                        ` · ${c.unlock_sessions} сессий`}
                                    </div>
                                  )}
                                </button>
                              </li>
                            );
                          })}
                        </ol>
                        </div>
                      </section>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Active chapter detail footer */}
            {active && !active.is_locked && (
              <motion.div
                initial={{ y: 8, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                transition={{ duration: 0.2 }}
                className="border-t p-4 space-y-2"
                style={{
                  borderColor: "var(--border-color)",
                  background: "var(--bg-secondary)",
                }}
              >
                <div
                  className="text-[13px] font-pixel uppercase tracking-wider"
                  style={{
                    color: EPOCH_COLORS[active.epoch],
                    letterSpacing: "0.18em",
                  }}
                >
                  Глава {active.id} · Эпоха {EPOCH_ROMAN[active.epoch]}
                </div>
                <div
                  className="text-lg font-bold"
                  style={{ color: "var(--text-primary)" }}
                >
                  {active.name}
                </div>
                <p
                  className="text-[13px] leading-relaxed"
                  style={{ color: "var(--text-secondary)" }}
                >
                  {active.narrative_intro}
                </p>
                <div className="flex flex-wrap gap-3 text-[13px] pt-1">
                  <span
                    className="flex items-center gap-1"
                    style={{ color: "var(--text-muted)" }}
                  >
                    <Star size={12} /> Сложность до {active.max_difficulty}/10
                  </span>
                  {active.unlocked_archetypes.length > 0 && (
                    <span
                      className="flex items-center gap-1"
                      style={{ color: "var(--text-muted)" }}
                    >
                      <Sword size={12} /> {active.unlocked_archetypes.length} архетип(ов)
                    </span>
                  )}
                  {active.unlocked_features.length > 0 && (
                    <span
                      className="flex items-center gap-1"
                      style={{ color: "var(--text-muted)" }}
                    >
                      <BookOpen size={12} /> {active.unlocked_features.length} фич
                    </span>
                  )}
                </div>
              </motion.div>
            )}
          </motion.aside>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
