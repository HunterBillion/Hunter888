"use client";

import { motion } from "framer-motion";
import { Trophy, Swords, BookOpen, Star, Lock } from "lucide-react";
import type { Achievement } from "@/types";
import { colorAlpha } from "@/lib/utils";

interface AchievementWallProps {
  achievements: Achievement[];
}

interface Category {
  key: string;
  label: string;
  icon: typeof Trophy;
  color: string;
  match: (slug: string) => boolean;
}

const CATEGORIES: Category[] = [
  { key: "training", label: "Тренировки", icon: Trophy, color: "var(--accent)", match: (s) => /session|complete|score|train|scenario/.test(s) },
  { key: "pvp", label: "PvP Арена", icon: Swords, color: "var(--warning)", match: (s) => /pvp|duel|arena|rating|rank/.test(s) },
  { key: "knowledge", label: "Знания", icon: BookOpen, color: "var(--neon-green)", match: (s) => /knowledge|quiz|law|legal/.test(s) },
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
        className="glass-panel p-8 text-center"
      >
        <Lock size={32} className="mx-auto animate-float-subtle" style={{ color: "var(--text-muted)", opacity: 0.4 }} />
        <p className="mt-3 text-sm" style={{ color: "var(--text-muted)" }}>
          Пройдите несколько тренировок чтобы открыть достижения
        </p>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-6"
    >
      {CATEGORIES.map((cat) => {
        const items = grouped[cat.key];
        if (!items || items.length === 0) return null;
        const Icon = cat.icon;

        return (
          <div key={cat.key}>
            <div className="flex items-center gap-2 mb-3">
              <Icon size={16} style={{ color: cat.color }} />
              <span className="font-display text-sm font-bold tracking-widest uppercase" style={{ color: "var(--text-secondary)" }}>
                {cat.label}
              </span>
              <span
                className="rounded-full px-2 py-0.5 text-xs font-mono font-bold"
                style={{ background: colorAlpha(cat.color, 9), color: cat.color }}
              >
                {items.length}
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
              {items.map((a, i) => (
                <motion.div
                  key={a.id}
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ delay: i * 0.04 }}
                  className="relative overflow-hidden rounded-xl p-4"
                  style={{
                    background: "var(--glass-bg)",
                    border: `1px solid ${colorAlpha(cat.color, 12)}`,
                    backdropFilter: "blur(16px)",
                  }}
                  whileHover={{ borderColor: colorAlpha(cat.color, 25), boxShadow: `0 4px 20px ${colorAlpha(cat.color, 8)}` }}
                >
                  <div className="absolute left-0 top-0 bottom-0 w-[3px]" style={{ background: cat.color }} />
                  <div className="absolute -top-6 -right-6 w-16 h-16 rounded-full pointer-events-none" style={{ background: `radial-gradient(circle, ${colorAlpha(cat.color, 6)} 0%, transparent 70%)` }} />
                  <div className="font-display text-sm font-bold" style={{ color: "var(--text-primary)" }}>
                    {a.title}
                  </div>
                  <p className="text-xs mt-1.5 leading-relaxed" style={{ color: "var(--text-muted)" }}>
                    {a.description}
                  </p>
                  {a.earned_at && (
                    <div className="font-mono text-xs mt-2.5 flex items-center gap-1" style={{ color: cat.color, opacity: 0.7 }}>
                      {new Date(a.earned_at).toLocaleDateString("ru-RU", { day: "numeric", month: "short", year: "numeric" })}
                    </div>
                  )}
                </motion.div>
              ))}
            </div>
          </div>
        );
      })}
    </motion.div>
  );
}
