"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import {
  Settings, Volume2, Bell, Palette, Save, Loader2, CheckCircle2,
  Link2, Unlink, Mail, MessageSquare, Clock, Smartphone, SendHorizonal,
  Gamepad2, GraduationCap, Kanban, LayoutGrid, Paintbrush, Info,
} from "lucide-react";
import { useTheme } from "next-themes";
import { api } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { useAuthStore } from "@/stores/useAuthStore";
import { useWebPush } from "@/hooks/useWebPush";
import AuthLayout from "@/components/layout/AuthLayout";
import { BackButton } from "@/components/ui/BackButton";
import { AvatarUpload } from "@/components/settings/AvatarUpload";
import { PIPELINE_STATUSES, CLIENT_STATUS_LABELS } from "@/types";
import type { ClientStatus, User } from "@/types";
import { logger } from "@/lib/logger";

/** Invalidate cache + re-fetch user to reflect avatar/profile changes immediately */
function invalidateUserCache() {
  useAuthStore.getState().invalidate(); // Reset 30s cache TTL
  void useAuthStore.getState().fetchUser(); // Force fresh fetch from /auth/me
}

const roleLabels: Record<string, string> = {
  manager: "Менеджер",
  rop: "Руководитель ОП",
  methodologist: "Методолог",
  admin: "Администратор",
};

const TRAINING_MODES = [
  { key: "voice", label: "Голос" },
  { key: "text", label: "Текст" },
  { key: "mixed", label: "Микс" },
  { key: "structured", label: "Структура" },
  { key: "freestyle", label: "Свобода" },
  { key: "challenge", label: "Вызов" },
] as const;

const EXPERIENCE_LEVELS = [
  { key: "beginner", label: "Новичок" },
  { key: "intermediate", label: "Средний" },
  { key: "advanced", label: "Продвинутый" },
] as const;

const ACCENT_COLORS = [
  { key: "violet", label: "Violet", color: "#8A2BE2" },
  { key: "blue", label: "Blue", color: "#3B82F6" },
  { key: "emerald", label: "Emerald", color: "#10B981" },
  { key: "amber", label: "Amber", color: "#F59E0B" },
  { key: "rose", label: "Rose", color: "#F43F5E" },
] as const;

// Toggle switch component to reduce repetition
function Toggle({ on, onChange, size = "md" }: { on: boolean; onChange: () => void; size?: "sm" | "md" }) {
  const w = size === "sm" ? "w-10 h-5" : "w-12 h-6";
  const dot = size === "sm" ? "w-4 h-4" : "w-4 h-4";
  const left = size === "sm" ? (on ? 22 : 2) : (on ? 28 : 4);
  const top = size === "sm" ? "top-0.5" : "top-1";
  return (
    <motion.button
      onClick={onChange}
      className={`relative ${w} rounded-full transition-colors`}
      style={{ background: on ? "var(--accent)" : "var(--border-color)" }}
      whileTap={{ scale: 0.95 }}
    >
      <motion.div
        className={`absolute ${top} ${dot} rounded-full bg-white`}
        animate={{ left }}
        transition={{ type: "spring", stiffness: 500, damping: 30 }}
      />
    </motion.button>
  );
}

export default function SettingsPage() {
  const { user } = useAuth();
  const { theme, setTheme } = useTheme();
  const [ttsEnabled, setTtsEnabled] = useState(true);
  const [notifications, setNotifications] = useState(true);
  const [notifyEmail, setNotifyEmail] = useState(false);
  const [notifyPush, setNotifyPush] = useState(true);
  const [notifyFrequency, setNotifyFrequency] = useState<"realtime" | "daily" | "weekly">("realtime");
  const [trainingMode, setTrainingMode] = useState<string>("mixed");
  const [experienceLevel, setExperienceLevel] = useState<string>("beginner");
  const [pipelineColumns, setPipelineColumns] = useState<string[]>(PIPELINE_STATUSES as string[]);
  const [compactMode, setCompactMode] = useState(false);
  const [accentColor, setAccentColor] = useState<string>("violet");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);

  const webPush = useWebPush();

  // OAuth state
  const [oauthStatus, setOauthStatus] = useState<{ google: boolean; yandex: boolean }>({ google: false, yandex: false });
  const [linkedGoogle, setLinkedGoogle] = useState(false);
  const [linkedYandex, setLinkedYandex] = useState(false);
  const [unlinking, setUnlinking] = useState<string | null>(null);
  const [avatarUrl, setAvatarUrl] = useState<string | null>(null);

  useEffect(() => setMounted(true), []);

  // Load preferences from user object (already in auth store, no extra API call)
  useEffect(() => {
    if (!user) return;
    if (user.avatar_url) setAvatarUrl(user.avatar_url);
    const p = (user.preferences as Record<string, unknown>) || {};
    if (typeof p.tts_enabled === "boolean") setTtsEnabled(p.tts_enabled);
    if (typeof p.notifications === "boolean") setNotifications(p.notifications);
    if (typeof p.notify_email === "boolean") setNotifyEmail(p.notify_email);
    if (typeof p.notify_push === "boolean") setNotifyPush(p.notify_push);
    if (typeof p.notify_frequency === "string") setNotifyFrequency(p.notify_frequency as "realtime" | "daily" | "weekly");
    if (typeof p.training_mode === "string") setTrainingMode(p.training_mode);
    if (typeof p.experience_level === "string") setExperienceLevel(p.experience_level);
    if (Array.isArray(p.pipeline_columns)) setPipelineColumns(p.pipeline_columns as string[]);
    if (typeof p.compact_mode === "boolean") setCompactMode(p.compact_mode);
    if (typeof p.accent_color === "string") setAccentColor(p.accent_color);
    setLinkedGoogle(!!user.google_id);
    setLinkedYandex(!!user.yandex_id);

    api.get("/auth/oauth/status")
      .then((data: { google: boolean; yandex: boolean }) => setOauthStatus(data))
      .catch((err) => { logger.error("Failed to load OAuth status:", err); });
  }, [user]);

  // Apply accent color + compact mode immediately (live preview via store)
  // Store is single source of truth for localStorage writes — no direct writes here
  useEffect(() => {
    if (!mounted) return;
    const html = document.documentElement;
    ACCENT_COLORS.forEach((c) => html.classList.remove(`accent-${c.key}`));
    if (accentColor && accentColor !== "violet") {
      html.classList.add(`accent-${accentColor}`);
    }
  }, [accentColor, mounted]);

  useEffect(() => {
    if (!mounted) return;
    document.body.classList.toggle("compact-mode", compactMode);
  }, [compactMode, mounted]);

  const handleSave = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      const prefs = {
        tts_enabled: ttsEnabled,
        notifications,
        notify_email: notifyEmail,
        notify_push: notifyPush,
        notify_frequency: notifyFrequency,
        training_mode: trainingMode,
        experience_level: experienceLevel,
        pipeline_columns: pipelineColumns,
        compact_mode: compactMode,
        accent_color: accentColor,
      };
      await api.post("/users/me/preferences", prefs);
      // Update store directly (no null flash, no redirect, instant UI sync)
      useAuthStore.getState().updatePreferences(prefs);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Ошибка сохранения настроек");
    }
    setSaving(false);
  };

  const showCRM = user?.role && ["admin", "rop", "manager"].includes(user.role);
  let delay = 0;
  const nextDelay = () => { delay += 0.05; return delay; };

  // Chip button helper
  const Chip = ({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) => (
    <motion.button
      onClick={onClick}
      className="rounded-lg px-3.5 py-2 font-mono text-xs transition-all"
      style={{
        background: active ? "var(--accent-muted)" : "var(--input-bg)",
        border: `1px solid ${active ? "var(--accent)" : "var(--border-color)"}`,
        color: active ? "var(--accent)" : "var(--text-muted)",
      }}
      whileTap={{ scale: 0.95 }}
    >
      {label}
    </motion.button>
  );

  return (
    <AuthLayout>
      <div className="relative panel-grid-bg min-h-screen">
        <div className="app-page max-w-2xl">
          <BackButton href="/home" label="На главную" />
          {/* Header: avatar + name + title */}
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
            className="flex items-center gap-4 mb-8"
          >
            <AvatarUpload
              currentUrl={avatarUrl}
              userName={user?.full_name || ""}
              size={52}
              onUploaded={(url) => { setAvatarUrl(url); invalidateUserCache(); }}
              onDeleted={() => { setAvatarUrl(null); invalidateUserCache(); }}
            />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <Settings size={18} style={{ color: "var(--accent)" }} />
                <h1 className="font-display text-2xl font-bold tracking-[0.12em]" style={{ color: "var(--text-primary)" }}>
                  НАСТРОЙКИ
                </h1>
              </div>
              <p className="text-xs mt-0.5 truncate" style={{ color: "var(--text-muted)" }}>
                {user?.full_name} • {user?.role ? roleLabels[user.role] || user.role : ""}
              </p>
            </div>
          </motion.div>

          <div className="space-y-4">

            {/* ── Appearance ── */}
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: nextDelay() }}
              className="glass-panel p-5"
            >
              <div className="flex items-center gap-3 mb-4">
                <Palette size={18} style={{ color: "var(--text-secondary)" }} />
                <div>
                  <div className="text-[15px] font-medium" style={{ color: "var(--text-primary)" }}>Оформление</div>
                  <div className="text-xs" style={{ color: "var(--text-muted)" }}>Тема и акцентный цвет</div>
                </div>
              </div>

              {/* Theme row */}
              <div className="flex items-center justify-between mb-4">
                <span className="text-xs" style={{ color: "var(--text-secondary)" }}>Тема</span>
                {mounted && (
                  <div className="flex gap-2">
                    {([
                      { key: "dark", label: "Тёмная" },
                      { key: "light", label: "Светлая" },
                      { key: "system", label: "Авто" },
                    ] as const).map((t) => (
                      <Chip key={t.key} active={theme === t.key} label={t.label} onClick={() => setTheme(t.key)} />
                    ))}
                  </div>
                )}
              </div>

              {/* Accent color row */}
              <div className="flex items-center justify-between">
                <span className="text-xs" style={{ color: "var(--text-secondary)" }}>Акцент</span>
                <div className="flex gap-2">
                  {ACCENT_COLORS.map((c) => (
                    <motion.button
                      key={c.key}
                      onClick={() => setAccentColor(c.key)}
                      className="relative w-8 h-8 rounded-full transition-all"
                      style={{
                        background: c.color,
                        boxShadow: accentColor === c.key ? `0 0 0 2px var(--bg-primary), 0 0 0 4px ${c.color}` : "none",
                        opacity: accentColor === c.key ? 1 : 0.6,
                      }}
                      whileHover={{ scale: 1.15 }}
                      whileTap={{ scale: 0.9 }}
                      title={c.label}
                    />
                  ))}
                </div>
              </div>
            </motion.div>

            {/* ── Training ── */}
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: nextDelay() }}
              className="glass-panel p-5"
            >
              <div className="flex items-center gap-3 mb-4">
                <Gamepad2 size={18} style={{ color: "var(--text-secondary)" }} />
                <div>
                  <div className="text-[15px] font-medium" style={{ color: "var(--text-primary)" }}>Тренировки</div>
                  <div className="text-xs" style={{ color: "var(--text-muted)" }}>Режим и сложность</div>
                </div>
              </div>

              {/* TTS */}
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <Volume2 size={15} style={{ color: "var(--text-muted)" }} />
                  <span className="text-xs" style={{ color: "var(--text-secondary)" }}>Озвучка AI-клиента</span>
                </div>
                <Toggle on={ttsEnabled} onChange={() => setTtsEnabled(!ttsEnabled)} />
              </div>

              {/* Training mode */}
              <div className="mb-4">
                <span className="text-xs block mb-2" style={{ color: "var(--text-secondary)" }}>Режим тренировки</span>
                <div className="flex flex-wrap gap-2">
                  {TRAINING_MODES.map((m) => (
                    <Chip key={m.key} active={trainingMode === m.key} label={m.label} onClick={() => setTrainingMode(m.key)} />
                  ))}
                </div>
              </div>

              {/* Experience level */}
              <div>
                <span className="text-xs block mb-2" style={{ color: "var(--text-secondary)" }}>Уровень опыта</span>
                <div className="flex gap-2">
                  {EXPERIENCE_LEVELS.map((l) => (
                    <Chip key={l.key} active={experienceLevel === l.key} label={l.label} onClick={() => setExperienceLevel(l.key)} />
                  ))}
                </div>
              </div>
            </motion.div>

            {/* ── Interface ── */}
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: nextDelay() }}
              className="glass-panel p-5"
            >
              <div className="flex items-center gap-3 mb-4">
                <LayoutGrid size={18} style={{ color: "var(--text-secondary)" }} />
                <div>
                  <div className="text-[15px] font-medium" style={{ color: "var(--text-primary)" }}>Интерфейс</div>
                  <div className="text-xs" style={{ color: "var(--text-muted)" }}>Плотность и отображение</div>
                </div>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-xs" style={{ color: "var(--text-secondary)" }}>Компактный режим</span>
                <Toggle on={compactMode} onChange={() => setCompactMode(!compactMode)} />
              </div>
            </motion.div>

            {/* ── Pipeline columns (CRM roles only) ── */}
            {showCRM && (
              <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: nextDelay() }}
                className="glass-panel p-5"
              >
                <div className="flex items-center gap-3 mb-4">
                  <Kanban size={18} style={{ color: "var(--text-secondary)" }} />
                  <div>
                    <div className="text-[15px] font-medium" style={{ color: "var(--text-primary)" }}>Воронка</div>
                    <div className="text-xs" style={{ color: "var(--text-muted)" }}>Видимые столбцы в канбане</div>
                  </div>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                  {PIPELINE_STATUSES.map((status) => {
                    const on = pipelineColumns.includes(status);
                    return (
                      <motion.button
                        key={status}
                        onClick={() => {
                          if (on && pipelineColumns.length <= 2) return; // min 2 columns
                          setPipelineColumns(on
                            ? pipelineColumns.filter((s) => s !== status)
                            : [...pipelineColumns, status],
                          );
                        }}
                        className="flex items-center gap-2 rounded-lg px-3 py-2 text-[12px] font-mono transition-all text-left"
                        style={{
                          background: on ? "var(--accent-muted)" : "var(--input-bg)",
                          border: `1px solid ${on ? "var(--accent)" : "var(--border-color)"}`,
                          color: on ? "var(--accent)" : "var(--text-muted)",
                        }}
                        whileTap={{ scale: 0.97 }}
                      >
                        <div
                          className="w-2 h-2 rounded-full shrink-0"
                          style={{
                            background: on ? "var(--accent)" : "var(--text-muted)",
                            opacity: on ? 1 : 0.4,
                          }}
                        />
                        {CLIENT_STATUS_LABELS[status as ClientStatus]}
                      </motion.button>
                    );
                  })}
                </div>
              </motion.div>
            )}

            {/* ── Notifications & Channels ── */}
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: nextDelay() }}
              className="glass-panel p-5"
            >
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <Bell size={18} style={{ color: "var(--text-secondary)" }} />
                  <div>
                    <div className="text-[15px] font-medium" style={{ color: "var(--text-primary)" }}>Уведомления</div>
                    <div className="text-xs" style={{ color: "var(--text-muted)" }}>Каналы и частота</div>
                  </div>
                </div>
                <Toggle on={notifications} onChange={() => setNotifications(!notifications)} />
              </div>

              {notifications && (
                <div className="space-y-3 pt-2 border-t" style={{ borderColor: "var(--border-color)" }}>
                  {/* In-app */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <MessageSquare size={14} style={{ color: "var(--text-muted)" }} />
                      <span className="text-xs" style={{ color: "var(--text-secondary)" }}>В приложении</span>
                    </div>
                    <Toggle on={notifyPush} onChange={() => setNotifyPush(!notifyPush)} size="sm" />
                  </div>

                  {/* Email */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Mail size={14} style={{ color: "var(--text-muted)" }} />
                      <span className="text-xs" style={{ color: "var(--text-secondary)" }}>Email</span>
                    </div>
                    <Toggle on={notifyEmail} onChange={() => setNotifyEmail(!notifyEmail)} size="sm" />
                  </div>

                  {/* Web Push */}
                  {webPush.isSupported && (
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Smartphone size={14} style={{ color: "var(--text-muted)" }} />
                        <div>
                          <span className="text-xs" style={{ color: "var(--text-secondary)" }}>Web Push</span>
                          {webPush.isDenied && (
                            <span className="block text-xs" style={{ color: "var(--neon-red)" }}>Заблокировано</span>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        {webPush.isSubscribed && (
                          <motion.button
                            onClick={webPush.sendTest}
                            className="rounded px-2 py-1 text-xs font-mono"
                            style={{ background: "var(--input-bg)", color: "var(--text-muted)", border: "1px solid var(--border-color)" }}
                            whileTap={{ scale: 0.95 }}
                            title="Тест"
                          >
                            <SendHorizonal size={11} />
                          </motion.button>
                        )}
                        <Toggle
                          on={webPush.isSubscribed}
                          onChange={() => webPush.isSubscribed ? webPush.unsubscribe() : webPush.subscribe()}
                          size="sm"
                        />
                      </div>
                    </div>
                  )}
                  {webPush.error && (
                    <p className="text-xs font-mono" style={{ color: "var(--neon-red)" }}>{webPush.error}</p>
                  )}

                  {/* Frequency */}
                  <div className="pt-2 border-t" style={{ borderColor: "var(--border-color)" }}>
                    <div className="flex items-center gap-2 mb-2">
                      <Clock size={14} style={{ color: "var(--text-muted)" }} />
                      <span className="text-xs" style={{ color: "var(--text-secondary)" }}>Частота</span>
                    </div>
                    <div className="flex gap-2">
                      {([
                        { key: "realtime" as const, label: "Сразу" },
                        { key: "daily" as const, label: "Раз в день" },
                        { key: "weekly" as const, label: "Раз в неделю" },
                      ]).map((f) => (
                        <Chip key={f.key} active={notifyFrequency === f.key} label={f.label} onClick={() => setNotifyFrequency(f.key)} />
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </motion.div>

            {/* ── Linked Accounts ── */}
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: nextDelay() }}
              className="glass-panel p-5"
            >
              <div className="flex items-center gap-3 mb-4">
                <Link2 size={18} style={{ color: "var(--text-secondary)" }} />
                <div>
                  <div className="text-[15px] font-medium" style={{ color: "var(--text-primary)" }}>Привязанные аккаунты</div>
                  <div className="text-xs" style={{ color: "var(--text-muted)" }}>Вход через Google или Yandex</div>
                </div>
              </div>
              <div className="space-y-3">
                {/* Google */}
                <div className="flex items-center justify-between rounded-xl p-3" style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)" }}>
                  <div className="flex items-center gap-3">
                    <svg width="20" height="20" viewBox="0 0 24 24"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/></svg>
                    <div>
                      <div className="text-[14px] font-medium" style={{ color: "var(--text-primary)" }}>Google</div>
                      <div className="text-xs font-mono" style={{ color: linkedGoogle ? "var(--neon-green)" : "var(--text-muted)" }}>
                        {linkedGoogle ? "Привязан" : "Не привязан"}
                      </div>
                    </div>
                  </div>
                  {linkedGoogle ? (
                    <motion.button
                      onClick={async () => {
                        setUnlinking("google");
                        try { await api.post("/auth/google/disconnect", {}); setLinkedGoogle(false); } catch (err) { logger.error("[Settings] Google disconnect failed:", err); }
                        setUnlinking(null);
                      }}
                      disabled={unlinking === "google"}
                      className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 font-mono text-[12px]"
                      style={{ background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.2)", color: "var(--neon-red)" }}
                      whileTap={{ scale: 0.95 }}
                    >
                      {unlinking === "google" ? <Loader2 size={12} className="animate-spin" /> : <Unlink size={12} />}
                      Отвязать
                    </motion.button>
                  ) : oauthStatus.google ? (
                    <motion.button
                      onClick={async () => { try { const d = await api.get("/auth/google/login"); if (d?.url) { const { validateOAuthUrl } = await import("@/lib/sanitize"); const safeUrl = validateOAuthUrl(d.url); if (safeUrl) window.location.href = safeUrl; } } catch (err) { logger.error("[Settings] Google link failed:", err); } }}
                      className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 font-mono text-[12px]"
                      style={{ background: "var(--accent-muted)", border: "1px solid var(--accent)", color: "var(--accent)" }}
                      whileTap={{ scale: 0.95 }}
                    >
                      <Link2 size={12} /> Привязать
                    </motion.button>
                  ) : (
                    <span className="font-mono text-xs" style={{ color: "var(--text-muted)" }}>Не настроен</span>
                  )}
                </div>

                {/* Yandex */}
                <div className="flex items-center justify-between rounded-xl p-3" style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)" }}>
                  <div className="flex items-center gap-3">
                    <svg width="20" height="20" viewBox="0 0 24 24"><path d="M2 12C2 6.48 6.48 2 12 2s10 4.48 10 10-4.48 10-10 10S2 17.52 2 12z" fill="#FC3F1D"/><path d="M13.32 17.5h-1.88V7.38h-.97c-1.57 0-2.39.8-2.39 1.95 0 1.3.59 1.9 1.8 2.7l1 .65-2.9 4.82H6l2.62-4.33C7.37 12.26 6.56 11.22 6.56 9.5c0-2.07 1.45-3.5 4-3.5h2.76V17.5z" fill="white"/></svg>
                    <div>
                      <div className="text-[14px] font-medium" style={{ color: "var(--text-primary)" }}>Yandex</div>
                      <div className="text-xs font-mono" style={{ color: linkedYandex ? "var(--neon-green)" : "var(--text-muted)" }}>
                        {linkedYandex ? "Привязан" : "Не привязан"}
                      </div>
                    </div>
                  </div>
                  {linkedYandex ? (
                    <motion.button
                      onClick={async () => {
                        setUnlinking("yandex");
                        try { await api.post("/auth/yandex/disconnect", {}); setLinkedYandex(false); } catch (err) { logger.error("[Settings] Yandex disconnect failed:", err); }
                        setUnlinking(null);
                      }}
                      disabled={unlinking === "yandex"}
                      className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 font-mono text-[12px]"
                      style={{ background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.2)", color: "var(--neon-red)" }}
                      whileTap={{ scale: 0.95 }}
                    >
                      {unlinking === "yandex" ? <Loader2 size={12} className="animate-spin" /> : <Unlink size={12} />}
                      Отвязать
                    </motion.button>
                  ) : oauthStatus.yandex ? (
                    <motion.button
                      onClick={async () => { try { const d = await api.get("/auth/yandex/login"); if (d?.url) { const { validateOAuthUrl } = await import("@/lib/sanitize"); const safeUrl = validateOAuthUrl(d.url); if (safeUrl) window.location.href = safeUrl; } } catch (err) { logger.error("[Settings] Yandex link failed:", err); } }}
                      className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 font-mono text-[12px]"
                      style={{ background: "var(--accent-muted)", border: "1px solid var(--accent)", color: "var(--accent)" }}
                      whileTap={{ scale: 0.95 }}
                    >
                      <Link2 size={12} /> Привязать
                    </motion.button>
                  ) : (
                    <span className="font-mono text-xs" style={{ color: "var(--text-muted)" }}>Не настроен</span>
                  )}
                </div>
              </div>
            </motion.div>

            {/* Save */}
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: nextDelay() }} className="flex flex-col items-end gap-2 pt-4">
              {saveError && (
                <p className="text-sm font-mono" style={{ color: "var(--neon-red)" }}>{saveError}</p>
              )}
              <motion.button
                onClick={handleSave}
                disabled={saving}
                className="btn-neon flex items-center gap-2 text-[14px]"
                whileTap={{ scale: 0.97 }}
              >
                {saving ? <Loader2 size={16} className="animate-spin" /> : saved ? <CheckCircle2 size={16} /> : <Save size={16} />}
                {saved ? "Сохранено" : "Сохранить настройки"}
              </motion.button>
            </motion.div>
          </div>
        </div>
      </div>
    </AuthLayout>
  );
}
