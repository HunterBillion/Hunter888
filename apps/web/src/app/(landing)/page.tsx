"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { motion } from "framer-motion";
import Link from "next/link";
import {
  CheckCircle2,
  Target,
  Terminal,
  ChevronRight,
} from "lucide-react";
import dynamic from "next/dynamic";
import { EASE_SNAP } from "@/lib/constants";

const WaveScene = dynamic(
  () => import("@/components/landing/WaveScene").then((m) => m.WaveScene),
  { ssr: false },
);

/* ── Constants ────────────────────────────────────────────────────── */
const STATS = [
  { target: 6000, suffix: "+", label: "Комбинаций" },
  { target: 10,   suffix: "",  label: "Слоёв скоринга" },
  { target: 24,   suffix: "",  label: "Ранга PvP" },
];

const TRUST = [
  "14 дней бесплатно",
  "Без кредитной карты",
  "Готово за 5 минут",
];

/* ── CountUp ─────────────────────────────────────────────────────── */
function CountUp({ target, suffix }: { target: number; suffix: string }) {
  const [count, setCount] = useState(0);
  const ref = useRef<HTMLSpanElement>(null);
  const started = useRef(false);

  const animate = useCallback(() => {
    const duration = 1800;
    const start = performance.now();
    const step = (now: number) => {
      const progress = Math.min((now - start) / duration, 1);
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

/* ── FlipCube: 3D rotating cube — date on one face, time on another ── */
function FlipCube() {
  const [time, setTime] = useState({ h: "00", m: "00", s: "00" });
  const [date, setDate] = useState({ d: "01", mo: "01", y: "2026" });
  const [showDate, setShowDate] = useState(true);

  useEffect(() => {
    const update = () => {
      const now = new Date();
      setTime({
        h: now.getHours().toString().padStart(2, "0"),
        m: now.getMinutes().toString().padStart(2, "0"),
        s: now.getSeconds().toString().padStart(2, "0"),
      });
      setDate({
        d: now.getDate().toString().padStart(2, "0"),
        mo: (now.getMonth() + 1).toString().padStart(2, "0"),
        y: now.getFullYear().toString(),
      });
    };
    update();
    const tickId = setInterval(update, 1000);
    const flipId = setInterval(() => setShowDate((p) => !p), 5000);
    return () => { clearInterval(tickId); clearInterval(flipId); };
  }, []);

  return (
    <div className="aspect-square rounded-xl overflow-hidden relative" style={{ background: "var(--bg-panel)", border: "1px solid var(--border-color)", perspective: "600px" }}>
      <div
        className="w-full h-full relative transition-transform duration-700"
        style={{
          transformStyle: "preserve-3d",
          transform: showDate ? "rotateX(0deg)" : "rotateX(-90deg)",
        }}
      >
        {/* Face 1: DATE */}
        <div
          className="absolute inset-0 flex flex-col items-center justify-center p-6"
          style={{ backfaceVisibility: "hidden" }}
        >
          <div className="text-[10px] font-mono tracking-widest uppercase mb-3" style={{ color: "var(--text-muted)" }}>
            ДАТА
          </div>
          <div className="flex items-baseline gap-1 tabular-nums">
            <span className="text-4xl sm:text-5xl font-black" style={{ color: "var(--accent)", textShadow: "0 0 30px var(--accent-glow)" }}>
              {date.d}
            </span>
            <span className="text-xl font-bold" style={{ color: "var(--text-muted)" }}>.</span>
            <span className="text-4xl sm:text-5xl font-black" style={{ color: "var(--accent)", textShadow: "0 0 30px var(--accent-glow)" }}>
              {date.mo}
            </span>
            <span className="text-xl font-bold" style={{ color: "var(--text-muted)" }}>.</span>
            <span className="text-2xl font-bold" style={{ color: "var(--text-muted)" }}>
              {date.y}
            </span>
          </div>
          <div className="mt-4 text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
            Никогда не поздно начать
          </div>
        </div>

        {/* Face 2: TIME */}
        <div
          className="absolute inset-0 flex flex-col items-center justify-center p-6"
          style={{ backfaceVisibility: "hidden", transform: "rotateX(90deg)" }}
        >
          <div className="text-[10px] font-mono tracking-widest uppercase mb-3" style={{ color: "var(--text-muted)" }}>
            ВРЕМЯ
          </div>
          <div className="flex items-baseline tabular-nums">
            <span className="text-4xl sm:text-5xl font-black" style={{ color: "var(--neon-green)", textShadow: "0 0 30px var(--neon-green)" }}>
              {time.h}
            </span>
            <motion.span
              className="text-3xl font-bold mx-0.5"
              style={{ color: "var(--neon-green)" }}
              animate={{ opacity: [1, 0.2, 1] }}
              transition={{ duration: 1, repeat: Infinity }}
            >
              :
            </motion.span>
            <span className="text-4xl sm:text-5xl font-black" style={{ color: "var(--neon-green)", textShadow: "0 0 30px var(--neon-green)" }}>
              {time.m}
            </span>
            <motion.span
              className="text-3xl font-bold mx-0.5"
              style={{ color: "var(--neon-green)" }}
              animate={{ opacity: [1, 0.2, 1] }}
              transition={{ duration: 1, repeat: Infinity }}
            >
              :
            </motion.span>
            <span className="text-2xl font-bold" style={{ color: "var(--neon-green)", opacity: 0.7 }}>
              {time.s}
            </span>
          </div>
          <div className="mt-4 text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
            Каждая секунда — шанс
          </div>
        </div>
      </div>

      {/* Corner indicator */}
      <div className="absolute top-4 right-4 flex gap-1.5">
        <div className="w-1.5 h-1.5 rounded-full transition-all duration-300" style={{ background: showDate ? "var(--accent)" : "var(--border-color)" }} />
        <div className="w-1.5 h-1.5 rounded-full transition-all duration-300" style={{ background: !showDate ? "var(--neon-green)" : "var(--border-color)" }} />
      </div>
    </div>
  );
}

/* ── NeuralBars ──────────────────────────────────────────────────── */
function NeuralBars() {
  const heights = [50, 75, 33, 100, 66, 55];
  return (
    <div className="flex items-end gap-1 h-32">
      {heights.map((h, i) => (
        <motion.div
          key={i}
          className="w-full rounded-t-sm"
          style={{ background: `rgba(99, 102, 241, ${0.2 + (i * 0.15)})`, height: `${h}%` }}
          whileHover={{ height: `${Math.min(h + 15, 100)}%` }}
          transition={{ duration: 0.3 }}
        />
      ))}
    </div>
  );
}

/* ═══════════════════════════ PAGE ═════════════════════════════════ */
export default function Home() {
  return (
    <>
      {/* ═══ HERO ═══════════════════════════════════════════════════ */}
      <section className="relative min-h-screen flex flex-col items-center justify-center overflow-hidden">
        <div className="absolute inset-0 z-0"><WaveScene /></div>

        <div className="absolute inset-0 z-[1] pointer-events-none" style={{ background: "linear-gradient(180deg, rgba(0,0,0,0.35) 0%, rgba(0,0,0,0.15) 50%, rgba(0,0,0,0.4) 100%)" }} />
        <div className="absolute inset-0 z-[2] pointer-events-none" style={{ background: "radial-gradient(ellipse at 50% 55%, rgba(99,102,241,0.22) 0%, transparent 55%)" }} />
        <div className="fixed inset-0 scanlines z-[3] opacity-[0.04] mix-blend-overlay pointer-events-none" />
        <div className="absolute inset-0 z-[3] pointer-events-none" style={{ backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='1'/%3E%3C/svg%3E")`, backgroundRepeat: "repeat", backgroundSize: "128px 128px", opacity: 0.035, mixBlendMode: "overlay" }} />

        <div className="relative z-[4] text-center px-4 sm:px-6 w-full max-w-4xl mx-auto pt-16 sm:pt-20">
          {/* Badge */}
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="inline-flex items-center gap-2 rounded-full px-4 py-1.5 mb-7" style={{ background: "rgba(99,102,241,0.12)", border: "1px solid rgba(99,102,241,0.32)" }}>
            <motion.span className="w-1.5 h-1.5 rounded-full" style={{ background: "var(--accent)" }} animate={{ opacity: [1, 0.25, 1] }} transition={{ duration: 1.8, repeat: Infinity }} />
            <span className="font-display text-sm font-bold tracking-[0.12em] italic" style={{ color: "var(--accent)", textShadow: "0 0 20px rgba(99,102,241,0.4)" }}>
              Выбор игры, важнее самой игры
            </span>
          </motion.div>

          {/* Title */}
          <motion.div initial={{ opacity: 0, scale: 0.88 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.2, duration: 0.85, ease: EASE_SNAP }}>
            <h1 className="font-display font-black leading-none">
              <span className="block select-none" style={{ fontSize: "clamp(5rem, 20vw, 16rem)", lineHeight: 0.88, color: "transparent", WebkitTextStroke: "1.5px var(--accent)", filter: "drop-shadow(0 0 40px var(--accent-glow))" }}>X</span>
              <span className="block tracking-[0.28em]" style={{ fontSize: "clamp(1.4rem, 5.5vw, 4.5rem)", color: "var(--text-primary)" }}>HUNTER</span>
            </h1>
          </motion.div>

          {/* UVP */}
          <motion.p initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.5 }} className="text-sm md:text-base max-w-sm mx-auto mt-5 mb-7" style={{ color: "var(--text-secondary)", lineHeight: 1.8 }}>
            Менеджеры теряют сделки на возражениях.{" "}
            <span style={{ color: "var(--text-primary)", fontWeight: 500 }}>X·Hunter учит их работать — с ИИ, данными и живым рейтингом.</span>
          </motion.p>

          {/* Stats */}
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.62 }} className="flex items-stretch justify-center mb-5">
            {STATS.map(({ target, suffix, label }, i) => (
              <div key={label} className="flex items-stretch">
                {i > 0 && <div className="w-px self-stretch mx-4 sm:mx-6 md:mx-8" style={{ background: "var(--border-color)", opacity: 0.45 }} />}
                <div className="text-center">
                  <div className="font-display font-black leading-none" style={{ fontSize: "clamp(1.6rem, 6vw, 2.5rem)", color: "var(--accent)", textShadow: "0 0 24px var(--accent-glow)" }}>
                    <CountUp target={target} suffix={suffix} />
                  </div>
                  <div className="font-mono tracking-[0.2em] mt-1.5 uppercase" style={{ fontSize: "clamp(8px, 1.8vw, 11px)", color: "var(--text-muted)" }}>{label}</div>
                </div>
              </div>
            ))}
          </motion.div>

          {/* Trust */}
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.78 }} className="flex flex-wrap items-center justify-center gap-x-5 gap-y-1.5">
            {TRUST.map((t) => (
              <span key={t} className="flex items-center gap-2 text-sm sm:text-base" style={{ color: "var(--text-secondary)" }}>
                <CheckCircle2 size={16} style={{ color: "var(--neon-green)", flexShrink: 0 }} />{t}
              </span>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ═══ TRANSITION ═══════════════════════════════════════════ */}
      <div aria-hidden style={{ height: "120px", marginTop: "-120px", position: "relative", zIndex: 5, background: "linear-gradient(180deg, transparent 0%, var(--bg-secondary) 100%)", pointerEvents: "none" }} />

      {/* ═══ BENTO GRID — GOLDEN RATIO PORTALS ═══════════════════ */}
      <section className="relative overflow-hidden" style={{ background: "var(--bg-secondary)" }}>
        {/* Geometric grid background */}
        <div className="absolute inset-0 opacity-[0.03] pointer-events-none" style={{ backgroundImage: `linear-gradient(to right, var(--text-muted) 1px, transparent 1px), linear-gradient(to bottom, var(--text-muted) 1px, transparent 1px)`, backgroundSize: "24px 24px" }} />

        <div className="relative z-10 max-w-[1920px] mx-auto px-5 sm:px-8 md:px-10 pt-14 sm:pt-20 pb-20">
          {/* Golden Ratio Grid: 1.618 : 1 */}
          <div className="grid lg:grid-cols-[1.618fr_1fr] gap-6">

            {/* ── PANEL A: Product Portal (62%) ── */}
            <Link href="/product" className="lg:row-span-2 group">
              <motion.div
                initial={{ opacity: 0, y: 30 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.7 }}
                whileHover={{ scale: 1.005, borderColor: "var(--accent)" }}
                className="rounded-xl p-6 sm:p-8 h-full flex flex-col cursor-pointer transition-all"
                style={{ background: "var(--bg-panel)", border: "1px solid var(--border-color)" }}
              >
                <div className="flex justify-between items-start mb-8 sm:mb-12">
                  <div>
                    <h2 className="font-display font-black tracking-tighter mb-4 leading-none uppercase" style={{ fontSize: "clamp(2rem, 4.5vw, 3.5rem)", color: "var(--text-primary)" }}>
                      ЦЕНТРАЛЬНЫЙ<br /><span style={{ color: "var(--accent)" }}>ИНТЕЛЛЕКТ</span>
                    </h2>
                    <p className="max-w-md text-sm sm:text-base" style={{ color: "var(--text-secondary)" }}>
                      60 сценариев × 100 архетипов ИИ-клиентов. Голосовые тренировки с 10-слойным скорингом каждой фразы. PvP-арена с рейтингом Glicko-2.
                    </p>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <motion.span className="w-2 h-2 rounded-full" style={{ background: "var(--neon-green)", boxShadow: "0 0 10px var(--neon-green)" }} animate={{ opacity: [1, 0.3, 1] }} transition={{ duration: 1.8, repeat: Infinity }} />
                    <span className="text-[10px] font-bold tracking-widest uppercase" style={{ color: "var(--neon-green)" }}>ПРЯМОЙ ЭФИР</span>
                  </div>
                </div>

                {/* Data Visualizations */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 flex-grow">
                  <div className="rounded-lg p-6 relative overflow-hidden" style={{ background: "var(--bg-tertiary)", border: "1px solid var(--border-color)" }}>
                    <h3 className="text-xs font-bold tracking-widest uppercase mb-4" style={{ color: "var(--text-muted)" }}>ПРОГРЕСС ПО АРХЕТИПАМ</h3>
                    <NeuralBars />
                  </div>
                  <div className="rounded-lg p-6" style={{ background: "var(--bg-tertiary)", border: "1px solid var(--border-color)" }}>
                    <h3 className="text-xs font-bold tracking-widest uppercase mb-4" style={{ color: "var(--text-muted)" }}>ЭФФЕКТИВНОСТЬ СКОРИНГА</h3>
                    <div className="space-y-3">
                      <div>
                        <div className="flex justify-between items-center text-[10px] font-mono mb-1">
                          <span style={{ color: "var(--text-muted)" }}>L1_SCRIPT</span>
                          <span style={{ color: "var(--neon-green)" }}>98.4%</span>
                        </div>
                        <div className="w-full h-1 rounded-full overflow-hidden" style={{ background: "var(--border-color)" }}>
                          <motion.div className="h-full rounded-full" style={{ background: "var(--neon-green)", boxShadow: "0 0 8px var(--neon-green)" }} initial={{ width: 0 }} whileInView={{ width: "98%" }} viewport={{ once: true }} transition={{ duration: 1.2, delay: 0.3 }} />
                        </div>
                      </div>
                      <div className="mt-3">
                        <div className="flex justify-between items-center text-[10px] font-mono mb-1">
                          <span style={{ color: "var(--text-muted)" }}>L2_OBJECTIONS</span>
                          <span style={{ color: "var(--accent)" }}>72.1%</span>
                        </div>
                        <div className="w-full h-1 rounded-full overflow-hidden" style={{ background: "var(--border-color)" }}>
                          <motion.div className="h-full rounded-full" style={{ background: "var(--accent)", boxShadow: "0 0 8px var(--accent-glow)" }} initial={{ width: 0 }} whileInView={{ width: "72%" }} viewport={{ once: true }} transition={{ duration: 1.2, delay: 0.5 }} />
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Main Visualization */}
                  <div className="sm:col-span-2 mt-2 rounded-lg overflow-hidden relative aspect-video" style={{ border: "1px solid var(--border-color)" }}>
                    {/* TODO: Заменить на реальное изображение — слот для пользовательского ассета */}
                    <div className="w-full h-full" style={{ background: "linear-gradient(135deg, var(--bg-tertiary) 0%, var(--accent-muted) 50%, var(--bg-tertiary) 100%)" }} />
                    <div className="absolute inset-0" style={{ background: "linear-gradient(to top, var(--bg-secondary), transparent)" }} />
                    <div className="absolute bottom-4 left-4 flex gap-3">
                      <span className="px-3 py-1 rounded text-[10px] font-mono" style={{ background: "var(--bg-panel)", backdropFilter: "blur(8px)", border: "1px solid var(--border-color)", color: "var(--accent)" }}>SCENARIO_V3_ACTIVE</span>
                      <span className="px-3 py-1 rounded text-[10px] font-mono hidden sm:block" style={{ background: "var(--bg-panel)", backdropFilter: "blur(8px)", border: "1px solid var(--border-color)", color: "var(--text-muted)" }}>ENCRYPTED_LINK_ESTABLISHED</span>
                    </div>
                  </div>
                </div>

                {/* Portal indicator */}
                <div className="mt-4 flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity" style={{ color: "var(--accent)" }}>
                  <span className="text-xs font-mono tracking-wider">ОТКРЫТЬ О ПРОДУКТЕ</span>
                  <ChevronRight size={14} />
                </div>
              </motion.div>
            </Link>

            {/* ── PANEL B: Pricing Portal (38% top) ── */}
            <Link href="/pricing">
              <motion.div
                initial={{ opacity: 0, y: 30 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.7, delay: 0.15 }}
                whileHover={{ scale: 1.01, borderColor: "var(--accent)" }}
                className="rounded-xl p-6 sm:p-8 cursor-pointer transition-all group"
                style={{ background: "var(--bg-panel)", border: "1px solid var(--border-color)" }}
              >
                <h3 className="text-xs font-bold tracking-[0.2em] uppercase mb-6 flex items-center gap-2" style={{ color: "var(--text-muted)" }}>
                  <Target size={14} style={{ color: "var(--accent)" }} /> МОДЕЛИ ПОДПИСКИ
                </h3>
                <div className="space-y-3">
                  <div className="flex justify-between items-center p-4 rounded-lg" style={{ background: "var(--bg-tertiary)", border: "1px solid var(--border-color)" }}>
                    <div>
                      <h4 className="font-bold text-sm uppercase" style={{ color: "var(--text-primary)" }}>SCOUT</h4>
                      <p className="text-[10px] uppercase tracking-tighter" style={{ color: "var(--text-muted)" }}>14 дней бесплатно</p>
                    </div>
                    <div className="text-right">
                      <span className="text-lg font-black" style={{ color: "var(--text-primary)" }}>$49</span>
                      <span className="text-[10px] block" style={{ color: "var(--text-muted)" }}>/мес</span>
                    </div>
                  </div>
                  <div className="flex justify-between items-center p-4 rounded-lg transition-transform" style={{ background: "var(--accent)", color: "white" }}>
                    <div>
                      <h4 className="font-black text-sm uppercase">HUNTER</h4>
                      <p className="text-[10px] opacity-80 uppercase tracking-tighter font-bold">Полное развертывание</p>
                    </div>
                    <div className="text-right">
                      <span className="text-2xl font-black">$199</span>
                      <span className="text-[10px] opacity-80 block font-bold">/мес</span>
                    </div>
                  </div>
                  <div className="flex justify-between items-center p-4 rounded-lg" style={{ background: "var(--bg-tertiary)", border: "1px solid var(--border-color)" }}>
                    <div>
                      <h4 className="font-bold text-sm uppercase" style={{ color: "var(--text-primary)" }}>API PROTOCOL</h4>
                      <p className="text-[10px] uppercase tracking-tighter" style={{ color: "var(--text-muted)" }}>Прямой API доступ</p>
                    </div>
                    <div className="text-right flex items-center gap-2">
                      <Terminal size={16} style={{ color: "var(--accent)" }} />
                      <span className="text-[10px] font-bold" style={{ color: "var(--text-primary)" }}>ИНДИВИДУАЛЬНО</span>
                    </div>
                  </div>
                </div>
                <div className="mt-4 flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity" style={{ color: "var(--accent)" }}>
                  <span className="text-xs font-mono tracking-wider">ТАРИФЫ И ПАРТНЁРЫ</span>
                  <ChevronRight size={14} />
                </div>
              </motion.div>
            </Link>

            {/* ── PANEL C: Interactive Duo (38% bottom) ── */}
            <motion.div
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.7, delay: 0.3 }}
              className="grid grid-cols-2 gap-4 sm:gap-6"
            >
              {/* 3D Flip Cube: Date ↔ Time */}
              <FlipCube />

              {/* CEO Quote — immersive */}
              <div
                className="aspect-square rounded-xl relative overflow-hidden group"
                style={{ background: "var(--bg-panel)", border: "1px solid var(--border-color)" }}
              >
                {/* Gradient accent background */}
                <div
                  className="absolute inset-0 opacity-[0.06] group-hover:opacity-[0.12] transition-opacity duration-700"
                  style={{ background: "radial-gradient(circle at 30% 70%, var(--accent), transparent 60%)" }}
                />

                {/* Large decorative quote mark */}
                <div className="absolute -top-2 -left-1 opacity-[0.04]" style={{ fontSize: "clamp(120px, 20vw, 200px)", lineHeight: 1, fontFamily: "Georgia, serif", color: "var(--accent)" }}>
                  &ldquo;
                </div>

                {/* Content */}
                <div className="relative z-10 h-full flex flex-col justify-between p-5 sm:p-6">
                  {/* Top: label */}
                  <div className="flex items-center gap-2">
                    <div className="w-6 h-px" style={{ background: "var(--accent)" }} />
                    <span className="text-[9px] font-mono tracking-[0.3em] uppercase" style={{ color: "var(--accent)" }}>
                      VISION
                    </span>
                  </div>

                  {/* Center: quote */}
                  <blockquote className="my-auto py-2">
                    <p
                      className="font-display font-black tracking-tight leading-[1.15] uppercase"
                      style={{ fontSize: "clamp(0.85rem, 2.2vw, 1.35rem)", color: "var(--text-primary)" }}
                    >
                      МЫ НЕ ПРЕДСКАЗЫВАЕМ БУДУЩЕЕ.{" "}
                      <span style={{ color: "var(--accent)" }}>НО С НАМИ</span>{" "}
                      МЫ ЕГО ПРОЕКТИРУЕМ.
                    </p>
                  </blockquote>

                  {/* Bottom: attribution + accent line */}
                  <div>
                    <div className="flex items-center gap-2 mb-3">
                      <div className="w-8 h-8 rounded-full flex items-center justify-center" style={{ background: "var(--accent-muted)", border: "1px solid var(--border-color)" }}>
                        <span className="text-[10px] font-black" style={{ color: "var(--accent)" }}>XH</span>
                      </div>
                      <div>
                        <div className="text-[10px] font-bold" style={{ color: "var(--text-primary)" }}>CEO</div>
                        <div className="text-[9px] font-mono tracking-wider" style={{ color: "var(--text-muted)" }}>X·HUNTER</div>
                      </div>
                    </div>
                    <div className="h-[2px] w-full rounded-full overflow-hidden" style={{ background: "var(--border-color)" }}>
                      <motion.div
                        className="h-full rounded-full"
                        style={{ background: "var(--accent)" }}
                        initial={{ width: "0%" }}
                        whileInView={{ width: "100%" }}
                        viewport={{ once: true }}
                        transition={{ duration: 2, delay: 0.5 }}
                      />
                    </div>
                  </div>
                </div>
              </div>
            </motion.div>
          </div>
        </div>
      </section>
    </>
  );
}
