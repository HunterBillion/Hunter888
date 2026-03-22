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
      <div
        className="flex items-start gap-2 rounded-lg px-3 py-2"
        style={{
          background: "var(--input-bg)",
          border: "1px solid var(--border-color)",
        }}
      >
        {state.status === "transcribing" && (
          <div className="mt-0.5 flex items-center gap-1">
            {[0, 1, 2].map((i) => (
              <span
                key={i}
                className="inline-block h-1.5 w-1.5 animate-bounce rounded-full"
                style={{
                  background: "var(--accent)",
                  animationDelay: `${i * 150}ms`,
                }}
              />
            ))}
          </div>
        )}
        <div className="min-w-0 flex-1">
          {state.status === "transcribing" && !displayText && (
            <span className="text-xs" style={{ color: "var(--text-muted)" }}>
              Распознавание речи...
            </span>
          )}
          {displayText && (
            <p
              className="text-sm"
              style={{
                color: state.status === "done" ? "var(--text-primary)" : "var(--text-secondary)",
              }}
            >
              {displayText}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
