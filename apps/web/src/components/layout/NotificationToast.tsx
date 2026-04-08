"use client";

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, Bell, Trophy, UserPlus, AlertTriangle, Info } from "lucide-react";
import type { NotificationType } from "@/types";

interface ToastItem {
  id: string;
  type: NotificationType;
  title: string;
  body: string;
}

const ICONS: Record<NotificationType, typeof Bell> = {
  reminder: Bell,
  assignment: UserPlus,
  achievement: Trophy,
  system: Info,
  status_change: Info,
  consent: Info,
  overdue: AlertTriangle,
};

// Global toast trigger — call pushToast() from anywhere
let _pushFn: ((item: Omit<ToastItem, "id">) => void) | null = null;
export function pushToast(item: Omit<ToastItem, "id">) {
  _pushFn?.(item);
}

export function NotificationToastProvider() {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const push = useCallback((item: Omit<ToastItem, "id">) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    setToasts((prev) => [...prev.slice(-4), { ...item, id }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 5000);
  }, []);

  useEffect(() => {
    _pushFn = push;
    return () => { _pushFn = null; };
  }, [push]);

  const dismiss = (id: string) => setToasts((prev) => prev.filter((t) => t.id !== id));

  return (
    <div
      className="fixed top-[4.5rem] right-3 z-[220] flex flex-col gap-2 w-[340px] pointer-events-none"
      role="status"
      aria-live="polite"
      aria-atomic="false"
    >
      <AnimatePresence>
        {toasts.map((t) => {
          const Icon = ICONS[t.type] || Bell;
          return (
            <motion.div
              key={t.id}
              initial={{ opacity: 0, x: 30, y: -20, scale: 0.85 }}
              animate={{ opacity: 1, x: 0, y: 0, scale: 1 }}
              exit={{ opacity: 0, x: 40, y: -10, scale: 0.85 }}
              transition={{ type: "spring", stiffness: 500, damping: 28 }}
              className="rounded-xl p-3 flex items-start gap-3 pointer-events-auto animate-[glow-pulse_0.6s_ease-out]"
              style={{
                background: "var(--glass-bg)",
                backdropFilter: "blur(20px)",
                border: "1px solid var(--border-color)",
                boxShadow: "var(--shadow-lg)",
              }}
            >
              <div
                className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
                style={{ background: "var(--accent-muted)" }}
              >
                <Icon size={16} style={{ color: "var(--accent)" }} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-xs font-medium" style={{ color: "var(--text-primary)" }}>
                  {t.title}
                </div>
                <div className="text-xs mt-0.5 line-clamp-2" style={{ color: "var(--text-muted)" }}>
                  {t.body}
                </div>
              </div>
              <button onClick={() => dismiss(t.id)} className="shrink-0 mt-0.5" style={{ color: "var(--text-muted)" }} aria-label="Закрыть уведомление">
                <X size={14} />
              </button>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
