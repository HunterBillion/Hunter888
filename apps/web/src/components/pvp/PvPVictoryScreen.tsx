"use client";

/**
 * PvPVictoryScreen — пиксельный 4-фазный reveal результата дуэли.
 *
 * 2026-04-30 (Фаза 5): полная переделка из спокойного 2-фазного
 * `Sword + ПОБЕДА` экрана в киношный аркадный финал:
 *
 * Phase 1 (0.0–0.8s): чёрный → flash → большой "KO!" / "FLAWLESS!" /
 *                     "VICTORY" / "DEFEAT" / "DRAW" с shake.
 * Phase 2 (0.8–2.3s): count-up очков «+0 → +247 ОЧКОВ» с цифровой
 *                     прокруткой + tier-бэйдж пульсирует.
 * Phase 3 (2.3–3.5s): ELO-дельта «1450 → 1487 (+37)» с trend-стрелкой;
 *                     если promotion флаг — конфетти + «↑ SILVER ↑».
 * Phase 4 (3.5+s):    score-сравнение, кнопка «ПОДРОБНЫЙ РАЗБОР»,
 *                     reactions/reveal как в обычном details-экране.
 *
 * Skip-кнопка в правом верхнем углу — пропустить к Phase 4 сразу,
 * полезно для повторных боёв. Состояние сохраняется в localStorage:
 * после первого использования следующая дуэль уже стартует с Phase 4.
 *
 * Уважает prefers-reduced-motion: все count-up / shake / scale → instant.
 */

import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { Minus } from "lucide-react";
import { TrendUp, TrendDown } from "@phosphor-icons/react";
import { useSound } from "@/hooks/useSound";
import { useHaptic } from "@/hooks/useHaptic";
import { Confetti } from "@/components/ui/Confetti";
import {
  type PvPRankTier,
  PVP_RANK_LABELS,
  PVP_RANK_COLORS,
  normalizeRankTier,
} from "@/types";

type Phase = "ko" | "score" | "elo" | "details";

interface PvPVictoryScreenProps {
  isWinner: boolean;
  isDraw: boolean;
  myScore: number;
  opponentScore: number;
  ratingDelta: number;
  onContinue: () => void;
  /** Optional: previous rating shown in count-up (e.g. 1450). */
  prevRating?: number;
  /** Optional: tier transitions for promotion confetti. */
  newTier?: PvPRankTier | string;
  prevTier?: PvPRankTier | string;
  /** Optional: тир игрока для tier-color бэйджа в Phase 2. */
  myTier?: PvPRankTier | string;
}

const STORAGE_SKIP_KEY = "pvp_victory_skip_intro";

export function PvPVictoryScreen({
  isWinner,
  isDraw,
  myScore,
  opponentScore,
  ratingDelta,
  onContinue,
  prevRating,
  newTier,
  prevTier,
  myTier,
}: PvPVictoryScreenProps) {
  const reducedMotion = useReducedMotion();
  const { playSound } = useSound();
  const haptic = useHaptic();

  // Skip intro если пользователь раньше нажимал «Skip»
  const skipIntroRef = useRef<boolean>(false);
  if (typeof window !== "undefined" && skipIntroRef.current === false) {
    try {
      skipIntroRef.current = localStorage.getItem(STORAGE_SKIP_KEY) === "1";
    } catch {
      /* storage disabled */
    }
  }
  const startPhase: Phase = skipIntroRef.current || reducedMotion ? "details" : "ko";
  const [phase, setPhase] = useState<Phase>(startPhase);
  const [confettiTick, setConfettiTick] = useState(0);
  const isPromotion = !!(newTier && prevTier && newTier !== prevTier && isWinner);

  /* ── Phase orchestration ─────────────────────────────── */
  useEffect(() => {
    if (phase === "details") return; // already there
    if (reducedMotion) {
      setPhase("details");
      return;
    }
    // SFX/haptic — only at the very start (KO phase).
    // 2026-05-01 (Фаза 8): KO! flash звучит «BOOM» (новый pixel-sound `ko`).
    // Через 600ms добавляется fanfare (victory) или dramatic (defeat) для слоистости.
    if (phase === "ko") {
      if (isWinner) {
        playSound("ko");
        haptic("victory");
        window.setTimeout(() => playSound("victory"), 600);
      } else if (isDraw) {
        playSound("hit");
        haptic("tap");
      } else {
        playSound("ko", 0.7);
        haptic("error");
        window.setTimeout(() => playSound("defeat"), 600);
      }
    }
    // Promotion confetti at ELO phase
    if (phase === "elo" && isPromotion) {
      setConfettiTick((n) => n + 1);
    }
    const advanceMap: Record<Phase, { next: Phase; ms: number }> = {
      ko: { next: "score", ms: 800 },
      score: { next: "elo", ms: 1500 },
      elo: { next: "details", ms: 1200 },
      details: { next: "details", ms: 0 },
    };
    const cfg = advanceMap[phase];
    const id = window.setTimeout(() => setPhase(cfg.next), cfg.ms);
    return () => window.clearTimeout(id);
  }, [phase, isWinner, isDraw, isPromotion, reducedMotion, playSound, haptic]);

  /* ── Skip handler ────────────────────────────────────── */
  const handleSkip = () => {
    setPhase("details");
    try {
      localStorage.setItem(STORAGE_SKIP_KEY, "1");
    } catch {
      /* storage disabled */
    }
  };

  /* ── Visual config per outcome ───────────────────────── */
  const headline = isWinner
    ? myScore - opponentScore >= 30
      ? "FLAWLESS!"
      : "VICTORY!"
    : isDraw
      ? "DRAW"
      : "DEFEAT";
  const koColor = isWinner
    ? "var(--gf-xp)"
    : isDraw
      ? "var(--text-secondary)"
      : "var(--danger)";
  const koGlow = isWinner
    ? "var(--gf-xp)"
    : isDraw
      ? "var(--text-muted)"
      : "var(--danger)";

  return (
    <motion.div
      role="dialog"
      aria-modal="true"
      aria-label="Результат дуэли"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-[200] flex items-center justify-center"
      style={{
        background: "rgba(0, 0, 0, 0.94)",
        backgroundImage: `
          radial-gradient(ellipse at center, rgba(0,0,0,0.5) 0%, rgba(0,0,0,0.95) 100%),
          repeating-linear-gradient(0deg, transparent 0, transparent 7px, rgba(255,255,255,0.025) 7px, rgba(255,255,255,0.025) 8px),
          repeating-linear-gradient(90deg, transparent 0, transparent 7px, rgba(255,255,255,0.025) 7px, rgba(255,255,255,0.025) 8px)
        `,
      }}
    >
      <Confetti trigger={confettiTick} />

      {/* Skip button — top-right pixel button */}
      {phase !== "details" && !reducedMotion && (
        <motion.button
          onClick={handleSkip}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.4 }}
          className="absolute top-4 right-4 font-pixel"
          aria-label="Пропустить вступление"
          style={{
            padding: "6px 12px",
            background: "transparent",
            border: "2px solid var(--text-muted)",
            color: "var(--text-muted)",
            fontSize: 11,
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            boxShadow: "2px 2px 0 0 var(--text-muted)",
            cursor: "pointer",
            borderRadius: 0,
          }}
          whileHover={{ x: -1, y: -1 }}
          whileTap={{ x: 2, y: 2 }}
        >
          Skip ▶▶
        </motion.button>
      )}

      <AnimatePresence mode="wait">
        {/* ── Phase 1: KO! flash ───────────────────────── */}
        {phase === "ko" && (
          <motion.div
            key="ko"
            initial={{ scale: 4, opacity: 0 }}
            animate={{ scale: 1, opacity: 1, x: [0, -4, 4, -4, 4, 0] }}
            exit={{ opacity: 0, scale: 1.4 }}
            transition={{
              scale: { type: "spring", stiffness: 280, damping: 14 },
              x: { duration: 0.5, delay: 0.1 },
              opacity: { duration: 0.2 },
            }}
            className="font-pixel text-center"
            style={{
              color: koColor,
              fontSize: "clamp(60px, 14vw, 180px)",
              letterSpacing: "0.04em",
              textShadow: `6px 6px 0 #000, 0 0 30px ${koGlow}, 0 0 60px ${koGlow}`,
              lineHeight: 1,
            }}
          >
            {headline}
          </motion.div>
        )}

        {/* ── Phase 2: count-up score ──────────────────── */}
        {phase === "score" && (
          <motion.div
            key="score"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -16 }}
            className="text-center space-y-6"
          >
            <CountUpScore value={myScore} color={koColor} />
            <div
              className="font-pixel"
              style={{
                color: "var(--text-muted)",
                fontSize: 14,
                letterSpacing: "0.25em",
                textTransform: "uppercase",
              }}
            >
              Очки за бой
            </div>
            {myTier && <TierPulseBadge tier={myTier} />}
          </motion.div>
        )}

        {/* ── Phase 3: ELO delta ───────────────────────── */}
        {phase === "elo" && (
          <motion.div
            key="elo"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -16 }}
            className="text-center space-y-4"
          >
            <ELODisplay prev={prevRating} delta={ratingDelta} />
            {isPromotion && (
              <motion.div
                initial={{ scale: 0.5, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                transition={{ delay: 0.3, type: "spring", stiffness: 220 }}
                className="font-pixel"
                style={{
                  color: PVP_RANK_COLORS[normalizeRankTier(typeof newTier === "string" ? newTier : "")] ?? "var(--accent)",
                  fontSize: "clamp(28px, 5vw, 44px)",
                  letterSpacing: "0.18em",
                  textShadow: "3px 3px 0 #000, 0 0 18px currentColor",
                }}
              >
                ↑ {PVP_RANK_LABELS[normalizeRankTier(typeof newTier === "string" ? newTier : "")] ?? newTier} ↑
              </motion.div>
            )}
          </motion.div>
        )}

        {/* ── Phase 4: details ─────────────────────────── */}
        {phase === "details" && (
          <motion.div
            key="details"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25 }}
            className="text-center space-y-8 px-4"
          >
            {/* Headline (small, pixel) */}
            <div
              className="font-pixel"
              style={{
                color: koColor,
                fontSize: "clamp(36px, 6vw, 64px)",
                letterSpacing: "0.16em",
                textShadow: `4px 4px 0 #000, 0 0 24px ${koGlow}`,
              }}
            >
              {headline}
            </div>

            {/* Score comparison */}
            <div className="flex items-center gap-6 sm:gap-12 justify-center">
              <ScoreCol score={myScore} label="Вы" highlight={isWinner} />
              <span
                className="font-pixel"
                style={{
                  color: "var(--text-muted)",
                  fontSize: 32,
                  letterSpacing: "0.04em",
                }}
              >
                :
              </span>
              <ScoreCol
                score={opponentScore}
                label="Соперник"
                highlight={!isWinner && !isDraw}
              />
            </div>

            {/* ELO chip */}
            <ELOChip delta={ratingDelta} />

            {/* Continue */}
            <motion.button
              onClick={onContinue}
              className="font-pixel inline-flex items-center gap-2"
              style={{
                padding: "12px 28px",
                background: "var(--accent)",
                color: "#fff",
                border: "2px solid var(--accent)",
                borderRadius: 0,
                fontSize: 16,
                letterSpacing: "0.18em",
                textTransform: "uppercase",
                boxShadow: "4px 4px 0 0 #000, 0 0 16px var(--accent-glow)",
                cursor: "pointer",
              }}
              whileHover={{ x: -1, y: -1 }}
              whileTap={{ x: 2, y: 2 }}
            >
              Подробный разбор ▶
            </motion.button>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

/* ── Sub-components ─────────────────────────────────────── */

function CountUpScore({ value, color }: { value: number; color: string }) {
  const reduce = useReducedMotion();
  const [n, setN] = useState(reduce ? value : 0);
  useEffect(() => {
    if (reduce) {
      setN(value);
      return;
    }
    const start = performance.now();
    const duration = 900;
    let raf = 0;
    const step = (t: number) => {
      const k = Math.min(1, (t - start) / duration);
      // ease-out cubic
      const e = 1 - Math.pow(1 - k, 3);
      setN(Math.round(value * e));
      if (k < 1) raf = window.requestAnimationFrame(step);
    };
    raf = window.requestAnimationFrame(step);
    return () => window.cancelAnimationFrame(raf);
  }, [value, reduce]);
  return (
    <div
      className="font-pixel"
      style={{
        color,
        fontSize: "clamp(48px, 9vw, 100px)",
        letterSpacing: "0.04em",
        textShadow: `4px 4px 0 #000, 0 0 30px ${color}`,
        lineHeight: 1,
        fontVariantNumeric: "tabular-nums",
      }}
    >
      +{n}
    </div>
  );
}

function ELODisplay({ prev, delta }: { prev?: number; delta: number }) {
  const reduce = useReducedMotion();
  const targetCurrent = (prev ?? 0) + delta;
  const [shown, setShown] = useState(reduce ? targetCurrent : prev ?? targetCurrent);
  useEffect(() => {
    if (reduce || prev == null) {
      setShown(targetCurrent);
      return;
    }
    const start = performance.now();
    const duration = 800;
    let raf = 0;
    const step = (t: number) => {
      const k = Math.min(1, (t - start) / duration);
      const e = 1 - Math.pow(1 - k, 3);
      setShown(Math.round(prev + delta * e));
      if (k < 1) raf = window.requestAnimationFrame(step);
    };
    raf = window.requestAnimationFrame(step);
    return () => window.cancelAnimationFrame(raf);
  }, [prev, delta, targetCurrent, reduce]);
  return (
    <div className="flex items-center justify-center gap-4">
      {prev != null && (
        <span
          className="font-pixel"
          style={{ color: "var(--text-muted)", fontSize: 32, letterSpacing: "0.04em" }}
        >
          {prev}
        </span>
      )}
      {prev != null && (
        <motion.span
          aria-hidden
          animate={{ x: [0, 8, 0] }}
          transition={{ repeat: Infinity, duration: 0.8 }}
          style={{
            color: delta >= 0 ? "var(--success)" : "var(--danger)",
            fontSize: 28,
          }}
        >
          ▶
        </motion.span>
      )}
      <span
        className="font-pixel"
        style={{
          color: delta >= 0 ? "var(--success)" : "var(--danger)",
          fontSize: 48,
          letterSpacing: "0.04em",
          textShadow: `3px 3px 0 #000, 0 0 18px currentColor`,
        }}
      >
        {shown}
      </span>
      <span
        className="font-pixel"
        style={{
          color: delta >= 0 ? "var(--success)" : "var(--danger)",
          fontSize: 24,
          letterSpacing: "0.08em",
        }}
      >
        ({delta >= 0 ? "+" : ""}{delta})
      </span>
    </div>
  );
}

function TierPulseBadge({ tier }: { tier: PvPRankTier | string }) {
  const norm = normalizeRankTier(typeof tier === "string" ? tier : "");
  const color = PVP_RANK_COLORS[norm] ?? "var(--text-muted)";
  const label = PVP_RANK_LABELS[norm] ?? "Без ранга";
  return (
    <motion.div
      animate={{ scale: [1, 1.06, 1] }}
      transition={{ repeat: Infinity, duration: 1.4 }}
      className="inline-block font-pixel"
      style={{
        padding: "6px 14px",
        outline: `2px solid ${color}`,
        outlineOffset: -2,
        background: `color-mix(in srgb, ${color} 14%, transparent)`,
        color,
        fontSize: 14,
        letterSpacing: "0.18em",
        textTransform: "uppercase",
        boxShadow: `3px 3px 0 0 ${color}, 0 0 16px ${color}`,
      }}
    >
      {label}
    </motion.div>
  );
}

function ScoreCol({
  score,
  label,
  highlight,
}: {
  score: number;
  label: string;
  highlight: boolean;
}) {
  return (
    <div className="text-center">
      <div
        className="font-pixel"
        style={{
          color: highlight ? "var(--gf-xp)" : "var(--text-primary)",
          fontSize: "clamp(40px, 7vw, 72px)",
          letterSpacing: "0.04em",
          textShadow: highlight ? "3px 3px 0 #000, 0 0 18px var(--gf-xp)" : "3px 3px 0 #000",
          lineHeight: 1,
        }}
      >
        {score}
      </div>
      <div
        className="font-pixel mt-2"
        style={{
          color: "var(--text-muted)",
          fontSize: 12,
          letterSpacing: "0.18em",
          textTransform: "uppercase",
        }}
      >
        {label}
      </div>
    </div>
  );
}

function ELOChip({ delta }: { delta: number }) {
  const positive = delta > 0;
  const negative = delta < 0;
  const color = positive ? "var(--success)" : negative ? "var(--danger)" : "var(--text-muted)";
  return (
    <div
      className="inline-flex items-center gap-2 font-pixel"
      style={{
        padding: "6px 14px",
        background: `color-mix(in srgb, ${color} 14%, transparent)`,
        outline: `2px solid ${color}`,
        outlineOffset: -2,
        color,
        fontSize: 14,
        letterSpacing: "0.16em",
        textTransform: "uppercase",
        boxShadow: `2px 2px 0 0 ${color}`,
      }}
    >
      {positive ? <TrendUp weight="duotone" size={16} /> : negative ? <TrendDown weight="duotone" size={16} /> : <Minus size={16} />}
      <span>
        {positive ? "+" : ""}
        {delta} ELO
      </span>
    </div>
  );
}
