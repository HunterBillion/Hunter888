"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import AuthLayout from "@/components/layout/AuthLayout";
import type { TrainingStats } from "@/types";

export default function ProfilePage() {
  const { user, loading: authLoading } = useAuth();
  const [stats, setStats] = useState<TrainingStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(true);

  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [passwordSuccess, setPasswordSuccess] = useState("");
  const [passwordLoading, setPasswordLoading] = useState(false);

  useEffect(() => {
    if (!user) return;
    api
      .get(`/users/${user.id}/stats`)
      .then(setStats)
      .catch(() => setStats(null))
      .finally(() => setStatsLoading(false));
  }, [user]);

  const handlePasswordChange = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordError("");
    setPasswordSuccess("");

    if (newPassword !== confirmPassword) {
      setPasswordError("Пароли не совпадают");
      return;
    }

    if (newPassword.length < 8) {
      setPasswordError("Пароль должен быть не менее 8 символов");
      return;
    }

    setPasswordLoading(true);
    try {
      await api.put("/users/me/password", {
        old_password: oldPassword,
        new_password: newPassword,
      });
      setPasswordSuccess("Пароль успешно изменен");
      setOldPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Не удалось изменить пароль";
      setPasswordError(message);
    } finally {
      setPasswordLoading(false);
    }
  };

  if (authLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-gray-500 animate-pulse">Загрузка...</div>
      </div>
    );
  }

  const roleLabels: Record<string, string> = {
    manager: "Менеджер",
    rop: "Руководитель отдела продаж",
    methodologist: "Методолог",
    admin: "Администратор",
  };

  return (
    <AuthLayout>
      <div className="mx-auto max-w-3xl px-4 py-8">
        <h1 className="text-2xl font-display font-bold text-vh-purple tracking-wider">
          ПРОФИЛЬ
        </h1>

        {/* User info */}
        <div className="mt-6 glass-panel p-6">
          <h2 className="text-lg font-display font-semibold text-gray-200">
            Личные данные
          </h2>
          <dl className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <dt className="text-sm font-medium text-gray-500">Имя</dt>
              <dd className="mt-1 text-sm text-gray-200">{user?.full_name || "—"}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-gray-500">Email</dt>
              <dd className="mt-1 text-sm text-gray-200">{user?.email || "—"}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-gray-500">Роль</dt>
              <dd className="mt-1 text-sm text-gray-200">
                {user?.role ? roleLabels[user.role] || user.role : "—"}
              </dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-gray-500">Команда</dt>
              <dd className="mt-1 text-sm text-gray-200">{user?.team || "Не указана"}</dd>
            </div>
          </dl>
        </div>

        {/* Training statistics */}
        <div className="mt-6 glass-panel p-6">
          <h2 className="text-lg font-display font-semibold text-gray-200">
            Статистика обучения
          </h2>
          {statsLoading ? (
            <div className="mt-4 text-sm text-gray-500 animate-pulse">Загрузка...</div>
          ) : stats ? (
            <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
              <div className="rounded-lg bg-white/5 border border-white/10 p-4 text-center">
                <div className="text-2xl font-bold text-gray-100">{stats.total_sessions}</div>
                <div className="mt-1 text-xs text-gray-500">Всего сессий</div>
              </div>
              <div className="rounded-lg bg-white/5 border border-white/10 p-4 text-center">
                <div className="text-2xl font-bold text-vh-green">{stats.completed_sessions}</div>
                <div className="mt-1 text-xs text-gray-500">Завершено</div>
              </div>
              <div className="rounded-lg bg-white/5 border border-white/10 p-4 text-center">
                <div className="text-2xl font-bold text-vh-purple">
                  {stats.average_score != null ? Math.round(stats.average_score) : "—"}
                </div>
                <div className="mt-1 text-xs text-gray-500">Средний балл</div>
              </div>
              <div className="rounded-lg bg-white/5 border border-white/10 p-4 text-center">
                <div className="text-2xl font-bold text-vh-magenta">
                  {stats.best_score != null ? Math.round(stats.best_score) : "—"}
                </div>
                <div className="mt-1 text-xs text-gray-500">Лучший балл</div>
              </div>
            </div>
          ) : (
            <div className="mt-4 text-sm text-gray-500">
              Статистика пока недоступна. Пройдите хотя бы одну тренировку.
            </div>
          )}
        </div>

        {/* Password change */}
        <div className="mt-6 glass-panel p-6">
          <h2 className="text-lg font-display font-semibold text-gray-200">
            Изменить пароль
          </h2>
          <form onSubmit={handlePasswordChange} className="mt-4 space-y-4">
            {passwordError && (
              <div className="rounded-md bg-vh-red/10 border border-vh-red/30 p-3 text-sm text-vh-red">
                {passwordError}
              </div>
            )}
            {passwordSuccess && (
              <div className="rounded-md bg-vh-green/10 border border-vh-green/30 p-3 text-sm text-vh-green">
                {passwordSuccess}
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
              />
            </div>

            <div>
              <label htmlFor="confirmPassword" className="vh-label">
                Подтвердите пароль
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
              disabled={passwordLoading}
              className="vh-btn-primary"
            >
              {passwordLoading ? "Сохранение..." : "Изменить пароль"}
            </button>
          </form>
        </div>
      </div>
    </AuthLayout>
  );
}
