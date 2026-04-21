"use client";

/**
 * DealPortfolio — visual archive of completed deals.
 * Each deal = a card with archetype, score, date.
 * Compact mode (dashboard): last 3 deals. Full mode (profile): all deals.
 */

import { useState, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import { Briefcase, Star, Zap, RotateCcw } from "lucide-react";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";

interface Deal {
  id: string;
  archetype: string;
  scenario: string;
  score: number;
  difficulty: number;
  duration_seconds: number;
  xp_earned: number;
  had_comeback: boolean;
  chain_completed: boolean;
  created_at: string;
}

interface DealPortfolioProps {
  compact?: boolean;  // true = dashboard (3 cards), false = full list
  limit?: number;
}

const ARCHETYPE_LABELS: Record<string, string> = {
  skeptic: "Скептик", anxious: "Тревожный", passive: "Пассивный",
  pragmatic: "Прагматик", desperate: "Отчаявшийся", aggressive: "Агрессивный",
  sarcastic: "Саркастичный", know_it_all: "Всезнайка", paranoid: "Параноик",
  manipulator: "Манипулятор", crying: "Плачущий", overwhelmed: "Подавленный",
  hostile: "Враждебный", ghosting: "Призрак", negotiator: "Переговорщик",
};

function scoreColor(score: number): string {
  if (score >= 90) return "var(--warning)";
  if (score >= 70) return "var(--success)";
  if (score >= 50) return "var(--accent)";
  return "var(--text-muted)";
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
  } catch {
    return "";
  }
}

export default function DealPortfolio({ compact = true, limit }: DealPortfolioProps) {
  const [deals, setDeals] = useState<Deal[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  const fetchDeals = useCallback(async () => {
    try {
      const data = await api.get<{ total_deals: number; deals: Deal[] }>(
        `/gamification/portfolio?limit=${limit || (compact ? 3 : 20)}`
      );
      setDeals(data.deals || []);
      setTotal(data.total_deals || 0);
    } catch (err) {
      logger.error("Failed to fetch portfolio:", err);
    } finally {
      setLoading(false);
    }
  }, [compact, limit]);

  useEffect(() => {
    fetchDeals();
  }, [fetchDeals]);

  if (loading) {
    return (
      <div className="rounded-xl bg-[var(--bg-secondary)] p-5 animate-pulse">
        <div className="h-4 w-36 rounded bg-[var(--input-bg)] mb-3" />
        <div className="grid grid-cols-3 gap-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-20 rounded-lg bg-[var(--input-bg)]" />
          ))}
        </div>
      </div>
    );
  }

  if (deals.length === 0) {
    return (
      <div className="rounded-xl bg-[var(--bg-secondary)] p-5">
        <div className="flex items-center gap-2 mb-2">
          <Briefcase size={18} className="text-[var(--text-muted)]" />
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">Портфолио сделок</h3>
        </div>
        <p className="text-xs text-[var(--text-muted)]">
          Завершите тренировку с результатом &laquo;сделка&raquo; чтобы добавить первую карточку.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl bg-[var(--bg-secondary)] p-5">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Briefcase size={18} className="text-[var(--accent)]" />
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">
            Портфолио сделок
          </h3>
        </div>
        <span className="text-xs font-mono text-[var(--text-muted)]">
          {total} {total === 1 ? "сделка" : total < 5 ? "сделки" : "сделок"}
        </span>
      </div>

      {/* Deal cards */}
      <div className={compact ? "grid grid-cols-1 sm:grid-cols-3 gap-3" : "space-y-2"}>
        {deals.map((deal, i) => (
          <motion.div
            key={deal.id}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
            className="rounded-lg bg-[var(--input-bg)] p-3 flex flex-col gap-1.5"
          >
            {/* Archetype + Score */}
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-[var(--text-primary)]">
                {ARCHETYPE_LABELS[deal.archetype] || deal.archetype}
              </span>
              <span
                className="text-sm font-bold font-mono"
                style={{ color: scoreColor(deal.score) }}
              >
                {deal.score}
              </span>
            </div>

            {/* Badges row */}
            <div className="flex items-center gap-1.5 flex-wrap">
              {deal.had_comeback && (
                <span className="inline-flex items-center gap-0.5 rounded bg-[var(--warning-muted)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--warning)]">
                  <RotateCcw size={9} /> Comeback
                </span>
              )}
              {deal.chain_completed && (
                <span className="inline-flex items-center gap-0.5 rounded bg-[var(--success-muted)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--success)]">
                  <Zap size={9} /> Chain
                </span>
              )}
              {deal.score >= 90 && (
                <span className="inline-flex items-center gap-0.5 rounded bg-[var(--warning-muted)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--warning)]">
                  <Star size={9} /> Perfect
                </span>
              )}
            </div>

            {/* Date + difficulty */}
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-[var(--text-muted)]">
                {formatDate(deal.created_at)}
              </span>
              <span className="text-[10px] text-[var(--text-muted)]">
                D{deal.difficulty}
              </span>
            </div>
          </motion.div>
        ))}
      </div>

      {/* See all link */}
      {compact && total > 3 && (
        <a
          href="/profile"
          className="mt-3 block text-center text-xs font-medium text-[var(--accent)] hover:underline"
        >
          Все {total} сделок &rarr;
        </a>
      )}
    </div>
  );
}
