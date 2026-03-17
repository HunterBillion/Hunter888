"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

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

    if (newPassword.length < 8) {
      setError("Пароль должен быть не менее 8 символов");
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
      router.push("/");
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Ошибка смены пароля";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="glass-panel w-full max-w-md p-8 space-y-8">
        <div className="text-center">
          <h1 className="text-2xl font-display font-bold text-vh-purple">
            СМЕНА ПАРОЛЯ
          </h1>
          <p className="mt-2 text-gray-400 text-sm">
            Для продолжения работы необходимо сменить пароль
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          {error && (
            <div className="rounded-md bg-vh-red/10 border border-vh-red/30 p-3 text-sm text-vh-red">
              {error}
            </div>
          )}

          <div>
            <label htmlFor="oldPassword" className="vh-label">
              Текущий пароль
            </label>
            <input
              id="oldPassword"
              type="password"
              value={oldPassword}
              onChange={(e) => setOldPassword(e.target.value)}
              required
              className="vh-input"
            />
          </div>

          <div>
            <label htmlFor="newPassword" className="vh-label">
              Новый пароль
            </label>
            <input
              id="newPassword"
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
              minLength={8}
              className="vh-input"
              placeholder="Минимум 8 символов"
            />
          </div>

          <div>
            <label htmlFor="confirmPassword" className="vh-label">
              Подтвердите новый пароль
            </label>
            <input
              id="confirmPassword"
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              minLength={8}
              className="vh-input"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="vh-btn-primary w-full"
          >
            {loading ? "Сохранение..." : "Сменить пароль"}
          </button>
        </form>
      </div>
    </div>
  );
}
