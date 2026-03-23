"use client";

import { Component, type ReactNode } from "react";
import { AlertTriangle } from "lucide-react";

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
    console.error("[TrainingErrorBoundary] Caught error:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-screen items-center justify-center bg-gray-950 p-4">
          <div className="max-w-md rounded-2xl border border-red-500/30 bg-gray-900 p-8 text-center">
            <AlertTriangle className="mx-auto mb-4 h-12 w-12 text-red-400" />
            <h2 className="mb-2 text-xl font-semibold text-white">
              Произошла ошибка
            </h2>
            <p className="mb-6 text-sm text-gray-400">
              Во время тренировки произошла непредвиденная ошибка.
              {this.props.sessionId && (
                <> Сессия <code className="text-xs text-gray-500">{this.props.sessionId}</code> сохранена.</>
              )}
            </p>
            <div className="flex gap-3 justify-center">
              <button
                onClick={() => this.setState({ hasError: false, error: null })}
                className="rounded-lg bg-gray-800 px-4 py-2 text-sm text-gray-300 hover:bg-gray-700 transition"
              >
                Попробовать снова
              </button>
              <a
                href="/training"
                className="rounded-lg bg-orange-600 px-4 py-2 text-sm text-white hover:bg-orange-500 transition"
              >
                К тренировкам
              </a>
            </div>
            {process.env.NODE_ENV === "development" && this.state.error && (
              <pre className="mt-4 max-h-32 overflow-auto rounded bg-gray-950 p-2 text-left text-xs text-red-300">
                {this.state.error.message}
              </pre>
            )}
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
