"use client";

/**
 * WarmupEndingAnimation — renders pixel-art canvas animations
 * for warmup ending scenarios via iframe.
 *
 * Animations are static HTML files in /animations/warmup-endings/
 * that accept URL params for dynamic data (streak count, date, questions).
 *
 * Variants:
 *   - "success"        → d1-success-5of5.html    (all correct)
 *   - "good-start"     → d2-good-start.html      (≥50% correct)
 *   - "not-slept"      → d3-not-fallen-asleep.html (< 50%)
 *   - "streak"         → d4-streak-milestone.html (streak hit 7/14/30/60/100)
 *   - "second-chance"  → d5-second-chance.html    (wrong Qs return via SRS)
 */

import { useMemo } from "react";

type AnimationVariant =
  | "success"
  | "good-start"
  | "not-slept"
  | "streak"
  | "second-chance";

interface WarmupEndingAnimationProps {
  variant: AnimationVariant;
  /** For "streak" variant: the milestone number (7, 14, 30, 60, 100) */
  streakCount?: number;
  /** For "streak" variant: bonus XP amount */
  bonusXP?: number;
  /** For "second-chance" variant: number of questions returning tomorrow */
  questionsReturning?: number;
  /** Custom size (default 256, displayed at 2x = 512px) */
  size?: number;
  className?: string;
}

const ANIMATION_MAP: Record<AnimationVariant, string> = {
  "success":       "/animations/warmup-endings/success-5of5/d1-success-5of5.html",
  "good-start":    "/animations/warmup-endings/good-start/d2-good-start.html",
  "not-slept":     "/animations/warmup-endings/not-fallen-asleep/d3-not-fallen-asleep.html",
  "streak":        "/animations/warmup-endings/streak-milestone/d4-streak-milestone.html",
  "second-chance": "/animations/warmup-endings/second-chance/d5-second-chance.html",
};

/** Determine bonus XP based on streak milestone */
function streakBonusXP(streak: number): number {
  if (streak >= 100) return 1000;
  if (streak >= 60)  return 500;
  if (streak >= 30)  return 300;
  if (streak >= 14)  return 200;
  if (streak >= 7)   return 100;
  return 50;
}

/** Check if current streak is a milestone worth celebrating */
export function isStreakMilestone(streak: number): boolean {
  return [7, 14, 30, 60, 100].includes(streak);
}

/**
 * Pick the right animation variant based on warmup results.
 */
export function pickAnimationVariant(
  correct: number,
  total: number,
  streakCount: number,
  failedQuestionCount: number
): AnimationVariant {
  // Streak milestones take priority
  if (isStreakMilestone(streakCount)) return "streak";

  const ratio = total > 0 ? correct / total : 0;

  if (ratio === 1) return "success";
  if (ratio >= 0.5) return "good-start";

  // If there are failed questions that will return via SRS
  if (failedQuestionCount > 0) return "second-chance";

  return "not-slept";
}

export default function WarmupEndingAnimation({
  variant,
  streakCount = 7,
  bonusXP,
  questionsReturning = 2,
  size = 256,
  className,
}: WarmupEndingAnimationProps) {
  const src = useMemo(() => {
    const base = ANIMATION_MAP[variant];
    const params = new URLSearchParams();

    if (variant === "streak") {
      params.set("streak", String(streakCount));
      params.set("bonus", String(bonusXP ?? streakBonusXP(streakCount)));
    }

    if (variant === "second-chance") {
      params.set("questions", String(questionsReturning));
      // Pass today's date so calendar is always accurate
      const today = new Date();
      params.set("date", today.toISOString().slice(0, 10));
    }

    const qs = params.toString();
    return qs ? `${base}?${qs}` : base;
  }, [variant, streakCount, bonusXP, questionsReturning]);

  const displaySize = size * 2; // 2x for crisp pixel art

  return (
    <div
      className={className}
      style={{
        width: displaySize,
        maxWidth: "100%",
        aspectRatio: "1",
        position: "relative",
        overflow: "hidden",
        borderRadius: 12,
        margin: "0 auto",
      }}
    >
      <iframe
        src={src}
        title={`Warmup ending: ${variant}`}
        style={{
          width: displaySize,
          height: displaySize,
          maxWidth: "100%",
          maxHeight: "100%",
          border: "none",
          display: "block",
          imageRendering: "pixelated",
        }}
        sandbox="allow-scripts"
        loading="eager"
      />
    </div>
  );
}
