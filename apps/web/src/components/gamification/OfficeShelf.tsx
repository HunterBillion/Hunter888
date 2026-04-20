"use client";

/**
 * OfficeShelf — visual meta-progression: items in the manager's "office" that
 * appear as you level up. Tactile classic aesthetic (muted tones, shadows, icons).
 *
 * Self-fetching: loads level, achievements, deals from API automatically.
 */

import { useState, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import type { Icon as PhosphorIcon } from "@phosphor-icons/react";
import {
  IdentificationBadge,
  Notebook,
  Certificate,
  Book,
  Trophy,
  Image as ImageIcon,
  Flag,
  Medal,
  GlobeHemisphereEast,
  Lock,
} from "@phosphor-icons/react";
import { api } from "@/lib/api";

interface OfficeShelfProps {
  level?: number;
  achievementCount?: number;
  totalDeals?: number;
  totalSessions?: number;
  compact?: boolean;
}

interface OfficeItem {
  icon: string;
  label: string;
  unlocksAt: number; // min level
  color: string;
}

const OFFICE_ITEMS: OfficeItem[] = [
  { icon: "badge", label: "Бейдж стажёра", unlocksAt: 1, color: "#8B9DAF" },
  { icon: "notebook", label: "Рабочий блокнот", unlocksAt: 3, color: "#6B7C8F" },
  { icon: "certificate", label: "Первый сертификат", unlocksAt: 6, color: "#C9A96E" },
  { icon: "book", label: "Справочник 127-ФЗ", unlocksAt: 8, color: "#4A6B8A" },
  { icon: "trophy", label: "Кубок достижений", unlocksAt: 11, color: "#D4A843" },
  { icon: "photo", label: "Фото команды", unlocksAt: 13, color: "#7B8F6B" },
  { icon: "nameplate", label: "Золотая табличка", unlocksAt: 16, color: "#C9963E" },
  { icon: "award", label: "Награда за заслуги", unlocksAt: 18, color: "#B8860B" },
  { icon: "globe", label: "Глобус лидера", unlocksAt: 20, color: "#4682B4" },
];

// 2026-04-20: swapped system emojis (🏆🎖🌍…) for Phosphor duotone icons.
// On macOS the Apple color emojis looked out of place in the pixel-art
// theme — user feedback: "странные и не красивые". Phosphor keeps a
// consistent stroke/fill style with the rest of the UI (same library
// used in the hero and AppIcon mapper).
const ICON_MAP: Record<string, PhosphorIcon> = {
  badge: IdentificationBadge,
  notebook: Notebook,
  certificate: Certificate,
  book: Book,
  trophy: Trophy,
  photo: ImageIcon,
  nameplate: Flag,
  award: Medal,
  globe: GlobeHemisphereEast,
};

export default function OfficeShelf({
  level: propLevel,
  achievementCount: propAch,
  totalDeals: propDeals,
  totalSessions: propSessions,
  compact = false,
}: OfficeShelfProps) {
  const [fetchedData, setFetchedData] = useState<{level: number; achievements: number; deals: number; sessions: number} | null>(null);

  useEffect(() => {
    // Self-fetch real data if props are 0 or undefined
    const needsFetch = !propLevel || !propDeals;
    if (!needsFetch) return;
    Promise.all([
      api.get("/gamification/me/progress").catch(() => null),
      api.get("/gamification/portfolio?limit=0").catch(() => null),
    ]).then(([progress, portfolio]) => {
      setFetchedData({
        level: (progress as any)?.level ?? 1,
        achievements: (progress as any)?.achievements?.length ?? 0,
        deals: (portfolio as any)?.total_deals ?? 0,
        sessions: 0,
      });
    });
  }, [propLevel, propDeals]);

  const level = propLevel || fetchedData?.level || 1;
  const achievementCount = propAch || fetchedData?.achievements || 0;
  const totalDeals = propDeals || fetchedData?.deals || 0;
  const totalSessions = propSessions || fetchedData?.sessions || 0;

  const unlockedItems = OFFICE_ITEMS.filter((item) => level >= item.unlocksAt);
  const nextItem = OFFICE_ITEMS.find((item) => level < item.unlocksAt);
  const progress = unlockedItems.length / OFFICE_ITEMS.length;

  if (compact) {
    return (
      <div className="flex items-center gap-1.5 flex-wrap">
        {unlockedItems.map((item, i) => {
          const Icon = ICON_MAP[item.icon];
          return (
            <motion.div
              key={item.icon}
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ delay: i * 0.06, type: "spring", stiffness: 300 }}
              title={item.label}
              className="flex h-7 w-7 items-center justify-center rounded-md"
              style={{
                background: `color-mix(in srgb, ${item.color} 18%, var(--input-bg))`,
                color: item.color,
              }}
            >
              {Icon ? <Icon weight="duotone" size={16} /> : null}
            </motion.div>
          );
        })}
        {nextItem && (
          <div
            className="flex h-7 w-7 items-center justify-center rounded-md opacity-50 border border-dashed"
            style={{ borderColor: "var(--text-muted)", color: "var(--text-muted)" }}
            title={`Разблокируется на уровне ${nextItem.unlocksAt}`}
          >
            <Lock size={12} weight="duotone" />
          </div>
        )}
      </div>
    );
  }

  // Full display (profile page)
  return (
    <div className="rounded-xl bg-[var(--bg-secondary)] p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">
          Кабинет менеджера
        </h3>
        <span className="text-xs text-[var(--text-muted)]">
          {unlockedItems.length}/{OFFICE_ITEMS.length} предметов
        </span>
      </div>

      {/* Progress bar */}
      <div className="h-1.5 rounded-full overflow-hidden mb-4" style={{ background: "var(--input-bg)" }}>
        <motion.div
          className="h-full rounded-full"
          style={{ background: "var(--accent)" }}
          initial={{ width: 0 }}
          animate={{ width: `${progress * 100}%` }}
          transition={{ duration: 0.8, ease: "easeOut" }}
        />
      </div>

      {/* Items grid */}
      <div className="grid grid-cols-3 sm:grid-cols-5 gap-3">
        {OFFICE_ITEMS.map((item, i) => {
          const unlocked = level >= item.unlocksAt;
          const Icon = ICON_MAP[item.icon];
          return (
            <motion.div
              key={item.icon}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.04 }}
              className={`flex flex-col items-center gap-1.5 rounded-lg p-3 transition-all ${
                unlocked ? "" : "opacity-40"
              }`}
              style={{
                background: unlocked
                  ? `color-mix(in srgb, ${item.color} 12%, var(--input-bg))`
                  : "var(--input-bg)",
              }}
            >
              {Icon ? (
                <Icon
                  weight="duotone"
                  size={26}
                  style={{ color: unlocked ? item.color : "var(--text-muted)" }}
                />
              ) : (
                <Lock size={22} style={{ color: "var(--text-muted)" }} />
              )}
              <span className="text-[10px] text-center leading-tight text-[var(--text-secondary)]">
                {item.label}
              </span>
              {!unlocked && (
                <span className="text-[9px] text-[var(--text-muted)]">
                  Ур. {item.unlocksAt}
                </span>
              )}
            </motion.div>
          );
        })}
      </div>

      {/* Stats row */}
      <div className="mt-4 grid grid-cols-3 gap-3">
        {[
          { label: "Сделок", value: totalDeals, color: "var(--success)" },
          { label: "Тренировок", value: totalSessions, color: "var(--accent)" },
          { label: "Достижений", value: achievementCount, color: "var(--warning)" },
        ].map((stat) => (
          <div key={stat.label} className="text-center">
            <span className="text-lg font-bold font-mono" style={{ color: stat.color }}>
              {stat.value}
            </span>
            <p className="text-[10px] text-[var(--text-muted)]">{stat.label}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
