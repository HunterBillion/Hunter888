"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";
import { CheckCircle2, ChevronRight, ArrowRight } from "lucide-react";
import dynamic from "next/dynamic";
import { EASE_SNAP } from "@/lib/constants";
import { useLandingAuth } from "@/components/landing/LandingAuthContext";
import { PixelTextReveal } from "@/components/pixel/PixelTextReveal";
import { PixelReviewButton } from "@/components/pixel/PixelReviewButton";
import { PixelGridBackground } from "@/components/landing/PixelGridBackground";
import { getApiBaseUrl } from "@/lib/public-origin";

const WaveScene = dynamic(
  () => import("@/components/landing/WaveScene").then((m) => m.WaveScene),
  { ssr: false },
);

/* ── Constants ────────────────────────────────────────────────────── */
const STATS = [
  { target: 23,  suffix: "%", label: "Рост конверсии за 3 недели" },
  { target: 147, suffix: "",  label: "Менеджеров тренируются" },
  { target: 4,   suffix: ".2 мин", label: "До первого результата" },
];

const TRUST = [
  "14 дней бесплатно",
  "Без кредитной карты",
  "Готово за 5 минут",
];

const CAROUSEL_SLIDES = [
  { title: "Тренировка", desc: "Менеджер разговаривает с ИИ-клиентом в реальном времени", icon: "🎯", accent: "var(--accent)" },
  { title: "Скоринг", desc: "Разбор по 10 параметрам: что сработало, где ошибка", icon: "📊", accent: "var(--success)" },
  { title: "Арена", desc: "Соревнуйтесь с коллегами. Рейтинг растёт с победами", icon: "⚔️", accent: "var(--warning)" },
  { title: "Результат", desc: "Видите прогресс: какие клиенты даются, а какие нет", icon: "📈", accent: "var(--info)" },
  { title: "ИИ-клиент", desc: "100 типов: скептики, манипуляторы, паникёры — как в жизни", icon: "🤖", accent: "#9a3bef" },
  { title: "Обратная связь", desc: "Где потеряли клиента и как вернуть — после каждого звонка", icon: "💬", accent: "var(--accent)" },
  { title: "PvP битвы", desc: "Рейтинговые дуэли с коллегами в реальном времени", icon: "🏆", accent: "var(--warning)" },
  { title: "Геймификация", desc: "XP, стрики, ачивки — обучение через азарт", icon: "🎮", accent: "var(--success)" },
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


/* ── Bento Testimonials (glass-panel, auto-scroll, pause on hover) ─ */
const BENTO_REVIEWS = [
  { name: "Алексей К.", role: "Руководитель отдела продаж", text: "За 2 месяца средний балл команды вырос с 54 до 78.", rating: 5 },
  { name: "Мария В.", role: "Менеджер по продажам", text: "Наконец-то тренировка, где клиент ведёт себя как настоящий.", rating: 5 },
  { name: "Дмитрий Л.", role: "Директор по развитию", text: "Конверсия из первого звонка выросла на 23% за квартал.", rating: 5 },
  { name: "Елена С.", role: "Старший менеджер БФЛ", text: "Каждый разговор — живой опыт. Клиент давит, торгуется — как в реальности.", rating: 4 },
  { name: "Игорь М.", role: "РОП, 15 менеджеров", text: "Вижу слабые места каждого менеджера без прослушки звонков.", rating: 5 },
];

function BentoTestimonials({ onReviewClick }: { onReviewClick: () => void }) {
  const [idx, setIdx] = useState(0);
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    if (paused) return;
    const id = setInterval(() => setIdx((p) => (p + 1) % BENTO_REVIEWS.length), 5000);
    return () => clearInterval(id);
  }, [paused]);

  const review = BENTO_REVIEWS[idx];

  return (
    <div className="flex flex-col gap-3 h-full">
      {/* Review card */}
      <div
        className="rounded-xl relative overflow-hidden flex-1 min-h-[180px]"
        style={{
          background: "var(--bg-panel)",
          border: "1px solid var(--border-color)",
        }}
        onMouseEnter={() => setPaused(true)}
        onMouseLeave={() => setPaused(false)}
      >
        <div className="h-full flex flex-col justify-between p-5">
          {/* Header with star rating */}
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-display font-bold tracking-wider uppercase" style={{ color: "var(--text-muted)" }}>Отзывы</span>
            <div className="flex gap-0.5">
              {[1, 2, 3, 4, 5].map((s) => (
                <span key={s} className="text-[10px]" style={{ color: s <= review.rating ? "#EAB308" : "var(--border-color)" }}>★</span>
              ))}
            </div>
          </div>

          <AnimatePresence mode="wait">
            <motion.div
              key={idx}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.3 }}
              className="my-auto py-2"
            >
              <p className="text-xs sm:text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                &laquo;{review.text}&raquo;
              </p>
            </motion.div>
          </AnimatePresence>

          {/* Author */}
          <div className="flex items-center gap-3">
            <div
              className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
              style={{ background: "var(--accent)", border: "2px solid var(--border-color)" }}
            >
              <span className="text-[10px] font-black text-white">{review.name.charAt(0)}</span>
            </div>
            <div className="min-w-0">
              <div className="text-xs font-bold truncate" style={{ color: "var(--text-primary)" }}>{review.name}</div>
              <div className="text-[10px] truncate" style={{ color: "var(--text-muted)" }}>{review.role}</div>
            </div>
          </div>
        </div>
      </div>

      {/* Pixel review button — directly under the card */}
      <PixelReviewButton onClick={onReviewClick} />
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

  const slide = CAROUSEL_SLIDES[active];

  return (
    <div
      className="rounded-xl overflow-hidden relative h-full min-h-[200px]"
      style={{ background: "var(--bg-panel)", border: "1px solid var(--border-color)" }}
    >
      <AnimatePresence mode="wait">
        <motion.div
          key={active}
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -20 }}
          transition={{ duration: 0.4 }}
          className="absolute inset-0 flex flex-col items-center justify-center p-5 sm:p-6 text-center"
        >
          {/* Icon with accent glow */}
          <div
            className="w-16 h-16 rounded-2xl flex items-center justify-center mb-4"
            style={{
              background: "var(--bg-tertiary)",
              border: `1px solid color-mix(in srgb, ${slide.accent} 30%, transparent)`,
              boxShadow: `0 0 24px color-mix(in srgb, ${slide.accent} 20%, transparent)`,
            }}
          >
            <span className="text-2xl select-none">{slide.icon}</span>
          </div>
          <h4 className="font-display font-bold text-sm mb-1" style={{ color: "var(--text-primary)" }}>
            {slide.title}
          </h4>
          <p className="text-xs leading-relaxed" style={{ color: "var(--text-muted)" }}>
            {slide.desc}
          </p>

          {/* Step indicator */}
          <div className="flex gap-1 mt-3">
            {CAROUSEL_SLIDES.map((_, i) => (
              <div
                key={i}
                className="h-1 rounded-full transition-all duration-300"
                style={{
                  width: i === active ? 16 : 4,
                  background: i === active ? slide.accent : "var(--border-color)",
                }}
              />
            ))}
          </div>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}


/* ═══════════════════════════ PAGE ═════════════════════════════════ */
export default function Home() {
  const { openRegister } = useLandingAuth();
  const [showReviewForm, setShowReviewForm] = useState(false);

  return (
    <>
      {/* ═══ HERO ═══════════════════════════════════════════════════ */}
      <section className="relative min-h-screen flex flex-col items-center justify-center overflow-hidden">
        <div className="absolute inset-0 z-0"><WaveScene /></div>
        <div className="absolute inset-0 z-[1] pointer-events-none" style={{ background: "linear-gradient(180deg, rgba(0,0,0,0.35) 0%, rgba(0,0,0,0.10) 40%, rgba(0,0,0,0.45) 80%, rgba(0,0,0,0.75) 100%)" }} />
        <div className="absolute inset-0 z-[2] pointer-events-none" style={{ background: "radial-gradient(ellipse at 50% 55%, var(--accent-glow) 0%, transparent 55%)" }} />

        <div className="relative z-[4] text-center px-5 sm:px-8 md:px-10 w-full max-w-[1440px] mx-auto pt-16 sm:pt-20">
          <motion.div initial={{ opacity: 0, scale: 0.88 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.2, duration: 0.85, ease: EASE_SNAP }}>
            <h1 className="font-display font-black leading-none">
              <span className="block select-none" style={{ fontSize: "clamp(5rem, 20vw, 16rem)", lineHeight: 0.88, color: "transparent", WebkitTextStroke: "1.5px var(--accent)", filter: "drop-shadow(0 0 40px var(--accent-glow))" }}>X</span>
              <span className="block tracking-widest" style={{ fontSize: "clamp(1.4rem, 5.5vw, 4.5rem)", color: "var(--text-primary)" }}>HUNTER</span>
            </h1>
          </motion.div>

          {/* UVP — headline + body */}
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.5 }} className="max-w-2xl mx-auto mt-6 mb-8">
            <p
              className="text-lg md:text-xl font-display font-bold mb-3"
              style={{ color: "var(--text-primary)", lineHeight: 1.5 }}
            >
              7 из 10 звонков вашего менеджера — в мусор.
            </p>
            <p className="text-base md:text-lg" style={{ color: "var(--text-secondary)", lineHeight: 1.7 }}>
              Мы прослушали 60 000 переговоров и знаем, где он ломается.
              <br />
              <strong style={{ color: "var(--text-primary)" }}>
                XHUNTER тренирует менеджеров БФЛ на реальных сценариях.
                <br />
                <span style={{ hyphens: "none" }}>Не теория — практика со скептиками, манипуляторами и агрессорами.</span>
              </strong>
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
                  <div className="font-display font-semibold tracking-wide mt-1.5 uppercase" style={{ fontSize: "clamp(14px, 2.2vw, 15px)", color: "var(--text-primary)", opacity: 0.75 }}>{label}</div>
                </div>
              </div>
            ))}
          </motion.div>

          {/* CTA in Hero */}
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.72 }} className="mb-5">
            <style>{`
              @keyframes pulse-glow {
                0%, 100% { box-shadow: 0 0 8px rgba(107,77,199,0.3), 0 0 24px rgba(107,77,199,0.1); }
                50% { box-shadow: 0 0 16px rgba(107,77,199,0.5), 0 0 40px rgba(107,77,199,0.25); }
              }
            `}</style>
            <button
              onClick={openRegister}
              className="inline-flex items-center gap-2 px-7 py-3.5 rounded-xl text-base font-bold transition-transform hover:scale-[1.02] active:scale-[0.98]"
              style={{ background: "var(--accent)", color: "white", animation: "pulse-glow 2s ease-in-out infinite" }}
            >
              Бесплатно протестировать за 2 минуты <ArrowRight size={18} />
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
        {/* Canvas pixel grid — full grid + 15% of cells decay ("disappear") */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            maskImage: "linear-gradient(to bottom, transparent 0%, black 15%)",
            WebkitMaskImage: "linear-gradient(to bottom, transparent 0%, black 15%)",
          }}
        >
          <PixelGridBackground cellSize={24} pixelSize={6} />
        </div>

        <div className="relative z-10 max-w-[1440px] mx-auto px-5 sm:px-8 md:px-10 pt-16 sm:pt-24 pb-16 sm:pb-24">

          {/* Section label — pixel text assembly */}
          <div className="mb-8">
            <PixelTextReveal />
          </div>

          <div className="grid lg:grid-cols-[1.618fr_1fr] lg:grid-rows-[1fr_1fr] gap-6">

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

                <div className="rounded-lg overflow-hidden flex-grow" style={{ border: "1px solid var(--border-color)" }}>
                  <video
                    autoPlay
                    loop
                    muted
                    playsInline
                    className="w-full h-full block object-cover"
                    src="/landing/promo.mp4"
                  />
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
                <div className="flex flex-col gap-4 flex-1 justify-between">
                  <div className="flex justify-between items-center p-5 rounded-lg flex-1" style={{ background: "var(--bg-tertiary)", border: "1px solid var(--border-color)" }}>
                    <div>
                      <h4 className="font-bold text-base uppercase" style={{ color: "var(--text-primary)" }}>Scout</h4>
                      <p className="text-sm mt-0.5" style={{ color: "var(--text-muted)" }}>Базовые сценарии</p>
                    </div>
                    <div className="text-right">
                      <span className="text-xl font-black" style={{ color: "var(--text-primary)" }}>4 900 ₽</span>
                      <span className="text-xs block" style={{ color: "var(--text-muted)" }}>/мес</span>
                    </div>
                  </div>
                  <div className="flex justify-between items-center p-5 rounded-lg flex-1" style={{ background: "var(--accent)", color: "white" }}>
                    <div>
                      <h4 className="font-black text-base uppercase">Hunter</h4>
                      <p className="text-sm mt-0.5 opacity-80">Всё включено</p>
                    </div>
                    <div className="text-right">
                      <span className="text-2xl font-black">19 900 ₽</span>
                      <span className="text-xs opacity-80 block">/мес</span>
                    </div>
                  </div>
                  <div className="flex justify-between items-center p-5 rounded-lg flex-1" style={{ background: "var(--bg-tertiary)", border: "1px solid var(--border-color)" }}>
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
              className="grid grid-cols-2 gap-6 h-full"
            >
              {/* Trust block — static testimonial (replaces carousel per WCAG 2.2.2) */}
              <div className="rounded-2xl p-6" style={{ background: "var(--bg-panel)", border: "1px solid var(--border-color)" }}>
                <blockquote className="text-base italic mb-4" style={{ color: "var(--text-secondary)", lineHeight: 1.7 }}>
                  &laquo;Конверсия отдела выросла на 23% за 3 недели. Менеджеры перестали бояться возражений.&raquo;
                </blockquote>
                <div className="text-sm font-medium" style={{ color: "var(--text-muted)" }}>
                  РОП, ООО &laquo;ПравоКонсульт&raquo;
                </div>
              </div>

              <BentoTestimonials onReviewClick={() => setShowReviewForm(true)} />
            </motion.div>
          </div>

          {/* Pre-footer CTA */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="mt-20 text-center py-14 sm:py-16 px-5 sm:px-8 rounded-2xl"
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
              Бесплатно протестировать за 2 минуты <ArrowRight size={18} />
            </button>
            <p className="mt-3 text-sm" style={{ color: "var(--text-muted)" }}>14 дней бесплатно · без кредитной карты · готово за 5 минут</p>
          </motion.div>
        </div>
      </section>

      {/* ═══ ARCADE REVIEW MODAL ═══════════════════════════════════ */}
      <AnimatePresence>
        {showReviewForm && (
          <ArcadeReviewModal onClose={() => setShowReviewForm(false)} />
        )}
      </AnimatePresence>
    </>
  );
}

/* ── Arcade-styled Review Form Modal ─────────────────────── */
function ArcadeReviewModal({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState("");
  const [role, setRole] = useState("");
  const [text, setText] = useState("");
  const [rating, setRating] = useState(5);
  const [hoverRating, setHoverRating] = useState(0);
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");

  const isValid = name.trim().length >= 2 && role.trim().length >= 2 && text.trim().length >= 10;

  const handleSubmit = async () => {
    if (!isValid) { setError("Заполните все поля"); return; }
    setError("");
    setSending(true);
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/reviews`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim(), role: role.trim(), text: text.trim(), rating }),
      });
      if (res.ok) {
        setSent(true);
        setTimeout(onClose, 2500);
      } else {
        setError("Не удалось отправить отзыв. Проверьте поля и попробуйте ещё раз");
      }
    } catch {
      setError("Нет соединения с сервером");
    } finally {
      setSending(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-[100] flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,0.7)", backdropFilter: "blur(4px)" }}
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <motion.div
        initial={{ scale: 0.9, y: 20 }}
        animate={{ scale: 1, y: 0 }}
        exit={{ scale: 0.9, y: 20 }}
        className="w-full max-w-md rounded-xl overflow-hidden"
        style={{
          background: "#0e0b1a",
          border: "2px solid #6b4dc7",
          boxShadow: "0 0 40px rgba(107,77,199,0.3), inset 0 1px 0 rgba(255,255,255,0.05)",
          imageRendering: "auto",
        }}
      >
        {/* Arcade title bar */}
        <div className="px-5 py-3 flex items-center justify-between" style={{ background: "#1a1530", borderBottom: "2px solid #6b4dc7" }}>
          <div className="flex items-center gap-3">
            <span className="text-lg">🎮</span>
            <span className="text-sm font-bold tracking-wider uppercase" style={{ color: "#e8e4f0", fontFamily: "monospace" }}>
              НОВЫЙ ОТЗЫВ
            </span>
          </div>
          <button onClick={onClose} className="w-7 h-7 rounded flex items-center justify-center text-xs font-bold transition-colors hover:bg-[#6b4dc7]" style={{ color: "#e8e4f0", border: "1px solid #5a5478" }}>
            ✕
          </button>
        </div>

        <div className="p-5 space-y-4">
          {sent ? (
            <div className="text-center py-8">
              <div className="text-4xl mb-3">🏆</div>
              <p className="text-base font-bold" style={{ color: "#d4a84b", fontFamily: "monospace" }}>
                ACHIEVEMENT UNLOCKED!
              </p>
              <p className="text-sm mt-2" style={{ color: "#5a5478", fontFamily: "monospace" }}>
                Отзыв отправлен на модерацию
              </p>
            </div>
          ) : (
            <>
              {/* Rating stars */}
              <div>
                <label className="block text-[10px] font-bold tracking-wider uppercase mb-2" style={{ color: "#5a5478", fontFamily: "monospace" }}>
                  РЕЙТИНГ
                </label>
                <div className="flex gap-1">
                  {[1, 2, 3, 4, 5].map((i) => (
                    <button
                      key={i}
                      type="button"
                      onMouseEnter={() => setHoverRating(i)}
                      onMouseLeave={() => setHoverRating(0)}
                      onClick={() => setRating(i)}
                      className="text-xl transition-transform hover:scale-125"
                      style={{ color: i <= (hoverRating || rating) ? "#d4a84b" : "#5a5478" }}
                    >
                      ★
                    </button>
                  ))}
                </div>
              </div>

              {/* Name */}
              <div>
                <label className="block text-[10px] font-bold tracking-wider uppercase mb-2" style={{ color: "#5a5478", fontFamily: "monospace" }}>
                  ИМЯ
                </label>
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Как вас зовут"
                  className="w-full rounded-lg px-3 py-2.5 text-sm outline-none"
                  style={{
                    background: "#1a1530",
                    border: "1px solid #5a5478",
                    color: "#e8e4f0",
                    fontFamily: "monospace",
                  }}
                />
              </div>

              {/* Role */}
              <div>
                <label className="block text-[10px] font-bold tracking-wider uppercase mb-2" style={{ color: "#5a5478", fontFamily: "monospace" }}>
                  ДОЛЖНОСТЬ
                </label>
                <input
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                  placeholder="Ваша должность"
                  className="w-full rounded-lg px-3 py-2.5 text-sm outline-none"
                  style={{
                    background: "#1a1530",
                    border: "1px solid #5a5478",
                    color: "#e8e4f0",
                    fontFamily: "monospace",
                  }}
                />
              </div>

              {/* Review text */}
              <div>
                <label className="block text-[10px] font-bold tracking-wider uppercase mb-2" style={{ color: "#5a5478", fontFamily: "monospace" }}>
                  ОТЗЫВ
                </label>
                <textarea
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  placeholder="Расскажите о вашем опыте"
                  rows={3}
                  className="w-full rounded-lg px-3 py-2.5 text-sm outline-none resize-none"
                  style={{
                    background: "#1a1530",
                    border: "1px solid #5a5478",
                    color: "#e8e4f0",
                    fontFamily: "monospace",
                  }}
                />
              </div>

              {error && (
                <p className="text-xs font-bold" style={{ color: "#ff5f57", fontFamily: "monospace" }}>
                  ⚠ {error}
                </p>
              )}

              <button
                onClick={handleSubmit}
                disabled={sending || !isValid}
                className="w-full rounded-lg px-4 py-3 text-sm font-bold uppercase tracking-wider transition-all disabled:opacity-40 hover:brightness-110"
                style={{
                  background: "linear-gradient(135deg, #6b4dc7, #9a3bef)",
                  color: "#fff",
                  border: "2px solid #9a3bef",
                  fontFamily: "monospace",
                  boxShadow: isValid ? "0 0 20px rgba(107,77,199,0.4)" : "none",
                }}
              >
                {sending ? "ОТПРАВКА..." : "▶ ОТПРАВИТЬ ОТЗЫВ"}
              </button>
            </>
          )}
        </div>
      </motion.div>
    </motion.div>
  );
}
