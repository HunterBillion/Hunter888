"use client";

/**
 * DuelRulesCarousel — компактная карусель правил дуэли в стиле
 * Clash Royale loading screen.
 *
 * 2026-05-10: заменяет полноэкранную «★ Правила дуэли ★» панель,
 * которая раньше показывалась в loading state на /pvp/duel/[id].
 * Пользователь обозначил её как «не понятный артефакт» — слишком
 * много текста при подключении к арене, нечитабельно.
 *
 * Поведение:
 *   - 4 коротких правила (топ-4 — структура, лимит, оценка, рейтинг).
 *     Полные 8 правил перенесены в /wiki — там можно изучить детально.
 *   - Auto-rotate каждые 5 секунд, плавный crossfade.
 *   - Прогресс-точки внизу (◇◇◇◇) — кликабельные, можно прыгнуть.
 *   - Стрелки ←→ для ручной навигации.
 *   - Pause при ховере — даём дочитать.
 *   - Прогресс-бар поверх плашки показывает таймер до следующего
 *     правила (4 секунды визуального feedback).
 *
 * Геометрия:
 *   - max-width 480 px (компактнее старой панели 768 px)
 *   - высота ~180 px (фиксированная, без layout shift)
 *   - пиксельная рамка 2px solid accent + glow
 *   - шрифты ≥ 14 px (font-pixel uppercase для лейблов)
 */

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronLeft, ChevronRight, Sparkles } from "lucide-react";

interface Rule {
  num: number;
  color: string;
  emoji: string;
  lead: string;
  body: string;
}

const RULES: Rule[] = [
  {
    num: 1,
    color: "var(--accent)",
    emoji: "⚔️",
    lead: "2 раунда + смена ролей",
    body: "Сначала ты — менеджер, потом — клиент. Учишься обеим сторонам разговора.",
  },
  {
    num: 2,
    color: "var(--magenta, #d946ef)",
    emoji: "💬",
    lead: "До 8 сообщений на раунд",
    body: "Будь лаконичным. Длинные простыни режутся — как в реальном звонке.",
  },
  {
    num: 3,
    color: "var(--success, #22c55e)",
    emoji: "⚖️",
    lead: "AI-судья · 4 критерия",
    body: "Возражения · Убеждение · Структура · Юридическая точность по 127-ФЗ.",
  },
  {
    num: 4,
    color: "var(--gf-xp, #facc15)",
    emoji: "📈",
    lead: "Glicko-2 рейтинг",
    body: "PvP — полные очки. PvE-бот даёт 50%. Первые 10 дуэлей — калибровочные.",
  },
];

const AUTO_ROTATE_MS = 5000;

interface Props {
  /** Опциональная подпись над каруселью. */
  caption?: string;
}

export function DuelRulesCarousel({ caption = "Готовься к арене" }: Props) {
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const [progress, setProgress] = useState(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Auto-rotate с прогресс-баром
  useEffect(() => {
    if (paused) return;
    setProgress(0);
    const startTime = Date.now();
    const tick = () => {
      const elapsed = Date.now() - startTime;
      const pct = Math.min(100, (elapsed / AUTO_ROTATE_MS) * 100);
      setProgress(pct);
      if (pct >= 100) {
        setIndex((i) => (i + 1) % RULES.length);
      }
    };
    intervalRef.current = setInterval(tick, 50);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [index, paused]);

  const goPrev = () => setIndex((i) => (i - 1 + RULES.length) % RULES.length);
  const goNext = () => setIndex((i) => (i + 1) % RULES.length);

  const rule = RULES[index];

  return (
    <div
      className="relative max-w-[480px] w-full mx-auto"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
    >
      {/* Caption над плашкой */}
      <div
        className="text-center font-pixel uppercase tracking-widest mb-2"
        style={{ color: "var(--text-muted)", fontSize: 14, letterSpacing: "0.18em" }}
      >
        <Sparkles size={14} className="inline mr-1.5 -mt-0.5" />
        {caption}
        <Sparkles size={14} className="inline ml-1.5 -mt-0.5" />
      </div>

      {/* Плашка с правилом */}
      <div
        className="relative rounded-sm overflow-hidden"
        style={{
          minHeight: 180,
          background: `linear-gradient(135deg, color-mix(in srgb, ${rule.color} 8%, rgba(8,5,18,0.92)) 0%, rgba(8,5,18,0.95) 100%)`,
          border: `2px solid ${rule.color}`,
          boxShadow: `0 0 22px color-mix(in srgb, ${rule.color} 30%, transparent), inset 0 0 16px rgba(0,0,0,0.4)`,
        }}
      >
        {/* Прогресс-бар сверху */}
        <div
          aria-hidden
          className="absolute top-0 left-0 right-0"
          style={{ height: 3, background: "rgba(0,0,0,0.4)" }}
        >
          <div
            style={{
              width: `${progress}%`,
              height: "100%",
              background: rule.color,
              transition: paused ? "none" : "width 50ms linear",
              boxShadow: `0 0 8px ${rule.color}`,
            }}
          />
        </div>

        {/* Контент правила с crossfade */}
        <AnimatePresence mode="wait">
          <motion.div
            key={rule.num}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.3, ease: "easeOut" }}
            className="px-5 pt-6 pb-4 flex items-start gap-4"
          >
            {/* Square pixel-«медаль» с emoji + номером */}
            <div
              className="flex flex-col items-center justify-center rounded-sm shrink-0"
              style={{
                width: 56,
                height: 56,
                background: `color-mix(in srgb, ${rule.color} 20%, rgba(0,0,0,0.4))`,
                border: `2px solid ${rule.color}`,
                boxShadow: `0 0 10px color-mix(in srgb, ${rule.color} 40%, transparent)`,
              }}
            >
              <div style={{ fontSize: 26, lineHeight: 1 }}>{rule.emoji}</div>
              <div
                className="font-pixel uppercase tracking-widest tabular-nums"
                style={{ color: rule.color, fontSize: 14, marginTop: 2 }}
              >
                {rule.num}/{RULES.length}
              </div>
            </div>

            {/* Текст правила */}
            <div className="flex-1 min-w-0">
              <div
                className="font-pixel uppercase tracking-widest mb-2"
                style={{
                  color: rule.color,
                  fontSize: 16,
                  lineHeight: 1.2,
                  textShadow: `0 0 8px color-mix(in srgb, ${rule.color} 60%, transparent)`,
                }}
              >
                {rule.lead}
              </div>
              <div
                style={{
                  color: "var(--text-secondary)",
                  fontSize: 14,
                  lineHeight: 1.5,
                }}
              >
                {rule.body}
              </div>
            </div>
          </motion.div>
        </AnimatePresence>

        {/* Стрелки ручной навигации */}
        <button
          type="button"
          onClick={goPrev}
          aria-label="Предыдущее правило"
          className="absolute left-1 bottom-1 rounded-sm transition-colors"
          style={{
            width: 28,
            height: 28,
            background: "rgba(0,0,0,0.5)",
            border: "1px solid rgba(255,255,255,0.18)",
            color: "var(--text-secondary)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <ChevronLeft size={16} />
        </button>
        <button
          type="button"
          onClick={goNext}
          aria-label="Следующее правило"
          className="absolute right-1 bottom-1 rounded-sm transition-colors"
          style={{
            width: 28,
            height: 28,
            background: "rgba(0,0,0,0.5)",
            border: "1px solid rgba(255,255,255,0.18)",
            color: "var(--text-secondary)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <ChevronRight size={16} />
        </button>
      </div>

      {/* Прогресс-точки */}
      <div className="flex items-center justify-center gap-2 mt-3">
        {RULES.map((r, i) => (
          <button
            key={r.num}
            type="button"
            onClick={() => setIndex(i)}
            aria-label={`Перейти к правилу ${i + 1}`}
            className="rounded-sm transition-all"
            style={{
              width: i === index ? 24 : 10,
              height: 10,
              background: i === index ? r.color : "rgba(255,255,255,0.18)",
              border: i === index ? `1px solid ${r.color}` : "1px solid transparent",
              boxShadow: i === index ? `0 0 8px ${r.color}` : "none",
            }}
          />
        ))}
      </div>
    </div>
  );
}
