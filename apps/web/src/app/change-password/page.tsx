"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { KeyRound, ArrowRight, AlertCircle } from "lucide-react";
import { api } from "@/lib/api";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { PasswordInput } from "@/components/ui/PasswordInput";
import { PasswordChecklist, isPasswordValid } from "@/components/ui/PasswordChecklist";

export default function ChangePasswordPage() {
  const router = useRouter();
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (!isPasswordValid(newPassword)) {
      setError("Пароль не соответствует требованиям безопасности");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("Пароли не совпадают");
      return;
    }

    setLoading(true);
    try {
      await api.put("/users/me/password", {
        old_password: oldPassword,
        new_password: newPassword,
      });
      router.push("/home");
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Ошибка смены пароля";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="flex min-h-screen items-center justify-center px-4"
      style={{ background: "var(--bg-primary)" }}
    >
      <div className="absolute right-4 top-4">
        <ThemeToggle />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 20, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.4 }}
        className="glass-panel w-full max-w-md p-8"
      >
        <div className="mb-8 text-center">
          <motion.div
            initial={{ scale: 0.8 }}
            animate={{ scale: 1 }}
            transition={{ type: "spring", stiffness: 300, delay: 0.1 }}
            className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl"
            style={{ background: "var(--accent-muted)" }}
          >
            <KeyRound size={24} style={{ color: "var(--accent)" }} />
          </motion.div>
          <h1
            className="font-display text-2xl font-bold tracking-wider"
            style={{ color: "var(--text-primary)" }}
          >
            СМЕНА ПАРОЛЯ
          </h1>
          <p className="mt-1 text-sm" style={{ color: "var(--text-muted)" }}>
            Для продолжения работы необходимо сменить пароль
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          {error && (
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex items-center gap-2 rounded-xl p-3 text-sm"
              style={{
                background: "rgba(239, 68, 68, 0.08)",
                border: "1px solid rgba(239, 68, 68, 0.2)",
                color: "var(--danger)",
              }}
            >
              <AlertCircle size={16} />
              {error}
            </motion.div>
          )}

          <div>
            <label htmlFor="oldPassword" className="vh-label">
              Текущий пароль
            </label>
            <PasswordInput
              id="oldPassword"
              value={oldPassword}
              onChange={(e) => setOldPassword(e.target.value)}
              autoComplete="current-password"
              ariaLabel="Текущий пароль"
            />
          </div>

          <div>
            <label htmlFor="newPassword" className="vh-label">
              Новый пароль
            </label>
            <PasswordInput
              id="newPassword"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder="Минимум 8 символов"
              autoComplete="new-password"
              ariaLabel="Новый пароль"
            />
            <PasswordChecklist value={newPassword} />
          </div>

          <div>
            <label htmlFor="confirmPassword" className="vh-label">
              Подтвердите новый пароль
            </label>
            <PasswordInput
              id="confirmPassword"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              minLength={8}
              autoComplete="new-password"
              ariaLabel="Подтвердите новый пароль"
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
                Сменить пароль
                <ArrowRight size={16} />
              </>
            )}
          </motion.button>
        </form>
      </motion.div>
    </div>
  );
}
