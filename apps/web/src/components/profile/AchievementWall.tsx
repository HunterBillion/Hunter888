"use client";

/**
 * 2026-05-08 (графическая полировка): rounded-xl + glass-bg → пиксель.
 *   - Крупные плитки с 3px sharp-corner border
 *   - Большая иконка-медаль слева (44px) в square frame
 *   - Заголовок 16px font-pixel, описание 14px (было 12-13)
 *   - Hover: scale-up + усиленный glow по цвету категории
 *   - Каждая категория — пиксельная плашка-заголовок с counter-чипом
 *   - 2-колоночная сетка на desktop (было 4) — даём дыхание
 */

import { motion } from "framer-motion";
import { Lock } from "lucide-react";
import { Trophy, Sword, BookOpen, Star } from "@phosphor-icons/react";
import type { Achievement } from "@/types";
import { colorAlpha } from "@/lib/utils";

interface AchievementWallProps {
  achievements: Achievement[];
}

interface Category {
  key: string;
  label: string;
  icon: React.ComponentType<Record<string, unknown>>;
  color: string;
  match: (slug: string) => boolean;
}

const CATEGORIES: Category[] = [
  { key: "training", label: "Тренировки", icon: Trophy, color: "var(--accent)", match: (s) => /session|complete|score|train|scenario/.test(s) },
  { key: "pvp", label: "PvP Арена", icon: Sword, color: "var(--warning)", match: (s) => /pvp|duel|arena|rating|rank/.test(s) },
  { key: "knowledge", label: "Знания", icon: BookOpen, color: "var(--success)", match: (s) => /knowledge|quiz|law|legal/.test(s) },
  { key: "special", label: "Особые", icon: Star, color: "var(--magenta)", match: () => true },
];

function categorize(achievements: Achievement[]): Record<string, Achievement[]> {
  const result: Record<string, Achievement[]> = { training: [], pvp: [], knowledge: [], special: [] };
  for (const a of achievements) {
    const slug = a.slug.toLowerCase();
    const cat = CATEGORIES.find((c) => c.key !== "special" && c.match(slug));
    result[cat ? cat.key : "special"].push(a);
  }
  return result;
}

export function AchievementWall({ achievements }: AchievementWallProps) {
  const grouped = categorize(achievements);

  if (achievements.length === 0) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        className="rounded-sm p-10 text-center"
        style={{
          background: "rgba(8,5,18,0.45)",
          border: "2px dashed rgba(255,255,255,0.18)",
        }}
      >
        <Lock size={36} className="mx-auto" style={{ color: "var(--text-muted)", opacity: 0.5 }} />
        <p
          className="mt-4 font-pixel uppercase tracking-widest"
          style={{ color: "var(--text-muted)", fontSize: 14 }}
        >
          Пройдите несколько тренировок чтобы открыть достижения
        </p>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-7"
    >
      {CATEGORIES.map((cat) => {
        const items = grouped[cat.key];
        if (!items || items.length === 0) return null;
        const Icon = cat.icon;

        return (
          <div key={cat.key}>
            {/* Заголовок категории — пиксельная плашка с counter-чипом */}
            <div
              className="inline-flex items-center gap-2 mb-3 px-3 py-1.5 rounded-sm"
              style={{
                background: colorAlpha(cat.color, 12),
                border: `2px solid ${cat.color}`,
                boxShadow: `0 0 10px ${colorAlpha(cat.color, 12)}`,
              }}
            >
              <Icon size={16} weight="duotone" style={{ color: cat.color }} />
              <span
                className="font-pixel uppercase tracking-widest"
                style={{ color: cat.color, fontSize: 14 }}
              >
                {cat.label}
              </span>
              <span
                className="rounded-sm px-2 py-0.5 font-pixel font-bold tabular-nums"
                style={{
                  background: cat.color,
                  color: "#0b0b14",
                  fontSize: 14,
                }}
              >
                {items.length}
              </span>
            </div>

            {/* Сетка медалей — крупная, дыхание (2-3 колонки вместо 4) */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 md:gap-4">
              {items.map((a, i) => (
                <motion.div
                  key={a.id ?? `${cat.key}-${i}`}
                  initial={{ opacity: 0, y: 12, scale: 0.96 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  transition={{ delay: i * 0.04 }}
                  whileHover={{
                    scale: 1.03,
                    boxShadow: `0 0 22px ${colorAlpha(cat.color, 25)}`,
                  }}
                  className="relative overflow-hidden rounded-sm p-4 flex items-start gap-3"
                  style={{
                    background: `linear-gradient(135deg, ${colorAlpha(cat.color, 8)} 0%, rgba(8,5,18,0.65) 100%)`,
                    border: `3px solid ${colorAlpha(cat.color, 35)}`,
                    cursor: "default",
                  }}
                  title={a.description}
                >
                  {/* Square pixel medal slot слева */}
                  <div
                    className="flex items-center justify-center rounded-sm shrink-0"
                    style={{
                      width: 44,
                      height: 44,
                      background: colorAlpha(cat.color, 18),
                      border: `2px solid ${cat.color}`,
                      boxShadow: `0 0 8px ${colorAlpha(cat.color, 25)}`,
                    }}
                  >
                    <Icon size={22} weight="duotone" style={{ color: cat.color }} />
                  </div>

                  {/* Текстовая часть */}
                  <div className="min-w-0 flex-1">
                    <div
                      className="font-pixel font-bold leading-tight"
                      style={{
                        color: "var(--text-primary)",
                        fontSize: 16,
                      }}
                    >
                      {a.title}
                    </div>
                    <p
                      className="mt-1.5 leading-snug"
                      style={{
                        color: "var(--text-muted)",
                        fontSize: 14,
                      }}
                    >
                      {a.description}
                    </p>
                    {a.earned_at && (
                      <div
                        className="font-pixel uppercase tracking-widest mt-2"
                        style={{ color: cat.color, fontSize: 12, opacity: 0.85 }}
                      >
                        ★ {new Date(a.earned_at).toLocaleDateString("ru-RU", { day: "numeric", month: "short", year: "numeric" })}
                      </div>
                    )}
                  </div>
                </motion.div>
              ))}
            </div>
          </div>
        );
      })}
    </motion.div>
  );
}
