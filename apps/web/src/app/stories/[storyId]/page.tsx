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
  // 2026-04-18: auto-scroll chat to bottom on new event (user complaint:
  // "когда пишу в чат, нет автоматического скрола вниз").
  const chatEndRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [events.length]);

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
            href="/stories"
            className="inline-flex items-center gap-1.5 text-sm font-medium transition-opacity hover:opacity-80"
            style={{ color: "var(--accent)" }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m15 18-6-6 6-6"/></svg>
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
      <div
        className="flex flex-col min-h-[calc(100vh-64px)] panel-grid-bg"
        style={{
          // 2026-04-18: align with the rest of the app (panel-grid-bg). Old
          // hard-coded dark-only gradient was missing in light theme and not
          // matching /home, /pvp, /training, /clients system styling.
          backgroundImage: `
            radial-gradient(circle at top, var(--accent-muted) 0%, transparent 42%),
            repeating-linear-gradient(0deg, transparent 0, transparent 31px, rgba(107,77,199,0.05) 31px, rgba(107,77,199,0.05) 32px),
            repeating-linear-gradient(90deg, transparent 0, transparent 31px, rgba(107,77,199,0.05) 31px, rgba(107,77,199,0.05) 32px)
          `,
          backgroundColor: "var(--bg-primary)",
        }}
      >
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="px-4 pt-4 pb-4 shrink-0"
        >
          <div className="mx-auto max-w-[900px]">
            {/* macOS Terminal window */}
            <div
              className="overflow-hidden rounded-lg"
              style={{
                background: "rgba(30, 30, 30, 0.95)",
                border: "1px solid rgba(255,255,255,0.1)",
                boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
              }}
            >
              {/* Title bar */}
              <div
                className="flex items-center px-4 py-2.5"
                style={{
                  background: "rgba(50, 50, 50, 0.9)",
                  borderBottom: "1px solid rgba(255,255,255,0.06)",
                }}
              >
                {/* Traffic lights */}
                <div className="flex items-center gap-2 shrink-0">
                  <BackButton href="/stories" label="К портфелю" />
                  <span className="block w-3 h-3 rounded-full" style={{ background: "#ff5f57" }} />
                  <span className="block w-3 h-3 rounded-full" style={{ background: "#febc2e" }} />
                  <span className="block w-3 h-3 rounded-full" style={{ background: "#28c840" }} />
                </div>
                {/* Centered title */}
                <div className="flex-1 text-center">
                  <span className="font-mono text-xs tracking-wide" style={{ color: "var(--text-muted)" }}>
                    Story Control Room — {story.story_name}
                  </span>
                </div>
                {/* Status badge */}
                <span
                  className="text-xs font-mono px-2 py-0.5 rounded shrink-0"
                  style={{
                    background: `${color}15`,
                    color,
                    border: `1px solid ${color}30`,
                  }}
                >
                  {statusLabel}
                </span>
              </div>

              {/* Terminal body */}
              <div className="p-5 font-mono text-xs">
                {/* Description as comment */}
                <div className="mb-4" style={{ color: "var(--text-muted)" }}>
                  <span style={{ color: "rgba(255,255,255,0.25)" }}>// </span>
                  Полная continuity AI-клиента: динамика напряжения, факторы,
                  <br />
                  <span style={{ color: "rgba(255,255,255,0.25)" }}>// </span>
                  последствия, сообщения и действия между звонками.
                </div>

                {/* Data fields */}
                <div className="space-y-1.5 mb-5">
                  <div className="flex items-center gap-2">
                    <span style={{ color: "var(--accent)" }}>$</span>
                    <span style={{ color: "var(--text-muted)" }}>call_progress:</span>
                    <Phone size={11} style={{ color: "var(--text-muted)" }} />
                    <span style={{ color: "var(--text-primary)" }}>
                      {story.current_call_number}/{story.total_calls_planned}
                    </span>
                  </div>
                  {story.tension_curve.length > 0 && (
                    <div className="flex items-center gap-2">
                      <span style={{ color: "var(--accent)" }}>$</span>
                      <span style={{ color: "var(--text-muted)" }}>tension:</span>
                      <Zap size={11} style={{ color: "var(--warning, var(--text-muted))" }} />
                      <span style={{ color: "var(--text-primary)" }}>
                        {(story.tension_curve[story.tension_curve.length - 1] * 10).toFixed(0)}/10
                      </span>
                    </div>
                  )}
                  <div className="flex items-center gap-2">
                    <span style={{ color: "var(--accent)" }}>$</span>
                    <span style={{ color: "var(--text-muted)" }}>events:</span>
                    <Layers3 size={11} style={{ color: "var(--text-muted)" }} />
                    <span style={{ color: "var(--text-primary)" }}>{story.event_count}</span>
                  </div>
                </div>

                {/* Stats grid */}
                <div className="grid grid-cols-2 gap-2 md:grid-cols-4 mb-5">
                  {[
                    { label: "avg_score", value: story.avg_score !== null ? Math.round(story.avg_score) : "—", icon: Trophy },
                    { label: "best_call", value: story.best_score !== null ? Math.round(story.best_score) : "—", icon: Target },
                    { label: "factors", value: story.active_factors.length, icon: Brain },
                    { label: "consequences", value: story.consequences.length, icon: ShieldAlert },
                  ].map((item) => (
                    <div
                      key={item.label}
                      className="rounded-md p-3"
                      style={{
                        background: "rgba(255,255,255,0.03)",
                        border: "1px solid rgba(255,255,255,0.06)",
                      }}
                    >
                      <div className="flex items-center gap-1.5 mb-1.5">
                        <item.icon size={12} style={{ color: "var(--accent)" }} />
                        <span className="uppercase tracking-wider" style={{ color: "var(--text-muted)", fontSize: "14px" }}>
                          {item.label}
                        </span>
                      </div>
                      <div className="text-xl font-semibold" style={{ color: "var(--text-primary)" }}>
                        {item.value}
                      </div>
                    </div>
                  ))}
                </div>

                {/* Progress bar as terminal output */}
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <div className="flex items-center gap-2">
                      <span style={{ color: "var(--accent)" }}>$</span>
                      <span style={{ color: "var(--text-muted)" }}>progress:</span>
                    </div>
                    <span style={{ color: "var(--text-primary)" }}>{progressPct}%</span>
                  </div>
                  <div
                    className="h-1.5 rounded-sm overflow-hidden"
                    style={{ background: "rgba(255,255,255,0.06)" }}
                  >
                    <div
                      className="h-full rounded-sm transition-all duration-500"
                      style={{
                        width: `${Math.max(progressPct, 3)}%`,
                        background: `linear-gradient(90deg, ${color}, var(--accent))`,
                      }}
                    />
                  </div>
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
                {[
                  { key: "event_stream", value: totalEvents, desc: "всех зафиксированных событий" },
                  { key: "between_calls", value: story.between_call_events.length, desc: "изменений поведения клиента" },
                  { key: "pacing", value: story.pacing, desc: "режим развития истории", capitalize: true },
                ].map((stat) => (
                  <div
                    key={stat.key}
                    className="overflow-hidden rounded-lg"
                    style={{
                      background: "rgba(30, 30, 30, 0.95)",
                      border: "1px solid rgba(255,255,255,0.1)",
                    }}
                  >
                    <div
                      className="flex items-center px-2.5 py-1.5"
                      style={{ background: "rgba(50,50,50,0.9)", borderBottom: "1px solid rgba(255,255,255,0.06)" }}
                    >
                      <div className="flex items-center gap-1 shrink-0">
                        <span className="block w-1.5 h-1.5 rounded-full" style={{ background: "#ff5f57" }} />
                        <span className="block w-1.5 h-1.5 rounded-full" style={{ background: "#febc2e" }} />
                        <span className="block w-1.5 h-1.5 rounded-full" style={{ background: "#28c840" }} />
                      </div>
                      <span className="flex-1 text-center text-xs font-mono tracking-wide" style={{ color: "var(--text-muted)" }}>
                        {stat.key}
                      </span>
                    </div>
                    <div className="px-3 py-3 font-mono">
                      <div className={`text-xl font-semibold ${stat.capitalize ? "capitalize" : ""}`} style={{ color: "var(--text-primary)" }}>
                        {stat.value}
                      </div>
                      <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>{stat.desc}</div>
                    </div>
                  </div>
                ))}
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
              {/* Auto-scroll target (2026-04-18) — chatEndRef.scrollIntoView fires on events.length change */}
              <div ref={chatEndRef} aria-hidden />
            </div>

            {/* Side panel: Quick actions — Terminal mini-windows */}
            <div className="w-full shrink-0 space-y-3 lg:w-[300px]">
              {/* Profile Snapshot */}
              <div
                className="overflow-hidden rounded-lg"
                style={{
                  background: "rgba(30, 30, 30, 0.95)",
                  border: "1px solid rgba(255,255,255,0.1)",
                  boxShadow: "0 4px 16px rgba(0,0,0,0.3)",
                }}
              >
                <div
                  className="flex items-center px-3 py-2"
                  style={{ background: "rgba(50,50,50,0.9)", borderBottom: "1px solid rgba(255,255,255,0.06)" }}
                >
                  <div className="flex items-center gap-1.5 shrink-0">
                    <span className="block w-2 h-2 rounded-full" style={{ background: "#ff5f57" }} />
                    <span className="block w-2 h-2 rounded-full" style={{ background: "#febc2e" }} />
                    <span className="block w-2 h-2 rounded-full" style={{ background: "#28c840" }} />
                  </div>
                  <span className="flex-1 text-center text-xs font-mono tracking-wide" style={{ color: "var(--text-muted)" }}>
                    profile_snapshot
                  </span>
                  <div className="w-[34px] shrink-0" />
                </div>
                <div className="px-3 py-3 font-mono text-xs space-y-1.5">
                  <div className="flex items-center gap-2">
                    <span style={{ color: "var(--accent)" }}>$</span>
                    <span style={{ color: "var(--text-muted)" }}>next_twist:</span>
                    <span style={{ color: "var(--text-primary)" }}>{story.next_twist || "—"}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span style={{ color: "var(--accent)" }}>$</span>
                    <span style={{ color: "var(--text-muted)" }}>calls_done:</span>
                    <span style={{ color: "var(--text-primary)" }}>{story.calls_completed}</span>
                  </div>
                </div>
              </div>

              {/* Message form */}
              <div
                className="overflow-hidden rounded-lg"
                style={{
                  background: "rgba(30, 30, 30, 0.95)",
                  border: "1px solid rgba(255,255,255,0.1)",
                  boxShadow: "0 4px 16px rgba(0,0,0,0.3)",
                }}
              >
                <div
                  className="flex items-center px-3 py-2"
                  style={{ background: "rgba(50,50,50,0.9)", borderBottom: "1px solid rgba(255,255,255,0.06)" }}
                >
                  <div className="flex items-center gap-1.5 shrink-0">
                    <span className="block w-2 h-2 rounded-full" style={{ background: "#ff5f57" }} />
                    <span className="block w-2 h-2 rounded-full" style={{ background: "#febc2e" }} />
                    <span className="block w-2 h-2 rounded-full" style={{ background: "#28c840" }} />
                  </div>
                  <span className="flex-1 text-center text-xs font-mono tracking-wide" style={{ color: "var(--text-muted)" }}>
                    send_message
                  </span>
                  <div className="w-[34px] shrink-0" />
                </div>
                <div className="px-3 py-3 font-mono text-xs">
                  <textarea
                    ref={messageInputRef}
                    value={messageText}
                    onChange={(e) => setMessageText(e.target.value)}
                    placeholder="$ echo 'Написать должнику...'"
                    rows={3}
                    className="w-full text-xs font-mono rounded-md p-2 resize-none"
                    style={{
                      background: "rgba(0,0,0,0.3)",
                      color: "var(--text-primary)",
                      border: "1px solid rgba(255,255,255,0.08)",
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
                    className="mt-2 w-full flex items-center justify-center gap-1.5 rounded-md px-3 py-2 text-xs font-mono transition-opacity"
                    style={{
                      background: "var(--accent)",
                      color: "#000",
                      opacity: messageText.trim() && !sending ? 1 : 0.5,
                    }}
                  >
                    {sending ? <Loader2 size={10} className="animate-spin" /> : <Send size={10} />}
                    {sending ? "executing..." : "$ send"}
                  </button>
                </div>
              </div>

              {/* Callback form */}
              <div
                className="overflow-hidden rounded-lg"
                style={{
                  background: "rgba(30, 30, 30, 0.95)",
                  border: "1px solid rgba(255,255,255,0.1)",
                  boxShadow: "0 4px 16px rgba(0,0,0,0.3)",
                }}
              >
                <div
                  className="flex items-center px-3 py-2 cursor-pointer"
                  style={{ background: "rgba(50,50,50,0.9)", borderBottom: "1px solid rgba(255,255,255,0.06)" }}
                  onClick={() => setShowCallbackForm((v) => !v)}
                >
                  <div className="flex items-center gap-1.5 shrink-0">
                    <span className="block w-2 h-2 rounded-full" style={{ background: "#ff5f57" }} />
                    <span className="block w-2 h-2 rounded-full" style={{ background: "#febc2e" }} />
                    <span className="block w-2 h-2 rounded-full" style={{ background: "#28c840" }} />
                  </div>
                  <span className="flex-1 text-center text-xs font-mono tracking-wide" style={{ color: "var(--text-muted)" }}>
                    schedule_callback
                  </span>
                  <ChevronRight
                    size={10}
                    className="transition-transform shrink-0"
                    style={{ color: "var(--text-muted)", transform: showCallbackForm ? "rotate(90deg)" : "rotate(0deg)" }}
                  />
                </div>
                <AnimatePresence>
                  {showCallbackForm && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      className="overflow-hidden"
                    >
                      <div className="px-3 py-3 font-mono text-xs space-y-2">
                        <input
                          type="text"
                          value={callbackDate}
                          onChange={(e) => setCallbackDate(e.target.value)}
                          placeholder="$ date --set '17 марта'"
                          className="w-full text-xs font-mono rounded-md p-2"
                          style={{
                            background: "rgba(0,0,0,0.3)",
                            color: "var(--text-primary)",
                            border: "1px solid rgba(255,255,255,0.08)",
                            outline: "none",
                          }}
                        />
                        <input
                          type="text"
                          value={callbackNote}
                          onChange={(e) => setCallbackNote(e.target.value)}
                          placeholder="$ note 'примечание...'"
                          className="w-full text-xs font-mono rounded-md p-2"
                          style={{
                            background: "rgba(0,0,0,0.3)",
                            color: "var(--text-primary)",
                            border: "1px solid rgba(255,255,255,0.08)",
                            outline: "none",
                          }}
                        />
                        <button
                          onClick={handleScheduleCallback}
                          disabled={!callbackDate.trim() || sending}
                          className="w-full flex items-center justify-center gap-1.5 rounded-md px-3 py-2 text-xs font-mono transition-opacity"
                          style={{
                            background: "var(--warning)",
                            color: "#000",
                            opacity: callbackDate.trim() && !sending ? 1 : 0.5,
                          }}
                        >
                          <Calendar size={10} />
                          $ schedule
                        </button>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              {/* Consequences */}
              {story.consequences.length > 0 && (
                <div
                  className="overflow-hidden rounded-lg"
                  style={{
                    background: "rgba(30, 30, 30, 0.95)",
                    border: "1px solid rgba(255,255,255,0.1)",
                    boxShadow: "0 4px 16px rgba(0,0,0,0.3)",
                  }}
                >
                  <div
                    className="flex items-center px-3 py-2"
                    style={{ background: "rgba(50,50,50,0.9)", borderBottom: "1px solid rgba(255,255,255,0.06)" }}
                  >
                    <div className="flex items-center gap-1.5 shrink-0">
                      <span className="block w-2 h-2 rounded-full" style={{ background: "#ff5f57" }} />
                      <span className="block w-2 h-2 rounded-full" style={{ background: "#febc2e" }} />
                      <span className="block w-2 h-2 rounded-full" style={{ background: "#28c840" }} />
                    </div>
                    <span className="flex-1 text-center text-xs font-mono tracking-wide" style={{ color: "var(--text-muted)" }}>
                      consequences ({story.consequences.length})
                    </span>
                    <div className="w-[34px] shrink-0" />
                  </div>
                  <div className="px-3 py-3 font-mono text-xs space-y-1">
                    {(story.consequences as Array<Record<string, unknown>>).slice(0, 5).map((csq, i) => (
                      <div
                        key={i}
                        className="flex items-center gap-2 p-1.5 rounded-md"
                        style={{ background: "rgba(0,0,0,0.2)" }}
                      >
                        <Zap size={10} style={{ color: "var(--warning)" }} />
                        <span style={{ color: "var(--text-muted)" }}>
                          {String(csq.type || csq.detail || "Последствие")}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Active factors */}
              {story.active_factors.length > 0 && (
                <div
                  className="overflow-hidden rounded-lg"
                  style={{
                    background: "rgba(30, 30, 30, 0.95)",
                    border: "1px solid rgba(255,255,255,0.1)",
                    boxShadow: "0 4px 16px rgba(0,0,0,0.3)",
                  }}
                >
                  <div
                    className="flex items-center px-3 py-2"
                    style={{ background: "rgba(50,50,50,0.9)", borderBottom: "1px solid rgba(255,255,255,0.06)" }}
                  >
                    <div className="flex items-center gap-1.5 shrink-0">
                      <span className="block w-2 h-2 rounded-full" style={{ background: "#ff5f57" }} />
                      <span className="block w-2 h-2 rounded-full" style={{ background: "#febc2e" }} />
                      <span className="block w-2 h-2 rounded-full" style={{ background: "#28c840" }} />
                    </div>
                    <span className="flex-1 text-center text-xs font-mono tracking-wide" style={{ color: "var(--text-muted)" }}>
                      active_factors
                    </span>
                    <div className="w-[34px] shrink-0" />
                  </div>
                  <div className="px-3 py-3 font-mono text-xs space-y-1.5">
                    {(story.active_factors as Array<Record<string, unknown>>).slice(0, 6).map((factor, i) => (
                      <div key={i} className="flex items-center gap-2">
                        <span style={{ color: "var(--accent)" }}>$</span>
                        <span style={{ color: "var(--accent)" }}>
                          {String(factor.factor || factor.name || "factor")}
                        </span>
                        <span style={{ color: "var(--text-muted)" }}>::</span>
                        <span style={{ color: "var(--text-primary)" }}>
                          {Math.round(Number(factor.intensity || 0) * 100)}%
                        </span>
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
