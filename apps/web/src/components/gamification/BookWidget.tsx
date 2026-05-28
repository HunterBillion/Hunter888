"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  BookOpen,
  Phone,
  Shield,
  MagnifyingGlass,
  Trophy,
  Scales,
  FileText,
  CaretRight,
} from "@phosphor-icons/react";
import { api } from "@/lib/api";

/* ── Types ────────────────────────────────────────────────────────── */

interface BookTopic {
  id: string;
  title: string;
  body?: string;
  tags?: string[];
  kind?: string;
  count?: number;
}

interface BookChapter {
  id: string;
  title: string;
  icon: string;
  description: string;
  topics_count: number;
  topics: BookTopic[];
}

interface BookData {
  chapters: BookChapter[];
  total_topics: number;
}

/* ── Icon map ─────────────────────────────────────────────────────── */

const ICON_MAP: Record<string, any> = {
  Phone,
  Shield,
  Search: MagnifyingGlass,
  Trophy,
  Scale: Scales,
  BookOpen,
  FileText,
};

/* ── Kind colors ──────────────────────────────────────────────────── */

const KIND_COLORS: Record<string, string> = {
  opener: "var(--success)",
  objection: "var(--warning)",
  discovery: "var(--accent)",
  closing: "var(--magenta, #d946ef)",
  legal: "var(--gf-xp, #facc15)",
  general: "var(--text-muted)",
};

/* ── Component ────────────────────────────────────────────────────── */

export default function BookWidget() {
  const [data, setData] = useState<BookData | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    api
      .get<BookData>("/book")
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => { console.warn("BookWidget fetch failed:", e); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  if (loading) {
    return (
      <div
        className="rounded-xl p-4 animate-pulse"
        style={{ background: "var(--card-bg)", border: "1px solid var(--input-bg)" }}
      >
        <div className="h-5 w-32 rounded" style={{ background: "var(--input-bg)" }} />
        <div className="mt-3 space-y-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-12 rounded-lg" style={{ background: "var(--input-bg)" }} />
          ))}
        </div>
      </div>
    );
  }

  if (!data || data.chapters.length === 0) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="rounded-xl overflow-hidden"
      style={{
        background: "var(--card-bg)",
        border: "1px solid var(--input-bg)",
      }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 pt-4 pb-2">
        <div className="flex items-center gap-2">
          <BookOpen weight="duotone" size={20} style={{ color: "var(--accent)" }} />
          <h3
            className="font-pixel text-sm uppercase tracking-wider"
            style={{ color: "var(--text-primary)" }}
          >
            Книга знаний
          </h3>
        </div>
        <span
          className="text-xs font-mono"
          style={{ color: "var(--text-muted)" }}
        >
          {data.total_topics} тем
        </span>
      </div>

      {/* Chapters */}
      <div className="px-3 pb-3 space-y-1.5">
        {data.chapters.map((chapter) => {
          const IconComp = ICON_MAP[chapter.icon] || FileText;
          const color = KIND_COLORS[chapter.id] || "var(--text-muted)";
          const isOpen = expanded === chapter.id;

          return (
            <div key={chapter.id}>
              <button
                onClick={() => setExpanded(isOpen ? null : chapter.id)}
                className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors hover:brightness-110"
                style={{
                  background: isOpen ? "var(--input-bg)" : "transparent",
                  textAlign: "left",
                }}
              >
                <div
                  className="shrink-0 w-8 h-8 rounded-md flex items-center justify-center"
                  style={{ background: `${color}20` }}
                >
                  <IconComp weight="duotone" size={16} style={{ color }} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                    {chapter.title}
                  </div>
                  <div className="text-xs truncate" style={{ color: "var(--text-muted)" }}>
                    {chapter.description}
                  </div>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  <span
                    className="text-xs font-mono px-1.5 py-0.5 rounded"
                    style={{
                      color,
                      background: `${color}15`,
                    }}
                  >
                    {chapter.topics_count}
                  </span>
                  <CaretRight
                    size={14}
                    style={{
                      color: "var(--text-muted)",
                      transform: isOpen ? "rotate(90deg)" : "rotate(0deg)",
                      transition: "transform 0.2s",
                    }}
                  />
                </div>
              </button>

              {/* Expanded topics */}
              <AnimatePresence>
                {isOpen && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.2 }}
                    className="overflow-hidden"
                  >
                    <div className="pl-14 pr-3 pb-2 space-y-1">
                      {chapter.topics.slice(0, 8).map((topic, idx) => (
                        <div
                          key={topic.id || idx}
                          className="text-xs py-1.5 px-2 rounded flex items-start gap-2"
                          style={{ color: "var(--text-secondary)" }}
                        >
                          <span style={{ color, opacity: 0.6 }}>•</span>
                          <span>{topic.title}</span>
                          {topic.count && (
                            <span className="ml-auto shrink-0 font-mono" style={{ color: "var(--text-muted)" }}>
                              {topic.count}
                            </span>
                          )}
                        </div>
                      ))}
                      {chapter.topics.length > 8 && (
                        <div className="text-xs py-1 px-2" style={{ color: "var(--text-muted)" }}>
                          +{chapter.topics.length - 8} ещё...
                        </div>
                      )}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          );
        })}
      </div>
    </motion.div>
  );
}
