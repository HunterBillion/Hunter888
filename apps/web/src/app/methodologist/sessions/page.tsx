"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { FileText, Search, ChevronLeft, ChevronRight, ShieldAlert } from "lucide-react";
import { BackButton } from "@/components/ui/BackButton";
import AuthLayout from "@/components/layout/AuthLayout";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";
import { useAuth } from "@/hooks/useAuth";
import { hasRole } from "@/lib/guards";

interface SessionItem {
  id: string;
  user_id: string;
  user_name: string;
  scenario_title: string | null;
  archetype: string | null;
  score_total: number | null;
  status: string;
  duration_seconds: number | null;
  started_at: string | null;
}

export default function MethodologistSessionsPage() {
  const { user, loading: authLoading } = useAuth();
  const accessDenied = !authLoading && user != null && !hasRole(user, ["admin", "rop", "methodologist"]);

  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");

  const pageSize = 20;

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    api.get(`/methodologist/sessions?${params}`)
      .then((res) => {
        setSessions(res.data.items);
        setTotal(res.data.total);
      })
      .catch((err) => logger.error("[MethodologistSessions] Failed to load sessions:", err))
      .finally(() => setLoading(false));
  }, [page]);

  const totalPages = Math.ceil(total / pageSize);

  if (accessDenied) {
    return (
      <AuthLayout>
        <div className="flex min-h-screen items-center justify-center">
          <div className="text-center">
            <ShieldAlert size={48} style={{ color: "var(--danger)", margin: "0 auto 16px" }} />
            <h2 className="font-display text-xl font-bold" style={{ color: "var(--text-primary)" }}>Доступ запрещён</h2>
            <p className="mt-2 text-sm" style={{ color: "var(--text-muted)" }}>Эта страница доступна только методологам, РОП и администраторам.</p>
          </div>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout>
      <div className="relative panel-grid-bg min-h-screen">
        <div className="mx-auto max-w-5xl px-4 py-8">
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
            <div className="mb-4">
              <BackButton href="/home" label="Назад" />
            </div>
            <div className="flex items-center gap-2">
              <FileText size={20} style={{ color: "var(--accent)" }} />
              <h1 className="font-display text-xl font-bold tracking-[0.15em]" style={{ color: "var(--text-primary)" }}>
                ВСЕ СЕССИИ
              </h1>
            </div>
            <p className="mt-1 font-mono text-xs" style={{ color: "var(--text-muted)" }}>
              {total} сессий
            </p>
          </motion.div>

          {loading ? (
            <div className="mt-6 space-y-2">
              {[1, 2, 3, 4, 5, 6].map((i) => (
                <div key={i} className="flex gap-4 p-3 animate-pulse">
                  <div className="h-3 w-24 rounded bg-[var(--input-bg)]" />
                  <div className="h-3 w-32 rounded bg-[var(--input-bg)]" />
                  <div className="h-3 w-12 rounded bg-[var(--input-bg)]" />
                  <div className="h-3 w-12 rounded bg-[var(--input-bg)]" />
                  <div className="h-3 w-20 rounded bg-[var(--input-bg)]" />
                </div>
              ))}
            </div>
          ) : (
            <div className="mt-6">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b" style={{ borderColor: "var(--border-color)" }}>
                    <th className="text-left p-2" style={{ color: "var(--text-muted)" }}>Менеджер</th>
                    <th className="text-left p-2" style={{ color: "var(--text-muted)" }}>Сценарий</th>
                    <th className="text-center p-2" style={{ color: "var(--text-muted)" }}>Балл</th>
                    <th className="text-center p-2" style={{ color: "var(--text-muted)" }}>Длит.</th>
                    <th className="text-right p-2" style={{ color: "var(--text-muted)" }}>Дата</th>
                  </tr>
                </thead>
                <tbody>
                  {sessions.map((s, i) => (
                    <motion.tr
                      key={s.id}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ delay: i * 0.02 }}
                      className="border-b cursor-pointer hover:bg-white/5"
                      style={{ borderColor: "var(--border-color)" }}
                    >
                      <td className="p-2" style={{ color: "var(--text-primary)" }}>{s.user_name}</td>
                      <td className="p-2" style={{ color: "var(--text-secondary)" }}>
                        {s.scenario_title || s.archetype || "—"}
                      </td>
                      <td className="p-2 text-center font-mono font-bold" style={{
                        color: (s.score_total ?? 0) >= 70 ? "#22c55e" : (s.score_total ?? 0) >= 50 ? "#f59e0b" : "#ef4444"
                      }}>
                        {s.score_total ? Math.round(s.score_total) : "—"}
                      </td>
                      <td className="p-2 text-center font-mono" style={{ color: "var(--text-muted)" }}>
                        {s.duration_seconds ? `${Math.round(s.duration_seconds / 60)}m` : "—"}
                      </td>
                      <td className="p-2 text-right font-mono" style={{ color: "var(--text-muted)" }}>
                        {s.started_at ? new Date(s.started_at).toLocaleDateString("ru-RU") : "—"}
                      </td>
                    </motion.tr>
                  ))}
                </tbody>
              </table>

              {/* Pagination */}
              <div className="mt-4 flex items-center justify-between">
                <button
                  onClick={() => setPage(Math.max(1, page - 1))}
                  disabled={page <= 1}
                  className="flex items-center gap-1 text-xs disabled:opacity-30"
                  style={{ color: "var(--accent)" }}
                >
                  <ChevronLeft size={14} /> Назад
                </button>
                <span className="font-mono text-xs" style={{ color: "var(--text-muted)" }}>
                  {page} / {totalPages}
                </span>
                <button
                  onClick={() => setPage(Math.min(totalPages, page + 1))}
                  disabled={page >= totalPages}
                  className="flex items-center gap-1 text-xs disabled:opacity-30"
                  style={{ color: "var(--accent)" }}
                >
                  Далее <ChevronRight size={14} />
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </AuthLayout>
  );
}
