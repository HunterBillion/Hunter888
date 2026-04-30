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
        background: "rgba(0,0,0,0.92)",
        backgroundImage: `
          radial-gradient(ellipse at center, rgba(0,0,0,0.6) 0%, rgba(0,0,0,0.95) 100%),
          repeating-linear-gradient(0deg, transparent 0, transparent 7px, rgba(255,255,255,0.025) 7px, rgba(255,255,255,0.025) 8px),
          repeating-linear-gradient(90deg, transparent 0, transparent 7px, rgba(255,255,255,0.025) 7px, rgba(255,255,255,0.025) 8px)
        `,
      }}
    >
      <motion.div
        initial={{ scale: 0.94, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ type: "spring", damping: 22, stiffness: 280 }}
        className="relative max-w-md w-full p-7 sm:p-8 text-center"
        style={{
          background: "var(--bg-panel)",
          outline: `2px solid ${ringColor}`,
          outlineOffset: -2,
          boxShadow: `4px 4px 0 0 ${ringColor}, 0 0 32px color-mix(in srgb, ${ringColor} 30%, transparent)`,
          borderRadius: 0,
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
                className="font-pixel"
                style={{
                  color: "var(--text-primary)",
                  fontSize: 22,
                  letterSpacing: "0.18em",
                  textTransform: "uppercase",
                }}
              >
                Ищем Соперника
              </h2>

              <div className="mt-5 space-y-3" aria-live="polite" aria-atomic="true">
                <div className="flex items-end justify-center gap-2 font-pixel">
                  <span
                    className="tabular-nums"
                    style={{
                      color: ringColor,
                      fontSize: 56,
                      letterSpacing: "0.04em",
                      textShadow: `3px 3px 0 #000, 0 0 18px ${ringColor}`,
                      lineHeight: 1,
                    }}
                  >
                    {displayWait}
                  </span>
                  <span
                    className="pb-2"
                    style={{
                      color: "var(--text-muted)",
                      fontSize: 12,
                      letterSpacing: "0.18em",
                      textTransform: "uppercase",
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
                    className="inline-flex items-center font-pixel"
                    style={{
                      padding: "3px 10px",
                      background: "var(--bg-secondary)",
                      outline: "2px solid var(--border-color)",
                      outlineOffset: -2,
                      color: "var(--text-secondary)",
                      fontSize: 11,
                      letterSpacing: "0.16em",
                      textTransform: "uppercase",
                      boxShadow: "2px 2px 0 0 var(--border-color)",
                    }}
                  >
                    В очереди: {position}
                  </div>
                )}

                {isLate && (
                  <motion.p
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="font-pixel"
                    style={{
                      color: "var(--warning)",
                      fontSize: 11,
                      letterSpacing: "0.18em",
                      textTransform: "uppercase",
                    }}
                  >
                    Готовим PvE-соперника…
                  </motion.p>
                )}
              </div>

              {/* Tips */}
              <div className="mt-6 min-h-[44px] flex items-start justify-center">
                <AnimatePresence mode="wait">
                  <motion.div
                    key={tipIndex}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -8 }}
                    transition={{ duration: 0.3 }}
                    className="flex items-start gap-2 max-w-xs"
                  >
                    <PixelIcon name="bolt" size={12} color="var(--accent)" />
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
                whileHover={{ x: -1, y: -1 }}
                whileTap={{ x: 2, y: 2 }}
                className="mt-6 inline-flex items-center gap-2 font-pixel mx-auto"
                style={{
                  padding: "8px 16px",
                  background: "transparent",
                  color: "var(--text-muted)",
                  border: "2px solid var(--border-color)",
                  fontSize: 12,
                  letterSpacing: "0.18em",
                  textTransform: "uppercase",
                  boxShadow: "2px 2px 0 0 var(--border-color)",
                  cursor: "pointer",
                  borderRadius: 0,
                }}
              >
                <X size={12} /> Отмена
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
                className="font-pixel"
                style={{
                  color: "var(--success)",
                  fontSize: 18,
                  letterSpacing: "0.22em",
                  textTransform: "uppercase",
                  textShadow: "2px 2px 0 #000, 0 0 14px color-mix(in srgb, var(--success) 40%, transparent)",
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
                  className="font-pixel"
                  style={{
                    color: "var(--accent)",
                    fontSize: 48,
                    letterSpacing: "-0.05em",
                    textShadow: "4px 4px 0 #000, 0 0 18px var(--accent-glow), 0 0 36px var(--accent)",
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
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.9, duration: 0.3 }}
                className="font-pixel mt-6"
                style={{
                  color: "var(--danger)",
                  fontSize: 28,
                  letterSpacing: "0.4em",
                  textShadow: "3px 3px 0 #000, 0 0 18px var(--danger)",
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
