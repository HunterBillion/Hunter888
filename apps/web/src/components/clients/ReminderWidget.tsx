"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { Clock, ChevronRight, Phone } from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { ReminderItem } from "@/types";

export function ReminderWidget() {
  const [reminders, setReminders] = useState<ReminderItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/reminders")
      .then((data: ReminderItem[]) => {
        const today = data.filter((r) => {
          const d = new Date(r.remind_at);
          return d.toDateString() === new Date().toDateString();
        });
        setReminders(today);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading || !reminders.length) return null;

  const formatTime = (iso: string) => {
    const d = new Date(iso);
    return d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-panel p-4"
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Clock size={14} style={{ color: "var(--accent)" }} />
          <span className="text-xs font-mono tracking-wider" style={{ color: "var(--accent)" }}>
            НАПОМИНАНИЯ НА СЕГОДНЯ
          </span>
        </div>
        <Link
          href="/clients"
          className="text-[10px] flex items-center gap-1 transition-colors"
          style={{ color: "var(--text-muted)" }}
        >
          Все <ChevronRight size={10} />
        </Link>
      </div>

      <div className="space-y-2">
        {reminders.slice(0, 5).map((r, i) => {
          const isOverdue = new Date(r.remind_at) < new Date();
          return (
            <motion.div
              key={r.id}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.05 }}
            >
              <Link
                href={`/clients/${r.client_id}`}
                className="flex items-center gap-3 rounded-lg p-2.5 transition-colors"
                style={{ background: "var(--input-bg)" }}
              >
                <Phone size={12} style={{ color: isOverdue ? "var(--neon-red, #FF3333)" : "var(--text-muted)" }} />
                <div className="flex-1 min-w-0">
                  <span className="text-sm truncate block" style={{ color: "var(--text-primary)" }}>
                    {r.client_name}
                  </span>
                  {r.message && (
                    <span className="text-[10px] truncate block" style={{ color: "var(--text-muted)" }}>
                      {r.message}
                    </span>
                  )}
                </div>
                <div className="shrink-0 text-right">
                  <span
                    className="text-[10px] font-mono"
                    style={{ color: isOverdue ? "var(--neon-red, #FF3333)" : "var(--text-muted)" }}
                  >
                    {formatTime(r.remind_at)}
                  </span>
                </div>
              </Link>
            </motion.div>
          );
        })}
      </div>

      {reminders.length > 5 && (
        <div className="text-center mt-2">
          <span className="text-[10px]" style={{ color: "var(--text-muted)" }}>
            +{reminders.length - 5} ещё
          </span>
        </div>
      )}
    </motion.div>
  );
}
