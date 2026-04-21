"use client";

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { CaretLeft, CaretRight, Terminal } from "@phosphor-icons/react";
import { getApiBaseUrl } from "@/lib/public-origin";

interface Review {
  name?: string;
  role: string;
  text: string;
  rating?: number;
}

const FALLBACK_REVIEWS: Review[] = [
  {
    role: "Руководитель отдела продаж",
    text: "За 2 месяца средний балл команды вырос с 54 до 78. Менеджеры сами просят доступ к тренажёру — раньше от обучения бегали.",
  },
  {
    role: "Менеджер по продажам",
    text: "Наконец-то тренировка, где клиент ведёт себя как настоящий. Первый раз я проиграла — и это было полезнее любого тренинга.",
  },
  {
    role: "Директор по развитию",
    text: "Подключили 12 менеджеров. Конверсия из первого звонка выросла на 23% за квартал. ROI окупился за первый месяц.",
  },
  {
    role: "Старший менеджер БФЛ",
    text: "Раньше скрипты учили по бумажке. Теперь каждый разговор — это живой опыт. Клиент давит, торгуется, уходит — как в реальности.",
  },
  {
    role: "РОП, 15 менеджеров",
    text: "Вижу слабые места каждого менеджера без прослушки звонков. Аналитика показывает всё: кто теряется на возражениях, кто не закрывает.",
  },
];

const AUTO_INTERVAL = 6000;

interface ReviewFormProps {
  onClose: () => void;
  onSubmit: (data: Review) => void;
}

function StarInput({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  const [hover, setHover] = useState(0);
  return (
    <div className="flex gap-1">
      {[1, 2, 3, 4, 5].map((i) => (
        <button
          key={i}
          type="button"
          onMouseEnter={() => setHover(i)}
          onMouseLeave={() => setHover(0)}
          onClick={() => onChange(i)}
          className="text-lg transition-transform hover:scale-125"
          style={{ color: i <= (hover || value) ? "var(--warning, #EAB308)" : "var(--text-muted)" }}
        >
          ★
        </button>
      ))}
    </div>
  );
}

function ReviewForm({ onClose, onSubmit }: ReviewFormProps) {
  const [name, setName] = useState("");
  const [role, setRole] = useState("");
  const [text, setText] = useState("");
  const [rating, setRating] = useState(5);
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");

  const isValid = name.trim().length >= 2 && role.trim().length >= 2 && text.trim().length >= 10;

  const handleSubmit = async () => {
    if (name.trim().length < 2) { setError("Укажите имя (мин. 2 символа)"); return; }
    if (role.trim().length < 2) { setError("Укажите должность (мин. 2 символа)"); return; }
    if (text.trim().length < 10) { setError("Напишите отзыв подробнее (мин. 10 символов)"); return; }
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
        onSubmit({ name: name.trim(), role: role.trim(), text: text.trim(), rating });
      } else {
        setError("Ошибка отправки. Попробуйте ещё раз.");
      }
    } catch {
      setError("Нет соединения с сервером");
    } finally {
      setSending(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 10 }}
      className="mt-4 rounded-xl overflow-hidden"
      style={{
        background: "var(--bg-secondary)",
        border: "1px solid var(--border-color)",
      }}
    >
      <div
        className="flex items-center gap-2 px-4 py-2"
        style={{ background: "var(--bg-tertiary)", borderBottom: "1px solid var(--border-color)" }}
      >
        <div className="flex gap-1.5">
          <button onClick={onClose} className="w-3 h-3 rounded-full bg-[#FF5F57] hover:brightness-110 transition-all" />
          <div className="w-3 h-3 rounded-full bg-[#FEBC2E]" />
          <div className="w-3 h-3 rounded-full bg-[#28C840]" />
        </div>
        <span className="ml-2 text-xs font-mono" style={{ color: "var(--text-muted)" }}>
          new-review — xhunter
        </span>
      </div>

      <div className="p-5 space-y-4">
        {sent ? (
          <div className="text-center py-4">
            <p className="font-mono text-sm" style={{ color: "var(--accent)" }}>
              $ echo &quot;Спасибо за отзыв!&quot;
            </p>
            <p className="font-mono text-xs mt-2" style={{ color: "var(--text-muted)" }}>
              Ваш отзыв опубликован
            </p>
          </div>
        ) : (
          <>
            <div>
              <label className="block text-xs font-mono mb-1.5 uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                $ name
              </label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Ваше имя"
                className="w-full rounded-lg px-3 py-2.5 text-sm font-mono outline-none transition-colors"
                style={{
                  background: "var(--bg-primary)",
                  border: "1px solid var(--border-color)",
                  color: "var(--text-primary)",
                }}
              />
            </div>
            <div>
              <label className="block text-xs font-mono mb-1.5 uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                $ role
              </label>
              <input
                value={role}
                onChange={(e) => setRole(e.target.value)}
                placeholder="Ваша должность"
                className="w-full rounded-lg px-3 py-2.5 text-sm font-mono outline-none transition-colors"
                style={{
                  background: "var(--bg-primary)",
                  border: "1px solid var(--border-color)",
                  color: "var(--text-primary)",
                }}
              />
            </div>
            <div>
              <label className="block text-xs font-mono mb-1.5 uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                $ rating
              </label>
              <StarInput value={rating} onChange={setRating} />
            </div>
            <div>
              <label className="block text-xs font-mono mb-1.5 uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                $ review
              </label>
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Расскажите о вашем опыте с X Hunter"
                rows={3}
                className="w-full rounded-lg px-3 py-2.5 text-sm font-mono outline-none resize-none transition-colors"
                style={{
                  background: "var(--bg-primary)",
                  border: "1px solid var(--border-color)",
                  color: "var(--text-primary)",
                }}
              />
            </div>
            {error && (
              <p className="text-xs font-mono" style={{ color: "var(--danger)" }}>{error}</p>
            )}
            <button
              onClick={handleSubmit}
              disabled={sending || !isValid}
              className="w-full rounded-lg px-4 py-2.5 text-sm font-semibold transition-all disabled:opacity-40"
              style={{ background: "var(--accent)", color: "#fff" }}
            >
              {sending ? "Отправка..." : "Отправить отзыв"}
            </button>
          </>
        )}
      </div>
    </motion.div>
  );
}

export function TestimonialsCarousel() {
  const [reviews, setReviews] = useState<Review[]>(FALLBACK_REVIEWS);
  const [current, setCurrent] = useState(0);
  const [direction, setDirection] = useState(1);
  const [showForm, setShowForm] = useState(false);

  // Load reviews from API, merge with fallback
  useEffect(() => {
    fetch(`${getApiBaseUrl()}/api/reviews`)
      .then((r) => r.ok ? r.json() : [])
      .then((data: Review[]) => {
        if (data.length > 0) {
          // API reviews first, then fallback (deduplicate by text)
          const seen = new Set(data.map((r) => r.text));
          const merged = [...data, ...FALLBACK_REVIEWS.filter((r) => !seen.has(r.text))];
          setReviews(merged);
        }
      })
      .catch(() => { /* keep fallback */ });
  }, []);

  const next = useCallback(() => {
    setDirection(1);
    setCurrent((prev) => (prev + 1) % reviews.length);
  }, [reviews.length]);

  const prev = useCallback(() => {
    setDirection(-1);
    setCurrent((prev) => (prev - 1 + reviews.length) % reviews.length);
  }, [reviews.length]);

  useEffect(() => {
    if (showForm) return;
    const timer = setInterval(next, AUTO_INTERVAL);
    return () => clearInterval(timer);
  }, [next, showForm]);

  const t = reviews[current % reviews.length];

  return (
    <div className="relative">
      {/* Terminal-style card */}
      <div
        className="rounded-xl overflow-hidden"
        style={{
          background: "var(--bg-secondary)",
          border: "1px solid var(--border-color)",
        }}
      >
        {/* macOS terminal title bar */}
        <div
          className="flex items-center gap-2 px-4 py-2"
          style={{
            background: "var(--bg-tertiary)",
            borderBottom: "1px solid var(--border-color)",
          }}
        >
          <div className="flex gap-1.5">
            <div className="w-3 h-3 rounded-full bg-[#FF5F57]" />
            <div className="w-3 h-3 rounded-full bg-[#FEBC2E]" />
            <div className="w-3 h-3 rounded-full bg-[#28C840]" />
          </div>
          <div className="flex-1 flex items-center justify-center">
            <Terminal size={14} className="mr-1.5" style={{ color: "var(--text-muted)" }} />
            <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
              reviews — xhunter
            </span>
          </div>
          <div className="w-[54px]" />
        </div>

        {/* Terminal body */}
        <div className="relative px-6 py-8 sm:px-8 sm:py-10 min-h-[180px] flex flex-col items-center justify-center">
          <AnimatePresence mode="wait" custom={direction}>
            <motion.div
              key={current}
              custom={direction}
              initial={{ opacity: 0, x: direction * 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: direction * -20 }}
              transition={{ duration: 0.25, ease: "easeInOut" }}
              className="text-center max-w-xl mx-auto"
            >
              <div className="mb-5">
                <span className="font-mono text-xs" style={{ color: "var(--accent)" }}>
                  $ cat review.txt
                </span>
              </div>

              <p
                className="font-display leading-relaxed mb-5"
                style={{
                  fontSize: "clamp(1rem, 2vw, 1.2rem)",
                  color: "var(--text-primary)",
                  fontWeight: 500,
                }}
              >
                &ldquo;{t?.text}&rdquo;
              </p>

              <p className="font-mono text-xs tracking-wide" style={{ color: "var(--text-muted)" }}>
                — {t?.role}
              </p>
            </motion.div>
          </AnimatePresence>

          {/* Nav arrows */}
          <button
            onClick={prev}
            className="absolute left-2 top-1/2 -translate-y-1/2 w-8 h-8 rounded-lg flex items-center justify-center transition-colors"
            style={{ color: "var(--text-muted)" }}
            aria-label="Предыдущий отзыв"
          >
            <CaretLeft size={16} weight="bold" />
          </button>
          <button
            onClick={next}
            className="absolute right-2 top-1/2 -translate-y-1/2 w-8 h-8 rounded-lg flex items-center justify-center transition-colors"
            style={{ color: "var(--text-muted)" }}
            aria-label="Следующий отзыв"
          >
            <CaretRight size={16} weight="bold" />
          </button>
        </div>
      </div>

      {/* "Оставить отзыв" button */}
      <div className="flex items-center justify-end mt-3">
        <button
          onClick={() => setShowForm(!showForm)}
          className="text-xs font-mono px-3 py-1.5 rounded-lg transition-all"
          style={{
            color: showForm ? "var(--text-primary)" : "var(--accent)",
            background: showForm ? "var(--bg-tertiary)" : "transparent",
            border: `1px solid ${showForm ? "var(--border-color)" : "var(--accent)"}`,
          }}
        >
          {showForm ? "Закрыть" : "Оставить отзыв"}
        </button>
      </div>

      {/* Review form */}
      <AnimatePresence>
        {showForm && (
          <ReviewForm
            onClose={() => setShowForm(false)}
            onSubmit={(newReview) => {
              // Add to carousel immediately
              setReviews((prev) => [newReview, ...prev]);
              setTimeout(() => setShowForm(false), 2000);
            }}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
