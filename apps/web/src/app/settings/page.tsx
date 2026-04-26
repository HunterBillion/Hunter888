"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Save, Loader2, CheckCircle2, Check,
} from "lucide-react";
import {
  Gear, SpeakerHigh, Bell, Palette, Envelope, ChatCircle,
  GameController, Kanban, LinkSimple, Lightning, Flame, User as UserIcon,
} from "@phosphor-icons/react";
import { useTheme } from "next-themes";
import { api } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { useGamificationStore } from "@/stores/useGamificationStore";
import { useAuthStore } from "@/stores/useAuthStore";
import AuthLayout from "@/components/layout/AuthLayout";
import { BackButton } from "@/components/ui/BackButton";
import { Button } from "@/components/ui/Button";
import { AvatarUpload } from "@/components/settings/AvatarUpload";
import { PIPELINE_STATUSES, CLIENT_STATUS_LABELS, CLIENT_STATUS_COLORS } from "@/types";
import type { ClientStatus } from "@/types";
import { logger } from "@/lib/logger";

function invalidateUserCache() {
  useAuthStore.getState().invalidate();
  void useAuthStore.getState().fetchUser();
}

const roleLabels: Record<string, string> = {
  manager: "Менеджер",
  rop: "Руководитель ОП",
  methodologist: "РОП",  // legacy enum — retired 2026-04-26, displays as ROP for stale tokens
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

const NOTIFY_FREQUENCIES = [
  { key: "realtime", label: "Сразу" },
  { key: "daily", label: "Раз в день" },
  { key: "weekly", label: "Раз в неделю" },
] as const;

function Toggle({ on, onChange, size = "md", label }: { on: boolean; onChange: () => void; size?: "sm" | "md"; label?: string }) {
  const w = size === "sm" ? "w-10 h-5" : "w-12 h-6";
  const dot = "w-4 h-4";
  const left = size === "sm" ? (on ? 22 : 2) : (on ? 28 : 4);
  const top = size === "sm" ? "top-0.5" : "top-1";
  return (
    <label className="flex items-center gap-3 cursor-pointer">
      {label && <span className="text-sm" style={{ color: "var(--text-secondary)" }}>{label}</span>}
      <motion.button
        type="button"
        onClick={onChange}
        className={`relative ${w} rounded-full transition-colors shrink-0`}
        style={{ background: on ? "var(--accent)" : "var(--border-color)" }}
        whileTap={{ scale: 0.95 }}
      >
        <motion.div
          className={`absolute ${top} ${dot} rounded-full bg-white`}
          animate={{ left }}
          transition={{ type: "spring", stiffness: 500, damping: 30 }}
        />
      </motion.button>
    </label>
  );
}

function Chip({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <motion.button
      type="button"
      onClick={onClick}
      className="rounded-lg px-3 py-2 text-sm font-medium transition-all"
      style={{
        background: active ? "var(--accent)" : "var(--input-bg)",
        border: `1px solid ${active ? "var(--accent)" : "var(--border-color)"}`,
        color: active ? "white" : "var(--text-secondary)",
      }}
      whileTap={{ scale: 0.95 }}
    >
      {label}
    </motion.button>
  );
}

function Section({ icon, title, description, children }: { icon: React.ComponentType<{ weight?: "duotone" | "regular" | "fill" | "bold"; size?: number; style?: React.CSSProperties }>; title: string; description?: string; children: React.ReactNode }) {
  const IconComponent = icon;
  return (
    <motion.section
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="mb-8"
    >
      <div className="flex items-center gap-2 mb-4">
        <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: "var(--accent-muted)" }}>
          <IconComponent weight="duotone" size={18} style={{ color: "var(--accent)" }} />
        </div>
        <div>
          <h2 className="text-lg font-semibold" style={{ color: "var(--text-primary)" }}>{title}</h2>
          {description && <p className="text-xs" style={{ color: "var(--text-muted)" }}>{description}</p>}
        </div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {children}
      </div>
    </motion.section>
  );
}

function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`glass-panel p-4 rounded-xl ${className}`}>
      {children}
    </div>
  );
}

export default function SettingsPage() {
  const { user } = useAuth();
  const { theme, setTheme } = useTheme();
  const mountedRef = useRef(false);
  const saveTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const [ttsEnabled, setTtsEnabled] = useState(true);
  const [notifyEmail, setNotifyEmail] = useState(false);
  const [notifyPush, setNotifyPush] = useState(true);
  const [notifyFrequency, setNotifyFrequency] = useState<"realtime" | "daily" | "weekly">("realtime");
  const [trainingMode, setTrainingMode] = useState<string>("mixed");
  const [experienceLevel, setExperienceLevel] = useState<string>("beginner");
  const [gender, setGender] = useState<string>("");
  const [roleTitle, setRoleTitle] = useState<string>("");
  const [primaryContact, setPrimaryContact] = useState<string>("");
  const [specialization, setSpecialization] = useState<string>("");
  const [pipelineColumns, setPipelineColumns] = useState<string[]>(PIPELINE_STATUSES as string[]);
  const [compactMode, setCompactMode] = useState(false);
  const [accentColor, setAccentColor] = useState<string>("violet");

  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [fullName, setFullName] = useState<string>("");
  const [fullNameSaving, setFullNameSaving] = useState(false);
  const [fullNameSaved, setFullNameSaved] = useState(false);
  const [fullNameError, setFullNameError] = useState<string | null>(null);
  const [avatarUrl, setAvatarUrl] = useState<string | null>(null);

  const [oauthStatus, setOauthStatus] = useState<{ google: boolean; yandex: boolean }>({ google: false, yandex: false });
  const [linkedGoogle, setLinkedGoogle] = useState(false);
  const [linkedYandex, setLinkedYandex] = useState(false);
  const [unlinking, setUnlinking] = useState<string | null>(null);

  const showCRM = user?.role && ["admin", "rop", "manager"].includes(user.role);
  const { level, streak, fetchProgress } = useGamificationStore();

  useEffect(() => { mountedRef.current = true; }, []);

  useEffect(() => {
    if (!user) return;
    if (user.avatar_url) setAvatarUrl(user.avatar_url);
    if (user.full_name) setFullName(user.full_name);
    const p = (user.preferences as Record<string, unknown>) || {};
    if (typeof p.tts_enabled === "boolean") setTtsEnabled(p.tts_enabled);
    if (typeof p.notify_email === "boolean") setNotifyEmail(p.notify_email);
    if (typeof p.notify_push === "boolean") setNotifyPush(p.notify_push);
    if (typeof p.notify_frequency === "string") setNotifyFrequency(p.notify_frequency as "realtime" | "daily" | "weekly");
    if (typeof p.training_mode === "string") setTrainingMode(p.training_mode);
    if (typeof p.experience_level === "string") setExperienceLevel(p.experience_level);
    if (typeof p.gender === "string") setGender(p.gender);
    if (typeof p.role_title === "string") setRoleTitle(p.role_title);
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

  useEffect(() => {
    if (!mountedRef.current) return;
    const html = document.documentElement;
    ACCENT_COLORS.forEach((c) => html.classList.remove(`accent-${c.key}`));
    if (accentColor && accentColor !== "violet") {
      html.classList.add(`accent-${accentColor}`);
    }
  }, [accentColor]);

  useEffect(() => {
    if (!mountedRef.current) return;
    document.body.classList.toggle("compact-mode", compactMode);
  }, [compactMode]);

  useEffect(() => { fetchProgress(); }, [fetchProgress]);

const triggerAutosave = useCallback(async () => {
    if (!mountedRef.current || !user) return;
    setSaving(true);
    try {
      // Backend rejects blank/short strings on gender/role_title/primary_contact
      // (Pydantic pattern + min_length). Drop fields the user hasn't filled yet
      // so autosave doesn't 422-spam while they're still typing.
      const trimmedRoleTitle = roleTitle.trim();
      const trimmedContact = primaryContact.trim();
      const prefs: Record<string, unknown> = {
        tts_enabled: ttsEnabled,
        notify_email: notifyEmail,
        notify_push: notifyPush,
        notify_frequency: notifyFrequency,
        training_mode: trainingMode,
        experience_level: experienceLevel,
        pipeline_columns: pipelineColumns,
        compact_mode: compactMode,
        accent_color: accentColor,
      };
      if (gender) prefs.gender = gender;
      if (trimmedRoleTitle.length >= 2) prefs.role_title = trimmedRoleTitle;
      if (trimmedContact.length >= 3) prefs.primary_contact = trimmedContact;
      if (specialization) prefs.specialization = specialization;
      await api.post("/users/me/preferences", prefs);
      useAuthStore.getState().updatePreferences(prefs);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      logger.error("Autosave failed:", e);
    }
    setSaving(false);
  }, [ttsEnabled, gender, roleTitle, primaryContact, specialization, notifyEmail, notifyPush, notifyFrequency, trainingMode, experienceLevel, pipelineColumns, compactMode, accentColor, user]);

  useEffect(() => {
    if (!mountedRef.current || !user) return;
    if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);
    const timeout = setTimeout(() => {
      triggerAutosave();
    }, 1500);
    saveTimeoutRef.current = timeout;
    return () => { if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current); };
  }, [ttsEnabled, gender, roleTitle, primaryContact, specialization, notifyEmail, notifyPush, notifyFrequency, trainingMode, experienceLevel, pipelineColumns, compactMode, accentColor, triggerAutosave]);

  const handleSaveName = async () => {
    const trimmed = fullName.trim();
    if (!trimmed || trimmed.length < 2) {
      setFullNameError("Имя должно содержать минимум 2 символа");
      return;
    }
    if (trimmed === user?.full_name) return;
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

  return (
    <AuthLayout>
      <div className="relative panel-grid-bg min-h-screen">
        <div className="app-page max-w-4xl mx-auto">
          <BackButton href="/home" label="На главную" />

          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
            className="relative flex items-center gap-4 mb-8 rounded-2xl p-5"
            style={{
              background: "linear-gradient(135deg, var(--glass-bg), var(--accent-muted))",
              border: "1px solid var(--accent-muted)",
            }}
          >
            <AvatarUpload
              currentUrl={avatarUrl}
              userName={user?.full_name || ""}
              size={56}
              onUploaded={(url) => { setAvatarUrl(url); invalidateUserCache(); }}
              onDeleted={() => { setAvatarUrl(null); invalidateUserCache(); }}
            />
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <Gear weight="duotone" size={22} style={{ color: "var(--accent)" }} />
                <h1 className="font-display text-xl font-bold tracking-widest" style={{ color: "var(--text-primary)" }}>
                  НАСТРОЙКИ
                </h1>
              </div>
              <div className="flex items-center gap-3 mt-1.5 flex-wrap">
                <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium" style={{ background: "var(--accent-muted)", color: "var(--accent)" }}>
                  {roleLabels[user?.role || ""] || user?.role || ""}
                </span>
                <span className="inline-flex items-center gap-1 text-xs font-mono" style={{ color: "var(--accent)" }}>
                  <Lightning weight="duotone" size={12} /> Lv.{level}
                </span>
                {streak > 0 && (
                  <span className="inline-flex items-center gap-1 text-xs font-mono" style={{ color: "var(--streak-color, var(--warning))" }}>
                    <Flame weight="duotone" size={12} /> {streak}д
                  </span>
                )}
              </div>
            </div>
            <div className="text-right shrink-0">
              <AnimatePresence mode="wait">
                {saving ? (
                  <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex items-center gap-2 text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                    <Loader2 size={12} className="animate-spin" />
                    Сохранение...
                  </motion.div>
                ) : saved ? (
                  <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex items-center gap-1 text-xs font-mono" style={{ color: "var(--success)" }}>
                    <Check size={12} />
                    Сохранено
                  </motion.div>
                ) : null}
              </AnimatePresence>
            </div>
          </motion.div>

          <Section icon={UserIcon} title="Профиль" description="Ваши личные данные">
            <Card className="md:col-span-2">
              <div className="flex gap-3 items-center">
                <input
                  type="text"
                  value={fullName}
                  onChange={(e) => { setFullName(e.target.value); setFullNameError(null); setFullNameSaved(false); }}
                  onKeyDown={(e) => { if (e.key === "Enter") handleSaveName(); }}
                  maxLength={100}
                  placeholder="Ваше имя"
                  disabled={fullNameSaving}
                  className="flex-1 rounded-lg px-4 py-2.5 text-base outline-none transition-colors"
                  style={{
                    background: "var(--input-bg)",
                    border: `1px solid ${fullNameError ? "var(--danger)" : "var(--border-color)"}`,
                    color: "var(--text-primary)",
                  }}
                />
                <Button onClick={handleSaveName} disabled={fullNameSaving || !fullName.trim() || fullName.trim() === user?.full_name} size="sm">
                  {fullNameSaving ? <Loader2 size={14} className="animate-spin" /> : fullNameSaved ? <Check size={14} /> : <Save size={14} />}
                </Button>
              </div>
              {fullNameError && <p className="text-xs mt-2" style={{ color: "var(--danger)" }}>{fullNameError}</p>}
              <p className="text-xs mt-2" style={{ color: "var(--text-muted)" }}>
                Email: {user?.email}
              </p>
            </Card>

            <Card>
              <label className="text-xs font-medium uppercase tracking-wide mb-3 block" style={{ color: "var(--text-muted)" }}>Пол</label>
              <div className="grid grid-cols-3 gap-2">
                {GENDERS.map((item) => (
                  <button key={item.key} type="button" onClick={() => setGender(item.key)}
                    className="rounded-lg py-2.5 text-sm font-medium transition-all"
                    style={{
                      background: gender === item.key ? "var(--accent)" : "var(--input-bg)",
                      border: `1px solid ${gender === item.key ? "var(--accent)" : "var(--border-color)"}`,
                      color: gender === item.key ? "white" : "var(--text-secondary)",
                    }}
                  >{item.label}</button>
                ))}
              </div>
            </Card>

            <Card>
              <label className="text-xs font-medium uppercase tracking-wide mb-3 block" style={{ color: "var(--text-muted)" }}>Должность</label>
              <input type="text" value={roleTitle} onChange={(e) => setRoleTitle(e.target.value)} maxLength={120}
                placeholder="Менеджер"
                className="w-full rounded-lg px-3 py-2.5 text-sm outline-none"
                style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)", color: "var(--text-primary)" }} />
            </Card>

            <Card>
              <label className="text-xs font-medium uppercase tracking-wide mb-3 block" style={{ color: "var(--text-muted)" }}>Контакт</label>
              <input type="text" value={primaryContact} onChange={(e) => setPrimaryContact(e.target.value)} maxLength={120}
                placeholder="Telegram / Phone"
                className="w-full rounded-lg px-3 py-2.5 text-sm outline-none"
                style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)", color: "var(--text-primary)" }} />
            </Card>

            <Card>
              <label className="text-xs font-medium uppercase tracking-wide mb-3 block" style={{ color: "var(--text-muted)" }}>Специализация</label>
              <input type="text" value={specialization} onChange={(e) => setSpecialization(e.target.value)} maxLength={120}
                placeholder="HR, Продажи..."
                className="w-full rounded-lg px-3 py-2.5 text-sm outline-none"
                style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)", color: "var(--text-primary)" }} />
            </Card>
          </Section>

          <Section icon={GameController} title="Продукт" description="Тренировки и опыт">
            <Card className="md:col-span-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <SpeakerHigh weight="duotone" size={20} style={{ color: "var(--accent)" }} />
                  <span className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>Озвучка AI</span>
                </div>
                <Toggle on={ttsEnabled} onChange={() => setTtsEnabled(!ttsEnabled)} size="sm" />
              </div>
            </Card>

            <Card className="md:col-span-2">
              <label className="text-xs font-medium uppercase tracking-wide mb-3 block" style={{ color: "var(--text-muted)" }}>Режим тренировки</label>
              <div className="flex flex-wrap gap-2">
                {TRAINING_MODES.map((m) => (
                  <Chip key={m.key} active={trainingMode === m.key} label={m.label} onClick={() => setTrainingMode(m.key)} />
                ))}
              </div>
            </Card>

            <Card className="md:col-span-2">
              <label className="text-xs font-medium uppercase tracking-wide mb-3 block" style={{ color: "var(--text-muted)" }}>Уровень сложности</label>
              <div className="flex gap-2">
                {EXPERIENCE_LEVELS.map((l) => (
                  <Chip key={l.key} active={experienceLevel === l.key} label={l.label} onClick={() => setExperienceLevel(l.key)} />
                ))}
              </div>
            </Card>
          </Section>

          <Section icon={Bell} title="Система" description="Оформление и уведомления">
            <Card>
              <label className="text-xs font-medium uppercase tracking-wide mb-3 block" style={{ color: "var(--text-muted)" }}>Тема</label>
              {mountedRef.current && (
                <div className="flex gap-2">
                  {([{ key: "dark", label: "Тёмная" }, { key: "light", label: "Светлая" }, { key: "system", label: "Авто" }] as const).map((t) => (
                    <Chip key={t.key} active={theme === t.key} label={t.label} onClick={() => setTheme(t.key)} />
                  ))}
                </div>
              )}
            </Card>

            <Card>
              <label className="text-xs font-medium uppercase tracking-wide mb-3 block" style={{ color: "var(--text-muted)" }}>Акцент</label>
              <div className="flex gap-2">
                {ACCENT_COLORS.map((c) => (
                  <motion.button key={c.key} type="button" onClick={() => setAccentColor(c.key)}
                    className="w-8 h-8 rounded-full transition-all"
                    style={{
                      background: c.color,
                      boxShadow: accentColor === c.key ? `0 0 0 3px var(--bg-primary), 0 0 0 5px ${c.color}` : "none",
                    }}
                    whileHover={{ scale: 1.1 }} whileTap={{ scale: 0.9 }}
                    title={c.label} />
                ))}
              </div>
            </Card>

            <Card className="md:col-span-2">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>Компактный режим</span>
                <Toggle on={compactMode} onChange={() => setCompactMode(!compactMode)} size="sm" />
              </div>
            </Card>

            <Card>
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <ChatCircle weight="duotone" size={16} style={{ color: "var(--accent)" }} />
                  <span className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>В приложении</span>
                </div>
                <Toggle on={notifyPush} onChange={() => setNotifyPush(!notifyPush)} size="sm" />
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Envelope weight="duotone" size={16} style={{ color: "var(--accent)" }} />
                  <span className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>Email</span>
                </div>
                <Toggle on={notifyEmail} onChange={() => setNotifyEmail(!notifyEmail)} size="sm" />
              </div>
            </Card>

            <Card>
              <label className="text-xs font-medium uppercase tracking-wide mb-3 block" style={{ color: "var(--text-muted)" }}>Частота уведомлений</label>
              <div className="flex flex-wrap gap-2">
                {NOTIFY_FREQUENCIES.map((f) => (
                  <Chip key={f.key} active={notifyFrequency === f.key} label={f.label} onClick={() => setNotifyFrequency(f.key as "realtime" | "daily" | "weekly")} />
                ))}
              </div>
            </Card>

            <Card>
              <label className="text-xs font-medium uppercase tracking-wide mb-3 block" style={{ color: "var(--text-muted)" }}>Привязанные аккаунты</label>
              <div className="space-y-2">
                <div className="flex items-center justify-between rounded-lg px-3 py-2" style={{ background: "var(--input-bg)" }}>
                  <div className="flex items-center gap-2">
                    <svg width="16" height="16" viewBox="0 0 24 24"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/></svg>
                    <span className="text-sm" style={{ color: "var(--text-secondary)" }}>Google</span>
                  </div>
                  {linkedGoogle ? (
                    <button onClick={async () => { setUnlinking("google"); try { await api.post("/auth/google/disconnect", {}); setLinkedGoogle(false); } catch {} setUnlinking(null); }}
                    disabled={unlinking === "google"} className="text-xs px-2.5 py-1 rounded-lg" style={{ background: "var(--danger-muted)", color: "var(--danger)" }}>
                    {unlinking === "google" ? <Loader2 size={10} className="animate-spin" /> : "Отвязать"}
                    </button>
                  ) : oauthStatus.google ? (
                    <button onClick={async () => { try { const d = await api.get("/auth/google/login"); if (d?.url) { const { validateOAuthUrl } = await import("@/lib/sanitize"); const safeUrl = validateOAuthUrl(d.url); if (safeUrl) window.location.href = safeUrl; } } catch {} }}
                    className="text-xs px-2.5 py-1 rounded-lg" style={{ background: "var(--accent-muted)", color: "var(--accent)" }}>
                    Привязать
                    </button>
                  ) : <span className="text-xs" style={{ color: "var(--text-muted)" }}>—</span>}
                </div>
                <div className="flex items-center justify-between rounded-lg px-3 py-2" style={{ background: "var(--input-bg)" }}>
                  <div className="flex items-center gap-2">
                    <svg width="16" height="16" viewBox="0 0 24 24"><path d="M2 12C2 6.48 6.48 2 12 2s10 4.48 10 10-4.48 10-10 10S2 17.52 2 12z" fill="#FC3F1D"/><path d="M13.32 17.5h-1.88V7.38h-.97c-1.57 0-2.39.8-2.39 1.95 0 1.3.59 1.9 1.8 2.7l1 .65-2.9 4.82H6l2.62-4.33C7.37 12.26 6.56 11.22 6.56 9.5c0-2.07 1.45-3.5 4-3.5h2.76V17.5z" fill="white"/></svg>
                    <span className="text-sm" style={{ color: "var(--text-secondary)" }}>Yandex</span>
                  </div>
                  {linkedYandex ? (
                    <button onClick={async () => { setUnlinking("yandex"); try { await api.post("/auth/yandex/disconnect", {}); setLinkedYandex(false); } catch {} setUnlinking(null); }}
                    disabled={unlinking === "yandex"} className="text-xs px-2.5 py-1 rounded-lg" style={{ background: "var(--danger-muted)", color: "var(--danger)" }}>
                    {unlinking === "yandex" ? <Loader2 size={10} className="animate-spin" /> : "Отвязать"}
                    </button>
                  ) : oauthStatus.yandex ? (
                    <button onClick={async () => { try { const d = await api.get("/auth/yandex/login"); if (d?.url) { const { validateOAuthUrl } = await import("@/lib/sanitize"); const safeUrl = validateOAuthUrl(d.url); if (safeUrl) window.location.href = safeUrl; } } catch {} }}
                    className="text-xs px-2.5 py-1 rounded-lg" style={{ background: "var(--accent-muted)", color: "var(--accent)" }}>
                    Привязать
                    </button>
                  ) : <span className="text-xs" style={{ color: "var(--text-muted)" }}>—</span>}
                </div>
              </div>
            </Card>
          </Section>

          {showCRM && (
            <Section icon={Kanban} title="Воронка" description="Столбцы канбана">
              <Card className="md:col-span-2">
                <label className="text-xs font-medium uppercase tracking-wide mb-3 block" style={{ color: "var(--text-muted)" }}>Активные этапы</label>
                <div className="flex flex-wrap gap-2">
                  {PIPELINE_STATUSES.map((status) => {
                    const on = pipelineColumns.includes(status);
                    const statusColor = CLIENT_STATUS_COLORS[status as ClientStatus] || "var(--text-muted)";
                    return (
                      <button key={status} type="button" onClick={() => { if (on && pipelineColumns.length <= 2) return; setPipelineColumns(on ? pipelineColumns.filter((s) => s !== status) : [...pipelineColumns, status]); }}
                        disabled={on && pipelineColumns.length <= 2}
                        className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-all"
                        style={{
                          background: on ? `${statusColor}20` : "var(--input-bg)",
                          border: `1px solid ${on ? statusColor : "var(--border-color)"}`,
                          color: on ? statusColor : "var(--text-secondary)",
                          opacity: on ? 1 : 0.7,
                        }}
                      >
                        <span className="w-2 h-2 rounded-full" style={{ background: statusColor }} />
                        {CLIENT_STATUS_LABELS[status as ClientStatus]}
                      </button>
                    );
                  })}
                </div>
                <p className="text-xs mt-3" style={{ color: "var(--text-muted)" }}>
                  Минимум 2 этапа • Переключите, чтобы скрыть
                </p>
              </Card>
            </Section>
          )}
        </div>
      </div>
    </AuthLayout>
  );
}