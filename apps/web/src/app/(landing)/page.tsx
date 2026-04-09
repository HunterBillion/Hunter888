"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";
import { CheckCircle2, ChevronRight, ArrowRight } from "lucide-react";
import dynamic from "next/dynamic";
import { EASE_SNAP } from "@/lib/constants";
import { useLandingAuth } from "@/components/landing/LandingAuthContext";

const WaveScene = dynamic(
  () => import("@/components/landing/WaveScene").then((m) => m.WaveScene),
  { ssr: false },
);

/* ── Constants ────────────────────────────────────────────────────── */
const STATS = [
  { target: 60,  suffix: "+", label: "Реальных сценариев" },
  { target: 100, suffix: "",  label: "Типов клиентов" },
  { target: 10,  suffix: "",  label: "Параметров оценки" },
];

const TRUST = [
  "14 дней бесплатно",
  "Без кредитной карты",
  "Готово за 5 минут",
];

const CAROUSEL_SLIDES = [
  { title: "Тренировка", desc: "Менеджер разговаривает с ИИ-клиентом в реальном времени" },
  { title: "Скоринг", desc: "Разбор по 10 параметрам: что сработало, где ошибка" },
  { title: "Арена", desc: "Соревнуйтесь с коллегами. Рейтинг растёт с победами" },
  { title: "Результат", desc: "Видите прогресс: какие клиенты даются, а какие нет" },
] as const;

/* ── Terminal scenarios (loops between them) ──────────────────────── */
const TERMINAL_SCENARIOS = [
  [
    { text: "> Анализ звонка #47...", delay: 0 },
    { text: "  Скрипт          ████████░░  82%", delay: 300 },
    { text: "  Возражения       ██████░░░░  61%", delay: 600 },
    { text: "  Коммуникация     ███████░░░  73%", delay: 900 },
    { text: "  Эмпатия          ████████░░  78%", delay: 1200 },
    { text: "  ⚠ Ловушка: ложная срочность", delay: 1600 },
    { text: "  Итог: 72/100 — Silver III", delay: 2000 },
  ],
  [
    { text: "> Анализ звонка #48...", delay: 0 },
    { text: "  Скрипт          █████████░  91%", delay: 300 },
    { text: "  Возражения       ████████░░  84%", delay: 600 },
    { text: "  Коммуникация     ██████████  96%", delay: 900 },
    { text: "  Эмпатия          █████████░  88%", delay: 1200 },
    { text: "  ✓ Ловушки пройдены", delay: 1600 },
    { text: "  Итог: 89/100 — Gold I ↑", delay: 2000 },
  ],
] as const;

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

/* ── Looping animated terminal ───────────────────────────────────── */
function ScoringTerminal() {
  const [scenarioIdx, setScenarioIdx] = useState(0);
  const [visibleLines, setVisibleLines] = useState(0);
  const [isTyping, setIsTyping] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const started = useRef(false);
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  const scenario = TERMINAL_SCENARIOS[scenarioIdx];

  const clearTimers = useCallback(() => {
    timersRef.current.forEach(clearTimeout);
    timersRef.current = [];
  }, []);

  const runScenario = useCallback((idx: number) => {
    clearTimers();
    setScenarioIdx(idx);
    setVisibleLines(0);
    setIsTyping(true);
    const lines = TERMINAL_SCENARIOS[idx];
    lines.forEach((_, i) => {
      timersRef.current.push(setTimeout(() => setVisibleLines(i + 1), lines[i].delay));
    });
    // After all lines shown, wait 4s then start next scenario
    timersRef.current.push(setTimeout(() => {
      setIsTyping(false);
      timersRef.current.push(setTimeout(() => {
        runScenario((idx + 1) % TERMINAL_SCENARIOS.length);
      }, 4000));
    }, lines[lines.length - 1].delay + 500));
  }, [clearTimers]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !started.current) {
          started.current = true;
          runScenario(0);
        }
      },
      { threshold: 0.3 },
    );
    observer.observe(el);
    return () => {
      observer.disconnect();
      clearTimers();
    };
  }, [runScenario, clearTimers]);

  return (
    <div
      ref={containerRef}
      className="rounded-lg overflow-hidden h-full"
      style={{ background: "#0a0a12", border: "1px solid var(--border-color)" }}
    >
      <div className="flex items-center gap-1.5 px-4 py-2.5" style={{ background: "#111118", borderBottom: "1px solid var(--border-color)" }}>
        <div className="w-2.5 h-2.5 rounded-full" style={{ background: "#ff5f57" }} />
        <div className="w-2.5 h-2.5 rounded-full" style={{ background: "#febc2e" }} />
        <div className="w-2.5 h-2.5 rounded-full" style={{ background: "#28c840" }} />
        <span className="ml-3 text-xs" style={{ color: "var(--text-muted)" }}>scoring_output</span>
      </div>

      <div className="p-5 font-mono text-sm sm:text-base leading-relaxed min-h-[220px]">
        {scenario.slice(0, visibleLines).map((line, i) => (
          <motion.div
            key={`${scenarioIdx}-${i}`}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.25 }}
            style={{
              color: line.text.includes("⚠") ? "var(--danger)"
                : line.text.includes("✓") ? "var(--success)"
                : line.text.includes("Итог") ? "var(--success)"
                : line.text.includes(">") ? "var(--accent)"
                : "var(--text-secondary)",
            }}
          >
            {line.text}
          </motion.div>
        ))}
        {isTyping && visibleLines < scenario.length && (
          <motion.span
            animate={{ opacity: [1, 0] }}
            transition={{ duration: 0.5, repeat: Infinity }}
            style={{ color: "var(--accent)" }}
          >
            █
          </motion.span>
        )}
      </div>
    </div>
  );
}

/* ── Product carousel ────────────────────────────────────────────── */
function ProductCarousel() {
  const [active, setActive] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setActive((p) => (p + 1) % CAROUSEL_SLIDES.length), 4000);
    return () => clearInterval(id);
  }, []);

  return (
    <div
      className="aspect-square rounded-xl overflow-hidden relative"
      style={{ background: "var(--bg-panel)", border: "1px solid var(--border-color)" }}
    >
      <AnimatePresence mode="wait">
        <motion.div
          key={active}
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -20 }}
          transition={{ duration: 0.4 }}
          className="absolute inset-0 flex flex-col items-center justify-center p-6 sm:p-8 text-center"
        >
          <div className="w-full h-2/3 rounded-lg mb-4" style={{ background: "linear-gradient(135deg, var(--bg-tertiary), var(--accent-muted))" }} />
          <h4 className="font-display font-bold text-sm mb-1" style={{ color: "var(--text-primary)" }}>
            {CAROUSEL_SLIDES[active].title}
          </h4>
          <p className="text-xs" style={{ color: "var(--text-muted)" }}>
            {CAROUSEL_SLIDES[active].desc}
          </p>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

/* ── Score bar ────────────────────────────────────────────────────── */
function ScoreBar({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div>
      <div className="flex justify-between items-center mb-1.5">
        <span className="text-sm font-medium" style={{ color: "var(--text-secondary)" }}>{label}</span>
        <span className="text-sm font-bold" style={{ color }}>{value}%</span>
      </div>
      <div className="w-full h-2 rounded-full overflow-hidden" style={{ background: "var(--border-color)" }}>
        <motion.div
          className="h-full rounded-full"
          style={{ background: color }}
          initial={{ width: 0 }}
          whileInView={{ width: `${value}%` }}
          viewport={{ once: true }}
          transition={{ duration: 1, delay: 0.2 }}
        />
      </div>
    </div>
  );
}

/* ═══════════════════════════ PAGE ═════════════════════════════════ */
export default function Home() {
  const { openRegister } = useLandingAuth();

  return (
    <>
      {/* ═══ HERO ═══════════════════════════════════════════════════ */}
      <section className="relative min-h-screen flex flex-col items-center justify-center overflow-hidden">
        <div className="absolute inset-0 z-0"><WaveScene /></div>
        <div className="absolute inset-0 z-[1] pointer-events-none" style={{ background: "linear-gradient(180deg, rgba(0,0,0,0.35) 0%, rgba(0,0,0,0.10) 40%, rgba(0,0,0,0.45) 80%, rgba(0,0,0,0.75) 100%)" }} />
        <div className="absolute inset-0 z-[2] pointer-events-none" style={{ background: "radial-gradient(ellipse at 50% 55%, rgba(124,106,232,0.22) 0%, transparent 55%)" }} />

        <div className="relative z-[4] text-center px-4 sm:px-6 w-full max-w-4xl mx-auto pt-16 sm:pt-20">
          <motion.div initial={{ opacity: 0, scale: 0.88 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.2, duration: 0.85, ease: EASE_SNAP }}>
            <h1 className="font-display font-black leading-none">
              <span className="block select-none" style={{ fontSize: "clamp(5rem, 20vw, 16rem)", lineHeight: 0.88, color: "transparent", WebkitTextStroke: "1.5px var(--accent)", filter: "drop-shadow(0 0 40px var(--accent-glow))" }}>X</span>
              <span className="block tracking-[0.28em]" style={{ fontSize: "clamp(1.4rem, 5.5vw, 4.5rem)", color: "var(--text-primary)" }}>HUNTER</span>
            </h1>
          </motion.div>

          {/* UVP — headline + body */}
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.5 }} className="max-w-xl mx-auto mt-6 mb-8">
            <p
              className="text-lg md:text-xl font-display font-bold mb-3"
              style={{ color: "var(--text-primary)", lineHeight: 1.5 }}
            >
              Каждое возражение — это сделка, которая ещё не закрыта.
            </p>
            <p className="text-base md:text-lg" style={{ color: "var(--text-secondary)", lineHeight: 1.7 }}>
              X Hunter даёт вашей команде сотни тренировок с ИИ-клиентами, которые ведут себя как настоящие — давят, сомневаются, уходят.{" "}
              <strong style={{ color: "var(--text-primary)" }}>После каждой тренировки — точный разбор: где потеряли и как вернуть.</strong>
            </p>
          </motion.div>

          {/* Stats */}
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.62 }} className="flex items-stretch justify-center mb-5">
            {STATS.map(({ target, suffix, label }, i) => (
              <div key={label} className="flex items-stretch">
                {i > 0 && <div className="w-px self-stretch mx-4 sm:mx-6 md:mx-8" style={{ background: "var(--border-color)", opacity: 0.45 }} />}
                <div className="text-center">
                  <div className="font-display font-black leading-none" style={{ fontSize: "clamp(1.6rem, 6vw, 2.5rem)", color: "var(--accent)" }}>
                    <CountUp target={target} suffix={suffix} />
                  </div>
                  <div className="font-display font-medium tracking-wide mt-1.5 uppercase" style={{ fontSize: "clamp(11px, 2vw, 14px)", color: "var(--text-muted)" }}>{label}</div>
                </div>
              </div>
            ))}
          </motion.div>

          {/* CTA in Hero */}
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.72 }} className="mb-5">
            <button
              onClick={openRegister}
              className="inline-flex items-center gap-2 px-7 py-3.5 rounded-xl text-base font-bold transition-transform hover:scale-[1.02] active:scale-[0.98]"
              style={{ background: "var(--accent)", color: "white" }}
            >
              Начать бесплатно <ArrowRight size={18} />
            </button>
          </motion.div>

          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.85 }} className="flex flex-wrap items-center justify-center gap-x-5 gap-y-1.5">
            {TRUST.map((t) => (
              <span key={t} className="flex items-center gap-2 text-sm sm:text-base" style={{ color: "var(--text-secondary)" }}>
                <CheckCircle2 size={16} style={{ color: "var(--success)", flexShrink: 0 }} />{t}
              </span>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ═══ BENTO GRID ═══════════════════════════════════════════ */}
      <section className="relative overflow-hidden" style={{ background: "var(--bg-primary)" }}>
        {/* Grid pattern — fades in from top */}
        <div className="absolute inset-0 pointer-events-none" style={{
          backgroundImage: `linear-gradient(to right, var(--text-muted) 1px, transparent 1px), linear-gradient(to bottom, var(--text-muted) 1px, transparent 1px)`,
          backgroundSize: "24px 24px",
          opacity: 0.03,
          maskImage: "linear-gradient(to bottom, transparent 0%, black 15%)",
          WebkitMaskImage: "linear-gradient(to bottom, transparent 0%, black 15%)",
        }} />

        <div className="relative z-10 max-w-[1440px] mx-auto px-5 sm:px-8 md:px-10 pt-14 sm:pt-20 pb-12">

          {/* Section label */}
          <motion.p
            initial={{ opacity: 0 }}
            whileInView={{ opacity: 1 }}
            viewport={{ once: true }}
            className="text-sm font-medium mb-8"
            style={{ color: "var(--text-muted)" }}
          >
            Тренировка → Разбор → Рост
          </motion.p>

          <div className="grid lg:grid-cols-[1.618fr_1fr] gap-6">

            {/* ── PANEL A: Product Portal (62%) ── */}
            <Link href="/product" className="lg:row-span-2 group">
              <motion.div
                initial={{ opacity: 0, y: 30 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.7 }}
                whileHover={{ scale: 1.003 }}
                className="rounded-xl p-7 sm:p-9 h-full flex flex-col cursor-pointer transition-all"
                style={{ background: "var(--bg-panel)", border: "1px solid var(--border-color)" }}
              >
                <div className="mb-8">
                  <h2
                    className="font-display font-black tracking-tight mb-5 leading-[1.05]"
                    style={{ fontSize: "clamp(1.8rem, 4vw, 2.8rem)", color: "var(--text-primary)" }}
                  >
                    Как это работает
                  </h2>
                  <p className="max-w-lg text-base sm:text-lg leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                    <strong style={{ color: "var(--text-primary)" }}>60 реальных ситуаций</strong> — от первого звонка до кризиса.{" "}
                    <strong style={{ color: "var(--text-primary)" }}>100 типов клиентов</strong> — скептики, манипуляторы, паникёры.{" "}
                    После каждого звонка — <strong style={{ color: "var(--text-primary)" }}>детальный разбор</strong>: что сработало, а где вы потеряли клиента.
                  </p>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-5 flex-grow">
                  <div className="rounded-lg p-5 sm:p-6" style={{ background: "var(--bg-tertiary)", border: "1px solid var(--border-color)" }}>
                    <h3 className="text-sm font-bold uppercase mb-5" style={{ color: "var(--text-muted)" }}>По типам клиентов</h3>
                    <div className="space-y-4">
                      <ScoreBar label="Скептики" value={87} color="var(--success)" />
                      <ScoreBar label="Переговорщики" value={64} color="var(--text-muted)" />
                      <ScoreBar label="Агрессоры" value={42} color="var(--danger)" />
                    </div>
                  </div>

                  <div className="rounded-lg p-5 sm:p-6" style={{ background: "var(--bg-tertiary)", border: "1px solid var(--border-color)" }}>
                    <h3 className="text-sm font-bold uppercase mb-5" style={{ color: "var(--text-muted)" }}>Оценка звонка</h3>
                    <div className="space-y-4">
                      <ScoreBar label="Следование скрипту" value={92} color="var(--success)" />
                      <ScoreBar label="Работа с возражениями" value={71} color="var(--text-muted)" />
                    </div>
                  </div>

                  <div className="sm:col-span-2 mt-1">
                    <ScoringTerminal />
                  </div>
                </div>

                <div className="mt-5 flex items-center gap-2 opacity-40 group-hover:opacity-100 transition-opacity" style={{ color: "var(--text-secondary)" }}>
                  <span className="text-sm font-medium">Узнать больше о продукте</span>
                  <ChevronRight size={16} />
                </div>
              </motion.div>
            </Link>

            {/* ── PANEL B: Pricing Portal (38%) ── */}
            <Link href="/pricing" className="group">
              <motion.div
                initial={{ opacity: 0, y: 30 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.7, delay: 0.15 }}
                whileHover={{ scale: 1.005 }}
                className="rounded-xl p-7 sm:p-9 cursor-pointer transition-all group h-full flex flex-col"
                style={{ background: "var(--bg-panel)", border: "1px solid var(--border-color)" }}
              >
                <h3 className="text-base font-bold uppercase mb-6" style={{ color: "var(--text-muted)" }}>Выберите план</h3>
                <div className="space-y-4 flex-grow">
                  <div className="flex justify-between items-center p-5 rounded-lg" style={{ background: "var(--bg-tertiary)", border: "1px solid var(--border-color)" }}>
                    <div>
                      <h4 className="font-bold text-base uppercase" style={{ color: "var(--text-primary)" }}>Scout</h4>
                      <p className="text-sm mt-0.5" style={{ color: "var(--text-muted)" }}>Базовые сценарии</p>
                    </div>
                    <div className="text-right">
                      <span className="text-xl font-black" style={{ color: "var(--text-primary)" }}>4 900 ₽</span>
                      <span className="text-xs block" style={{ color: "var(--text-muted)" }}>/мес</span>
                    </div>
                  </div>
                  <div className="flex justify-between items-center p-5 rounded-lg" style={{ background: "var(--accent)", color: "white" }}>
                    <div>
                      <h4 className="font-black text-base uppercase">Hunter</h4>
                      <p className="text-sm mt-0.5 opacity-80">Всё включено</p>
                    </div>
                    <div className="text-right">
                      <span className="text-2xl font-black">19 900 ₽</span>
                      <span className="text-xs opacity-80 block">/мес</span>
                    </div>
                  </div>
                  <div className="flex justify-between items-center p-5 rounded-lg" style={{ background: "var(--bg-tertiary)", border: "1px solid var(--border-color)" }}>
                    <div>
                      <h4 className="font-bold text-base uppercase" style={{ color: "var(--text-primary)" }}>Enterprise</h4>
                      <p className="text-sm mt-0.5" style={{ color: "var(--text-muted)" }}>Для команд</p>
                    </div>
                    <span className="text-sm font-bold" style={{ color: "var(--text-primary)" }}>По запросу</span>
                  </div>
                </div>
                <div className="mt-5 flex items-center gap-2 opacity-40 group-hover:opacity-100 transition-opacity" style={{ color: "var(--text-secondary)" }}>
                  <span className="text-sm font-medium">Сравнить тарифы</span>
                  <ChevronRight size={16} />
                </div>
              </motion.div>
            </Link>

            {/* ── PANEL C: Carousel + CEO Quote ── */}
            <motion.div
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.7, delay: 0.3 }}
              className="grid grid-cols-2 gap-4 sm:gap-6"
            >
              <ProductCarousel />

              <div className="aspect-square rounded-xl relative overflow-hidden" style={{ background: "var(--bg-panel)", border: "1px solid var(--border-color)" }}>
                <div className="relative z-10 h-full flex flex-col justify-between p-5 sm:p-7">
                  <div className="flex items-center gap-2">
                    <div className="w-6 h-px" style={{ background: "var(--text-muted)" }} />
                    <span className="text-xs font-display font-bold tracking-widest uppercase" style={{ color: "var(--text-muted)" }}>Основатель</span>
                  </div>
                  <blockquote className="my-auto py-2">
                    <p className="text-xs sm:text-sm leading-relaxed italic" style={{ color: "var(--text-secondary)", fontFamily: "Georgia, 'Times New Roman', serif" }}>
                      &laquo;Я 8 лет руководил отделом продаж в банкротстве и видел, как менеджеры повторяют одни и те же ошибки.{" "}
                      <strong className="not-italic" style={{ color: "var(--text-primary)", fontFamily: "var(--font-display, sans-serif)" }}>X Hunter — это тренажёр, который я хотел иметь тогда.</strong>&raquo;
                    </p>
                  </blockquote>
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-full flex items-center justify-center" style={{ background: "var(--bg-tertiary)", border: "1px solid var(--border-color)" }}>
                      <span className="text-xs font-black" style={{ color: "var(--text-muted)" }}>XH</span>
                    </div>
                    <div>
                      <div className="text-xs font-bold" style={{ color: "var(--text-primary)" }}>CEO</div>
                      <div className="text-xs" style={{ color: "var(--text-muted)" }}>X Hunter</div>
                    </div>
                  </div>
                </div>
              </div>
            </motion.div>
          </div>

          {/* Pre-footer CTA */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="mt-16 text-center py-12 rounded-2xl"
            style={{ background: "var(--bg-panel)", border: "1px solid var(--border-color)" }}
          >
            <h3
              className="font-display font-black tracking-tight mb-4"
              style={{ fontSize: "clamp(1.5rem, 3vw, 2.2rem)", color: "var(--text-primary)" }}
            >
              Готовы попробовать?
            </h3>
            <button
              onClick={openRegister}
              className="inline-flex items-center gap-2 px-8 py-4 rounded-xl text-base font-bold transition-transform hover:scale-[1.02] active:scale-[0.98]"
              style={{ background: "var(--accent)", color: "white" }}
            >
              Начать бесплатно <ArrowRight size={18} />
            </button>
            <p className="mt-3 text-sm" style={{ color: "var(--text-muted)" }}>14 дней · без карты · отмена в любой момент</p>
          </motion.div>
        </div>
      </section>
    </>
  );
}
