"use client";

/**
 * MatchProgressHUD — right-column "growth visible" panel.
 *
 * Sprint 3 (2026-04-20). Shows, in real time:
 *   - accuracy (X/Y correct + percent)
 *   - current streak with flame icon
 *   - XP accumulated this match
 *   - per-category progress bars (eligibility, procedure, etc.)
 *   - level progress bar to next tier
 *
 * Data comes from the knowledge store. All values fall back to 0 when
 * missing so the component can render from first mount without guards.
 */

import { motion } from "framer-motion";
import { Flame, Sparkles, Target, TrendingUp } from "lucide-react";

export interface CategoryStat {
  code: string;
  label: string;
  correct: number;
  total: number;
}

interface Props {
  accentColor: string;
  /** Correct answers so far. */
  correct: number;
  /** Total answered (correct + wrong + skipped). */
  answered: number;
  /** Current consecutive correct streak. */
  streak: number;
  /** XP accumulated in this match. */
  xpGained: number;
  /** Optional per-category breakdown (≤5 categories shown). */
  categories?: CategoryStat[];
  /** Percentage towards next level (0-100). */
  levelProgress?: number;
  /** Short label for current level ("Стажёр", "Эксперт", …). */
  levelLabel?: string;
}

export function MatchProgressHUD({
  accentColor,
  correct,
  answered,
  streak,
  xpGained,
  categories = [],
  levelProgress,
  levelLabel,
}: Props) {
  const accuracy = answered > 0 ? Math.round((correct / answered) * 100) : 0;

  return (
    <div className="space-y-4">
      {/* Section title */}
      <div
        className="text-[10px] font-semibold uppercase tracking-wider"
        style={{ color: "var(--text-muted)" }}
      >
        Твой матч
      </div>

      {/* Big accuracy number */}
      <div
        className="rounded-xl p-3"
        style={{
          background: `linear-gradient(135deg, ${accentColor}14, transparent)`,
          border: `1px solid ${accentColor}22`,
        }}
      >
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-1.5">
            <Target size={12} style={{ color: accentColor }} />
            <span
              className="text-[10px] font-semibold uppercase tracking-wider"
              style={{ color: "var(--text-muted)" }}
            >
              Точность
            </span>
          </div>
          <span
            className="font-mono text-sm tabular-nums"
            style={{ color: "var(--text-secondary)" }}
          >
            {correct}/{answered || 0}
          </span>
        </div>
        <div
          className="font-display text-3xl font-bold tabular-nums"
          style={{ color: accentColor }}
        >
          {accuracy}
          <span className="text-base opacity-60">%</span>
        </div>
      </div>

      {/* Streak + XP row */}
      <div className="grid grid-cols-2 gap-2">
        <MetricPill
          icon={Flame}
          label="Streak"
          value={streak}
          accent={streak >= 3 ? "#f97316" : "var(--text-muted)"}
        />
        <MetricPill
          icon={Sparkles}
          label="XP"
          value={xpGained}
          accent={xpGained > 0 ? "#22c55e" : xpGained < 0 ? "var(--danger)" : "var(--text-muted)"}
          signed
        />
      </div>

      {/* Categories */}
      {categories.length > 0 && (
        <div>
          <div
            className="text-[10px] font-semibold uppercase tracking-wider mb-2"
            style={{ color: "var(--text-muted)" }}
          >
            По категориям
          </div>
          <div className="space-y-1.5">
            {categories.slice(0, 5).map((cat) => (
              <CategoryRow key={cat.code} cat={cat} accent={accentColor} />
            ))}
          </div>
        </div>
      )}

      {/* Level progress */}
      {typeof levelProgress === "number" && (
        <div
          className="rounded-xl p-3"
          style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)" }}
        >
          <div className="flex items-center justify-between mb-1.5">
            <div className="flex items-center gap-1.5">
              <TrendingUp size={12} style={{ color: accentColor }} />
              <span
                className="text-[10px] font-semibold uppercase tracking-wider"
                style={{ color: "var(--text-muted)" }}
              >
                {levelLabel ? `Уровень — ${levelLabel}` : "До уровня"}
              </span>
            </div>
            <span
              className="font-mono text-xs tabular-nums"
              style={{ color: accentColor }}
            >
              {Math.round(levelProgress)}%
            </span>
          </div>
          <div
            className="h-1.5 rounded-full overflow-hidden"
            style={{ background: "var(--bg-primary)" }}
          >
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${Math.max(0, Math.min(100, levelProgress))}%` }}
              transition={{ duration: 0.7, ease: "easeOut" }}
              className="h-full rounded-full"
              style={{ background: accentColor }}
            />
          </div>
        </div>
      )}
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────

function MetricPill({
  icon: Icon,
  label,
  value,
  accent,
  signed = false,
}: {
  icon: React.ComponentType<{ size?: number }>;
  label: string;
  value: number;
  accent: string;
  signed?: boolean;
}) {
  const display = signed && value > 0 ? `+${value}` : `${value}`;
  return (
    <div
      className="rounded-xl p-2.5"
      style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)" }}
    >
      <div className="flex items-center gap-1 mb-0.5">
        <Icon size={10} />
        <span
          className="text-[9px] font-semibold uppercase tracking-wider"
          style={{ color: "var(--text-muted)" }}
        >
          {label}
        </span>
      </div>
      <div
        className="font-display text-xl font-bold tabular-nums"
        style={{ color: accent }}
      >
        {display}
      </div>
    </div>
  );
}

function CategoryRow({ cat, accent }: { cat: CategoryStat; accent: string }) {
  const pct = cat.total > 0 ? Math.round((cat.correct / cat.total) * 100) : 0;
  return (
    <div>
      <div className="flex justify-between text-[11px] mb-0.5">
        <span style={{ color: "var(--text-secondary)" }}>{cat.label}</span>
        <span className="font-mono tabular-nums" style={{ color: "var(--text-muted)" }}>
          {cat.correct}/{cat.total}
        </span>
      </div>
      <div
        className="h-1 rounded-full overflow-hidden"
        style={{ background: "var(--input-bg)" }}
      >
        <motion.div
          className="h-full rounded-full"
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.6 }}
          style={{ background: accent }}
        />
      </div>
    </div>
  );
}
