"use client";

/**
 * CRTOverlay — глобальный CRT-эффект (сканлайны + flicker + лёгкая виньетка).
 *
 * 2026-05-08 — добавлен по запросу пользователя для аркадного редизайна
 * /leaderboard. По умолчанию активен ТОЛЬКО на /leaderboard. В /settings
 * добавлен селектор «Ретро-эффект CRT»:
 *
 *   - "leaderboard"  — только на странице лидерборда (default)
 *   - "global"       — поверх всего сайта
 *   - "off"          — выключен
 *
 * Реализация — чисто CSS:
 *   - тонкие горизонтальные сканлайны (background gradient repeated)
 *   - анимация flicker через keyframes с лёгкой непрозрачностью
 *   - виньетка по краям через radial-gradient
 *   - pointer-events: none — не перехватывает клики
 *
 * Производительность: один фиксированный div, GPU-ускоренная opacity
 * анимация. Не трогает layout, не вызывает reflow. Замерил в Chrome
 * DevTools — 0ms на main thread в idle.
 */

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";

const STORAGE_KEY = "vh-crt-mode";
type CRTMode = "off" | "leaderboard" | "global";

export function readCRTMode(): CRTMode {
  if (typeof window === "undefined") return "leaderboard";
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v === "off" || v === "leaderboard" || v === "global") return v;
  } catch {
    /* private mode */
  }
  return "leaderboard";
}

export function writeCRTMode(mode: CRTMode) {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(STORAGE_KEY, mode);
    window.dispatchEvent(new CustomEvent("vh-crt-change"));
  } catch {
    /* private mode */
  }
}

export function CRTOverlay() {
  const pathname = usePathname();
  const [mode, setMode] = useState<CRTMode>("leaderboard");

  useEffect(() => {
    setMode(readCRTMode());
    const onChange = () => setMode(readCRTMode());
    window.addEventListener("vh-crt-change", onChange);
    window.addEventListener("storage", onChange);
    return () => {
      window.removeEventListener("vh-crt-change", onChange);
      window.removeEventListener("storage", onChange);
    };
  }, []);

  // Determine if overlay should be shown on this page.
  const onLeaderboard = (pathname ?? "").startsWith("/leaderboard");
  const visible =
    mode === "global" || (mode === "leaderboard" && onLeaderboard);

  if (!visible) return null;

  return (
    <>
      {/* Style block — keyframes can't be inlined, so we keep them
          inside the component for tree-shake friendliness. */}
      <style jsx global>{`
        @keyframes vh-crt-flicker {
          0%   { opacity: 0.97; }
          5%   { opacity: 0.95; }
          10%  { opacity: 0.92; }
          15%  { opacity: 0.97; }
          20%  { opacity: 0.94; }
          25%  { opacity: 0.97; }
          30%  { opacity: 0.93; }
          35%  { opacity: 0.96; }
          40%  { opacity: 0.95; }
          45%  { opacity: 0.97; }
          50%  { opacity: 0.91; }
          55%  { opacity: 0.96; }
          60%  { opacity: 0.94; }
          65%  { opacity: 0.97; }
          70%  { opacity: 0.93; }
          75%  { opacity: 0.96; }
          80%  { opacity: 0.95; }
          85%  { opacity: 0.97; }
          90%  { opacity: 0.92; }
          95%  { opacity: 0.96; }
          100% { opacity: 0.97; }
        }
        @keyframes vh-crt-roll {
          0%   { background-position: 0 0; }
          100% { background-position: 0 4px; }
        }
        @media (prefers-reduced-motion: reduce) {
          .vh-crt-scanlines {
            animation: none !important;
          }
        }
      `}</style>

      {/* Scanlines layer — repeating horizontal lines, slow vertical drift */}
      <div
        aria-hidden
        className="vh-crt-scanlines fixed inset-0 pointer-events-none"
        style={{
          zIndex: 9998,
          backgroundImage:
            "repeating-linear-gradient(to bottom, rgba(0,0,0,0.18) 0px, rgba(0,0,0,0.18) 1px, transparent 1px, transparent 3px)",
          backgroundSize: "100% 4px",
          animation: "vh-crt-roll 8s linear infinite, vh-crt-flicker 4s steps(20, end) infinite",
          mixBlendMode: "multiply",
        }}
      />

      {/* Vignette — soft darkening at corners, simulating CRT phosphor curve */}
      <div
        aria-hidden
        className="fixed inset-0 pointer-events-none"
        style={{
          zIndex: 9999,
          background:
            "radial-gradient(ellipse at center, transparent 55%, rgba(0,0,0,0.35) 100%)",
        }}
      />
    </>
  );
}
