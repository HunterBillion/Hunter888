"use client";

import { useState, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import { Check, CheckCheck, Loader2, Inbox } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import AuthLayout from "@/components/layout/AuthLayout";
import { EmptyState } from "@/components/ui/EmptyState";
import type { AppNotification } from "@/types";
import { logger } from "@/lib/logger";

type TabFilter = "all" | "unread";

export default function NotificationsPage() {
  useAuth();
  const [items, setItems] = useState<AppNotification[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<TabFilter>("all");
  const [unreadCount, setUnreadCount] = useState(0);

  const fetchNotifications = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get("/notifications");
      const all: AppNotification[] = data.items || [];
      setUnreadCount(data.unread_count || 0);
      setItems(tab === "unread" ? all.filter((n) => !n.read_at) : all);
    } catch (err) { logger.error("Failed to fetch notifications:", err); }
    setLoading(false);
  }, [tab]);

  useEffect(() => { fetchNotifications(); }, [fetchNotifications]);

  const markRead = async (id: string) => {
    try {
      await api.post(`/notifications/${id}/read`, {});
      setItems((prev) => prev.map((n) => n.id === id ? { ...n, read_at: new Date().toISOString() } : n));
      setUnreadCount((prev) => Math.max(0, prev - 1));
    } catch { /* ignore */ }
  };

  const markAllRead = async () => {
    try {
      await api.post("/notifications/read-all", {});
      setItems((prev) => prev.map((n) => ({ ...n, read_at: new Date().toISOString() })));
      setUnreadCount(0);
    } catch { /* ignore */ }
  };

  const formatDate = (iso: string) => {
    const d = new Date(iso);
    const now = new Date();
    const diff = now.getTime() - d.getTime();
    const mins = Math.floor(diff / 60_000);
    if (mins < 1) return "Только что";
    if (mins < 60) return `${mins} мин назад`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs} ч назад`;
    const days = Math.floor(hrs / 24);
    if (days < 7) return `${days} д назад`;
    return d.toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
  };

  const tabs: { key: TabFilter; label: string }[] = [
    { key: "all", label: "Все" },
    { key: "unread", label: `Непрочитанные${unreadCount > 0 ? ` (${unreadCount})` : ""}` },
  ];

  return (
    <AuthLayout>
      <div className="panel-grid-bg min-h-screen">
        <div className="app-page max-w-2xl">
        {/* Header — compact */}
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
          <h1 className="font-display text-2xl font-bold tracking-[0.15em]" style={{ color: "var(--text-primary)" }}>
            УВЕДОМЛЕНИЯ
          </h1>
          <div className="flex items-center justify-between mt-1">
            <span className="text-sm" style={{ color: "var(--text-muted)" }}>
              {unreadCount > 0 ? `${unreadCount} непрочитанных` : "Все прочитано"}
            </span>
            {unreadCount > 0 && (
              <motion.button
                onClick={markAllRead}
                className="flex items-center gap-1.5 text-xs transition-colors"
                style={{ color: "var(--accent)" }}
                whileTap={{ scale: 0.95 }}
              >
                <CheckCheck size={14} /> Прочитать все
              </motion.button>
            )}
          </div>
        </motion.div>

        {/* Tabs */}
        <div className="flex gap-2 mt-6">
          {tabs.map((t) => (
            <motion.button
              key={t.key}
              onClick={() => setTab(t.key)}
              className="rounded-lg px-4 py-2 text-xs font-mono transition-all"
              style={{
                background: tab === t.key ? "var(--accent-muted)" : "var(--input-bg)",
                border: `1px solid ${tab === t.key ? "var(--accent)" : "var(--border-color)"}`,
                color: tab === t.key ? "var(--accent)" : "var(--text-muted)",
              }}
              whileHover={{ scale: 1.03, borderColor: "var(--border-hover)" }}
              whileTap={{ scale: 0.97 }}
            >
              {t.label}
            </motion.button>
          ))}
        </div>

        {/* List */}
        <div className="mt-6 space-y-2">
          {loading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 size={24} className="animate-spin" style={{ color: "var(--accent)" }} />
            </div>
          ) : items.length === 0 ? (
            <EmptyState
              icon={Inbox}
              title={tab === "unread" ? "Нет непрочитанных" : "Нет уведомлений"}
              description={tab === "unread" ? "Все уведомления прочитаны — отличная работа!" : "Уведомления появятся по мере активности"}
            />
          ) : (
            items.map((n, i) => (
              <motion.div
                key={n.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.02 * i }}
                className="glass-panel p-4 flex items-start gap-3 cursor-pointer"
                style={{ background: n.read_at ? undefined : "var(--accent-muted)" }}
                onClick={() => !n.read_at && markRead(n.id)}
                onKeyDown={(e) => { if ((e.key === "Enter" || e.key === " ") && !n.read_at) { e.preventDefault(); markRead(n.id); } }}
                role="button"
                tabIndex={0}
                aria-label={`${n.read_at ? "Прочитано" : "Отметить как прочитанное"}: ${n.title}`}
              >
                {/* Unread indicator */}
                <div className="mt-1 shrink-0">
                  {!n.read_at ? (
                    <div className="w-2.5 h-2.5 rounded-full" style={{ background: "var(--accent)" }} />
                  ) : (
                    <Check size={12} style={{ color: "var(--text-muted)", opacity: 0.3 }} />
                  )}
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                      {n.title}
                    </span>
                    <span className="text-xs font-mono shrink-0 ml-3" style={{ color: "var(--text-muted)" }}>
                      {formatDate(n.created_at)}
                    </span>
                  </div>
                  <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
                    {n.body}
                  </p>
                </div>
              </motion.div>
            ))
          )}
        </div>
      </div>
    </div>
    </AuthLayout>
  );
}
