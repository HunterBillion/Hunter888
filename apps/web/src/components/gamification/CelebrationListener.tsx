"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Trophy, Flame, TrendingUp } from "lucide-react";
import { useSound } from "@/hooks/useSound";
import type { GamificationEvent } from "@/stores/useGamificationStore";

/**
 * CelebrationListener — listens for gamification events and shows
 * celebration overlays with sound. Mount once in AuthLayout.
 */
export function CelebrationListener() {
  const { playSound } = useSound();
  const [celebration, setCelebration] = useState<GamificationEvent | null>(null);

  useEffect(() => {
    function handleEvent(e: Event) {
      const detail = (e as CustomEvent<GamificationEvent>).detail;
      if (!detail) return;

      setCelebration(detail);

      // Play sound
      switch (detail.type) {
        case "xp-gain":
          playSound("xp");
          break;
        case "level-up":
          playSound("levelUp");
          break;
        case "streak-milestone":
          playSound("streak");
          break;
      }

      // Auto-dismiss
      const duration = detail.type === "level-up" ? 3000 : 2000;
      setTimeout(() => setCelebration(null), duration);
    }

    window.addEventListener("gamification", handleEvent);
    return () => window.removeEventListener("gamification", handleEvent);
  }, [playSound]);

  return (
    <AnimatePresence>
      {celebration && (
        <motion.div
          initial={{ opacity: 0, y: -20, scale: 0.9 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: -10, scale: 0.95 }}
          transition={{ type: "spring", stiffness: 400, damping: 25 }}
          className="fixed top-20 left-1/2 -translate-x-1/2 z-[200] pointer-events-none"
        >
          {celebration.type === "level-up" && (
            <div
              className="flex items-center gap-3 rounded-2xl px-6 py-4 backdrop-blur-xl"
              style={{
                background: "linear-gradient(135deg, var(--brand-deep), var(--accent))",
                boxShadow: "0 8px 40px rgba(49, 21, 115, 0.5), 0 0 0 1px rgba(255,255,255,0.1)",
              }}
            >
              <Trophy size={28} className="text-white" />
              <div>
                <div className="text-white text-lg font-bold">
                  Уровень {celebration.newLevel}!
                </div>
                <div className="text-white/70 text-sm">
                  Новые сценарии разблокированы
                </div>
              </div>
            </div>
          )}

          {celebration.type === "xp-gain" && (
            <div
              className="flex items-center gap-2 rounded-xl px-5 py-3 backdrop-blur-xl"
              style={{
                background: "color-mix(in srgb, var(--accent) 20%, transparent)",
                border: "1px solid color-mix(in srgb, var(--accent) 30%, transparent)",
                boxShadow: "0 4px 20px rgba(124, 106, 232, 0.3)",
              }}
            >
              <TrendingUp size={18} style={{ color: "var(--accent)" }} />
              <span className="font-bold font-mono text-base" style={{ color: "var(--accent)" }}>
                +{celebration.amount} XP
              </span>
            </div>
          )}

          {celebration.type === "streak-milestone" && (
            <div
              className="flex items-center gap-3 rounded-2xl px-6 py-4 backdrop-blur-xl"
              style={{
                background: "linear-gradient(135deg, rgba(232, 166, 48, 0.2), rgba(212, 168, 75, 0.1))",
                border: "1px solid rgba(232, 166, 48, 0.3)",
                boxShadow: "0 8px 32px rgba(232, 166, 48, 0.2)",
              }}
            >
              <Flame size={24} style={{ color: "var(--rank-gold)" }} />
              <div>
                <div className="font-bold text-base" style={{ color: "var(--rank-gold)" }}>
                  Серия {celebration.days} дней!
                </div>
                <div className="text-sm" style={{ color: "var(--text-muted)" }}>
                  Продолжай в том же духе
                </div>
              </div>
            </div>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
