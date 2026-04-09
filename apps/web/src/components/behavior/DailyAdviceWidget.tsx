"use client";

import { useEffect } from "react";
import { useBehaviorStore } from "@/stores/useBehaviorStore";
import { Lightbulb, ArrowRight, Target, Brain, BookOpen, Flame, AlertTriangle } from "lucide-react";

const CATEGORY_CONFIG: Record<string, { icon: typeof Lightbulb; color: string; label: string }> = {
  weak_skill: { icon: Target, color: "var(--danger)", label: "Слабый навык" },
  arena_knowledge: { icon: BookOpen, color: "var(--accent, #6366F1)", label: "Знания ФЗ-127" },
  confidence_low: { icon: Brain, color: "#F59E0B", label: "Уверенность" },
  stress_high: { icon: AlertTriangle, color: "#EF4444", label: "Стресс" },
  streak_motivation: { icon: Flame, color: "#F97316", label: "Мотивация" },
  decline_alert: { icon: AlertTriangle, color: "#EF4444", label: "Внимание" },
  general: { icon: Lightbulb, color: "var(--accent, #6366F1)", label: "Совет дня" },
};

export default function DailyAdviceWidget() {
  const { dailyAdvice, adviceLoading, fetchDailyAdvice, markAdviceActed } = useBehaviorStore();

  useEffect(() => {
    fetchDailyAdvice();
  }, [fetchDailyAdvice]);

  if (adviceLoading) {
    return (
      <div className="glass-panel rounded-xl p-4 animate-pulse">
        <div className="h-5 w-32 rounded" style={{ background: "var(--glass-bg)" }} />
        <div className="mt-3 h-4 w-full rounded" style={{ background: "var(--glass-bg)" }} />
        <div className="mt-2 h-4 w-3/4 rounded" style={{ background: "var(--glass-bg)" }} />
      </div>
    );
  }

  if (!dailyAdvice) return null;

  const config = CATEGORY_CONFIG[dailyAdvice.category] || CATEGORY_CONFIG.general;
  const Icon = config.icon;

  const handleAction = () => {
    markAdviceActed(dailyAdvice.id);
    if (dailyAdvice.action_type === "start_training") {
      window.location.href = "/training";
    } else if (dailyAdvice.action_type === "start_quiz") {
      window.location.href = "/pvp";
    } else if (dailyAdvice.action_type === "view_progress") {
      window.location.href = "/dashboard";
    }
  };

  return (
    <div
      className="glass-panel rounded-xl p-4 border-l-4"
      style={{ borderLeftColor: config.color }}
    >
      <div className="flex items-start gap-3">
        <div
          className="flex-shrink-0 w-10 h-10 rounded-lg flex items-center justify-center"
          style={{ background: `color-mix(in srgb, ${config.color} 12%, transparent)` }}
        >
          <Icon className="w-5 h-5" style={{ color: config.color }} />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span
              className="text-xs px-2 py-0.5 rounded-full font-medium"
              style={{ background: `color-mix(in srgb, ${config.color} 12%, transparent)`, color: config.color }}
            >
              {config.label}
            </span>
          </div>

          <h3 className="font-semibold text-sm" style={{ color: "var(--text-primary)" }}>
            {dailyAdvice.title}
          </h3>

          <p className="mt-1 text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
            {dailyAdvice.body}
          </p>

          {dailyAdvice.action_type && (
            <button
              onClick={handleAction}
              className="mt-3 inline-flex items-center gap-1.5 text-sm font-medium transition-colors hover:opacity-80"
              style={{ color: config.color }}
            >
              {dailyAdvice.action_type === "start_training" && "Начать тренировку"}
              {dailyAdvice.action_type === "start_quiz" && "Пройти тест"}
              {dailyAdvice.action_type === "view_progress" && "Смотреть прогресс"}
              <ArrowRight className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
