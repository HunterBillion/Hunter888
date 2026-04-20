"use client";

/**
 * WrongShake — brief screen-edge red flash + shake on incorrect answer.
 *
 * Sprint 1 (2026-04-20). Low-cost visual complement to the SFX "wrong"
 * cue: the outer ArenaShell gets ~0.5s of inner red glow + a tiny shake
 * of children. Fires from Arena match page when a verdict arrives with
 * is_correct=false.
 */

import { motion, AnimatePresence } from "framer-motion";

interface Props {
  trigger: boolean;
}

export function WrongShake({ trigger }: Props) {
  return (
    <AnimatePresence>
      {trigger && (
        <motion.div
          key={`shake-${trigger}`}
          className="pointer-events-none fixed inset-0 z-[250]"
          initial={{ opacity: 0 }}
          animate={{ opacity: [0, 1, 1, 0] }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.55 }}
          style={{
            boxShadow: "inset 0 0 120px 40px rgba(239,68,68,0.35)",
          }}
        />
      )}
    </AnimatePresence>
  );
}

/**
 * Shake variants for children of ArenaShell — pass to a motion.div wrapper.
 */
export const shakeVariants = {
  idle: { x: 0 },
  shake: {
    x: [0, -6, 6, -4, 4, 0],
    transition: { duration: 0.4 },
  },
};
