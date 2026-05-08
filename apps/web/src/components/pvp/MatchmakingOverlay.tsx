"use client";

/**
 * MatchmakingOverlay — пиксельный full-screen overlay поиска соперника + VS reveal.
 *
 * 2026-04-30 (Фаза 7): полная переделка. Было: смесь glass-panel + emoji
 * (⚔️ 🛡️ 🤖) + font-display + font-pixel — стилистическая каша. Теперь:
 *   - SEARCHING: pixel scanner-ring (16 сегментов, вращающаяся «иголка») +
 *     pixel-таймер + pixel-чип очереди + ротация tip-карточек.
 *   - MATCHED: pixel-аватары обоих бойцов (PixelSprite), tier-чип через
 *     RankBadge-like, центральная VS pixel-плашка, FIGHT! ribbon с задержкой.
 *
 * Lifecycle/props не сломаны:
 *   { status, position, estimatedWait, opponentRating?, onCancel }
 * Старые потребители продолжают работать без правок.
 */

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { X } from "lucide-react";
import { PixelIcon } from "./PixelIcon";

interface Props {
  status: "searching" | "matched";
  position: number;
  estimatedWait: number;
  opponentRating?: number;
  onCancel: () => void;
}

const MATCH_TIMEOUT = 90;

const TIPS = [
  "Первые 10 дуэлей — калибровочные. Рейтинг определяется быстрее.",
  "В Round 2 роли меняются: менеджер становится клиентом и наоборот.",
  "AI-судья оценивает: возражения, убеждение, структуру и юр. точность.",
  "Чем точнее ты цитируешь ФЗ-127, тем выше балл за юридическую точность.",
  "Лимит — 8 сообщений за раунд. Будь лаконичным и убедительным.",
  "PvE-дуэли дают 50% рейтинговых очков. Живой соперник — полный рейтинг.",
];

const SCAN_SEGMENTS = 16;

export function MatchmakingOverlay({
  status,
  position,
  estimatedWait,
  opponentRating,
  onCancel,
}: Props) {
  const reducedMotion = useReducedMotion();
  const rem = estimatedWait > 0 ? estimatedWait : MATCH_TIMEOUT;
  const [anchor, setAnchor] = useState({
    remaining: rem,
    wait: MATCH_TIMEOUT - rem,
    ts: Date.now(),
  });
  const [live, setLive] = useState({
    remaining: rem,
    wait: Math.max(0, MATCH_TIMEOUT - rem),
  });
  const [tipIndex, setTipIndex] = useState(0);
  const [scanRot, setScanRot] = useState(0);

  const searchStartedRef = useRef(false);
  useEffect(() => {
    if (status !== "searching") {
      searchStartedRef.current = false;
      return;
    }
    if (searchStartedRef.current) return;
    searchStartedRef.current = true;
    const r = estimatedWait > 0 ? estimatedWait : MATCH_TIMEOUT;
    const w = Math.max(0, MATCH_TIMEOUT - r);
    setAnchor({ remaining: r, wait: w, ts: Date.now() });
    setLive({ remaining: r, wait: w });
  }, [status, estimatedWait]);

  useEffect(() => {
    if (status !== "searching") return;
    const tick = () => {
      const elapsed = Math.floor((Date.now() - anchor.ts) / 1000);
      setLive({
        remaining: Math.max(0, anchor.remaining - elapsed),
        wait: anchor.wait + elapsed,
      });
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [status, anchor.remaining, anchor.wait, anchor.ts]);

  // Tips rotation
  useEffect(() => {
    if (status !== "searching") return;
    const id = setInterval(() => setTipIndex((i) => (i + 1) % TIPS.length), 8000);
    return () => clearInterval(id);
  }, [status]);

  // Scanner rotation — отдельный rAF, чтобы плавно
  useEffect(() => {
    if (status !== "searching" || reducedMotion) return;
    let raf = 0;
    let last = performance.now();
    const tick = (t: number) => {
      const dt = t - last;
      last = t;
      // 1 оборот в 3 секунды
      setScanRot((r) => (r + (dt / 3000) * SCAN_SEGMENTS) % SCAN_SEGMENTS);
      raf = window.requestAnimationFrame(tick);
    };
    raf = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(raf);
  }, [status, reducedMotion]);

  const displayWait = status === "searching" ? live.wait : 0;
  const isLate = displayWait > 60;
  const ringColor = isLate ? "var(--warning)" : "var(--accent)";

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-[150] flex items-center justify-center px-4"
      role="dialog"
      aria-modal="true"
      aria-label={status === "searching" ? "Идёт поиск соперника" : "Соперник найден"}
      style={{
        background: "rgba(5,5,10,0.88)",
        backgroundImage: `
          radial-gradient(ellipse 60% 50% at 50% 30%, color-mix(in srgb, ${ringColor} 14%, transparent) 0%, transparent 70%),
          radial-gradient(ellipse at center, rgba(0,0,0,0.5) 0%, rgba(0,0,0,0.92) 100%),
          repeating-linear-gradient(0deg, transparent 0, transparent 31px, rgba(255,255,255,0.018) 31px, rgba(255,255,255,0.018) 32px),
          repeating-linear-gradient(90deg, transparent 0, transparent 31px, rgba(255,255,255,0.018) 31px, rgba(255,255,255,0.018) 32px)
        `,
        backdropFilter: "blur(8px)",
        WebkitBackdropFilter: "blur(8px)",
        WebkitFontSmoothing: "antialiased",
        MozOsxFontSmoothing: "grayscale",
      } as React.CSSProperties}
    >
      <motion.div
        initial={{ scale: 0.94, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ type: "spring", damping: 22, stiffness: 280 }}
        className="relative max-w-md w-full p-7 sm:p-8 text-center rounded-3xl"
        style={{
          background: `linear-gradient(135deg, color-mix(in srgb, ${ringColor} 10%, rgba(15,15,20,0.92)) 0%, rgba(15,15,20,0.96) 100%)`,
          border: `1px solid color-mix(in srgb, ${ringColor} 45%, transparent)`,
          boxShadow: `0 24px 64px color-mix(in srgb, ${ringColor} 30%, transparent), 0 0 0 1px color-mix(in srgb, ${ringColor} 18%, transparent), inset 0 1px 0 rgba(255,255,255,0.08)`,
          backdropFilter: "blur(24px) saturate(1.4)",
          WebkitBackdropFilter: "blur(24px) saturate(1.4)",
        }}
      >
        <AnimatePresence mode="wait">
          {status === "searching" ? (
            <motion.div
              key="searching"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
            >
              {/* Pixel scanner */}
              <div
                className="relative mx-auto mb-6"
                style={{ width: 128, height: 128 }}
              >
                <PixelScanner color={ringColor} rotation={scanRot} />
                <div className="absolute inset-0 flex items-center justify-center">
                  <PixelIcon name="target" size={36} color={ringColor} />
                </div>
              </div>

              <h2
                className="font-display font-bold uppercase"
                style={{
                  color: "var(--text-primary)",
                  fontSize: 22,
                  letterSpacing: "0.16em",
                  textShadow: `0 0 18px ${ringColor}55`,
                }}
              >
                Ищем соперника
              </h2>

              <div className="mt-5 space-y-3" aria-live="polite" aria-atomic="true">
                <div className="flex items-end justify-center gap-2">
                  <span
                    className="font-display font-bold tabular-nums"
                    style={{
                      color: ringColor,
                      fontSize: 64,
                      letterSpacing: "-0.02em",
                      textShadow: `0 0 32px ${ringColor}88, 0 0 12px ${ringColor}`,
                      lineHeight: 1,
                    }}
                  >
                    {displayWait}
                  </span>
                  <span
                    className="pb-2 font-mono uppercase"
                    style={{
                      color: "var(--text-muted)",
                      fontSize: 12,
                      letterSpacing: "0.18em",
                    }}
                  >
                    сек
                  </span>
                </div>

                {/* Pixel progress bar */}
                <SegmentedProgress
                  value={Math.min(100, Math.round((displayWait / MATCH_TIMEOUT) * 100))}
                  color={ringColor}
                  segments={20}
                />

                {position > 0 && (
                  <div
                    className="inline-flex items-center gap-2 rounded-full px-3 py-1.5 font-display font-bold uppercase"
                    style={{
                      background: "rgba(255,255,255,0.04)",
                      border: "1px solid rgba(255,255,255,0.1)",
                      color: "var(--text-secondary)",
                      fontSize: 11,
                      letterSpacing: "0.16em",
                      backdropFilter: "blur(20px)",
                    }}
                  >
                    <span
                      className="rounded-full"
                      style={{
                        width: 6,
                        height: 6,
                        background: ringColor,
                        boxShadow: `0 0 8px ${ringColor}`,
                      }}
                    />
                    В очереди: {position}
                  </div>
                )}

                {isLate && (
                  <motion.p
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="font-display font-bold uppercase"
                    style={{
                      color: "var(--warning)",
                      fontSize: 11,
                      letterSpacing: "0.18em",
                    }}
                  >
                    Готовим PvE-соперника…
                  </motion.p>
                )}
              </div>

              {/* Tips — glass card */}
              <div className="mt-6 min-h-[60px] flex items-start justify-center">
                <AnimatePresence mode="wait">
                  <motion.div
                    key={tipIndex}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -8 }}
                    transition={{ duration: 0.3 }}
                    className="rounded-xl px-3 py-2 flex items-start gap-2 max-w-xs"
                    style={{
                      background: "rgba(255,255,255,0.03)",
                      border: "1px solid rgba(255,255,255,0.08)",
                      backdropFilter: "blur(20px)",
                    }}
                  >
                    <PixelIcon name="bolt" size={12} color={ringColor} />
                    <p
                      className="leading-relaxed text-left"
                      style={{ color: "var(--text-muted)", fontSize: 12 }}
                    >
                      {TIPS[tipIndex]}
                    </p>
                  </motion.div>
                </AnimatePresence>
              </div>

              <motion.button
                onClick={onCancel}
                whileHover={{ y: -1 }}
                whileTap={{ scale: 0.96 }}
                className="mt-6 inline-flex items-center gap-2 mx-auto rounded-xl font-display font-bold uppercase"
                style={{
                  padding: "10px 20px",
                  background: "rgba(255,255,255,0.03)",
                  color: "var(--text-secondary)",
                  border: "1px solid rgba(255,255,255,0.12)",
                  fontSize: 12,
                  letterSpacing: "0.18em",
                  backdropFilter: "blur(20px)",
                  cursor: "pointer",
                }}
              >
                <X size={14} /> Отмена
              </motion.button>
            </motion.div>
          ) : (
            <motion.div
              key="matched"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.25 }}
            >
              {/* Match found header */}
              <motion.h2
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.1 }}
                className="font-display font-bold uppercase"
                style={{
                  color: "var(--success)",
                  fontSize: 18,
                  letterSpacing: "0.18em",
                  textShadow: "0 0 24px color-mix(in srgb, var(--success) 60%, transparent)",
                }}
                aria-live="assertive"
              >
                Противник найден
              </motion.h2>

              {/* VS layout */}
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.3 }}
                className="mt-6 flex items-center justify-center gap-5"
              >
                <FighterMini side="left" label="Вы" sublabel="MANAGER" color="var(--accent)" />

                <motion.div
                  initial={{ scale: 0, rotate: -15 }}
                  animate={{ scale: 1, rotate: 0 }}
                  transition={{ delay: 0.5, type: "spring", stiffness: 360, damping: 18 }}
                  className="font-display font-bold"
                  style={{
                    color: "var(--accent)",
                    fontSize: 56,
                    letterSpacing: "-0.04em",
                    textShadow: "0 0 32px var(--accent-glow), 0 0 64px var(--accent), 0 8px 24px rgba(0,0,0,0.6)",
                    lineHeight: 1,
                  }}
                >
                  VS
                </motion.div>

                <FighterMini
                  side="right"
                  label={opponentRating ? `HUNTER ${Math.round(opponentRating)}` : "AI БОТ"}
                  sublabel={opponentRating ? "RIVAL" : "PVE"}
                  color={opponentRating ? "var(--danger)" : "var(--text-muted)"}
                />
              </motion.div>

              {/* FIGHT! ribbon */}
              <motion.div
                initial={{ opacity: 0, y: 16, scale: 0.8 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                transition={{ delay: 0.9, type: "spring", stiffness: 280, damping: 18 }}
                className="font-display font-bold mt-6"
                style={{
                  color: "var(--danger)",
                  fontSize: 32,
                  letterSpacing: "0.32em",
                  textShadow: "0 0 24px var(--danger), 0 0 48px color-mix(in srgb, var(--danger) 50%, transparent)",
                }}
              >
                БОЙ!
              </motion.div>

              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 1.0 }}
                className="mt-4 inline-flex items-center gap-2 font-pixel"
                style={{
                  padding: "5px 12px",
                  background: "var(--bg-secondary)",
                  border: "2px solid var(--border-color)",
                  color: "var(--text-muted)",
                  fontSize: 11,
                  letterSpacing: "0.18em",
                  textTransform: "uppercase",
                  boxShadow: "2px 2px 0 0 var(--border-color)",
                }}
              >
                <span
                  className="animate-pulse"
                  style={{
                    display: "inline-block",
                    width: 6,
                    height: 6,
                    background: "var(--accent)",
                  }}
                />
                Подготовка арены
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </motion.div>
  );
}

/* ── Pixel scanner ──────────────────────────────────────── */
function PixelScanner({ color, rotation }: { color: string; rotation: number }) {
  const center = 64;
  const radius = 56;
  const segs: React.ReactElement[] = [];
  // 16 «иголок» по окружности; «активная» (под линзой сканера) — самая яркая,
  // соседние — тусклее, остальные — едва видны.
  for (let i = 0; i < SCAN_SEGMENTS; i += 1) {
    const angle = (i / SCAN_SEGMENTS) * 2 * Math.PI - Math.PI / 2;
    const x = center + radius * Math.cos(angle) - 4;
    const y = center + radius * Math.sin(angle) - 4;
    // Distance from current rotation (mod segments)
    const dist = Math.min(
      Math.abs(i - rotation),
      SCAN_SEGMENTS - Math.abs(i - rotation),
    );
    const intensity = Math.max(0, 1 - dist / 4); // 4 ближайших сегмента светятся
    segs.push(
      <span
        key={i}
        aria-hidden
        style={{
          position: "absolute",
          left: x,
          top: y,
          width: 8,
          height: 8,
          background: `color-mix(in srgb, ${color} ${Math.round(intensity * 95 + 5)}%, transparent)`,
          boxShadow: intensity > 0.5 ? `0 0 6px ${color}` : "none",
        }}
      />,
    );
  }
  return <div className="absolute inset-0">{segs}</div>;
}

/* ── Segmented progress ─────────────────────────────────── */
function SegmentedProgress({
  value,
  color,
  segments,
}: {
  value: number;
  color: string;
  segments: number;
}) {
  const lit = Math.round((value / 100) * segments);
  return (
    <div
      className="inline-flex items-center"
      style={{
        gap: 1,
        padding: 2,
        outline: "2px solid var(--text-primary)",
        outlineOffset: -2,
        background: "var(--bg-secondary)",
        boxShadow: "2px 2px 0 0 #000",
      }}
    >
      {Array.from({ length: segments }).map((_, i) => (
        <span
          key={i}
          aria-hidden
          style={{
            width: 8,
            height: 10,
            background: i < lit ? color : `color-mix(in srgb, ${color} 14%, transparent)`,
            boxShadow: i < lit ? `0 0 4px ${color}` : "none",
            transition: "background 220ms ease-out",
          }}
        />
      ))}
    </div>
  );
}

/* ── Fighter mini-card (для VS reveal) ──────────────────── */
function FighterMini({
  side,
  label,
  sublabel,
  color,
}: {
  side: "left" | "right";
  label: string;
  sublabel: string;
  color: string;
}) {
  // Pixel "head" silhouette — простая 16x16 пиксель-сцена под цвет
  return (
    <motion.div
      initial={{ x: side === "left" ? -40 : 40, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      transition={{ delay: 0.4, type: "spring", stiffness: 280, damping: 22 }}
      className="text-center"
    >
      <div
        className="mx-auto flex items-center justify-center"
        style={{
          width: 64,
          height: 64,
          outline: `3px solid ${color}`,
          outlineOffset: -3,
          background: `color-mix(in srgb, ${color} 18%, var(--bg-panel))`,
          backgroundImage: `repeating-linear-gradient(
            0deg,
            transparent 0,
            transparent 3px,
            color-mix(in srgb, ${color} 14%, transparent) 3px,
            color-mix(in srgb, ${color} 14%, transparent) 4px
          )`,
          boxShadow:
            side === "left"
              ? `3px 3px 0 0 ${color}`
              : `-3px 3px 0 0 ${color}`,
        }}
      >
        <PixelIcon
          name={side === "left" ? "shield" : "sword"}
          size={36}
          color={color}
        />
      </div>
      <p
        className="mt-2 font-pixel"
        style={{
          color,
          fontSize: 12,
          letterSpacing: "0.16em",
          textTransform: "uppercase",
        }}
      >
        {label}
      </p>
      <p
        className="font-pixel"
        style={{
          color: "var(--text-muted)",
          fontSize: 9,
          letterSpacing: "0.22em",
          textTransform: "uppercase",
        }}
      >
        {sublabel}
      </p>
    </motion.div>
  );
}
