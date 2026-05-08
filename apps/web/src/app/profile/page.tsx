"use client";

/**
 * /profile — «★ ПРОФИЛЬ ОХОТНИКА ★» (аркадный редизайн 2026-05-08).
 *
 * Что изменилось vs прошлой версии:
 *   - убран скучный H1 «ПРОФИЛЬ» — теперь пиксельный сяющий лого
 *     (тот же effect что на /leaderboard «ЗАЛ СЛАВЫ», но в фиолет-
 *     зелёном градиенте чтобы отличался)
 *   - подзаголовок-метрики «УР. 15 · 123 008 XP · СЕЗОН I»
 *   - добавлен ActivityHeatmap — GitHub-style daily heatmap за
 *     180 дней + streak counters (источник: новый GET /users/me/activity)
 *   - все блоки обёрнуты в пиксельные `<ProfileSection>` с акцентной
 *     рамкой по теме секции (цвет HUD-блока) — единый ритм
 *   - смена пароля — accordion-блок «ПЕРЕВЫПУСТИТЬ КЛЮЧ» внизу,
 *     не доминирует
 *
 * НЕ ТРОГАЛ:
 *   - HunterCard (там и так пиксель), ProgressGraph, OfficeShelf,
 *     DealPortfolio — оставлены как есть, обёрнуты в новые секции
 *   - все API-вызовы, типы, payload'ы
 */

import { useEffect, useState, Suspense, type ReactNode } from "react";
import { useSearchParams } from "next/navigation";
import { motion } from "framer-motion";
import {
  User as UserIcon,
  Lock,
  ArrowRight,
  AlertCircle,
  CheckCircle,
  Loader2,
  ChevronDown,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { api } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import AuthLayout from "@/components/layout/AuthLayout";
import { BackButton } from "@/components/ui/BackButton";
import { HunterCard } from "@/components/profile/HunterCard";
import { ActivityHeatmap } from "@/components/profile/ActivityHeatmap";
import { XPDailyProgress } from "@/components/gamification/XPDailyProgress";
import dynamic from "next/dynamic";
import { Skeleton } from "@/components/ui/Skeleton";

const ProgressGraph = dynamic(
  () => import("@/components/profile/ProgressGraph").then((m) => m.ProgressGraph),
  { loading: () => <Skeleton height={240} width="100%" rounded="12px" />, ssr: false },
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
  const [, setStatsLoading] = useState(true);
  const [progress, setProgress] = useState<GamificationProgress | null>(null);
  const [progressData, setProgressData] = useState<ProgressPoint[]>([]);

  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [passwordSuccess, setPasswordSuccess] = useState("");
  const [passwordLoading, setPasswordLoading] = useState(false);
  const [passwordOpen, setPasswordOpen] = useState(false);

  const isViewingOther = !!viewUserId && viewUserId !== user?.id;
  const targetUserId = isViewingOther ? viewUserId : user?.id;

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

          {/*
            ═══ ПИКСЕЛЬНЫЙ ЛОГОТИП ★ ПРОФИЛЬ ОХОТНИКА ★ ═══
            Те же 3 keyframes, что на /leaderboard «Зал Славы», но
            градиент развёрнут — здесь акцент → зелёный (символика
            «достижений / роста»). Скан-блик 4сек, pulse-glow 3сек,
            звёзды twinkle в противофазе.
          */}
          <style jsx>{`
            @keyframes vh-profile-shine {
              0%   { background-position: -150% 0; }
              60%  { background-position:  250% 0; }
              100% { background-position:  250% 0; }
            }
            @keyframes vh-profile-pulse {
              0%, 100% {
                filter:
                  drop-shadow(0 3px 0 rgba(0,0,0,0.45))
                  drop-shadow(0 0 12px rgba(167,139,250,0.45))
                  drop-shadow(0 0 22px rgba(74,222,128,0.30));
              }
              50% {
                filter:
                  drop-shadow(0 3px 0 rgba(0,0,0,0.45))
                  drop-shadow(0 0 18px rgba(167,139,250,0.85))
                  drop-shadow(0 0 36px rgba(74,222,128,0.55));
              }
            }
            @keyframes vh-profile-star-a {
              0%, 100% { opacity: 1; transform: scale(1) rotate(0deg); }
              50%      { opacity: 0.55; transform: scale(0.85) rotate(15deg); }
            }
            @keyframes vh-profile-star-b {
              0%, 100% { opacity: 0.6; transform: scale(0.9) rotate(0deg); }
              50%      { opacity: 1; transform: scale(1.1) rotate(-15deg); }
            }
            .vh-profile-text {
              background:
                linear-gradient(
                  120deg,
                  transparent 0%,
                  transparent 35%,
                  rgba(255,255,255,0.9) 48%,
                  rgba(255,255,255,1) 50%,
                  rgba(255,255,255,0.9) 52%,
                  transparent 65%,
                  transparent 100%
                ),
                linear-gradient(180deg, #a78bfa 0%, #c4b5fd 35%, #4ade80 100%);
              background-size: 200% 100%, 100% 100%;
              background-position: -150% 0, 0 0;
              -webkit-background-clip: text;
              background-clip: text;
              -webkit-text-fill-color: transparent;
              animation:
                vh-profile-shine 4s ease-in-out infinite,
                vh-profile-pulse 3s ease-in-out infinite;
            }
            .vh-profile-star-left  { animation: vh-profile-star-a 1.8s ease-in-out infinite; display: inline-block; }
            .vh-profile-star-right { animation: vh-profile-star-b 1.8s ease-in-out infinite; display: inline-block; }
            @media (prefers-reduced-motion: reduce) {
              .vh-profile-text, .vh-profile-star-left, .vh-profile-star-right {
                animation: none !important;
              }
            }
          `}</style>
          <div className="text-center pt-2 pb-5 select-none">
            <div
              className="font-pixel vh-profile-text"
              style={{
                fontSize: "clamp(28px, 5vw, 48px)",
                lineHeight: 1.0,
                letterSpacing: "0.06em",
              }}
            >
              <span
                aria-hidden
                className="vh-profile-star-left"
                style={{
                  marginRight: 10,
                  color: "#a78bfa",
                  WebkitTextFillColor: "#a78bfa",
                  textShadow: "0 0 10px rgba(167,139,250,0.85)",
                }}
              >★</span>
              {isViewingOther && viewedUser
                ? "ПРОФИЛЬ ОХОТНИКА"
                : "ПРОФИЛЬ ОХОТНИКА"}
              <span
                aria-hidden
                className="vh-profile-star-right"
                style={{
                  marginLeft: 10,
                  color: "#a78bfa",
                  WebkitTextFillColor: "#a78bfa",
                  textShadow: "0 0 10px rgba(167,139,250,0.85)",
                }}
              >★</span>
            </div>
            {progress && !isViewingOther && (
              <div
                className="font-pixel uppercase tracking-widest mt-2"
                style={{ color: "var(--text-muted)", fontSize: 14 }}
              >
                УР. {progress.level} · {(progress.total_xp ?? 0).toLocaleString("ru-RU")} XP · СЕЗОН I
              </div>
            )}
          </div>

          {/* Hero — HunterCard остаётся, обёрнут в пиксельную рамку */}
          <ProfileSection accent="#a78bfa">
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
          </ProfileSection>

          {/* Daily XP cap — компактный, только себе */}
          {!isViewingOther && (
            <div className="mt-6">
              <XPDailyProgress />
            </div>
          )}

          {/*
            Активность по дням (heatmap) — только своему профилю.
            Endpoint /users/me/activity возвращает данные для viewer'а,
            чужой профиль показывать не имеет смысла.
          */}
          {!isViewingOther && (
            <ProfileSection accent="#4ade80" title="🔥 АКТИВНОСТЬ" mt={6}>
              <ActivityHeatmap days={180} accent="#4ade80" />
            </ProfileSection>
          )}

          {/* Прогресс по неделям */}
          <ProfileSection accent="#facc15" title="📈 ПРОГРЕСС" mt={6}>
            <ProgressGraph data={progressData} />
          </ProfileSection>

          {/* Достижения + полки + сделки */}
          <ProfileSection accent="#fb923c" title="🏆 ДОСТИЖЕНИЯ" mt={6}>
            <AchievementWall achievements={progress?.achievements ?? []} />
            <div className="mt-6">
              <OfficeShelf
                level={progress?.level ?? 1}
                achievementCount={progress?.achievements?.length ?? 0}
                totalDeals={0}
                totalSessions={stats?.completed_sessions ?? 0}
              />
            </div>
            <div className="mt-6">
              <DealPortfolio compact={false} limit={50} />
            </div>
          </ProfileSection>

          {/*
            Смена пароля — accordion. Пользователь делает это редко,
            нет смысла держать форму всегда раскрытой и тянуть на себя
            визуальный фокус. Кнопка-плашка раскрывает форму по клику.
          */}
          {!isViewingOther && (
            <ProfileSection accent="#f87171" title="🔑 БЕЗОПАСНОСТЬ" mt={6}>
              <button
                type="button"
                onClick={() => setPasswordOpen((v) => !v)}
                className="w-full flex items-center justify-between font-pixel uppercase tracking-widest px-4 py-3 rounded-md transition-colors"
                style={{
                  background: passwordOpen ? "rgba(248,113,113,0.12)" : "rgba(255,255,255,0.04)",
                  border: "1px solid rgba(248,113,113,0.35)",
                  color: passwordOpen ? "#f87171" : "var(--text-secondary)",
                  fontSize: 14,
                }}
              >
                <span className="inline-flex items-center gap-2">
                  <Lock size={14} />
                  ПЕРЕВЫПУСТИТЬ КЛЮЧ ДОСТУПА
                </span>
                <motion.span
                  animate={{ rotate: passwordOpen ? 180 : 0 }}
                  transition={{ duration: 0.2 }}
                >
                  <ChevronDown size={14} />
                </motion.span>
              </button>

              {passwordOpen && (
                <motion.form
                  onSubmit={handlePasswordChange}
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  className="overflow-hidden mt-4 space-y-3"
                >
                  {passwordError && (
                    <div
                      className="flex items-center gap-2 rounded-md p-3"
                      style={{
                        background: "rgba(248,113,113,0.12)",
                        border: "1px solid rgba(248,113,113,0.35)",
                        color: "#f87171",
                        fontSize: 14,
                      }}
                    >
                      <AlertCircle size={14} />
                      {passwordError}
                    </div>
                  )}
                  {passwordSuccess && (
                    <div
                      className="flex items-center gap-2 rounded-md p-3"
                      style={{
                        background: "rgba(74,222,128,0.12)",
                        border: "1px solid rgba(74,222,128,0.35)",
                        color: "#4ade80",
                        fontSize: 14,
                      }}
                    >
                      <CheckCircle size={14} />
                      {passwordSuccess}
                    </div>
                  )}
                  {[
                    { id: "oldPwd", label: "Текущий пароль", value: oldPassword, setter: setOldPassword },
                    { id: "newPwd", label: "Новый пароль", value: newPassword, setter: setNewPassword, placeholder: "Минимум 8 символов" },
                    { id: "confPwd", label: "Подтвердите пароль", value: confirmPassword, setter: setConfirmPassword },
                  ].map((f) => (
                    <div key={f.id}>
                      <label
                        htmlFor={f.id}
                        className="block font-pixel uppercase tracking-widest mb-1.5"
                        style={{ color: "var(--text-muted)", fontSize: 14 }}
                      >
                        {f.label}
                      </label>
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
                          style={{ fontSize: 14 }}
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
                </motion.form>
              )}
            </ProfileSection>
          )}

          {/* Footer — пиксельная подпись, симметрично /leaderboard */}
          <div className="text-center mt-12 mb-8">
            <div
              className="font-pixel uppercase tracking-widest inline-flex items-center gap-2"
              style={{ color: "var(--text-muted)", fontSize: 14 }}
            >
              <UserIcon size={14} />
              ★ КОНЕЦ ПРОФИЛЯ ★
              <UserIcon size={14} />
            </div>
          </div>
        </div>
      </div>
    </AuthLayout>
  );
}

/**
 * ProfileSection — пиксельная рамка для блока на /profile.
 *
 * Симметричен StageSection с /leaderboard, но без divider'а сверху —
 * вместо него встроенный заголовок-плашка слева в верхнем углу. Цвет
 * акцента варьируется по секции, чтобы создать визуальный ритм
 * (HUD-блок, активность, прогресс, достижения, безопасность).
 */
function ProfileSection({
  children,
  accent,
  title,
  mt,
}: {
  children: ReactNode;
  accent: string;
  title?: string;
  mt?: number;
}) {
  return (
    <section
      className="relative"
      style={{
        marginTop: mt ?? 24,
        border: `2px solid ${accent}33`,
        background: "rgba(8,5,18,0.35)",
        boxShadow: "inset 0 0 24px rgba(0,0,0,0.35)",
      }}
    >
      {title && (
        <div
          className="absolute -top-3 left-4 px-2 font-pixel uppercase tracking-widest"
          style={{
            background: "var(--bg-primary, #0b0b14)",
            color: accent,
            fontSize: 14,
            letterSpacing: "0.18em",
          }}
        >
          {title}
        </div>
      )}
      <div className="p-4 md:p-5">{children}</div>
    </section>
  );
}

export default function ProfilePage() {
  return (
    <Suspense
      fallback={
        <AuthLayout>
          <div className="flex items-center justify-center min-h-screen">
            <Loader2 size={24} className="animate-spin" style={{ color: "var(--accent)" }} />
          </div>
        </AuthLayout>
      }
    >
      <ProfilePageContent />
    </Suspense>
  );
}
