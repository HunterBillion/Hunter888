"use client";

import { useEffect, useState, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Trophy, Flame, TrendingUp, Swords, Sparkles, Star } from "lucide-react";
import { useSound } from "@/hooks/useSound";
import { useHaptic } from "@/hooks/useHaptic";
import { Confetti } from "@/components/ui/Confetti";
import { LegendaryUnlockModal } from "@/components/gamification/LegendaryUnlockModal";
import type { GamificationEvent } from "@/stores/useGamificationStore";

/**
 * CelebrationListener — Phase Soul celebration system.
 * Listens for gamification events and shows immersive overlays with
 * sound, confetti, haptic feedback, and animations.
 * Mount once in AuthLayout.
 */
export function CelebrationListener() {
  const { playSound } = useSound();
  const haptic = useHaptic();
  const [celebration, setCelebration] = useState<GamificationEvent | null>(null);
  const [confettiTrigger, setConfettiTrigger] = useState(0);
  const [xpBursts, setXpBursts] = useState<Array<{ id: number; amount: number }>>([]);
  const [legendary, setLegendary] = useState<{ title: string; description: string; icon?: string } | null>(null);
  const burstIdRef = useRef(0);

  useEffect(() => {
    function handleEvent(e: Event) {
      const detail = (e as CustomEvent<GamificationEvent>).detail;
      if (!detail) return;

      setCelebration(detail);

      // Sound + haptic
      switch (detail.type) {
        case "xp-gain":
          playSound("xp");
          haptic("tap");
          // XP micro-burst: floating "+X XP" particle
          setXpBursts((prev) => [
            ...prev.slice(-4), // keep max 5
            { id: ++burstIdRef.current, amount: detail.amount },
          ]);
          break;
        case "level-up":
          playSound("levelUp");
          haptic("levelUp");
          setConfettiTrigger((n) => n + 1);
          break;
        case "streak-milestone":
          playSound("streak");
          haptic("success");
          break;
        case "pvp-win":
          playSound("victory");
          haptic("victory");
          setConfettiTrigger((n) => n + 1);
          break;
        case "perfect-score":
          playSound("legendary");
          haptic("victory");
          setConfettiTrigger((n) => n + 1);
          break;
        case "first-session":
          playSound("success");
          haptic("success");
          setConfettiTrigger((n) => n + 1);
          break;
        case "legendary-unlock":
          setLegendary({ title: detail.title, description: detail.description, icon: detail.icon });
          return; // LegendaryUnlockModal handles its own lifecycle
        case "rank-up":
          playSound("legendary");
          haptic("victory");
          setConfettiTrigger((n) => n + 1);
          break;
      }

      // Auto-dismiss: level-up gets full-screen (shorter auto, user can click), rest are toasts
      const duration =
        detail.type === "level-up" || detail.type === "rank-up" ? 3000 :
        detail.type === "pvp-win" || detail.type === "perfect-score" ? 3000 :
        detail.type === "xp-gain" ? 1500 :
        2500;
      setTimeout(() => setCelebration(null), duration);
    }

    window.addEventListener("gamification", handleEvent);
    return () => window.removeEventListener("gamification", handleEvent);
  }, [playSound, haptic]);

  // Clean up XP bursts after animation
  useEffect(() => {
    if (xpBursts.length === 0) return;
    const timer = setTimeout(() => {
      setXpBursts((prev) => prev.slice(1));
    }, 1200);
    return () => clearTimeout(timer);
  }, [xpBursts]);

  return (
    <>
      <Confetti trigger={confettiTrigger} />

      {/* Legendary unlock modal */}
      {legendary && (
        <LegendaryUnlockModal
          title={legendary.title}
          description={legendary.description}
          icon={legendary.icon}
          onClose={() => setLegendary(null)}
        />
      )}

      {/* XP Micro-bursts — floating "+X XP" particles */}
      <div className="fixed top-16 left-1/2 -translate-x-1/2 z-[201] pointer-events-none">
        <AnimatePresence>
          {xpBursts.map((burst) => (
            <motion.div
              key={burst.id}
              initial={{ opacity: 0, y: 0, scale: 0.5 }}
              animate={{ opacity: [0, 1, 1, 0], y: -80, scale: [0.5, 1.2, 1, 0.8] }}
              exit={{ opacity: 0 }}
              transition={{ duration: 1, ease: "easeOut" }}
              className="absolute left-1/2 -translate-x-1/2 font-mono font-bold text-lg whitespace-nowrap"
              style={{ color: "var(--accent)", textShadow: "0 0 12px var(--accent-glow)" }}
            >
              +{burst.amount} XP
              {/* Particle dots */}
              {[...Array(4)].map((_, i) => (
                <motion.span
                  key={i}
                  className="absolute rounded-full"
                  style={{
                    width: 4,
                    height: 4,
                    background: "var(--accent)",
                    left: "50%",
                    top: "50%",
                  }}
                  initial={{ x: 0, y: 0, opacity: 1 }}
                  animate={{
                    x: [0, (Math.cos((i * Math.PI) / 2) * 30)],
                    y: [0, (Math.sin((i * Math.PI) / 2) * 30)],
                    opacity: [1, 0],
                    scale: [1, 0],
                  }}
                  transition={{ duration: 0.6, delay: 0.1 }}
                />
              ))}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      <AnimatePresence>
        {celebration && (
          <>
            {/* ── LEVEL UP: Full-screen overlay ── */}
            {celebration.type === "level-up" && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.3 }}
                className="fixed inset-0 z-[200] flex items-center justify-center"
                style={{ background: "rgba(0, 0, 0, 0.85)" }}
                onClick={() => setCelebration(null)}
              >
                <motion.div
                  initial={{ scale: 0.3, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  exit={{ scale: 0.8, opacity: 0 }}
                  transition={{ type: "spring", stiffness: 200, damping: 15 }}
                  className="text-center space-y-4"
                >
                  {/* Glowing ring */}
                  <motion.div
                    className="mx-auto rounded-full flex items-center justify-center"
                    style={{
                      width: 120,
                      height: 120,
                      background: "linear-gradient(135deg, var(--brand-deep), var(--accent))",
                      boxShadow: "0 0 60px var(--accent-glow), 0 0 120px rgba(49, 21, 115, 0.4)",
                    }}
                    animate={{ scale: [1, 1.08, 1] }}
                    transition={{ duration: 1.5, repeat: Infinity, ease: "easeInOut" }}
                  >
                    <Trophy size={48} className="text-white" />
                  </motion.div>

                  {/* Level number */}
                  <motion.div
                    className="font-display font-black"
                    style={{
                      fontSize: "72px",
                      lineHeight: 1,
                      color: "var(--accent)",
                      textShadow: "0 0 40px var(--accent-glow)",
                    }}
                    initial={{ scale: 0 }}
                    animate={{ scale: [0, 1.3, 1] }}
                    transition={{ delay: 0.3, duration: 0.5 }}
                  >
                    {celebration.newLevel}
                  </motion.div>

                  <motion.div
                    className="font-mono text-sm tracking-[0.3em] uppercase"
                    style={{ color: "var(--text-muted)" }}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.5 }}
                  >
                    LEVEL REACHED
                  </motion.div>

                  <motion.div
                    className="text-base font-medium"
                    style={{ color: "var(--text-secondary)" }}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.7 }}
                  >
                    Новые сценарии разблокированы
                  </motion.div>
                </motion.div>
              </motion.div>
            )}

            {/* ── RANK UP: Full-screen overlay ── */}
            {celebration.type === "rank-up" && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.3 }}
                className="fixed inset-0 z-[200] flex items-center justify-center"
                style={{ background: "rgba(0, 0, 0, 0.85)" }}
                onClick={() => setCelebration(null)}
              >
                <motion.div
                  initial={{ scale: 0.3, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  exit={{ scale: 0.8, opacity: 0 }}
                  transition={{ type: "spring", stiffness: 200, damping: 15 }}
                  className="text-center space-y-4"
                >
                  <motion.div
                    className="mx-auto rounded-full flex items-center justify-center"
                    style={{
                      width: 100,
                      height: 100,
                      background: "linear-gradient(135deg, rgba(255, 215, 0, 0.3), rgba(124, 106, 232, 0.2))",
                      boxShadow: "0 0 60px rgba(255, 215, 0, 0.3)",
                    }}
                    animate={{ scale: [1, 1.08, 1] }}
                    transition={{ duration: 1.5, repeat: Infinity }}
                  >
                    <Trophy size={44} style={{ color: "var(--gf-xp)" }} />
                  </motion.div>
                  <motion.div
                    className="font-display font-black text-3xl"
                    style={{ color: "var(--gf-xp)", textShadow: "0 0 30px rgba(255, 215, 0, 0.3)" }}
                    initial={{ scale: 0 }}
                    animate={{ scale: [0, 1.2, 1] }}
                    transition={{ delay: 0.3 }}
                  >
                    {celebration.newRank}
                  </motion.div>
                  <motion.div
                    className="font-mono text-sm tracking-[0.3em] uppercase"
                    style={{ color: "var(--text-muted)" }}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.5 }}
                  >
                    НОВЫЙ РАНГ ДОСТИГНУТ
                  </motion.div>
                  <motion.div
                    className="font-mono text-lg font-bold"
                    style={{ color: celebration.ratingDelta > 0 ? "var(--success)" : "var(--text-secondary)" }}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.7 }}
                  >
                    {celebration.ratingDelta > 0 ? "+" : ""}{celebration.ratingDelta} ELO
                  </motion.div>
                </motion.div>
              </motion.div>
            )}

            {/* ── XP GAIN: Small toast (no overlay needed, micro-burst above handles it) ── */}
            {celebration.type === "xp-gain" && (
              <motion.div
                initial={{ opacity: 0, y: -20, scale: 0.9 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -10, scale: 0.95 }}
                transition={{ type: "spring", stiffness: 400, damping: 25 }}
                className="fixed top-20 left-1/2 -translate-x-1/2 z-[200] pointer-events-none"
              >
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
              </motion.div>
            )}

            {/* ── STREAK MILESTONE: Toast with animated flame ── */}
            {celebration.type === "streak-milestone" && (
              <motion.div
                initial={{ opacity: 0, y: -20, scale: 0.9 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -10, scale: 0.95 }}
                transition={{ type: "spring", stiffness: 400, damping: 25 }}
                className="fixed top-20 left-1/2 -translate-x-1/2 z-[200] pointer-events-none"
              >
                <div
                  className="flex items-center gap-3 rounded-2xl px-6 py-4 backdrop-blur-xl"
                  style={{
                    background: "linear-gradient(135deg, rgba(232, 166, 48, 0.2), rgba(212, 168, 75, 0.1))",
                    border: "1px solid rgba(232, 166, 48, 0.3)",
                    boxShadow: "0 8px 32px rgba(232, 166, 48, 0.2)",
                  }}
                >
                  {/* Animated flame */}
                  <motion.div
                    animate={{
                      scale: [1, 1.2, 0.95, 1.15, 1],
                      rotate: [0, -5, 5, -3, 0],
                    }}
                    transition={{ duration: 0.8, repeat: Infinity, repeatType: "loop" }}
                  >
                    <Flame size={28} style={{ color: "var(--rank-gold)", filter: "drop-shadow(0 0 8px rgba(232, 166, 48, 0.6))" }} />
                  </motion.div>
                  <div>
                    <div className="font-bold text-base" style={{ color: "var(--rank-gold)" }}>
                      Серия {celebration.days} {celebration.days >= 30 ? "дней!" : celebration.days >= 14 ? "дней!" : celebration.days >= 7 ? "дней!" : "дня!"}
                    </div>
                    <div className="text-sm" style={{ color: "var(--text-muted)" }}>
                      {celebration.days >= 30 ? "Легендарная серия! Ты неудержим" :
                       celebration.days >= 14 ? "Впечатляющая дисциплина!" :
                       celebration.days >= 7 ? "Неделя стабильных тренировок!" :
                       "Продолжай в том же духе"}
                    </div>
                  </div>
                </div>
              </motion.div>
            )}

            {/* ── PVP WIN: Enhanced toast ── */}
            {celebration.type === "pvp-win" && (
              <motion.div
                initial={{ opacity: 0, y: -20, scale: 0.9 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -10, scale: 0.95 }}
                transition={{ type: "spring", stiffness: 400, damping: 25 }}
                className="fixed top-20 left-1/2 -translate-x-1/2 z-[200] pointer-events-none"
              >
                <div
                  className="flex items-center gap-3 rounded-2xl px-6 py-4 backdrop-blur-xl"
                  style={{
                    background: "linear-gradient(135deg, rgba(232, 166, 48, 0.25), rgba(255, 215, 0, 0.1))",
                    border: "1px solid rgba(255, 215, 0, 0.4)",
                    boxShadow: "0 8px 40px rgba(255, 215, 0, 0.3)",
                  }}
                >
                  <motion.div
                    animate={{ rotate: [0, -15, 15, 0] }}
                    transition={{ duration: 0.5, delay: 0.2 }}
                  >
                    <Swords size={28} style={{ color: "var(--gf-xp)" }} />
                  </motion.div>
                  <div>
                    <div className="font-bold text-lg" style={{ color: "var(--gf-xp)" }}>
                      Победа в дуэли!
                    </div>
                    <div className="text-sm" style={{ color: "var(--text-muted)" }}>
                      Соперник повержен
                    </div>
                  </div>
                </div>
              </motion.div>
            )}

            {/* ── PERFECT SCORE: Gold stars + glow ── */}
            {celebration.type === "perfect-score" && (
              <motion.div
                initial={{ opacity: 0, y: -20, scale: 0.9 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -10, scale: 0.95 }}
                transition={{ type: "spring", stiffness: 400, damping: 25 }}
                className="fixed top-20 left-1/2 -translate-x-1/2 z-[200] pointer-events-none"
              >
                <div
                  className="relative flex items-center gap-3 rounded-2xl px-6 py-4 backdrop-blur-xl"
                  style={{
                    background: "linear-gradient(135deg, rgba(255, 215, 0, 0.2), rgba(124, 106, 232, 0.15))",
                    border: "2px solid rgba(255, 215, 0, 0.5)",
                    boxShadow: "0 8px 40px rgba(255, 215, 0, 0.3), 0 0 60px rgba(124, 106, 232, 0.15)",
                  }}
                >
                  {/* Rotating stars */}
                  {[0, 1, 2, 3].map((i) => (
                    <motion.div
                      key={i}
                      className="absolute"
                      style={{
                        top: i < 2 ? -6 : undefined,
                        bottom: i >= 2 ? -6 : undefined,
                        left: i % 2 === 0 ? -6 : undefined,
                        right: i % 2 !== 0 ? -6 : undefined,
                      }}
                      animate={{ rotate: 360, scale: [0.8, 1.2, 0.8] }}
                      transition={{ duration: 3, repeat: Infinity, delay: i * 0.3 }}
                    >
                      <Star size={14} fill="var(--gf-xp)" style={{ color: "var(--gf-xp)" }} />
                    </motion.div>
                  ))}
                  <Star size={28} fill="var(--gf-xp)" style={{ color: "var(--gf-xp)" }} />
                  <div>
                    <div className="font-bold text-lg" style={{ color: "var(--gf-xp)" }}>
                      Идеальный результат! {celebration.score}/100
                    </div>
                    <div className="text-sm" style={{ color: "var(--text-muted)" }}>
                      Мастерство на высшем уровне
                    </div>
                  </div>
                </div>
              </motion.div>
            )}

            {/* ── FIRST SESSION: Welcome celebration ── */}
            {celebration.type === "first-session" && (
              <motion.div
                initial={{ opacity: 0, y: -20, scale: 0.9 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -10, scale: 0.95 }}
                transition={{ type: "spring", stiffness: 400, damping: 25 }}
                className="fixed top-20 left-1/2 -translate-x-1/2 z-[200] pointer-events-none"
              >
                <div
                  className="flex items-center gap-3 rounded-2xl px-6 py-4 backdrop-blur-xl"
                  style={{
                    background: "linear-gradient(135deg, var(--brand-deep), var(--accent))",
                    boxShadow: "0 8px 40px rgba(49, 21, 115, 0.5), 0 0 0 1px rgba(255,255,255,0.1)",
                  }}
                >
                  <motion.div
                    animate={{ rotate: [0, 15, -15, 10, -10, 0] }}
                    transition={{ duration: 1, delay: 0.2 }}
                  >
                    <Sparkles size={28} className="text-white" />
                  </motion.div>
                  <div>
                    <div className="text-white text-lg font-bold">
                      Первая охота завершена!
                    </div>
                    <div className="text-white/70 text-sm">
                      Добро пожаловать в мир Hunter888
                    </div>
                  </div>
                </div>
              </motion.div>
            )}
          </>
        )}
      </AnimatePresence>
    </>
  );
}
