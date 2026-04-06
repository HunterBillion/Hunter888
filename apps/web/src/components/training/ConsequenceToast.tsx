"use client";

import { useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { AlertTriangle, Zap } from "lucide-react";
import type { ConsequenceEvent } from "@/types/story";
import { useScreenShake } from "@/components/ui/ScreenShake";
import { useHaptic } from "@/hooks/useHaptic";

interface Props {
  consequence: ConsequenceEvent | null;
  onDismiss: () => void;
}

export function ConsequenceToast({ consequence, onDismiss }: Props) {
  const shake = useScreenShake();
  const haptic = useHaptic();

  // Trigger haptic + screen shake when consequence appears
  useEffect(() => {
    if (!consequence) return;
    const isHigh = consequence.severity >= 0.7;
    shake(isHigh ? "heavy" : "medium");
    haptic(isHigh ? "error" : "impact");
  }, [consequence, shake, haptic]);

  const isHigh = consequence ? consequence.severity >= 0.7 : false;
  const color = isHigh ? "var(--neon-red, #FF3333)" : "var(--warning, #F59E0B)";
  const bgColor = isHigh ? "rgba(255,51,51,0.1)" : "rgba(245,158,11,0.1)";
  const borderColor = isHigh ? "rgba(255,51,51,0.3)" : "rgba(245,158,11,0.3)";

  return (
    <AnimatePresence>
      {consequence && (
      <motion.div
        initial={{ opacity: 0, y: 40, scale: 0.9 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 40, scale: 0.9 }}
        className="fixed bottom-6 right-6 z-[170] max-w-sm cursor-pointer"
        onClick={onDismiss}
      >
        <div
          className="rounded-xl p-4 backdrop-blur-xl"
          style={{
            background: bgColor,
            border: `1px solid ${borderColor}`,
            boxShadow: `0 0 30px ${borderColor}`,
          }}
        >
          <div className="flex items-start gap-3">
            <div className="mt-0.5">
              {isHigh ? (
                <AlertTriangle size={18} style={{ color }} />
              ) : (
                <Zap size={18} style={{ color }} />
              )}
            </div>
            <div>
              <div className="font-mono text-xs tracking-widest uppercase" style={{ color }}>
                ПОСЛЕДСТВИЕ · ЗВОНОК {consequence.call}
              </div>
              <div className="text-sm mt-1 font-medium" style={{ color: "var(--text-primary)" }}>
                {consequence.type.replace(/_/g, " ")}
              </div>
              <div className="text-xs mt-1" style={{ color: "var(--text-secondary)" }}>
                {consequence.detail}
              </div>
              {/* Severity bar */}
              <div className="mt-2 h-1 w-full rounded-full" style={{ background: "var(--input-bg)" }}>
                <motion.div
                  className="h-full rounded-full"
                  style={{ background: color }}
                  initial={{ width: 0 }}
                  animate={{ width: `${consequence.severity * 100}%` }}
                  transition={{ duration: 0.8, delay: 0.3 }}
                />
              </div>
            </div>
          </div>
        </div>
      </motion.div>
      )}
    </AnimatePresence>
  );
}
