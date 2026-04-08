"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  User,
  Lock,
  ArrowRight,
  AlertCircle,
  CheckCircle,
  Loader2,
} from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import AuthLayout from "@/components/layout/AuthLayout";
import { BackButton } from "@/components/ui/BackButton";
import { HunterCard } from "@/components/profile/HunterCard";
import { ProgressGraph } from "@/components/profile/ProgressGraph";
import { AchievementWall } from "@/components/profile/AchievementWall";
import type { TrainingStats, GamificationProgress, ProgressPoint } from "@/types";
import { logger } from "@/lib/logger";

export default function ProfilePage() {
  const { user, loading: authLoading } = useAuth();
  const [stats, setStats] = useState<TrainingStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(true);
  const [progress, setProgress] = useState<GamificationProgress | null>(null);
  const [progressData, setProgressData] = useState<ProgressPoint[]>([]);

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
      .catch((err) => { logger.error("Failed to load user stats:", err); setStats(null); })
      .finally(() => setStatsLoading(false));

    api
      .get("/gamification/me/progress")
      .then(setProgress)
      .catch((err) => { logger.error("Failed to load gamification progress:", err); setProgress(null); });

    api
      .get("/analytics/me/snapshot")
      .then((data: { progress?: ProgressPoint[] }) => setProgressData(data.progress ?? []))
      .catch((err) => { logger.error("Failed to load progress data:", err); });
  }, [user]);

  const handlePasswordChange = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordError("");
    setPasswordSuccess("");
    if (newPassword !== confirmPassword) { setPasswordError("Пароли не совпадают"); return; }
    if (newPassword.length < 8) { setPasswordError("Пароль должен быть не менее 8 символов"); return; }

    setPasswordLoading(true);
    try {
      await api.put("/users/me/password", { old_password: oldPassword, new_password: newPassword });
      setPasswordSuccess("Пароль успешно изменён");
      setTimeout(() => setPasswordSuccess(""), 4000);
      setOldPassword(""); setNewPassword(""); setConfirmPassword("");
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

  return (
    <AuthLayout>
      <div className="panel-grid-bg min-h-screen">
        <div className="app-page max-w-4xl">
          <BackButton href="/home" label="На главную" />
          {/* Header */}
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
            <div className="flex items-center gap-2">
              <User size={24} style={{ color: "var(--accent)" }} />
              <h1 className="font-display text-3xl font-bold tracking-wider" style={{ color: "var(--text-primary)" }}>
                ПРОФИЛЬ
              </h1>
            </div>
          </motion.div>

          {/* Hunter Card */}
          <div className="mt-6">
            <HunterCard
              user={{ full_name: user?.full_name || "", email: user?.email || "", role: user?.role || "" }}
              stats={stats ? { completed_sessions: stats.completed_sessions, avg_score: stats.average_score, best_score: stats.best_score } : null}
              gamification={progress}
              teamName={user?.team ?? undefined}
            />
          </div>

          {/* Progress Graph */}
          <div className="mt-6">
            <ProgressGraph data={progressData} />
          </div>

          {/* Achievement Wall */}
          <div className="mt-6">
            <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
              <div className="flex items-center gap-2 mb-4">
                <User size={16} style={{ color: "var(--accent)" }} />
                <span className="font-display text-sm font-bold tracking-widest uppercase" style={{ color: "var(--text-secondary)" }}>
                  Достижения
                </span>
              </div>
              <AchievementWall achievements={progress?.achievements ?? []} />
            </motion.div>
          </div>

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
                    <Lock size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2" style={{ color: "var(--text-muted)" }} />
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
                className="btn-neon flex items-center gap-2"
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
