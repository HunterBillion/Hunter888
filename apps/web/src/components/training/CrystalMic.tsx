"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Mic, Keyboard, Loader2 } from "lucide-react";
import { useReducedMotion } from "@/hooks/useReducedMotion";

interface CrystalMicProps {
  isRecording: boolean;
  isProcessing: boolean;
  audioLevel: number;
  onPress: () => void;
  onRelease: () => void;
  onTextMode: () => void;
  disabled: boolean;
  /** 2026-04-18 new: "toggle" = tap-to-start / tap-to-stop (default, user request).
      "hold" = legacy hold-to-record. */
  mode?: "toggle" | "hold";
}

export function CrystalMic({
  isRecording,
  isProcessing,
  audioLevel,
  onPress,
  onRelease,
  onTextMode,
  disabled,
  mode = "toggle",
}: CrystalMicProps) {
  const normalizedLevel = Math.min(audioLevel / 100, 1);
  const reducedMotion = useReducedMotion();

  // P2-23: Show tooltip on first use
  const [showTooltip, setShowTooltip] = useState(false);
  useEffect(() => {
    const seen = localStorage.getItem("vh_mic_tooltip_seen");
    if (!seen) {
      setShowTooltip(true);
      const timer = setTimeout(() => {
        setShowTooltip(false);
        localStorage.setItem("vh_mic_tooltip_seen", "1");
      }, 5000);
      return () => clearTimeout(timer);
    }
  }, []);

  const dismissTooltip = () => {
    setShowTooltip(false);
    localStorage.setItem("vh_mic_tooltip_seen", "1");
  };

  return (
    // Phase F2.1 (2026-04-20): wrapper теперь `relative`, раньше был просто
    // flex-col → tooltip с `absolute -top-16` позиционировался относительно
    // дальнего ancestor'а и «прыгал» при скролле / reflow. Владелец писал:
    // «подсказки то наверху то внизу». Теперь привязан к самому компоненту.
    <div className="relative flex flex-col items-center gap-4">
      {/* P2-23: First-use tooltip */}
      <AnimatePresence>
        {showTooltip && (
          <motion.div
            initial={{ opacity: 0, y: 10, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 5, scale: 0.95 }}
            className="absolute -top-16 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-xl px-4 py-2.5 text-xs font-medium z-50"
            style={{
              background: "var(--accent)",
              color: "white",
              boxShadow: "0 4px 20px var(--accent-glow)",
            }}
            onClick={dismissTooltip}
          >
            Удерживайте для записи голоса
            <div className="absolute -bottom-1.5 left-1/2 -translate-x-1/2 w-3 h-3 rotate-45" style={{ background: "var(--accent)" }} />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Status text */}
      <span
        className="font-mono text-xs tracking-widest uppercase transition-colors"
        style={{
          color: isRecording ? "var(--magenta)" : isProcessing ? "var(--accent)" : "var(--text-muted)",
        }}
      >
        {isRecording ? "Говорите..." : isProcessing ? "Обработка..." : "Нажмите и удерживайте"}
      </span>

      {/* Crystal mic button */}
      <div className="relative cursor-pointer group">
        {/* Outer glow rings (visible when recording) */}
        {isRecording && !reducedMotion && (
          <>
            <motion.div
              className="absolute inset-[-20px] rounded-full opacity-20"
              style={{ background: "var(--accent)" }}
              animate={{
                scale: [1, 1.3 + normalizedLevel * 0.3, 1],
                opacity: [0.15, 0.05, 0.15],
              }}
              transition={{ duration: 1.5, repeat: Infinity }}
            />
            <motion.div
              className="absolute inset-[-12px] rounded-full opacity-30"
              style={{ background: "var(--magenta)" }}
              animate={{
                scale: [1, 1.2 + normalizedLevel * 0.2, 1],
                opacity: [0.2, 0.08, 0.2],
              }}
              transition={{ duration: 1.2, repeat: Infinity, delay: 0.2 }}
            />
            <motion.div
              className="absolute inset-[-6px] rounded-full opacity-40"
              style={{ background: "var(--accent)" }}
              animate={{
                scale: [1, 1.1 + normalizedLevel * 0.15, 1],
                opacity: [0.3, 0.1, 0.3],
              }}
              transition={{ duration: 1, repeat: Infinity, delay: 0.4 }}
            />
          </>
        )}

        {/* Blur glow behind */}
        <div
          className="absolute inset-[-10px] rounded-full blur-xl transition-opacity"
          style={{
            background: isRecording ? "var(--magenta)" : "var(--accent)",
            opacity: isRecording ? 0.4 : 0.15,
          }}
        />

        {/* Crystal hexagon
            2026-04-18: default mode="toggle" — one tap to start, another to stop.
            Legacy mode="hold" retained for components that still rely on hold-and-release. */}
        <motion.button
          aria-label={
            mode === "toggle"
              ? (isRecording ? "Нажмите чтобы остановить запись" : isProcessing ? "Обработка…" : "Нажмите чтобы начать запись")
              : (isRecording ? "Запись голоса" : isProcessing ? "Обработка" : "Нажмите и удерживайте для записи")
          }
          role="button"
          onClick={!disabled && mode === "toggle"
            ? () => { if (isRecording) onRelease(); else onPress(); }
            : undefined
          }
          onMouseDown={!disabled && mode === "hold" ? onPress : undefined}
          onMouseUp={!disabled && mode === "hold" ? onRelease : undefined}
          onMouseLeave={!disabled && mode === "hold" ? onRelease : undefined}
          onTouchStart={!disabled && mode === "hold" ? onPress : undefined}
          onTouchEnd={!disabled && mode === "hold" ? onRelease : undefined}
          disabled={disabled}
          className="crystal-shape relative z-10 flex items-center justify-center"
          style={{
            width: "clamp(64px, 10vw, 80px)",
            height: "clamp(76px, 12vw, 96px)",
            background: isRecording
              ? "linear-gradient(135deg, rgba(224,40,204,0.8) 0%, rgba(107,77,199,0.9) 100%)"
              : isProcessing
                ? "var(--bg-tertiary)"
                : "rgba(255,255,255,0.08)",
            backdropFilter: "blur(12px)",
            border: "1px solid rgba(255,255,255,0.15)",
            boxShadow: isRecording
              ? "0 0 30px rgba(224,40,204,0.5), 0 8px 32px rgba(0,0,0,0.3)"
              : "0 8px 32px rgba(0,0,0,0.3)",
            opacity: disabled ? 0.4 : 1,
          }}
          whileHover={!disabled ? { scale: 1.05 } : undefined}
          whileTap={!disabled ? { scale: 0.95 } : undefined}
        >
          {/* Inner crystal */}
          <div
            className="crystal-inner absolute inset-[2px] z-0 transition-colors"
            style={{
              background: isRecording
                ? "linear-gradient(135deg, rgba(224,40,204,0.6) 0%, rgba(107,77,199,0.7) 100%)"
                : "linear-gradient(135deg, var(--bg-tertiary) 0%, var(--bg-primary) 100%)",
            }}
          />

          {/* Icon */}
          {isProcessing ? (
            <Loader2 size={28} className="relative z-20 animate-spin text-white" />
          ) : (
            <motion.div className="relative z-20" animate={isRecording && !reducedMotion ? { scale: [1, 1.15, 1] } : {}} transition={{ duration: 0.8, repeat: Infinity }}>
              <Mic
                size={28}
                className="drop-shadow-[0_0_8px_rgba(255,255,255,0.8)]"
                style={{ color: isRecording ? "white" : "var(--text-primary)" }}
              />
            </motion.div>
          )}
        </motion.button>
      </div>

      {/* Text mode toggle */}
      <motion.button
        onClick={onTextMode}
        className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 font-mono text-xs uppercase tracking-widest transition-colors"
        style={{
          background: "var(--input-bg)",
          border: "1px solid var(--border-color)",
          color: "var(--text-muted)",
        }}
        whileHover={{ borderColor: "var(--accent)", color: "var(--accent)" }}
        whileTap={{ scale: 0.95 }}
      >
        <Keyboard size={12} />
        Текстовый режим
      </motion.button>
    </div>
  );
}
