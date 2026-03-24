"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { motion } from "framer-motion";
import { Crosshair, Mail, ArrowRight, AlertCircle } from "lucide-react";
import { api } from "@/lib/api";
import { setTokens } from "@/lib/auth";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { LogoSeparator } from "@/components/ui/LogoSeparator";
import { PasswordInput } from "@/components/ui/PasswordInput";
import dynamic from "next/dynamic";
const WaveScene = dynamic(
  () => import("@/components/landing/WaveScene").then((m) => m.WaveScene),
  { ssr: false },
);
import { FishermanError } from "@/components/errors/FishermanError";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [networkError, setNetworkError] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const data = await api.post("/auth/login", { email: email.trim(), password });
      setTokens(data.access_token, data.refresh_token);
      if (data.must_change_password) {
        router.push("/change-password");
      } else {
        router.push("/home");
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Ошибка входа";
      if (msg.includes("недоступен") || msg.includes("fetch") || msg.includes("network")) {
        setNetworkError(true);
      } else {
        setError(msg);
      }
    } finally {
      setLoading(false);
    }
  };

  if (networkError) {
    return (
      <FishermanError
        onRetry={() => { setNetworkError(false); setError(""); }}
        message="Похоже, рыба сегодня не клюёт..."
      />
    );
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center px-4 overflow-hidden" style={{ background: "var(--bg-primary)" }}>
      {/* Ambient glow */}
      <div className="fixed inset-0 z-0 pointer-events-none" style={{ background: "radial-gradient(ellipse at 50% 70%, rgba(138,43,226,0.15) 0%, transparent 60%)" }} />

      {/* 3D Wave Background */}
      <div className="fixed inset-0 z-[1]">
        <WaveScene />
      </div>

      {/* Theme toggle */}
      <div className="absolute right-4 top-4 z-10">
        <ThemeToggle />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 20, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.5 }}
        className="glass-panel w-full max-w-md p-8 relative z-10"
        style={{ borderColor: "var(--glass-border)" }}
      >
        {/* Purple accent line on top */}
        <div className="absolute top-0 left-6 right-6 h-[2px] rounded-full" style={{ background: "linear-gradient(90deg, transparent, var(--accent), transparent)" }} />

        <div className="mb-8 text-center">
          {/* Animated logo icon — orbiting rings */}
          <motion.div
            initial={{ scale: 0.5, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ type: "spring", stiffness: 200, delay: 0.1 }}
            className="relative mx-auto mb-5 h-16 w-16 flex items-center justify-center"
          >
            {/* Outer rotating ring */}
            <motion.div
              className="absolute inset-0 rounded-full"
              style={{ border: "1.5px solid var(--accent)", opacity: 0.4 }}
              animate={{ rotate: 360 }}
              transition={{ duration: 8, repeat: Infinity, ease: "linear" }}
            />
            {/* Middle ring — counter-rotate */}
            <motion.div
              className="absolute inset-2 rounded-full"
              style={{ border: "1px dashed var(--accent)", opacity: 0.25 }}
              animate={{ rotate: -360 }}
              transition={{ duration: 12, repeat: Infinity, ease: "linear" }}
            />
            {/* Core glow */}
            <motion.div
              className="w-6 h-6 rounded-full"
              style={{ background: "var(--accent)" }}
              animate={{
                boxShadow: [
                  "0 0 15px var(--accent-glow)",
                  "0 0 35px var(--accent-glow)",
                  "0 0 15px var(--accent-glow)",
                ],
                scale: [1, 1.15, 1],
              }}
              transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
            />
            {/* Orbiting dot */}
            <motion.div
              className="absolute w-2 h-2 rounded-full"
              style={{ background: "var(--accent)", boxShadow: "0 0 8px var(--accent)" }}
              animate={{
                x: [24, 0, -24, 0, 24],
                y: [0, -24, 0, 24, 0],
              }}
              transition={{ duration: 4, repeat: Infinity, ease: "linear" }}
            />
          </motion.div>

          {/* Logo text */}
          <motion.h1
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="font-display text-[2.375rem] font-black tracking-[0.2em] inline-flex items-center justify-center"
          >
            <span style={{ color: "var(--accent)" }}>X</span>
            <LogoSeparator size={32} />
            <span style={{ color: "var(--text-primary)" }}>HUNTER</span>
          </motion.h1>
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.5 }}
            className="mt-2 font-mono text-xs tracking-[0.4em] uppercase"
            style={{ color: "var(--text-muted)" }}
          >
            Neural Sales Environment
          </motion.p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          {error && (
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex items-center gap-2 rounded-xl p-3 text-sm"
              style={{
                background: "rgba(255, 51, 51, 0.08)",
                border: "1px solid rgba(255, 51, 51, 0.2)",
                color: "var(--neon-red)",
              }}
            >
              <AlertCircle size={16} />
              {error}
            </motion.div>
          )}

          <div>
            <label htmlFor="email" className="vh-label">Email</label>
            <div className="relative">
              <Mail size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2" style={{ color: "var(--text-muted)" }} />
              <input
                id="email"
                type="text"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="vh-input pl-10"
                placeholder="you@example.com"
                aria-label="Email"
                autoComplete="email"
              />
            </div>
          </div>

          <div>
            <label htmlFor="password" className="vh-label">Пароль</label>
            <PasswordInput
              id="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              ariaLabel="Пароль"
            />
          </div>

          <motion.button
            type="submit"
            disabled={loading}
            className="vh-btn-primary flex w-full items-center justify-center gap-2"
            whileHover={{ scale: 1.01 }}
            whileTap={{ scale: 0.99 }}
          >
            {loading ? (
              <div className="h-5 w-5 animate-spin rounded-full border-2 border-white/30 border-t-white" />
            ) : (
              <>
                Войти
                <ArrowRight size={16} />
              </>
            )}
          </motion.button>

          {/* Social login */}
          <div className="relative">
            <div className="flex items-center gap-3 my-1">
              <div className="flex-1 h-px" style={{ background: "var(--border-color)" }} />
              <span className="font-mono text-[9px] tracking-wider" style={{ color: "var(--text-muted)" }}>ИЛИ</span>
              <div className="flex-1 h-px" style={{ background: "var(--border-color)" }} />
            </div>
            <div className="flex gap-3 mt-3">
              <motion.button
                type="button"
                className="flex-1 flex items-center justify-center gap-2 rounded-xl py-2.5 text-sm transition-colors"
                style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)", color: "var(--text-secondary)" }}
                whileHover={{ borderColor: "var(--border-hover)" }}
                whileTap={{ scale: 0.97 }}
                onClick={async () => {
                  try {
                    const data = await api.get("/auth/google/login");
                    if (data?.url) window.location.href = data.url;
                  } catch (err: unknown) {
                    setError(err instanceof Error ? err.message : "Google OAuth недоступен");
                  }
                }}
              >
                <svg width="16" height="16" viewBox="0 0 24 24"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/></svg>
                Google
              </motion.button>
              <motion.button
                type="button"
                className="flex-1 flex items-center justify-center gap-2 rounded-xl py-2.5 text-sm transition-colors"
                style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)", color: "var(--text-secondary)" }}
                whileHover={{ borderColor: "var(--border-hover)" }}
                whileTap={{ scale: 0.97 }}
                onClick={async () => {
                  try {
                    const data = await api.get("/auth/yandex/login");
                    if (data?.url) window.location.href = data.url;
                  } catch (err: unknown) {
                    setError(err instanceof Error ? err.message : "Yandex OAuth недоступен");
                  }
                }}
              >
                <svg width="16" height="16" viewBox="0 0 24 24"><path d="M2 12C2 6.48 6.48 2 12 2s10 4.48 10 10-4.48 10-10 10S2 17.52 2 12z" fill="#FC3F1D"/><path d="M13.32 17.5h-1.88V7.38h-.97c-1.57 0-2.39.8-2.39 1.95 0 1.3.59 1.9 1.8 2.7l1 .65-2.9 4.82H6l2.62-4.33C7.37 12.26 6.56 11.22 6.56 9.5c0-2.07 1.45-3.5 4-3.5h2.76V17.5z" fill="white"/></svg>
                Yandex
              </motion.button>
            </div>
          </div>
        </form>

        <p className="mt-5 text-center text-sm" style={{ color: "var(--text-muted)" }}>
          Нет аккаунта?{" "}
          <Link href="/register" className="font-medium transition-colors" style={{ color: "var(--accent)" }}>
            Зарегистрироваться
          </Link>
        </p>
      </motion.div>
    </div>
  );
}
