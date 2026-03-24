"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { motion } from "framer-motion";
import { UserPlus, Mail, Lock, User, ArrowRight, AlertCircle } from "lucide-react";
import { api } from "@/lib/api";
import { setTokens } from "@/lib/auth";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import dynamic from "next/dynamic";
import { FishermanError } from "@/components/errors/FishermanError";
const WaveScene = dynamic(
  () => import("@/components/landing/WaveScene").then((m) => m.WaveScene),
  { ssr: false },
);

export default function RegisterPage() {
  const router = useRouter();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [networkError, setNetworkError] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setNetworkError(false);

    const normalizedEmail = email.trim().toLowerCase();
    const normalizedName = fullName.trim();

    if (!normalizedName) {
      setError("Укажите имя");
      return;
    }
    if (password !== confirmPassword) {
      setError("Пароли не совпадают");
      return;
    }
    if (password.length < 8) {
      setError("Пароль должен быть не короче 8 символов");
      return;
    }
    if (!/[A-Z]/.test(password)) {
      setError("Пароль должен содержать хотя бы одну заглавную букву");
      return;
    }
    if (!/[a-z]/.test(password)) {
      setError("Пароль должен содержать хотя бы одну строчную букву");
      return;
    }
    if (!/[0-9]/.test(password)) {
      setError("Пароль должен содержать хотя бы одну цифру");
      return;
    }

    setLoading(true);

    try {
      const data = await api.post("/auth/register", {
        email: normalizedEmail,
        password,
        full_name: normalizedName,
      });
      setTokens(data.access_token, data.refresh_token);
      router.push("/onboarding");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Ошибка регистрации";
      if (msg.includes("недоступен") || msg.includes("fetch")) {
        setNetworkError(true);
      } else {
        setError(msg);
      }
    } finally {
      setLoading(false);
    }
  };

  const passwordStrength = password.length >= 12 ? "strong" : password.length >= 8 ? "medium" : "weak";
  const passwordsMatch = confirmPassword.length === 0 || password === confirmPassword;

  if (networkError) {
    return <FishermanError onRetry={() => { setNetworkError(false); setError(""); }} message="Похоже, рыба сегодня не клюёт..." />;
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center px-4 py-8 overflow-hidden" style={{ background: "var(--bg-primary)" }}>
      {/* Ambient glow */}
      <div className="fixed inset-0 z-0 pointer-events-none" style={{ background: "radial-gradient(ellipse at 50% 70%, rgba(138,43,226,0.15) 0%, transparent 60%)" }} />

      {/* 3D Wave Background */}
      <div className="fixed inset-0 z-[1]">
        <WaveScene />
      </div>

      <div className="absolute right-4 top-4 z-10">
        <ThemeToggle />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 20, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.5 }}
        className="glass-panel w-full max-w-md p-8 relative z-10"
      >
        <div className="absolute top-0 left-6 right-6 h-[2px] rounded-full" style={{ background: "linear-gradient(90deg, transparent, var(--magenta), transparent)" }} />

        <div className="mb-8 text-center">
          <motion.div
            initial={{ scale: 0.8 }}
            animate={{ scale: 1 }}
            transition={{ type: "spring", stiffness: 300, delay: 0.1 }}
            className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl"
            style={{ background: "var(--accent)", boxShadow: "0 0 30px rgba(139,92,246,0.3)" }}
          >
            <UserPlus size={26} className="text-white" />
          </motion.div>
          <h1 className="font-display text-2xl font-bold tracking-[0.15em]" style={{ color: "var(--text-primary)" }}>
            РЕГИСТРАЦИЯ
          </h1>
          <p className="mt-1 font-mono text-xs tracking-wider" style={{ color: "var(--text-muted)" }}>
            СОЗДАЙТЕ АККАУНТ ДЛЯ ОБУЧЕНИЯ
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          {error && (
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex items-center gap-2 rounded-xl p-3 text-sm"
              style={{ background: "rgba(255, 51, 51, 0.08)", border: "1px solid rgba(255, 51, 51, 0.2)", color: "var(--neon-red)" }}
            >
              <AlertCircle size={16} />
              {error}
            </motion.div>
          )}

          <div>
            <label htmlFor="fullName" className="vh-label">Полное имя</label>
            <div className="relative">
              <User size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2" style={{ color: "var(--text-muted)" }} />
              <input id="fullName" type="text" value={fullName} onChange={(e) => setFullName(e.target.value)} required className="vh-input pl-10" placeholder="Иван Петров" autoComplete="name" aria-label="Полное имя" />
            </div>
          </div>

          <div>
            <label htmlFor="email" className="vh-label">Email</label>
            <div className="relative">
              <Mail size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2" style={{ color: "var(--text-muted)" }} />
              <input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required className="vh-input pl-10" placeholder="you@example.com" autoComplete="email" aria-label="Email" />
            </div>
          </div>

          <div>
            <label htmlFor="password" className="vh-label">Пароль</label>
            <div className="relative">
              <Lock size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2" style={{ color: "var(--text-muted)" }} />
              <input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} className="vh-input pl-10" placeholder="Минимум 8 символов" autoComplete="new-password" aria-label="Пароль" aria-describedby="password-requirements" />
            </div>
            {password.length > 0 && (
              <div className="mt-2 flex items-center gap-2">
                <div className="flex flex-1 gap-1">
                  {[1, 2, 3].map((i) => (
                    <motion.div
                      key={i}
                      className="h-1.5 flex-1 rounded-full"
                      initial={{ scaleX: 0 }}
                      animate={{ scaleX: 1 }}
                      style={{
                        background:
                          i <= (passwordStrength === "strong" ? 3 : passwordStrength === "medium" ? 2 : 1)
                            ? passwordStrength === "strong" ? "var(--neon-green)" : passwordStrength === "medium" ? "var(--warning)" : "var(--neon-red)"
                            : "var(--border-color)",
                        boxShadow: i <= (passwordStrength === "strong" ? 3 : passwordStrength === "medium" ? 2 : 1)
                          ? passwordStrength === "strong" ? "0 0 8px rgba(0,255,102,0.3)" : "none"
                          : "none",
                      }}
                    />
                  ))}
                </div>
                <span className="text-[10px] font-mono" style={{ color: "var(--text-muted)" }}>
                  {passwordStrength === "strong" ? "НАДЁЖНЫЙ" : passwordStrength === "medium" ? "СРЕДНИЙ" : "СЛАБЫЙ"}
                </span>
              </div>
            )}
            <div id="password-requirements" className="mt-2 text-[11px]" style={{ color: "var(--text-muted)" }}>
              Требования: 8+ символов, заглавная, строчная буква и цифра.
            </div>
          </div>

          <div>
            <label htmlFor="confirmPassword" className="vh-label">Повторите пароль</label>
            <div className="relative">
              <Lock size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2" style={{ color: "var(--text-muted)" }} />
              <input
                id="confirmPassword"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                className="vh-input pl-10"
                placeholder="Повторите пароль"
                autoComplete="new-password"
                aria-label="Повторите пароль"
              />
            </div>
            {!passwordsMatch && (
              <div className="mt-2 text-[11px]" style={{ color: "var(--neon-red)" }}>
                Пароли не совпадают.
              </div>
            )}
          </div>

          <motion.button
            type="submit"
            disabled={loading || !passwordsMatch}
            className="vh-btn-primary flex w-full items-center justify-center gap-2"
            whileHover={{ scale: 1.01 }}
            whileTap={{ scale: 0.99 }}
          >
            {loading ? (
              <div className="h-5 w-5 animate-spin rounded-full border-2 border-white/30 border-t-white" />
            ) : (
              <>
                Зарегистрироваться
                <ArrowRight size={16} />
              </>
            )}
          </motion.button>
        </form>

        <p className="mt-6 text-center text-sm" style={{ color: "var(--text-muted)" }}>
          Уже есть аккаунт?{" "}
          <Link href="/login" className="font-medium transition-colors" style={{ color: "var(--accent)" }}>
            Войти
          </Link>
        </p>
      </motion.div>
    </div>
  );
}
