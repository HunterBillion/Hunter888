"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Award } from "lucide-react";
import { AppIcon } from "@/components/ui/AppIcon";
import { useSound } from "@/hooks/useSound";
import { useReducedMotion } from "@/hooks/useReducedMotion";
import { Confetti } from "@/components/ui/Confetti";
import { useScreenShake } from "@/components/ui/ScreenShake";
import { useHaptic } from "@/hooks/useHaptic";

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
  const [confettiTrigger, setConfettiTrigger] = useState(0);
  const shake = useScreenShake();
  const haptic = useHaptic();

  useEffect(() => {
    if (achievement) {
      playSound("success");
      setConfettiTrigger((n) => n + 1);
      shake("victory");
      haptic("success");
    }
  }, [achievement, playSound, shake, haptic]);

  return (
    <>
    <Confetti trigger={confettiTrigger} />
    <AnimatePresence>
      {achievement && (
        <motion.div
          initial={{ opacity: 0, y: -60, x: "-50%", scale: 0.9 }}
          animate={{ opacity: 1, y: 0, x: "-50%", scale: 1 }}
          exit={{ opacity: 0, y: -40, x: "-50%", scale: 0.95 }}
          transition={{ type: "spring", stiffness: 400, damping: 25 }}
          className="fixed top-6 left-1/2 z-[200] glass-panel overflow-hidden flex items-center gap-4"
          style={{
            borderColor: "rgba(124,106,232,0.35)",
            boxShadow: "0 0 40px rgba(124,106,232,0.25), 0 0 80px rgba(124,106,232,0.08)",
            minWidth: "340px",
            padding: "0",
          }}
          onAnimationComplete={(def) => {
            if (typeof def === "object" && "opacity" in def && def.opacity === 1) {
              setTimeout(onClose, 4000);
            }
          }}
        >
          {/* Animated top border — sweep effect */}
          <motion.div
            className="absolute top-0 left-0 right-0 h-[2px]"
            style={{ background: "linear-gradient(90deg, transparent, var(--accent), var(--magenta), transparent)" }}
            initial={{ scaleX: 0 }}
            animate={{ scaleX: 1 }}
            transition={{ duration: 0.8, delay: 0.2, ease: "easeOut" }}
          />

          {/* Icon */}
          <motion.div
            className="flex h-full items-center justify-center px-5 py-5 self-stretch"
            style={{
              background: "linear-gradient(135deg, var(--accent), rgba(124,106,232,0.7))",
            }}
            animate={reducedMotion ? {} : { rotate: [0, -10, 10, -5, 5, 0] }}
            transition={reducedMotion ? {} : { duration: 0.6, delay: 0.3 }}
          >
            {achievement.icon ? (
              <AppIcon emoji={achievement.icon} size={28} />
            ) : (
              <Award size={26} className="text-white" />
            )}
          </motion.div>

          {/* Content */}
          <div className="py-4 pr-5">
            <motion.div
              className="font-mono text-xs uppercase tracking-wider font-bold"
              style={{ color: "var(--accent)" }}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.15 }}
            >
              {"> ACHIEVEMENT_UNLOCKED"}
            </motion.div>
            <motion.div
              className="font-display text-base font-black mt-1"
              style={{ color: "var(--text-primary)" }}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.25 }}
            >
              {achievement.title}
            </motion.div>
            <motion.div
              className="text-xs mt-1"
              style={{ color: "var(--text-muted)" }}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.35 }}
            >
              {achievement.description}
            </motion.div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
    </>
  );
}
