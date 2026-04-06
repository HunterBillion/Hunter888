"use client";

import { Suspense, useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { KeyRound, ArrowRight, AlertCircle, CheckCircle2 } from "lucide-react";
import { api } from "@/lib/api";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { PasswordInput } from "@/components/ui/PasswordInput";
import { PasswordChecklist, isPasswordValid } from "@/components/ui/PasswordChecklist";

/* ─────────────── inner component (needs useSearchParams) ─────────────── */
function ResetPasswordForm() {
  const router = useRouter();
  const params = useSearchParams();
  const token = params.get("token") ?? "";

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  // Redirect if no token
  useEffect(() => {
    if (!token) router.replace("/");
  }, [token, router]);

  const passwordsMatch = confirmPassword.length === 0 || password === confirmPassword;
  const canSubmit = isPasswordValid(password) && password === confirmPassword && !loading;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (!isPasswordValid(password)) {
      setError("Пароль не соответствует требованиям");
      return;
    }
    if (password !== confirmPassword) {
      setError("Пароли не совпадают");
      return;
    }

    setLoading(true);
    try {
      await api.post("/auth/reset-password", {
        token,
        new_password: password,
      });
      setDone(true);
      setTimeout(() => router.push("/"), 3000);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Ошибка сброса пароля";
      // Token expired or invalid
      if (msg.includes("invalid") || msg.includes("expired") || msg.includes("не найден")) {
        setError("Ссылка устарела или уже использована. Запросите новую.");
      } else {
        setError(msg);
      }
    } finally {
      setLoading(false);
    }
  };

  if (!token) return null;

  return (
    <div
      className="flex min-h-screen items-center justify-center px-4"
      style={{ background: "var(--bg-primary)" }}
    >
      {/* Ambient glow */}
      <div
        className="fixed inset-0 z-0 pointer-events-none"
        style={{
          background:
            "radial-gradient(ellipse at 50% 55%, rgba(99,102,241,0.18) 0%, transparent 60%)",
        }}
      />

      <div className="absolute right-4 top-4 z-10">
        <ThemeToggle />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 20, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.45 }}
        className="glass-panel w-full max-w-md p-8 relative z-10"
      >
        {/* Top accent line */}
        <div
          className="absolute top-0 left-6 right-6 h-[2px] rounded-full"
          style={{
            background: "linear-gradient(90deg, transparent, var(--accent), transparent)",
          }}
        />

        <AnimatePresence mode="wait">
          {done ? (
            /* ── Success state ── */
            <motion.div
              key="done"
              initial={{ opacity: 0, scale: 0.92 }}
              animate={{ opacity: 1, scale: 1 }}
              className="text-center py-6"
            >
              <motion.div
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ type: "spring", stiffness: 280, delay: 0.1 }}
                className="w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-5"
                style={{
                  background: "rgba(0,255,148,0.1)",
                  border: "1px solid rgba(0,255,148,0.25)",
                }}
              >
                <CheckCircle2 size={28} style={{ color: "var(--neon-green)" }} />
              </motion.div>
              <h2
                className="font-display font-bold text-xl mb-2"
                style={{ color: "var(--text-primary)" }}
              >
                Пароль изменён!
              </h2>
              <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                Перенаправляем на главную страницу…
              </p>
            </motion.div>
          ) : (
            /* ── Form state ── */
            <motion.div key="form" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
              {/* Icon + title */}
              <div className="mb-8 text-center">
                <motion.div
                  initial={{ scale: 0.8 }}
                  animate={{ scale: 1 }}
                  transition={{ type: "spring", stiffness: 300, delay: 0.1 }}
                  className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl"
                  style={{ background: "var(--accent-muted)" }}
                >
                  <KeyRound size={22} style={{ color: "var(--accent)" }} />
                </motion.div>
                <h1
                  className="font-display text-2xl font-bold tracking-wider"
                  style={{ color: "var(--text-primary)" }}
                >
                  НОВЫЙ ПАРОЛЬ
                </h1>
                <p className="mt-1 text-sm" style={{ color: "var(--text-muted)" }}>
                  Придумайте надёжный пароль для вашего аккаунта
                </p>
              </div>

              <form onSubmit={handleSubmit} className="space-y-5">
                {/* Error */}
                <AnimatePresence>
                  {error && (
                    <motion.div
                      key="err"
                      initial={{ opacity: 0, y: -8 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0 }}
                      className="flex items-start gap-2 rounded-xl p-3 text-sm"
                      style={{
                        background: "rgba(239, 68, 68, 0.08)",
                        border: "1px solid rgba(239, 68, 68, 0.2)",
                        color: "var(--danger)",
                      }}
                    >
                      <AlertCircle size={16} className="flex-shrink-0 mt-0.5" />
                      {error}
                    </motion.div>
                  )}
                </AnimatePresence>

                {/* New password */}
                <div>
                  <label htmlFor="newPassword" className="vh-label">
                    Новый пароль
                  </label>
                  <PasswordInput
                    id="newPassword"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Введите новый пароль"
                    autoComplete="new-password"
                    ariaLabel="Новый пароль"
                  />
                  <PasswordChecklist value={password} />
                </div>

                {/* Confirm password */}
                <div>
                  <label htmlFor="confirmPassword" className="vh-label">
                    Подтвердите пароль
                  </label>
                  <PasswordInput
                    id="confirmPassword"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="Повторите пароль"
                    autoComplete="new-password"
                    ariaLabel="Подтвердите пароль"
                  />
                  {!passwordsMatch && confirmPassword.length > 0 && (
                    <p className="mt-1.5 text-xs" style={{ color: "var(--neon-red)" }}>
                      Пароли не совпадают
                    </p>
                  )}
                </div>

                <motion.button
                  type="submit"
                  disabled={!canSubmit}
                  className="btn-neon flex w-full items-center justify-center gap-2"
                  whileHover={{ scale: canSubmit ? 1.01 : 1 }}
                  whileTap={{ scale: canSubmit ? 0.99 : 1 }}
                >
                  {loading ? (
                    <div className="h-5 w-5 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                  ) : (
                    <>
                      Сохранить пароль
                      <ArrowRight size={16} />
                    </>
                  )}
                </motion.button>
              </form>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </div>
  );
}

/* ─────────────── page (wrapped in Suspense for useSearchParams) ─────── */
export default function ResetPasswordPage() {
  return (
    <Suspense
      fallback={
        <div
          className="flex min-h-screen items-center justify-center"
          style={{ background: "var(--bg-primary)" }}
        >
          <div className="w-2 h-2 rounded-full animate-ping" style={{ background: "var(--accent)" }} />
        </div>
      }
    >
      <ResetPasswordForm />
    </Suspense>
  );
}
