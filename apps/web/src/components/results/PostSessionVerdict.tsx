"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Star } from "lucide-react";
import { useSound } from "@/hooks/useSound";
import { Confetti } from "@/components/ui/Confetti";

interface PostSessionVerdictProps {
  score: number;
  onContinue: () => void;
  xpGained?: number;
}

function getVerdict(score: number): { word: string; wordRu: string; color: string; glow: string } {
  if (score >= 90) return { word: "DOMINANT", wordRu: "ДОМИНИРУЮЩИЙ", color: "var(--success)", glow: "color-mix(in srgb, var(--success) 50%, transparent)" };
  if (score >= 75) return { word: "CONFIDENT", wordRu: "УВЕРЕННЫЙ", color: "var(--accent)", glow: "color-mix(in srgb, var(--accent) 50%, transparent)" };
  if (score >= 60) return { word: "STEADY", wordRu: "СТАБИЛЬНЫЙ", color: "var(--gf-xp)", glow: "color-mix(in srgb, var(--gf-xp) 50%, transparent)" };
  if (score >= 40) return { word: "HESITANT", wordRu: "НЕУВЕРЕННЫЙ", color: "var(--info)", glow: "color-mix(in srgb, var(--info) 50%, transparent)" };
  return { word: "LOST CONTROL", wordRu: "ПОТЕРЯЛ КОНТРОЛЬ", color: "var(--danger)", glow: "color-mix(in srgb, var(--danger) 50%, transparent)" };
}

export function PostSessionVerdict({ score, onContinue, xpGained = 0 }: PostSessionVerdictProps) {
  const [phase, setPhase] = useState<"counting" | "verdict" | "details">("counting");
  const [displayScore, setDisplayScore] = useState(0);
  const [confettiTrigger, setConfettiTrigger] = useState(0);
  const { playSound } = useSound();
  const verdict = getVerdict(score);
  const isPerfect = score >= 90;

  // Count-up animation
  useEffect(() => {
    if (phase !== "counting") return;
    const duration = 1500;
    const steps = 60;
    const increment = score / steps;
    let current = 0;
    let step = 0;

    const timer = setInterval(() => {
      step++;
      current = Math.min(score, Math.round(increment * step));
      setDisplayScore(current);

      if (step >= steps) {
        clearInterval(timer);
        setDisplayScore(score);
        setTimeout(() => setPhase("verdict"), 300);
      }
    }, duration / steps);

    return () => clearInterval(timer);
  }, [phase, score]);

  // Auto-advance to details
  useEffect(() => {
    if (phase === "verdict") {
      // Trigger confetti for perfect scores
      if (isPerfect) {
        setConfettiTrigger((n) => n + 1);
        playSound("legendary");
      }
      const timer = setTimeout(() => setPhase("details"), 2000);
      return () => clearTimeout(timer);
    }
  }, [phase, isPerfect, playSound]);

  return (
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center"
      style={{ background: "var(--bg-primary)" }}
    >
      <Confetti trigger={confettiTrigger} />

      <div className="relative z-[202] text-center">
        <AnimatePresence mode="wait">
          {/* Phase 1: Score count-up */}
          {phase === "counting" && (
            <motion.div
              key="counting"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0, scale: 1.5 }}
            >
              {/* Gold frame for perfect scores */}
              <div className="relative inline-block">
                {isPerfect && (
                  <>
                    {/* Rotating stars around the score */}
                    {[0, 1, 2, 3].map((i) => (
                      <motion.div
                        key={i}
                        className="absolute"
                        style={{
                          top: i === 0 ? -20 : i === 2 ? undefined : "50%",
                          bottom: i === 2 ? -20 : undefined,
                          left: i === 3 ? -20 : i === 1 ? undefined : "50%",
                          right: i === 1 ? -20 : undefined,
                          transform: "translate(-50%, -50%)",
                        }}
                        animate={{
                          rotate: 360,
                          scale: [0.6, 1, 0.6],
                        }}
                        transition={{
                          rotate: { duration: 4, repeat: Infinity, ease: "linear" },
                          scale: { duration: 2, repeat: Infinity, delay: i * 0.5 },
                        }}
                      >
                        <Star size={18} fill="var(--gf-xp)" style={{ color: "var(--gf-xp)", filter: "drop-shadow(0 0 6px rgba(255, 215, 0, 0.6))" }} />
                      </motion.div>
                    ))}
                    {/* Gold glow ring */}
                    <motion.div
                      className="absolute inset-[-24px] rounded-full pointer-events-none"
                      style={{
                        border: "2px solid rgba(255, 215, 0, 0.3)",
                        boxShadow: "0 0 40px rgba(255, 215, 0, 0.15), inset 0 0 40px rgba(255, 215, 0, 0.05)",
                      }}
                      animate={{ opacity: [0.5, 1, 0.5] }}
                      transition={{ duration: 2, repeat: Infinity }}
                    />
                  </>
                )}
                <motion.div
                  className="font-display font-bold"
                  style={{
                    fontSize: "140px",
                    lineHeight: 1,
                    color: verdict.color,
                    textShadow: `0 0 60px ${verdict.glow}`,
                  }}
                >
                  {displayScore}
                </motion.div>
              </div>
              <div className="font-mono text-sm tracking-[0.3em] mt-2" style={{ color: "var(--text-muted)" }}>
                MASTERY SCORE
              </div>
            </motion.div>
          )}

          {/* Phase 2: Verdict word with GLITCH effect */}
          {phase === "verdict" && (
            <motion.div
              key="verdict"
              initial={{ scale: 3, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ opacity: 0, y: -30 }}
              transition={{ type: "spring", stiffness: 200, damping: 15 }}
              className="space-y-4"
            >
              {/* Full-screen color flash */}
              <div
                className="fixed inset-0 emotion-flash pointer-events-none z-[203]"
                style={{ background: verdict.color }}
              />
              <div
                className="font-display font-black tracking-[0.2em] glitch-text"
                data-text={verdict.word}
                style={{
                  fontSize: "80px",
                  lineHeight: 1.1,
                  color: verdict.color,
                  textShadow: `0 0 60px ${verdict.glow}, 0 0 120px ${verdict.glow}`,
                }}
              >
                {verdict.word}
              </div>
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.4 }}
                className="font-mono text-xl tracking-[0.3em]"
                style={{ color: "var(--text-secondary)" }}
              >
                {verdict.wordRu}
              </motion.div>
            </motion.div>
          )}

          {/* Phase 3: Summary + continue */}
          {phase === "details" && (
            <motion.div
              key="details"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="space-y-8"
            >
              {/* Score with optional gold frame */}
              <div className="relative inline-block">
                {isPerfect && (
                  <motion.div
                    className="absolute inset-[-16px] rounded-2xl pointer-events-none"
                    style={{
                      border: "2px solid rgba(255, 215, 0, 0.4)",
                      boxShadow: "0 0 30px rgba(255, 215, 0, 0.15)",
                      background: "linear-gradient(135deg, rgba(255, 215, 0, 0.05), transparent)",
                    }}
                    animate={{ opacity: [0.6, 1, 0.6] }}
                    transition={{ duration: 2, repeat: Infinity }}
                  />
                )}
                <div
                  className="font-display text-7xl font-bold"
                  style={{ color: verdict.color, textShadow: `0 0 30px ${verdict.glow}` }}
                >
                  {score}
                  <span className="text-3xl" style={{ color: "var(--text-muted)" }}>/100</span>
                </div>
                <div
                  className="font-display text-2xl font-bold tracking-[0.15em] mt-2"
                  style={{ color: verdict.color }}
                >
                  {verdict.word}
                </div>
              </div>

              {/* XP gained */}
              {xpGained > 0 && (
                <motion.div
                  initial={{ scale: 0, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  transition={{ delay: 0.3, type: "spring" }}
                  className="inline-flex items-center gap-2 rounded-full px-5 py-2"
                  style={{
                    background: "var(--accent-muted)",
                    border: "1px solid var(--accent)",
                    boxShadow: `0 0 20px ${verdict.glow}`,
                  }}
                >
                  <span className="font-display text-lg font-bold" style={{ color: "var(--accent)" }}>
                    +{xpGained} XP
                  </span>
                </motion.div>
              )}

              {/* Continue button */}
              <motion.button
                onClick={onContinue}
                className="btn-neon flex items-center gap-2 mx-auto text-lg px-8 py-4"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.5 }}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
              >
                Разбор полёта
              </motion.button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
