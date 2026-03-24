"use client";

import { Component, type ReactNode, type ErrorInfo } from "react";
import { AlertTriangle, RotateCcw, Home } from "lucide-react";
import Link from "next/link";

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
 * Especially important for complex pages like training sessions (#7).
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
    console.error("[ErrorBoundary] Caught error:", error, errorInfo);
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      const title = this.props.fallbackTitle || "Что-то пошло не так";
      const description =
        this.props.fallbackDescription ||
        "Произошла ошибка при загрузке страницы. Попробуйте перезагрузить.";

      return (
        <div className="flex min-h-[400px] items-center justify-center p-8">
          <div className="text-center max-w-md">
            <div
              className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl"
              style={{ background: "rgba(255,51,51,0.1)" }}
            >
              <AlertTriangle size={28} style={{ color: "#FF3333" }} />
            </div>
            <h2 className="mb-2 text-xl font-bold" style={{ color: "var(--text-primary)" }}>
              {title}
            </h2>
            <p className="mb-6 text-sm" style={{ color: "var(--text-secondary)" }}>
              {description}
            </p>
            {this.state.error && (
              <pre
                className="mb-6 max-h-32 overflow-auto rounded-lg p-3 text-left text-xs"
                style={{ background: "var(--input-bg)", color: "var(--text-muted)" }}
              >
                {this.state.error.message}
              </pre>
            )}
            <div className="flex items-center justify-center gap-3">
              <button
                onClick={this.handleRetry}
                className="vh-btn-primary flex items-center gap-2"
              >
                <RotateCcw size={14} /> Попробовать снова
              </button>
              <Link href="/home" className="vh-btn-outline flex items-center gap-2">
                <Home size={14} /> На главную
              </Link>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
