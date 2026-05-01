"use client";

/**
 * RoundIndicator — пиксельный таймер раунда дуэли.
 *
 * 2026-04-30 (Фаза 4): полная переделка из glass-стиля на пиксельный
 * сегментированный ring + цифровой mm:ss + role badge + round dots.
 *
 * - Ring 80×80, 16 сегментов-квадратов, гаснут по одному за tick.
 * - Цвет ring: tier-color → warning (≤30s) → danger (≤10s).
 * - Цифры shake последние 3 секунды.
 * - Pulse последние 5 секунд (визуальный «heartbeat» — SFX в Фазе 8).
 * - Поддерживает prefers-reduced-motion (выключает анимации).
 *
 * Server-driven `deadline_at` поддерживается через optional prop —
 * если задан, считаем остаток через Date.now() vs deadline,
 * иначе используем `timeRemaining` как было.
 */

import * as React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { ArrowLeftRight } from "lucide-react";
import { useSound } from "@/hooks/useSound";

interface Props {
  roundNumber: number;
  myRole: "seller" | "client";
  timeRemaining: number;
  /** Total seconds for current round — used to compute ring fill. Default 180 (3 min). */
  totalSeconds?: number;
  /** Optional: server-side deadline as ISO/epoch — if provided, taкes precedence over timeRemaining. */
  deadlineAt?: string | number | null;
  /** Tier color of the active player — used for ring full-state color. Defaults to var(--accent). */
  tierColor?: string;
}

const RING_SEGMENTS = 16;
const RING_SIZE = 88;

export function RoundIndicator({
  roundNumber,
  myRole,
  timeRemaining,
  totalSeconds = 180,
  deadlineAt,
  tierColor = "var(--accent)",
}: Props) {
  const reducedMotion = useReducedMotion();

  // Server-driven deadline → recompute every animation frame for smooth countdown
  const [serverRemaining, setServerRemaining] = React.useState<number | null>(
    deadlineAt ? computeRemaining(deadlineAt) : null,
  );
  React.useEffect(() => {
    if (!deadlineAt) {
      setServerRemaining(null);
      return;
    }
    let raf = 0;
    const tick = () => {
      setServerRemaining(computeRemaining(deadlineAt));
      raf = window.requestAnimationFrame(tick);
    };
    raf = window.requestAnimationFrame(tick);
    // Re-sync on tab focus (Chrome clamps rAF in background)
    const onVisible = () => {
      if (document.visibilityState === "visible") {
        setServerRemaining(computeRemaining(deadlineAt));
      }
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.cancelAnimationFrame(raf);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [deadlineAt]);

  const remaining = Math.max(
    0,
    serverRemaining != null ? serverRemaining : timeRemaining,
  );
  const mins = Math.floor(remaining / 60);
  const secs = Math.floor(remaining % 60);

  // Severity bands
  const isCritical = remaining <= 10 && remaining > 0;
  const isLow = remaining <= 30 && remaining > 10;
  const isHeartbeat = remaining <= 5 && remaining > 0;

  // 2026-05-01 (Фаза 8): heartbeat sfx последние 5 секунд раунда.
  // Срабатывает на каждой смене целочисленной секунды, не уважает rAF.
  const { playSound } = useSound();
  const lastSecRef = React.useRef<number>(-1);
  React.useEffect(() => {
    const intSec = Math.floor(remaining);
    if (intSec === lastSecRef.current) return;
    lastSecRef.current = intSec;
    if (isHeartbeat && intSec > 0 && !reducedMotion) {
      playSound("heartbeat");
    }
  }, [remaining, isHeartbeat, reducedMotion, playSound]);
  const ringColor = isCritical
    ? "var(--danger)"
    : isLow
      ? "var(--warning)"
      : tierColor;

  // Ring fill — fraction of segments lit
  const fraction = totalSeconds > 0 ? Math.max(0, Math.min(1, remaining / totalSeconds)) : 0;
  const litSegments = Math.ceil(fraction * RING_SEGMENTS);

  return (
    <div
      className="relative flex items-center justify-between gap-4 px-5 py-3"
      style={{
        background: "var(--bg-panel)",
        outline: "2px solid var(--accent)",
        outlineOffset: -2,
        boxShadow: "3px 3px 0 0 var(--accent)",
        borderRadius: 0,
      }}
    >
      {/* Round dots + label */}
      <div className="flex items-center gap-3 min-w-0">
        <div className="flex gap-1.5">
          {[1, 2].map((r) => (
            <span
              key={r}
              aria-hidden
              style={{
                display: "inline-block",
                width: 22,
                height: 8,
                background:
                  r === roundNumber
                    ? "var(--accent)"
                    : r < roundNumber
                      ? "var(--success)"
                      : "var(--bg-secondary)",
                outline: "2px solid var(--accent)",
                outlineOffset: -2,
              }}
            />
          ))}
        </div>
        <span
          className="font-pixel"
          style={{
            color: "var(--text-primary)",
            fontSize: 13,
            letterSpacing: "0.18em",
            textTransform: "uppercase",
          }}
        >
          Раунд {roundNumber}/2
        </span>
        {roundNumber === 0 && (
          <motion.div
            animate={reducedMotion ? {} : { x: [0, 2, -2, 0] }}
            transition={reducedMotion ? {} : { repeat: Infinity, duration: 0.8 }}
            className="font-pixel inline-flex items-center gap-1"
            style={{
              color: "var(--warning)",
              fontSize: 12,
              letterSpacing: "0.14em",
              textTransform: "uppercase",
            }}
          >
            <ArrowLeftRight size={12} /> Смена ролей
          </motion.div>
        )}
      </div>

      {/* Role badge */}
      <div
        className="shrink-0 font-pixel"
        style={{
          padding: "4px 10px",
          background:
            myRole === "seller"
              ? "var(--accent-muted)"
              : "color-mix(in srgb, var(--info) 18%, transparent)",
          color: myRole === "seller" ? "var(--accent)" : "var(--info)",
          outline: `2px solid ${myRole === "seller" ? "var(--accent)" : "var(--info)"}`,
          outlineOffset: -2,
          fontSize: 12,
          letterSpacing: "0.16em",
          textTransform: "uppercase",
          boxShadow: `2px 2px 0 0 ${myRole === "seller" ? "var(--accent)" : "var(--info)"}`,
        }}
      >
        {myRole === "seller" ? "Менеджер" : "Клиент"}
      </div>

      {/* Pixel ring + center mm:ss */}
      <div
        className="relative shrink-0"
        style={{ width: RING_SIZE, height: RING_SIZE }}
      >
        <PixelRing
          segments={RING_SEGMENTS}
          litSegments={litSegments}
          color={ringColor}
          size={RING_SIZE}
          pulsing={isHeartbeat && !reducedMotion}
        />

        {/* Center digits with optional shake */}
        <motion.div
          animate={
            isCritical && !reducedMotion
              ? { x: [0, -1, 1, -1, 0] }
              : { x: 0 }
          }
          transition={
            isCritical && !reducedMotion
              ? { repeat: Infinity, duration: 0.45 }
              : {}
          }
          className="absolute inset-0 flex items-center justify-center font-pixel"
          style={{
            color: ringColor,
            fontSize: 22,
            letterSpacing: "0.04em",
            textShadow: `2px 2px 0 #000`,
            lineHeight: 1,
          }}
        >
          {mins}:{secs.toString().padStart(2, "0")}
        </motion.div>
      </div>
    </div>
  );
}

/* ── PixelRing ──────────────────────────────────────────── */
interface RingProps {
  segments: number;
  litSegments: number;
  color: string;
  size: number;
  pulsing: boolean;
}
function PixelRing({ segments, litSegments, color, size, pulsing }: RingProps) {
  // 16 квадратиков расположены по окружности.
  const radius = size / 2 - 6;
  const center = size / 2;
  const segs: React.ReactElement[] = [];
  for (let i = 0; i < segments; i += 1) {
    // Start at top (12 o'clock), go clockwise
    const angle = (i / segments) * 2 * Math.PI - Math.PI / 2;
    const x = center + radius * Math.cos(angle) - 4;
    const y = center + radius * Math.sin(angle) - 4;
    const isLit = i < litSegments;
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
          background: isLit ? color : "color-mix(in srgb, " + color + " 14%, transparent)",
          boxShadow: isLit ? `0 0 6px ${color}` : "none",
          transition: "background 180ms ease-out, box-shadow 180ms ease-out",
          animation: pulsing && isLit ? "ring-pulse 0.7s ease-in-out infinite" : "none",
        }}
      />,
    );
  }
  return (
    <div className="absolute inset-0">
      {segs}
      <style>{`@keyframes ring-pulse { 0%,100% { opacity: 1 } 50% { opacity: 0.45 } }`}</style>
    </div>
  );
}

/* ── Helper ─────────────────────────────────────────────── */
function computeRemaining(deadline: string | number): number {
  const ms = typeof deadline === "string" ? Date.parse(deadline) : deadline;
  if (Number.isNaN(ms)) return 0;
  return Math.max(0, (ms - Date.now()) / 1000);
}
