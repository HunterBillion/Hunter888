"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Search, Swords, Loader2, X } from "lucide-react";
import { useReducedMotion } from "@/hooks/useReducedMotion";

interface Props {
  status: "searching" | "matched";
  position: number;
  estimatedWait: number;
  opponentRating?: number;
  onCancel: () => void;
}

const MATCH_TIMEOUT = 60;

export function MatchmakingOverlay({ status, position, estimatedWait, opponentRating, onCancel }: Props) {
  const reducedMotion = useReducedMotion();
  const rem = estimatedWait > 0 ? estimatedWait : MATCH_TIMEOUT;
  const [anchor, setAnchor] = useState({ remaining: rem, wait: MATCH_TIMEOUT - rem, ts: Date.now() });
  const [live, setLive] = useState({ remaining: rem, wait: Math.max(0, MATCH_TIMEOUT - rem) });

  useEffect(() => {
    if (status !== "searching") return;
    const r = estimatedWait > 0 ? estimatedWait : MATCH_TIMEOUT;
    const w = Math.max(0, MATCH_TIMEOUT - r);
    setAnchor({ remaining: r, wait: w, ts: Date.now() });
    setLive({ remaining: r, wait: w });
  }, [status, estimatedWait]);

  useEffect(() => {
    if (status !== "searching") return;
    const tick = () => {
      const elapsed = Math.floor((Date.now() - anchor.ts) / 1000);
      setLive({
        remaining: Math.max(0, anchor.remaining - elapsed),
        wait: anchor.wait + elapsed,
      });
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [status, anchor.remaining, anchor.wait, anchor.ts]);

  const displayRemaining = status === "searching" ? live.remaining : 0;
  const displayWait = status === "searching" ? live.wait : 0;
  const progress = Math.min(100, Math.round((displayWait / MATCH_TIMEOUT) * 100));

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-[150] flex items-center justify-center"
      style={{ background: "rgba(0,0,0,0.85)" }}
    >
      <motion.div
        initial={{ scale: 0.9 }}
        animate={{ scale: 1 }}
        className="glass-panel max-w-sm w-full mx-4 p-8 text-center"
      >
        {status === "searching" ? (
          <>
            {/* Searching animation */}
            <div className="relative mx-auto w-24 h-24 mb-6">
              <motion.div
                className="absolute inset-0 rounded-full border-2 border-dashed"
                style={{ borderColor: "var(--accent)" }}
                animate={reducedMotion ? {} : { rotate: 360 }}
                transition={reducedMotion ? {} : { duration: 3, repeat: Infinity, ease: "linear" }}
              />
              <motion.div
                className="absolute inset-3 rounded-full border-2"
                style={{ borderColor: "rgba(139,92,246,0.3)" }}
                animate={reducedMotion ? {} : { rotate: -360 }}
                transition={reducedMotion ? {} : { duration: 5, repeat: Infinity, ease: "linear" }}
              />
              <div className="absolute inset-0 flex items-center justify-center">
                <Search size={28} style={{ color: "var(--accent)" }} />
              </div>
            </div>

            <h2 className="font-display text-xl font-bold" style={{ color: "var(--text-primary)" }}>
              ИЩЕМ СОПЕРНИКА
            </h2>
            <div className="mt-3 text-xs leading-5 font-mono" style={{ color: "var(--text-muted)" }}>
              Если за 60 секунд игрок не найден, арена автоматически запускает бой с AI.
            </div>
            <div className="mt-5 space-y-3 font-mono" style={{ color: "var(--text-muted)" }}>
              {position > 0 && <p className="text-xs">Активных игроков в очереди: {position}</p>}
              <div className="flex items-end justify-center gap-2">
                <span className="text-4xl font-bold tabular-nums" style={{ color: "var(--accent)" }}>
                  {displayWait}
                </span>
                <span className="pb-1 text-xs">сек в поиске</span>
              </div>
              <div className="mx-auto h-2 w-full overflow-hidden rounded-full" style={{ background: "rgba(255,255,255,0.08)" }}>
                <motion.div
                  className="h-full rounded-full"
                  style={{ background: "linear-gradient(90deg, var(--accent), #FFD700)" }}
                  animate={{ width: `${progress}%` }}
                />
              </div>
              <p className="text-[10px] opacity-70">Готовим автоматический PvE, если живой соперник не подключится</p>
            </div>

            <motion.button
              onClick={onCancel}
              className="mt-6 vh-btn-outline flex items-center gap-2 mx-auto"
              whileTap={{ scale: 0.97 }}
            >
              <X size={14} /> Отмена
            </motion.button>
          </>
        ) : (
          <>
            {/* Match found */}
            <motion.div
              initial={{ scale: 0 }}
              animate={{ scale: [0, 1.2, 1] }}
              transition={{ duration: 0.5 }}
              className="mx-auto w-20 h-20 rounded-full flex items-center justify-center mb-6"
              style={{ background: "rgba(0,255,102,0.1)", border: "2px solid rgba(0,255,102,0.3)" }}
            >
              <Swords size={32} style={{ color: "#00FF66" }} />
            </motion.div>

            <h2 className="font-display text-xl font-bold" style={{ color: "#00FF66" }}>
              {opponentRating ? "СОПЕРНИК НАЙДЕН!" : "АРЕНА ГОТОВА!"}
            </h2>
            {opponentRating ? (
              <p className="mt-2 font-mono text-sm" style={{ color: "var(--text-muted)" }}>
                Рейтинг: {Math.round(opponentRating)}
              </p>
            ) : (
              <p className="mt-2 font-mono text-sm" style={{ color: "var(--text-muted)" }}>
                Запускаем бой против AI-клиента
              </p>
            )}
            <div className="mt-4 flex items-center justify-center gap-2">
              <Loader2 size={14} className="animate-spin" style={{ color: "var(--accent)" }} />
              <span className="font-mono text-xs" style={{ color: "var(--text-muted)" }}>Подготовка арены...</span>
            </div>
          </>
        )}
      </motion.div>
    </motion.div>
  );
}
