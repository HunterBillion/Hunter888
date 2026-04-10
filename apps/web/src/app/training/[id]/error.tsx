"use client";

import { useEffect } from "react";
import { RotateCcw, BookOpen } from "lucide-react";

export default function TrainingError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[Training Error]", error);
  }, [error]);

  return (
    <div
      className="flex min-h-screen items-center justify-center px-4"
      style={{ background: "var(--bg-primary)" }}
    >
      <div className="text-center max-w-md">
        <h2 className="mb-3 text-xl font-bold" style={{ color: "var(--text-primary)" }}>
          Сессия прервана
        </h2>
        <p className="mb-4 text-sm" style={{ color: "var(--text-muted)" }}>
          {(error?.message || "Произошла ошибка").slice(0, 200)}
        </p>
        <div className="flex gap-3 justify-center">
          <button
            onClick={reset}
            className="flex items-center gap-2 rounded-xl px-5 py-3 text-sm font-semibold"
            style={{ background: "var(--accent)", color: "#fff" }}
          >
            <RotateCcw size={15} /> Попробовать снова
          </button>
          <a
            href="/training"
            className="flex items-center gap-2 rounded-xl px-5 py-3 text-sm font-semibold"
            style={{ background: "var(--input-bg)", color: "var(--text-primary)", border: "1px solid var(--border-color)" }}
          >
            <BookOpen size={15} /> К тренировкам
          </a>
        </div>
      </div>
    </div>
  );
}
