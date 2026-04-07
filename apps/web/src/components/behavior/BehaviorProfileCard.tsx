"use client";

import { useEffect } from "react";
import { useBehaviorStore } from "@/stores/useBehaviorStore";
import { Shield, Brain, Zap, Heart, TrendingUp, TrendingDown, Minus } from "lucide-react";

function ScoreBar({ label, value, icon: Icon, color }: {
  label: string;
  value: number;
  icon: typeof Shield;
  color: string;
}) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div className="flex items-center gap-3">
      <div className="flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: `${color}15` }}>
        <Icon className="w-4 h-4" style={{ color }} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs font-medium" style={{ color: "var(--text-secondary)" }}>{label}</span>
          <span className="text-xs font-bold" style={{ color }}>{Math.round(pct)}</span>
        </div>
        <div className="h-2 rounded-full overflow-hidden" style={{ background: "var(--glass-bg)" }}>
          <div
            className="h-full rounded-full transition-all duration-700"
            style={{ width: `${pct}%`, background: color }}
          />
        </div>
      </div>
    </div>
  );
}

function TrendBadge({ direction }: { direction: string | null }) {
  if (!direction) return null;
  const config = {
    improving: { icon: TrendingUp, color: "#22C55E", text: "Рост" },
    declining: { icon: TrendingDown, color: "#EF4444", text: "Спад" },
    stable: { icon: Minus, color: "#F59E0B", text: "Стабильно" },
    stagnating: { icon: Minus, color: "#9CA3AF", text: "Стагнация" },
  }[direction] || { icon: Minus, color: "#9CA3AF", text: direction };

  const Icon = config.icon;
  return (
    <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full" style={{ background: `${config.color}15`, color: config.color }}>
      <Icon className="w-3 h-3" />
      {config.text}
    </span>
  );
}

export default function BehaviorProfileCard({ userId }: { userId?: string }) {
  const { profile, profileLoading, trends, fetchProfile, fetchTrends } = useBehaviorStore();

  useEffect(() => {
    fetchProfile(userId);
    fetchTrends(userId, 4);
  }, [userId, fetchProfile, fetchTrends]);

  if (profileLoading || !profile) {
    return (
      <div className="glass-panel rounded-xl p-4 animate-pulse">
        <div className="h-5 w-40 rounded mb-4" style={{ background: "var(--glass-bg)" }} />
        <div className="space-y-3">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="h-8 rounded" style={{ background: "var(--glass-bg)" }} />
          ))}
        </div>
      </div>
    );
  }

  const latestTrend = trends[0];

  return (
    <div className="glass-panel rounded-xl p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-sm" style={{ color: "var(--text-primary)" }}>
          Поведенческий профиль
        </h3>
        {latestTrend && <TrendBadge direction={latestTrend.direction} />}
      </div>

      <div className="space-y-3">
        <ScoreBar
          label="Уверенность"
          value={profile.composite_scores.confidence}
          icon={Shield}
          color="#6366F1"
        />
        <ScoreBar
          label="Стрессоустойчивость"
          value={profile.composite_scores.stress_resistance}
          icon={Zap}
          color="#F59E0B"
        />
        <ScoreBar
          label="Адаптивность"
          value={profile.composite_scores.adaptability}
          icon={Brain}
          color="var(--info)"
        />
        <ScoreBar
          label="Эмпатия"
          value={profile.composite_scores.empathy}
          icon={Heart}
          color="#EC4899"
        />
      </div>

      {profile.sessions_analyzed > 0 && (
        <p className="mt-3 text-xs" style={{ color: "var(--text-muted)" }}>
          На основе {profile.sessions_analyzed} сессий
        </p>
      )}
    </div>
  );
}
