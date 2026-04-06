"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { motion } from "framer-motion";
import { Mail, ArrowRight, AlertCircle, KeyRound } from "lucide-react";
import { api } from "@/lib/api";
import { EASE_SNAP } from "@/lib/constants";
import { setTokens } from "@/lib/auth";
import { getApiBaseUrl } from "@/lib/public-origin";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { LogoSeparator } from "@/components/ui/LogoSeparator";
import { PasswordInput } from "@/components/ui/PasswordInput";
import dynamic from "next/dynamic";
const WaveScene = dynamic(
  () => import("@/components/landing/WaveScene").then((m) => m.WaveScene),
  {
    ssr: false,
    loading: () => <div className="fixed inset-0 -z-10" style={{ background: "var(--bg-primary)" }} />,
  },
);
import { FishermanError } from "@/components/errors/FishermanError";

type ForgotMode = "idle" | "form" | "sent";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [networkError, setNetworkError] = useState(false);
  const [forgotMode, setForgotMode] = useState<ForgotMode>("idle");
  const [forgotEmail, setForgotEmail] = useState("");
  const [forgotLoading, setForgotLoading] = useState(false);

  const handleForgot = async () => {
    if (!forgotEmail.trim()) return;
    setForgotLoading(true);
    try {
      await fetch(`${getApiBaseUrl()}/api/auth/forgot-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: forgotEmail.trim() }),
      });
    } catch { /* silent — always show success for security */ }
    setForgotLoading(false);
    setForgotMode("sent");
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    // Client-side validation (#13) — avoid unnecessary API calls
    const trimmedEmail = email.trim();
    if (!trimmedEmail || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmedEmail)) {
      setError("Введите корректный email");
      return;
    }
    if (!password || password.length < 4) {
      setError("Пароль должен содержать минимум 4 символа");
      return;
    }

    setLoading(true);

    try {
      const data = await api.post("/auth/login", { email: trimmedEmail, password });
      setTokens(data.access_token, data.refresh_token);
      // router.push keeps tokens in memory (no page reload), middleware sees
      // vh_authenticated cookie set by setTokens above.
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

  // Forgot-password screen
  if (forgotMode !== "idle") {
    return (
      <div
        className="flex min-h-screen items-center justify-center px-4"
        style={{ background: "var(--bg-primary)" }}
      >
        <div className="absolute right-4 top-4 z-10"><ThemeToggle /></div>
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass-panel w-full max-w-md p-8 relative z-10"
        >
          <div className="absolute top-0 left-6 right-6 h-[2px] rounded-full" style={{ background: "linear-gradient(90deg, transparent, var(--accent), transparent)" }} />

          {forgotMode === "sent" ? (
            <div className="text-center py-6">
              <motion.div initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: "spring", stiffness: 280 }}
                className="w-14 h-14 rounded-full flex items-center justify-center mx-auto mb-5"
                style={{ background: "rgba(0,255,148,0.1)", border: "1px solid rgba(0,255,148,0.25)" }}
              >
                <Mail size={24} style={{ color: "var(--neon-green)" }} />
              </motion.div>
              <h2 className="font-display font-bold text-xl mb-2" style={{ color: "var(--text-primary)" }}>Письмо отправлено</h2>
              <p className="text-sm mb-6" style={{ color: "var(--text-muted)" }}>
                Проверьте <strong style={{ color: "var(--text-secondary)" }}>{forgotEmail}</strong><br />и следуйте инструкциям в письме.
              </p>
              <button onClick={() => { setForgotMode("idle"); setForgotEmail(""); }} className="text-sm font-medium" style={{ color: "var(--accent)" }}>
                ← Вернуться ко входу
              </button>
            </div>
          ) : (
            <div>
              <button onClick={() => setForgotMode("idle")} className="flex items-center gap-1.5 text-xs mb-6" style={{ color: "var(--text-muted)" }}>
                ← Назад
              </button>
              <div className="mb-6 flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0" style={{ background: "var(--accent-muted)" }}>
                  <KeyRound size={18} style={{ color: "var(--accent)" }} />
                </div>
                <div>
                  <h2 className="font-display font-bold text-lg" style={{ color: "var(--text-primary)" }}>Забыли пароль?</h2>
                  <p className="text-xs" style={{ color: "var(--text-muted)" }}>Пришлём ссылку для сброса</p>
                </div>
              </div>
              <label className="vh-label">Email</label>
              <div className="relative mb-4">
                <Mail size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2" style={{ color: "var(--text-muted)" }} />
                <input
                  type="email" value={forgotEmail} onChange={(e) => setForgotEmail(e.target.value)}
                  className="vh-input pl-10 w-full" placeholder="you@example.com" autoComplete="email"
                  onKeyDown={(e) => e.key === "Enter" && handleForgot()}
                />
              </div>
              <motion.button
                onClick={handleForgot} disabled={forgotLoading || !forgotEmail.trim()}
                className="btn-neon flex w-full items-center justify-center gap-2"
                whileHover={{ scale: 1.01 }} whileTap={{ scale: 0.99 }}
              >
                {forgotLoading
                  ? <div className="h-5 w-5 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                  : <><Mail size={15} />Отправить ссылку</>}
              </motion.button>
            </div>
          )}
        </motion.div>
      </div>
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
          {/* Animated logo icon — neural pulse */}
          <motion.div
            initial={{ scale: 0.5, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ type: "spring", stiffness: 200, delay: 0.1 }}
            className="relative mx-auto mb-5 h-20 w-20 flex items-center justify-center"
          >
            {/* Outer breathing ring */}
            <motion.div
              className="absolute inset-0 rounded-2xl"
              style={{
                border: "1.5px solid var(--accent)",
                opacity: 0.3,
              }}
              animate={{
                rotate: [0, 90],
                borderRadius: ["28%", "50%", "28%"],
                scale: [1, 1.06, 1],
              }}
              transition={{ duration: 6, repeat: Infinity, ease: "easeInOut" }}
            />
            {/* Inner morphing shape */}
            <motion.div
              className="absolute rounded-2xl"
              style={{
                inset: 8,
                border: "1px solid var(--accent)",
                opacity: 0.2,
              }}
              animate={{
                rotate: [0, -90],
                borderRadius: ["50%", "28%", "50%"],
              }}
              transition={{ duration: 6, repeat: Infinity, ease: "easeInOut" }}
            />
            {/* Core — stylized "X" */}
            <motion.svg
              width="28"
              height="28"
              viewBox="0 0 28 28"
              fill="none"
              className="relative z-10"
              animate={{
                filter: [
                  "drop-shadow(0 0 8px var(--accent-glow))",
                  "drop-shadow(0 0 20px var(--accent-glow))",
                  "drop-shadow(0 0 8px var(--accent-glow))",
                ],
              }}
              transition={{ duration: 2.5, repeat: Infinity, ease: "easeInOut" }}
            >
              <motion.path
                d="M6 6L22 22M22 6L6 22"
                stroke="var(--accent)"
                strokeWidth="2.5"
                strokeLinecap="round"
                initial={{ pathLength: 0 }}
                animate={{ pathLength: 1 }}
                transition={{ duration: 1.2, delay: 0.3, ease: EASE_SNAP }}
              />
            </motion.svg>
            {/* Ambient glow behind */}
            <motion.div
              className="absolute rounded-full"
              style={{
                inset: -4,
                background: "radial-gradient(circle, var(--accent-glow) 0%, transparent 70%)",
              }}
              animate={{ opacity: [0.3, 0.6, 0.3] }}
              transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
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
            className="mt-2 font-display text-base font-bold tracking-[0.12em] italic"
            style={{ color: "var(--accent)", textShadow: "0 0 20px rgba(99,102,241,0.4)" }}
          >
            Выбор игры, важнее самой игры
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
            <div className="flex items-center justify-between mb-1">
              <label htmlFor="password" className="vh-label mb-0">Пароль</label>
              <button
                type="button"
                onClick={() => { setForgotMode("form"); setForgotEmail(email.trim()); }}
                className="text-xs transition-colors"
                style={{ color: "var(--text-muted)" }}
                onMouseEnter={(e) => (e.currentTarget.style.color = "var(--accent)")}
                onMouseLeave={(e) => (e.currentTarget.style.color = "var(--text-muted)")}
              >
                Забыли пароль?
              </button>
            </div>
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
            className="btn-neon flex w-full items-center justify-center gap-2"
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
              <span className="font-mono text-xs tracking-wider" style={{ color: "var(--text-muted)" }}>ИЛИ</span>
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
                    setError(""); // Clear stale error before redirect (#18)
                    const data = await api.get("/auth/google/login");
                    if (data?.url) {
                      const { validateOAuthUrl } = await import("@/lib/sanitize");
                      const safeUrl = validateOAuthUrl(data.url);
                      if (safeUrl) window.location.href = safeUrl;
                      else setError("Недоверенный OAuth URL");
                    }
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
                    setError(""); // Clear stale error before redirect (#18)
                    const data = await api.get("/auth/yandex/login");
                    if (data?.url) {
                      const { validateOAuthUrl } = await import("@/lib/sanitize");
                      const safeUrl = validateOAuthUrl(data.url);
                      if (safeUrl) window.location.href = safeUrl;
                      else setError("Недоверенный OAuth URL");
                    }
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
