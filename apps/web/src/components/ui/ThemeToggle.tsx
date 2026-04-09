"use client";

import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Sun, Moon } from "lucide-react";

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const [ripple, setRipple] = useState(false);

  useEffect(() => setMounted(true), []);

  if (!mounted) {
    return <div className="h-10 w-10" />;
  }

  const isDark = theme === "dark";

  const toggle = () => {
    setRipple(true);
    setTheme(isDark ? "light" : "dark");
    setTimeout(() => setRipple(false), 600);
  };

  return (
    <motion.button
      onClick={toggle}
      className="relative flex h-10 w-10 items-center justify-center rounded-xl overflow-hidden"
      style={{
        background: "var(--input-bg)",
        border: "1px solid var(--border-color)",
      }}
      whileHover={{
        scale: 1.08,
        borderColor: "var(--accent)",
        boxShadow: "0 0 12px var(--accent-glow)",
      }}
      whileTap={{ scale: 0.9, rotate: isDark ? 15 : -15 }}
      transition={{ type: "spring", stiffness: 400, damping: 20 }}
      aria-label={isDark ? "Включить светлую тему" : "Включить тёмную тему"}
    >
      {/* Ripple effect on toggle */}
      <AnimatePresence>
        {ripple && (
          <motion.div
            className="absolute inset-0 rounded-xl"
            initial={{ scale: 0, opacity: 0.5 }}
            animate={{ scale: 2.5, opacity: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.6, ease: "easeOut" }}
            style={{ background: isDark ? "var(--warning)" : "var(--accent)" }}
          />
        )}
      </AnimatePresence>

      {/* Icon transition */}
      <AnimatePresence mode="wait" initial={false}>
        {isDark ? (
          <motion.div
            key="moon"
            initial={{ y: 20, opacity: 0, rotate: -45 }}
            animate={{ y: 0, opacity: 1, rotate: 0 }}
            exit={{ y: -20, opacity: 0, rotate: 45 }}
            transition={{ duration: 0.25, ease: "easeOut" }}
            className="relative z-10"
          >
            <Moon size={17} style={{ color: "var(--text-secondary)" }} />
          </motion.div>
        ) : (
          <motion.div
            key="sun"
            initial={{ y: -20, opacity: 0, rotate: 45 }}
            animate={{ y: 0, opacity: 1, rotate: 0 }}
            exit={{ y: 20, opacity: 0, rotate: -45 }}
            transition={{ duration: 0.25, ease: "easeOut" }}
            className="relative z-10"
          >
            <Sun size={17} style={{ color: "var(--warning)" }} />
          </motion.div>
        )}
      </AnimatePresence>
    </motion.button>
  );
}
