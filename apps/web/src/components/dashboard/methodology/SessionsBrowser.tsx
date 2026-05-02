"use client";

/**
 * SessionsBrowser — paginated browse of every training session in scope.
 *
 * Migrated 2026-04-26 from `apps/web/src/app/methodologist/sessions/page.tsx`
 * into a dashboard sub-tab. Backend route switched to `/rop/sessions` (the
 * `/methodologist/sessions` alias still works thanks to PR B1 dual-mount,
 * but new callers should hit the canonical URL).
 */

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { ChevronLeft, ChevronRight, FileText } from "lucide-react";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";

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

const PAGE_SIZE = 20;

export function SessionsBrowser() {
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    api.get<{ items: SessionItem[]; total: number }>(`/rop/sessions?${params}`)
      .then((res) => {
        setSessions(res.items);
        setTotal(res.total);
      })
      .catch((err) => logger.error("[SessionsBrowser] load failed:", err))
      .finally(() => setLoading(false));
  }, [page]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <FileText size={16} style={{ color: "var(--accent)" }} />
        <h3 className="font-display text-sm tracking-wider" style={{ color: "var(--text-secondary)" }}>
          ВСЕ СЕССИИ
        </h3>
        <span className="ml-auto font-mono text-xs" style={{ color: "var(--text-muted)" }}>
          {total} сессий
        </span>
      </div>

      {loading ? (
        <div className="space-y-2">
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
        <>
          <div className="overflow-x-auto rounded-lg" style={{ border: "1px solid var(--border-color)" }}>
            <table className="w-full text-xs">
              <thead style={{ background: "var(--input-bg)" }}>
                <tr>
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
                    className="border-t hover:bg-white/5"
                    style={{ borderColor: "var(--border-color)" }}
                  >
                    <td className="p-2" style={{ color: "var(--text-primary)" }}>{s.user_name}</td>
                    <td className="p-2" style={{ color: "var(--text-secondary)" }}>
                      {s.scenario_title || s.archetype || "—"}
                    </td>
                    <td
                      className="p-2 text-center font-mono font-bold"
                      style={{
                        color:
                          (s.score_total ?? 0) >= 70
                            ? "var(--success)"
                            : (s.score_total ?? 0) >= 50
                              ? "var(--warning)"
                              : "var(--danger)",
                      }}
                    >
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
          </div>

          <div className="flex items-center justify-between">
            <button
              onClick={() => setPage(Math.max(1, page - 1))}
              disabled={page <= 1}
              className="flex items-center gap-1 text-xs disabled:opacity-40"
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
              className="flex items-center gap-1 text-xs disabled:opacity-40"
              style={{ color: "var(--accent)" }}
            >
              Далее <ChevronRight size={14} />
            </button>
          </div>
        </>
      )}
    </div>
  );
}
