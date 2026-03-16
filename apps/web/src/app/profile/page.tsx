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

  // Password change form
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
        <div className="text-gray-500">Загрузка...</div>
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
        <h1 className="text-2xl font-bold text-gray-900">Профиль</h1>

        {/* User info */}
        <div className="mt-6 rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-gray-900">
            Личные данные
          </h2>
          <dl className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <dt className="text-sm font-medium text-gray-500">Имя</dt>
              <dd className="mt-1 text-sm text-gray-900">
                {user?.full_name || "—"}
              </dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-gray-500">Email</dt>
              <dd className="mt-1 text-sm text-gray-900">
                {user?.email || "—"}
              </dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-gray-500">Роль</dt>
              <dd className="mt-1 text-sm text-gray-900">
                {user?.role ? roleLabels[user.role] || user.role : "—"}
              </dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-gray-500">Команда</dt>
              <dd className="mt-1 text-sm text-gray-900">
                {user?.team || "Не указана"}
              </dd>
            </div>
          </dl>
        </div>

        {/* Training statistics */}
        <div className="mt-6 rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-gray-900">
            Статистика обучения
          </h2>
          {statsLoading ? (
            <div className="mt-4 text-sm text-gray-500">Загрузка...</div>
          ) : stats ? (
            <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
              <div className="rounded-lg bg-gray-50 p-4 text-center">
                <div className="text-2xl font-bold text-gray-900">
                  {stats.total_sessions}
                </div>
                <div className="mt-1 text-xs text-gray-500">
                  Всего сессий
                </div>
              </div>
              <div className="rounded-lg bg-gray-50 p-4 text-center">
                <div className="text-2xl font-bold text-green-600">
                  {stats.completed_sessions}
                </div>
                <div className="mt-1 text-xs text-gray-500">
                  Завершено
                </div>
              </div>
              <div className="rounded-lg bg-gray-50 p-4 text-center">
                <div className="text-2xl font-bold text-blue-600">
                  {stats.average_score != null
                    ? Math.round(stats.average_score)
                    : "—"}
                </div>
                <div className="mt-1 text-xs text-gray-500">
                  Средний балл
                </div>
              </div>
              <div className="rounded-lg bg-gray-50 p-4 text-center">
                <div className="text-2xl font-bold text-purple-600">
                  {stats.best_score != null
                    ? Math.round(stats.best_score)
                    : "—"}
                </div>
                <div className="mt-1 text-xs text-gray-500">
                  Лучший балл
                </div>
              </div>
            </div>
          ) : (
            <div className="mt-4 text-sm text-gray-500">
              Статистика пока недоступна. Пройдите хотя бы одну тренировку.
            </div>
          )}
        </div>

        {/* Password change */}
        <div className="mt-6 rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-gray-900">
            Изменить пароль
          </h2>
          <form onSubmit={handlePasswordChange} className="mt-4 space-y-4">
            {passwordError && (
              <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">
                {passwordError}
              </div>
            )}
            {passwordSuccess && (
              <div className="rounded-md bg-green-50 p-3 text-sm text-green-700">
                {passwordSuccess}
              </div>
            )}

            <div>
              <label
                htmlFor="oldPassword"
                className="block text-sm font-medium text-gray-700"
              >
                Текущий пароль
              </label>
              <input
                id="oldPassword"
                type="password"
                value={oldPassword}
                onChange={(e) => setOldPassword(e.target.value)}
                required
                className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>

            <div>
              <label
                htmlFor="newPassword"
                className="block text-sm font-medium text-gray-700"
              >
                Новый пароль
              </label>
              <input
                id="newPassword"
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
                minLength={8}
                className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>

            <div>
              <label
                htmlFor="confirmPassword"
                className="block text-sm font-medium text-gray-700"
              >
                Подтвердите пароль
              </label>
              <input
                id="confirmPassword"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                minLength={8}
                className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>

            <button
              type="submit"
              disabled={passwordLoading}
              className="rounded-md bg-blue-600 px-6 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {passwordLoading ? "Сохранение..." : "Изменить пароль"}
            </button>
          </form>
        </div>
      </div>
    </AuthLayout>
  );
}
