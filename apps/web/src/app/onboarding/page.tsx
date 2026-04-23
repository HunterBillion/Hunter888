"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  User, Settings, Target, Mic, MessageCircle,
  ArrowRight, ChevronLeft, Check, Crosshair,
  Sun, Moon, Volume2, Bell, CheckCircle, Lightbulb,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { api } from "@/lib/api";
import { AvatarUpload } from "@/components/settings/AvatarUpload";
import { UserAvatar } from "@/components/ui/UserAvatar";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { AppIcon } from "@/components/ui/AppIcon";
import { logger } from "@/lib/logger";
import { PixelGridBackground } from "@/components/landing/PixelGridBackground";
import { useAuthStore } from "@/stores/useAuthStore";

// ── Steps config (3 steps per XHUNTER_PLAN_v2 §3.4) ──────
// Old: 5 steps (Профиль, Настройки, Микрофон, Тренировка, Демо)
// New: 3 steps — mic test embedded in step 3, settings merged into step 1
const STEPS = [
  { id: 1, label: "Профиль", icon: User },
  { id: 2, label: "Архетип", icon: Crosshair },
  { id: 3, label: "Пробная", icon: MessageCircle },
];

const TEAMS = ["Отдел продаж", "Отдел B2B", "Холодные звонки", "Сопровождение", "Другое"];
const SPECIALIZATIONS = [
  { value: "real_estate", label: "Недвижимость", desc: "Сделки, договоры, регистрация", icon: "🏠" },
  { value: "corporate", label: "Корпоративное право", desc: "Договоры, ООО, ИП", icon: "🏢" },
  { value: "family", label: "Семейное право", desc: "Разводы, наследство, опека", icon: "👨‍👩‍👧" },
  { value: "bankruptcy", label: "Банкротство", desc: "Физ. и юр. лица", icon: "📉" },
  { value: "criminal", label: "Уголовное право", desc: "Защита, представительство", icon: "⚖️" },
  { value: "general", label: "Общая практика", desc: "Широкий профиль", icon: "📋" },
];
const EXP_LEVELS = [
  { value: "beginner", label: "Новичок", desc: "Менее 1 года", icon: "🌱" },
  { value: "intermediate", label: "Опытный", desc: "1-3 года", icon: "⚡" },
  { value: "advanced", label: "Профи", desc: "Более 3 лет", icon: "🏆" },
];
const GENDERS = [
  { value: "male", label: "Мужской" },
  { value: "female", label: "Женский" },
  { value: "neutral", label: "Не указывать" },
];
const LEAD_SOURCES = [
  { value: "sso_google", label: "Google / SSO" },
  { value: "sso_yandex", label: "Yandex / SSO" },
  { value: "website", label: "Сайт" },
  { value: "referral", label: "Рекомендация" },
  { value: "manual", label: "Вручную" },
];
const MODES = [
  { value: "structured", label: "Структурированный", desc: "Пошаговые сценарии", icon: "📋" },
  { value: "freestyle", label: "Свободный", desc: "Импровизация", icon: "🎯" },
  { value: "challenge", label: "Челлендж", desc: "Сложные клиенты", icon: "⚡" },
];

// D2: Trial dialog messages
const DEMO_MESSAGES = [
  { role: "system" as const, text: "Сценарий: Холодный звонок скептичному клиенту. Ваша задача — заинтересовать его." },
  { role: "bot" as const, text: "Алло, слушаю. Кто это?" },
];
const DEMO_HINTS = [
  "Попробуйте представиться и назвать причину звонка",
  "Отлично! Теперь можете перейти к делу",
];

// ── D1: Clean SVG illustrations (no animation artifacts) ──────────────
function StepIllustration({ step }: { step: number }) {
  const illustrations: Record<number, React.ReactNode> = {
    1: (
      <div className="flex justify-center mb-4">
        <div className="w-20 h-20 rounded-2xl flex items-center justify-center" style={{ background: "var(--accent-muted)", border: "2px solid var(--accent)" }}>
          <User size={36} style={{ color: "var(--accent)" }} />
        </div>
      </div>
    ),
    2: (
      <div className="flex justify-center mb-4">
        <div className="w-20 h-20 rounded-2xl flex items-center justify-center" style={{ background: "var(--accent-muted)", border: "2px solid var(--accent)" }}>
          <Crosshair size={36} style={{ color: "var(--accent)" }} />
        </div>
      </div>
    ),
    3: (
      <div className="flex justify-center mb-4">
        <div className="w-20 h-20 rounded-2xl flex items-center justify-center" style={{ background: "var(--accent-muted)", border: "2px solid var(--accent)" }}>
          <MessageCircle size={36} style={{ color: "var(--accent)" }} />
        </div>
      </div>
    ),
  };
  return illustrations[step] ?? null;
}

// ── D3: Mic test component ─────────────────────────────────
function MicTest({ onResult }: { onResult: (ok: boolean) => void }) {
  const [status, setStatus] = useState<"idle" | "testing" | "success" | "error">("idle");
  const [level, setLevel] = useState(0);
  const streamRef = useRef<MediaStream | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animRef = useRef(0);

  const startTest = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const ctx = new AudioContext();
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      analyserRef.current = analyser;
      setStatus("testing");

      const data = new Uint8Array(analyser.frequencyBinCount);
      let maxLevel = 0;
      const tick = () => {
        analyser.getByteFrequencyData(data);
        const avg = data.reduce((a, b) => a + b, 0) / data.length;
        const normalized = Math.min(1, avg / 80);
        setLevel(normalized);
        if (normalized > maxLevel) maxLevel = normalized;
        animRef.current = requestAnimationFrame(tick);
      };
      tick();

      // Auto-detect after 3 seconds
      setTimeout(() => {
        cancelAnimationFrame(animRef.current);
        stream.getTracks().forEach(t => t.stop());
        if (maxLevel > 0.05) {
          setStatus("success");
          onResult(true);
        } else {
          setStatus("error");
          onResult(false);
        }
      }, 3000);
    } catch {
      setStatus("error");
      onResult(false);
    }
  }, [onResult]);

  useEffect(() => {
    return () => {
      cancelAnimationFrame(animRef.current);
      streamRef.current?.getTracks().forEach(t => t.stop());
    };
  }, []);

  return (
    <div className="space-y-4">
      {status === "idle" && (
        <motion.button
          type="button"
          onClick={startTest}
          className="w-full rounded-xl p-6 flex flex-col items-center gap-3 transition-all"
          style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)" }}
          whileHover={{ borderColor: "var(--accent)", boxShadow: "0 0 15px var(--accent-glow)" }}
          whileTap={{ scale: 0.98 }}
        >
          <Mic size={32} style={{ color: "var(--accent)" }} />
          <span className="font-medium" style={{ color: "var(--text-primary)" }}>Проверить микрофон</span>
          <span className="text-xs" style={{ color: "var(--text-muted)" }}>Скажите что-нибудь</span>
        </motion.button>
      )}

      {status === "testing" && (
        <div className="rounded-xl p-6 flex flex-col items-center gap-4" style={{ background: "var(--input-bg)", border: "1px solid var(--accent)" }}>
          <div className="flex items-end gap-1 h-16">
            {Array.from({ length: 20 }).map((_, i) => (
              <motion.div
                key={i}
                className="w-1.5 rounded-full"
                style={{ background: "var(--accent)" }}
                animate={{
                  height: Math.max(4, level * 64 * (0.3 + Math.sin(i * 0.5) * 0.7)),
                  opacity: 0.3 + level * 0.7,
                }}
                transition={{ duration: 0.05 }}
              />
            ))}
          </div>
          <span className="font-mono text-xs animate-pulse" style={{ color: "var(--accent)" }}>СЛУШАЮ...</span>
        </div>
      )}

      {status === "success" && (
        <motion.div initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
          className="rounded-xl p-6 flex flex-col items-center gap-3"
          style={{ background: "var(--success-muted)", border: "1px solid var(--success-muted)" }}
        >
          <Check size={32} style={{ color: "var(--success)" }} />
          <span className="font-medium" style={{ color: "var(--success)" }}>Микрофон работает!</span>
        </motion.div>
      )}

      {status === "error" && (
        <motion.div initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
          className="rounded-xl p-6 flex flex-col items-center gap-3"
          style={{ background: "var(--danger-muted)", border: "1px solid var(--danger-muted)" }}
        >
          <Mic size={32} style={{ color: "var(--danger)" }} />
          <span className="font-medium" style={{ color: "var(--danger)" }}>Микрофон недоступен</span>
          <span className="text-xs" style={{ color: "var(--text-muted)" }}>Можно использовать текстовый ввод</span>
          <button type="button" onClick={startTest} className="text-xs mt-1" style={{ color: "var(--accent)" }}>
            Попробовать снова
          </button>
        </motion.div>
      )}
    </div>
  );
}

// ── D2: Trial dialog ───────────────────────────────────────
// ── Typewriter text: reveals character by character ────────────
function Typewriter({ text, speed = 28, onDone }: { text: string; speed?: number; onDone?: () => void }) {
  const [shown, setShown] = useState("");
  useEffect(() => {
    let i = 0;
    const id = setInterval(() => {
      i++;
      setShown(text.slice(0, i));
      if (i >= text.length) {
        clearInterval(id);
        onDone?.();
      }
    }, speed);
    return () => clearInterval(id);
  }, [text, speed, onDone]);
  return (
    <>
      {shown}
      {shown.length < text.length && (
        <motion.span
          className="inline-block w-[2px] h-[14px] align-middle ml-[1px]"
          style={{ background: "var(--accent)" }}
          animate={{ opacity: [1, 0, 1] }}
          transition={{ duration: 0.7, repeat: Infinity }}
        />
      )}
    </>
  );
}

function TrialDialog() {
  const [messages, setMessages] = useState<{ role: "system" | "bot" | "user"; text: string; typing?: boolean }[]>(DEMO_MESSAGES);
  const [input, setInput] = useState("");
  const [responded, setResponded] = useState(false);
  const [botTyping, setBotTyping] = useState(false);

  const sendMessage = () => {
    if (!input.trim() || responded) return;
    setMessages(prev => [...prev, { role: "user" as const, text: input.trim() }]);
    setInput("");
    setBotTyping(true);
    setTimeout(() => {
      setBotTyping(false);
      // Bot response with typewriter flag — will animate character-by-character
      setMessages(prev => [...prev, {
        role: "bot" as const,
        text: "Хм, ладно, слушаю. У вас 30 секунд. Что за компания и зачем звоните?",
        typing: true,
      }]);
      setResponded(true);
    }, 1200);
  };

  return (
    <div className="space-y-3">
      <div
        className="rounded-xl p-4 space-y-3 max-h-[260px] overflow-y-auto"
        style={{
          background: "var(--input-bg)",
          border: "1px solid var(--border-color)",
          backgroundImage: "linear-gradient(180deg, var(--input-bg) 0%, color-mix(in oklab, var(--input-bg) 85%, var(--accent) 15%) 100%)",
        }}
      >
        {messages.map((msg, i) => {
          const isUser = msg.role === "user";
          const isSystem = msg.role === "system";
          const isBot = msg.role === "bot";
          return (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 10, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              transition={{ delay: i * 0.08, type: "spring", stiffness: 200, damping: 20 }}
              className={`flex ${isUser ? "justify-end" : "justify-start"} gap-2 items-end`}
            >
              {/* Bot avatar */}
              {isBot && (
                <div
                  className="flex items-center justify-center w-7 h-7 rounded-full shrink-0 text-sm"
                  style={{
                    background: "var(--accent-muted)",
                    border: "1px solid var(--accent)",
                    boxShadow: "0 0 10px var(--accent-glow)",
                  }}
                >
                  🤨
                </div>
              )}
              <div
                className="rounded-2xl px-3.5 py-2.5 text-sm max-w-[78%] relative"
                style={{
                  background: isUser ? "var(--accent)" : isSystem ? "var(--accent-muted)" : "var(--glass-bg)",
                  color: isUser ? "white" : isSystem ? "var(--accent)" : "var(--text-primary)",
                  border: isBot ? "1px solid var(--border-color)" : "none",
                  borderBottomRightRadius: isUser ? "4px" : undefined,
                  borderBottomLeftRadius: isBot ? "4px" : undefined,
                }}
              >
                {isSystem && (
                  <span
                    className="font-mono text-[10px] block mb-1 tracking-wider uppercase"
                    style={{ color: "var(--accent)", opacity: 0.7 }}
                  >
                    АГИ
                  </span>
                )}
                {isBot && msg.typing ? (
                  <Typewriter text={msg.text} speed={25} />
                ) : (
                  msg.text
                )}
              </div>
            </motion.div>
          );
        })}
        {botTyping && (
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex items-end gap-2"
          >
            <div
              className="flex items-center justify-center w-7 h-7 rounded-full shrink-0 text-sm"
              style={{
                background: "var(--accent-muted)",
                border: "1px solid var(--accent)",
                boxShadow: "0 0 10px var(--accent-glow)",
              }}
            >
              🤨
            </div>
            <div
              className="rounded-2xl px-4 py-3 flex gap-1.5 items-center"
              style={{
                background: "var(--glass-bg)",
                border: "1px solid var(--border-color)",
                borderBottomLeftRadius: "4px",
              }}
            >
              {[0, 1, 2].map(i => (
                <motion.span
                  key={i}
                  className="w-2 h-2 rounded-full"
                  style={{ background: "var(--accent)" }}
                  animate={{ y: [0, -5, 0], opacity: [0.4, 1, 0.4] }}
                  transition={{ duration: 0.9, repeat: Infinity, delay: i * 0.15 }}
                />
              ))}
            </div>
          </motion.div>
        )}
      </div>

      {!responded && (
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && sendMessage()}
            className="vh-input flex-1"
            placeholder="Ваш ответ..."
            autoFocus
          />
          <Button size="sm" onClick={sendMessage} disabled={!input.trim()} icon={<ArrowRight size={16} />} />
        </div>
      )}

      {!responded && (
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="text-xs text-center flex items-center justify-center gap-1.5"
          style={{ color: "var(--text-muted)" }}
        >
          <Lightbulb size={14} className="inline" style={{ color: "var(--accent)" }} />
          {DEMO_HINTS[0]}
        </motion.p>
      )}

      {responded && (
        <motion.p
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 1.8 }}
          className="text-xs text-center flex items-center justify-center gap-1.5"
          style={{ color: "var(--success)" }}
        >
          <CheckCircle size={16} className="inline" /> Отлично! Вы готовы к настоящим тренировкам
        </motion.p>
      )}
    </div>
  );
}

// ── Main Onboarding Page ───────────────────────────────────
export default function OnboardingPage() {
  const router = useRouter();
  const { user, invalidate } = useAuthStore();
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Form data
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState<"manager" | "rop">("manager");
  const [gender, setGender] = useState("");
  const [roleTitle, setRoleTitle] = useState("");
  const [leadSource, setLeadSource] = useState("");
  const [primaryContact, setPrimaryContact] = useState("");
  const [team, setTeam] = useState("");
  const [specialization, setSpecialization] = useState("");
  const [experience, setExperience] = useState("");
  const [ttsEnabled, setTtsEnabled] = useState(true);
  const [notifications, setNotifications] = useState(true);
  const [micOk, setMicOk] = useState<boolean | null>(null);
  const [trainingMode, setTrainingMode] = useState("structured");
  const [avatarUrl, setAvatarUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    const prefs = (user.preferences as Record<string, unknown>) || {};
    if (user.full_name) setFullName(user.full_name);
    if (user.avatar_url) setAvatarUrl(user.avatar_url);
    if (user.role === "manager" || user.role === "rop") setRole(user.role);
    if (typeof prefs.gender === "string") setGender(prefs.gender);
    if (typeof prefs.role_title === "string") setRoleTitle(prefs.role_title);
    if (typeof prefs.lead_source === "string") setLeadSource(prefs.lead_source);
    if (typeof prefs.primary_contact === "string") setPrimaryContact(prefs.primary_contact);
    if (typeof prefs.specialization === "string") setSpecialization(prefs.specialization);
    if (typeof prefs.experience_level === "string") setExperience(prefs.experience_level);
    if (typeof prefs.training_mode === "string") setTrainingMode(prefs.training_mode);
    if (typeof prefs.tts_enabled === "boolean") setTtsEnabled(prefs.tts_enabled);
    if (typeof prefs.notifications === "boolean") setNotifications(prefs.notifications);
  }, [user]);

  const canAdvance = () => {
    // Step 1: canonical profile required by profile_gate.py
    if (step === 1) {
      return fullName.trim().length >= 2
        && !!role
        && gender !== ""
        && roleTitle.trim().length >= 2
        && leadSource !== ""
        && specialization !== ""
        && experience !== "";
    }
    // Step 2: Archetype choice (pick first client type)
    if (step === 2) return trainingMode !== "";
    // Step 3: First call (demo) — always can finish
    if (step === 3) return true;
    return false;
  };

  const handleFinish = async () => {
    setLoading(true);
    setSubmitError(null);
    try {
      if (fullName.trim() && fullName.trim() !== user?.full_name) {
        await api.patch("/users/me/profile", { full_name: fullName.trim() });
      }
      await api.post("/users/me/preferences", {
        role,
        team,
        gender,
        role_title: roleTitle,
        lead_source: leadSource,
        primary_contact: primaryContact,
        specialization,
        experience_level: experience,
        tts_enabled: ttsEnabled,
        notifications,
        training_mode: trainingMode,
      });
      invalidate();
    } catch (err) {
      logger.warn("Failed to save onboarding profile:", err);
      setSubmitError(err instanceof Error ? err.message : "Не удалось сохранить профиль");
      setLoading(false);
      return;
    }
    router.push("/home");
  };

  const totalSteps = STEPS.length;
  const progressPct = ((step - 1) / (totalSteps - 1)) * 100;

  return (
    <div className="relative min-h-screen flex items-center justify-center px-4 py-8 overflow-hidden" style={{ background: "var(--bg-primary)" }}>
      {/* Living pixel field — CRT-style grid with ~15% cells in decay cycle.
          Fixed positioning via component's own className; pixelAlpha=0.22
          keeps it subtle so content cards stay readable. */}
      <div className="absolute inset-0 pointer-events-none">
        <PixelGridBackground cellSize={28} pixelSize={3} pixelAlpha={0.22} />
      </div>

      {/* Radial purple glow — sits above pixel field, adds depth */}
      <div
        className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[900px] h-[900px] rounded-full opacity-[0.18] pointer-events-none"
        style={{ background: "radial-gradient(circle, var(--accent) 0%, transparent 60%)" }}
      />

      {/* Subtle top/bottom vignette — makes content cards pop */}
      <div className="absolute inset-x-0 top-0 h-40 pointer-events-none" style={{ background: "linear-gradient(to bottom, var(--bg-primary) 0%, transparent 100%)" }} />
      <div className="absolute inset-x-0 bottom-0 h-40 pointer-events-none" style={{ background: "linear-gradient(to top, var(--bg-primary) 0%, transparent 100%)" }} />

      {/* Theme toggle */}
      <div className="fixed right-4 top-4 z-50">
        <ThemeToggle />
      </div>

      <div className="w-full max-w-lg">
        {/* D5: Visual stepper — centered with connecting line */}
        <div className="mb-10">
          <div className="flex items-start justify-center relative px-4">
            {/* Connecting line - full width behind circles */}
            <div
              className="absolute top-5 h-[2px] rounded-full"
              style={{
                left: "15%",
                right: "15%",
                background: "var(--border-color)",
              }}
            />

            {STEPS.map((s, idx) => {
              const Icon = s.icon;
              const isActive = s.id === step;
              const isDone = s.id < step;
              const isLast = idx === STEPS.length - 1;

              return (
                <div key={s.id} className="flex flex-col items-center relative" style={{ width: `${100 / totalSteps}%` }}>
                  {/* Step circle */}
                  <motion.div
                    className="flex h-10 w-10 items-center justify-center rounded-full transition-all relative z-10"
                    style={{
                      background: isDone ? "var(--accent)" : isActive ? "var(--bg-primary)" : "var(--bg-secondary)",
                      border: `2px solid ${isDone || isActive ? "var(--accent)" : "var(--border-color)"}`,
                      boxShadow: isActive ? "0 0 20px var(--accent-glow)" : "none",
                    }}
                    animate={isActive ? { scale: 1.1 } : { scale: 1 }}
                    transition={{ type: "spring", stiffness: 300 }}
                  >
                    {isDone ? (
                      <Check size={16} className="text-white" />
                    ) : (
                      <Icon size={16} style={{ color: isActive ? "var(--accent)" : "var(--text-muted)" }} />
                    )}
                  </motion.div>

                  {/* Step label */}
                  <span
                    className="mt-2 font-mono text-xs tracking-wide text-center"
                    style={{ color: isActive ? "var(--accent)" : isDone ? "var(--text-secondary)" : "var(--text-muted)" }}
                  >
                    {s.label}
                  </span>

                  {/* Progress indicator for completed steps */}
                  {isDone && !isLast && (
                    <motion.div
                      className="absolute top-5 right-0 w-[calc(100%-40px)] h-[2px]"
                      style={{ background: "var(--accent)" }}
                      initial={{ scaleX: 0 }}
                      animate={{ scaleX: 1 }}
                      transition={{ duration: 0.4 }}
                    />
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Step content */}
        <AnimatePresence mode="wait">
          <motion.div
            key={step}
            initial={{ opacity: 0, x: 30 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -30 }}
            transition={{ duration: 0.3 }}
            className="glass-panel p-8"
          >
            {/* D1: Animated illustration */}
            <StepIllustration step={step} />

            {/* Step 1: Profile */}
            {step === 1 && (
              <>
                {/* Avatar + Header section */}
                <div className="flex flex-col items-center mb-8">
                  <AvatarUpload
                    currentUrl={avatarUrl}
                    userName={fullName || "Новый пользователь"}
                    size={80}
                    onUploaded={(url) => setAvatarUrl(url)}
                    onDeleted={() => setAvatarUrl(null)}
                  />
                  <h2 className="font-display text-2xl font-bold tracking-wide mt-4 mb-1 text-center" style={{ color: "var(--text-primary)" }}>
                    Расскажите о себе
                  </h2>
                  <p className="text-sm text-center" style={{ color: "var(--text-muted)" }}>
                    Подберём оптимальные сценарии тренировок
                  </p>
                </div>

                <div className="space-y-6">
                  <div>
                    <label className="vh-label">Имя <span style={{ color: "var(--danger)" }}>*</span></label>
                    <input
                      type="text"
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      maxLength={100}
                      placeholder="Как к вам обращаться"
                      className="vh-input w-full"
                    />
                  </div>

                  <div>
                    <label className="vh-label">Ваша роль <span style={{ color: "var(--danger)" }}>*</span></label>
                    <div className="grid grid-cols-2 gap-3">
                      {[
                        { value: "manager" as const, label: "Менеджер", desc: "Тренировки, звонки, рейтинг", icon: "🎯" },
                        { value: "rop" as const, label: "Руководитель (РОП)", desc: "Аналитика, команда, контроль", icon: "📊" },
                      ].map((r, i) => {
                        const active = role === r.value;
                        return (
                          <motion.button
                            key={r.value}
                            type="button"
                            onClick={() => setRole(r.value)}
                            className="rounded-xl px-4 py-4 text-left flex items-center gap-3 transition-colors"
                            style={{
                              background: active ? "var(--accent-muted)" : "var(--input-bg)",
                              border: `1.5px solid ${active ? "var(--accent)" : "var(--border-color)"}`,
                              boxShadow: active ? "0 0 20px var(--accent-glow), inset 0 0 0 1px var(--accent)" : "none",
                            }}
                            initial={{ opacity: 0, y: 8 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: i * 0.05 }}
                            whileHover={{ y: -2, boxShadow: "0 8px 24px var(--accent-glow)" }}
                            whileTap={{ scale: 0.97 }}
                          >
                            <AppIcon emoji={r.icon} size={28} />
                            <div>
                              <div className="font-display font-bold text-sm" style={{ color: active ? "var(--accent)" : "var(--text-primary)" }}>{r.label}</div>
                              <div className="text-xs leading-snug" style={{ color: "var(--text-muted)" }}>{r.desc}</div>
                            </div>
                          </motion.button>
                        );
                      })}
                    </div>
                  </div>

                  <div>
                    <label className="vh-label">Пол для персонализации <span style={{ color: "var(--danger)" }}>*</span></label>
                    <div className="grid grid-cols-3 gap-2">
                      {GENDERS.map((g) => {
                        const active = gender === g.value;
                        return (
                          <button
                            key={g.value}
                            type="button"
                            onClick={() => setGender(g.value)}
                            className="rounded-xl px-3 py-2.5 text-sm transition-colors"
                            style={{
                              background: active ? "var(--accent-muted)" : "var(--input-bg)",
                              border: `1px solid ${active ? "var(--accent)" : "var(--border-color)"}`,
                              color: active ? "var(--accent)" : "var(--text-secondary)",
                            }}
                          >
                            {g.label}
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <label className="vh-label">Должность <span style={{ color: "var(--danger)" }}>*</span></label>
                      <input
                        type="text"
                        value={roleTitle}
                        onChange={(e) => setRoleTitle(e.target.value)}
                        maxLength={120}
                        placeholder="Например: менеджер БФЛ"
                        className="vh-input w-full"
                      />
                    </div>
                    <div>
                      <label className="vh-label">Контакт <span className="text-xs opacity-60">(необязательно)</span></label>
                      <input
                        type="text"
                        value={primaryContact}
                        onChange={(e) => setPrimaryContact(e.target.value)}
                        maxLength={120}
                        placeholder="Телефон или Telegram"
                        className="vh-input w-full"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="vh-label">Источник профиля <span style={{ color: "var(--danger)" }}>*</span></label>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {LEAD_SOURCES.map((source) => {
                        const active = leadSource === source.value;
                        return (
                          <button
                            key={source.value}
                            type="button"
                            onClick={() => setLeadSource(source.value)}
                            className="rounded-xl px-3 py-2.5 text-sm text-left transition-colors"
                            style={{
                              background: active ? "var(--accent-muted)" : "var(--input-bg)",
                              border: `1px solid ${active ? "var(--accent)" : "var(--border-color)"}`,
                              color: active ? "var(--accent)" : "var(--text-secondary)",
                            }}
                          >
                            {source.label}
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  <div>
                    <label className="vh-label">Команда <span style={{ color: "var(--danger)" }}>*</span></label>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {TEAMS.map((t, i) => {
                        const active = team === t;
                        return (
                          <motion.button key={t} type="button" onClick={() => setTeam(t)}
                            className="rounded-xl px-3 py-2.5 text-sm text-left transition-colors"
                            style={{
                              background: active ? "var(--accent-muted)" : "var(--input-bg)",
                              border: `1px solid ${active ? "var(--accent)" : "var(--border-color)"}`,
                              color: active ? "var(--accent)" : "var(--text-secondary)",
                            }}
                            initial={{ opacity: 0, y: 6 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: 0.1 + i * 0.03 }}
                            whileHover={{ y: -1, borderColor: "var(--accent)" }}
                            whileTap={{ scale: 0.97 }}
                          >{t}</motion.button>
                        );
                      })}
                    </div>
                  </div>
                  <div>
                    <label className="vh-label">Специализация <span style={{ color: "var(--danger)" }}>*</span></label>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {SPECIALIZATIONS.map((s, i) => {
                        const active = specialization === s.value;
                        return (
                          <motion.button key={s.value} type="button" onClick={() => setSpecialization(s.value)}
                            className="rounded-xl px-3 py-2.5 text-left flex items-center gap-2.5 transition-colors"
                            style={{
                              background: active ? "var(--accent-muted)" : "var(--input-bg)",
                              border: `1px solid ${active ? "var(--accent)" : "var(--border-color)"}`,
                              boxShadow: active ? "0 0 12px var(--accent-glow)" : "none",
                            }}
                            initial={{ opacity: 0, y: 6 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: 0.2 + i * 0.03 }}
                            whileHover={{ y: -1, borderColor: "var(--accent)" }}
                            whileTap={{ scale: 0.97 }}
                          >
                            <AppIcon emoji={s.icon} size={22} />
                            <div className="min-w-0">
                              <div className="font-semibold text-[13px] leading-tight" style={{ color: active ? "var(--accent)" : "var(--text-primary)" }}>{s.label}</div>
                              <div className="text-[11px] mt-0.5 truncate" style={{ color: "var(--text-muted)" }}>{s.desc}</div>
                            </div>
                          </motion.button>
                        );
                      })}
                    </div>
                  </div>
                  <div>
                    <label className="vh-label">Опыт <span style={{ color: "var(--danger)" }}>*</span></label>
                    <div className="space-y-2">
                      {EXP_LEVELS.map((e, i) => {
                        const active = experience === e.value;
                        return (
                          <motion.button key={e.value} type="button" onClick={() => setExperience(e.value)}
                            className="w-full rounded-xl px-4 py-3 text-left flex items-center gap-3 transition-colors"
                            style={{
                              background: active ? "var(--accent-muted)" : "var(--input-bg)",
                              border: `1px solid ${active ? "var(--accent)" : "var(--border-color)"}`,
                              boxShadow: active ? "0 0 14px var(--accent-glow)" : "none",
                            }}
                            initial={{ opacity: 0, y: 6 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: 0.3 + i * 0.04 }}
                            whileHover={{ y: -1, borderColor: "var(--accent)" }}
                            whileTap={{ scale: 0.97 }}
                          >
                            <AppIcon emoji={e.icon} size={26} />
                            <div>
                              <div className="font-semibold text-[14px]" style={{ color: active ? "var(--accent)" : "var(--text-primary)" }}>{e.label}</div>
                              <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>{e.desc}</div>
                            </div>
                          </motion.button>
                        );
                      })}
                    </div>
                  </div>
                </div>
              </>
            )}

            {/* Step 2: Archetype choice — 'Кто твой первый клиент?' */}
            {step === 2 && (
              <>
                <h2 className="font-display text-2xl font-bold tracking-wide mb-1 text-center" style={{ color: "var(--text-primary)" }}>Кто твой первый клиент?</h2>
                <p className="text-sm mb-7 text-center" style={{ color: "var(--text-muted)" }}>Выбери архетип для первого звонка</p>
                <div className="space-y-3">
                  {[
                    { value: "structured", label: "Скептик", desc: "Не верит, сомневается, задаёт неудобные вопросы", icon: "🤨", hue: "#a78bfa" },
                    { value: "freestyle", label: "Занятой", desc: "Торопится, перебивает, хочет быстро", icon: "⏰", hue: "#fbbf24" },
                    { value: "challenge", label: "Агрессор", desc: "Давит, угрожает, требует невозможного", icon: "😤", hue: "#f87171" },
                  ].map((m, i) => {
                    const active = trainingMode === m.value;
                    return (
                      <motion.button
                        key={m.value}
                        type="button"
                        onClick={() => setTrainingMode(m.value)}
                        className="w-full rounded-xl px-5 py-4 text-left flex items-center gap-4 transition-colors relative overflow-hidden"
                        style={{
                          background: active ? "var(--accent-muted)" : "var(--input-bg)",
                          border: `1.5px solid ${active ? "var(--accent)" : "var(--border-color)"}`,
                          boxShadow: active ? "0 0 22px var(--accent-glow), inset 0 0 0 1px var(--accent)" : "none",
                        }}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: i * 0.08 }}
                        whileHover={{ y: -2, boxShadow: "0 10px 28px var(--accent-glow)" }}
                        whileTap={{ scale: 0.98 }}
                      >
                        {/* Subtle color accent dot (per-archetype hue) */}
                        <div
                          className="flex items-center justify-center w-12 h-12 rounded-lg shrink-0"
                          style={{
                            background: `${m.hue}22`,
                            boxShadow: active ? `0 0 14px ${m.hue}55` : "none",
                          }}
                        >
                          <AppIcon emoji={m.icon} size={28} />
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="font-display font-bold text-base" style={{ color: active ? "var(--accent)" : "var(--text-primary)" }}>{m.label}</div>
                          <div className="text-[13px] mt-0.5 leading-snug" style={{ color: "var(--text-muted)" }}>{m.desc}</div>
                        </div>
                        {active && (
                          <motion.div
                            initial={{ scale: 0 }}
                            animate={{ scale: 1 }}
                            className="shrink-0"
                          >
                            <Check size={20} style={{ color: "var(--accent)" }} />
                          </motion.div>
                        )}
                      </motion.button>
                    );
                  })}
                </div>
              </>
            )}

            {/* Step 3: Demo training (chat-based) */}
            {step === 3 && (
              <>
                <h2 className="font-display text-xl font-bold tracking-wider mb-1 text-center" style={{ color: "var(--text-primary)" }}>Охота начинается</h2>
                <p className="text-sm mb-6 text-center" style={{ color: "var(--text-muted)" }}>Пробная тренировка — напиши ответ клиенту</p>
                <TrialDialog />
              </>
            )}
          </motion.div>
        </AnimatePresence>

        {/* Navigation */}
        <div className="mt-6 flex justify-between">
          {step > 1 ? (
            <Button variant="ghost" onClick={() => setStep(step - 1)} icon={<ChevronLeft size={16} />}>
              Назад
            </Button>
          ) : <div />}

          {step < totalSteps ? (
            <Button onClick={() => setStep(step + 1)} disabled={!canAdvance()} iconRight={<ArrowRight size={16} />}>
              Далее
            </Button>
          ) : (
            <Button variant="primary" onClick={handleFinish} loading={loading} icon={<Crosshair size={16} />}>
              Начать охоту
            </Button>
          )}
        </div>

        {submitError && (
          <p className="mt-3 text-center text-sm" style={{ color: "var(--danger)" }}>
            {submitError}
          </p>
        )}

        {/* Step counter */}
        <p className="mt-4 text-center font-mono text-xs tracking-wider" style={{ color: "var(--text-muted)" }}>
          ШАГ {step} ИЗ {totalSteps}
        </p>
      </div>
    </div>
  );
}
