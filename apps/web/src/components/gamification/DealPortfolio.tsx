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

  // 2026-05-08 graphics polish: rounded-xl + bg-secondary заменены на
  // пиксельную рамку, шрифты ≥14px, square borders на каждой карточке.
  const containerStyle: React.CSSProperties = {
    background: "rgba(8,5,18,0.55)",
    border: "2px solid rgba(167,139,250,0.28)",
    boxShadow: "inset 0 0 18px rgba(0,0,0,0.4)",
  };

  if (loading) {
    return (
      <div className="rounded-sm p-5 animate-pulse" style={containerStyle}>
        <div className="h-4 w-40 rounded-sm bg-[var(--input-bg)] mb-3" />
        <div className="grid grid-cols-3 gap-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-20 rounded-sm bg-[var(--input-bg)]" />
          ))}
        </div>
      </div>
    );
  }

  if (deals.length === 0) {
    return (
      <div className="rounded-sm p-5" style={containerStyle}>
        <div className="flex items-center gap-2 mb-2">
          <Briefcase size={18} className="text-[var(--text-muted)]" />
          <h3
            className="font-pixel uppercase tracking-widest"
            style={{ color: "var(--text-primary)", fontSize: 14 }}
          >
            ▰ ПОРТФОЛИО СДЕЛОК ▰
          </h3>
        </div>
        <p
          className="font-pixel uppercase tracking-widest"
          style={{ color: "var(--text-muted)", fontSize: 14 }}
        >
          Завершите тренировку с результатом «сделка» чтобы добавить первую карточку.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-sm p-5" style={containerStyle}>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Briefcase size={18} className="text-[var(--accent)]" />
          <h3
            className="font-pixel uppercase tracking-widest"
            style={{ color: "var(--text-primary)", fontSize: 14 }}
          >
            ▰ ПОРТФОЛИО СДЕЛОК ▰
          </h3>
        </div>
        <span
          className="font-pixel uppercase tracking-widest tabular-nums"
          style={{ color: "var(--text-muted)", fontSize: 14 }}
        >
          {total} {total === 1 ? "СДЕЛКА" : total < 5 ? "СДЕЛКИ" : "СДЕЛОК"}
        </span>
      </div>

      {/* Deal cards */}
      <div className={compact ? "grid grid-cols-1 sm:grid-cols-3 gap-3" : "grid grid-cols-1 sm:grid-cols-2 gap-3"}>
        {deals.map((deal, i) => (
          <motion.div
            key={deal.id}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
            whileHover={{ scale: 1.02 }}
            className="rounded-sm p-3 flex flex-col gap-2"
            style={{
              background: "rgba(0,0,0,0.4)",
              border: `2px solid ${scoreColor(deal.score)}55`,
            }}
          >
            {/* Archetype + Score */}
            <div className="flex items-center justify-between gap-2">
              <span
                className="font-pixel uppercase tracking-widest truncate"
                style={{
                  color: "var(--text-primary)",
                  fontSize: 14,
                }}
                title={ARCHETYPE_LABELS[deal.archetype] || deal.archetype}
              >
                {ARCHETYPE_LABELS[deal.archetype] || deal.archetype}
              </span>
              <span
                className="font-pixel font-black tabular-nums shrink-0"
                style={{ color: scoreColor(deal.score), fontSize: 22, lineHeight: 1.0 }}
              >
                {deal.score}
              </span>
            </div>

            {/* Badges row */}
            <div className="flex items-center gap-1.5 flex-wrap">
              {deal.had_comeback && (
                <span
                  className="inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 font-pixel uppercase tracking-widest"
                  style={{
                    background: "rgba(250,204,21,0.18)",
                    color: "#facc15",
                    border: "1px solid rgba(250,204,21,0.5)",
                    fontSize: 11,
                  }}
                >
                  <RotateCcw size={10} /> COMEBACK
                </span>
              )}
              {deal.chain_completed && (
                <span
                  className="inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 font-pixel uppercase tracking-widest"
                  style={{
                    background: "rgba(74,222,128,0.18)",
                    color: "#4ade80",
                    border: "1px solid rgba(74,222,128,0.5)",
                    fontSize: 11,
                  }}
                >
                  <Zap size={10} /> CHAIN
                </span>
              )}
              {deal.score >= 90 && (
                <span
                  className="inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 font-pixel uppercase tracking-widest"
                  style={{
                    background: "rgba(255,210,80,0.22)",
                    color: "#ffd650",
                    border: "1px solid rgba(255,210,80,0.6)",
                    fontSize: 11,
                  }}
                >
                  <Star size={10} /> PERFECT
                </span>
              )}
            </div>

            {/* Date + difficulty */}
            <div className="flex items-center justify-between font-pixel uppercase tracking-widest" style={{ fontSize: 12, color: "var(--text-muted)" }}>
              <span>{formatDate(deal.created_at)}</span>
              <span>D{deal.difficulty}</span>
            </div>
          </motion.div>
        ))}
      </div>

      {/* See all link */}
      {compact && total > 3 && (
        <a
          href="/profile"
          className="mt-4 block text-center font-pixel uppercase tracking-widest hover:underline"
          style={{ color: "var(--accent)", fontSize: 14 }}
        >
          Все {total} сделок →
        </a>
      )}
    </div>
  );
}
