"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import {
  Save, Loader2, CheckCircle2,
  Unlink, Link2, Smartphone, SendHorizonal,
} from "lucide-react";
import {
  Gear, SpeakerHigh, Bell, Palette, Envelope, ChatCircle, Clock,
  GameController, Kanban, LinkSimple, Lightning, Terminal, Keyboard, Flame, User as UserIcon,
} from "@phosphor-icons/react";
import { useTheme } from "next-themes";
import { api } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { useGamificationStore } from "@/stores/useGamificationStore";
import { useAuthStore } from "@/stores/useAuthStore";
import { useWebPush } from "@/hooks/useWebPush";
import AuthLayout from "@/components/layout/AuthLayout";
import { BackButton } from "@/components/ui/BackButton";
import { Button } from "@/components/ui/Button";
import { AvatarUpload } from "@/components/settings/AvatarUpload";
import { PIPELINE_STATUSES, CLIENT_STATUS_LABELS, CLIENT_STATUS_COLORS } from "@/types";
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

const GENDERS = [
  { key: "male", label: "Мужской" },
  { key: "female", label: "Женский" },
  { key: "neutral", label: "Не указывать" },
] as const;

const ACCENT_COLORS = [
  { key: "violet", label: "Violet", color: "#8A2BE2" },
  { key: "blue", label: "Blue", color: "var(--info)" },
  { key: "emerald", label: "Emerald", color: "var(--success)" },
  { key: "amber", label: "Amber", color: "var(--warning)" },
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
  const [gender, setGender] = useState<string>("");
  const [roleTitle, setRoleTitle] = useState<string>("");
  const [leadSource, setLeadSource] = useState<string>("");
  const [primaryContact, setPrimaryContact] = useState<string>("");
  const [specialization, setSpecialization] = useState<string>("");
  const [pipelineColumns, setPipelineColumns] = useState<string[]>(PIPELINE_STATUSES as string[]);
  const [compactMode, setCompactMode] = useState(false);
  const [accentColor, setAccentColor] = useState<string>("violet");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);
  // Editable display name (PATCH /api/users/me/profile)
  const [fullName, setFullName] = useState<string>("");
  const [fullNameSaving, setFullNameSaving] = useState(false);
  const [fullNameSaved, setFullNameSaved] = useState(false);
  const [fullNameError, setFullNameError] = useState<string | null>(null);

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
    if (user.full_name) setFullName(user.full_name);
    const p = (user.preferences as Record<string, unknown>) || {};
    if (typeof p.tts_enabled === "boolean") setTtsEnabled(p.tts_enabled);
    if (typeof p.notifications === "boolean") setNotifications(p.notifications);
    if (typeof p.notify_email === "boolean") setNotifyEmail(p.notify_email);
    if (typeof p.notify_push === "boolean") setNotifyPush(p.notify_push);
    if (typeof p.notify_frequency === "string") setNotifyFrequency(p.notify_frequency as "realtime" | "daily" | "weekly");
    if (typeof p.training_mode === "string") setTrainingMode(p.training_mode);
    if (typeof p.experience_level === "string") setExperienceLevel(p.experience_level);
    if (typeof p.gender === "string") setGender(p.gender);
    if (typeof p.role_title === "string") setRoleTitle(p.role_title);
    if (typeof p.lead_source === "string") setLeadSource(p.lead_source);
    if (typeof p.primary_contact === "string") setPrimaryContact(p.primary_contact);
    if (typeof p.specialization === "string") setSpecialization(p.specialization);
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
        gender,
        role_title: roleTitle,
        lead_source: leadSource,
        primary_contact: primaryContact,
        specialization,
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

  const handleSaveName = async () => {
    const trimmed = fullName.trim();
    if (!trimmed || trimmed.length < 2) {
      setFullNameError("Имя должно содержать минимум 2 символа");
      return;
    }
    if (trimmed === user?.full_name) {
      // No change
      return;
    }
    setFullNameSaving(true);
    setFullNameError(null);
    try {
      await api.patch("/users/me/profile", { full_name: trimmed });
      invalidateUserCache();
      setFullNameSaved(true);
      setTimeout(() => setFullNameSaved(false), 2000);
    } catch (e) {
      setFullNameError(e instanceof Error ? e.message : "Ошибка сохранения имени");
    }
    setFullNameSaving(false);
  };

  const showCRM = user?.role && ["admin", "rop", "manager"].includes(user.role);
  const { level, currentXP, nextLevelXP, streak, fetchProgress } = useGamificationStore();
  useEffect(() => { fetchProgress(); }, [fetchProgress]);
  const xpPct = nextLevelXP > 0 ? Math.round((currentXP / nextLevelXP) * 100) : 0;
  let delay = 0;
  const nextDelay = () => { delay += 0.05; return delay; };

  // Chip button helper
  const Chip = ({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) => (
    <motion.button
      onClick={onClick}
      className="rounded-lg px-3.5 py-2 font-mono text-sm transition-all"
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

  // Bento grid card variants
  const bentoLarge = "md:col-span-2";
  const bentoMedium = "md:col-span-1";
  const bentoSmall = "md:col-span-1";

  const BentoCard = ({ children, className = "", delay = 0, accentColor = "var(--accent)" }: { children: React.ReactNode; className?: string; delay?: number; accentColor?: string }) => (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: delay * 0.05 }}
      className={`glass-panel p-5 relative overflow-hidden ${className}`}
      style={{ borderLeft: `3px solid ${accentColor}` }}
    >
      {children}
    </motion.div>
  );

  const BentoHeader = ({ icon: Icon, title, subtitle }: { icon: React.ElementType<any>; title: string; subtitle?: string }) => (
    <div className="flex items-center gap-3 mb-4">
      <div className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0" style={{ background: "var(--accent-muted)" }}>
        <Icon weight="duotone" size={20} style={{ color: "var(--accent)" }} />
      </div>
      <div>
        <div className="text-base font-semibold" style={{ color: "var(--text-primary)" }}>{title}</div>
        {subtitle && <div className="text-sm" style={{ color: "var(--text-muted)" }}>{subtitle}</div>}
      </div>
    </div>
  );

  return (
    <AuthLayout>
      <div className="relative panel-grid-bg min-h-screen">
        <div className="app-page max-w-5xl mx-auto">
          <BackButton href="/home" label="На главную" />
          
          {/* Bento Header - Full width */}
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
            className="relative flex items-center gap-5 mb-6 rounded-2xl p-6 overflow-hidden"
            style={{
              background: "linear-gradient(135deg, var(--glass-bg), var(--accent-muted))",
              border: "1px solid var(--accent-muted)",
            }}
          >
            <div className="absolute -top-16 -right-16 w-48 h-48 rounded-full pointer-events-none" style={{ background: "radial-gradient(circle, var(--accent-muted) 0%, transparent 70%)" }} />
            <AvatarUpload
              currentUrl={avatarUrl}
              userName={user?.full_name || ""}
              size={72}
              onUploaded={(url) => { setAvatarUrl(url); invalidateUserCache(); }}
              onDeleted={() => { setAvatarUrl(null); invalidateUserCache(); }}
            />
            <div className="relative z-10 flex-1">
              <div className="flex items-center gap-2">
                <Gear weight="duotone" size={24} style={{ color: "var(--accent)" }} />
                <h1 className="font-display text-2xl font-bold tracking-widest" style={{ color: "var(--text-primary)" }}>
                  НАСТРОЙКИ
                </h1>
              </div>
              <div className="flex items-center gap-3 mt-2 flex-wrap">
                <span className="inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-mono" style={{ background: "var(--accent-muted)", color: "var(--accent)" }}>
                  {roleLabels[user?.role || ""] || user?.role || ""}
                </span>
                <span className="inline-flex items-center gap-1 text-xs font-mono" style={{ color: "var(--accent)" }}>
                  <Lightning weight="duotone" size={12} /> Lv.{level}
                </span>
                <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                  {currentXP}/{nextLevelXP} XP
                </span>
                {streak > 0 && (
                  <span className="inline-flex items-center gap-1 text-xs font-mono" style={{ color: "var(--streak-color, var(--warning))" }}>
                    <Flame weight="duotone" size={12} /> {streak}д
                  </span>
                )}
              </div>
              <div className="mt-2 h-1.5 rounded-full w-full max-w-[240px]" style={{ background: "rgba(255,255,255,0.08)" }}>
                <div className="h-full rounded-full transition-all duration-700" style={{ width: `${xpPct}%`, background: "var(--accent)" }} />
              </div>
            </div>
            <div className="text-xs font-mono shrink-0 text-right" style={{ color: "var(--text-muted)" }}>
              ID: {user?.id ? `${user.id.slice(0, 8)}...` : "—"}
            </div>
          </motion.div>

          {/* Bento Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">

            {/* Account - Large card */}
            <BentoCard className={bentoLarge} delay={10}>
              <BentoHeader icon={Gear} title="Аккаунт" subtitle="Ваше отображаемое имя" />
              <div className="flex gap-2 items-center">
                <input
                  type="text"
                  value={fullName}
                  onChange={(e) => { setFullName(e.target.value); setFullNameError(null); setFullNameSaved(false); }}
                  onKeyDown={(e) => { if (e.key === "Enter") handleSaveName(); }}
                  maxLength={100}
                  placeholder="Введите ваше имя"
                  disabled={fullNameSaving}
                  className="flex-1 rounded-xl px-4 py-3 text-base outline-none transition-colors"
                  style={{
                    background: "var(--glass-bg)",
                    border: "1px solid var(--glass-border)",
                    color: "var(--text-primary)",
                  }}
                />
                <Button onClick={handleSaveName} disabled={fullNameSaving || !fullName.trim() || fullName.trim() === user?.full_name} className="shrink-0 px-4">
                  {fullNameSaving ? <Loader2 size={16} className="animate-spin" /> : fullNameSaved ? <CheckCircle2 size={16} /> : <Save size={16} />}
                </Button>
              </div>
              {fullNameError && <div className="text-xs mt-2" style={{ color: "var(--danger)" }}>{fullNameError}</div>}
              {fullNameSaved && <div className="text-xs mt-2" style={{ color: "var(--success)" }}>✓ Имя обновлено</div>}
              <div className="mt-3 pt-3 text-xs" style={{ color: "var(--text-muted)", borderTop: "1px solid var(--border-color)" }}>
                Email: {user?.email} (не редактируется)
              </div>
            </BentoCard>

            {/* Required Profile - Medium card */}
            <BentoCard className={bentoMedium} delay={20} accentColor="var(--success)">
              <BentoHeader icon={UserIcon} title="Обязательный профиль" subtitle="Для персонализации" />
              <div className="grid grid-cols-2 gap-3">
                <div className="col-span-2">
                  <label className="block text-xs font-mono uppercase tracking-wider mb-1.5" style={{ color: "var(--text-muted)" }}>Пол</label>
                  <div className="grid grid-cols-3 gap-1.5">
                    {GENDERS.map((item) => (
                      <button key={item.key} type="button" onClick={() => setGender(item.key)}
                        className="rounded-lg px-2 py-2 text-xs transition-colors"
                        style={{
                          background: gender === item.key ? "var(--accent-muted)" : "var(--glass-bg)",
                          border: `1px solid ${gender === item.key ? "var(--accent)" : "var(--glass-border)"}`,
                          color: gender === item.key ? "var(--accent)" : "var(--text-secondary)",
                        }}
                      >{item.label}</button>
                    ))}
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-mono uppercase tracking-wider mb-1.5" style={{ color: "var(--text-muted)" }}>Должность</label>
                  <input type="text" value={roleTitle} onChange={(e) => setRoleTitle(e.target.value)} maxLength={120}
                    placeholder="Менеджер БФЛ" className="w-full rounded-lg px-3 py-2 text-sm outline-none"
                    style={{ background: "var(--glass-bg)", border: "1px solid var(--glass-border)", color: "var(--text-primary)" }} />
                </div>
                <div>
                  <label className="block text-xs font-mono uppercase tracking-wider mb-1.5" style={{ color: "var(--text-muted)" }}>Контакт</label>
                  <input type="text" value={primaryContact} onChange={(e) => setPrimaryContact(e.target.value)} maxLength={120}
                    placeholder="Telegram / Phone" className="w-full rounded-lg px-3 py-2 text-sm outline-none"
                    style={{ background: "var(--glass-bg)", border: "1px solid var(--glass-border)", color: "var(--text-primary)" }} />
                </div>
              </div>
            </BentoCard>

            {/* Training - Medium card */}
            <BentoCard className={bentoMedium} delay={30} accentColor="var(--success)">
              <BentoHeader icon={GameController} title="Тренировки" subtitle="Режим и сложность" />
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <SpeakerHigh weight="duotone" size={16} style={{ color: "var(--text-muted)" }} />
                    <span className="text-sm" style={{ color: "var(--text-secondary)" }}>Озвучка AI</span>
                  </div>
                  <Toggle on={ttsEnabled} onChange={() => setTtsEnabled(!ttsEnabled)} size="sm" />
                </div>
                <div>
                  <span className="text-xs block mb-2" style={{ color: "var(--text-muted)" }}>Режим</span>
                  <div className="flex flex-wrap gap-1.5">
                    {TRAINING_MODES.map((m) => (
                      <Chip key={m.key} active={trainingMode === m.key} label={m.label} onClick={() => setTrainingMode(m.key)} />
                    ))}
                  </div>
                </div>
                <div>
                  <span className="text-xs block mb-2" style={{ color: "var(--text-muted)" }}>Уровень</span>
                  <div className="flex gap-1.5">
                    {EXPERIENCE_LEVELS.map((l) => (
                      <Chip key={l.key} active={experienceLevel === l.key} label={l.label} onClick={() => setExperienceLevel(l.key)} />
                    ))}
                  </div>
                </div>
              </div>
            </BentoCard>

            {/* Appearance - Medium card */}
            <BentoCard className={bentoMedium} delay={40} accentColor="var(--info)">
              <BentoHeader icon={Palette} title="Оформление" subtitle="Тема и акцент" />
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-sm" style={{ color: "var(--text-secondary)" }}>Тема</span>
                  {mounted && (
                    <div className="flex gap-1.5">
                      {([{ key: "dark", label: "Тёмная" }, { key: "light", label: "Светлая" }, { key: "system", label: "Авто" }] as const).map((t) => (
                        <Chip key={t.key} active={theme === t.key} label={t.label} onClick={() => setTheme(t.key)} />
                      ))}
                    </div>
                  )}
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm" style={{ color: "var(--text-secondary)" }}>Акцент</span>
                  <div className="flex gap-1.5">
                    {ACCENT_COLORS.map((c) => (
                      <motion.button key={c.key} onClick={() => setAccentColor(c.key)}
                        className="w-7 h-7 rounded-full transition-all"
                        style={{
                          background: c.color,
                          boxShadow: accentColor === c.key ? `0 0 0 2px var(--bg-primary), 0 0 0 4px ${c.color}` : "none",
                          opacity: accentColor === c.key ? 1 : 0.6,
                        }}
                        whileHover={{ scale: 1.15 }} whileTap={{ scale: 0.9 }}
                        title={c.label} />
                    ))}
                  </div>
                </div>
                <div className="flex items-center justify-between pt-2" style={{ borderTop: "1px solid var(--border-color)" }}>
                  <span className="text-sm" style={{ color: "var(--text-secondary)" }}>Компактный</span>
                  <Toggle on={compactMode} onChange={() => setCompactMode(!compactMode)} size="sm" />
                </div>
              </div>
            </BentoCard>

            {/* Notifications - Medium card */}
            <BentoCard className={bentoMedium} delay={50} accentColor="var(--info)">
              <BentoHeader icon={Bell} title="Уведомления" subtitle="Каналы и частота" />
              <div className="space-y-2.5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <ChatCircle weight="duotone" size={14} style={{ color: "var(--text-muted)" }} />
                    <span className="text-xs" style={{ color: "var(--text-secondary)" }}>В приложении</span>
                  </div>
                  <Toggle on={notifyPush} onChange={() => setNotifyPush(!notifyPush)} size="sm" />
                </div>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Envelope weight="duotone" size={14} style={{ color: "var(--text-muted)" }} />
                    <span className="text-xs" style={{ color: "var(--text-secondary)" }}>Email</span>
                  </div>
                  <Toggle on={notifyEmail} onChange={() => setNotifyEmail(!notifyEmail)} size="sm" />
                </div>
                <div className="pt-2 mt-1" style={{ borderTop: "1px solid var(--border-color)" }}>
                  <span className="text-xs block mb-1.5" style={{ color: "var(--text-muted)" }}>Частота</span>
                  <div className="flex gap-1.5">
                    {([{ key: "realtime" as const, label: "Сразу" }, { key: "daily" as const, label: "День" }, { key: "weekly" as const, label: "Неделя" }] as const).map((f) => (
                      <Chip key={f.key} active={notifyFrequency === f.key} label={f.label} onClick={() => setNotifyFrequency(f.key)} />
                    ))}
                  </div>
                </div>
              </div>
            </BentoCard>

            {/* Linked Accounts - Small card */}
            <BentoCard className={bentoSmall} delay={60} accentColor="var(--magenta, #D926B8)">
              <BentoHeader icon={LinkSimple} title="Привязки" subtitle="Google / Yandex" />
              <div className="space-y-2">
                <div className="flex items-center justify-between rounded-lg p-2" style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)" }}>
                  <div className="flex items-center gap-2">
                    <svg width="16" height="16" viewBox="0 0 24 24"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/></svg>
                    <span className="text-xs" style={{ color: "var(--text-secondary)" }}>Google</span>
                  </div>
                  {linkedGoogle ? (
                    <motion.button onClick={async () => { setUnlinking("google"); try { await api.post("/auth/google/disconnect", {}); setLinkedGoogle(false); } catch {} setUnlinking(null); }}
                    disabled={unlinking === "google"} className="text-xs px-2 py-1 rounded" style={{ background: "var(--danger-muted)", color: "var(--danger)" }} whileTap={{ scale: 0.95 }}>
                    {unlinking === "google" ? <Loader2 size={10} className="animate-spin" /> : "Отвязать"}
                    </motion.button>
                  ) : oauthStatus.google ? (
                    <motion.button onClick={async () => { try { const d = await api.get("/auth/google/login"); if (d?.url) { const { validateOAuthUrl } = await import("@/lib/sanitize"); const safeUrl = validateOAuthUrl(d.url); if (safeUrl) window.location.href = safeUrl; } } catch {} }}
                    className="text-xs px-2 py-1 rounded" style={{ background: "var(--accent-muted)", color: "var(--accent)" }} whileTap={{ scale: 0.95 }}>
                    Привязать
                    </motion.button>
                  ) : <span className="text-xs" style={{ color: "var(--text-muted)" }}>—</span>}
                </div>
                <div className="flex items-center justify-between rounded-lg p-2" style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)" }}>
                  <div className="flex items-center gap-2">
                    <svg width="16" height="16" viewBox="0 0 24 24"><path d="M2 12C2 6.48 6.48 2 12 2s10 4.48 10 10-4.48 10-10 10S2 17.52 2 12z" fill="#FC3F1D"/><path d="M13.32 17.5h-1.88V7.38h-.97c-1.57 0-2.39.8-2.39 1.95 0 1.3.59 1.9 1.8 2.7l1 .65-2.9 4.82H6l2.62-4.33C7.37 12.26 6.56 11.22 6.56 9.5c0-2.07 1.45-3.5 4-3.5h2.76V17.5z" fill="white"/></svg>
                    <span className="text-xs" style={{ color: "var(--text-secondary)" }}>Yandex</span>
                  </div>
                  {linkedYandex ? (
                    <motion.button onClick={async () => { setUnlinking("yandex"); try { await api.post("/auth/yandex/disconnect", {}); setLinkedYandex(false); } catch {} setUnlinking(null); }}
                    disabled={unlinking === "yandex"} className="text-xs px-2 py-1 rounded" style={{ background: "var(--danger-muted)", color: "var(--danger)" }} whileTap={{ scale: 0.95 }}>
                    {unlinking === "yandex" ? <Loader2 size={10} className="animate-spin" /> : "Отвязать"}
                    </motion.button>
                  ) : oauthStatus.yandex ? (
                    <motion.button onClick={async () => { try { const d = await api.get("/auth/yandex/login"); if (d?.url) { const { validateOAuthUrl } = await import("@/lib/sanitize"); const safeUrl = validateOAuthUrl(d.url); if (safeUrl) window.location.href = safeUrl; } } catch {} }}
                    className="text-xs px-2 py-1 rounded" style={{ background: "var(--accent-muted)", color: "var(--accent)" }} whileTap={{ scale: 0.95 }}>
                    Привязать
                    </motion.button>
                  ) : <span className="text-xs" style={{ color: "var(--text-muted)" }}>—</span>}
                </div>
              </div>
            </BentoCard>

            {/* Pipeline - Show only for CRM roles */}
            {showCRM && (
              <BentoCard className={bentoLarge} delay={70} accentColor="var(--warning)">
                <BentoHeader icon={Kanban} title="Воронка" subtitle="Столбцы в канбане" />
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                  {PIPELINE_STATUSES.map((status) => {
                    const on = pipelineColumns.includes(status);
                    const statusColor = CLIENT_STATUS_COLORS[status as ClientStatus] || "var(--text-muted)";
                    return (
                      <motion.button key={status} onClick={() => { if (on && pipelineColumns.length <= 2) return; setPipelineColumns(on ? pipelineColumns.filter((s) => s !== status) : [...pipelineColumns, status]); }}
                        className="flex items-center gap-2 rounded-lg px-3 py-2.5 text-xs font-mono transition-all text-left"
                        style={{
                          background: on ? `${statusColor}12` : "var(--input-bg)",
                          border: `1px solid ${on ? `${statusColor}40` : "var(--border-color)"}`,
                          color: on ? statusColor : "var(--text-muted)",
                        }}
                        whileTap={{ scale: 0.97 }}
                      >
                        <div className="w-2 h-2 rounded-full" style={{ background: statusColor, opacity: on ? 1 : 0.3 }} />
                        {CLIENT_STATUS_LABELS[status as ClientStatus]}
                      </motion.button>
                    );
                  })}
                </div>
              </BentoCard>
            )}

          </div>

          {/* Save button - Fixed at bottom */}
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 80 * 0.05 }} className="sticky bottom-4 flex justify-end gap-3 pt-4 mt-4" style={{ background: "linear-gradient(transparent, var(--bg-primary) 50%)" }}>
            {saveError && <p className="text-sm font-mono" style={{ color: "var(--danger)" }}>{saveError}</p>}
            <Button onClick={handleSave} loading={saving} icon={saved ? <CheckCircle2 size={16} /> : <Save size={16} />} className="shadow-lg">
              {saved ? "Сохранено" : "Сохранить"}
            </Button>
          </motion.div>
        </div>
      </div>
    </AuthLayout>
  );
}
