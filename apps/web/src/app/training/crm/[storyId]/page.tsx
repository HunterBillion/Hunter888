"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
    Loader2,
    Send,
    Calendar,
  RefreshCw,
    BookOpen,
    Phone,
    Zap,
    ChevronRight,
    Trophy,
    Brain,
    Activity,
    Layers3,
    Target,
    ShieldAlert,
  } from "lucide-react";
import Link from "next/link";
import { BackButton } from "@/components/ui/BackButton";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import AuthLayout from "@/components/layout/AuthLayout";
import { GameTimeline } from "@/components/game-crm/GameTimeline";
import { useWebSocket } from "@/hooks/useWebSocket";
import type {
  GameStoryDetail,
  GameTimelineEvent,
  GameClientStatus,
} from "@/types";
import { GAME_STATUS_LABELS, GAME_STATUS_COLORS } from "@/types";
import { useNotificationStore } from "@/stores/useNotificationStore";
import { logger } from "@/lib/logger";

export default function GameClientPanelPage() {
  const { storyId } = useParams<{ storyId: string }>();

  const [story, setStory] = useState<GameStoryDetail | null>(null);
  const [events, setEvents] = useState<GameTimelineEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [eventsLoading, setEventsLoading] = useState(true);
  const [totalEvents, setTotalEvents] = useState(0);

  // Message & callback state
  const [messageText, setMessageText] = useState("");
  const [callbackDate, setCallbackDate] = useState("");
  const [callbackNote, setCallbackNote] = useState("");
  const [showCallbackForm, setShowCallbackForm] = useState(false);
  const [sending, setSending] = useState(false);

  const messageInputRef = useRef<HTMLTextAreaElement>(null);

  const { sendMessage, connectionState } = useWebSocket({
    path: "/ws/game-crm",
    autoConnect: true,
    onMessage: (msg) => {
      switch (msg.type) {
        case "story.subscribed":
          break;
        case "game_crm.message.created": {
          const managerEvent = msg.data?.manager_event as GameTimelineEvent | undefined;
          const aiEvent = msg.data?.ai_event as GameTimelineEvent | undefined;
          setEvents((prev) => [aiEvent, managerEvent, ...prev].filter(Boolean) as GameTimelineEvent[]);
          setTotalEvents((prev) => prev + (managerEvent ? 1 : 0) + (aiEvent ? 1 : 0));
          setSending(false);
          break;
        }
        case "error":
          setSending(false);
          break;
      }
    },
  });

  // ── Fetch story detail ──
  const fetchStory = useCallback(async () => {
    try {
      const data: GameStoryDetail = await api.get(`/game/clients/stories/${storyId}`);
      setStory(data);
    } catch (err) {
      useNotificationStore.getState().addToast({
        title: "Ошибка",
        body: "Не удалось загрузить историю клиента.",
        type: "error",
      });
      logger.error("Failed to load story:", err);
    }
    setLoading(false);
  }, [storyId]);

  // ── Fetch timeline ──
  const fetchTimeline = useCallback(async (append = false) => {
    try {
      const offset = append ? events.length : 0;
      const data = await api.get(
        `/game/clients/stories/${storyId}/timeline?limit=30&offset=${offset}`,
      );
      if (append) {
        setEvents((prev) => [...prev, ...(data.items || [])]);
      } else {
        setEvents(data.items || []);
      }
      setTotalEvents(data.total || 0);
    } catch (err) {
      logger.error("Failed to load timeline:", err);
    }
    setEventsLoading(false);
  }, [storyId, events.length]);

  useEffect(() => {
    fetchStory();
    fetchTimeline();
  }, [fetchStory, fetchTimeline]);

  useEffect(() => {
    if (connectionState === "connected" && storyId) {
      sendMessage({ type: "story.subscribe", data: { story_id: storyId } });
    }
  }, [connectionState, storyId, sendMessage]);

  // ── Send message ──
  const handleSendMessage = useCallback(async () => {
    if (!messageText.trim() || sending) return;
    setSending(true);
    const trimmed = messageText.trim();
    try {
      if (connectionState === "connected") {
        sendMessage({
          type: "story.message",
          data: {
            story_id: storyId,
            content: trimmed,
          },
        });
      } else {
        await api.post(`/game/clients/stories/${storyId}/message`, {
          content: trimmed,
        });
        setEventsLoading(true);
        await fetchTimeline();
        setSending(false);
      }
      setMessageText("");
    } catch (err) {
      useNotificationStore.getState().addToast({
        title: "Ошибка отправки",
        body: "Сообщение не отправлено. Проверьте соединение.",
        type: "error",
      });
      logger.error("Failed to send message:", err);
      setSending(false);
    }
  }, [messageText, storyId, sending, fetchTimeline, connectionState, sendMessage]);

  // ── Schedule callback ──
  const handleScheduleCallback = useCallback(async () => {
    if (!callbackDate.trim() || sending) return;
    setSending(true);
    try {
      await api.post(`/game/clients/stories/${storyId}/callback`, {
        scheduled_for: callbackDate.trim(),
        note: callbackNote.trim() || null,
      });
      setCallbackDate("");
      setCallbackNote("");
      setShowCallbackForm(false);
      setEventsLoading(true);
      await fetchTimeline();
    } catch (err) {
      useNotificationStore.getState().addToast({
        title: "Ошибка",
        body: "Не удалось запланировать звонок.",
        type: "error",
      });
      logger.error("Failed to schedule callback:", err);
    }
    setSending(false);
  }, [callbackDate, callbackNote, storyId, sending, fetchTimeline]);

  // ── Mark events read ──
  useEffect(() => {
    if (events.length > 0 && storyId) {
      const unread = events.filter((e) => !e.is_read).map((e) => e.id);
      if (unread.length > 0) {
        api.post(`/game/clients/stories/${storyId}/read`, { event_ids: unread }).catch((err) => { logger.error("Failed to mark events as read:", err); });
      }
    }
  }, [events, storyId]);

  if (loading) {
    return (
      <AuthLayout>
        <div className="flex items-center justify-center h-[calc(100vh-64px)]">
          <Loader2 size={24} className="animate-spin" style={{ color: "var(--accent)" }} />
        </div>
      </AuthLayout>
    );
  }

  if (!story) {
    return (
      <AuthLayout>
        <div className="flex flex-col items-center justify-center h-[calc(100vh-64px)] gap-3">
          <span className="text-sm font-mono" style={{ color: "var(--text-muted)" }}>
            История не найдена
          </span>
          <Link
            href="/training/crm"
            className="text-xs font-mono underline"
            style={{ color: "var(--accent)" }}
          >
            Назад
          </Link>
        </div>
      </AuthLayout>
    );
  }

  const color = GAME_STATUS_COLORS[story.game_status] || "var(--text-muted)";
  const statusLabel = GAME_STATUS_LABELS[story.game_status] || story.game_status;
  const progressPct = story.total_calls_planned > 0
    ? Math.round((story.current_call_number / story.total_calls_planned) * 100)
    : 0;

  return (
    <AuthLayout>
      <div className="flex flex-col min-h-[calc(100vh-64px)] bg-[radial-gradient(circle_at_top,rgba(99,102,241,0.15),transparent_32%),linear-gradient(180deg,#040405_0%,#09090c_55%,#0b0b0f_100%)]">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="px-4 pt-4 pb-4 shrink-0"
        >
          <div className="mx-auto max-w-[900px]">
            <div className="overflow-hidden rounded-[30px] border p-6" style={{ background: "linear-gradient(180deg, rgba(9,9,11,0.96), rgba(14,14,18,0.94))", borderColor: "rgba(255,255,255,0.08)" }}>
              <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
                <div className="max-w-2xl">
                  <div className="flex items-center gap-3 mb-3">
                    <BackButton href="/training/crm" label="К историям" />
                    <div className="flex h-12 w-12 items-center justify-center rounded-2xl" style={{ background: `${color}18`, border: `1px solid ${color}30` }}>
                      <BookOpen size={18} style={{ color }} />
                    </div>
                    <div>
                      <div className="font-mono text-xs uppercase tracking-[0.28em]" style={{ color: "var(--accent)" }}>
                        Story Control Room
                      </div>
                      <h1 className="font-display text-2xl font-bold tracking-[0.08em]" style={{ color: "var(--text-primary)" }}>
                        {story.story_name}
                      </h1>
                    </div>
                    <span
                      className="text-xs font-mono px-2 py-0.5 rounded-full"
                      style={{
                        background: `${color}15`,
                        color,
                        border: `1px solid ${color}30`,
                      }}
                    >
                      {statusLabel}
                    </span>
                  </div>

                  <p className="text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                    Полная continuity AI-клиента: динамика напряжения, факторы, последствия, сообщения и действия между звонками. Это канонический профиль клиента, а не отдельный call-log.
                  </p>

                  <div className="mt-4 flex flex-wrap gap-3">
                    <span className="flex items-center gap-1 text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                      <Phone size={11} />
                      Звонок {story.current_call_number}/{story.total_calls_planned}
                    </span>
                    {story.tension_curve.length > 0 && (
                      <span className="flex items-center gap-1 text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                        <Zap size={11} />
                        Напряжение: {(story.tension_curve[story.tension_curve.length - 1] * 10).toFixed(0)}/10
                      </span>
                    )}
                    <span className="flex items-center gap-1 text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                      <Layers3 size={11} />
                      Событий: {story.event_count}
                    </span>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3 md:min-w-[320px]">
                  {[
                    { label: "Средний балл", value: story.avg_score !== null ? Math.round(story.avg_score) : "—", icon: Trophy },
                    { label: "Лучший звонок", value: story.best_score !== null ? Math.round(story.best_score) : "—", icon: Target },
                    { label: "Факторы", value: story.active_factors.length, icon: Brain },
                    { label: "Последствия", value: story.consequences.length, icon: ShieldAlert },
                  ].map((item) => (
                    <div key={item.label} className="rounded-2xl p-4" style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)" }}>
                      <item.icon size={14} style={{ color: "var(--accent)" }} />
                      <div className="mt-2 text-2xl font-semibold" style={{ color: "var(--text-primary)" }}>{item.value}</div>
                      <div className="font-mono text-xs uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>{item.label}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="mt-5">
                <div className="mb-2 flex items-center justify-between text-xs font-mono uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                  <span>Прогресс истории</span>
                  <span>{progressPct}%</span>
                </div>
                <div className="h-2 rounded-full overflow-hidden" style={{ background: "rgba(255,255,255,0.06)" }}>
                  <div className="h-full rounded-full" style={{ width: `${Math.max(progressPct, 3)}%`, background: `linear-gradient(90deg, ${color}, rgba(255,255,255,0.92))` }} />
                </div>
              </div>
            </div>
          </div>
        </motion.div>

        {/* Main content: Timeline + Actions */}
        <div className="flex-1 overflow-y-auto px-4 py-4">
          <div className="mx-auto max-w-[900px] flex flex-col gap-4 lg:flex-row">
            {/* Timeline (main area) */}
            <div className="flex-1 min-w-0">
              <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
                <div className="rounded-2xl p-4" style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)" }}>
                  <div className="font-mono text-xs uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>Поток истории</div>
                  <div className="mt-2 text-xl font-semibold" style={{ color: "var(--text-primary)" }}>{totalEvents}</div>
                  <div className="text-xs" style={{ color: "var(--text-secondary)" }}>всех зафиксированных событий</div>
                </div>
                <div className="rounded-2xl p-4" style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)" }}>
                  <div className="font-mono text-xs uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>Между звонками</div>
                  <div className="mt-2 text-xl font-semibold" style={{ color: "var(--text-primary)" }}>{story.between_call_events.length}</div>
                  <div className="text-xs" style={{ color: "var(--text-secondary)" }}>изменений поведения клиента</div>
                </div>
                <div className="rounded-2xl p-4" style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)" }}>
                  <div className="font-mono text-xs uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>Темп</div>
                  <div className="mt-2 text-xl font-semibold capitalize" style={{ color: "var(--text-primary)" }}>{story.pacing}</div>
                  <div className="text-xs" style={{ color: "var(--text-secondary)" }}>режим развития истории</div>
                </div>
              </div>

              <div className="flex items-center justify-between mb-3">
                <span
                  className="text-xs font-mono font-semibold uppercase tracking-wider"
                  style={{ color: "var(--text-muted)" }}
                >
                  Таймлайн ({totalEvents})
                </span>
                <button
                  onClick={() => { setEventsLoading(true); fetchTimeline(); }}
                  className="text-xs font-mono flex items-center gap-1"
                  style={{ color: "var(--text-muted)" }}
                >
                  <RefreshCw size={10} />
                  Обновить
                </button>
              </div>
              <GameTimeline
                events={events}
                loading={eventsLoading}
                hasMore={events.length < totalEvents}
                onLoadMore={() => fetchTimeline(true)}
              />
            </div>

            {/* Side panel: Quick actions */}
            <div className="w-full shrink-0 space-y-3 lg:w-[300px]">
              <div
                className="rounded-2xl p-4"
                style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)" }}
              >
                <span className="text-xs font-mono font-semibold uppercase tracking-wider block mb-2" style={{ color: "var(--text-muted)" }}>
                  Profile Snapshot
                </span>
                <div className="space-y-2 text-xs" style={{ color: "var(--text-secondary)" }}>
                  <div className="flex items-center justify-between">
                    <span>Следующий твист</span>
                    <span style={{ color: "var(--text-primary)" }}>{story.next_twist || "—"}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span>Завершённых звонков</span>
                    <span style={{ color: "var(--text-primary)" }}>{story.calls_completed}</span>
                  </div>
                </div>
              </div>

              {/* Message form */}
              <div
                className="rounded-2xl p-4"
                style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)" }}
              >
                <span
                  className="text-xs font-mono font-semibold uppercase tracking-wider block mb-2"
                  style={{ color: "var(--text-muted)" }}
                >
                  Сообщение AI-клиенту
                </span>
                <textarea
                  ref={messageInputRef}
                  value={messageText}
                  onChange={(e) => setMessageText(e.target.value)}
                  placeholder="Написать должнику и проверить его реакцию..."
                  rows={3}
                  className="w-full text-xs font-mono rounded-lg p-2 resize-none"
                  style={{
                    background: "var(--input-bg)",
                    color: "var(--text-primary)",
                    border: "1px solid var(--border-color)",
                    outline: "none",
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                      handleSendMessage();
                    }
                  }}
                />
                <button
                  onClick={handleSendMessage}
                  disabled={!messageText.trim() || sending}
                  className="mt-2 w-full flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-xs font-mono transition-opacity"
                  style={{
                    background: "var(--accent)",
                    color: "#000",
                    opacity: messageText.trim() && !sending ? 1 : 0.5,
                  }}
                >
                  {sending ? <Loader2 size={10} className="animate-spin" /> : <Send size={10} />}
                  {sending ? "Диалог..." : "Отправить"}
                </button>
              </div>

              {/* Callback form */}
              <div
                className="rounded-2xl p-4"
                style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)" }}
              >
                <button
                  onClick={() => setShowCallbackForm((v) => !v)}
                  className="w-full flex items-center justify-between text-xs font-mono font-semibold uppercase tracking-wider"
                  style={{ color: "var(--text-muted)" }}
                >
                  Обратный звонок
                  <ChevronRight
                    size={12}
                    className="transition-transform"
                    style={{ transform: showCallbackForm ? "rotate(90deg)" : "rotate(0deg)" }}
                  />
                </button>
                <AnimatePresence>
                  {showCallbackForm && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      className="overflow-hidden"
                    >
                      <div className="mt-2 space-y-2">
                        <input
                          type="text"
                          value={callbackDate}
                          onChange={(e) => setCallbackDate(e.target.value)}
                          placeholder="Дата (напр. 17 марта)"
                          className="w-full text-xs font-mono rounded-lg p-2"
                          style={{
                            background: "var(--input-bg)",
                            color: "var(--text-primary)",
                            border: "1px solid var(--border-color)",
                            outline: "none",
                          }}
                        />
                        <input
                          type="text"
                          value={callbackNote}
                          onChange={(e) => setCallbackNote(e.target.value)}
                          placeholder="Примечание (опционально)"
                          className="w-full text-xs font-mono rounded-lg p-2"
                          style={{
                            background: "var(--input-bg)",
                            color: "var(--text-primary)",
                            border: "1px solid var(--border-color)",
                            outline: "none",
                          }}
                        />
                        <button
                          onClick={handleScheduleCallback}
                          disabled={!callbackDate.trim() || sending}
                          className="w-full flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-xs font-mono transition-opacity"
                          style={{
                            background: "var(--warning)",
                            color: "#000",
                            opacity: callbackDate.trim() && !sending ? 1 : 0.5,
                          }}
                        >
                          <Calendar size={10} />
                          Запланировать
                        </button>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              {/* Story info */}
              {story.consequences.length > 0 && (
                <div
                  className="rounded-2xl p-4"
                  style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)" }}
                >
                  <span
                    className="text-xs font-mono font-semibold uppercase tracking-wider block mb-2"
                    style={{ color: "var(--text-muted)" }}
                  >
                    Последствия ({story.consequences.length})
                  </span>
                  <div className="space-y-1">
                    {(story.consequences as Array<Record<string, unknown>>).slice(0, 5).map((csq, i) => (
                      <div
                        key={i}
                        className="text-xs font-mono p-1.5 rounded"
                        style={{
                          background: "var(--input-bg)",
                          color: "var(--text-muted)",
                        }}
                      >
                        <span style={{ color: "var(--warning)" }}>⚡</span>{" "}
                        {String(csq.type || csq.detail || "Последствие")}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {story.active_factors.length > 0 && (
                <div
                  className="rounded-2xl p-4"
                  style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)" }}
                >
                  <span className="text-xs font-mono font-semibold uppercase tracking-wider block mb-2" style={{ color: "var(--text-muted)" }}>
                    Активные факторы
                  </span>
                  <div className="space-y-2">
                    {(story.active_factors as Array<Record<string, unknown>>).slice(0, 6).map((factor, i) => (
                      <div key={i} className="rounded-xl px-3 py-2 text-xs" style={{ background: "var(--input-bg)", color: "var(--text-secondary)" }}>
                        <div className="font-mono text-xs uppercase tracking-wider" style={{ color: "var(--accent)" }}>
                          {String(factor.factor || factor.name || "factor")}
                        </div>
                        <div className="mt-1">Интенсивность: {Math.round(Number(factor.intensity || 0) * 100)}%</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </AuthLayout>
  );
}
