"use client";

import { useEffect } from "react";
import { motion } from "framer-motion";
import { AlertTriangle, RotateCcw, Home } from "lucide-react";
import { sanitizeText } from "@/lib/sanitize";
import { logger } from "@/lib/logger";

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
      className="flex min-h-screen items-center justify-center px-4"
      style={{ background: "var(--bg-primary)" }}
    >
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass-panel max-w-md w-full p-8 text-center"
      >
        <motion.div
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          transition={{ type: "spring", stiffness: 300 }}
          className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl"
          style={{ background: "rgba(255,42,109,0.1)" }}
        >
          <AlertTriangle size={30} style={{ color: "var(--neon-red)" }} />
        </motion.div>

        <h1
          className="font-display text-2xl font-bold tracking-wider mb-2"
          style={{ color: "var(--text-primary)" }}
        >
          SYSTEM ERROR
        </h1>

        <p className="text-sm mb-1" style={{ color: "var(--text-secondary)" }}>
          Произошла непредвиденная ошибка
        </p>

        <p
          className="font-mono text-[10px] mb-6 px-4 py-2 rounded-lg"
          style={{ background: "var(--input-bg)", color: "var(--text-muted)" }}
        >
          {sanitizeText(error.message || "Unknown error")}
          {error.digest && ` [${sanitizeText(error.digest)}]`}
        </p>

        <div className="flex gap-3 justify-center">
          <motion.button
            onClick={() => (window.location.href = "/")}
            className="vh-btn-outline flex items-center gap-2"
            whileTap={{ scale: 0.97 }}
          >
            <Home size={16} />
            На главную
          </motion.button>
          <motion.button
            onClick={reset}
            className="vh-btn-primary flex items-center gap-2"
            whileTap={{ scale: 0.97 }}
          >
            <RotateCcw size={16} />
            Повторить
          </motion.button>
        </div>
      </motion.div>
    </div>
  );
}
