// 2026-04-23 Sprint 6 — Deja-vu widget shown at the top of the client's
// interaction history when the CRM card was opened via `?retrain=...&from=...`.
// Encourages the manager to replay the previous training session with the
// same parameters (cloned via `clone_from_session_id`).

"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { RotateCcw, Star, Clock, BookOpen, X, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { useNotificationStore } from "@/stores/useNotificationStore";
import { logger } from "@/lib/logger";

interface RetrainWidgetLastSession {
  id: string;
  session_mode: string;
  total_score: number | null;
  duration_seconds: number | null;
  stages_completed: number[];
  final_stage: number | null;
}

export interface RetrainWidgetProps {
  mode: "call" | "chat";
  fromSessionId: string;
  lastSession: RetrainWidgetLastSession;
  clientName: string;
  onDismiss?: () => void;
}

function formatDuration(seconds: number | null): string {
  if (seconds === null || seconds === undefined || seconds < 0) return "—";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function formatScore(total: number | null): string {
  if (total === null || total === undefined) return "—";
  return `${Math.round(total)} / 100`;
}

export function RetrainWidget({
  mode,
  fromSessionId,
  lastSession,
  clientName,
  onDismiss,
}: RetrainWidgetProps) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);

  const modeLabelAcc = mode === "call" ? "звонок" : "чат";
  const modeLabelGen = mode === "call" ? "звонок" : "чат";

  const handleRetrain = async () => {
    if (loading) return;
    setLoading(true);
    try {
      const session = await api.post<{ id: string }>("/training/sessions", {
        clone_from_session_id: fromSessionId,
      });
      if (!session?.id) throw new Error("Сервер не вернул id сессии");
      if (mode === "call") {
        router.push(`/training/${session.id}/call`);
      } else {
        router.push(`/training/${session.id}`);
      }
    } catch (err) {
      logger.error("[RetrainWidget] clone session failed:", err);
      try {
        useNotificationStore.getState().addToast({
          title: "Не удалось повторить сеанс",
          body: err instanceof Error ? err.message : "Попробуйте ещё раз",
          type: "error",
        });
      } catch {
        // If the store import path changes upstream, swallow — the logger
        // already captured the failure and we don't want to block UI.
      }
      setLoading(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: -12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.28 }}
      className="glass-panel rounded-2xl p-5 mb-5"
      style={{
        borderLeft: "3px solid var(--accent)",
        boxShadow: "0 2px 18px color-mix(in srgb, var(--accent) 18%, transparent)",
      }}
    >
      <div className="flex items-start justify-between gap-3">
        <h3
          className="font-display text-base font-semibold flex items-center gap-2"
          style={{ color: "var(--text-primary)" }}
        >
          <RotateCcw size={16} style={{ color: "var(--accent)" }} />
          Закрепите разговор с {clientName}
        </h3>
        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            className="p-1 rounded-md transition hover:opacity-100 opacity-60"
            style={{ color: "var(--text-muted)" }}
            aria-label="Закрыть"
          >
            <X size={14} />
          </button>
        )}
      </div>

      <p className="text-xs mt-2 mb-3" style={{ color: "var(--text-muted)" }}>
        Ваш предыдущий {modeLabelGen}:
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mb-4">
        <div
          className="flex items-center gap-2 rounded-lg px-3 py-2"
          style={{ background: "var(--input-bg)" }}
        >
          <Star size={13} style={{ color: "var(--gf-xp)" }} />
          <div className="flex flex-col">
            <span className="text-[10px] uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
              Результат
            </span>
            <span className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
              {formatScore(lastSession.total_score)}
            </span>
          </div>
        </div>

        <div
          className="flex items-center gap-2 rounded-lg px-3 py-2"
          style={{ background: "var(--input-bg)" }}
        >
          <Clock size={13} style={{ color: "var(--accent)" }} />
          <div className="flex flex-col">
            <span className="text-[10px] uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
              Длительность
            </span>
            <span className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
              {formatDuration(lastSession.duration_seconds)}
            </span>
          </div>
        </div>

        <div
          className="flex items-center gap-2 rounded-lg px-3 py-2"
          style={{ background: "var(--input-bg)" }}
        >
          <BookOpen size={13} style={{ color: "var(--success)" }} />
          <div className="flex flex-col">
            <span className="text-[10px] uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
              Скрипт
            </span>
            <span className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
              {lastSession.stages_completed.length} / 7 этапов
            </span>
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <motion.button
          type="button"
          onClick={handleRetrain}
          disabled={loading}
          whileTap={{ scale: 0.98 }}
          className="btn-neon flex items-center justify-center gap-2 text-sm font-semibold"
          style={{
            color: "var(--accent)",
            borderColor: "var(--accent)",
            opacity: loading ? 0.6 : 1,
          }}
        >
          {loading ? (
            <Loader2 size={15} className="animate-spin" />
          ) : (
            <RotateCcw size={15} />
          )}
          Повторить {modeLabelAcc}
        </motion.button>
        <span className="text-[11px] text-center" style={{ color: "var(--text-muted)" }}>
          Те же настройки, тот же клиент
        </span>

        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            className="text-xs mt-1 self-center underline-offset-2 hover:underline"
            style={{ color: "var(--text-muted)" }}
          >
            Закрыть
          </button>
        )}
      </div>
    </motion.div>
  );
}

export default RetrainWidget;
