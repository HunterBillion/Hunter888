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
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { AppIcon } from "@/components/ui/AppIcon";
import { logger } from "@/lib/logger";

// ── Steps config ───────────────────────────────────────────
const STEPS = [
  { id: 1, label: "Профиль", icon: User },
  { id: 2, label: "Настройки", icon: Settings },
  { id: 3, label: "Микрофон", icon: Mic },
  { id: 4, label: "Тренировка", icon: Target },
  { id: 5, label: "Демо", icon: MessageCircle },
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

// ── D1: Animated SVG illustrations ─────────────────────────
function StepIllustration({ step }: { step: number }) {
  const illustrations: Record<number, React.ReactNode> = {
    1: (
      <svg viewBox="0 0 120 120" className="w-24 h-24">
        <motion.circle cx="60" cy="40" r="18" fill="none" stroke="var(--accent)" strokeWidth="2"
          initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1 }} />
        <motion.path d="M30 95 C30 70 90 70 90 95" fill="none" stroke="var(--accent)" strokeWidth="2"
          initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1, delay: 0.3 }} />
        <motion.circle cx="60" cy="40" r="5" fill="var(--accent)"
          initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ delay: 0.8, type: "spring" }} />
      </svg>
    ),
    2: (
      <svg viewBox="0 0 120 120" className="w-24 h-24">
        <motion.rect x="25" y="25" width="70" height="70" rx="12" fill="none" stroke="var(--accent)" strokeWidth="2"
          initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1 }} />
        <motion.circle cx="48" cy="55" r="4" fill="var(--accent)"
          initial={{ scale: 0 }} animate={{ scale: [0, 1.3, 1] }} transition={{ delay: 0.5, duration: 0.5 }} />
        <motion.circle cx="72" cy="55" r="4" fill="var(--accent)"
          initial={{ scale: 0 }} animate={{ scale: [0, 1.3, 1] }} transition={{ delay: 0.7, duration: 0.5 }} />
        <motion.path d="M45 72 Q60 82 75 72" fill="none" stroke="var(--accent)" strokeWidth="2"
          initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ delay: 0.9, duration: 0.5 }} />
      </svg>
    ),
    3: (
      <svg viewBox="0 0 120 120" className="w-24 h-24">
        <motion.rect x="50" y="20" width="20" height="45" rx="10" fill="none" stroke="var(--accent)" strokeWidth="2"
          initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 0.8 }} />
        <motion.path d="M35 55 Q35 80 60 80 Q85 80 85 55" fill="none" stroke="var(--accent)" strokeWidth="2"
          initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ delay: 0.5, duration: 0.7 }} />
        <motion.line x1="60" y1="80" x2="60" y2="100" stroke="var(--accent)" strokeWidth="2"
          initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ delay: 1 }} />
        {[0, 1, 2].map((i) => (
          <motion.circle key={i} cx={60} cy={42} r={22 + i * 8} fill="none" stroke="var(--accent)" strokeWidth="1" opacity={0.2}
            animate={{ scale: [1, 1.1, 1], opacity: [0.1, 0.3, 0.1] }}
            transition={{ duration: 1.5, repeat: Infinity, delay: i * 0.3 }} />
        ))}
      </svg>
    ),
    4: (
      <svg viewBox="0 0 120 120" className="w-24 h-24">
        <motion.path d="M60 20 L95 50 L80 95 L40 95 L25 50 Z" fill="none" stroke="var(--accent)" strokeWidth="2"
          initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1.2 }} />
        <motion.circle cx="60" cy="60" r="8" fill="var(--accent)" opacity={0.3}
          animate={{ r: [8, 12, 8], opacity: [0.2, 0.5, 0.2] }}
          transition={{ duration: 2, repeat: Infinity }} />
        <motion.circle cx="60" cy="60" r="3" fill="var(--accent)"
          initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ delay: 1, type: "spring" }} />
      </svg>
    ),
    5: (
      <svg viewBox="0 0 120 120" className="w-24 h-24">
        <motion.rect x="15" y="25" width="55" height="35" rx="8" fill="none" stroke="var(--accent)" strokeWidth="2"
          initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 0.6 }} />
        <motion.rect x="50" y="60" width="55" height="35" rx="8" fill="none" stroke="var(--magenta)" strokeWidth="2"
          initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ delay: 0.4, duration: 0.6 }} />
        {[0, 1, 2].map((i) => (
          <motion.circle key={i} cx={28 + i * 12} cy={42} r="2" fill="var(--accent)"
            initial={{ scale: 0 }} animate={{ scale: [0, 1, 0] }}
            transition={{ delay: 0.8 + i * 0.2, duration: 0.8, repeat: Infinity, repeatDelay: 1 }} />
        ))}
      </svg>
    ),
  };
  return <div className="flex justify-center mb-6">{illustrations[step]}</div>;
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
          style={{ background: "rgba(61,220,132,0.05)", border: "1px solid rgba(61,220,132,0.2)" }}
        >
          <Check size={32} style={{ color: "var(--success)" }} />
          <span className="font-medium" style={{ color: "var(--success)" }}>Микрофон работает!</span>
        </motion.div>
      )}

      {status === "error" && (
        <motion.div initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
          className="rounded-xl p-6 flex flex-col items-center gap-3"
          style={{ background: "rgba(229,72,77,0.05)", border: "1px solid rgba(229,72,77,0.2)" }}
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
function TrialDialog() {
  const [messages, setMessages] = useState<{ role: "system" | "bot" | "user"; text: string }[]>(DEMO_MESSAGES);
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
      setMessages(prev => [...prev, {
        role: "bot" as const,
        text: "Хм, ладно, слушаю. У вас 30 секунд. Что за компания и зачем звоните?",
      }]);
      setResponded(true);
    }, 2000);
  };

  return (
    <div className="space-y-3">
      <div className="rounded-xl p-4 space-y-3 max-h-[200px] overflow-y-auto" style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)" }}>
        {messages.map((msg, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.1 }}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className="rounded-lg px-3 py-2 text-sm max-w-[80%]"
              style={{
                background: msg.role === "user" ? "var(--accent)" : msg.role === "system" ? "var(--accent-muted)" : "var(--glass-bg)",
                color: msg.role === "user" ? "white" : msg.role === "system" ? "var(--accent)" : "var(--text-primary)",
                border: msg.role === "bot" ? "1px solid var(--border-color)" : "none",
              }}
            >
              {msg.role === "system" && <span className="font-mono text-xs block mb-1" style={{ color: "var(--text-muted)" }}>СИСТЕМА</span>}
              {msg.text}
            </div>
          </motion.div>
        ))}
        {botTyping && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex gap-1 px-3">
            {[0, 1, 2].map(i => (
              <motion.span key={i} className="w-1.5 h-1.5 rounded-full" style={{ background: "var(--accent)" }}
                animate={{ y: [0, -4, 0] }} transition={{ duration: 0.5, repeat: Infinity, delay: i * 0.15 }} />
            ))}
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
          />
          <Button size="sm" onClick={sendMessage} disabled={!input.trim()} icon={<ArrowRight size={16} />} />
        </div>
      )}

      {!responded && (
        <p className="text-xs text-center" style={{ color: "var(--text-muted)" }}>
          <Lightbulb size={14} className="inline" /> {DEMO_HINTS[0]}
        </p>
      )}

      {responded && (
        <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-xs text-center" style={{ color: "var(--success)" }}>
          <CheckCircle size={16} className="inline" /> Отлично! Вы готовы к настоящим тренировкам
        </motion.p>
      )}
    </div>
  );
}

// ── Main Onboarding Page ───────────────────────────────────
export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);

  // Form data
  const [role, setRole] = useState<"manager" | "rop">("manager");
  const [team, setTeam] = useState("");
  const [specialization, setSpecialization] = useState("");
  const [experience, setExperience] = useState("");
  const [ttsEnabled, setTtsEnabled] = useState(true);
  const [notifications, setNotifications] = useState(true);
  const [micOk, setMicOk] = useState<boolean | null>(null);
  const [trainingMode, setTrainingMode] = useState("structured");

  const canAdvance = () => {
    if (step === 1) return !!role && team !== "" && specialization !== "" && experience !== "";
    if (step === 2) return true;
    if (step === 3) return micOk !== null;
    if (step === 4) return trainingMode !== "";
    if (step === 5) return true;
    return false;
  };

  const handleFinish = async () => {
    setLoading(true);
    try {
      await api.post("/users/me/preferences", {
        role,
        team,
        specialization,
        experience_level: experience,
        tts_enabled: ttsEnabled,
        notifications,
        training_mode: trainingMode,
      });
    } catch (err) { logger.warn("Failed to save preferences, proceeding:", err); }
    router.push("/home");
  };

  const totalSteps = STEPS.length;
  const progressPct = ((step - 1) / (totalSteps - 1)) * 100;

  return (
    <div className="relative min-h-screen flex items-center justify-center px-4 py-8 overflow-hidden" style={{ background: "var(--bg-primary)" }}>
      <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] rounded-full opacity-10 pointer-events-none" style={{ background: "radial-gradient(circle, var(--accent) 0%, transparent 60%)" }} />

      {/* Theme toggle */}
      <div className="fixed right-4 top-4 z-50">
        <ThemeToggle />
      </div>

      <div className="w-full max-w-lg">
        {/* D5: Visual stepper */}
        <div className="mb-8">
          <div className="flex items-center justify-between relative">
            {/* Line connecting steps */}
            <div className="absolute top-5 left-[10%] right-[10%] h-[2px]" style={{ background: "var(--border-color)" }}>
              <motion.div
                className="h-full rounded-full"
                style={{ background: "var(--accent)" }}
                animate={{ width: `${progressPct}%` }}
                transition={{ duration: 0.5 }}
              />
            </div>

            {STEPS.map((s) => {
              const Icon = s.icon;
              const isActive = s.id === step;
              const isDone = s.id < step;
              return (
                <div key={s.id} className="flex flex-col items-center gap-1.5 relative z-10">
                  <motion.div
                    className="flex h-10 w-10 items-center justify-center rounded-full transition-all"
                    style={{
                      background: isDone ? "var(--accent)" : isActive ? "var(--bg-primary)" : "var(--bg-secondary)",
                      border: `2px solid ${isDone ? "var(--accent)" : isActive ? "var(--accent)" : "var(--border-color)"}`,
                      boxShadow: isActive ? "0 0 15px var(--accent-glow)" : "none",
                    }}
                    animate={{ scale: isActive ? 1.15 : 1 }}
                    transition={{ type: "spring", stiffness: 300 }}
                  >
                    {isDone ? (
                      <Check size={16} className="text-white" />
                    ) : (
                      <Icon size={16} style={{ color: isActive ? "var(--accent)" : "var(--text-muted)" }} />
                    )}
                  </motion.div>
                  <span
                    className="font-mono text-xs tracking-wider"
                    style={{ color: isActive ? "var(--accent)" : isDone ? "var(--text-secondary)" : "var(--text-muted)" }}
                  >
                    {s.label}
                  </span>
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
                <h2 className="font-display text-xl font-bold tracking-wider mb-1 text-center" style={{ color: "var(--text-primary)" }}>
                  Расскажите о себе
                </h2>
                <p className="text-sm mb-6 text-center" style={{ color: "var(--text-muted)" }}>Подберём оптимальные сценарии</p>

                <div className="space-y-5">
                  <div>
                    <label className="vh-label">Ваша роль</label>
                    <div className="grid grid-cols-2 gap-3">
                      {[
                        { value: "manager" as const, label: "Менеджер", desc: "Тренировки, звонки, рейтинг", icon: "🎯" },
                        { value: "rop" as const, label: "Руководитель (РОП)", desc: "Аналитика, команда, контроль", icon: "📊" },
                      ].map((r) => (
                        <motion.button
                          key={r.value}
                          type="button"
                          onClick={() => setRole(r.value)}
                          className="rounded-xl px-4 py-4 text-left flex items-center gap-3"
                          style={{
                            background: role === r.value ? "var(--accent-muted)" : "var(--input-bg)",
                            border: `1.5px solid ${role === r.value ? "var(--accent)" : "var(--border-color)"}`,
                            boxShadow: role === r.value ? "0 0 16px var(--accent-glow)" : "none",
                          }}
                          whileTap={{ scale: 0.97 }}
                        >
                          <AppIcon emoji={r.icon} size={28} />
                          <div>
                            <div className="font-display font-bold text-sm" style={{ color: role === r.value ? "var(--accent)" : "var(--text-primary)" }}>{r.label}</div>
                            <div className="text-xs" style={{ color: "var(--text-muted)" }}>{r.desc}</div>
                          </div>
                        </motion.button>
                      ))}
                    </div>
                  </div>
                  <div>
                    <label className="vh-label">Команда</label>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {TEAMS.map(t => (
                        <motion.button key={t} type="button" onClick={() => setTeam(t)}
                          className="rounded-xl px-3 py-2.5 text-sm text-left"
                          style={{
                            background: team === t ? "var(--accent-muted)" : "var(--input-bg)",
                            border: `1px solid ${team === t ? "var(--accent)" : "var(--border-color)"}`,
                            color: team === t ? "var(--accent)" : "var(--text-secondary)",
                          }}
                          whileTap={{ scale: 0.97 }}
                        >{t}</motion.button>
                      ))}
                    </div>
                  </div>
                  <div>
                    <label className="vh-label">Специализация</label>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {SPECIALIZATIONS.map(s => (
                        <motion.button key={s.value} type="button" onClick={() => setSpecialization(s.value)}
                          className="rounded-xl px-3 py-2.5 text-left flex items-center gap-2"
                          style={{
                            background: specialization === s.value ? "var(--accent-muted)" : "var(--input-bg)",
                            border: `1px solid ${specialization === s.value ? "var(--accent)" : "var(--border-color)"}`,
                          }}
                          whileTap={{ scale: 0.97 }}
                        >
                          <AppIcon emoji={s.icon} size={20} />
                          <div>
                            <div className="font-medium text-xs" style={{ color: specialization === s.value ? "var(--accent)" : "var(--text-primary)" }}>{s.label}</div>
                            <div className="text-xs" style={{ color: "var(--text-muted)" }}>{s.desc}</div>
                          </div>
                        </motion.button>
                      ))}
                    </div>
                  </div>
                  <div>
                    <label className="vh-label">Опыт</label>
                    <div className="space-y-2">
                      {EXP_LEVELS.map(e => (
                        <motion.button key={e.value} type="button" onClick={() => setExperience(e.value)}
                          className="w-full rounded-xl px-4 py-3 text-left flex items-center gap-3"
                          style={{
                            background: experience === e.value ? "var(--accent-muted)" : "var(--input-bg)",
                            border: `1px solid ${experience === e.value ? "var(--accent)" : "var(--border-color)"}`,
                          }}
                          whileTap={{ scale: 0.97 }}
                        >
                          <AppIcon emoji={e.icon} size={24} />
                          <div>
                            <div className="font-medium text-sm" style={{ color: experience === e.value ? "var(--accent)" : "var(--text-primary)" }}>{e.label}</div>
                            <div className="text-xs" style={{ color: "var(--text-muted)" }}>{e.desc}</div>
                          </div>
                        </motion.button>
                      ))}
                    </div>
                  </div>
                </div>
              </>
            )}

            {/* Step 2: Settings */}
            {step === 2 && (
              <>
                <h2 className="font-display text-xl font-bold tracking-wider mb-1 text-center" style={{ color: "var(--text-primary)" }}>Настройки</h2>
                <p className="text-sm mb-6 text-center" style={{ color: "var(--text-muted)" }}>Настройте интерфейс</p>
                <div className="space-y-3">
                  {[
                    { label: "Озвучка AI-клиента", desc: "Голосовые ответы", icon: Volume2, value: ttsEnabled, toggle: () => setTtsEnabled(!ttsEnabled) },
                    { label: "Уведомления", desc: "Напоминания", icon: Bell, value: notifications, toggle: () => setNotifications(!notifications) },
                  ].map(item => (
                    <div key={item.label} className="flex items-center justify-between rounded-xl p-4" style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)" }}>
                      <div className="flex items-center gap-3">
                        <item.icon size={18} style={{ color: "var(--accent)" }} />
                        <div>
                          <div className="font-medium text-sm" style={{ color: "var(--text-primary)" }}>{item.label}</div>
                          <div className="text-xs" style={{ color: "var(--text-muted)" }}>{item.desc}</div>
                        </div>
                      </div>
                      <motion.div
                        className="relative w-11 h-6 rounded-full cursor-pointer"
                        style={{ background: item.value ? "var(--accent)" : "var(--border-color)" }}
                        onClick={item.toggle}
                        whileTap={{ scale: 0.95 }}
                      >
                        <motion.div className="absolute top-1 w-4 h-4 rounded-full bg-white"
                          animate={{ left: item.value ? 24 : 4 }}
                          transition={{ type: "spring", stiffness: 500, damping: 30 }} />
                      </motion.div>
                    </div>
                  ))}

                  {/* D4: Theme selection */}
                  <div className="rounded-xl p-4" style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)" }}>
                    <div className="flex items-center gap-3 mb-3">
                      <Sun size={18} style={{ color: "var(--accent)" }} />
                      <div>
                        <div className="font-medium text-sm" style={{ color: "var(--text-primary)" }}>Тема оформления</div>
                        <div className="text-xs" style={{ color: "var(--text-muted)" }}>Выберите комфортный стиль</div>
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <ThemeToggle />
                      <span className="text-xs self-center" style={{ color: "var(--text-muted)" }}>Нажмите для переключения</span>
                    </div>
                  </div>
                </div>
              </>
            )}

            {/* Step 3: D3 Mic test */}
            {step === 3 && (
              <>
                <h2 className="font-display text-xl font-bold tracking-wider mb-1 text-center" style={{ color: "var(--text-primary)" }}>Проверка микрофона</h2>
                <p className="text-sm mb-6 text-center" style={{ color: "var(--text-muted)" }}>Для голосового ввода</p>
                <MicTest onResult={(ok) => setMicOk(ok)} />
                {micOk === null && (
                  <button type="button" onClick={() => setMicOk(false)}
                    className="mt-4 w-full text-center text-xs" style={{ color: "var(--text-muted)" }}>
                    Пропустить — буду печатать
                  </button>
                )}
              </>
            )}

            {/* Step 4: Training mode */}
            {step === 4 && (
              <>
                <h2 className="font-display text-xl font-bold tracking-wider mb-1 text-center" style={{ color: "var(--text-primary)" }}>Режим тренировки</h2>
                <p className="text-sm mb-6 text-center" style={{ color: "var(--text-muted)" }}>Формат обучения</p>
                <div className="space-y-3">
                  {MODES.map(m => (
                    <motion.button key={m.value} type="button" onClick={() => setTrainingMode(m.value)}
                      className="w-full rounded-xl px-5 py-4 text-left flex items-center gap-3"
                      style={{
                        background: trainingMode === m.value ? "var(--accent-muted)" : "var(--input-bg)",
                        border: `1px solid ${trainingMode === m.value ? "var(--accent)" : "var(--border-color)"}`,
                        boxShadow: trainingMode === m.value ? "0 0 15px var(--accent-glow)" : "none",
                      }}
                      whileHover={{ y: -2 }} whileTap={{ scale: 0.98 }}
                    >
                      <AppIcon emoji={m.icon} size={28} />
                      <div>
                        <div className="font-medium text-sm" style={{ color: trainingMode === m.value ? "var(--accent)" : "var(--text-primary)" }}>{m.label}</div>
                        <div className="text-xs" style={{ color: "var(--text-muted)" }}>{m.desc}</div>
                      </div>
                    </motion.button>
                  ))}
                </div>
              </>
            )}

            {/* Step 5: D2 Trial dialog */}
            {step === 5 && (
              <>
                <h2 className="font-display text-xl font-bold tracking-wider mb-1 text-center" style={{ color: "var(--text-primary)" }}>Пробный диалог</h2>
                <p className="text-sm mb-6 text-center" style={{ color: "var(--text-muted)" }}>Попробуйте перед стартом</p>
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

        {/* Step counter */}
        <p className="mt-4 text-center font-mono text-xs tracking-wider" style={{ color: "var(--text-muted)" }}>
          ШАГ {step} ИЗ {totalSteps}
        </p>
      </div>
    </div>
  );
}
