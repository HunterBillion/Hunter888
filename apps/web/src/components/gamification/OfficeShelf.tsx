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
  // 2026-05-08 graphics polish: rounded-xl + bg-secondary заменены
  // на пиксельную рамку с акцентом var(--accent). Шрифты ≥14px.
  return (
    <div
      className="rounded-sm p-5"
      style={{
        background: "rgba(8,5,18,0.55)",
        border: "2px solid rgba(167,139,250,0.28)",
        boxShadow: "inset 0 0 18px rgba(0,0,0,0.4)",
      }}
    >
      <div className="flex items-center justify-between mb-4">
        <h3
          className="font-pixel uppercase tracking-widest"
          style={{ color: "var(--text-primary)", fontSize: 14 }}
        >
          ▰ КАБИНЕТ МЕНЕДЖЕРА ▰
        </h3>
        <span
          className="font-pixel uppercase tracking-widest tabular-nums"
          style={{ color: "var(--text-muted)", fontSize: 14 }}
        >
          {unlockedItems.length}/{OFFICE_ITEMS.length} ПРЕДМЕТОВ
        </span>
      </div>

      {/* Progress bar — пиксельный outline + neon glow */}
      <div
        className="h-3 rounded-sm overflow-hidden mb-5"
        style={{
          background: "rgba(0,0,0,0.45)",
          border: "2px solid rgba(167,139,250,0.4)",
        }}
      >
        <motion.div
          className="h-full"
          style={{
            background: "linear-gradient(90deg, var(--accent), rgba(255,210,80,0.9))",
            boxShadow: "0 0 10px var(--accent-glow)",
          }}
          initial={{ width: 0 }}
          animate={{ width: `${progress * 100}%` }}
          transition={{ duration: 0.8, ease: "easeOut" }}
        />
      </div>

      {/* Items grid — крупнее, square pixel slots */}
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
              whileHover={unlocked ? { scale: 1.04 } : {}}
              className={`flex flex-col items-center gap-2 rounded-sm p-3 transition-all ${
                unlocked ? "" : "opacity-40"
              }`}
              style={{
                background: unlocked
                  ? `color-mix(in srgb, ${item.color} 14%, rgba(0,0,0,0.4))`
                  : "rgba(0,0,0,0.3)",
                border: unlocked
                  ? `2px solid ${item.color}`
                  : "2px dashed rgba(255,255,255,0.18)",
                boxShadow: unlocked
                  ? `0 0 10px color-mix(in srgb, ${item.color} 25%, transparent)`
                  : "none",
              }}
            >
              {Icon ? (
                <Icon
                  weight="duotone"
                  size={32}
                  style={{ color: unlocked ? item.color : "var(--text-muted)" }}
                />
              ) : (
                <Lock size={26} style={{ color: "var(--text-muted)" }} />
              )}
              <span
                className="font-pixel uppercase tracking-widest text-center leading-tight"
                style={{
                  color: "var(--text-secondary)",
                  fontSize: 12,
                  minHeight: "2.4em",
                }}
              >
                {item.label}
              </span>
              {!unlocked && (
                <span
                  className="font-pixel uppercase tracking-widest"
                  style={{ color: "var(--text-muted)", fontSize: 12 }}
                >
                  УР. {item.unlocksAt}
                </span>
              )}
            </motion.div>
          );
        })}
      </div>

      {/* Stats row — крупные тumbler'ы */}
      <div className="mt-5 grid grid-cols-3 gap-3">
        {[
          { label: "СДЕЛОК", value: totalDeals, color: "var(--success, #4ade80)" },
          { label: "ТРЕНИРОВОК", value: totalSessions, color: "var(--accent)" },
          { label: "ДОСТИЖЕНИЙ", value: achievementCount, color: "var(--warning, #facc15)" },
        ].map((stat) => (
          <div
            key={stat.label}
            className="text-center rounded-sm py-2.5"
            style={{
              background: "rgba(0,0,0,0.35)",
              border: `2px solid ${stat.color}55`,
            }}
          >
            <div
              className="font-pixel font-black tabular-nums"
              style={{ color: stat.color, fontSize: 22, lineHeight: 1.0 }}
            >
              {stat.value}
            </div>
            <div
              className="font-pixel uppercase tracking-widest mt-1"
              style={{ color: "var(--text-muted)", fontSize: 12 }}
            >
              {stat.label}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
