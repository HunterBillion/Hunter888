"use client";

import { Component, type ReactNode } from "react";
import { RotateCcw, BookOpen } from "lucide-react";
import { logger } from "@/lib/logger";

interface Props {
  children: ReactNode;
  sessionId?: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class TrainingErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    logger.error("[TrainingErrorBoundary] Caught error:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          className="flex min-h-screen items-center justify-center px-4"
          style={{ background: "var(--bg-primary)" }}
        >
          <div className="relative text-center max-w-md w-full">
            {/* Background ghost */}
            <div
              className="pointer-events-none absolute inset-0 flex items-center justify-center select-none"
              style={{ overflow: "hidden" }}
            >
              <span
                className="font-display font-black leading-none"
                style={{
                  fontSize: "140px",
                  color: "transparent",
                  WebkitTextStroke: "1.5px rgba(255,42,109,0.06)",
                }}
              >
                СБОЙ
              </span>
            </div>

            <div className="relative z-10">
              {/* Pulsing warning ring */}
              <div
                className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full"
                style={{
                  background: "rgba(255,42,109,0.06)",
                  border: "2px solid rgba(255,42,109,0.15)",
                  boxShadow: "0 0 30px rgba(255,42,109,0.08)",
                }}
              >
                <div
                  className="font-display text-xl font-black"
                  style={{
                    color: "var(--danger)",
                    animation: "pulse 2s ease-in-out infinite",
                  }}
                >
                  !
                </div>
              </div>

              <div
                className="font-mono text-[10px] tracking-[0.25em] uppercase mb-3"
                style={{ color: "rgba(255,42,109,0.5)" }}
              >
                {"// ОШИБКА_ТРЕНИРОВКИ"}
              </div>

              <h2
                className="mb-2 text-xl font-bold"
                style={{ color: "var(--text-primary)" }}
              >
                Сессия прервана
              </h2>

              <p className="mb-3 text-sm" style={{ color: "var(--text-muted)" }}>
                Во время тренировки произошла непредвиденная ошибка.
              </p>

              {this.props.sessionId && (
                <div
                  className="font-mono text-xs rounded-lg px-4 py-2 mb-5 inline-block"
                  style={{
                    background: "var(--input-bg)",
                    border: "1px solid var(--border-color)",
                    color: "var(--text-muted)",
                  }}
                >
                  <span style={{ opacity: 0.5 }}>session:</span>{" "}
                  <span style={{ color: "var(--accent)" }}>{this.props.sessionId}</span>
                  <span style={{ opacity: 0.5 }}> — сохранена</span>
                </div>
              )}

              {process.env.NODE_ENV === "development" && this.state.error && (
                <div
                  className="mb-5 rounded-lg px-4 py-2.5 text-left font-mono text-xs mx-auto max-w-sm"
                  style={{
                    background: "var(--input-bg)",
                    border: "1px solid var(--border-color)",
                    color: "var(--text-muted)",
                  }}
                >
                  <span style={{ color: "rgba(255,42,109,0.5)" }}>{">"} </span>
                  {this.state.error.message}
                </div>
              )}

              <div className="flex gap-3 justify-center mt-6">
                <button
                  onClick={() => this.setState({ hasError: false, error: null })}
                  className="flex items-center gap-2 rounded-xl px-5 py-3 text-sm font-semibold transition-all"
                  style={{
                    background: "var(--accent)",
                    color: "#fff",
                    boxShadow: "0 0 20px var(--accent-glow)",
                  }}
                >
                  <RotateCcw size={15} /> Попробовать снова
                </button>
                <a
                  href="/training"
                  className="flex items-center gap-2 rounded-xl px-5 py-3 text-sm font-semibold transition-all"
                  style={{
                    background: "var(--input-bg)",
                    color: "var(--text-primary)",
                    border: "1px solid var(--border-color)",
                  }}
                >
                  <BookOpen size={15} /> К тренировкам
                </a>
              </div>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
