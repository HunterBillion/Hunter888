"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { Loader2, ArrowRight } from "lucide-react";
import { Brain, Lightbulb } from "@phosphor-icons/react";
import Link from "next/link";
import { api } from "@/lib/api";

interface OceanTrait {
  value: number;
  label: string;
  level: "high" | "medium" | "low";
}

interface OceanRecommendation {
  archetypes: string[];
  reason: string;
  tip: string;
}

interface OceanData {
  traits: Record<string, OceanTrait>;
  sessions_analyzed: number;
  overall_confidence: number;
  overall_stress_resistance: number;
  overall_adaptability: number;
  archetype_scores: Record<string, number>;
  recommendations: OceanRecommendation[];
  performance: {
    under_hostility: number;
    under_stress: number;
    with_empathy: number;
  };
}

const TRAIT_COLORS: Record<string, string> = {
  openness: "var(--accent)",
  conscientiousness: "var(--success)",
  extraversion: "var(--warning)",
  agreeableness: "var(--accent)",
  neuroticism: "var(--magenta)",
};

function TraitBar({ traitKey, trait }: { traitKey: string; trait: OceanTrait }) {
  const color = TRAIT_COLORS[traitKey] || "var(--accent)";
  const pct = Math.min(100, Math.max(0, trait.value));

  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
          {trait.label}
        </span>
        <span className="text-xs font-mono font-bold" style={{ color }}>
          {Math.round(trait.value)}
        </span>
      </div>
      <div className="h-1.5 rounded-full overflow-hidden" style={{ background: "var(--bg-secondary)" }}>
        <motion.div
          className="h-full rounded-full"
          style={{ background: color }}
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.8, ease: "easeOut" }}
        />
      </div>
    </div>
  );
}

export function OceanProfileWidget() {
  const [data, setData] = useState<OceanData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get("/gamification/me/ocean-profile")
      .then((resp) => setData(resp as OceanData))
      .catch(() => null)
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="glass-panel p-5 flex items-center justify-center py-8">
        <Loader2 size={18} className="animate-spin" style={{ color: "var(--accent)" }} />
      </div>
    );
  }

  if (!data || data.sessions_analyzed < 3) {
    return (
      <div className="glass-panel p-5">
        <div className="flex items-center gap-2 mb-3">
          <Brain size={16} weight="duotone" style={{ color: "var(--accent)" }} />
          <h3 className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--accent)" }}>
            OCEAN ПРОФИЛЬ
          </h3>
        </div>
        <div className="text-center py-4">
          <Brain size={24} weight="duotone" className="mx-auto mb-2" style={{ color: "var(--text-muted)", opacity: 0.5 }} />
          <p className="text-xs" style={{ color: "var(--text-muted)" }}>
            Пройдите минимум 3 тренировки для построения профиля
          </p>
        </div>
      </div>
    );
  }

  return (
    <motion.div
      className="glass-panel p-5"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.15 }}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Brain size={16} weight="duotone" style={{ color: "var(--accent)" }} />
          <h3 className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--accent)" }}>
            OCEAN ПРОФИЛЬ
          </h3>
        </div>
        <span className="text-xs font-medium" style={{ color: "var(--text-muted)" }}>
          {data.sessions_analyzed} сессий
        </span>
      </div>

      {/* OCEAN bars */}
      <div className="space-y-2.5 mb-4">
        {Object.entries(data.traits).map(([key, trait]) => (
          <TraitBar key={key} traitKey={key} trait={trait} />
        ))}
      </div>

      {/* Performance under conditions */}
      <div className="flex gap-2 mb-4">
        <div
          className="flex-1 rounded-lg p-2 text-center"
          style={{ background: "var(--bg-secondary)", border: "1px solid var(--glass-border)" }}
        >
          <div className="text-xs font-mono font-bold" style={{
            color: data.performance.under_hostility >= 60 ? "var(--success)" : "var(--danger)",
          }}>
            {Math.round(data.performance.under_hostility)}
          </div>
          <div className="text-xs font-semibold" style={{ color: "var(--text-muted)" }}>АГРЕССИЯ</div>
        </div>
        <div
          className="flex-1 rounded-lg p-2 text-center"
          style={{ background: "var(--bg-secondary)", border: "1px solid var(--glass-border)" }}
        >
          <div className="text-xs font-mono font-bold" style={{
            color: data.performance.under_stress >= 60 ? "var(--success)" : "var(--warning)",
          }}>
            {Math.round(data.performance.under_stress)}
          </div>
          <div className="text-xs font-semibold" style={{ color: "var(--text-muted)" }}>СТРЕСС</div>
        </div>
        <div
          className="flex-1 rounded-lg p-2 text-center"
          style={{ background: "var(--bg-secondary)", border: "1px solid var(--glass-border)" }}
        >
          <div className="text-xs font-mono font-bold" style={{
            color: data.performance.with_empathy >= 60 ? "var(--success)" : "var(--accent)",
          }}>
            {Math.round(data.performance.with_empathy)}
          </div>
          <div className="text-xs font-semibold" style={{ color: "var(--text-muted)" }}>ЭМПАТИЯ</div>
        </div>
      </div>

      {/* Recommendations */}
      {data.recommendations.length > 0 && (
        <div className="space-y-1.5 mb-4">
          {data.recommendations.slice(0, 2).map((rec, i) => (
            <div key={i} className="flex items-start gap-2">
              <Lightbulb
                size={11}
                weight="duotone"
                className="mt-0.5 flex-shrink-0"
                style={{ color: "var(--warning)" }}
              />
              <div>
                <span className="text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
                  {rec.reason}
                </span>
                <span className="text-xs block mt-0.5" style={{ color: "var(--text-muted)" }}>
                  {rec.tip}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Action */}
      <Link href="/training">
        <button
          className="w-full flex items-center justify-center gap-1.5 py-2 rounded text-xs font-medium transition-colors"
          style={{ background: "var(--accent)", color: "var(--bg-primary)" }}
        >
          Тренировать слабые стороны
          <ArrowRight size={12} />
        </button>
      </Link>
    </motion.div>
  );
}
