"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { motion } from "framer-motion";
import {
  User,
  Lock,
  ArrowRight,
  AlertCircle,
  CheckCircle,
  Loader2,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { api } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import AuthLayout from "@/components/layout/AuthLayout";
import { BackButton } from "@/components/ui/BackButton";
import { HunterCard } from "@/components/profile/HunterCard";
import { XPDailyProgress } from "@/components/gamification/XPDailyProgress";
import dynamic from "next/dynamic";
import { Skeleton } from "@/components/ui/Skeleton";

const ProgressGraph = dynamic(
  () => import("@/components/profile/ProgressGraph").then((m) => m.ProgressGraph),
  { loading: () => <Skeleton height={240} width="100%" rounded="12px" />, ssr: false }
);
import { AchievementWall } from "@/components/profile/AchievementWall";
import OfficeShelf from "@/components/gamification/OfficeShelf";
import DealPortfolio from "@/components/gamification/DealPortfolio";
import type { TrainingStats, GamificationProgress, ProgressPoint } from "@/types";
import { logger } from "@/lib/logger";

function ProfilePageContent() {
  const searchParams = useSearchParams();
  const viewUserId = searchParams.get("user");
  const { user, loading: authLoading } = useAuth();
  const [viewedUser, setViewedUser] = useState<{ id: string; full_name: string; role: string; avatar_url?: string | null } | null>(null);
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

  const isViewingOther = !!viewUserId && viewUserId !== user?.id;
  const targetUserId = isViewingOther ? viewUserId : user?.id;

  // Fetch viewed user info if viewing someone else
  useEffect(() => {
    if (!isViewingOther || !viewUserId) { setViewedUser(null); return; }
    api.get(`/users/${viewUserId}/profile`)
      .then((data: { id: string; full_name: string; role: string; avatar_url?: string | null }) => setViewedUser(data))
      .catch(() => setViewedUser(null));
  }, [viewUserId, isViewingOther]);

  useEffect(() => {
    if (!targetUserId) return;
    setStatsLoading(true);
    api
      .get(`/users/${targetUserId}/stats`)
      .then(setStats)
      .catch((err) => { logger.error("Failed to load user stats:", err); setStats(null); })
      .finally(() => setStatsLoading(false));

    if (!isViewingOther) {
      api
        .get("/gamification/me/progress")
        .then(setProgress)
        .catch((err) => { logger.error("Failed to load gamification progress:", err); setProgress(null); });

      api
        .get("/analytics/me/snapshot")
        .then((data: { progress?: ProgressPoint[] }) => setProgressData(data.progress ?? []))
        .catch((err) => { logger.error("Failed to load progress data:", err); });
    } else {
      // For other users — try fetching their progress via admin endpoint
      api
        .get(`/users/${targetUserId}/progress`)
        .then((data: { progress?: ProgressPoint[] }) => setProgressData(data.progress ?? []))
        .catch(() => setProgressData([]));
    }
  }, [targetUserId, isViewingOther]);

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
          <BackButton href={isViewingOther ? "/dashboard" : "/home"} label={isViewingOther ? "Панель РОП" : "На главную"} />
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
            {isViewingOther && !viewedUser ? (
              <Skeleton height={160} width="100%" rounded="12px" />
            ) : (
              <HunterCard
                user={{
                  full_name: isViewingOther && viewedUser ? viewedUser.full_name : user?.full_name || "",
                  email: isViewingOther ? "" : user?.email || "",
                  role: isViewingOther && viewedUser ? viewedUser.role : user?.role || "",
                }}
                stats={stats ? { completed_sessions: stats.completed_sessions, avg_score: stats.average_score ?? stats.avg_score ?? null, best_score: stats.best_score } : null}
                gamification={progress}
                teamName={user?.team ?? undefined}
              />
            )}
          </div>

          {/* Daily XP Cap Status */}
          {!isViewingOther && (
            <XPDailyProgress className="mt-8" />
          )}

          {/* Progress Graph */}
          <div className="mt-8">
            <ProgressGraph data={progressData} />
          </div>

          {/* Achievement Wall */}
          <div className="mt-10 mb-12">
            <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
              <div className="flex items-center gap-2 mb-6">
                <User size={18} style={{ color: "var(--accent)" }} />
                <span className="font-display text-base font-bold tracking-widest uppercase" style={{ color: "var(--text-secondary)" }}>
                  Достижения
                </span>
              </div>
              <AchievementWall achievements={progress?.achievements ?? []} />
            </motion.div>

            {/* Office Shelf — full display */}
            <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 }}>
              <OfficeShelf
                level={progress?.level ?? 1}
                achievementCount={progress?.achievements?.length ?? 0}
                totalDeals={0}
                totalSessions={stats?.completed_sessions ?? 0}
              />
            </motion.div>

            {/* Deal Portfolio — full display */}
            <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}>
              <DealPortfolio compact={false} limit={50} />
            </motion.div>
          </div>

          {/* Password change — only for own profile */}
          {!isViewingOther && <motion.div
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
                  style={{ background: "var(--danger-muted)", border: "1px solid var(--danger-muted)", color: "var(--danger)" }}
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
                  style={{ background: "var(--success-muted)", border: "1px solid var(--success-muted)", color: "var(--success)" }}
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

              <Button
                type="submit"
                disabled={passwordLoading}
                loading={passwordLoading}
                iconRight={<ArrowRight size={16} />}
              >
                Изменить пароль
              </Button>
            </form>
          </motion.div>}
        </div>
      </div>
    </AuthLayout>
  );
}

export default function ProfilePage() {
  return (
    <Suspense fallback={<AuthLayout><div className="flex items-center justify-center min-h-screen"><Loader2 size={24} className="animate-spin" style={{ color: "var(--accent)" }} /></div></AuthLayout>}>
      <ProfilePageContent />
    </Suspense>
  );
}
