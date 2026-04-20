"use client";

/**
 * CountdownOverlay — pre-round "3..2..1..GO!" overlay for all Arena modes.
 *
 * Phase A (2026-04-20). Used right before round.start/rapid.round_start/
 * gauntlet.duel_start so the player has a moment to focus. Uses the mode
 * accent color and fires a short SFX tick per digit.
 *
 * Auto-dismisses at the end and calls `onDone`. Parent controls `open`
 * via state — typically: on WS round event → set open=true → countdown
 * component finishes → set open=false.
 */

import { useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { sfx } from "@/components/arena/sfx/useSFX";

interface Props {
  open: boolean;
  accentColor: string;
  /** Seconds to count from. Default 3. Clamped to [1, 5]. */
  from?: number;
  /** Label shown under the big digit (e.g. "Раунд 2"). */
  label?: string;
  /** Called when countdown ends. */
  onDone?: () => void;
}

export function CountdownOverlay({
  open,
  accentColor,
  from = 3,
  label,
  onDone,
}: Props) {
  const doneRef = useRef(false);
  const start = Math.max(1, Math.min(5, from));

  useEffect(() => {
    if (!open) {
      doneRef.current = false;
      return;
    }
    // Pre-fire sound for immediate feedback
    sfx.play("tick");
    let step = 0;
    const t = setInterval(() => {
      step += 1;
      if (step < start) {
        sfx.play("tick");
      } else {
        clearInterval(t);
        sfx.play("round_start");
        if (!doneRef.current) {
          doneRef.current = true;
          onDone?.();
        }
      }
    }, 850);
    return () => clearInterval(t);
  }, [open, start, onDone]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[70] flex items-center justify-center pointer-events-none"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          style={{ background: "rgba(6,2,15,0.55)", backdropFilter: "blur(3px)" }}
        >
          <div className="relative flex flex-col items-center">
            {[...Array(start)].map((_, i) => {
              const digit = start - i;
              const delay = i * 0.85;
              return (
                <motion.div
                  key={i}
                  className="absolute font-mono font-extrabold text-center select-none"
                  style={{
                    fontSize: "min(22vw, 220px)",
                    lineHeight: 1,
                    color: accentColor,
                    textShadow: `0 0 60px ${accentColor}aa, 0 0 18px ${accentColor}`,
                  }}
                  initial={{ scale: 0.4, opacity: 0 }}
                  animate={{
                    scale: [0.4, 1.1, 1.0, 1.0, 0.88],
                    opacity: [0, 1, 1, 1, 0],
                  }}
                  transition={{
                    duration: 0.82,
                    times: [0, 0.18, 0.35, 0.7, 1],
                    delay,
                    ease: "easeOut",
                  }}
                >
                  {digit}
                </motion.div>
              );
            })}
            {label && (
              <motion.div
                className="absolute"
                style={{
                  bottom: "-22vh",
                  color: accentColor,
                  letterSpacing: "0.35em",
                }}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 0.85, y: 0 }}
                transition={{ delay: 0.2 }}
              >
                <span className="uppercase text-xs font-semibold">
                  {label}
                </span>
              </motion.div>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
