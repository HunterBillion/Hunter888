"use client";

/**
 * HonestNavigator — единая точка входа на /pvp.
 *
 * Заменяет PreCallWarmUpHero (4 фейк-кнопки → одна дуэль) + tab-Дуэли +
 * tab-Знания ФЗ-127 + 3 mode-card + 2 personality-card + 10 категорий —
 * всё это сливается в ОДИН блок с 4-мя реально разными режимами:
 *
 *   1. Дуэль с ботом    → handleFindMatch() (PvE-fallback в <15s)
 *   2. Квиз ФЗ-127      → POST /knowledge/sessions {mode:"free_dialog"}
 *   3. Блиц 20×60       → POST /knowledge/sessions {mode:"blitz"}
 *   4. По теме          → POST /knowledge/sessions {mode:"themed",category}
 *
 * AI-personality зашита `professor` — `detective` отличался только
 * стилем формулировок hints; разница не считывается, оставляем один
 * стиль для пилота.
 *
 * При выборе "По теме" раскрывается chip-row из 10 категорий ФЗ-127;
 * START активна только когда категория выбрана.
 */

import * as React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Loader2 } from "lucide-react";
import { PixelIcon, type PixelIconName } from "./PixelIcon";

export type NavigatorMode = "duel" | "free_dialog" | "blitz" | "themed";

interface Props {
  disabled?: boolean;
  starting?: boolean;
  onDuel: () => void;
  onQuiz: (mode: "free_dialog" | "blitz" | "themed", category?: string) => void;
}

type Card = {
  mode: NavigatorMode;
  icon: PixelIconName;
  title: string;
  hint: string;
  accent: string;
};

const CARDS: Card[] = [
  {
    mode: "duel",
    icon: "sword",
    title: "Дуэль с ботом",
    hint: "10 мин · диалог · разбор от AI",
    accent: "var(--accent)",
  },
  {
    mode: "free_dialog",
    icon: "book",
    title: "Квиз ФЗ-127",
    hint: "10 вопросов · без таймера",
    accent: "var(--success, #22c55e)",
  },
  {
    mode: "blitz",
    icon: "bolt",
    title: "Блиц 20×60",
    hint: "Скорость · рандом по 10 темам",
    accent: "var(--gf-xp, #facc15)",
  },
  {
    mode: "themed",
    icon: "target",
    title: "По теме",
    hint: "Выбери 1 категорию · 15 вопросов",
    accent: "var(--magenta, #d946ef)",
  },
];

const CATEGORIES: Array<{ id: string; label: string; icon: PixelIconName }> = [
  { id: "eligibility", label: "Условия подачи", icon: "book" },
  { id: "procedure", label: "Порядок процедуры", icon: "ladder" },
  { id: "property", label: "Имущество", icon: "castle" },
  { id: "consequences", label: "Последствия", icon: "skull" },
  { id: "costs", label: "Расходы", icon: "target" },
  { id: "creditors", label: "Кредиторы", icon: "group" },
  { id: "documents", label: "Документы", icon: "book" },
  { id: "timeline", label: "Сроки", icon: "bolt" },
  { id: "court", label: "Суд", icon: "castle" },
  { id: "rights", label: "Права должника", icon: "shield" },
];

export function HonestNavigator({ disabled, starting, onDuel, onQuiz }: Props) {
  const [picked, setPicked] = React.useState<NavigatorMode | null>(null);
  const [category, setCategory] = React.useState<string | null>(null);

  const isBusy = !!disabled || !!starting;

  const handleCard = (m: NavigatorMode) => {
    if (isBusy) return;
    if (m === "duel") {
      onDuel();
      return;
    }
    if (m === "free_dialog" || m === "blitz") {
      onQuiz(m);
      return;
    }
    // themed → reveal category row
    setPicked(m);
  };

  const handleStart = () => {
    if (isBusy) return;
    if (picked === "themed" && category) {
      onQuiz("themed", category);
    }
  };

  return (
    <div
      className="p-4 sm:p-5"
      style={{
        background: "var(--bg-panel)",
        outline: "2px solid var(--accent)",
        outlineOffset: -2,
        boxShadow: "4px 4px 0 0 var(--accent)",
        borderRadius: 0,
      }}
    >
      <h2
        className="font-pixel uppercase tracking-widest pixel-glow mb-3"
        style={{
          color: "var(--text-primary)",
          fontSize: "clamp(15px, 2.4vw, 18px)",
          lineHeight: 1.2,
        }}
      >
        ▸ Что делаем сейчас?
      </h2>

      <div className="grid grid-cols-2 gap-2 sm:gap-3">
        {CARDS.map((c) => {
          const active = picked === c.mode;
          return (
            <motion.button
              key={c.mode}
              type="button"
              onClick={() => handleCard(c.mode)}
              disabled={isBusy}
              whileHover={!isBusy ? { x: -1, y: -1 } : undefined}
              whileTap={!isBusy ? { x: 2, y: 2 } : undefined}
              className="flex flex-col items-start gap-1.5 p-3 text-left transition-opacity"
              style={{
                background: active
                  ? `color-mix(in srgb, ${c.accent} 14%, var(--bg-secondary, rgba(0,0,0,0.4)))`
                  : "var(--bg-secondary, rgba(0,0,0,0.4))",
                outline: `2px solid ${c.accent}`,
                outlineOffset: -2,
                borderRadius: 0,
                boxShadow: `2px 2px 0 0 ${c.accent}`,
                opacity: isBusy ? 0.5 : 1,
                cursor: isBusy ? "not-allowed" : "pointer",
                minHeight: 92,
              }}
            >
              <PixelIcon name={c.icon} size={18} color={c.accent} />
              <span
                className="font-pixel uppercase"
                style={{
                  color: c.accent,
                  fontSize: 12,
                  letterSpacing: "0.1em",
                  lineHeight: 1.15,
                }}
              >
                {c.title}
              </span>
              <span
                className="font-pixel"
                style={{
                  color: "var(--text-muted)",
                  fontSize: 9,
                  letterSpacing: "0.06em",
                  lineHeight: 1.2,
                }}
              >
                {c.hint}
              </span>
            </motion.button>
          );
        })}
      </div>

      <AnimatePresence mode="wait">
        {picked === "themed" && (
          <motion.div
            key="cat-row"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.18 }}
            className="overflow-hidden"
          >
            <div className="mt-3 pt-3 border-t border-dashed" style={{ borderColor: "var(--border-color)" }}>
              <div
                className="font-pixel uppercase mb-2"
                style={{ color: "var(--text-muted)", fontSize: 10, letterSpacing: "0.14em" }}
              >
                Выбери тему
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                {CATEGORIES.map((cat) => {
                  const active = category === cat.id;
                  return (
                    <motion.button
                      key={cat.id}
                      type="button"
                      onClick={() => setCategory(cat.id)}
                      disabled={isBusy}
                      whileHover={!isBusy && !active ? { x: -1, y: -1 } : undefined}
                      whileTap={!isBusy ? { x: 2, y: 2 } : undefined}
                      className="flex items-center gap-2 px-2.5 py-2"
                      style={{
                        background: active
                          ? "color-mix(in srgb, var(--success) 14%, var(--bg-panel))"
                          : "var(--bg-panel)",
                        outline: `2px solid ${active ? "var(--success)" : "var(--border-color)"}`,
                        outlineOffset: -2,
                        borderRadius: 0,
                        boxShadow: active ? "2px 2px 0 0 var(--success)" : "1px 1px 0 0 var(--border-color)",
                        cursor: isBusy ? "not-allowed" : "pointer",
                      }}
                    >
                      <PixelIcon name={cat.icon} size={14} color={active ? "var(--success)" : "var(--text-muted)"} />
                      <span
                        className="font-pixel uppercase"
                        style={{
                          color: active ? "var(--success)" : "var(--text-primary)",
                          fontSize: 10,
                          letterSpacing: "0.08em",
                          lineHeight: 1.1,
                        }}
                      >
                        {cat.label}
                      </span>
                    </motion.button>
                  );
                })}
              </div>

              <motion.button
                type="button"
                onClick={handleStart}
                disabled={isBusy || !category}
                whileHover={!isBusy && category ? { x: -1, y: -1 } : undefined}
                whileTap={!isBusy && category ? { x: 2, y: 2 } : undefined}
                className="mt-3 w-full flex items-center justify-center gap-2 py-3 font-pixel uppercase"
                style={{
                  background: category ? "var(--accent)" : "var(--bg-secondary, rgba(0,0,0,0.4))",
                  color: category ? "#fff" : "var(--text-muted)",
                  outline: `2px solid ${category ? "var(--accent)" : "var(--border-color)"}`,
                  outlineOffset: -2,
                  borderRadius: 0,
                  boxShadow: category ? "3px 3px 0 0 #000, 0 0 12px var(--accent-glow)" : "1px 1px 0 0 var(--border-color)",
                  fontSize: 13,
                  letterSpacing: "0.16em",
                  cursor: !isBusy && category ? "pointer" : "not-allowed",
                  opacity: isBusy ? 0.6 : 1,
                }}
              >
                {starting ? <Loader2 size={16} className="animate-spin" /> : "▶ Начать"}
              </motion.button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
