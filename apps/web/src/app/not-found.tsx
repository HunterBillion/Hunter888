"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { Home } from "lucide-react";
import { BackButton } from "@/components/ui/BackButton";
import { EASE_SNAP } from "@/lib/constants";

export default function NotFound() {
  return (
    <div
      className="relative flex min-h-screen items-center justify-center overflow-hidden px-4"
      style={{ background: "var(--bg-primary)" }}
    >
      {/* Giant "404" background — IYO-style viewport fill */}
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
            WebkitTextStroke: "2px var(--accent)",
            opacity: 0.12,
            filter: "blur(1px)",
          }}
        >
          404
        </span>
      </motion.div>

      {/* Scanline overlay */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background: "repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(107,77,199,0.015) 2px, rgba(107,77,199,0.015) 4px)",
        }}
      />

      {/* Content */}
      <div className="relative z-10 text-center">
        {/* Error code */}
        <motion.h1
          className="font-display font-black tracking-tighter"
          style={{
            fontSize: "clamp(80px, 15vw, 160px)",
            lineHeight: 0.9,
            color: "var(--accent)",
            textShadow: "0 0 60px var(--accent-glow), 0 0 120px var(--accent-muted)",
          }}
          initial={{ opacity: 0, y: 40 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, ease: EASE_SNAP }}
        >
          404
        </motion.h1>

        {/* Terminal label */}
        <motion.div
          className="font-mono text-xs tracking-widest uppercase mt-4 mb-2"
          style={{ color: "var(--text-muted)" }}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.2 }}
        >
          {"// СТРАНИЦА_НЕ_НАЙДЕНА"}
        </motion.div>

        {/* Divider line */}
        <motion.div
          className="mx-auto my-5"
          style={{
            height: "1px",
            width: "80px",
            background: "linear-gradient(90deg, transparent, var(--accent), transparent)",
          }}
          initial={{ scaleX: 0 }}
          animate={{ scaleX: 1 }}
          transition={{ duration: 0.8, delay: 0.3 }}
        />

        {/* Message */}
        <motion.p
          className="text-base mb-2 font-medium"
          style={{ color: "var(--text-primary)" }}
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.4 }}
        >
          Запрашиваемая страница не существует
        </motion.p>
        <motion.p
          className="text-sm mb-10 max-w-sm mx-auto"
          style={{ color: "var(--text-muted)" }}
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.5 }}
        >
          Возможно, она была перемещена или удалена. Проверьте адрес или вернитесь на главную.
        </motion.p>

        {/* Buttons */}
        <motion.div
          className="flex gap-3 justify-center"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.6 }}
        >
          <BackButton href="/" />
          <Link href="/home">
            <motion.span
              className="flex items-center gap-2 rounded-xl px-5 py-3 text-sm font-semibold transition-colors"
              style={{
                background: "var(--accent)",
                color: "#fff",
                boxShadow: "0 0 20px var(--accent-glow), 0 4px 12px rgba(0,0,0,0.2)",
              }}
              whileHover={{ scale: 1.03, y: -1 }}
              whileTap={{ scale: 0.97 }}
            >
              <Home size={16} /> Командный центр
            </motion.span>
          </Link>
        </motion.div>
      </div>
    </div>
  );
}
