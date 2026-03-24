"use client";

import { useEffect, useState, useCallback, useRef, useMemo } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence, useMotionValue, useTransform } from "framer-motion";
import {
  Crosshair,
  ArrowRight,
  Mail,
  Lock,
  AlertCircle,
  Mouse,
  User,
} from "lucide-react";
import dynamic from "next/dynamic";
import { FishermanError } from "@/components/errors/FishermanError";
import { useReducedMotion } from "@/hooks/useReducedMotion";
import { getToken, setTokens } from "@/lib/auth";
import { api } from "@/lib/api";
import { getApiBaseUrl } from "@/lib/public-origin";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { LogoSeparator } from "@/components/ui/LogoSeparator";

const WaveScene = dynamic(
  () => import("@/components/landing/WaveScene").then((m) => m.WaveScene),
  { ssr: false },
);

type Phase = "waiting" | "flying" | "ocean" | "form-rising" | "ready";

export default function Home() {
  const router = useRouter();
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [showPortal, setShowPortal] = useState(false);
  const [phase, setPhase] = useState<Phase>("waiting");

  // Login form
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [isLogin, setIsLogin] = useState(true);
  const [fullName, setFullName] = useState("");
  const [networkError, setNetworkError] = useState(false);
  const [rememberMe, setRememberMe] = useState(true);
  const [showForgot, setShowForgot] = useState(false);
  const [forgotEmail, setForgotEmail] = useState("");
  const [forgotSent, setForgotSent] = useState(false);

  // A11y: respect prefers-reduced-motion
  const reducedMotion = useReducedMotion();

  // A1: Parallax mouse tracking
  const mouseX = useMotionValue(0.5);
  const mouseY = useMotionValue(0.5);
  const gateParallaxL = useTransform(mouseX, [0, 1], [8, -8]);
  const gateParallaxR = useTransform(mouseX, [0, 1], [-8, 8]);
  const gateParallaxY = useTransform(mouseY, [0, 1], [4, -4]);
  const beamParallaxX = useTransform(mouseX, [0, 1], [-3, 3]);
  const beamParallaxY = useTransform(mouseY, [0, 1], [-5, 5]);

  useEffect(() => {
    if (reducedMotion) return; // Skip parallax when user prefers reduced motion
    const onMove = (e: MouseEvent) => {
      mouseX.set(e.clientX / window.innerWidth);
      mouseY.set(e.clientY / window.innerHeight);
    };
    window.addEventListener("mousemove", onMove);
    return () => window.removeEventListener("mousemove", onMove);
  }, [mouseX, mouseY, reducedMotion]);

  // A4: Detect mobile for adaptive timing
  const isMobile = useMemo(() => {
    if (typeof window === "undefined") return false;
    return window.innerWidth < 768 || "ontouchstart" in window;
  }, []);

  // Auth check
  useEffect(() => {
    const token = getToken();
    if (!token) {
      setCheckingAuth(false);
      setShowPortal(true);
      return;
    }
    api
      .get("/consent/status")
      .then((data) => router.replace(data.all_accepted ? "/home" : "/consent"))
      .catch(() => router.replace("/home"));
  }, [router]);

  // A3: Sound engine ref
  const audioCtxRef = useRef<AudioContext | null>(null);

  const playGateSound = useCallback(() => {
    try {
      const ctx = new AudioContext();
      audioCtxRef.current = ctx;

      // Low rumble — oscillator sweep 40Hz → 80Hz
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.setValueAtTime(40, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(80, ctx.currentTime + 1.5);
      gain.gain.setValueAtTime(0, ctx.currentTime);
      gain.gain.linearRampToValueAtTime(0.15, ctx.currentTime + 0.3);
      gain.gain.linearRampToValueAtTime(0.25, ctx.currentTime + 1.0);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 2.5);
      osc.connect(gain).connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 2.5);

      // Whoosh — filtered noise burst at 1.5s
      const bufferSize = ctx.sampleRate * 0.8;
      const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
      const data = buffer.getChannelData(0);
      for (let i = 0; i < bufferSize; i++) data[i] = (Math.random() * 2 - 1) * 0.3;
      const noise = ctx.createBufferSource();
      noise.buffer = buffer;
      const filter = ctx.createBiquadFilter();
      filter.type = "bandpass";
      filter.frequency.setValueAtTime(200, ctx.currentTime + 1.2);
      filter.frequency.exponentialRampToValueAtTime(2000, ctx.currentTime + 1.8);
      filter.Q.value = 2;
      const noiseGain = ctx.createGain();
      noiseGain.gain.setValueAtTime(0, ctx.currentTime + 1.2);
      noiseGain.gain.linearRampToValueAtTime(0.12, ctx.currentTime + 1.5);
      noiseGain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 2.2);
      noise.connect(filter).connect(noiseGain).connect(ctx.destination);
      noise.start(ctx.currentTime + 1.2);
      noise.stop(ctx.currentTime + 2.2);
    } catch { /* Audio not available */ }
  }, []);

  // A4: Adaptive flight timing — fast splash, form after text gone
  const triggerFlight = useCallback(() => {
    if (phase !== "waiting") return;
    playGateSound();
    setPhase("flying");
    const t1 = isMobile ? 600 : 900;
    const t2 = isMobile ? 1000 : 1400;
    const t3 = isMobile ? 1400 : 1900;
    setTimeout(() => setPhase("ocean"), t1);
    setTimeout(() => setPhase("form-rising"), t2);
    setTimeout(() => setPhase("ready"), t3);
  }, [phase, isMobile, playGateSound]);

  // Scroll / click / touch triggers
  useEffect(() => {
    if (!showPortal) return;
    const onWheel = (e: WheelEvent) => { if (e.deltaY > 0) triggerFlight(); };
    const onClick = (e: MouseEvent) => {
      try {
        const t = e.target as HTMLElement;
        if (t?.closest?.("form") || t?.closest?.("button") || t?.closest?.("input") || t?.closest?.("a")) return;
      } catch { /* proceed */ }
      triggerFlight();
    };
    window.addEventListener("wheel", onWheel, { passive: true });
    document.addEventListener("click", onClick);
    return () => {
      window.removeEventListener("wheel", onWheel);
      document.removeEventListener("click", onClick);
    };
  }, [showPortal, triggerFlight]);

  // A2: Particle dust positions (deterministic) — must be before early returns
  const particles = useMemo(() =>
    Array.from({ length: 40 }, (_, i) => ({
      id: i,
      startY: 10 + (i * 67 % 80),
      duration: 3 + (i % 5) * 0.8,
      delay: (i * 0.15) % 4,
      size: 1 + (i % 3),
      drift: (i % 2 === 0 ? 1 : -1) * (2 + (i % 4)),
      opacity: 0.15 + (i % 5) * 0.08,
    })),
  []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      if (isLogin) {
        const data = await api.post("/auth/login", { email: email.trim(), password });
        setTokens(data.access_token, data.refresh_token);
        router.push(data.must_change_password ? "/change-password" : "/home");
      } else {
        const data = await api.post("/auth/register", { email: email.trim(), password, full_name: fullName });
        setTokens(data.access_token, data.refresh_token);
        router.push("/onboarding");
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Ошибка";
      if (msg.includes("недоступен") || msg.includes("fetch") || msg.includes("network")) {
        setNetworkError(true);
      } else {
        setError(msg);
      }
    } finally {
      setLoading(false);
    }
  };

  if (networkError) {
    return <FishermanError onRetry={() => { setNetworkError(false); setError(""); }} message="Похоже, рыба сегодня не клюёт..." />;
  }

  if (checkingAuth && !showPortal) {
    return (
      <div className="flex min-h-screen items-center justify-center" style={{ background: "var(--bg-primary)" }}>
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex items-center gap-2">
          <Crosshair size={20} className="animate-pulse" style={{ color: "var(--accent)" }} />
          <span className="font-mono text-sm" style={{ color: "var(--text-muted)" }}>ИНИЦИАЛИЗАЦИЯ...</span>
        </motion.div>
      </div>
    );
  }

  const gatesGone = phase === "ocean" || phase === "form-rising" || phase === "ready";
  const showForm = phase === "form-rising" || phase === "ready";

  return (
    <div className="relative min-h-screen overflow-hidden" style={{ background: "var(--bg-primary)" }}>

      {/* ── Ocean background (hidden during V-Gate, visible after flight) ── */}
      <motion.div
        className="fixed inset-0 z-[1]"
        initial={{ opacity: 0 }}
        animate={{ opacity: gatesGone ? 1 : 0 }}
        transition={{ duration: 1.5 }}
      >
        <div
          className="absolute inset-0 pointer-events-none"
          style={{ background: "radial-gradient(ellipse at 50% 80%, var(--accent-glow) 0%, transparent 60%)" }}
        />
        <WaveScene />
      </motion.div>

      {/* ── Clickable overlay (waiting phase) ── */}
      {phase === "waiting" && (
        <div className="fixed inset-0 z-[65] cursor-pointer" onClick={triggerFlight} />
      )}

      {/* ── V-GATES with A1 parallax ── */}
      <AnimatePresence>
        {!gatesGone && (
          <>
            {/* Left gate — parallax reacts to mouse */}
            <motion.div
              className="fixed top-0 left-0 z-[50] h-screen"
              style={{
                width: "52vw",
                background: "var(--bg-primary)",
                clipPath: "polygon(0 0, 100% 0, 70% 100%, 0 100%)",
                x: phase === "waiting" ? gateParallaxL : 0,
                y: phase === "waiting" ? gateParallaxY : 0,
              }}
              initial={{ x: 0 }}
              animate={
                phase === "flying"
                  ? { x: "-55vw", opacity: 0 }
                  : {}
              }
              exit={{ opacity: 0 }}
              transition={{ duration: isMobile ? 0.8 : 1.2, ease: [0.4, 0, 0.2, 1] }}
            >
              {/* Edge glow */}
              <div
                className="absolute top-0 right-0 w-[3px] h-full"
                style={{
                  background: "linear-gradient(180deg, transparent 10%, var(--accent) 50%, transparent 90%)",
                  boxShadow: "0 0 20px var(--accent-glow), 0 0 60px var(--accent-glow)",
                }}
              />
              {/* Grid texture */}
              <div className="absolute inset-0 opacity-[0.03]" style={{
                backgroundImage: `linear-gradient(var(--accent-glow) 1px, transparent 1px), linear-gradient(90deg, var(--accent-glow) 1px, transparent 1px)`,
                backgroundSize: "40px 40px",
              }} />
            </motion.div>

            {/* Right gate — parallax opposite */}
            <motion.div
              className="fixed top-0 right-0 z-[50] h-screen"
              style={{
                width: "52vw",
                background: "var(--bg-primary)",
                clipPath: "polygon(30% 100%, 100% 100%, 100% 0, 0 0)",
                x: phase === "waiting" ? gateParallaxR : 0,
                y: phase === "waiting" ? gateParallaxY : 0,
              }}
              initial={{ x: 0 }}
              animate={
                phase === "flying"
                  ? { x: "55vw", opacity: 0 }
                  : {}
              }
              exit={{ opacity: 0 }}
              transition={{ duration: isMobile ? 0.8 : 1.2, ease: [0.4, 0, 0.2, 1] }}
            >
              <div
                className="absolute top-0 left-0 w-[3px] h-full"
                style={{
                  background: "linear-gradient(180deg, transparent 10%, var(--accent) 50%, transparent 90%)",
                  boxShadow: "0 0 20px var(--accent-glow), 0 0 60px var(--accent-glow)",
                }}
              />
              <div className="absolute inset-0 opacity-[0.03]" style={{
                backgroundImage: `linear-gradient(var(--accent-glow) 1px, transparent 1px), linear-gradient(90deg, var(--accent-glow) 1px, transparent 1px)`,
                backgroundSize: "40px 40px",
              }} />
            </motion.div>

            {/* A2: Particle dust floating in the crack */}
            <div className="fixed inset-0 z-[51] pointer-events-none flex items-center justify-center">
              {phase === "waiting" && particles.map((p) => (
                <motion.div
                  key={p.id}
                  className="absolute rounded-full"
                  style={{
                    width: p.size,
                    height: p.size,
                    background: "var(--accent)",
                    left: `calc(50% + ${p.drift}px)`,
                    top: `${p.startY}%`,
                  }}
                  animate={{
                    y: [0, -30, -60],
                    x: [0, p.drift, p.drift * 1.5],
                    opacity: [0, p.opacity, 0],
                  }}
                  transition={{
                    duration: p.duration,
                    repeat: Infinity,
                    delay: p.delay,
                    ease: "easeOut",
                  }}
                />
              ))}
            </div>

            {/* V-shaped light beam with parallax */}
            <motion.div
              className="fixed inset-0 z-[49] pointer-events-none flex items-center justify-center"
              initial={{ opacity: 0.6 }}
              animate={phase === "flying" ? { opacity: 0, scale: 3 } : { opacity: 0.6 }}
              transition={{ duration: 1.5 }}
              style={{ x: beamParallaxX, y: beamParallaxY }}
            >
              <div
                className="w-[4px] h-[70vh]"
                style={{
                  background: `linear-gradient(180deg, transparent 0%, var(--accent) 30%, var(--accent-hover) 50%, var(--accent) 70%, transparent 100%)`,
                  boxShadow: "0 0 30px var(--accent-glow), 0 0 80px var(--accent-glow), 0 0 120px var(--accent-glow)",
                  filter: "blur(0.5px)",
                }}
              />
            </motion.div>

            {/* "V" letter behind crack — subtly glowing */}
            <motion.div
              className="fixed inset-0 z-[48] flex flex-col items-center justify-center pointer-events-none"
              initial={{ opacity: 0 }}
              animate={phase === "waiting" ? { opacity: 1 } : { opacity: 0, scale: 1.2 }}
              transition={{ duration: phase === "waiting" ? 1.5 : 0.6, ease: "easeOut" }}
            >
              <motion.h1
                className="font-display font-black text-[14vw] md:text-[10vw] leading-none tracking-[0.15em]"
                style={{
                  color: "transparent",
                  WebkitTextStroke: "1px var(--accent)",
                  opacity: 0.12,
                  filter: "drop-shadow(0 0 30px var(--accent-glow))",
                }}
                animate={{ opacity: [0.08, 0.15, 0.08] }}
                transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
              >
                V
              </motion.h1>
            </motion.div>
          </>
        )}
      </AnimatePresence>

      {/* ── Logo flash during flight — instant punch, smooth exit ── */}
      <AnimatePresence>
        {phase === "flying" && (
          <motion.div
            className="fixed inset-0 z-[60] flex flex-col items-center justify-center pointer-events-none"
            initial={{ opacity: 0, scale: 0.85 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 1.05 }}
            transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
          >
            <div className="relative">
              <h1 className="font-display font-black text-6xl md:text-8xl tracking-[0.15em]">
                <span style={{ color: "var(--accent)" }}>X</span><span style={{ color: "var(--text-primary)" }}>HUNTER</span>
              </h1>
              <div className="absolute inset-0 rounded-full opacity-30 blur-[80px]" style={{ background: "var(--accent)" }} />
            </div>
            <motion.p
              className="font-mono text-xs tracking-[0.4em] uppercase mt-3"
              style={{ color: "var(--accent)" }}
              initial={{ opacity: 0, y: 5 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.15 }}
            >
              Neural Sales Environment
            </motion.p>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Ocean bloom flash ── */}
      <AnimatePresence>
        {phase === "ocean" && (
          <motion.div
            className="fixed inset-0 z-[55] pointer-events-none"
            initial={{ opacity: 0.6 }}
            animate={{ opacity: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 1.5 }}
            style={{ background: "radial-gradient(circle at 50% 50%, var(--accent-glow), transparent 70%)" }}
          />
        )}
      </AnimatePresence>

      {/* ── Scroll prompt ── */}
      <AnimatePresence>
        {phase === "waiting" && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 0.6 }}
            exit={{ opacity: 0 }}
            className="fixed bottom-12 left-1/2 -translate-x-1/2 z-[40] flex flex-col items-center gap-3"
          >
            <motion.div animate={{ y: [0, 8, 0] }} transition={{ duration: 2, repeat: Infinity }}>
              <Mouse size={22} style={{ color: "var(--accent)" }} />
            </motion.div>
            <span className="font-mono text-[10px] tracking-[0.4em] uppercase" style={{ color: "var(--accent)" }}>
              {isMobile ? "Tap to Enter" : "Scroll to Enter"}
            </span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Theme toggle ── */}
      <div className="fixed right-4 top-4 z-[70]">
        <ThemeToggle />
      </div>

      {/* ── Login/Register form ── */}
      <AnimatePresence>
        {showForm && (
          <motion.div
            className="fixed inset-0 z-[30] flex items-end justify-center pb-[15vh] md:pb-[18vh] pointer-events-none"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.5 }}
          >
            <motion.div
              initial={{ y: 120, opacity: 0, scale: 0.95 }}
              animate={
                phase === "ready"
                  ? { y: 0, opacity: 1, scale: 1 }
                  : { y: 30, opacity: 0.85, scale: 0.97 }
              }
              transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
              className="w-full max-w-md px-4 pointer-events-auto"
            >
              <div
                className="rounded-2xl p-8 relative overflow-hidden"
                style={{
                  background: "var(--glass-bg)",
                  backdropFilter: "blur(24px)",
                  border: "1px solid var(--glass-border)",
                  boxShadow: "0 -20px 80px var(--accent-glow), var(--shadow-md)",
                }}
              >
                {/* Top accent line */}
                <div
                  className="absolute top-0 left-8 right-8 h-[2px] rounded-full"
                  style={{ background: "linear-gradient(90deg, transparent, var(--accent), transparent)" }}
                />

                {/* Wave shimmer */}
                <motion.div
                  className="absolute top-0 left-0 right-0 h-[60px] pointer-events-none opacity-20"
                  style={{
                    background: "linear-gradient(180deg, var(--accent-glow), transparent)",
                    maskImage: "linear-gradient(180deg, black, transparent)",
                  }}
                  animate={{ opacity: [0.15, 0.25, 0.15] }}
                  transition={{ duration: 3, repeat: Infinity }}
                />

                {/* Header */}
                <div className="mb-6 text-center relative z-10">
                  {/* Animated logo — orbiting rings */}
                  <motion.div
                    initial={{ scale: 0.5, opacity: 0 }}
                    animate={{ scale: 1, opacity: 1 }}
                    transition={{ type: "spring", stiffness: 200, delay: 0.3 }}
                    className="relative mx-auto mb-4 h-14 w-14 flex items-center justify-center"
                  >
                    <motion.div
                      className="absolute inset-0 rounded-full"
                      style={{ border: "1.5px solid var(--accent)", opacity: 0.4 }}
                      animate={{ rotate: 360 }}
                      transition={{ duration: 8, repeat: Infinity, ease: "linear" }}
                    />
                    <motion.div
                      className="absolute inset-2 rounded-full"
                      style={{ border: "1px dashed var(--accent)", opacity: 0.2 }}
                      animate={{ rotate: -360 }}
                      transition={{ duration: 12, repeat: Infinity, ease: "linear" }}
                    />
                    <motion.div
                      className="w-5 h-5 rounded-full"
                      style={{ background: "var(--accent)" }}
                      animate={{
                        boxShadow: ["0 0 12px var(--accent-glow)", "0 0 30px var(--accent-glow)", "0 0 12px var(--accent-glow)"],
                        scale: [1, 1.15, 1],
                      }}
                      transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
                    />
                  </motion.div>
                  <h1 className="font-display text-[2rem] font-black tracking-[0.2em] inline-flex items-center justify-center">
                    <span style={{ color: "var(--accent)" }}>X</span>
                    <LogoSeparator size={26} />
                    <span style={{ color: "var(--text-primary)" }}>HUNTER</span>
                  </h1>
                  <p className="mt-1 font-mono text-xs tracking-[0.3em]" style={{ color: "var(--text-muted)" }}>
                    {isLogin ? "ВХОД В СИСТЕМУ" : "СОЗДАНИЕ АККАУНТА"}
                  </p>
                </div>

                {/* Form */}
                <form onSubmit={handleSubmit} className="space-y-4 relative z-10">
                  {error && (
                    <motion.div
                      initial={{ opacity: 0, y: -8 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="flex items-center gap-2 rounded-xl p-3 text-sm"
                      style={{ background: "rgba(255,42,109,0.1)", border: "1px solid rgba(255,42,109,0.2)", color: "var(--neon-red)" }}
                    >
                      <AlertCircle size={16} />
                      {error}
                    </motion.div>
                  )}

                  <AnimatePresence mode="wait">
                    {!isLogin && (
                      <motion.div
                        key="name-field"
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.3 }}
                      >
                        <div className="relative">
                          <User size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2" style={{ color: "var(--text-muted)" }} />
                          <input
                            type="text"
                            value={fullName}
                            onChange={(e) => setFullName(e.target.value)}
                            required={!isLogin}
                            className="vh-input pl-10 w-full"
                            placeholder="Полное имя"
                            aria-label="Полное имя"
                            autoComplete="name"
                          />
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>

                  <div className="relative">
                    <Mail size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2" style={{ color: "var(--text-muted)" }} />
                    <input
                      id="email"
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      required
                      className="vh-input pl-10 w-full"
                      placeholder="Email"
                      aria-label="Email"
                      autoComplete="email"
                    />
                  </div>

                  {/* Password + C4 wave strength */}
                  <div>
                    <div className="relative">
                      <Lock size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2" style={{ color: "var(--text-muted)" }} />
                      <input
                        id="password"
                        type="password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        required
                        className="vh-input pl-10 w-full"
                        placeholder="Пароль"
                        aria-label="Пароль"
                        autoComplete={isLogin ? "current-password" : "new-password"}
                      />
                    </div>
                    {/* C4: Password strength wave */}
                    {!isLogin && password.length > 0 && (() => {
                      const str = password.length >= 12 && /[A-Z]/.test(password) && /[0-9]/.test(password) && /[^A-Za-z0-9]/.test(password)
                        ? 3 : password.length >= 8 && /[A-Z]/.test(password) && /[0-9]/.test(password)
                        ? 2 : 1;
                      const labels = ["СЛАБЫЙ", "СРЕДНИЙ", "НАДЁЖНЫЙ"];
                      const colors = ["var(--neon-red)", "var(--neon-amber)", "var(--neon-green)"];
                      return (
                        <div className="mt-2 relative h-3 rounded-full overflow-hidden" style={{ background: "var(--input-bg)" }}>
                          <motion.div
                            className="absolute inset-y-0 left-0 rounded-full"
                            initial={{ width: 0 }}
                            animate={{ width: `${(str / 3) * 100}%` }}
                            transition={{ duration: 0.5, ease: "easeOut" }}
                            style={{ background: colors[str - 1], boxShadow: `0 0 8px ${colors[str - 1]}` }}
                          />
                          {/* Mini wave on the edge */}
                          <motion.div
                            className="absolute top-0 h-full w-2 rounded-full"
                            animate={{ left: `calc(${(str / 3) * 100}% - 4px)`, opacity: [0.5, 1, 0.5] }}
                            transition={{ duration: 1.5, repeat: Infinity }}
                            style={{ background: colors[str - 1], filter: "blur(1px)" }}
                          />
                          <span
                            className="absolute right-2 top-1/2 -translate-y-1/2 font-mono text-[8px] tracking-wider"
                            style={{ color: colors[str - 1] }}
                          >
                            {labels[str - 1]}
                          </span>
                        </div>
                      );
                    })()}
                  </div>

                  {/* C6: Remember me + C7: Forgot password */}
                  {isLogin && (
                    <div className="flex items-center justify-between">
                      <label className="flex items-center gap-2 cursor-pointer select-none">
                        <motion.div
                          className="relative w-9 h-5 rounded-full cursor-pointer"
                          style={{
                            background: rememberMe ? "var(--accent)" : "var(--input-bg)",
                            border: `1px solid ${rememberMe ? "var(--accent)" : "var(--border-color)"}`,
                          }}
                          onClick={() => setRememberMe(!rememberMe)}
                          whileTap={{ scale: 0.95 }}
                        >
                          <motion.div
                            className="absolute top-0.5 w-3.5 h-3.5 rounded-full bg-white"
                            animate={{ left: rememberMe ? 18 : 2 }}
                            transition={{ type: "spring", stiffness: 500, damping: 30 }}
                            style={{ boxShadow: rememberMe ? "0 0 6px var(--accent-glow)" : "none" }}
                          />
                        </motion.div>
                        <span className="text-xs" style={{ color: "var(--text-muted)" }}>Запомнить</span>
                      </label>
                      <button
                        type="button"
                        onClick={() => setShowForgot(true)}
                        className="text-xs transition-colors"
                        style={{ color: "var(--text-muted)" }}
                        onMouseEnter={(e) => (e.currentTarget.style.color = "var(--accent)")}
                        onMouseLeave={(e) => (e.currentTarget.style.color = "var(--text-muted)")}
                      >
                        Забыли пароль?
                      </button>
                    </div>
                  )}

                  <motion.button
                    type="submit"
                    disabled={loading}
                    className="vh-btn-primary flex w-full items-center justify-center gap-2"
                    whileHover={{ scale: 1.01 }}
                    whileTap={{ scale: 0.98 }}
                  >
                    {loading ? (
                      <div className="h-5 w-5 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                    ) : (
                      <>
                        {isLogin ? "Войти" : "Зарегистрироваться"}
                        <ArrowRight size={16} />
                      </>
                    )}
                  </motion.button>

                  {/* C5: Social login stubs */}
                  {isLogin && (
                    <div className="relative z-10">
                      <div className="flex items-center gap-3 my-1">
                        <div className="flex-1 h-px" style={{ background: "var(--border-color)" }} />
                        <span className="font-mono text-[9px] tracking-wider" style={{ color: "var(--text-muted)" }}>ИЛИ</span>
                        <div className="flex-1 h-px" style={{ background: "var(--border-color)" }} />
                      </div>
                      <div className="flex gap-3 mt-3">
                        <motion.button
                          type="button"
                          className="flex-1 flex items-center justify-center gap-2 rounded-xl py-2.5 text-sm transition-colors"
                          style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)", color: "var(--text-secondary)" }}
                          whileHover={{ borderColor: "var(--border-hover)", background: "var(--bg-tertiary)" }}
                          whileTap={{ scale: 0.97 }}
                          onClick={async () => {
                            try {
                              const data = await api.get("/auth/google/login");
                              if (data?.url) window.location.href = data.url;
                            } catch (err: unknown) {
                              setError(err instanceof Error ? err.message : "Google OAuth недоступен");
                            }
                          }}
                        >
                          <svg width="16" height="16" viewBox="0 0 24 24"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/></svg>
                          Google
                        </motion.button>
                        <motion.button
                          type="button"
                          className="flex-1 flex items-center justify-center gap-2 rounded-xl py-2.5 text-sm transition-colors"
                          style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)", color: "var(--text-secondary)" }}
                          whileHover={{ borderColor: "var(--border-hover)", background: "var(--bg-tertiary)" }}
                          whileTap={{ scale: 0.97 }}
                          onClick={async () => {
                            try {
                              const data = await api.get("/auth/yandex/login");
                              if (data?.url) window.location.href = data.url;
                            } catch (err: unknown) {
                              setError(err instanceof Error ? err.message : "Yandex OAuth недоступен");
                            }
                          }}
                        >
                          <svg width="16" height="16" viewBox="0 0 24 24"><path d="M2 12C2 6.48 6.48 2 12 2s10 4.48 10 10-4.48 10-10 10S2 17.52 2 12z" fill="#FC3F1D"/><path d="M13.32 17.5h-1.88V7.38h-.97c-1.57 0-2.39.8-2.39 1.95 0 1.3.59 1.9 1.8 2.7l1 .65-2.9 4.82H6l2.62-4.33C7.37 12.26 6.56 11.22 6.56 9.5c0-2.07 1.45-3.5 4-3.5h2.76V17.5z" fill="white"/></svg>
                          Yandex
                        </motion.button>
                      </div>
                    </div>
                  )}
                </form>

                {/* Toggle login/register */}
                <p className="mt-4 text-center text-sm relative z-10" style={{ color: "var(--text-muted)" }}>
                  {isLogin ? "Нет аккаунта?" : "Уже есть аккаунт?"}{" "}
                  <button
                    onClick={() => { setIsLogin(!isLogin); setError(""); setShowForgot(false); }}
                    className="font-medium transition-colors"
                    style={{ color: "var(--accent)" }}
                  >
                    {isLogin ? "Зарегистрироваться" : "Войти"}
                  </button>
                </p>

                {/* C7: Forgot password modal */}
                <AnimatePresence>
                  {showForgot && (
                    <motion.div
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: 10 }}
                      className="absolute inset-0 z-20 rounded-2xl flex flex-col items-center justify-center p-8"
                      style={{ background: "var(--glass-bg)", backdropFilter: "blur(24px)" }}
                    >
                      {forgotSent ? (
                        <div className="text-center">
                          <motion.div
                            initial={{ scale: 0 }}
                            animate={{ scale: 1 }}
                            transition={{ type: "spring", stiffness: 300 }}
                            className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full"
                            style={{ background: "rgba(0,255,148,0.1)" }}
                          >
                            <Mail size={24} style={{ color: "var(--neon-green)" }} />
                          </motion.div>
                          <h3 className="font-display text-lg font-bold mb-2" style={{ color: "var(--text-primary)" }}>
                            Письмо отправлено
                          </h3>
                          <p className="text-sm mb-4" style={{ color: "var(--text-muted)" }}>
                            Проверьте {forgotEmail}
                          </p>
                          <button
                            onClick={() => { setShowForgot(false); setForgotSent(false); setForgotEmail(""); }}
                            className="text-sm font-medium"
                            style={{ color: "var(--accent)" }}
                          >
                            Вернуться ко входу
                          </button>
                        </div>
                      ) : (
                        <>
                          <h3 className="font-display text-lg font-bold mb-2" style={{ color: "var(--text-primary)" }}>
                            Восстановление пароля
                          </h3>
                          <p className="text-sm text-center mb-4" style={{ color: "var(--text-muted)" }}>
                            Введите email, на который зарегистрирован аккаунт
                          </p>
                          <div className="w-full relative mb-4">
                            <Mail size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2" style={{ color: "var(--text-muted)" }} />
                            <input
                              type="email"
                              value={forgotEmail}
                              onChange={(e) => setForgotEmail(e.target.value)}
                              className="vh-input pl-10 w-full"
                              placeholder="Email"
                              aria-label="Email для восстановления пароля"
                              autoComplete="email"
                            />
                          </div>
                          <div className="flex gap-3 w-full">
                            <button
                              type="button"
                              onClick={() => { setShowForgot(false); setForgotEmail(""); }}
                              className="vh-btn-outline flex-1"
                            >
                              Отмена
                            </button>
                            <motion.button
                              type="button"
                              onClick={async () => {
                                if (forgotEmail.trim()) {
                                  try {
                                    await fetch(`${getApiBaseUrl()}/api/auth/forgot-password`, {
                                      method: "POST",
                                      headers: { "Content-Type": "application/json" },
                                      body: JSON.stringify({ email: forgotEmail.trim() }),
                                    });
                                  } catch {
                                    // Показываем успех даже при ошибке (безопасность: не раскрываем наличие email)
                                  }
                                  setForgotSent(true);
                                }
                              }}
                              disabled={!forgotEmail.trim()}
                              className="vh-btn-primary flex-1 flex items-center justify-center gap-2"
                              whileTap={{ scale: 0.97 }}
                            >
                              Отправить
                              <ArrowRight size={14} />
                            </motion.button>
                          </div>
                        </>
                      )}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
