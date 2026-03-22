"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { Bell, ExternalLink, Check, Wifi, WifiOff, Swords } from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useNotificationStore } from "@/stores/useNotificationStore";
import type { AppNotification } from "@/types";

/**
 * NotificationBell — reads from useNotificationStore (populated by NotificationWSProvider).
 * WS logic lives in NotificationWSProvider, not here.
 * This component only handles: dropdown UI, shake, toasts display, mark-read.
 */
interface NotificationBellProps {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

export function NotificationBell({ open: controlledOpen, onOpenChange }: NotificationBellProps = {}) {
  const { items, unread, wsConnected, toasts, markRead: storeMarkRead, removeToast } = useNotificationStore();
  const [internalOpen, setInternalOpen] = useState(false);
  const [shake, setShake] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const prevUnreadRef = useRef(unread);
  const open = controlledOpen ?? internalOpen;
  const setOpen = useCallback((next: boolean) => {
    if (controlledOpen === undefined) {
      setInternalOpen(next);
    }
    onOpenChange?.(next);
  }, [controlledOpen, onOpenChange]);

  // Shake bell when unread increases
  useEffect(() => {
    if (unread > prevUnreadRef.current) {
      setShake(true);
      setTimeout(() => setShake(false), 600);
      if (navigator.vibrate) navigator.vibrate(100);
    }
    prevUnreadRef.current = unread;
  }, [unread]);

  // Close dropdown on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // Mark read — try REST API, update store
  const handleMarkRead = useCallback((id: string) => {
    storeMarkRead(id);
    api.post(`/notifications/${id}/read`, {}).catch(() => {});
  }, [storeMarkRead]);

  const formatTime = (iso: string) => {
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60_000);
    if (mins < 1) return "Только что";
    if (mins < 60) return `${mins} мин`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs} ч`;
    return `${Math.floor(hrs / 24)} д`;
  };

  const toastColors: Record<string, { bg: string; border: string; color: string }> = {
    info: { bg: "rgba(59,130,246,0.1)", border: "rgba(59,130,246,0.25)", color: "#3B82F6" },
    system: { bg: "rgba(59,130,246,0.1)", border: "rgba(59,130,246,0.25)", color: "#3B82F6" },
    success: { bg: "rgba(34,197,94,0.1)", border: "rgba(34,197,94,0.25)", color: "#22C55E" },
    consent: { bg: "rgba(34,197,94,0.1)", border: "rgba(34,197,94,0.25)", color: "#22C55E" },
    warning: { bg: "rgba(245,158,11,0.1)", border: "rgba(245,158,11,0.25)", color: "#F59E0B" },
    reminder: { bg: "rgba(139,92,246,0.1)", border: "rgba(139,92,246,0.25)", color: "#8B5CF6" },
    achievement: { bg: "rgba(255,215,0,0.1)", border: "rgba(255,215,0,0.25)", color: "#FFD700" },
    pvp_invitation: { bg: "rgba(255,215,0,0.12)", border: "rgba(255,215,0,0.3)", color: "#FFD700" },
  };

  const router = useRouter();

  return (
    <>
      {/* Toast notifications from store */}
      <div className="fixed top-24 right-4 z-[220] flex flex-col gap-2 pointer-events-none">
        <AnimatePresence>
          {toasts.map((toast) => {
            const style = toastColors[toast.type] || toastColors.info;
            const isPvPInvite = toast.type === "pvp_invitation" && toast.challenger_id;

            return (
              <motion.div
                key={toast.id}
                initial={{ opacity: 0, x: 60, scale: 0.9 }}
                animate={{ opacity: 1, x: 0, scale: 1 }}
                exit={{ opacity: 0, x: 60, scale: 0.9 }}
                transition={{ duration: 0.25, ease: [0.4, 0, 0.2, 1] }}
                className={`pointer-events-auto rounded-xl px-4 py-3 text-xs font-medium max-w-xs ${!isPvPInvite ? "cursor-pointer" : ""}`}
                onClick={!isPvPInvite ? () => removeToast(toast.id) : undefined}
                style={{
                  background: style.bg,
                  border: `1px solid ${style.border}`,
                  color: style.color,
                  backdropFilter: "blur(12px)",
                  boxShadow: "0 8px 32px rgba(0,0,0,0.2)",
                }}
              >
                <div className="font-semibold flex items-center gap-2">
                  {isPvPInvite && <Swords size={14} />}
                  {toast.title}
                </div>
                {toast.body && <div className="mt-0.5 opacity-80">{toast.body}</div>}
                {isPvPInvite ? (
                  <div className="mt-2 flex gap-2" onClick={(e) => e.stopPropagation()}>
                    <button
                      type="button"
                      className="px-3 py-1 rounded-lg text-[10px] font-bold uppercase tracking-wider transition-opacity hover:opacity-90"
                      style={{ background: "rgba(34,197,94,0.3)", color: "#22C55E" }}
                      onClick={() => {
                        removeToast(toast.id);
                        router.push(`/pvp?accept=${toast.challenger_id}`);
                      }}
                    >
                      Принять
                    </button>
                    <button
                      type="button"
                      className="px-3 py-1 rounded-lg text-[10px] font-bold uppercase tracking-wider opacity-70 hover:opacity-100 transition-opacity"
                      style={{ color: style.color }}
                      onClick={() => removeToast(toast.id)}
                    >
                      Отказать
                    </button>
                  </div>
                ) : null}
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>

      <div className="relative" ref={dropdownRef}>
        <motion.button
          onClick={() => setOpen(!open)}
          className="relative p-2 rounded-lg transition-colors"
          style={{ color: "var(--text-secondary)" }}
          whileTap={{ scale: 0.95 }}
          animate={shake ? { rotate: [0, -12, 12, -8, 8, -4, 0] } : {}}
          transition={shake ? { duration: 0.5 } : {}}
        >
          <Bell size={18} />
          {unread > 0 && (
            <motion.div
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 flex items-center justify-center rounded-full px-1 text-[9px] font-bold text-white"
              style={{ background: "var(--neon-red, #FF3333)" }}
            >
              {unread > 99 ? "99+" : unread}
            </motion.div>
          )}
          {/* WS connection indicator */}
          <div
            className="absolute bottom-0.5 right-0.5 w-1.5 h-1.5 rounded-full"
            style={{ background: wsConnected ? "var(--neon-green, #00FF66)" : "var(--text-muted)" }}
            title={wsConnected ? "Подключено" : "Переподключение..."}
          />
        </motion.button>

        <AnimatePresence>
          {open && (
            <motion.div
              initial={{ opacity: 0, y: -4, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -4, scale: 0.95 }}
              transition={{ duration: 0.15 }}
              className="absolute right-0 top-full mt-3 w-80 rounded-[22px] overflow-hidden z-[70]"
              style={{
                background: "linear-gradient(180deg, rgba(8,8,12,0.98), rgba(14,16,22,0.96))",
                backdropFilter: "blur(24px)",
                border: "1px solid rgba(255,255,255,0.08)",
                boxShadow: "0 24px 60px rgba(0,0,0,0.52)",
              }}
            >
              {/* Header */}
              <div className="flex items-center justify-between px-4 py-3 border-b" style={{ borderColor: "var(--border-color)" }}>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                    Уведомления
                  </span>
                  {wsConnected ? (
                    <Wifi size={10} style={{ color: "var(--neon-green, #00FF66)" }} />
                  ) : (
                    <WifiOff size={10} style={{ color: "var(--text-muted)" }} />
                  )}
                </div>
                {unread > 0 && (
                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded-full"
                    style={{ background: "rgba(255,51,51,0.1)", color: "var(--neon-red, #FF3333)" }}
                  >
                    {unread} новых
                  </span>
                )}
              </div>

              {/* Items */}
              <div className="max-h-[320px] overflow-y-auto">
                {items.length === 0 ? (
                  <div className="py-8 text-center">
                    <Bell size={24} className="mx-auto mb-2 opacity-20" style={{ color: "var(--text-muted)" }} />
                    <span className="text-xs" style={{ color: "var(--text-muted)" }}>Нет уведомлений</span>
                  </div>
                ) : (
                  items.map((n) => (
                    <motion.div
                      key={n.id}
                      className="flex items-start gap-3 px-4 py-3 transition-colors cursor-pointer"
                      style={{
                        background: n.read ? "transparent" : "var(--accent-muted)",
                        borderBottom: "1px solid var(--border-color)",
                      }}
                      whileHover={{ background: "var(--bg-tertiary)" }}
                      onClick={() => !n.read && handleMarkRead(n.id)}
                    >
                      {/* Unread dot */}
                      <div className="mt-1.5 shrink-0">
                        {!n.read ? (
                          <div className="w-2 h-2 rounded-full" style={{ background: "var(--accent)" }} />
                        ) : (
                          <Check size={10} style={{ color: "var(--text-muted)", opacity: 0.4 }} />
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-medium" style={{ color: "var(--text-primary)" }}>
                          {n.title}
                        </div>
                        <div className="text-[11px] mt-0.5 line-clamp-2" style={{ color: "var(--text-muted)" }}>
                          {n.body || ""}
                        </div>
                        <div className="text-[9px] font-mono mt-1" style={{ color: "var(--text-muted)", opacity: 0.6 }}>
                          {formatTime(n.created_at)}
                        </div>
                      </div>
                    </motion.div>
                  ))
                )}
              </div>

              {/* Footer */}
              <Link
                href="/notifications"
                onClick={() => setOpen(false)}
                className="flex items-center justify-center gap-1.5 px-4 py-2.5 text-xs font-medium transition-colors border-t"
                style={{ borderColor: "var(--border-color)", color: "var(--accent)" }}
              >
                Все уведомления <ExternalLink size={11} />
              </Link>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </>
  );
}
