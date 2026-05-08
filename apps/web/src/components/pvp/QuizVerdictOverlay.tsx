"use client";

/**
 * QuizVerdictOverlay — Phase 2 (PR-22).
 *
 * Большая «карточка вердикта» появляется НАД областью вопроса как только
 * приходит feedback от backend. Не подменяет chat (история ответов всё ещё
 * есть в чате) — это «фокусный» layer для свежего вердикта.
 *
 * Particle-burst:  6 искр разлетаются под случайными углами с stagger
 * Auto-advance:    в блице через 2 сек skipNext()
 *                  в тематик/диалог — ждём ручного клика «Далее →»
 * Dismissal:       вызывается из page.tsx когда currentQuestion инкрементировался
 */

import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { CheckCircle2, XCircle, AlertCircle, Compass, BookOpen, ArrowRight } from "lucide-react";
import type { QuizMessage } from "@/stores/useKnowledgeStore";

interface QuizVerdictOverlayProps {
  /** Last feedback message — null когда нет свежего вердикта (overlay скрыт). */
  verdict: QuizMessage | null;
  /** Если true — auto-advance через autoAdvanceMs */
  autoAdvance: boolean;
  autoAdvanceMs?: number;
  /** Колл-бэк когда юзер кликает «Далее» или auto-advance срабатывает. */
  onDismiss: () => void;
}

type Level = "correct" | "partial" | "off_topic" | "wrong";

const PALETTE: Record<Level, {
  color: string;
  bgGlow: string;
  label: string;
  Icon: typeof CheckCircle2;
}> = {
  correct: {
    color: "var(--success, #22c55e)",
    bgGlow: "rgba(34,197,94,0.18)",
    label: "ВЕРНО",
    Icon: CheckCircle2,
  },
  partial: {
    color: "var(--warning, #f59e0b)",
    bgGlow: "rgba(245,158,11,0.18)",
    label: "ПОЧТИ",
    Icon: AlertCircle,
  },
  off_topic: {
    color: "#60a5fa",
    bgGlow: "rgba(96,165,250,0.18)",
    label: "НЕ ПО ТЕМЕ",
    Icon: Compass,
  },
  wrong: {
    color: "var(--danger, #ef4444)",
    bgGlow: "rgba(239,68,68,0.18)",
    label: "НЕВЕРНО",
    Icon: XCircle,
  },
};

/** 6 randomly-angled sparks animating outward from centre. */
function ParticleBurst({ color, count = 8 }: { color: string; count?: number }) {
  // Generate stable random angles per render-key (Math.random in render OK
  // since AnimatePresence remount on key-change).
  const sparks = useMemo(
    () =>
      Array.from({ length: count }).map(() => ({
        angle: Math.random() * Math.PI * 2,
        distance: 60 + Math.random() * 40,
        delay: Math.random() * 0.08,
        size: 3 + Math.random() * 3,
      })),
    [count],
  );
  return (
    <div className="absolute inset-0 pointer-events-none flex items-center justify-center">
      {sparks.map((s, i) => (
        <motion.span
          key={i}
          className="absolute rounded-full"
          style={{
            background: color,
            width: s.size,
            height: s.size,
            boxShadow: `0 0 8px ${color}`,
          }}
          initial={{ opacity: 1, x: 0, y: 0, scale: 0 }}
          animate={{
            opacity: 0,
            x: Math.cos(s.angle) * s.distance,
            y: Math.sin(s.angle) * s.distance,
            scale: [0, 1.4, 0.6],
          }}
          transition={{ duration: 0.85, delay: s.delay, ease: "easeOut" }}
        />
      ))}
    </div>
  );
}

/** Countdown-ring внутри кнопки «Далее» — 0..1 fill. */
function CountdownRing({ progress, color }: { progress: number; color: string }) {
  const r = 9;
  const circ = 2 * Math.PI * r;
  return (
    <svg
      width={22}
      height={22}
      style={{ shapeRendering: "geometricPrecision", transform: "rotate(-90deg)" }}
    >
      <circle cx={11} cy={11} r={r} fill="none" stroke="rgba(255,255,255,0.18)" strokeWidth={2} />
      <circle
        cx={11}
        cy={11}
        r={r}
        fill="none"
        stroke={color}
        strokeWidth={2}
        strokeLinecap="round"
        strokeDasharray={circ}
        strokeDashoffset={circ * (1 - progress)}
        style={{ transition: "stroke-dashoffset 60ms linear" }}
      />
    </svg>
  );
}

export function QuizVerdictOverlay({
  verdict,
  autoAdvance,
  autoAdvanceMs = 2000,
  onDismiss,
}: QuizVerdictOverlayProps) {
  const [progress, setProgress] = useState(0);
  const visible = verdict !== null;
  const verdictId = verdict?.id ?? null; // changes with each new verdict

  // Reset countdown when new verdict arrives.
  useEffect(() => {
    if (!visible || !autoAdvance) {
      setProgress(0);
      return;
    }
    const start = Date.now();
    const tick = setInterval(() => {
      const elapsed = Date.now() - start;
      const p = Math.min(1, elapsed / autoAdvanceMs);
      setProgress(p);
      if (p >= 1) {
        clearInterval(tick);
        onDismiss();
      }
    }, 60);
    return () => clearInterval(tick);
  }, [visible, autoAdvance, autoAdvanceMs, onDismiss, verdictId]);

  if (!verdict) return null;
  const level: Level = (verdict.verdictLevel as Level) ?? (verdict.isCorrect ? "correct" : "wrong");
  const { color, bgGlow, label, Icon } = PALETTE[level];
  const rightAnswer = (verdict.correctAnswer ?? "").trim();
  const explanation = (verdict.explanation ?? "").trim();
  const showRightAnswer = level !== "correct" && rightAnswer;
  const articleRef = verdict.articleRef;
  const personalityComment = verdict.personalityComment;

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={verdictId}
        initial={{ opacity: 0, y: 16, scale: 0.96 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: -8, scale: 0.98 }}
        transition={{ type: "spring", stiffness: 280, damping: 22 }}
        className="relative rounded-2xl overflow-hidden"
        style={{
          background: `linear-gradient(135deg, ${bgGlow} 0%, rgba(255,255,255,0.02) 60%, rgba(255,255,255,0.04) 100%)`,
          border: `1px solid ${color}`,
          boxShadow: `0 12px 48px ${bgGlow}, 0 0 0 1px ${color}40, inset 0 1px 0 rgba(255,255,255,0.08)`,
          backdropFilter: "blur(24px) saturate(1.4)",
          WebkitBackdropFilter: "blur(24px) saturate(1.4)",
        }}
      >
        {/* Particle burst — играет 1 раз при mount */}
        <ParticleBurst color={color} />

        <div className="relative px-5 py-4">
          {/* Большой icon + label */}
          <div className="flex items-center gap-3 mb-3">
            <motion.div
              initial={{ scale: 0, rotate: -180 }}
              animate={{ scale: 1, rotate: 0 }}
              transition={{ type: "spring", stiffness: 320, damping: 18, delay: 0.05 }}
              className="flex items-center justify-center rounded-2xl shrink-0"
              style={{
                width: 72,
                height: 72,
                background: `linear-gradient(135deg, ${bgGlow} 0%, rgba(0,0,0,0.2) 100%)`,
                border: `2px solid ${color}`,
                boxShadow: `0 0 32px ${color}, inset 0 1px 0 rgba(255,255,255,0.14)`,
              }}
            >
              <Icon size={42} style={{ color, filter: `drop-shadow(0 0 8px ${color})` }} />
            </motion.div>
            <div className="flex-1 min-w-0">
              <motion.div
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.08 }}
                className="font-display font-bold uppercase tracking-widest"
                style={{
                  color,
                  fontSize: 30,
                  letterSpacing: "0.12em",
                  textShadow: `0 0 24px ${color}88`,
                  lineHeight: 1.05,
                }}
              >
                {label}
              </motion.div>
              {typeof verdict.llmScore === "number" && (
                <div
                  className="font-mono mt-1 tabular-nums"
                  style={{ color: "var(--text-secondary)", fontSize: 14 }}
                >
                  Оценка: {Math.round(verdict.llmScore)}/10
                </div>
              )}
            </div>
            {verdict.speedBonus && verdict.speedBonus > 0 && (
              <motion.div
                initial={{ scale: 0.4, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                transition={{ type: "spring", stiffness: 360, damping: 18, delay: 0.15 }}
                className="flex items-center gap-1 px-3 py-1.5 rounded-xl font-display font-bold uppercase tracking-wider"
                style={{
                  background: "linear-gradient(135deg, rgba(245,158,11,0.95) 0%, rgba(245,158,11,0.78) 100%)",
                  color: "#1a0f00",
                  boxShadow: "0 4px 14px rgba(245,158,11,0.45), inset 0 1px 0 rgba(255,255,255,0.3)",
                  fontSize: 11,
                  letterSpacing: "0.1em",
                }}
              >
                ⚡ +{verdict.speedBonus} SPEED
              </motion.div>
            )}
          </div>

          {/* Personality comment */}
          {personalityComment && (
            <motion.div
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.12 }}
              className="px-4 py-3 mb-3 rounded-xl italic"
              style={{
                background: "rgba(255,255,255,0.04)",
                borderLeft: "4px solid var(--accent)",
                color: "var(--text-primary)",
                fontSize: 16,
                lineHeight: 1.55,
              }}
            >
              {verdict.avatarEmoji && <span style={{ marginRight: 8, fontSize: 18 }}>{verdict.avatarEmoji}</span>}
              {personalityComment}
            </motion.div>
          )}

          {/* Правильный ответ (если не correct) */}
          {showRightAnswer && (
            <motion.div
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.16 }}
              className="px-4 py-3 mb-3 rounded-xl"
              style={{
                background: "linear-gradient(135deg, rgba(34,197,94,0.16) 0%, rgba(34,197,94,0.05) 100%)",
                border: "1px solid rgba(34,197,94,0.5)",
                boxShadow: "0 4px 18px rgba(34,197,94,0.2), inset 0 1px 0 rgba(255,255,255,0.06)",
              }}
            >
              <div
                className="font-display font-bold uppercase tracking-widest mb-2"
                style={{ color: "var(--success)", fontSize: 13, letterSpacing: "0.16em" }}
              >
                ✓ Правильный ответ
              </div>
              <div style={{ color: "var(--text-primary)", fontSize: 17, lineHeight: 1.55, fontWeight: 500 }}>
                {rightAnswer}
              </div>
            </motion.div>
          )}

          {/* Объяснение для correct (или дополнительное для остальных) */}
          {(level === "correct" && explanation) && (
            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.18 }}
              style={{ color: "var(--text-secondary)", fontSize: 15, lineHeight: 1.55 }}
              className="mb-3"
            >
              {explanation}
            </motion.p>
          )}

          {/* Footer: source chip + dismiss button */}
          <div className="flex items-center gap-3 mt-1">
            {articleRef && (
              <div
                className="inline-flex items-center gap-1.5 font-mono uppercase px-3 py-1.5 rounded-lg shrink-0"
                style={{
                  color: "var(--text-secondary)",
                  background: "rgba(255,255,255,0.05)",
                  border: "1px solid rgba(255,255,255,0.1)",
                  fontSize: 13,
                  letterSpacing: "0.06em",
                  fontWeight: 600,
                }}
              >
                <BookOpen size={14} />
                {articleRef}
              </div>
            )}
            <motion.button
              type="button"
              onClick={onDismiss}
              whileHover={{ x: 2 }}
              whileTap={{ scale: 0.96 }}
              className="ml-auto inline-flex items-center gap-2.5 rounded-xl font-display font-bold uppercase tracking-widest"
              style={{
                padding: "14px 24px",
                background: `linear-gradient(135deg, ${color} 0%, color-mix(in srgb, ${color} 78%, black) 100%)`,
                color: "#0a0810",
                border: `1px solid color-mix(in srgb, ${color} 60%, white)`,
                boxShadow: `0 8px 24px ${color}66, inset 0 1px 0 rgba(255,255,255,0.22)`,
                fontSize: 16,
                letterSpacing: "0.14em",
                cursor: "pointer",
              }}
            >
              {autoAdvance && progress > 0 && progress < 1 && (
                <CountdownRing progress={progress} color="#0a0810" />
              )}
              Далее
              <ArrowRight size={20} />
            </motion.button>
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
