"use client";

import { useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Award } from "lucide-react";
import { useSound } from "@/hooks/useSound";
import { useReducedMotion } from "@/hooks/useReducedMotion";

interface Achievement {
  id: string;
  title: string;
  description: string;
  icon?: string;
}

interface AchievementToastProps {
  achievement: Achievement | null;
  onClose: () => void;
}

export function AchievementToast({ achievement, onClose }: AchievementToastProps) {
  const { playSound } = useSound();
  const reducedMotion = useReducedMotion();

  // Play sound when achievement appears
  useEffect(() => {
    if (achievement) {
      playSound("success");
    }
  }, [achievement, playSound]);

  return (
    <AnimatePresence>
      {achievement && (
        <motion.div
          initial={{ opacity: 0, y: -50, x: "-50%" }}
          animate={{ opacity: 1, y: 0, x: "-50%" }}
          exit={{ opacity: 0, y: -30, x: "-50%" }}
          className="fixed top-6 left-1/2 z-[200] glass-panel px-6 py-4 flex items-center gap-4"
          style={{
            borderColor: "rgba(139,92,246,0.3)",
            boxShadow: "0 0 30px rgba(139,92,246,0.2)",
            minWidth: "300px",
          }}
          onAnimationComplete={(def) => {
            if (typeof def === "object" && "opacity" in def && def.opacity === 1) {
              setTimeout(onClose, 3000);
            }
          }}
        >
          <motion.div
            className="flex h-12 w-12 items-center justify-center rounded-xl"
            style={{ background: "var(--accent)", boxShadow: "0 0 20px rgba(139,92,246,0.4)" }}
            animate={reducedMotion ? {} : { rotate: [0, -10, 10, -5, 5, 0] }}
            transition={reducedMotion ? {} : { duration: 0.6, delay: 0.3 }}
          >
            {achievement.icon ? (
              <span className="text-xl">{achievement.icon}</span>
            ) : (
              <Award size={22} className="text-white" />
            )}
          </motion.div>
          <div>
            <div className="font-mono text-[10px] uppercase tracking-widest" style={{ color: "var(--accent)" }}>
              ACHIEVEMENT UNLOCKED
            </div>
            <div className="font-display text-sm font-bold mt-0.5" style={{ color: "var(--text-primary)" }}>
              {achievement.title}
            </div>
            <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
              {achievement.description}
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
