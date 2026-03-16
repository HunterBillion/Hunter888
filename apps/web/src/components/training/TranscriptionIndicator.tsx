"use client";

import { useEffect, useState } from "react";
import type { TranscriptionState } from "@/types";

interface TranscriptionIndicatorProps {
  state: TranscriptionState;
}

export default function TranscriptionIndicator({
  state,
}: TranscriptionIndicatorProps) {
  const [visible, setVisible] = useState(false);
  const [displayText, setDisplayText] = useState("");

  useEffect(() => {
    if (state.status === "idle" && !state.final) {
      setVisible(false);
      setDisplayText("");
      return;
    }

    setVisible(true);

    if (state.status === "transcribing") {
      setDisplayText(state.partial || "");
    } else if (state.status === "done") {
      setDisplayText(state.final);
      // Fade out after showing final text
      const timer = setTimeout(() => {
        setVisible(false);
      }, 2000);
      return () => clearTimeout(timer);
    }
  }, [state]);

  if (!visible && !displayText) return null;

  return (
    <div
      className={`transition-opacity duration-500 ${
        visible ? "opacity-100" : "opacity-0"
      }`}
    >
      <div className="flex items-start gap-2 rounded-lg bg-gray-50 px-3 py-2">
        {state.status === "transcribing" && (
          <div className="mt-0.5 flex items-center gap-1">
            <span
              className="inline-block h-1.5 w-1.5 animate-bounce rounded-full bg-blue-500"
              style={{ animationDelay: "0ms" }}
            />
            <span
              className="inline-block h-1.5 w-1.5 animate-bounce rounded-full bg-blue-500"
              style={{ animationDelay: "150ms" }}
            />
            <span
              className="inline-block h-1.5 w-1.5 animate-bounce rounded-full bg-blue-500"
              style={{ animationDelay: "300ms" }}
            />
          </div>
        )}
        <div className="min-w-0 flex-1">
          {state.status === "transcribing" && !displayText && (
            <span className="text-xs text-gray-500">
              Распознавание речи...
            </span>
          )}
          {displayText && (
            <p
              className={`text-sm ${
                state.status === "done" ? "text-gray-900" : "text-gray-600"
              }`}
            >
              {displayText}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
