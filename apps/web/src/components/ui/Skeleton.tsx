"use client";

import { motion } from "framer-motion";

interface SkeletonProps {
  className?: string;
  width?: string | number;
  height?: string | number;
  rounded?: string;
}

export function Skeleton({ className = "", width, height, rounded = "8px" }: SkeletonProps) {
  return (
    <motion.div
      className={`relative overflow-hidden ${className}`}
      style={{
        width,
        height,
        borderRadius: rounded,
        background: "var(--input-bg)",
      }}
      animate={{ opacity: [0.4, 0.7, 0.4] }}
      transition={{ duration: 1.5, repeat: Infinity, ease: "easeInOut" }}
    >
      <motion.div
        className="absolute inset-0"
        style={{
          background: "linear-gradient(90deg, transparent 0%, var(--accent-muted) 50%, transparent 100%)",
        }}
        animate={{ x: ["-100%", "100%"] }}
        transition={{ duration: 1.8, repeat: Infinity, ease: "easeInOut" }}
      />
    </motion.div>
  );
}

// Pre-built skeleton layouts
export function CardSkeleton() {
  return (
    <div className="glass-panel p-5 space-y-3">
      <Skeleton height={14} width="40%" />
      <Skeleton height={28} width="60%" />
      <Skeleton height={10} width="80%" />
    </div>
  );
}

export function ListItemSkeleton() {
  return (
    <div className="glass-panel p-5 flex items-center gap-4">
      <Skeleton width={40} height={40} rounded="12px" />
      <div className="flex-1 space-y-2">
        <Skeleton height={12} width="50%" />
        <Skeleton height={10} width="70%" />
      </div>
      <Skeleton width={40} height={24} rounded="4px" />
    </div>
  );
}

export function PageSkeleton() {
  return (
    <div className="mx-auto max-w-5xl px-4 py-8 space-y-6">
      <div className="space-y-2">
        <Skeleton height={28} width="30%" />
        <Skeleton height={12} width="50%" />
      </div>
      <Skeleton height={12} width="100%" rounded="999px" />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map(i => <CardSkeleton key={i} />)}
      </div>
      <div className="space-y-3">
        {[1, 2, 3].map(i => <ListItemSkeleton key={i} />)}
      </div>
    </div>
  );
}

/** Dashboard page skeleton — 4 stat cards + team list */
export function DashboardSkeleton() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-8 space-y-6">
      <Skeleton height={24} width="25%" />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map(i => <CardSkeleton key={i} />)}
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="glass-panel p-5 space-y-3">
          <Skeleton height={16} width="40%" />
          {[1, 2, 3, 4].map(i => <ListItemSkeleton key={i} />)}
        </div>
        <div className="glass-panel p-5 space-y-3">
          <Skeleton height={16} width="40%" />
          <Skeleton height={200} width="100%" rounded="12px" />
        </div>
      </div>
    </div>
  );
}

/** Client list skeleton — filters + card grid */
export function ClientListSkeleton() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-8 space-y-6">
      <div className="flex items-center justify-between">
        <Skeleton height={24} width="20%" />
        <Skeleton height={36} width={120} rounded="12px" />
      </div>
      <div className="flex gap-3">
        <Skeleton height={36} width={200} rounded="12px" />
        <Skeleton height={36} width={150} rounded="12px" />
        <Skeleton height={36} width={100} rounded="12px" />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {[1, 2, 3, 4, 5, 6].map(i => <CardSkeleton key={i} />)}
      </div>
    </div>
  );
}

/** Analytics page skeleton — charts + metrics */
export function AnalyticsSkeleton() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-8 space-y-6">
      <Skeleton height={24} width="30%" />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map(i => <CardSkeleton key={i} />)}
      </div>
      <Skeleton height={300} width="100%" rounded="12px" />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Skeleton height={200} width="100%" rounded="12px" />
        <Skeleton height={200} width="100%" rounded="12px" />
      </div>
    </div>
  );
}

/** Leaderboard skeleton — podium + list */
export function LeaderboardSkeleton() {
  return (
    <div className="mt-6 space-y-4">
      <div className="flex items-end justify-center gap-4 py-8">
        <Skeleton width={60} height={80} rounded="12px" />
        <Skeleton width={70} height={100} rounded="12px" />
        <Skeleton width={60} height={70} rounded="12px" />
      </div>
      {[1, 2, 3, 4, 5].map(i => <ListItemSkeleton key={i} />)}
    </div>
  );
}

// Static widths for chat bubbles — Math.random() causes server/client hydration mismatch.
const _CHAT_BUBBLE_WIDTHS = ["42%", "67%", "53%", "71%"];

/** Training session skeleton — 3-column layout with chat, controls, metrics */
export function TrainingSessionSkeleton() {
  return (
    <div className="h-screen flex flex-col" style={{ background: "var(--bg-primary)" }}>
      {/* Top bar */}
      <div className="flex items-center justify-between px-4 py-3 border-b" style={{ borderColor: "var(--border-color)" }}>
        <div className="flex items-center gap-3">
          <Skeleton width={32} height={32} rounded="50%" />
          <Skeleton height={14} width={140} />
        </div>
        <div className="flex gap-2">
          <Skeleton width={80} height={28} rounded="8px" />
          <Skeleton width={80} height={28} rounded="8px" />
        </div>
      </div>
      {/* 3-column body */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-3 gap-0">
        {/* Left — whisper panel */}
        <div className="p-4 space-y-3 border-r" style={{ borderColor: "var(--border-color)" }}>
          <Skeleton height={16} width="50%" />
          {[1, 2, 3].map(i => (
            <div key={i} className="glass-panel p-3 space-y-2">
              <Skeleton height={10} width="80%" />
              <Skeleton height={10} width="60%" />
            </div>
          ))}
        </div>
        {/* Center — chat + mic */}
        <div className="flex flex-col items-center justify-between p-4">
          <div className="w-full space-y-3 flex-1">
            {[0, 1, 2, 3].map(i => (
              <div key={i} className={`flex ${i % 2 === 1 ? "justify-end" : "justify-start"}`}>
                <Skeleton width={_CHAT_BUBBLE_WIDTHS[i]} height={48} rounded="16px" />
              </div>
            ))}
          </div>
          <Skeleton width={72} height={72} rounded="50%" />
        </div>
        {/* Right — scores */}
        <div className="p-4 space-y-3 border-l" style={{ borderColor: "var(--border-color)" }}>
          <Skeleton height={16} width="40%" />
          <Skeleton height={120} width="100%" rounded="12px" />
          <Skeleton height={16} width="60%" />
          <div className="space-y-2">
            {[1, 2, 3, 4].map(i => (
              <div key={i} className="flex items-center gap-2">
                <Skeleton width={14} height={14} rounded="4px" />
                <Skeleton height={10} width="50%" />
                <Skeleton height={10} width={40} />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

/** Arena/Quiz skeleton — question + answers */
export function ArenaQuizSkeleton() {
  return (
    <div className="mx-auto max-w-2xl px-4 py-8 space-y-8">
      {/* Header with timer */}
      <div className="flex items-center justify-between">
        <Skeleton height={20} width="30%" />
        <Skeleton width={60} height={60} rounded="50%" />
      </div>
      {/* Question */}
      <div className="glass-panel p-6 space-y-3">
        <Skeleton height={16} width="90%" />
        <Skeleton height={16} width="70%" />
      </div>
      {/* Answers */}
      <div className="space-y-3">
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="glass-panel p-4 flex items-center gap-3">
            <Skeleton width={28} height={28} rounded="8px" />
            <Skeleton height={12} width={`${50 + i * 8}%`} />
          </div>
        ))}
      </div>
      {/* Scoreboard */}
      <div className="flex justify-center gap-4">
        <Skeleton width={80} height={40} rounded="12px" />
        <Skeleton width={40} height={40} rounded="50%" />
        <Skeleton width={80} height={40} rounded="12px" />
      </div>
    </div>
  );
}

/** Results page skeleton — score + charts + recommendations */
export function ResultsSkeleton() {
  return (
    <div className="mx-auto max-w-4xl px-4 py-8 space-y-6">
      {/* Verdict card */}
      <div className="glass-panel p-6 text-center space-y-3">
        <Skeleton width={80} height={80} rounded="50%" className="mx-auto" />
        <Skeleton height={24} width="40%" className="mx-auto" />
        <Skeleton height={12} width="60%" className="mx-auto" />
      </div>
      {/* Charts row */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="glass-panel p-5 space-y-3">
          <Skeleton height={16} width="50%" />
          <Skeleton height={200} width="100%" rounded="12px" />
        </div>
        <div className="glass-panel p-5 space-y-3">
          <Skeleton height={16} width="40%" />
          <Skeleton height={200} width="100%" rounded="12px" />
        </div>
      </div>
      {/* Recommendations */}
      <div className="glass-panel p-5 space-y-3">
        <Skeleton height={16} width="35%" />
        {[1, 2, 3].map(i => (
          <div key={i} className="flex items-start gap-3">
            <Skeleton width={24} height={24} rounded="6px" />
            <div className="flex-1 space-y-1">
              <Skeleton height={12} width="70%" />
              <Skeleton height={10} width="90%" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── Loading Tips — rotating micro-copy for skeleton states ─────────── */

const LOADING_TIPS = [
  "Топ-перформеры тренируются 3+ раза в неделю",
  "Нажмите Cmd+K для быстрого поиска по платформе",
  "Серия 7 дней — и вы получите ачивку!",
  "Попробуйте арену — PvP прокачивает навыки быстрее",
  "Сценарий «Скептик» — любимый челлендж наших юристов",
  "Результаты видны уже после 5 тренировок",
  "Лидерборд обновляется в реальном времени",
  "Ваша серия сохраняется при ежедневных сессиях",
  "Горячая клавиша ? покажет все шорткаты",
  "Тёмная тема снижает нагрузку на глаза вечером",
  "Рекомендации подбираются по вашему уровню",
  "Турниры проходят каждую неделю — не пропустите!",
  "Чем сложнее сценарий, тем больше XP",
  "Средний балл > 80 — признак мастера переговоров",
  "Навигатор обновляет цитату каждые 6 часов",
  "Первая сессия — самая важная. Начните сегодня.",
  "Архетип «Скептик» раскрывает навыки работы с возражениями",
  "Средний рост балла после 10 сессий — +18%",
  "Конструктор клиентов позволяет создать любой сценарий",
  "Анализируйте историю — каждая тренировка учит",
  "Командный рейтинг обновляется каждый понедельник",
  "Режим «История» создаёт многодневные сюжеты",
  "Чем выше сложность, тем больше XP за победу",
  "Навыки переговоров растут с практикой, не с теорией",
  "Арена PvP — лучший способ проверить себя",
];

/**
 * Shows a rotating tip below skeleton loaders.
 * Picks a stable tip based on the current minute so it doesn't flicker on re-render.
 */
export function LoadingTip() {
  const idx = Math.floor(Date.now() / 60_000) % LOADING_TIPS.length;
  return (
    <motion.p
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ delay: 0.5 }}
      className="mt-4 text-center font-mono text-xs uppercase tracking-wider"
      style={{ color: "var(--text-muted)", opacity: 0.6 }}
    >
      {LOADING_TIPS[idx]}
    </motion.p>
  );
}
