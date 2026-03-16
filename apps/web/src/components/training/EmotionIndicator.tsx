"use client";

import { useEffect, useState } from "react";
import type { EmotionState } from "@/types";

interface EmotionIndicatorProps {
  emotion: EmotionState;
}

const EMOTION_CONFIG: Record<
  EmotionState,
  { label: string; icon: string; bg: string; text: string; border: string }
> = {
  cold: {
    label: "Холодный",
    icon: "\u2744\uFE0F", // snowflake
    bg: "bg-blue-100",
    text: "text-blue-800",
    border: "border-blue-200",
  },
  warming: {
    label: "Теплеет",
    icon: "\u2600\uFE0F", // sun
    bg: "bg-yellow-100",
    text: "text-yellow-800",
    border: "border-yellow-200",
  },
  open: {
    label: "Открыт",
    icon: "\u2705", // checkmark
    bg: "bg-green-100",
    text: "text-green-800",
    border: "border-green-200",
  },
};

export default function EmotionIndicator({ emotion }: EmotionIndicatorProps) {
  const [animating, setAnimating] = useState(false);
  const [prevEmotion, setPrevEmotion] = useState(emotion);

  useEffect(() => {
    if (emotion !== prevEmotion) {
      setAnimating(true);
      setPrevEmotion(emotion);
      const timer = setTimeout(() => setAnimating(false), 500);
      return () => clearTimeout(timer);
    }
  }, [emotion, prevEmotion]);

  const config = EMOTION_CONFIG[emotion] || EMOTION_CONFIG.cold;

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-all duration-300 ${
        config.bg
      } ${config.text} ${config.border} ${
        animating ? "scale-110" : "scale-100"
      }`}
    >
      <span className={`${animating ? "animate-bounce" : ""}`}>
        {config.icon}
      </span>
      {config.label}
    </span>
  );
}
