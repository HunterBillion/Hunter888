"use client";

/**
 * /settings — «⚙ НАСТРОЙКИ ⚙» (аркадный редизайн 2026-05-08).
 *
 * Что изменилось vs прошлой версии:
 *   - убран glass-panel header — заменён пиксельным сяющим лого
 *     «⚙ НАСТРОЙКИ ⚙» (тот же эффект что на /leaderboard и /profile,
 *     но с серебряно-голубым градиентом для UI-«пульта»).
 *   - autosave-индикатор теперь пиксельный плашка справа
 *   - 6 секций (Игрок · Тренировка · Звук · Внешний вид · Уведомления ·
 *     Связки) + опциональная Воронка для CRM-ролей
 *   - каждая секция в `<SettingsSection accent={...}>` с цветной рамкой
 *     и заголовком-плашкой слева сверху (симметрично /profile)
 *   - все Toggle/Chip/input получили пиксельный стиль (2-3px borders,
 *     square corners, neon glow при active)
 *   - все шрифты ≥ 14px (font-pixel uppercase tracking-widest для
 *     лейблов, font-medium 14-16px для текста)
 *
 * НЕ ТРОГАЛ:
 *   - всю логику сохранения (autosave, password, OAuth, avatar upload)
 *   - все 18 preferences keys
 *   - SoundSettings, AudioDevicesPanel, AvatarUpload (они уже пиксельные)
 *   - API-вызовы и payload'ы
 */

import { useState, useEffect, useCallback, useRef, type ReactNode } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Save, Loader2, Check, type LucideIcon,
} from "lucide-react";
import {
  Gear, SpeakerHigh, Bell, Envelope, ChatCircle,
  GameController, Kanban, User as UserIcon, Palette, LinkSimple, Lightning, Flame,
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
import { SoundSettings } from "@/components/settings/SoundSettings";
import { AudioDevicesPanel } from "@/components/settings/AudioDevicesPanel";
import { readCRTMode, writeCRTMode } from "@/components/leaderboard/CRTOverlay";
import { toast } from "sonner";
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

const THEMES = [
  { key: "dark", label: "Тёмная" },
  { key: "light", label: "Светлая" },
  { key: "system", label: "Авто" },
] as const;

/* ═══ Pixel Toggle ═══════════════════════════════════════════════════════ */

function PixelToggle({
  on,
  onChange,
  accent = "var(--accent)",
}: {
  on: boolean;
  onChange: () => void;
  accent?: string;
}) {
  return (
    <motion.button
      type="button"
      onClick={onChange}
      whileTap={{ scale: 0.95 }}
      aria-pressed={on}
      className="relative shrink-0 rounded-sm transition-colors"
      style={{
        width: 48,
        height: 24,
        background: on ? accent : "rgba(0,0,0,0.45)",
        border: `2px solid ${on ? accent : "rgba(255,255,255,0.18)"}`,
        boxShadow: on ? `0 0 10px ${accent}` : "inset 0 0 4px rgba(0,0,0,0.5)",
      }}
    >
      <motion.div
        className="absolute top-0.5 rounded-sm"
        animate={{ left: on ? 26 : 2 }}
        transition={{ type: "spring", stiffness: 500, damping: 30 }}
        style={{
          width: 16,
          height: 16,
          background: on ? "#0b0b14" : "#fff",
        }}
      />
    </motion.button>
  );
}

/* ═══ Pixel Chip ═════════════════════════════════════════════════════════ */

function PixelChip({
  active,
  label,
  onClick,
  accent = "var(--accent)",
  disabled = false,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
  accent?: string;
  disabled?: boolean;
}) {
  return (
    <motion.button
      type="button"
      onClick={onClick}
      disabled={disabled}
      whileHover={!disabled ? { scale: 1.03 } : {}}
      whileTap={!disabled ? { scale: 0.97 } : {}}
      className="rounded-sm font-pixel uppercase tracking-widest transition-all"
      style={{
        padding: "8px 14px",
        fontSize: 14,
        background: active ? accent : "rgba(255,255,255,0.04)",
        border: `2px solid ${active ? accent : "rgba(255,255,255,0.18)"}`,
        color: active ? "#0b0b14" : "var(--text-secondary)",
        boxShadow: active ? `0 0 10px ${accent}` : "none",
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.5 : 1,
      }}
    >
      {label}
    </motion.button>
  );
}

/* ═══ Pixel Input ════════════════════════════════════════════════════════ */

function PixelInput({
  value,
  onChange,
  placeholder,
  maxLength = 120,
  type = "text",
  disabled = false,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  maxLength?: number;
  type?: string;
  disabled?: boolean;
}) {
  return (
    <input
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      maxLength={maxLength}
      disabled={disabled}
      className="w-full rounded-sm outline-none transition-colors"
      style={{
        padding: "10px 14px",
        fontSize: 14,
        background: "rgba(0,0,0,0.45)",
        border: "2px solid rgba(255,255,255,0.18)",
        color: "var(--text-primary)",
      }}
    />
  );
}

/* ═══ SettingsSection — пиксельная рамка для каждой секции ══════════════ */

function SettingsSection({
  children,
  accent,
  title,
  icon: Icon,
  description,
  mt,
}: {
  children: ReactNode;
  accent: string;
  title: string;
  icon: LucideIcon | React.ComponentType<{ size?: number; weight?: "duotone" | "regular" | "fill" | "bold"; style?: React.CSSProperties }>;
  description?: string;
  mt?: number;
}) {
  return (
    <section
      className="relative rounded-sm"
      style={{
        marginTop: mt ?? 32,
        border: `2px solid ${accent}33`,
        background: "rgba(8,5,18,0.45)",
        boxShadow: "inset 0 0 24px rgba(0,0,0,0.35)",
      }}
    >
      {/* Заголовок-плашка */}
      <div
        className="absolute -top-3 left-4 px-2.5 py-0.5 font-pixel uppercase tracking-widest inline-flex items-center gap-2 rounded-sm"
        style={{
          background: "var(--bg-primary, #0b0b14)",
          color: accent,
          fontSize: 14,
          letterSpacing: "0.18em",
          border: `2px solid ${accent}`,
        }}
      >
        <Icon size={14} weight="duotone" style={{ color: accent }} />
        {title}
      </div>

      <div className="p-4 md:p-5 pt-7">
        {description && (
          <p
            className="mb-4 font-pixel uppercase tracking-widest"
            style={{ color: "var(--text-muted)", fontSize: 14 }}
          >
            {description}
          </p>
        )}
        {children}
      </div>
    </section>
  );
}

/* ═══ Internal pixel «card» внутри секций ═══════════════════════════════ */

function SettingsCard({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={`rounded-sm p-4 ${className}`}
      style={{
        background: "rgba(0,0,0,0.35)",
        border: "1px solid rgba(255,255,255,0.08)",
      }}
    >
      {children}
    </div>
  );
}

function SettingsLabel({ children }: { children: ReactNode }) {
  return (
    <div
      className="font-pixel uppercase tracking-widest mb-2.5"
      style={{ color: "var(--text-muted)", fontSize: 14 }}
    >
      {children}
    </div>
  );
}

/* ═══ Main page ══════════════════════════════════════════════════════════ */

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
  const [crtMode, setCrtModeState] = useState<"off" | "leaderboard" | "global">("leaderboard");
  useEffect(() => { setCrtModeState(readCRTMode()); }, []);

  const [micDeviceId, setMicDeviceId] = useState<string>("default");
  const [speakerDeviceId, setSpeakerDeviceId] = useState<string>("default");
  const [noiseSuppression, setNoiseSuppression] = useState<boolean>(true);
  const [echoCancellation, setEchoCancellation] = useState<boolean>(true);
  const [ttsVoice, setTtsVoice] = useState<string>("default");
  const [ttsRate, setTtsRate] = useState<number>(0.95);

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

  const [hydrated, setHydrated] = useState(false);
  useEffect(() => { mountedRef.current = true; setHydrated(true); }, []);

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
    if (typeof p.mic_device_id === "string") setMicDeviceId(p.mic_device_id);
    if (typeof p.speaker_device_id === "string") setSpeakerDeviceId(p.speaker_device_id);
    if (typeof p.noise_suppression === "boolean") setNoiseSuppression(p.noise_suppression);
    if (typeof p.echo_cancellation === "boolean") setEchoCancellation(p.echo_cancellation);
    if (typeof p.tts_voice === "string") setTtsVoice(p.tts_voice);
    if (typeof p.tts_rate === "number") setTtsRate(p.tts_rate);
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
        mic_device_id: micDeviceId,
        speaker_device_id: speakerDeviceId,
        noise_suppression: noiseSuppression,
        echo_cancellation: echoCancellation,
        tts_voice: ttsVoice,
        tts_rate: ttsRate,
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
      const msg = e instanceof Error ? e.message : "Не удалось сохранить настройки";
      toast.error("Ошибка сохранения", { description: msg });
    }
    setSaving(false);
  }, [ttsEnabled, gender, roleTitle, primaryContact, specialization, notifyEmail, notifyPush, notifyFrequency, trainingMode, experienceLevel, pipelineColumns, compactMode, accentColor, micDeviceId, speakerDeviceId, noiseSuppression, echoCancellation, ttsVoice, ttsRate, user]);

  useEffect(() => {
    if (!mountedRef.current || !user) return;
    if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);
    const timeout = setTimeout(() => { triggerAutosave(); }, 1500);
    saveTimeoutRef.current = timeout;
    return () => { if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current); };
  }, [ttsEnabled, gender, roleTitle, primaryContact, specialization, notifyEmail, notifyPush, notifyFrequency, trainingMode, experienceLevel, pipelineColumns, compactMode, accentColor, micDeviceId, speakerDeviceId, noiseSuppression, echoCancellation, ttsVoice, ttsRate, triggerAutosave]);

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
      toast.success("Имя обновлено");
      setTimeout(() => setFullNameSaved(false), 2000);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Ошибка сохранения имени";
      setFullNameError(msg);
      toast.error("Не удалось сохранить имя", { description: msg });
    }
    setFullNameSaving(false);
  };

  return (
    <AuthLayout>
      <div className="relative panel-grid-bg min-h-screen">
        <div className="app-page max-w-4xl mx-auto">
          <BackButton href="/home" label="На главную" />

          {/*
            ═══ ПИКСЕЛЬНЫЙ ЛОГОТИП ⚙ НАСТРОЙКИ ⚙ ═══
            Симметричный «Зал Славы» / «Профиль Охотника», но в
            холодной серебряно-голубой палитре — это страница «пульта»,
            не геймификация. Те же 3 keyframes (shine, pulse, twinkle).
          */}
          <style jsx>{`
            @keyframes vh-settings-shine {
              0%   { background-position: -150% 0; }
              60%  { background-position:  250% 0; }
              100% { background-position:  250% 0; }
            }
            @keyframes vh-settings-pulse {
              0%, 100% {
                filter:
                  drop-shadow(0 3px 0 rgba(0,0,0,0.45))
                  drop-shadow(0 0 12px rgba(167,139,250,0.4))
                  drop-shadow(0 0 22px rgba(165,180,252,0.30));
              }
              50% {
                filter:
                  drop-shadow(0 3px 0 rgba(0,0,0,0.45))
                  drop-shadow(0 0 18px rgba(167,139,250,0.75))
                  drop-shadow(0 0 36px rgba(165,180,252,0.55));
              }
            }
            @keyframes vh-settings-gear-a {
              from { transform: rotate(0deg); }
              to   { transform: rotate(360deg); }
            }
            @keyframes vh-settings-gear-b {
              from { transform: rotate(360deg); }
              to   { transform: rotate(0deg); }
            }
            .vh-settings-text {
              background:
                linear-gradient(
                  120deg,
                  transparent 0%,
                  transparent 35%,
                  rgba(255,255,255,0.95) 48%,
                  rgba(255,255,255,1) 50%,
                  rgba(255,255,255,0.95) 52%,
                  transparent 65%,
                  transparent 100%
                ),
                linear-gradient(180deg, #c4b5fd 0%, #a78bfa 35%, #818cf8 100%);
              background-size: 200% 100%, 100% 100%;
              background-position: -150% 0, 0 0;
              -webkit-background-clip: text;
              background-clip: text;
              -webkit-text-fill-color: transparent;
              animation:
                vh-settings-shine 4s ease-in-out infinite,
                vh-settings-pulse 3s ease-in-out infinite;
            }
            .vh-settings-gear-left  { animation: vh-settings-gear-a 6s linear infinite; display: inline-block; }
            .vh-settings-gear-right { animation: vh-settings-gear-b 6s linear infinite; display: inline-block; }
            @media (prefers-reduced-motion: reduce) {
              .vh-settings-text, .vh-settings-gear-left, .vh-settings-gear-right {
                animation: none !important;
              }
            }
          `}</style>
          <div className="text-center pt-2 pb-2 select-none">
            <div
              className="font-pixel vh-settings-text"
              style={{
                fontSize: "clamp(28px, 5vw, 48px)",
                lineHeight: 1.0,
                letterSpacing: "0.06em",
              }}
            >
              <span
                aria-hidden
                className="vh-settings-gear-left"
                style={{
                  marginRight: 12,
                  color: "#a78bfa",
                  WebkitTextFillColor: "#a78bfa",
                  textShadow: "0 0 10px rgba(167,139,250,0.85)",
                }}
              >⚙</span>
              НАСТРОЙКИ
              <span
                aria-hidden
                className="vh-settings-gear-right"
                style={{
                  marginLeft: 12,
                  color: "#a78bfa",
                  WebkitTextFillColor: "#a78bfa",
                  textShadow: "0 0 10px rgba(167,139,250,0.85)",
                }}
              >⚙</span>
            </div>
          </div>

          {/* Header-bar: avatar + role + level + autosave indicator */}
          <div
            className="flex items-center gap-4 mt-3 p-4 rounded-sm"
            style={{
              background: "rgba(8,5,18,0.55)",
              border: "2px solid rgba(167,139,250,0.28)",
            }}
          >
            <AvatarUpload
              currentUrl={avatarUrl}
              userName={user?.full_name || ""}
              size={56}
              onUploaded={(url) => { setAvatarUrl(url); invalidateUserCache(); }}
              onDeleted={() => { setAvatarUrl(null); invalidateUserCache(); }}
            />
            <div className="flex-1 min-w-0">
              <div
                className="font-pixel uppercase tracking-widest truncate"
                style={{ color: "var(--text-primary)", fontSize: 18 }}
              >
                {user?.full_name || "—"}
              </div>
              <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                <span
                  className="rounded-sm px-2 py-0.5 font-pixel uppercase tracking-widest"
                  style={{
                    background: "rgba(167,139,250,0.18)",
                    color: "var(--accent)",
                    border: "1px solid var(--accent)",
                    fontSize: 14,
                  }}
                >
                  {roleLabels[user?.role || ""] || user?.role || ""}
                </span>
                <span
                  className="inline-flex items-center gap-1 font-pixel tabular-nums"
                  style={{ color: "var(--accent)", fontSize: 14 }}
                >
                  <Lightning weight="duotone" size={12} /> УР. {level}
                </span>
                {streak > 0 && (
                  <span
                    className="inline-flex items-center gap-1 font-pixel tabular-nums"
                    style={{ color: "#fb923c", fontSize: 14 }}
                  >
                    <Flame weight="duotone" size={12} /> {streak}д
                  </span>
                )}
              </div>
            </div>
            <div className="text-right shrink-0">
              <AnimatePresence mode="wait">
                {saving ? (
                  <motion.div
                    key="saving"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className="inline-flex items-center gap-2 px-2.5 py-1 rounded-sm font-pixel uppercase tracking-widest"
                    style={{
                      background: "rgba(255,255,255,0.05)",
                      border: "1px solid rgba(255,255,255,0.18)",
                      color: "var(--text-muted)",
                      fontSize: 14,
                    }}
                  >
                    <Loader2 size={12} className="animate-spin" />
                    Сохранение
                  </motion.div>
                ) : saved ? (
                  <motion.div
                    key="saved"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-sm font-pixel uppercase tracking-widest"
                    style={{
                      background: "rgba(74,222,128,0.18)",
                      border: "1px solid #4ade80",
                      color: "#4ade80",
                      fontSize: 14,
                    }}
                  >
                    <Check size={12} /> Сохранено
                  </motion.div>
                ) : null}
              </AnimatePresence>
            </div>
          </div>

          {/* ═══ SECTION 1: ИГРОК ═══ */}
          <SettingsSection
            accent="#a78bfa"
            title="👤 ИГРОК"
            icon={UserIcon}
            description="Личные данные и контактная информация"
          >
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <SettingsCard className="md:col-span-2">
                <SettingsLabel>Имя</SettingsLabel>
                <div className="flex gap-2 items-center">
                  <PixelInput
                    value={fullName}
                    onChange={(v) => { setFullName(v); setFullNameError(null); setFullNameSaved(false); }}
                    placeholder="Ваше имя"
                    maxLength={100}
                    disabled={fullNameSaving}
                  />
                  <Button
                    onClick={handleSaveName}
                    disabled={fullNameSaving || !fullName.trim() || fullName.trim() === user?.full_name}
                    size="sm"
                  >
                    {fullNameSaving ? <Loader2 size={14} className="animate-spin" /> : fullNameSaved ? <Check size={14} /> : <Save size={14} />}
                  </Button>
                </div>
                {fullNameError && (
                  <p className="font-pixel uppercase tracking-widest mt-2" style={{ color: "var(--danger)", fontSize: 14 }}>
                    {fullNameError}
                  </p>
                )}
                <p className="font-pixel uppercase tracking-widest mt-2" style={{ color: "var(--text-muted)", fontSize: 14 }}>
                  Email: {user?.email}
                </p>
              </SettingsCard>

              <SettingsCard>
                <SettingsLabel>Пол</SettingsLabel>
                <div className="flex flex-wrap gap-2">
                  {GENDERS.map((g) => (
                    <PixelChip
                      key={g.key}
                      active={gender === g.key}
                      label={g.label}
                      onClick={() => setGender(g.key)}
                      accent="#a78bfa"
                    />
                  ))}
                </div>
              </SettingsCard>

              <SettingsCard>
                <SettingsLabel>Должность</SettingsLabel>
                <PixelInput value={roleTitle} onChange={setRoleTitle} placeholder="Менеджер" />
              </SettingsCard>

              <SettingsCard>
                <SettingsLabel>Контакт</SettingsLabel>
                <PixelInput value={primaryContact} onChange={setPrimaryContact} placeholder="Telegram / Phone" />
              </SettingsCard>

              <SettingsCard>
                <SettingsLabel>Специализация</SettingsLabel>
                <PixelInput value={specialization} onChange={setSpecialization} placeholder="HR, Продажи..." />
              </SettingsCard>
            </div>
          </SettingsSection>

          {/* ═══ SECTION 2: ТРЕНИРОВКА ═══ */}
          <SettingsSection
            accent="#4ade80"
            title="🎮 ТРЕНИРОВКА"
            icon={GameController}
            description="Режим, уровень, озвучка"
          >
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <SettingsCard className="md:col-span-2">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <SpeakerHigh weight="duotone" size={20} style={{ color: "#4ade80" }} />
                    <span className="font-pixel uppercase tracking-widest" style={{ color: "var(--text-primary)", fontSize: 14 }}>
                      Озвучка AI
                    </span>
                  </div>
                  <PixelToggle on={ttsEnabled} onChange={() => setTtsEnabled(!ttsEnabled)} accent="#4ade80" />
                </div>
              </SettingsCard>

              <SettingsCard className="md:col-span-2">
                <SettingsLabel>Режим тренировки</SettingsLabel>
                <div className="flex flex-wrap gap-2">
                  {TRAINING_MODES.map((m) => (
                    <PixelChip
                      key={m.key}
                      active={trainingMode === m.key}
                      label={m.label}
                      onClick={() => setTrainingMode(m.key)}
                      accent="#4ade80"
                    />
                  ))}
                </div>
              </SettingsCard>

              <SettingsCard className="md:col-span-2">
                <SettingsLabel>Уровень сложности</SettingsLabel>
                <div className="flex gap-2 flex-wrap">
                  {EXPERIENCE_LEVELS.map((l) => (
                    <PixelChip
                      key={l.key}
                      active={experienceLevel === l.key}
                      label={l.label}
                      onClick={() => setExperienceLevel(l.key)}
                      accent="#4ade80"
                    />
                  ))}
                </div>
              </SettingsCard>
            </div>
          </SettingsSection>

          {/* ═══ SECTION 3: ЗВУК ═══ */}
          <SettingsSection
            accent="#facc15"
            title="🔊 ЗВУК"
            icon={SpeakerHigh}
            description="Громкость, устройства, голос"
          >
            <SoundSettings />
            <div className="mt-4">
              <AudioDevicesPanel
                micDeviceId={micDeviceId}
                speakerDeviceId={speakerDeviceId}
                noiseSuppression={noiseSuppression}
                echoCancellation={echoCancellation}
                ttsVoice={ttsVoice}
                ttsRate={ttsRate}
                onChangeMicDevice={setMicDeviceId}
                onChangeSpeakerDevice={setSpeakerDeviceId}
                onChangeNoiseSuppression={setNoiseSuppression}
                onChangeEchoCancellation={setEchoCancellation}
                onChangeTtsVoice={setTtsVoice}
                onChangeTtsRate={setTtsRate}
              />
            </div>
          </SettingsSection>

          {/* ═══ SECTION 4: ВНЕШНИЙ ВИД ═══ */}
          <SettingsSection
            accent="#fb923c"
            title="🎨 ВНЕШНИЙ ВИД"
            icon={Palette}
            description="Тема, акцент, эффекты"
          >
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <SettingsCard>
                <SettingsLabel>Тема</SettingsLabel>
                {hydrated && (
                  <div className="flex gap-2 flex-wrap">
                    {THEMES.map((t) => (
                      <PixelChip
                        key={t.key}
                        active={theme === t.key}
                        label={t.label}
                        onClick={() => setTheme(t.key)}
                        accent="#fb923c"
                      />
                    ))}
                  </div>
                )}
              </SettingsCard>

              <SettingsCard>
                <SettingsLabel>Акцент</SettingsLabel>
                <div className="flex gap-2.5 flex-wrap">
                  {ACCENT_COLORS.map((c) => (
                    <motion.button
                      key={c.key}
                      type="button"
                      onClick={() => setAccentColor(c.key)}
                      className="rounded-sm transition-all"
                      style={{
                        width: 36,
                        height: 36,
                        background: c.color,
                        border: accentColor === c.key ? "3px solid #fff" : "2px solid rgba(255,255,255,0.2)",
                        boxShadow: accentColor === c.key ? `0 0 12px ${c.color}` : "none",
                      }}
                      whileHover={{ scale: 1.1 }}
                      whileTap={{ scale: 0.9 }}
                      title={c.label}
                    />
                  ))}
                </div>
              </SettingsCard>

              <SettingsCard className="md:col-span-2">
                <div className="flex items-center justify-between">
                  <span className="font-pixel uppercase tracking-widest" style={{ color: "var(--text-primary)", fontSize: 14 }}>
                    Компактный режим
                  </span>
                  <PixelToggle on={compactMode} onChange={() => setCompactMode(!compactMode)} accent="#fb923c" />
                </div>
              </SettingsCard>

              <SettingsCard className="md:col-span-2">
                <SettingsLabel>Ретро-эффект CRT</SettingsLabel>
                <p className="font-pixel uppercase tracking-widest mb-3" style={{ color: "var(--text-muted)", fontSize: 14 }}>
                  Сканлайны + flicker. На /leaderboard всегда вкл (Зал Славы).
                </p>
                <div className="flex flex-wrap gap-2">
                  {[
                    { key: "leaderboard", label: "Только лидерборд" },
                    { key: "global", label: "На всём сайте" },
                    { key: "off", label: "Выключить" },
                  ].map((opt) => (
                    <PixelChip
                      key={opt.key}
                      active={crtMode === opt.key}
                      label={opt.label}
                      onClick={() => {
                        const next = opt.key as "off" | "leaderboard" | "global";
                        setCrtModeState(next);
                        writeCRTMode(next);
                      }}
                      accent="#fb923c"
                    />
                  ))}
                </div>
              </SettingsCard>
            </div>
          </SettingsSection>

          {/* ═══ SECTION 5: УВЕДОМЛЕНИЯ ═══ */}
          <SettingsSection
            accent="#f87171"
            title="🔔 УВЕДОМЛЕНИЯ"
            icon={Bell}
            description="Когда и как сообщать"
          >
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <SettingsCard>
                <div className="flex items-center justify-between mb-3">
                  <span className="inline-flex items-center gap-2 font-pixel uppercase tracking-widest" style={{ color: "var(--text-primary)", fontSize: 14 }}>
                    <ChatCircle weight="duotone" size={16} style={{ color: "#f87171" }} /> В приложении
                  </span>
                  <PixelToggle on={notifyPush} onChange={() => setNotifyPush(!notifyPush)} accent="#f87171" />
                </div>
                <div className="flex items-center justify-between">
                  <span className="inline-flex items-center gap-2 font-pixel uppercase tracking-widest" style={{ color: "var(--text-primary)", fontSize: 14 }}>
                    <Envelope weight="duotone" size={16} style={{ color: "#f87171" }} /> Email
                  </span>
                  <PixelToggle on={notifyEmail} onChange={() => setNotifyEmail(!notifyEmail)} accent="#f87171" />
                </div>
              </SettingsCard>

              <SettingsCard>
                <SettingsLabel>Частота</SettingsLabel>
                <div className="flex flex-wrap gap-2">
                  {NOTIFY_FREQUENCIES.map((f) => (
                    <PixelChip
                      key={f.key}
                      active={notifyFrequency === f.key}
                      label={f.label}
                      onClick={() => setNotifyFrequency(f.key as "realtime" | "daily" | "weekly")}
                      accent="#f87171"
                    />
                  ))}
                </div>
              </SettingsCard>
            </div>
          </SettingsSection>

          {/* ═══ SECTION 6: СВЯЗКИ ═══ */}
          <SettingsSection
            accent="#06b6d4"
            title="🔗 СВЯЗКИ"
            icon={LinkSimple}
            description="Внешние аккаунты"
          >
            <div className="space-y-2">
              {/* Google */}
              <div
                className="flex items-center justify-between rounded-sm px-3 py-2.5"
                style={{
                  background: "rgba(0,0,0,0.35)",
                  border: "1px solid rgba(255,255,255,0.08)",
                }}
              >
                <div className="flex items-center gap-2.5">
                  <svg width="18" height="18" viewBox="0 0 24 24"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/></svg>
                  <span className="font-pixel uppercase tracking-widest" style={{ color: "var(--text-secondary)", fontSize: 14 }}>
                    Google
                  </span>
                </div>
                {linkedGoogle ? (
                  <button
                    onClick={async () => {
                      setUnlinking("google");
                      try {
                        await api.post("/auth/google/disconnect", {});
                        setLinkedGoogle(false);
                        toast.success("Google отвязан");
                      } catch (e) {
                        logger.error("Google unlink failed:", e);
                        toast.error("Не удалось отвязать Google", { description: e instanceof Error ? e.message : undefined });
                      }
                      setUnlinking(null);
                    }}
                    disabled={unlinking === "google"}
                    className="rounded-sm font-pixel uppercase tracking-widest"
                    style={{
                      padding: "6px 12px",
                      background: "rgba(248,113,113,0.18)",
                      color: "#f87171",
                      border: "2px solid #f87171",
                      fontSize: 14,
                    }}
                  >
                    {unlinking === "google" ? <Loader2 size={12} className="animate-spin" /> : "Отвязать"}
                  </button>
                ) : oauthStatus.google ? (
                  <button
                    onClick={async () => {
                      try {
                        const d = await api.get<{ url?: string }>("/auth/google/login");
                        if (d?.url) {
                          const { validateOAuthUrl } = await import("@/lib/sanitize");
                          const safeUrl = validateOAuthUrl(d.url);
                          if (safeUrl) window.location.href = safeUrl;
                          else toast.error("Получен небезопасный URL для OAuth");
                        } else {
                          toast.error("Сервер не вернул URL для входа Google");
                        }
                      } catch (e) {
                        logger.error("Google link failed:", e);
                        toast.error("Не удалось начать привязку Google");
                      }
                    }}
                    className="rounded-sm font-pixel uppercase tracking-widest"
                    style={{
                      padding: "6px 12px",
                      background: "rgba(167,139,250,0.18)",
                      color: "var(--accent)",
                      border: "2px solid var(--accent)",
                      fontSize: 14,
                    }}
                  >
                    Привязать
                  </button>
                ) : (
                  <span className="font-pixel uppercase tracking-widest" style={{ color: "var(--text-muted)", fontSize: 14 }}>—</span>
                )}
              </div>

              {/* Yandex */}
              <div
                className="flex items-center justify-between rounded-sm px-3 py-2.5"
                style={{
                  background: "rgba(0,0,0,0.35)",
                  border: "1px solid rgba(255,255,255,0.08)",
                }}
              >
                <div className="flex items-center gap-2.5">
                  <svg width="18" height="18" viewBox="0 0 24 24"><path d="M2 12C2 6.48 6.48 2 12 2s10 4.48 10 10-4.48 10-10 10S2 17.52 2 12z" fill="#FC3F1D"/><path d="M13.32 17.5h-1.88V7.38h-.97c-1.57 0-2.39.8-2.39 1.95 0 1.3.59 1.9 1.8 2.7l1 .65-2.9 4.82H6l2.62-4.33C7.37 12.26 6.56 11.22 6.56 9.5c0-2.07 1.45-3.5 4-3.5h2.76V17.5z" fill="white"/></svg>
                  <span className="font-pixel uppercase tracking-widest" style={{ color: "var(--text-secondary)", fontSize: 14 }}>
                    Yandex
                  </span>
                </div>
                {linkedYandex ? (
                  <button
                    onClick={async () => {
                      setUnlinking("yandex");
                      try {
                        await api.post("/auth/yandex/disconnect", {});
                        setLinkedYandex(false);
                        toast.success("Яндекс отвязан");
                      } catch (e) {
                        logger.error("Yandex unlink failed:", e);
                        toast.error("Не удалось отвязать Яндекс", { description: e instanceof Error ? e.message : undefined });
                      }
                      setUnlinking(null);
                    }}
                    disabled={unlinking === "yandex"}
                    className="rounded-sm font-pixel uppercase tracking-widest"
                    style={{
                      padding: "6px 12px",
                      background: "rgba(248,113,113,0.18)",
                      color: "#f87171",
                      border: "2px solid #f87171",
                      fontSize: 14,
                    }}
                  >
                    {unlinking === "yandex" ? <Loader2 size={12} className="animate-spin" /> : "Отвязать"}
                  </button>
                ) : oauthStatus.yandex ? (
                  <button
                    onClick={async () => {
                      try {
                        const d = await api.get<{ url?: string }>("/auth/yandex/login");
                        if (d?.url) {
                          const { validateOAuthUrl } = await import("@/lib/sanitize");
                          const safeUrl = validateOAuthUrl(d.url);
                          if (safeUrl) window.location.href = safeUrl;
                          else toast.error("Получен небезопасный URL для OAuth");
                        } else {
                          toast.error("Сервер не вернул URL для входа Яндекса");
                        }
                      } catch (e) {
                        logger.error("Yandex link failed:", e);
                        toast.error("Не удалось начать привязку Яндекса");
                      }
                    }}
                    className="rounded-sm font-pixel uppercase tracking-widest"
                    style={{
                      padding: "6px 12px",
                      background: "rgba(167,139,250,0.18)",
                      color: "var(--accent)",
                      border: "2px solid var(--accent)",
                      fontSize: 14,
                    }}
                  >
                    Привязать
                  </button>
                ) : (
                  <span className="font-pixel uppercase tracking-widest" style={{ color: "var(--text-muted)", fontSize: 14 }}>—</span>
                )}
              </div>
            </div>
          </SettingsSection>

          {/* ═══ SECTION 7: ВОРОНКА (CRM only) ═══ */}
          {showCRM && (
            <SettingsSection
              accent="#ff3ec8"
              title="📋 ВОРОНКА"
              icon={Kanban}
              description="Колонки CRM-канбана"
            >
              <SettingsCard>
                <SettingsLabel>Активные этапы (минимум 2)</SettingsLabel>
                <div className="flex flex-wrap gap-2">
                  {PIPELINE_STATUSES.map((status) => {
                    const on = pipelineColumns.includes(status);
                    const statusColor = CLIENT_STATUS_COLORS[status as ClientStatus] || "var(--text-muted)";
                    const disabled = on && pipelineColumns.length <= 2;
                    return (
                      <button
                        key={status}
                        type="button"
                        disabled={disabled}
                        onClick={() => {
                          if (disabled) return;
                          setPipelineColumns(on
                            ? pipelineColumns.filter((s) => s !== status)
                            : [...pipelineColumns, status]
                          );
                        }}
                        className="inline-flex items-center gap-2 rounded-sm font-pixel uppercase tracking-widest transition-all"
                        style={{
                          padding: "8px 14px",
                          fontSize: 14,
                          background: on ? `${statusColor}1f` : "rgba(255,255,255,0.04)",
                          border: `2px solid ${on ? statusColor : "rgba(255,255,255,0.18)"}`,
                          color: on ? statusColor : "var(--text-secondary)",
                          opacity: on ? 1 : 0.7,
                          cursor: disabled ? "not-allowed" : "pointer",
                          boxShadow: on ? `0 0 8px ${statusColor}55` : "none",
                        }}
                      >
                        <span className="rounded-sm" style={{ width: 8, height: 8, background: statusColor }} />
                        {CLIENT_STATUS_LABELS[status as ClientStatus]}
                      </button>
                    );
                  })}
                </div>
              </SettingsCard>
            </SettingsSection>
          )}

          {/* Footer — пиксельная подпись симметрично /leaderboard и /profile */}
          <div className="text-center mt-12 mb-8">
            <div
              className="font-pixel uppercase tracking-widest inline-flex items-center gap-2"
              style={{ color: "var(--text-muted)", fontSize: 14 }}
            >
              <Gear weight="duotone" size={14} />
              ★ КОНЕЦ НАСТРОЕК ★
              <Gear weight="duotone" size={14} />
            </div>
          </div>
        </div>
      </div>
    </AuthLayout>
  );
}
