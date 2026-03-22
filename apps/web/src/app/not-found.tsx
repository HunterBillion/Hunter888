"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { Crosshair, Home, ArrowLeft } from "lucide-react";

export default function NotFound() {
  return (
    <div
      className="flex min-h-screen items-center justify-center px-4"
      style={{ background: "var(--bg-primary)" }}
    >
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="text-center"
      >
        <motion.div
          initial={{ scale: 0 }}
          animate={{ scale: 1, rotate: [0, 10, -10, 0] }}
          transition={{ type: "spring", stiffness: 200 }}
          className="mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-2xl"
          style={{ background: "var(--accent-muted)" }}
        >
          <Crosshair size={36} style={{ color: "var(--accent)" }} />
        </motion.div>

        <h1
          className="font-display text-6xl font-black tracking-wider mb-2"
          style={{ color: "var(--accent)" }}
        >
          404
        </h1>

        <p className="font-mono text-sm tracking-wider mb-1" style={{ color: "var(--text-primary)" }}>
          SIGNAL NOT FOUND
        </p>
        <p className="text-sm mb-8" style={{ color: "var(--text-muted)" }}>
          Эта частота не зарегистрирована в системе
        </p>

        <div className="flex gap-3 justify-center">
          <Link href="/">
            <motion.span className="vh-btn-outline flex items-center gap-2" whileTap={{ scale: 0.97 }}>
              <ArrowLeft size={16} /> Назад
            </motion.span>
          </Link>
          <Link href="/home">
            <motion.span className="vh-btn-primary flex items-center gap-2" whileTap={{ scale: 0.97 }}>
              <Home size={16} /> Командный центр
            </motion.span>
          </Link>
        </div>
      </motion.div>
    </div>
  );
}
