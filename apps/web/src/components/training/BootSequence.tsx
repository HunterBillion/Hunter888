"use client";

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";

// ═══════════════════════════════════════════════════════════
//  BootSequence — pixel typewriter loading screen
//  Replaces spinner during training session WS connect
//  Runs in parallel with actual connection (no added delay)
// ═══════════════════════════════════════════════════════════

interface BootSequenceProps {
  /** Status text from WS connection (e.g. "ЗАПУСК AI-ИСТОРИИ...") */
  statusText?: string;
  /** Session metadata from store/URL params */
  scenarioTitle?: string;
  characterName?: string;
  difficulty?: number;
  callNumber?: number;
  totalCalls?: number;
  /** Whether WS is connected (controls skip button visibility) */
  isConnected?: boolean;
  /** Called when user clicks Skip */
  onSkip?: () => void;
}

const LINE_DELAY = 0.35; // seconds between lines

export function BootSequence({
  statusText,
  scenarioTitle,
  characterName,
  difficulty,
  callNumber,
  totalCalls,
  isConnected,
  onSkip,
}: BootSequenceProps) {
  const [visibleLines, setVisibleLines] = useState(0);
  const [showCursor, setShowCursor] = useState(true);

  // Build boot lines from available data
  const lines = useCallback(() => {
    const l: { text: string; color?: string }[] = [];
    l.push({ text: "> Инициализация системы...", color: "var(--text-muted)" });
    if (scenarioTitle) {
      l.push({ text: `> Сценарий: ${scenarioTitle}`, color: "var(--accent)" });
    }
    if (characterName) {
      l.push({ text: `> Клиент: ${characterName}`, color: "var(--text-secondary)" });
    }
    if (difficulty) {
      const label = difficulty <= 3 ? "EASY" : difficulty <= 5 ? "NORMAL" : difficulty <= 7 ? "HARD" : "NIGHTMARE";
      const color = difficulty <= 3 ? "var(--success)" : difficulty <= 5 ? "var(--warning)" : difficulty <= 7 ? "#ff8800" : "var(--danger)";
      l.push({ text: `> Сложность: ${difficulty}/10 [${label}]`, color });
    }
    if (callNumber && totalCalls) {
      l.push({ text: `> Звонок: ${callNumber}/${totalCalls}`, color: "var(--info)" });
    }
    if (statusText) {
      l.push({ text: `> ${statusText}`, color: "var(--text-muted)" });
    }
    l.push({ text: "> ОХОТА НАЧИНАЕТСЯ", color: "var(--warning, #d4a84b)" });
    return l;
  }, [scenarioTitle, characterName, difficulty, callNumber, totalCalls, statusText]);

  const allLines = lines();

  // Reveal lines one by one
  useEffect(() => {
    if (visibleLines >= allLines.length) return;
    const timer = setTimeout(() => setVisibleLines((v) => v + 1), LINE_DELAY * 1000);
    return () => clearTimeout(timer);
  }, [visibleLines, allLines.length]);

  // Blink cursor
  useEffect(() => {
    const id = setInterval(() => setShowCursor((v) => !v), 530);
    return () => clearInterval(id);
  }, []);

  return (
    <div
      className="flex h-screen flex-col items-center justify-center px-6"
      style={{ background: "#0e0b1a" }}
    >
      <div className="w-full max-w-md">
        {/* Terminal header */}
        <div
          className="flex items-center gap-2 px-4 py-2 rounded-t-none"
          style={{ background: "#1a1530", borderBottom: "2px solid var(--accent)" }}
        >
          <div className="flex gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full" style={{ background: "#ff5f57" }} />
            <div className="w-2.5 h-2.5 rounded-full" style={{ background: "#febc2e" }} />
            <div className="w-2.5 h-2.5 rounded-full" style={{ background: "#28c840" }} />
          </div>
          <span className="font-pixel text-[10px] ml-2 uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
            xhunter — boot
          </span>
        </div>

        {/* Terminal body */}
        <div
          className="px-5 py-6 min-h-[200px] pixel-border"
          style={{ "--pixel-border-color": "var(--accent)", background: "#0e0b1a" } as React.CSSProperties}
        >
          <AnimatePresence>
            {allLines.slice(0, visibleLines).map((line, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.15 }}
                className="font-pixel text-sm leading-relaxed mb-1"
                style={{ color: line.color ?? "var(--text-secondary)" }}
              >
                {line.text}
              </motion.div>
            ))}
          </AnimatePresence>

          {/* Blinking cursor */}
          {visibleLines < allLines.length && (
            <span
              className="font-pixel text-sm inline-block"
              style={{ color: "var(--accent)", opacity: showCursor ? 1 : 0 }}
            >
              _
            </span>
          )}

          {/* Final glow when all lines shown */}
          {visibleLines >= allLines.length && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="mt-3 font-pixel text-xs uppercase tracking-wider pixel-glow"
              style={{ color: "var(--accent)" }}
            >
              {showCursor ? "▶ LOADING..." : "▶ LOADING..."}
            </motion.div>
          )}
        </div>
      </div>

      {/* Skip button — only shows when WS is connected (don't skip real loading) */}
      {isConnected && visibleLines >= 2 && (
        <motion.button
          initial={{ opacity: 0 }}
          animate={{ opacity: 0.5 }}
          whileHover={{ opacity: 1 }}
          onClick={onSkip}
          className="mt-6 font-pixel text-[10px] uppercase tracking-wider px-3 py-1"
          style={{ color: "var(--text-muted)", border: "1px solid var(--border-color)" }}
        >
          SKIP ▶
        </motion.button>
      )}
    </div>
  );
}
