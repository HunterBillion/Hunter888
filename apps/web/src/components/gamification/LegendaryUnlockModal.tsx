"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Crown } from "lucide-react";
import { useSound } from "@/hooks/useSound";
import { useHaptic } from "@/hooks/useHaptic";
import { Confetti } from "@/components/ui/Confetti";
import { AppIcon } from "@/components/ui/AppIcon";

interface LegendaryUnlockProps {
  title: string;
  description: string;
  icon?: string;
  onClose: () => void;
}

/**
 * Full-screen legendary unlock reveal with expanding glow,
 * confetti, sound, and haptic feedback.
 */
export function LegendaryUnlockModal({ title, description, icon, onClose }: LegendaryUnlockProps) {
  const { playSound } = useSound();
  const haptic = useHaptic();
  const [confettiTrigger, setConfettiTrigger] = useState(0);
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    playSound("legendary");
    haptic("victory");
    setConfettiTrigger((n) => n + 1);

    const timer = setTimeout(() => {
      setVisible(false);
      setTimeout(onClose, 300);
    }, 3000);

    return () => clearTimeout(timer);
  }, [playSound, haptic, onClose]);

  return (
    <>
      <Confetti trigger={confettiTrigger} />
      <AnimatePresence>
        {visible && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[210] flex items-center justify-center cursor-pointer"
            style={{ background: "rgba(0, 0, 0, 0.9)" }}
            onClick={() => {
              setVisible(false);
              setTimeout(onClose, 300);
            }}
          >
            {/* Expanding glow ring */}
            <motion.div
              className="absolute rounded-full"
              style={{
                background: "radial-gradient(circle, rgba(255, 215, 0, 0.15), transparent 70%)",
              }}
              initial={{ width: 0, height: 0, opacity: 0 }}
              animate={{ width: 600, height: 600, opacity: [0, 0.8, 0.4] }}
              transition={{ duration: 1.5, ease: "easeOut" }}
            />

            {/* Content */}
            <motion.div
              className="relative text-center space-y-6"
              initial={{ scale: 0, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.8, opacity: 0 }}
              transition={{ type: "spring", stiffness: 200, damping: 15, delay: 0.3 }}
            >
              {/* Icon with glow */}
              <motion.div
                className="mx-auto rounded-full flex items-center justify-center"
                style={{
                  width: 100,
                  height: 100,
                  background: "linear-gradient(135deg, rgba(255, 215, 0, 0.3), rgba(124, 106, 232, 0.2))",
                  border: "2px solid rgba(255, 215, 0, 0.5)",
                  boxShadow: "0 0 40px rgba(255, 215, 0, 0.3), 0 0 80px rgba(255, 215, 0, 0.1)",
                }}
                animate={{
                  boxShadow: [
                    "0 0 40px rgba(255, 215, 0, 0.3), 0 0 80px rgba(255, 215, 0, 0.1)",
                    "0 0 60px rgba(255, 215, 0, 0.5), 0 0 120px rgba(255, 215, 0, 0.2)",
                    "0 0 40px rgba(255, 215, 0, 0.3), 0 0 80px rgba(255, 215, 0, 0.1)",
                  ],
                }}
                transition={{ duration: 2, repeat: Infinity }}
              >
                {icon ? (
                  <AppIcon emoji={icon} size={48} />
                ) : (
                  <Crown size={48} style={{ color: "var(--gf-xp)" }} />
                )}
              </motion.div>

              {/* Label */}
              <motion.div
                className="font-mono text-xs uppercase tracking-widest font-bold"
                style={{ color: "var(--gf-xp)" }}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.6 }}
              >
                LEGENDARY UNLOCK
              </motion.div>

              {/* Title */}
              <motion.div
                className="font-display text-3xl font-black"
                style={{
                  color: "var(--text-primary)",
                  textShadow: "0 0 30px rgba(255, 215, 0, 0.2)",
                }}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.8 }}
              >
                {title}
              </motion.div>

              {/* Description */}
              <motion.div
                className="text-base max-w-sm mx-auto"
                style={{ color: "var(--text-muted)" }}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 1 }}
              >
                {description}
              </motion.div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
