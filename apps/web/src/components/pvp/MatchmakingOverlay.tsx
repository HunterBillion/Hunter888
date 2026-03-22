"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Search, Swords, Loader2, X } from "lucide-react";

interface Props {
  status: "searching" | "matched";
  position: number;
  estimatedWait: number;
  opponentRating?: number;
  onCancel: () => void;
}

const MATCH_TIMEOUT = 60;

export function MatchmakingOverlay({ status, position, estimatedWait, opponentRating, onCancel }: Props) {
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
                animate={{ rotate: 360 }}
                transition={{ duration: 3, repeat: Infinity, ease: "linear" }}
              />
              <motion.div
                className="absolute inset-3 rounded-full border-2"
                style={{ borderColor: "rgba(139,92,246,0.3)" }}
                animate={{ rotate: -360 }}
                transition={{ duration: 5, repeat: Infinity, ease: "linear" }}
              />
              <div className="absolute inset-0 flex items-center justify-center">
                <Search size={28} style={{ color: "var(--accent)" }} />
              </div>
            </div>

            <h2 className="font-display text-xl font-bold" style={{ color: "var(--text-primary)" }}>
              ПОИСК СОПЕРНИКА
            </h2>
            <div className="mt-4 space-y-2 font-mono" style={{ color: "var(--text-muted)" }}>
              {position > 0 && <p className="text-xs">Позиция в очереди: {position}</p>}
              <motion.div
                key={displayRemaining}
                initial={{ scale: 1.1, opacity: 0.8 }}
                animate={{ scale: 1, opacity: 1 }}
                className="flex items-center justify-center gap-2"
              >
                <span className="text-3xl font-bold tabular-nums" style={{ color: "var(--accent)" }}>
                  {displayRemaining}
                </span>
                <span className="text-xs">сек осталось</span>
              </motion.div>
              <p className="text-[10px] opacity-70">Прошло: {displayWait} сек</p>
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
              СОПЕРНИК НАЙДЕН!
            </h2>
            {opponentRating && (
              <p className="mt-2 font-mono text-sm" style={{ color: "var(--text-muted)" }}>
                Рейтинг: {Math.round(opponentRating)}
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
