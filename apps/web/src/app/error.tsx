"use client";

import { useEffect } from "react";
import { motion } from "framer-motion";
import { RotateCcw, Home } from "lucide-react";
import { sanitizeText } from "@/lib/sanitize";
import { logger } from "@/lib/logger";
import { EASE_SNAP } from "@/lib/constants";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    logger.error("App error:", error);
  }, [error]);

  return (
    <div
      className="relative flex min-h-screen items-center justify-center overflow-hidden px-4"
      style={{ background: "var(--bg-primary)" }}
    >
      {/* Giant "500" background */}
      <motion.div
        className="pointer-events-none absolute inset-0 flex items-center justify-center select-none"
        initial={{ opacity: 0, scale: 0.8 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 1.2, ease: EASE_SNAP }}
      >
        <span
          className="font-display font-black leading-none"
          style={{
            fontSize: "clamp(180px, 30vw, 400px)",
            color: "transparent",
            WebkitTextStroke: "2px rgba(255,42,109,0.5)",
            opacity: 0.1,
            filter: "blur(1px)",
          }}
        >
          ERR
        </span>
      </motion.div>

      {/* Scanline overlay */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background: "repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(255,42,109,0.01) 2px, rgba(255,42,109,0.01) 4px)",
        }}
      />

      {/* Animated glitch line */}
      <motion.div
        className="pointer-events-none absolute left-0 right-0 h-[1px]"
        style={{ background: "rgba(255,42,109,0.3)" }}
        initial={{ top: "20%" }}
        animate={{ top: ["20%", "80%", "45%", "65%", "30%"] }}
        transition={{ duration: 8, repeat: Infinity, ease: "linear" }}
      />

      {/* Content */}
      <div className="relative z-10 text-center max-w-lg">
        {/* Error icon — pulsing ring */}
        <motion.div
          className="mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-full"
          style={{
            background: "rgba(255,42,109,0.08)",
            border: "2px solid rgba(255,42,109,0.2)",
            boxShadow: "0 0 40px rgba(255,42,109,0.1)",
          }}
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          transition={{ type: "spring", stiffness: 200, delay: 0.1 }}
        >
          <motion.div
            className="font-display text-2xl font-black"
            style={{ color: "var(--neon-red, #FF2A6D)" }}
            animate={{ opacity: [1, 0.5, 1] }}
            transition={{ duration: 2, repeat: Infinity }}
          >
            !
          </motion.div>
        </motion.div>

        {/* Terminal label */}
        <motion.div
          className="font-mono text-xs tracking-[0.3em] uppercase mb-3"
          style={{ color: "rgba(255,42,109,0.6)" }}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.2 }}
        >
          {"// СИСТЕМНАЯ_ОШИБКА"}
        </motion.div>

        {/* Title */}
        <motion.h1
          className="font-display text-3xl font-black tracking-tight mb-3"
          style={{ color: "var(--text-primary)" }}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.3 }}
        >
          Что-то пошло не так
        </motion.h1>

        {/* Description */}
        <motion.p
          className="text-sm mb-4"
          style={{ color: "var(--text-muted)" }}
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.4 }}
        >
          Произошла непредвиденная ошибка. Попробуйте перезагрузить страницу.
        </motion.p>

        {/* Error details — terminal block */}
        <motion.div
          className="font-mono text-xs rounded-xl px-5 py-3 mb-8 text-left mx-auto max-w-md"
          style={{
            background: "var(--input-bg)",
            border: "1px solid var(--border-color)",
            color: "var(--text-muted)",
          }}
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.5 }}
        >
          <span style={{ color: "rgba(255,42,109,0.6)" }}>{">"} </span>
          {sanitizeText(error.message || "Unknown error")}
          {error.digest && (
            <span style={{ opacity: 0.4 }}>{` [${sanitizeText(error.digest)}]`}</span>
          )}
        </motion.div>

        {/* Buttons */}
        <motion.div
          className="flex gap-3 justify-center"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.6 }}
        >
          <motion.button
            onClick={reset}
            className="flex items-center gap-2 rounded-xl px-5 py-3 text-sm font-semibold transition-colors"
            style={{
              background: "var(--accent)",
              color: "#fff",
              boxShadow: "0 0 20px var(--accent-glow), 0 4px 12px rgba(0,0,0,0.2)",
            }}
            whileHover={{ scale: 1.03, y: -1 }}
            whileTap={{ scale: 0.97 }}
          >
            <RotateCcw size={16} />
            Попробовать снова
          </motion.button>
          <motion.button
            onClick={() => (window.location.href = "/home")}
            className="flex items-center gap-2 rounded-xl px-5 py-3 text-sm font-semibold transition-colors"
            style={{
              background: "var(--input-bg)",
              color: "var(--text-primary)",
              border: "1px solid var(--border-color)",
            }}
            whileHover={{ scale: 1.03, y: -1 }}
            whileTap={{ scale: 0.97 }}
          >
            <Home size={16} />
            На главную
          </motion.button>
        </motion.div>
      </div>
    </div>
  );
}
