"use client";

import { Component, type ReactNode, type ErrorInfo } from "react";
import { RotateCcw, Home } from "lucide-react";
import Link from "next/link";
import { logger } from "@/lib/logger";

interface ErrorBoundaryProps {
  children: ReactNode;
  fallbackTitle?: string;
  fallbackDescription?: string;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

/**
 * Generic error boundary component.
 * Catches rendering errors in child tree and shows a recovery UI.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    logger.error("[ErrorBoundary] Caught error:", error, errorInfo);
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      const title = this.props.fallbackTitle || "Что-то пошло не так";
      const description =
        this.props.fallbackDescription ||
        "Связь нестабильна. Попробуем через мгновение.";

      return (
        <div className="flex min-h-[400px] items-center justify-center p-8">
          <div className="relative text-center max-w-md w-full">
            {/* Background ghost text */}
            <div
              className="pointer-events-none absolute inset-0 flex items-center justify-center select-none"
              style={{ overflow: "hidden" }}
            >
              <span
                className="font-display font-black leading-none"
                style={{
                  fontSize: "120px",
                  color: "transparent",
                  WebkitTextStroke: "1px var(--danger-muted)",
                }}
              >
                ERR
              </span>
            </div>

            {/* Content */}
            <div className="relative z-10">
              {/* Pulsing dot */}
              <div
                className="mx-auto mb-5 flex h-12 w-12 items-center justify-center rounded-full"
                style={{
                  background: "var(--danger-muted)",
                  border: "1.5px solid var(--danger-muted)",
                }}
              >
                <div
                  className="h-3 w-3 rounded-full"
                  style={{
                    background: "var(--danger)",
                    boxShadow: "0 0 12px var(--danger-muted)",
                    animation: "pulse 2s ease-in-out infinite",
                  }}
                />
              </div>

              <div
                className="font-mono text-xs tracking-widest uppercase mb-2"
                style={{ color: "var(--danger)" }}
              >
                {"// ОШИБКА_КОМПОНЕНТА"}
              </div>

              <h2
                className="mb-2 text-lg font-bold"
                style={{ color: "var(--text-primary)" }}
              >
                {title}
              </h2>

              <p className="mb-4 text-sm" style={{ color: "var(--text-muted)" }}>
                {description}
              </p>

              {this.state.error && (
                <div
                  className="mb-5 rounded-lg px-4 py-2.5 text-left font-mono text-xs"
                  style={{
                    background: "var(--input-bg)",
                    border: "1px solid var(--border-color)",
                    color: "var(--text-muted)",
                  }}
                >
                  <span style={{ color: "rgba(229,72,77,0.5)" }}>{">"} </span>
                  {this.state.error.message}
                </div>
              )}

              <div className="flex items-center justify-center gap-3">
                <button
                  onClick={this.handleRetry}
                  className="flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition-all"
                  style={{
                    background: "var(--accent)",
                    color: "#fff",
                    boxShadow: "0 0 16px var(--accent-glow)",
                  }}
                >
                  <RotateCcw size={14} /> Повторить
                </button>
                <Link
                  href="/home"
                  className="flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition-all"
                  style={{
                    background: "var(--input-bg)",
                    color: "var(--text-primary)",
                    border: "1px solid var(--border-color)",
                  }}
                >
                  <Home size={14} /> На главную
                </Link>
              </div>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
