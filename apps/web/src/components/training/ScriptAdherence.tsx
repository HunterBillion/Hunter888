"use client";

import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { CheckCircle2, Circle, ChevronDown } from "lucide-react";

export interface CheckpointInfo {
  id: string;
  title: string;
  order: number;
  hit: boolean;
  score: number;
}

interface ScriptAdherenceProps {
  progress: number;
  checkpointsHit: number;
  checkpointsTotal: number;
  checkpoints?: CheckpointInfo[];
  /** Name of checkpoint to highlight (from hint.checkpoint WS event) */
  highlightCheckpoint?: string | null;
  /** Title of newly matched checkpoint (from score.update new_checkpoint) */
  newCheckpoint?: string | null;
  /** Whether the score is preliminary (real-time, during active session) */
  isPreliminary?: boolean;
}

export default function ScriptAdherence({
  progress,
  checkpointsHit,
  checkpointsTotal,
  checkpoints = [],
  highlightCheckpoint = null,
  newCheckpoint = null,
  isPreliminary = false,
}: ScriptAdherenceProps) {
  const pct = Math.min(Math.max(progress, 0), 100);
  const [mobileExpanded, setMobileExpanded] = useState(false);

  // New checkpoint flash state
  const [flashCheckpoint, setFlashCheckpoint] = useState<string | null>(null);
  const flashTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (newCheckpoint) {
      setFlashCheckpoint(newCheckpoint);
      if (flashTimerRef.current) clearTimeout(flashTimerRef.current);
      flashTimerRef.current = setTimeout(() => setFlashCheckpoint(null), 3000);
    }
    return () => {
      if (flashTimerRef.current) clearTimeout(flashTimerRef.current);
    };
  }, [newCheckpoint]);

  // Find first un-hit checkpoint as "current"
  const currentIdx = checkpoints.findIndex((cp) => !cp.hit);

  const total = checkpoints.length || checkpointsTotal;
  const hit = checkpoints.length ? checkpoints.filter((c) => c.hit).length : checkpointsHit;

  return (
    <div
      className="rounded-xl p-4"
      style={{
        background: "var(--glass-bg)",
        border: "1px solid var(--glass-border)",
        backdropFilter: "blur(20px)",
      }}
    >
      <div className="flex items-center justify-between mb-2.5">
        <div className="font-mono text-xs uppercase tracking-wider font-semibold" style={{ color: "var(--text-secondary)" }}>
          Следование скрипту
        </div>
        {isPreliminary && (
          <span
            className="font-mono text-xs uppercase tracking-wider px-2 py-0.5 rounded-full"
            style={{ color: "var(--text-muted)", background: "var(--input-bg)", opacity: 0.7 }}
          >
            предварительно
          </span>
        )}
      </div>

      {/* Progress bar */}
      <div className="flex items-center gap-3">
        <div className="flex-1 h-2 rounded-full overflow-hidden" style={{ background: "var(--input-bg)" }}>
          <motion.div
            className="h-full rounded-full"
            style={{ background: "var(--accent)", boxShadow: "0 0 5px rgba(99,102,241,0.5)" }}
            animate={{ width: `${pct}%` }}
            transition={{ duration: 0.8 }}
          />
        </div>
        <span className="font-mono text-sm font-bold" style={{ color: "var(--text-primary)" }}>{Math.round(pct)}%</span>
      </div>

      {/* New checkpoint flash toast */}
      <AnimatePresence>
        {flashCheckpoint && (
          <motion.div
            initial={{ opacity: 0, y: -8, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.95 }}
            transition={{ duration: 0.3 }}
            className="mt-2.5 flex items-center gap-2 px-3 py-1.5 rounded-lg"
            style={{
              background: "rgba(0, 255, 148, 0.1)",
              border: "1px solid rgba(0, 255, 148, 0.3)",
            }}
          >
            <CheckCircle2 size={14} style={{ color: "var(--neon-green, #00FF94)" }} strokeWidth={2.5} />
            <span className="font-mono text-xs font-semibold" style={{ color: "var(--neon-green, #00FF94)" }}>
              {flashCheckpoint}
            </span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Checkpoint circles — desktop */}
      {checkpoints.length > 0 && (
        <div className="hidden sm:flex mt-3 items-center gap-1.5 overflow-x-auto pb-1">
          {checkpoints.map((cp, i) => {
            const isCurrent = i === currentIdx;
            const isHighlighted = highlightCheckpoint != null && cp.title === highlightCheckpoint;
            const isNewlyHit = flashCheckpoint != null && cp.title === flashCheckpoint;
            const isHit = cp.hit;

            return (
              <div key={cp.id} className="flex items-center">
                <div className="relative group" title={cp.title}>
                  <AnimatePresence mode="wait">
                    {isHit ? (
                      <motion.div
                        key="hit"
                        initial={{ scale: 0 }}
                        animate={{
                          scale: isNewlyHit ? [1, 1.5, 1] : 1,
                          filter: isNewlyHit ? ["brightness(1)", "brightness(1.8)", "brightness(1)"] : "brightness(1)",
                        }}
                        transition={isNewlyHit
                          ? { duration: 0.6, ease: "easeOut" }
                          : { type: "spring", stiffness: 400, damping: 15 }
                        }
                      >
                        <CheckCircle2
                          size={20}
                          style={{ color: "var(--neon-green, #00FF94)" }}
                          strokeWidth={2.5}
                        />
                      </motion.div>
                    ) : (
                      <motion.div
                        key="pending"
                        animate={(isCurrent || isHighlighted) ? {
                          scale: isHighlighted ? [1, 1.4, 1] : [1, 1.2, 1],
                          opacity: [0.6, 1, 0.6],
                        } : {}}
                        transition={(isCurrent || isHighlighted) ? {
                          duration: isHighlighted ? 0.8 : 2,
                          repeat: Infinity,
                          ease: "easeInOut",
                        } : {}}
                      >
                        <Circle
                          size={20}
                          style={{
                            color: isHighlighted ? "#FFD700" : isCurrent ? "var(--accent)" : "var(--border-color)",
                            filter: isHighlighted ? "drop-shadow(0 0 6px rgba(255,215,0,0.6))" : "none",
                          }}
                          strokeWidth={(isCurrent || isHighlighted) ? 2.5 : 1.5}
                        />
                      </motion.div>
                    )}
                  </AnimatePresence>

                  {/* Tooltip */}
                  <div
                    className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 px-2.5 py-1.5 rounded-lg text-xs font-mono whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-20"
                    style={{
                      background: "var(--bg-secondary)",
                      border: "1px solid var(--border-color)",
                      color: "var(--text-secondary)",
                    }}
                  >
                    {cp.title}
                  </div>
                </div>

                {/* Connector line */}
                {i < checkpoints.length - 1 && (
                  <div
                    className="w-2.5 h-px mx-0.5"
                    style={{
                      background: checkpoints[i + 1]?.hit || isHit
                        ? "var(--accent)"
                        : "var(--border-color)",
                    }}
                  />
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Checkpoint mobile — collapsible */}
      {checkpoints.length > 0 && (
        <div className="sm:hidden mt-2.5">
          <button
            onClick={() => setMobileExpanded(!mobileExpanded)}
            className="flex items-center gap-2 w-full"
          >
            <CheckCircle2 size={14} style={{ color: "var(--accent)" }} />
            <span className="font-mono text-xs" style={{ color: "var(--text-secondary)" }}>
              {hit}/{total} чекпоинтов
            </span>
            <motion.span
              animate={{ rotate: mobileExpanded ? 180 : 0 }}
              transition={{ duration: 0.2 }}
              className="ml-auto"
            >
              <ChevronDown size={14} style={{ color: "var(--text-muted)" }} />
            </motion.span>
          </button>

          <AnimatePresence>
            {mobileExpanded && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.25 }}
                className="overflow-hidden"
              >
                <div className="mt-2 space-y-2 pl-1">
                  {checkpoints.map((cp) => (
                    <div key={cp.id} className="flex items-center gap-2">
                      {cp.hit ? (
                        <CheckCircle2 size={16} style={{ color: "var(--neon-green, #00FF94)" }} strokeWidth={2.5} />
                      ) : (
                        <Circle size={16} style={{ color: "var(--border-color)" }} strokeWidth={1.5} />
                      )}
                      <span
                        className="text-xs truncate"
                        style={{ color: cp.hit ? "var(--text-primary)" : "var(--text-muted)" }}
                      >
                        {cp.title}
                      </span>
                    </div>
                  ))}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}

      {/* Fallback counter if no checkpoint details */}
      {checkpoints.length === 0 && checkpointsTotal > 0 && (
        <div className="flex items-center gap-2 mt-2.5">
          <CheckCircle2 size={14} style={{ color: "var(--accent)" }} />
          <span className="font-mono text-xs" style={{ color: "var(--text-secondary)" }}>
            {checkpointsHit}/{checkpointsTotal} чекпоинтов
          </span>
        </div>
      )}
    </div>
  );
}
