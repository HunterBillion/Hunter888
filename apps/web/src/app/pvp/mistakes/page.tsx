"use client";

/**
 * /pvp/mistakes — "Работа над ошибками" (Mistake Book).
 *
 * Phase B→C (2026-04-20). Moved from /training/review into the Arena
 * panel per user feedback: Mistake Book is discovered after playing
 * quizzes, so it belongs next to /pvp/league and /pvp/teams rather than
 * in the top-level navigation.
 *
 * Surfaces the SM-2 + Leitner SRS queue that already exists on the
 * backend (`services/spaced_repetition.py`).
 *
 * APIs used:
 *   GET /knowledge/srs/stats          — header KPIs + review_queue_preview
 *   GET /knowledge/srs/review-queue   — paginated priority queue
 *   GET /knowledge/srs/mastery        — per-category breakdown
 */

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  AlertTriangle,
  BookOpen,
  Clock,
  Flame,
  Gauge,
  Loader2,
  ArrowLeft,
  TrendingDown,
  Sparkles,
  CheckCircle2,
} from "lucide-react";
import AuthLayout from "@/components/layout/AuthLayout";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";

interface QueueItem {
  question_text: string;
  question_category: string;
  question_hash: string;
  priority: "overdue" | "weak" | "learning";
  ease_factor: number;
  interval_days: number;
  leitner_box: number;
  current_streak: number;
  total_reviews: number;
}

interface StatsResponse {
  total_reviews: number;
  overdue_count: number;
  weak_count: number;
  avg_ease_factor: number;
  mastered_count: number;
  learning_count: number;
  review_queue_preview: QueueItem[];
}

interface MasteryCategory {
  category: string;
  items_total: number;
  mastered: number;
  weak: number;
  accuracy?: number;
  avg_ease_factor?: number;
}

interface QueueResponse {
  items: QueueItem[];
  total: number;
}

type IconComp = React.ComponentType<{ size?: number; style?: React.CSSProperties }>;

const PRIORITY_META: Record<
  QueueItem["priority"],
  { label: string; color: string; icon: IconComp; bg: string }
> = {
  overdue: {
    label: "Просрочено",
    color: "#f87171",
    icon: AlertTriangle,
    bg: "rgba(248,113,113,0.12)",
  },
  weak: {
    label: "Слабое",
    color: "#facc15",
    icon: TrendingDown,
    bg: "rgba(250,204,21,0.12)",
  },
  learning: {
    label: "Учится",
    color: "#22d3ee",
    icon: Sparkles,
    bg: "rgba(34,211,238,0.12)",
  },
};

const CATEGORY_LABEL: Record<string, string> = {
  eligibility: "Условия банкротства",
  procedure: "Порядок процедуры",
  property: "Имущество",
  consequences: "Последствия",
  costs: "Стоимость",
  creditors: "Кредиторы",
  documents: "Документы",
  timeline: "Сроки",
  court: "Суд",
  rights: "Права должника",
};

function LeitnerBox({ box }: { box: number }) {
  const filled = Math.max(0, Math.min(4, box));
  return (
    <div className="flex gap-0.5" aria-label={`Leitner ${filled}/4`}>
      {[0, 1, 2, 3, 4].map((i) => (
        <span
          key={i}
          className="block h-1.5 w-2.5 rounded-[1px]"
          style={{
            background:
              i <= filled
                ? i === 4
                  ? "#4ade80"
                  : "#a78bfa"
                : "rgba(255,255,255,0.12)",
          }}
        />
      ))}
    </div>
  );
}

export default function ReviewPage() {
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [mastery, setMastery] = useState<MasteryCategory[]>([]);
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [category, setCategory] = useState<string | null>(null);

  const load = useCallback(async (cat: string | null) => {
    setLoading(true);
    try {
      const [statsResp, masteryResp, queueResp] = await Promise.all([
        api.get<StatsResponse>("/knowledge/srs/stats"),
        api.get<{ categories: MasteryCategory[] }>("/knowledge/srs/mastery").catch(
          () => ({ categories: [] as MasteryCategory[] }),
        ),
        api.get<QueueResponse>(
          cat
            ? `/knowledge/srs/review-queue?limit=30&category=${encodeURIComponent(cat)}`
            : "/knowledge/srs/review-queue?limit=30",
        ),
      ]);
      setStats(statsResp);
      setMastery(masteryResp.categories ?? []);
      setQueue(queueResp.items ?? []);
    } catch (e) {
      logger.error("review/srs load failed", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(category);
  }, [category, load]);

  const backfill = useCallback(async () => {
    try {
      await api.post("/knowledge/srs/backfill", {});
      await load(category);
    } catch (e) {
      logger.warn("backfill failed", e);
    }
  }, [category, load]);

  const accentByPriority = useMemo(() => {
    if (!stats) return "#a78bfa";
    if (stats.overdue_count > 0) return PRIORITY_META.overdue.color;
    if (stats.weak_count > 0) return PRIORITY_META.weak.color;
    return "#4ade80";
  }, [stats]);

  return (
    <AuthLayout>
      <div className="max-w-4xl mx-auto px-4 md:px-6 py-6">
        <div className="flex items-center justify-between mb-5">
          <Link
            href="/pvp"
            className="inline-flex items-center gap-1.5 text-sm"
            style={{ color: "var(--text-muted)" }}
          >
            <ArrowLeft size={14} />
            На арену
          </Link>
          <button
            type="button"
            onClick={backfill}
            className="text-[11px] uppercase tracking-widest px-2 py-1 rounded-md"
            style={{
              color: "var(--text-muted)",
              border: "1px solid var(--border-color)",
            }}
            title="Восстановить SRS-историю из прошлых квизов"
          >
            Синхронизировать историю
          </button>
        </div>

        {/* Hero */}
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="relative overflow-hidden rounded-2xl p-5 md:p-6 mb-6"
          style={{
            background: `linear-gradient(135deg, ${accentByPriority}14 0%, rgba(16,12,28,0.85) 55%, rgba(16,12,28,0.95) 100%)`,
            border: `1px solid ${accentByPriority}33`,
          }}
        >
          <div className="flex items-start justify-between gap-4">
            <div>
              <div
                className="text-[10px] uppercase tracking-wider font-semibold"
                style={{ color: accentByPriority }}
              >
                Работа над ошибками
              </div>
              <h1
                className="text-2xl md:text-3xl font-bold mt-1"
                style={{ color: "var(--text-primary)" }}
              >
                Твой личный Leitner
              </h1>
              <p
                className="text-sm mt-2 max-w-lg"
                style={{ color: "var(--text-muted)" }}
              >
                Система spaced repetition (SM-2 + Leitner) сама возвращает
                слабые вопросы, пока не закрепишь. Чем ниже ease factor — тем
                чаще увидишь.
              </p>
            </div>
            <div
              className="flex h-14 w-14 items-center justify-center rounded-2xl"
              style={{
                background: `${accentByPriority}22`,
                border: `1px solid ${accentByPriority}55`,
                color: accentByPriority,
              }}
            >
              <BookOpen size={26} />
            </div>
          </div>

          <div className="mt-5 grid grid-cols-2 md:grid-cols-4 gap-3">
            <KPI
              label="Всего разборов"
              value={stats?.total_reviews ?? 0}
              icon={Gauge}
              color="#a78bfa"
            />
            <KPI
              label="Просрочено"
              value={stats?.overdue_count ?? 0}
              icon={Clock}
              color="#f87171"
              highlight={(stats?.overdue_count ?? 0) > 0}
            />
            <KPI
              label="Слабых вопросов"
              value={stats?.weak_count ?? 0}
              icon={TrendingDown}
              color="#facc15"
            />
            <KPI
              label="Освоено"
              value={stats?.mastered_count ?? 0}
              icon={CheckCircle2}
              color="#4ade80"
            />
          </div>
        </motion.div>

        {/* Category filter */}
        {mastery.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-5">
            <button
              type="button"
              onClick={() => setCategory(null)}
              className="px-3 py-1 rounded-full text-xs font-semibold uppercase tracking-wider transition-all"
              style={{
                background: category === null ? "#a78bfa22" : "transparent",
                color: category === null ? "#a78bfa" : "var(--text-muted)",
                border: `1px solid ${
                  category === null ? "#a78bfa55" : "var(--border-color)"
                }`,
              }}
            >
              Все
            </button>
            {mastery.map((m) => (
              <button
                key={m.category}
                type="button"
                onClick={() => setCategory(m.category)}
                className="px-3 py-1 rounded-full text-xs font-semibold uppercase tracking-wider transition-all"
                style={{
                  background:
                    category === m.category ? "#a78bfa22" : "transparent",
                  color:
                    category === m.category ? "#a78bfa" : "var(--text-muted)",
                  border: `1px solid ${
                    category === m.category ? "#a78bfa55" : "var(--border-color)"
                  }`,
                }}
              >
                {CATEGORY_LABEL[m.category] ?? m.category}
                <span className="opacity-70 ml-1 font-mono">
                  {m.items_total}
                </span>
              </button>
            ))}
          </div>
        )}

        {/* Queue */}
        {loading ? (
          <div className="flex items-center justify-center py-14">
            <Loader2 size={26} className="animate-spin" style={{ color: "#a78bfa" }} />
          </div>
        ) : queue.length === 0 ? (
          <div
            className="rounded-2xl p-8 text-center"
            style={{
              background: "var(--bg-panel)",
              border: "1px solid var(--border-color)",
            }}
          >
            <CheckCircle2 size={28} style={{ color: "#4ade80" }} className="mx-auto mb-2" />
            <div
              className="font-semibold"
              style={{ color: "var(--text-primary)" }}
            >
              Сегодня очередь пуста
            </div>
            <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
              Играй в Арене или Тренировке — слабые вопросы вернутся сюда.
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {queue.map((item, idx) => {
              const p = PRIORITY_META[item.priority] ?? PRIORITY_META.learning;
              const Icon = p.icon;
              return (
                <motion.div
                  key={item.question_hash}
                  layout
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: idx * 0.02 }}
                  className="rounded-xl p-3 md:p-4 grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3"
                  style={{
                    background: "var(--bg-panel)",
                    border: `1px solid ${p.color}22`,
                  }}
                >
                  <div
                    className="flex items-center justify-center h-9 w-9 rounded-lg"
                    style={{ background: p.bg, color: p.color }}
                  >
                    <Icon size={16} />
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 mb-0.5 flex-wrap">
                      <span
                        className="text-[9px] font-semibold uppercase tracking-widest"
                        style={{ color: p.color }}
                      >
                        {p.label}
                      </span>
                      <span
                        className="text-[10px] uppercase tracking-wider"
                        style={{ color: "var(--text-muted)" }}
                      >
                        {CATEGORY_LABEL[item.question_category] ?? item.question_category}
                      </span>
                    </div>
                    <div
                      className="text-sm leading-snug line-clamp-2"
                      style={{ color: "var(--text-primary)" }}
                    >
                      {item.question_text}
                    </div>
                    <div className="flex items-center gap-3 mt-1 text-[11px] font-mono" style={{ color: "var(--text-muted)" }}>
                      <span title="Ease factor (SM-2)">
                        EF {item.ease_factor.toFixed(2)}
                      </span>
                      <span title="Интервал в днях">
                        {item.interval_days}d
                      </span>
                      {item.current_streak > 0 && (
                        <span className="inline-flex items-center gap-0.5" title="Серия правильных">
                          <Flame size={10} style={{ color: "#fb923c" }} />
                          {item.current_streak}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <LeitnerBox box={item.leitner_box} />
                    <span
                      className="text-[10px] uppercase tracking-wider"
                      style={{ color: "var(--text-muted)" }}
                    >
                      box {item.leitner_box}
                    </span>
                  </div>
                </motion.div>
              );
            })}
          </div>
        )}

        {/* CTA */}
        {queue.length > 0 && (
          <div className="mt-6 flex justify-center">
            <Link
              href="/pvp"
              className="inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold"
              style={{
                background: "#a78bfa",
                color: "#0b0b14",
                boxShadow: "0 12px 24px -12px rgba(167,139,250,0.7)",
              }}
            >
              <BookOpen size={14} />
              Запустить квиз — эти вопросы появятся первыми
            </Link>
          </div>
        )}
      </div>
    </AuthLayout>
  );
}

function KPI({
  label,
  value,
  icon: Icon,
  color,
  highlight,
}: {
  label: string;
  value: number;
  icon: IconComp;
  color: string;
  highlight?: boolean;
}) {
  return (
    <div
      className="rounded-xl p-3"
      style={{
        background: highlight ? `${color}18` : "rgba(255,255,255,0.03)",
        border: `1px solid ${highlight ? `${color}55` : "rgba(255,255,255,0.08)"}`,
      }}
    >
      <div className="flex items-center gap-1.5 mb-1">
        <Icon size={12} style={{ color }} />
        <span
          className="text-[10px] uppercase tracking-widest"
          style={{ color: "var(--text-muted)" }}
        >
          {label}
        </span>
      </div>
      <div
        className="text-2xl font-black font-display tabular-nums"
        style={{ color }}
      >
        {value}
      </div>
    </div>
  );
}
