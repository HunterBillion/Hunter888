"use client";

import { useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Phone,
  MessageSquare,
  Zap,
  BookOpen,
  RefreshCw,
  Calendar,
  ChevronDown,
} from "lucide-react";
import type { GameTimelineEvent, GameEventType } from "@/types";
import { GAME_EVENT_LABELS } from "@/types";
import { colorAlpha } from "@/lib/utils";

interface GameTimelineProps {
  events: GameTimelineEvent[];
  loading?: boolean;
  onLoadMore?: () => void;
  hasMore?: boolean;
}

const EVENT_ICONS: Record<GameEventType, typeof Phone> = {
  call: Phone,
  message: MessageSquare,
  consequence: Zap,
  storylet: BookOpen,
  status_change: RefreshCw,
  callback: Calendar,
};

const EVENT_COLORS: Record<GameEventType, string> = {
  call: "var(--event-call)",
  message: "var(--event-message)",
  consequence: "var(--event-consequence)",
  storylet: "var(--event-storylet)",
  status_change: "var(--event-status)",
  callback: "var(--event-callback)",
};

const SOURCE_LABELS: Record<string, string> = {
  manager: "Менеджер",
  ai_client: "AI-клиент",
  game_director: "Director",
  scheduler: "Scheduler",
  memory: "Memory",
  system: "System",
};

function formatTime(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleString("ru-RU", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function GameTimeline({
  events,
  loading,
  onLoadMore,
  hasMore,
}: GameTimelineProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const toggle = useCallback((id: string) => {
    setExpandedId((prev) => (prev === id ? null : id));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <RefreshCw
          size={20}
          className="animate-spin"
          style={{ color: "var(--accent)" }}
        />
      </div>
    );
  }

  if (!events.length) {
    return (
      <div className="text-center py-12">
        <span
          className="text-sm font-mono"
          style={{ color: "var(--text-muted)" }}
        >
          Нет событий
        </span>
      </div>
    );
  }

  return (
    <div className="space-y-1">
      <AnimatePresence initial={false}>
        {events.map((event, i) => {
          const Icon = EVENT_ICONS[event.type] || BookOpen;
          const color = EVENT_COLORS[event.type] || "var(--text-muted)";
          const isExpanded = expandedId === event.id;

          return (
            <motion.div
              key={event.id || i}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ delay: i * 0.03 }}
            >
              <div
                className="flex gap-3 p-3 rounded-lg transition-colors cursor-pointer"
                style={{
                  background: isExpanded
                    ? "var(--bg-secondary)"
                    : "transparent",
                }}
                onClick={() => toggle(event.id)}
              >
                {/* Timeline dot */}
                <div className="flex flex-col items-center pt-0.5">
                  <div
                    className="w-7 h-7 rounded-full flex items-center justify-center shrink-0"
                    style={{
                      background: colorAlpha(color, 8),
                      border: `1.5px solid ${colorAlpha(color, 25)}`,
                    }}
                  >
                    <Icon size={13} style={{ color }} />
                  </div>
                  {i < events.length - 1 && (
                    <div
                      className="w-px flex-1 mt-1"
                      style={{ background: "var(--border-color)" }}
                    />
                  )}
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span
                      className="text-xs font-mono px-1.5 py-0.5 rounded"
                      style={{
                        background: colorAlpha(color, 6),
                        color,
                        border: `1px solid ${colorAlpha(color, 12)}`,
                      }}
                    >
                      {GAME_EVENT_LABELS[event.type]}
                    </span>
                    <span
                      className="text-xs font-mono px-1.5 py-0.5 rounded"
                      style={{
                        background: "rgba(255,255,255,0.06)",
                        color: "var(--text-secondary)",
                        border: "1px solid rgba(255,255,255,0.08)",
                      }}
                    >
                      {SOURCE_LABELS[event.source] || event.source}
                    </span>
                    {event.narrative_date && (
                      <span
                        className="text-xs font-mono"
                        style={{ color: "var(--text-muted)" }}
                      >
                        {event.narrative_date}
                      </span>
                    )}
                    {!event.is_read && (
                      <div
                        className="w-1.5 h-1.5 rounded-full"
                        style={{ background: "var(--accent)" }}
                      />
                    )}
                  </div>

                  <p
                    className="text-[13px] font-medium mt-1 leading-tight"
                    style={{ color: "var(--text-primary)" }}
                  >
                    {event.title}
                  </p>

                  <span
                    className="text-xs font-mono"
                    style={{ color: "var(--text-muted)", opacity: 0.7 }}
                  >
                    {formatTime(event.timestamp)}
                  </span>

                  {/* Expanded content */}
                  <AnimatePresence>
                    {isExpanded && event.content && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.2 }}
                        className="overflow-hidden"
                      >
                        <p
                          className="text-xs mt-2 leading-relaxed whitespace-pre-wrap"
                          style={{ color: "var(--text-muted)" }}
                        >
                          {event.content}
                        </p>
                        {event.payload && Object.keys(event.payload).length > 0 && (
                          <div
                            className="mt-2 p-2 rounded text-xs font-mono"
                            style={{
                              background: "var(--input-bg)",
                              color: "var(--text-muted)",
                            }}
                          >
                            {Object.entries(event.payload)
                              .filter(([k]) => !["story_name"].includes(k))
                              .slice(0, 5)
                              .map(([k, v]) => (
                                <div key={k}>
                                  {k}: {typeof v === "object" ? JSON.stringify(v) : String(v)}
                                </div>
                              ))}
                          </div>
                        )}
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>

                {/* Expand icon */}
                {event.content && (
                  <ChevronDown
                    size={14}
                    className="shrink-0 mt-1 transition-transform"
                    style={{
                      color: "var(--text-muted)",
                      transform: isExpanded ? "rotate(180deg)" : "rotate(0deg)",
                    }}
                  />
                )}
              </div>
            </motion.div>
          );
        })}
      </AnimatePresence>

      {/* Load more */}
      {hasMore && onLoadMore && (
        <button
          onClick={onLoadMore}
          className="w-full text-center py-3 text-xs font-mono transition-colors"
          style={{ color: "var(--accent)" }}
        >
          Загрузить ещё...
        </button>
      )}
    </div>
  );
}
