"use client";

/**
 * PreCallWarmUpHero — Y-pattern primary CTA on /pvp.
 *
 * Replaces the previous CTA-zoo (RatingCard + AP chip + DailyDrillCard +
 * LeagueHeroCard + "Найти соперника" + CharacterPicker stacked above the
 * fold). Asks the working agent ONE question — "когда у тебя встреча
 * с клиентом?" — and routes to the right intensity of training:
 *
 *   30 мин → fast warm-up against a randomly assigned archetype
 *           (matchmaker auto-falls to PvE in <15s on empty queue)
 *   2 часа → same as 30 мин but with the longer 2-round classic flow
 *   завтра → schedule mindset, route to the regular Find Match
 *   нет встречи → "тренировочный режим" — same Find Match but tagged
 *           in localStorage so the streak rule doesn't count idle days
 *
 * Streak is computed off ``localStorage.warmupStreak`` (days where any
 * of the four buttons fired). Source-of-truth lives in the FE for the
 * pilot — moving to the BE belongs to PR-4 (mastery map).
 *
 * Source pattern: Hyperbound's "embed where reps are" (workflow trigger
 * vs daily-app trigger). Source: hyperbound.ai/product/ai-sales-roleplays
 * + Lenny Mazal CURR analysis (Duolingo): streak only counts meaningful
 * action, never "opened the app".
 */

import * as React from "react";
import { motion } from "framer-motion";
import { Clock, Phone, Calendar, BookOpen, Flame } from "lucide-react";

export type MeetingProximity = "30min" | "2h" | "tomorrow" | "none";

interface Props {
  /** Disabled while a queue/duel is in flight to prevent double-submit. */
  disabled?: boolean;
  /** Caller fires Find Match (existing PvE-fallback flow). */
  onPick: (proximity: MeetingProximity) => void;
}

const STORAGE_STREAK = "hunter888.pvp.warmupStreak";
const STORAGE_LAST_DAY = "hunter888.pvp.warmupLastDay";

function todayKey(): string {
  const d = new Date();
  return `${d.getUTCFullYear()}-${d.getUTCMonth() + 1}-${d.getUTCDate()}`;
}

function readStreak(): number {
  try {
    const raw = localStorage.getItem(STORAGE_STREAK);
    return raw ? Math.max(0, parseInt(raw, 10) || 0) : 0;
  } catch { return 0; }
}

function recordWarmupForToday(): number {
  try {
    const today = todayKey();
    const last = localStorage.getItem(STORAGE_LAST_DAY);
    if (last === today) return readStreak();
    const prev = readStreak();
    // Compute yesterday's key — naive UTC math is fine for streak purposes
    // (the worst case is a tz-edge user gets one extra streak day, never
    // loses one).
    const yest = new Date();
    yest.setUTCDate(yest.getUTCDate() - 1);
    const yestKey = `${yest.getUTCFullYear()}-${yest.getUTCMonth() + 1}-${yest.getUTCDate()}`;
    const next = last === yestKey ? prev + 1 : 1;
    localStorage.setItem(STORAGE_STREAK, String(next));
    localStorage.setItem(STORAGE_LAST_DAY, today);
    return next;
  } catch { return readStreak(); }
}

const buttons: Array<{
  proximity: MeetingProximity;
  icon: typeof Clock;
  label: string;
  hint: string;
  accent: string;
}> = [
  {
    proximity: "30min",
    icon: Phone,
    label: "Через 30 мин",
    hint: "Быстрая разминка — голос и темп",
    accent: "var(--danger)",
  },
  {
    proximity: "2h",
    icon: Clock,
    label: "Через 2 часа",
    hint: "Классическая дуэль — 2 раунда",
    accent: "var(--accent)",
  },
  {
    proximity: "tomorrow",
    icon: Calendar,
    label: "Завтра",
    hint: "Стратегическая подготовка",
    accent: "var(--gf-xp, #facc15)",
  },
  {
    proximity: "none",
    icon: BookOpen,
    label: "Нет встречи",
    hint: "Тренировка для прокачки",
    accent: "var(--text-muted)",
  },
];

export function PreCallWarmUpHero({ disabled, onPick }: Props) {
  const [streak, setStreak] = React.useState<number>(0);

  React.useEffect(() => {
    setStreak(readStreak());
  }, []);

  const handle = (p: MeetingProximity) => {
    if (disabled) return;
    if (p !== "none") {
      // Only meaningful warm-ups count toward the streak — "нет встречи"
      // is honest signaling, not a fake-touch.
      const next = recordWarmupForToday();
      setStreak(next);
    }
    onPick(p);
  };

  return (
    <div
      className="p-4 sm:p-5"
      style={{
        background: "var(--bg-panel)",
        outline: "2px solid var(--accent)",
        outlineOffset: -2,
        boxShadow: "4px 4px 0 0 var(--accent)",
        borderRadius: 0,
      }}
    >
      <div className="flex items-start justify-between gap-3 mb-3">
        <div>
          <h2
            className="font-pixel uppercase tracking-widest pixel-glow"
            style={{
              color: "var(--text-primary)",
              fontSize: "clamp(15px, 2.4vw, 18px)",
              lineHeight: 1.2,
            }}
          >
            Когда у тебя встреча?
          </h2>
          <p
            className="font-pixel uppercase mt-1"
            style={{ color: "var(--text-muted)", fontSize: 11, letterSpacing: "0.12em" }}
          >
            Подберём интенсивность тренировки
          </p>
        </div>
        {streak > 0 && (
          <div
            className="flex items-center gap-1.5 px-2.5 py-1.5 shrink-0"
            style={{
              background: "color-mix(in srgb, var(--danger) 15%, var(--bg-panel))",
              outline: "1px solid var(--danger)",
              outlineOffset: -1,
              borderRadius: 0,
            }}
            title="Стрик завершённых разминок"
          >
            <Flame size={14} style={{ color: "var(--danger)" }} />
            <span
              className="font-pixel"
              style={{ color: "var(--danger)", fontSize: 13, lineHeight: 1 }}
            >
              {streak}
            </span>
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 sm:gap-3">
        {buttons.map((b) => {
          const Icon = b.icon;
          return (
            <motion.button
              key={b.proximity}
              type="button"
              onClick={() => handle(b.proximity)}
              disabled={disabled}
              whileHover={!disabled ? { x: -1, y: -1 } : undefined}
              whileTap={!disabled ? { x: 2, y: 2 } : undefined}
              className="flex flex-col items-start gap-1.5 p-2.5 sm:p-3 text-left transition-opacity"
              style={{
                background: "var(--bg-secondary, rgba(0,0,0,0.4))",
                outline: `2px solid ${b.accent}`,
                outlineOffset: -2,
                borderRadius: 0,
                boxShadow: `2px 2px 0 0 ${b.accent}`,
                opacity: disabled ? 0.5 : 1,
                cursor: disabled ? "not-allowed" : "pointer",
                minHeight: 78,
              }}
            >
              <Icon size={16} style={{ color: b.accent }} />
              <span
                className="font-pixel uppercase"
                style={{
                  color: b.accent,
                  fontSize: 11,
                  letterSpacing: "0.1em",
                  lineHeight: 1.15,
                }}
              >
                {b.label}
              </span>
              <span
                className="font-pixel"
                style={{
                  color: "var(--text-muted)",
                  fontSize: 9,
                  letterSpacing: "0.06em",
                  lineHeight: 1.2,
                }}
              >
                {b.hint}
              </span>
            </motion.button>
          );
        })}
      </div>
    </div>
  );
}
