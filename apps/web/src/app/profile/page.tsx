"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  User,
  Mail,
  Shield,
  Users,
  Trophy,
  CheckCircle2,
  TrendingUp,
  Star,
  Lock,
  ArrowRight,
  AlertCircle,
  CheckCircle,
  Loader2,
  Flame,
  Zap,
  Award,
} from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import AuthLayout from "@/components/layout/AuthLayout";
import { UserAvatar } from "@/components/ui/UserAvatar";
import type { TrainingStats, GamificationProgress } from "@/types";

const roleLabels: Record<string, string> = {
  manager: "Менеджер",
  rop: "Руководитель отдела продаж",
  methodologist: "Методолог",
  admin: "Администратор",
};

export default function ProfilePage() {
  const { user, loading: authLoading } = useAuth();
  const [stats, setStats] = useState<TrainingStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(true);
  const [progress, setProgress] = useState<GamificationProgress | null>(null);

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
    api
      .get("/gamification/me/progress")
      .then(setProgress)
      .catch(() => setProgress(null));
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
      setPasswordSuccess("Пароль успешно изменён");
      setTimeout(() => setPasswordSuccess(""), 4000);
      setOldPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err: unknown) {
      setPasswordError(err instanceof Error ? err.message : "Ошибка");
    } finally {
      setPasswordLoading(false);
    }
  };

  if (authLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center" style={{ background: "var(--bg-primary)" }}>
        <Loader2 size={20} className="animate-spin" style={{ color: "var(--accent)" }} />
      </div>
    );
  }

  const statCards = stats
    ? [
        { label: "Всего сессий", value: stats.total_sessions, icon: Trophy, color: "var(--text-primary)" },
        { label: "Завершено", value: stats.completed_sessions, icon: CheckCircle2, color: "var(--success)" },
        { label: "Средний балл", value: stats.average_score != null ? Math.round(stats.average_score) : "—", icon: TrendingUp, color: "var(--accent)" },
        { label: "Лучший балл", value: stats.best_score != null ? Math.round(stats.best_score) : "—", icon: Star, color: "var(--warning)" },
      ]
    : [];

  return (
    <AuthLayout>
      <div className="panel-grid-bg min-h-screen">
        <div className="mx-auto max-w-3xl px-4 py-8">
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
          <div className="flex items-center gap-2">
            <User size={20} style={{ color: "var(--accent)" }} />
            <h1 className="font-display text-2xl font-bold tracking-wider" style={{ color: "var(--text-primary)" }}>
              ПРОФИЛЬ
            </h1>
          </div>
        </motion.div>

        {/* User info */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="glass-panel mt-6 p-6"
        >
          <div className="flex items-center gap-4 mb-4">
            <UserAvatar avatarUrl={user?.avatar_url} fullName={user?.full_name || ""} size={64} />
            <div>
              <h2 className="font-display text-lg font-semibold" style={{ color: "var(--text-primary)" }}>
                {user?.full_name}
              </h2>
              <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                {user?.role ? roleLabels[user.role] || user.role : ""}
              </span>
            </div>
          </div>
          <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {[
              { icon: User, label: "Имя", value: user?.full_name || "—" },
              { icon: Mail, label: "Email", value: user?.email || "—" },
              { icon: Shield, label: "Роль", value: user?.role ? roleLabels[user.role] || user.role : "—" },
              { icon: Users, label: "Команда", value: user?.team || "Не указана" },
            ].map((item) => {
              const Icon = item.icon;
              return (
                <div key={item.label} className="flex items-start gap-3">
                  <div
                    className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg"
                    style={{ background: "var(--accent-muted)" }}
                  >
                    <Icon size={14} style={{ color: "var(--accent)" }} />
                  </div>
                  <div>
                    <dt className="text-xs font-medium" style={{ color: "var(--text-muted)" }}>
                      {item.label}
                    </dt>
                    <dd className="mt-0.5 text-sm" style={{ color: "var(--text-primary)" }}>
                      {item.value}
                    </dd>
                  </div>
                </div>
              );
            })}
          </dl>
        </motion.div>

        {/* Stats */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="glass-panel mt-6 p-6"
        >
          <h2 className="font-display text-lg font-semibold" style={{ color: "var(--text-primary)" }}>
            Статистика обучения
          </h2>
          {statsLoading ? (
            <div className="mt-4 flex items-center gap-2">
              <Loader2 size={14} className="animate-spin" style={{ color: "var(--accent)" }} />
              <span className="text-sm" style={{ color: "var(--text-muted)" }}>Загрузка...</span>
            </div>
          ) : stats ? (
            <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
              {statCards.map((card, i) => {
                const Icon = card.icon;
                return (
                  <motion.div
                    key={card.label}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.3 + i * 0.08 }}
                    className="rounded-xl p-4 text-center"
                    style={{
                      background: "var(--input-bg)",
                      border: "1px solid var(--border-color)",
                    }}
                  >
                    <Icon size={16} className="mx-auto mb-1" style={{ color: card.color }} />
                    <div className="text-xl font-bold" style={{ color: card.color }}>
                      {card.value}
                    </div>
                    <div className="mt-0.5 text-[10px]" style={{ color: "var(--text-muted)" }}>
                      {card.label}
                    </div>
                  </motion.div>
                );
              })}
            </div>
          ) : (
            <p className="mt-4 text-sm" style={{ color: "var(--text-muted)" }}>
              Статистика пока недоступна. Пройдите хотя бы одну тренировку.
            </p>
          )}
        </motion.div>

        {/* XP & Achievements */}
        {progress && (
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.25 }}
            className="glass-panel mt-6 p-6"
          >
            <h2 className="font-display text-lg font-semibold" style={{ color: "var(--text-primary)" }}>
              Прогресс
            </h2>
            <div className="mt-4 grid grid-cols-3 gap-3">
              <div className="rounded-xl p-4 text-center" style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)" }}>
                <Zap size={16} className="mx-auto mb-1" style={{ color: "var(--accent)" }} />
                <div className="text-xl font-bold" style={{ color: "var(--accent)" }}>
                  {progress.level}
                </div>
                <div className="mt-0.5 text-[10px]" style={{ color: "var(--text-muted)" }}>Уровень</div>
              </div>
              <div className="rounded-xl p-4 text-center" style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)" }}>
                <Star size={16} className="mx-auto mb-1" style={{ color: "var(--warning)" }} />
                <div className="text-xl font-bold" style={{ color: "var(--text-primary)" }}>
                  {progress.total_xp}
                </div>
                <div className="mt-0.5 text-[10px]" style={{ color: "var(--text-muted)" }}>Всего XP</div>
              </div>
              <div className="rounded-xl p-4 text-center" style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)" }}>
                <Flame size={16} className="mx-auto mb-1" style={{ color: "var(--neon-red, #FF3333)" }} />
                <div className="text-xl font-bold" style={{ color: "var(--text-primary)" }}>
                  {progress.streak_days}
                </div>
                <div className="mt-0.5 text-[10px]" style={{ color: "var(--text-muted)" }}>Streak дней</div>
              </div>
            </div>

            {/* XP bar */}
            <div className="mt-4">
              <div className="flex items-center justify-between mb-1">
                <span className="font-mono text-[10px] tracking-wider" style={{ color: "var(--text-muted)" }}>УРОВЕНЬ {progress.level}</span>
                <span className="font-mono text-[10px]" style={{ color: "var(--accent)" }}>{progress.xp_current_level}/{progress.xp_next_level} XP</span>
              </div>
              <div className="h-2 rounded-full overflow-hidden" style={{ background: "var(--input-bg)" }}>
                <motion.div
                  className="h-full rounded-full"
                  style={{ background: "var(--accent)" }}
                  initial={{ width: 0 }}
                  animate={{ width: `${progress.xp_next_level > 0 ? Math.round((progress.xp_current_level / progress.xp_next_level) * 100) : 0}%` }}
                  transition={{ duration: 1 }}
                />
              </div>
            </div>

            {/* Achievements */}
            {progress.achievements.length > 0 && (
              <div className="mt-4">
                <div className="flex items-center gap-2 mb-2">
                  <Award size={14} style={{ color: "var(--accent)" }} />
                  <span className="font-mono text-[10px] uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>Достижения</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {progress.achievements.map((a) => (
                    <div
                      key={a.slug}
                      className="flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs"
                      style={{ background: "var(--accent-muted)", border: "1px solid var(--glass-border)", color: "var(--text-primary)" }}
                    >
                      <span>{a.icon_url || "🏆"}</span>
                      <span>{a.title}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </motion.div>
        )}

        {/* Password change */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="glass-panel mt-6 p-6"
        >
          <h2 className="font-display text-lg font-semibold" style={{ color: "var(--text-primary)" }}>
            Изменить пароль
          </h2>
          <form onSubmit={handlePasswordChange} className="mt-4 space-y-4">
            {passwordError && (
              <motion.div
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex items-center gap-2 rounded-xl p-3 text-sm"
                style={{ background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.2)", color: "var(--danger)" }}
              >
                <AlertCircle size={14} />
                {passwordError}
              </motion.div>
            )}
            {passwordSuccess && (
              <motion.div
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex items-center gap-2 rounded-xl p-3 text-sm"
                style={{ background: "rgba(34,197,94,0.08)", border: "1px solid rgba(34,197,94,0.2)", color: "var(--success)" }}
              >
                <CheckCircle size={14} />
                {passwordSuccess}
              </motion.div>
            )}

            {[
              { id: "oldPwd", label: "Текущий пароль", value: oldPassword, setter: setOldPassword },
              { id: "newPwd", label: "Новый пароль", value: newPassword, setter: setNewPassword, placeholder: "Минимум 8 символов" },
              { id: "confPwd", label: "Подтвердите пароль", value: confirmPassword, setter: setConfirmPassword },
            ].map((f) => (
              <div key={f.id}>
                <label htmlFor={f.id} className="vh-label">{f.label}</label>
                <div className="relative">
                  <Lock
                    size={16}
                    className="absolute left-3.5 top-1/2 -translate-y-1/2"
                    style={{ color: "var(--text-muted)" }}
                  />
                  <input
                    id={f.id}
                    type="password"
                    value={f.value}
                    onChange={(e) => f.setter(e.target.value)}
                    required
                    minLength={f.id === "oldPwd" ? undefined : 8}
                    className="vh-input pl-10"
                    placeholder={f.placeholder}
                  />
                </div>
              </div>
            ))}

            <motion.button
              type="submit"
              disabled={passwordLoading}
              className="vh-btn-primary flex items-center gap-2"
              whileTap={{ scale: 0.98 }}
            >
              {passwordLoading ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <>
                  Изменить пароль
                  <ArrowRight size={16} />
                </>
              )}
            </motion.button>
          </form>
        </motion.div>
        </div>
      </div>
    </AuthLayout>
  );
}
