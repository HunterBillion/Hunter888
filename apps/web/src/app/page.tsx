"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowRight,
  Mail,
  AlertCircle,
  User,
  X as XIcon,
  Brain,
  BarChart3,
  Trophy,
  Target,
  CheckCircle2,
  ShieldCheck,
} from "lucide-react";
import dynamic from "next/dynamic";
import { FishermanError } from "@/components/errors/FishermanError";
import { getToken, setTokens } from "@/lib/auth";
import { api } from "@/lib/api";
import { getApiBaseUrl } from "@/lib/public-origin";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { PasswordInput } from "@/components/ui/PasswordInput";
import { PasswordChecklist, isPasswordValid } from "@/components/ui/PasswordChecklist";
import { EASE_SNAP } from "@/lib/constants";

const WaveScene = dynamic(
  () => import("@/components/landing/WaveScene").then((m) => m.WaveScene),
  { ssr: false },
);

type Panel = "login" | "register" | null;
type ForgotMode = "idle" | "form" | "sent";

/* ─────────────────────────────── constants ────────────────────────────── */
const FEATURES = [
  {
    icon: Brain,
    title: "AI-тренинг",
    sub: "Переговоры с ИИ",
    desc: "Сотни реальных сценариев. Клиент возражает, давит, торгуется — ты учишься отвечать без скриптов и без страха.",
    num: "01",
  },
  {
    icon: BarChart3,
    title: "Аналитика",
    sub: "Видишь каждую ошибку",
    desc: "После каждой сессии — детальный разбор: темп речи, паузы, упущенные возражения. Данные, а не ощущения.",
    num: "02",
  },
  {
    icon: Trophy,
    title: "Рейтинги",
    sub: "Командная игра",
    desc: "Живая таблица лидеров. Лучшие охотники видны всем — это мотивирует сильнее любого KPI.",
    num: "03",
  },
] as const;

const STATS = [
  { target: 500, suffix: "+", label: "Сценариев" },
  { target: 98,  suffix: "%", label: "Точность ИИ" },
  { target: 3,   suffix: "×", label: "Рост конверсии" },
];

const TRUST = [
  "14 дней бесплатно",
  "Без кредитной карты",
  "Готово за 5 минут",
];

const SSO_BUTTONS = [
  {
    label: "Google",
    endpoint: "/auth/google/login",
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24">
        <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4" />
        <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
        <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05" />
        <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
      </svg>
    ),
  },
  {
    label: "Yandex",
    endpoint: "/auth/yandex/login",
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24">
        <path d="M2 12C2 6.48 6.48 2 12 2s10 4.48 10 10-4.48 10-10 10S2 17.52 2 12z" fill="#FC3F1D" />
        <path d="M13.32 17.5h-1.88V7.38h-.97c-1.57 0-2.39.8-2.39 1.95 0 1.3.59 1.9 1.8 2.7l1 .65-2.9 4.82H6l2.62-4.33C7.37 12.26 6.56 11.22 6.56 9.5c0-2.07 1.45-3.5 4-3.5h2.76V17.5z" fill="white" />
      </svg>
    ),
  },
];


/* ── CountUp: eased counter animation triggered by IntersectionObserver ─ */
function CountUp({ target, suffix }: { target: number; suffix: string }) {
  const [count, setCount] = useState(0);
  const ref = useRef<HTMLSpanElement>(null);
  const started = useRef(false);

  const animate = useCallback(() => {
    const duration = 1800;
    const start = performance.now();
    const step = (now: number) => {
      const progress = Math.min((now - start) / duration, 1);
      // ease-out cubic
      const ease = 1 - Math.pow(1 - progress, 3);
      setCount(Math.round(ease * target));
      if (progress < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }, [target]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !started.current) {
          started.current = true;
          animate();
        }
      },
      { threshold: 0.5 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [animate]);

  return <span ref={ref}>{count}{suffix}</span>;
}

/* ─────────────────────────────── component ────────────────────────────── */
export default function Home() {
  const router = useRouter();
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [activePanel, setActivePanel] = useState<Panel>(null);
  const [networkError, setNetworkError] = useState(false);


  // Main form
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [rememberMe, setRememberMe] = useState(true);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // Forgot password
  const [forgotMode, setForgotMode] = useState<ForgotMode>("idle");
  const [forgotEmail, setForgotEmail] = useState("");
  const [forgotLoading, setForgotLoading] = useState(false);

  useEffect(() => {
    const token = getToken();
    if (!token) { setCheckingAuth(false); return; }
    api.get("/consent/status")
      .then((d) => router.replace(d.all_accepted ? "/home" : "/consent"))
      .catch(() => router.replace("/home"));
  }, [router]);

  const openPanel = (panel: Panel) => {
    setActivePanel(panel);
    setError("");
    setEmail(""); setPassword(""); setConfirmPassword(""); setFullName("");
    setForgotMode("idle"); setForgotEmail("");
  };
  const closePanel = () => { setActivePanel(null); setError(""); setForgotMode("idle"); };

  // Close auth drawer on Escape key
  useEffect(() => {
    if (!activePanel) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") closePanel();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [activePanel]); // eslint-disable-line react-hooks/exhaustive-deps -- closePanel is a stable setState wrapper

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (activePanel === "register") {
      if (!fullName.trim()) { setError("Укажите имя"); return; }
      if (!isPasswordValid(password)) { setError("Пароль не соответствует требованиям"); return; }
      if (password !== confirmPassword) { setError("Пароли не совпадают"); return; }
    }
    setLoading(true);
    try {
      if (activePanel === "login") {
        const data = await api.post("/auth/login", { email: email.trim(), password });
        setTokens(data.access_token, data.refresh_token);
        router.push(data.must_change_password ? "/change-password" : "/home");
      } else {
        const data = await api.post("/auth/register", {
          email: email.trim(), password, full_name: fullName.trim(),
        });
        setTokens(data.access_token, data.refresh_token);
        router.push("/onboarding");
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Ошибка";
      if (msg.includes("недоступен") || msg.includes("fetch") || msg.includes("network")) {
        setNetworkError(true);
      } else { setError(msg); }
    } finally { setLoading(false); }
  };

  const handleForgot = async () => {
    if (!forgotEmail.trim()) return;
    setForgotLoading(true);
    try {
      await fetch(`${getApiBaseUrl()}/api/auth/forgot-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: forgotEmail.trim() }),
      });
    } catch { /* silent — always show success for security */ }
    setForgotLoading(false);
    setForgotMode("sent");
  };

  const handleSso = async (endpoint: string, label: string) => {
    try {
      const data = await api.get(endpoint);
      if (data?.url) {
        const { validateOAuthUrl } = await import("@/lib/sanitize");
        const safeUrl = validateOAuthUrl(data.url);
        if (safeUrl) {
          window.location.href = safeUrl;
        } else {
          setError(`Недоверенный OAuth URL от ${label}`);
        }
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : `${label} OAuth недоступен`);
    }
  };

  /* ── early returns ── */
  if (networkError) {
    return (
      <FishermanError
        onRetry={() => { setNetworkError(false); setError(""); }}
        message="Похоже, рыба сегодня не клюёт..."
      />
    );
  }
  if (checkingAuth) {
    return (
      <div className="flex min-h-screen items-center justify-center" style={{ background: "var(--bg-primary)" }}>
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex items-center gap-3">
          <div className="w-2 h-2 rounded-full animate-ping" style={{ background: "var(--accent)" }} />
          <span className="font-mono text-sm tracking-wider" style={{ color: "var(--text-muted)" }}>ИНИЦИАЛИЗАЦИЯ...</span>
        </motion.div>
      </div>
    );
  }

  const passwordsMatch = confirmPassword.length === 0 || password === confirmPassword;

  /* ═══════════════════════════ render ═══════════════════════════════════ */
  return (
    <div style={{ background: "var(--bg-primary)" }}>

      {/* ═══ HEADER ═══════════════════════════════════════════════════════ */}
      <header className="fixed top-0 left-0 right-0 z-[100]">
        <div
          className="absolute inset-0 pointer-events-none"
          style={{ background: "linear-gradient(180deg, var(--bg-primary) 55%, transparent 100%)" }}
        />
        <div className="relative z-10 flex items-center justify-between px-4 sm:px-6 md:px-10 py-4 sm:py-5 max-w-6xl mx-auto">
          <div className="flex items-center gap-1">
            <span className="font-display font-black text-lg sm:text-xl tracking-[0.18em]" style={{ color: "var(--text-primary)" }}>
              X<span style={{ color: "var(--accent)" }}>·</span>HUNTER
            </span>
          </div>
          <div className="flex items-center gap-1.5 sm:gap-2.5">
            <ThemeToggle />
            <button onClick={() => openPanel("login")} className="btn-neon px-3 sm:px-5 py-1.5 sm:py-2 text-xs sm:text-sm">
              Войти
            </button>
            <motion.button
              onClick={() => openPanel("register")}
              className="btn-neon px-3 sm:px-5 py-1.5 sm:py-2 text-xs sm:text-sm flex items-center gap-1"
              whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
            >
              Начать <ArrowRight size={13} />
            </motion.button>
          </div>
        </div>
      </header>

      {/* ═══ SECTION 1 — HERO ═════════════════════════════════════════════ */}
      <section className="relative min-h-screen flex flex-col items-center justify-center overflow-hidden">

        {/* Wave background */}
        <div className="absolute inset-0 z-0"><WaveScene /></div>

        {/* 🟡 Darkening overlay — makes typography readable */}
        <div
          className="absolute inset-0 z-[1] pointer-events-none"
          style={{ background: "linear-gradient(180deg, rgba(0,0,0,0.35) 0%, rgba(0,0,0,0.15) 50%, rgba(0,0,0,0.4) 100%)" }}
        />

        {/* Accent radial glow */}
        <div
          className="absolute inset-0 z-[2] pointer-events-none"
          style={{ background: "radial-gradient(ellipse at 50% 55%, rgba(99,102,241,0.22) 0%, transparent 55%)" }}
        />

        {/* Scanlines */}
        <div className="fixed inset-0 scanlines z-[3] opacity-[0.04] mix-blend-overlay pointer-events-none" />

        {/* Grain/noise texture — SVG feTurbulence overlay */}
        <div
          className="absolute inset-0 z-[3] pointer-events-none"
          style={{
            backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='1'/%3E%3C/svg%3E")`,
            backgroundRepeat: "repeat",
            backgroundSize: "128px 128px",
            opacity: 0.035,
            mixBlendMode: "overlay",
          }}
        />

        {/* ── Hero content ── */}
        <div className="relative z-[4] text-center px-4 sm:px-6 w-full max-w-4xl mx-auto pt-16 sm:pt-20">

          {/* Badge */}
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="inline-flex items-center gap-2 rounded-full px-4 py-1.5 mb-7"
            style={{ background: "rgba(99,102,241,0.12)", border: "1px solid rgba(99,102,241,0.32)" }}
          >
            <motion.span
              className="w-1.5 h-1.5 rounded-full"
              style={{ background: "var(--accent)" }}
              animate={{ opacity: [1, 0.25, 1] }}
              transition={{ duration: 1.8, repeat: Infinity }}
            />
            <span className="font-display text-sm font-bold tracking-[0.12em] italic" style={{ color: "var(--accent)", textShadow: "0 0 20px rgba(99,102,241,0.4)" }}>
              Выбор игры, важнее самой игры
            </span>
          </motion.div>

          {/* Title X·HUNTER */}
          <motion.div
            initial={{ opacity: 0, scale: 0.88 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.2, duration: 0.85, ease: EASE_SNAP }}
          >
            <h1 className="font-display font-black leading-none">
              <span
                className="block select-none"
                style={{
                  fontSize: "clamp(5rem, 20vw, 16rem)",
                  lineHeight: 0.88,
                  color: "transparent",
                  WebkitTextStroke: "1.5px var(--accent)",
                  filter: "drop-shadow(0 0 40px var(--accent-glow))",
                }}
              >
                X
              </span>
              <span
                className="block tracking-[0.28em]"
                style={{ fontSize: "clamp(1.4rem, 5.5vw, 4.5rem)", color: "var(--text-primary)" }}
              >
                HUNTER
              </span>
            </h1>
          </motion.div>

          {/* 🟡 UVP — переписан, конкретная боль + решение */}
          <motion.p
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.5 }}
            className="text-sm md:text-base max-w-sm mx-auto mt-5 mb-7"
            style={{ color: "var(--text-secondary)", lineHeight: 1.8 }}
          >
            Менеджеры теряют сделки на возражениях.{" "}
            <span style={{ color: "var(--text-primary)", fontWeight: 500 }}>
              X·Hunter учит их работать — с ИИ, данными и живым рейтингом.
            </span>
          </motion.p>

          {/* Stats — count-up on viewport enter */}
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.62 }}
            className="flex items-stretch justify-center mb-5"
          >
            {STATS.map(({ target, suffix, label }, i) => (
              <div key={label} className="flex items-stretch">
                {i > 0 && (
                  <div
                    className="w-px self-stretch mx-4 sm:mx-6 md:mx-8"
                    style={{ background: "var(--border-color)", opacity: 0.45 }}
                  />
                )}
                <div className="text-center">
                  <div
                    className="font-display font-black leading-none"
                    style={{
                      fontSize: "clamp(1.6rem, 6vw, 2.5rem)",
                      color: "var(--accent)",
                      textShadow: "0 0 24px var(--accent-glow)",
                    }}
                  >
                    <CountUp target={target} suffix={suffix} />
                  </div>
                  <div
                    className="font-mono tracking-[0.2em] mt-1.5 uppercase"
                    style={{ fontSize: "clamp(8px, 1.8vw, 11px)", color: "var(--text-muted)" }}
                  >
                    {label}
                  </div>
                </div>
              </div>
            ))}
          </motion.div>

          {/* 🟢 Trust strip */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.78 }}
            className="flex flex-wrap items-center justify-center gap-x-5 gap-y-1.5"
          >
            {TRUST.map((t) => (
              <span
                key={t}
                className="flex items-center gap-2 text-sm sm:text-base"
                style={{ color: "var(--text-secondary)" }}
              >
                <CheckCircle2 size={16} style={{ color: "var(--neon-green)", flexShrink: 0 }} />
                {t}
              </span>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ═══ TRANSITION ════════════════════════════════════════════════════ */}
      <div
        aria-hidden
        style={{
          height: "120px",
          marginTop: "-120px",
          position: "relative",
          zIndex: 5,
          background: "linear-gradient(180deg, transparent 0%, var(--bg-secondary) 100%)",
          pointerEvents: "none",
        }}
      />


      {/* ═══ SECTION 2 — FEATURES (EDITORIAL) ════════════════════════════ */}
      <section
        className="relative overflow-hidden"
        style={{ background: "var(--bg-secondary)", paddingBottom: "7rem" }}
      >
        <div
          className="absolute inset-0 opacity-[0.02] pointer-events-none"
          style={{
            backgroundImage: `linear-gradient(var(--text-primary) 1px, transparent 1px),
                              linear-gradient(90deg, var(--text-primary) 1px, transparent 1px)`,
            backgroundSize: "80px 80px",
          }}
        />

        <div className="relative z-10 max-w-6xl mx-auto px-5 sm:px-8 md:px-10">
          <div className="grid lg:grid-cols-[2fr_3fr] gap-10 md:gap-16 lg:gap-24 pt-14 sm:pt-20 lg:pt-28">

            {/* Left: sticky context */}
            <motion.div
              initial={{ opacity: 0, x: -20 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.7 }}
              className="lg:sticky lg:top-32 lg:self-start"
            >
              <span
                className="font-mono text-xs tracking-[0.5em] uppercase block mb-6"
                style={{ color: "var(--accent)" }}
              >
                Инструменты
              </span>
              <h2
                className="font-display font-black leading-[1.05]"
                style={{ fontSize: "clamp(2rem, 4vw, 3.25rem)", color: "var(--text-primary)" }}
              >
                Три системы.<br />
                <span style={{ color: "var(--accent)" }}>Один охотник.</span>
              </h2>
              <p
                className="mt-5 text-sm leading-relaxed max-w-[260px]"
                style={{ color: "var(--text-muted)" }}
              >
                Всё что нужно для системного роста — от первого звонка до закрытой сделки.
              </p>

              {/* 🟢 Left-side trust badge */}
              <div
                className="mt-8 inline-flex items-center gap-2 rounded-xl px-4 py-3"
                style={{
                  background: "rgba(0,255,148,0.05)",
                  border: "1px solid rgba(0,255,148,0.15)",
                }}
              >
                <ShieldCheck size={14} style={{ color: "var(--neon-green)", flexShrink: 0 }} />
                <span className="text-xs leading-snug" style={{ color: "var(--text-muted)" }}>
                  Данные защищены.<br />Никакой передачи третьим лицам.
                </span>
              </div>
            </motion.div>

            {/* Right: editorial numbered list */}
            <div>
              {FEATURES.map(({ icon: Icon, title, sub, desc, num }, i) => (
                <motion.div
                  key={title}
                  initial={{ opacity: 0, y: 24 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: i * 0.1, duration: 0.65 }}
                >
                  <div style={{ height: "1px", background: "var(--border-color)", opacity: 0.5 }} />
                  <div className="group flex items-start gap-6 py-8 cursor-default">
                    <span
                      className="font-mono text-xs tracking-wider pt-0.5 flex-shrink-0 w-8 transition-colors duration-300 group-hover:text-accent"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {num}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-3 mb-1.5">
                        <h3
                          className="font-display font-bold transition-colors duration-300"
                          style={{ fontSize: "clamp(1.1rem, 2vw, 1.4rem)", color: "var(--text-primary)" }}
                        >
                          {title}
                        </h3>
                        <span
                          className="font-mono text-xs tracking-wider uppercase px-2 py-0.5 rounded"
                          style={{
                            color: "var(--text-muted)",
                            background: "var(--bg-tertiary)",
                            border: "1px solid var(--border-color)",
                          }}
                        >
                          {sub}
                        </span>
                      </div>
                      <p className="text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>{desc}</p>
                    </div>
                    <div
                      className="flex-shrink-0 w-10 h-10 rounded-xl flex items-center justify-center mt-0.5 opacity-35 group-hover:opacity-75 transition-opacity duration-300"
                      style={{ background: "var(--bg-tertiary)", border: "1px solid var(--border-color)" }}
                    >
                      <Icon size={18} style={{ color: "var(--text-secondary)" }} />
                    </div>
                  </div>
                </motion.div>
              ))}
              <div style={{ height: "1px", background: "var(--border-color)", opacity: 0.5 }} />
            </div>
          </div>
        </div>
      </section>

      {/* ═══ FOOTER ═══════════════════════════════════════════════════════ */}
      <footer
        className="relative z-10 border-t"
        style={{ borderColor: "var(--border-color)", background: "var(--bg-secondary)" }}
      >
        <div className="max-w-6xl mx-auto px-5 sm:px-8 md:px-10 py-12 sm:py-16">
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-10 lg:gap-8">
            {/* Brand */}
            <div className="sm:col-span-2 lg:col-span-1">
              <div className="flex items-center gap-1 mb-4">
                <span className="font-display font-black text-xl" style={{ color: "var(--accent)" }}>X</span>
                <span className="font-display font-black text-xs tracking-[0.16em]" style={{ color: "var(--text-primary)" }}>·HUNTER</span>
              </div>
              <p className="text-sm leading-relaxed max-w-[240px]" style={{ color: "var(--text-muted)" }}>
                Платформа нейро-тренировки продаж. ИИ-сценарии, аналитика, рейтинги.
              </p>
            </div>

            {/* Product */}
            <div>
              <h4 className="font-mono text-xs tracking-[0.3em] uppercase mb-4" style={{ color: "var(--text-muted)" }}>
                Продукт
              </h4>
              <ul className="space-y-2.5">
                {["ИИ-Тренировки", "Аналитика", "PvP-Арена", "Лидерборд"].map((item) => (
                  <li key={item}>
                    <span className="text-sm transition-colors cursor-default" style={{ color: "var(--text-secondary)" }}>
                      {item}
                    </span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Company */}
            <div>
              <h4 className="font-mono text-xs tracking-[0.3em] uppercase mb-4" style={{ color: "var(--text-muted)" }}>
                Компания
              </h4>
              <ul className="space-y-2.5">
                {["О платформе", "Безопасность", "Контакты", "Поддержка"].map((item) => (
                  <li key={item}>
                    <span className="text-sm transition-colors cursor-default" style={{ color: "var(--text-secondary)" }}>
                      {item}
                    </span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Legal */}
            <div>
              <h4 className="font-mono text-xs tracking-[0.3em] uppercase mb-4" style={{ color: "var(--text-muted)" }}>
                Документы
              </h4>
              <ul className="space-y-2.5">
                {["Политика конфиденциальности", "Условия использования", "Согласие на обработку данных"].map((item) => (
                  <li key={item}>
                    <span className="text-sm transition-colors cursor-default" style={{ color: "var(--text-secondary)" }}>
                      {item}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          {/* Bottom bar */}
          <div
            className="mt-12 pt-6 flex flex-col sm:flex-row items-center justify-between gap-3 border-t"
            style={{ borderColor: "var(--border-color)" }}
          >
            <p className="text-xs" style={{ color: "var(--text-muted)" }}>
              © {new Date().getFullYear()} X·Hunter. Все права защищены.
            </p>
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-1.5">
                <div className="w-1.5 h-1.5 rounded-full" style={{ background: "var(--neon-green)" }} />
                <span className="text-xs" style={{ color: "var(--text-muted)" }}>Все системы работают</span>
              </div>
            </div>
          </div>
        </div>
      </footer>

      {/* ═══ AUTH DRAWER ══════════════════════════════════════════════════ */}
      <AnimatePresence>
        {activePanel && (
          <>
            {/* Backdrop */}
            <motion.div
              key="backdrop"
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="fixed inset-0 z-[200] cursor-pointer"
              style={{ background: "rgba(0,0,0,0.65)", backdropFilter: "blur(8px)" }}
              onClick={closePanel}
            />

            {/* Drawer */}
            <motion.div
              key="drawer"
              initial={{ x: "100%" }} animate={{ x: 0 }} exit={{ x: "100%" }}
              transition={{ type: "spring", stiffness: 320, damping: 32 }}
              className="fixed right-0 top-0 bottom-0 z-[201] w-full sm:max-w-[420px] overflow-y-auto"
              style={{
                background: "var(--bg-secondary)",
                borderLeft: "1px solid var(--glass-border)",
                boxShadow: "-24px 0 80px rgba(0,0,0,0.5)",
              }}
            >
              {/* ── Drawer header ── */}
              <div
                className="sticky top-0 z-10 flex items-center justify-between px-5 sm:px-8 py-5"
                style={{ background: "var(--bg-secondary)", borderBottom: "1px solid var(--glass-border)" }}
              >
                <div>
                  <h2
                    className="font-display font-bold text-base tracking-[0.12em]"
                    style={{ color: "var(--text-primary)" }}
                  >
                    {forgotMode !== "idle"
                      ? "ВОССТАНОВЛЕНИЕ"
                      : activePanel === "login" ? "ВХОД В СИСТЕМУ" : "РЕГИСТРАЦИЯ"}
                  </h2>
                  <p className="font-mono text-xs mt-0.5 tracking-wider" style={{ color: "var(--text-muted)" }}>
                    X·HUNTER PLATFORM
                  </p>
                </div>
                <button
                  onClick={closePanel}
                  className="w-8 h-8 rounded-lg flex items-center justify-center"
                  style={{ background: "var(--bg-tertiary)", border: "1px solid var(--border-color)" }}
                  aria-label="Закрыть"
                >
                  <XIcon size={15} style={{ color: "var(--text-muted)" }} />
                </button>
              </div>

              {/* Accent gradient line */}
              <div
                className="h-[2px] w-full"
                style={{ background: "linear-gradient(90deg, var(--accent), var(--magenta), transparent)", opacity: 0.65 }}
              />

              {/* ── Form body ── */}
              <div className="px-5 sm:px-8 py-7">

                {/* ─── FORGOT PASSWORD VIEW ─── */}
                <AnimatePresence mode="wait">
                  {forgotMode !== "idle" ? (
                    <motion.div
                      key="forgot"
                      initial={{ opacity: 0, x: 20 }}
                      animate={{ opacity: 1, x: 0 }}
                      exit={{ opacity: 0, x: -20 }}
                      transition={{ duration: 0.25 }}
                    >
                      {forgotMode === "sent" ? (
                        /* Sent confirmation */
                        <div className="text-center py-8">
                          <motion.div
                            initial={{ scale: 0 }}
                            animate={{ scale: 1 }}
                            transition={{ type: "spring", stiffness: 300, delay: 0.1 }}
                            className="w-14 h-14 rounded-full flex items-center justify-center mx-auto mb-5"
                            style={{ background: "rgba(0,255,148,0.1)", border: "1px solid rgba(0,255,148,0.25)" }}
                          >
                            <Mail size={22} style={{ color: "var(--neon-green)" }} />
                          </motion.div>
                          <h3 className="font-display font-bold text-lg mb-2" style={{ color: "var(--text-primary)" }}>
                            Письмо отправлено
                          </h3>
                          <p className="text-sm mb-6" style={{ color: "var(--text-muted)" }}>
                            Проверьте <strong style={{ color: "var(--text-secondary)" }}>{forgotEmail}</strong>
                            <br />и следуйте инструкциям в письме.
                          </p>
                          <button
                            onClick={() => { setForgotMode("idle"); setForgotEmail(""); }}
                            className="text-sm font-medium"
                            style={{ color: "var(--accent)" }}
                          >
                            ← Вернуться ко входу
                          </button>
                        </div>
                      ) : (
                        /* Forgot form */
                        <div>
                          <button
                            onClick={() => setForgotMode("idle")}
                            className="flex items-center gap-1.5 text-xs mb-6 transition-colors"
                            style={{ color: "var(--text-muted)" }}
                            onMouseEnter={(e) => (e.currentTarget.style.color = "var(--text-primary)")}
                            onMouseLeave={(e) => (e.currentTarget.style.color = "var(--text-muted)")}
                          >
                            ← Назад
                          </button>
                          <h3 className="font-display font-bold text-xl mb-1.5" style={{ color: "var(--text-primary)" }}>
                            Забыли пароль?
                          </h3>
                          <p className="text-sm mb-6" style={{ color: "var(--text-muted)", lineHeight: 1.7 }}>
                            Введите email — пришлём ссылку для сброса пароля.
                          </p>
                          <label className="vh-label">Email</label>
                          <div className="relative mb-4">
                            <Mail size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2" style={{ color: "var(--text-muted)" }} />
                            <input
                              type="email"
                              value={forgotEmail}
                              onChange={(e) => setForgotEmail(e.target.value)}
                              className="vh-input pl-10 w-full"
                              placeholder="you@example.com"
                              autoComplete="email"
                              aria-label="Email для восстановления"
                            />
                          </div>
                          <motion.button
                            onClick={handleForgot}
                            disabled={forgotLoading || !forgotEmail.trim()}
                            className="btn-neon flex w-full items-center justify-center gap-2"
                            whileHover={{ scale: 1.01 }} whileTap={{ scale: 0.99 }}
                          >
                            {forgotLoading
                              ? <div className="h-5 w-5 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                              : <><Mail size={15} />Отправить ссылку</>}
                          </motion.button>
                        </div>
                      )}
                    </motion.div>
                  ) : (

                    /* ─── MAIN LOGIN / REGISTER FORM ─── */
                    <motion.div
                      key="main"
                      initial={{ opacity: 0, x: -20 }}
                      animate={{ opacity: 1, x: 0 }}
                      exit={{ opacity: 0, x: 20 }}
                      transition={{ duration: 0.25 }}
                    >
                      {/* Error */}
                      {error && (
                        <motion.div
                          initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}
                          className="flex items-center gap-2 rounded-xl p-3 text-sm mb-5"
                          style={{ background: "rgba(255,51,51,0.08)", border: "1px solid rgba(255,51,51,0.2)", color: "var(--neon-red)" }}
                        >
                          <AlertCircle size={16} />{error}
                        </motion.div>
                      )}

                      {/* 🟢 SSO buttons — BOTH panels */}
                      <div className="mb-5">
                        <div className="flex gap-3">
                          {SSO_BUTTONS.map(({ label, endpoint, icon }) => (
                            <motion.button
                              key={label} type="button"
                              className="flex-1 flex items-center justify-center gap-2 rounded-xl py-2.5 text-sm"
                              style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)", color: "var(--text-secondary)" }}
                              whileHover={{ borderColor: "var(--border-hover)" }} whileTap={{ scale: 0.97 }}
                              onClick={() => handleSso(endpoint, label)}
                            >
                              {icon}{label}
                            </motion.button>
                          ))}
                        </div>
                        <div className="flex items-center gap-3 mt-4">
                          <div className="flex-1 h-px" style={{ background: "var(--border-color)" }} />
                          <span className="font-mono text-xs tracking-wider" style={{ color: "var(--text-muted)" }}>
                            или через email
                          </span>
                          <div className="flex-1 h-px" style={{ background: "var(--border-color)" }} />
                        </div>
                      </div>

                      <form onSubmit={handleSubmit} className="space-y-4">

                        {/* Full name — register only */}
                        {activePanel === "register" && (
                          <div>
                            <label className="vh-label">Полное имя</label>
                            <div className="relative">
                              <User size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2" style={{ color: "var(--text-muted)" }} />
                              <input
                                type="text" value={fullName} onChange={(e) => setFullName(e.target.value)}
                                required className="vh-input pl-10 w-full" placeholder="Иван Петров"
                                autoComplete="name" aria-label="Полное имя"
                              />
                            </div>
                          </div>
                        )}

                        {/* Email */}
                        <div>
                          <label className="vh-label">Email</label>
                          <div className="relative">
                            <Mail size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2" style={{ color: "var(--text-muted)" }} />
                            <input
                              type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                              required className="vh-input pl-10 w-full" placeholder="you@example.com"
                              autoComplete="email" aria-label="Email"
                            />
                          </div>
                        </div>

                        {/* Password */}
                        <div>
                          <div className="flex items-center justify-between mb-1">
                            <label className="vh-label mb-0">Пароль</label>
                            {/* 🔴 Забыли пароль — login only */}
                            {activePanel === "login" && (
                              <button
                                type="button"
                                onClick={() => setForgotMode("form")}
                                className="text-xs transition-colors"
                                style={{ color: "var(--text-muted)" }}
                                onMouseEnter={(e) => (e.currentTarget.style.color = "var(--accent)")}
                                onMouseLeave={(e) => (e.currentTarget.style.color = "var(--text-muted)")}
                              >
                                Забыли пароль?
                              </button>
                            )}
                          </div>
                          <PasswordInput
                            id="panel-password" value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            placeholder={activePanel === "register" ? "Минимум 8 символов" : "Введите пароль"}
                            autoComplete={activePanel === "login" ? "current-password" : "new-password"}
                            ariaLabel="Пароль"
                          />
                          {activePanel === "register" && (
                            <PasswordChecklist value={password} />
                          )}
                        </div>

                        {/* 🔴 Confirm password — register only, с placeholder */}
                        {activePanel === "register" && (
                          <div>
                            <label className="vh-label">Повторите пароль</label>
                            <PasswordInput
                              id="panel-confirm-password" value={confirmPassword}
                              onChange={(e) => setConfirmPassword(e.target.value)}
                              placeholder="Введите пароль ещё раз"
                              autoComplete="new-password" ariaLabel="Подтвердите пароль"
                            />
                            {!passwordsMatch && (
                              <p className="mt-1.5 text-xs" style={{ color: "var(--neon-red)" }}>Пароли не совпадают</p>
                            )}
                          </div>
                        )}

                        {/* 🔴 Remember me — login only */}
                        {activePanel === "login" && (
                          <label className="flex items-center gap-2.5 cursor-pointer select-none">
                            <div
                              className="relative w-9 h-5 rounded-full cursor-pointer flex-shrink-0"
                              style={{
                                background: rememberMe ? "var(--accent)" : "var(--input-bg)",
                                border: `1px solid ${rememberMe ? "var(--accent)" : "var(--border-color)"}`,
                                transition: "background 0.2s",
                              }}
                              onClick={() => setRememberMe(!rememberMe)}
                            >
                              <motion.div
                                className="absolute top-0.5 w-3.5 h-3.5 rounded-full bg-white"
                                animate={{ left: rememberMe ? 18 : 2 }}
                                transition={{ type: "spring", stiffness: 500, damping: 30 }}
                                style={{ boxShadow: rememberMe ? "0 0 6px var(--accent-glow)" : "none" }}
                              />
                            </div>
                            <span className="text-xs" style={{ color: "var(--text-muted)" }}>Запомнить меня</span>
                          </label>
                        )}

                        {/* Submit */}
                        <motion.button
                          type="submit" disabled={loading || !passwordsMatch}
                          className="btn-neon flex w-full items-center justify-center gap-2"
                          whileHover={{ scale: 1.01 }} whileTap={{ scale: 0.99 }}
                        >
                          {loading
                            ? <div className="h-5 w-5 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                            : <>{activePanel === "login" ? "Войти" : "Зарегистрироваться"}<ArrowRight size={16} /></>}
                        </motion.button>

                        {/* 🟢 Register micro-trust */}
                        {activePanel === "register" && (
                          <p className="text-center text-sm mt-2" style={{ color: "var(--text-muted)" }}>
                            14 дней бесплатно · Без кредитной карты
                          </p>
                        )}
                      </form>

                      {/* Switch panel */}
                      <p className="mt-5 text-center text-sm" style={{ color: "var(--text-muted)" }}>
                        {activePanel === "login" ? "Нет аккаунта?" : "Уже есть аккаунт?"}{" "}
                        <button
                          onClick={() => openPanel(activePanel === "login" ? "register" : "login")}
                          className="font-medium" style={{ color: "var(--accent)" }}
                        >
                          {activePanel === "login" ? "Зарегистрироваться" : "Войти"}
                        </button>
                      </p>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}
