"use client";

/**
 * VsBanner — pre-match overlay «<NAME> vs <NAME>» с пиксельным «VS» центром.
 *
 * 2026-04-29 (Фаза 3): показывается в начале матча на ~2 секунды или пока
 * пользователь не закроет вручную. Блокирует чат под собой через z-index.
 *
 * Используется через локальный state в parent: setVsOpen(true) при `match.found`,
 * setVsOpen(false) через setTimeout 2200ms или по onDone.
 */

import * as React from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  type PvPRankTier,
  PVP_RANK_COLORS,
  normalizeRankTier,
} from "@/types";

interface Props {
  open: boolean;
  leftName: string;
  rightName: string;
  leftTier?: PvPRankTier | string;
  rightTier?: PvPRankTier | string;
  /** Длительность отображения в мс перед auto-close. По умолчанию 2200. */
  durationMs?: number;
  onDone?: () => void;
}

function tierColorOf(tier?: PvPRankTier | string): string {
  if (!tier) return "var(--text-muted)";
  const norm = normalizeRankTier(typeof tier === "string" ? tier : tier);
  return PVP_RANK_COLORS[norm] ?? "var(--text-muted)";
}

export function VsBanner({
  open,
  leftName,
  rightName,
  leftTier,
  rightTier,
  durationMs = 2200,
  onDone,
}: Props) {
  React.useEffect(() => {
    if (!open || !onDone) return;
    const id = window.setTimeout(onDone, durationMs);
    return () => window.clearTimeout(id);
  }, [open, durationMs, onDone]);

  const leftColor = tierColorOf(leftTier);
  const rightColor = tierColorOf(rightTier);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          role="dialog"
          aria-modal="true"
          aria-label="Старт матча"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
          className="fixed inset-0 z-[9000] flex items-center justify-center"
          style={{
            background:
              "radial-gradient(ellipse at center, rgba(0,0,0,0.65) 0%, rgba(0,0,0,0.92) 100%)",
            backgroundImage: `
              radial-gradient(ellipse at center, rgba(0,0,0,0.55) 0%, rgba(0,0,0,0.92) 100%),
              repeating-linear-gradient(0deg, transparent 0, transparent 7px, rgba(255,255,255,0.025) 7px, rgba(255,255,255,0.025) 8px),
              repeating-linear-gradient(90deg, transparent 0, transparent 7px, rgba(255,255,255,0.025) 7px, rgba(255,255,255,0.025) 8px)
            `,
          }}
        >
          <div className="flex items-center gap-6 sm:gap-12 px-4">
            {/* Left fighter name */}
            <motion.div
              initial={{ x: -120, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: -120, opacity: 0 }}
              transition={{ type: "spring", stiffness: 200, damping: 22, delay: 0.1 }}
              className="text-right"
            >
              <span
                className="font-pixel block"
                style={{
                  color: leftColor,
                  fontSize: "clamp(28px, 6vw, 56px)",
                  letterSpacing: "0.16em",
                  textTransform: "uppercase",
                  textShadow: `4px 4px 0 #000, 0 0 20px ${leftColor}`,
                  lineHeight: 1,
                }}
              >
                {leftName}
              </span>
            </motion.div>

            {/* VS */}
            <motion.div
              initial={{ scale: 0.4, opacity: 0, rotate: -15 }}
              animate={{ scale: 1, opacity: 1, rotate: 0 }}
              exit={{ scale: 0.6, opacity: 0 }}
              transition={{ type: "spring", stiffness: 360, damping: 18, delay: 0.4 }}
              className="font-pixel relative"
              style={{
                color: "var(--accent)",
                fontSize: "clamp(64px, 12vw, 140px)",
                letterSpacing: "-0.04em",
                textShadow: `6px 6px 0 #000, 0 0 36px var(--accent-glow), 0 0 60px var(--accent)`,
                lineHeight: 1,
              }}
            >
              VS
              {/* glow ring */}
              <motion.span
                aria-hidden
                className="absolute inset-0"
                animate={{ opacity: [0.3, 0.8, 0.3] }}
                transition={{ duration: 1.4, repeat: Infinity }}
                style={{
                  textShadow:
                    "0 0 24px var(--accent), 0 0 48px var(--accent), 0 0 96px var(--magenta)",
                }}
              >
                VS
              </motion.span>
            </motion.div>

            {/* Right fighter name */}
            <motion.div
              initial={{ x: 120, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: 120, opacity: 0 }}
              transition={{ type: "spring", stiffness: 200, damping: 22, delay: 0.1 }}
              className="text-left"
            >
              <span
                className="font-pixel block"
                style={{
                  color: rightColor,
                  fontSize: "clamp(28px, 6vw, 56px)",
                  letterSpacing: "0.16em",
                  textTransform: "uppercase",
                  textShadow: `4px 4px 0 #000, 0 0 20px ${rightColor}`,
                  lineHeight: 1,
                }}
              >
                {rightName}
              </span>
            </motion.div>
          </div>

          {/* FIGHT! ribbon — после небольшой задержки */}
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 1.0, duration: 0.3 }}
            className="absolute bottom-[20%] font-pixel"
            style={{
              color: "var(--danger)",
              fontSize: "clamp(20px, 3.5vw, 38px)",
              letterSpacing: "0.4em",
              textTransform: "uppercase",
              textShadow: "3px 3px 0 #000, 0 0 18px var(--danger)",
            }}
          >
            БОЙ!
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
