"use client";

import { useEffect, useState, useRef, Component, type ReactNode, type ErrorInfo } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { logger } from "@/lib/logger";
import { Crosshair, Loader2, RefreshCw } from "lucide-react";
import { getToken } from "@/lib/auth";
import { api } from "@/lib/api";
import Header from "./Header";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { KeyboardShortcutsOverlay } from "@/components/ui/KeyboardShortcutsOverlay";
import { CommandPalette } from "@/components/ui/CommandPalette";
import { PageTransition } from "@/components/layout/PageTransition";

// ── Error Boundary ──────────────────────────────────────
interface ErrorBoundaryProps {
  children: ReactNode;
}
interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

class AuthErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    logger.error("[AuthLayout] Error caught:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-screen items-center justify-center" style={{ background: "var(--bg-primary)" }}>
          <div className="glass-panel max-w-md px-8 py-6 text-center">
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full mb-4" style={{ background: "rgba(255,51,51,0.1)" }}>
              <span className="text-2xl">⚠️</span>
            </div>
            <h2 className="font-display text-lg font-bold mb-2" style={{ color: "var(--text-primary)" }}>
              Что-то пошло не так
            </h2>
            <p className="text-sm mb-4" style={{ color: "var(--text-muted)" }}>
              {this.state.error?.message || "Произошла непредвиденная ошибка"}
            </p>
            <button
              onClick={() => {
                this.setState({ hasError: false, error: null });
                window.location.reload();
              }}
              className="vh-btn-primary flex items-center gap-2 mx-auto"
            >
              <RefreshCw size={14} />
              Перезагрузить
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

// ── Auth Layout ──────────────────────────────────────────
interface AuthLayoutProps {
  children: ReactNode;
  requireConsent?: boolean;
}

// Module-level consent cache (avoids re-fetching on every page nav)
// Keyed by user token hash to prevent cross-user cache leakage
let _consentChecked = false;
let _consentOk = false;
let _consentUserToken: string | null = null;

/** Reset consent cache — MUST be called on logout to prevent cross-user leakage */
export function resetConsentCache() {
  _consentChecked = false;
  _consentOk = false;
  _consentUserToken = null;
}

export default function AuthLayout({
  children,
  requireConsent = true,
}: AuthLayoutProps) {
  const router = useRouter();
  const [state, setState] = useState<"loading" | "ready" | "redirecting" | "error">(
    () => {
      const token = typeof window !== "undefined" ? getToken() : null;
      if (!token) return "loading";
      if (!requireConsent || _consentOk) return "ready";
      return "loading";
    },
  );
  const [errorMessage, setErrorMessage] = useState("");
  const didRun = useRef(false);

  useEffect(() => {
    if (didRun.current) return;
    didRun.current = true;

    const token = getToken();
    if (!token) {
      setState("redirecting");
      router.replace("/login");
      return;
    }

    // Invalidate consent cache if user changed (prevents cross-user leakage)
    if (_consentUserToken && _consentUserToken !== token) {
      _consentChecked = false;
      _consentOk = false;
    }
    _consentUserToken = token;

    if (!requireConsent || _consentOk) {
      setState("ready");
      return;
    }

    if (_consentChecked) {
      setState(_consentOk ? "ready" : "redirecting");
      if (!_consentOk) router.replace("/consent");
      return;
    }

    api
      .get("/consent/status")
      .then((data) => {
        _consentChecked = true;
        _consentOk = data.all_accepted;
        if (data.all_accepted) {
          setState("ready");
        } else {
          setState("redirecting");
          router.replace("/consent");
        }
      })
      .catch((err) => {
        // Fail-closed: don't allow access if consent check fails
        _consentChecked = false;
        _consentOk = false;
        setState("error");
        setErrorMessage(err?.message || "Не удалось проверить статус согласия");
      });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  if (state === "error") {
    return (
      <div className="flex min-h-screen items-center justify-center" style={{ background: "var(--bg-primary)" }}>
        <div className="glass-panel max-w-md px-8 py-6 text-center">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full mb-4" style={{ background: "rgba(255,51,51,0.1)" }}>
            <span className="text-2xl">⚠️</span>
          </div>
          <h2 className="font-display text-lg font-bold mb-2" style={{ color: "var(--text-primary)" }}>
            Ошибка подключения
          </h2>
          <p className="text-sm mb-4" style={{ color: "var(--text-muted)" }}>
            {errorMessage || "Не удалось подключиться к серверу"}
          </p>
          <button
            onClick={() => {
              didRun.current = false;
              setState("loading");
              setErrorMessage("");
              // Retry consent check
              setTimeout(() => {
                didRun.current = false;
                const token = getToken();
                if (!token) {
                  router.replace("/login");
                  return;
                }
                api.get("/consent/status")
                  .then((data) => {
                    _consentChecked = true;
                    _consentOk = data.all_accepted;
                    setState(data.all_accepted ? "ready" : "redirecting");
                    if (!data.all_accepted) router.replace("/consent");
                  })
                  .catch(() => {
                    setState("error");
                    setErrorMessage("Сервер по-прежнему недоступен");
                  });
              }, 100);
            }}
            className="vh-btn-primary flex items-center gap-2 mx-auto"
          >
            <RefreshCw size={14} />
            Повторить
          </button>
        </div>
      </div>
    );
  }

  if (state === "loading" || state === "redirecting") {
    return (
      <div className="flex min-h-screen items-center justify-center" style={{ background: "var(--bg-primary)" }}>
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          className="flex flex-col items-center gap-3"
        >
          <div className="relative">
            <Crosshair size={24} style={{ color: "var(--accent)" }} />
            <Loader2
              size={40}
              className="absolute -left-2 -top-2 animate-spin"
              style={{ color: "var(--accent)", opacity: 0.3 }}
            />
          </div>
          <span className="font-mono text-xs" style={{ color: "var(--text-muted)" }}>
            {state === "loading" ? "ПРОВЕРКА АВТОРИЗАЦИИ..." : "ПЕРЕНАПРАВЛЕНИЕ..."}
          </span>
        </motion.div>
      </div>
    );
  }

  return (
    <AuthErrorBoundary>
      <div className="flex min-h-screen flex-col" style={{ background: "var(--bg-primary)" }}>
        {/* Scanlines — centralized here */}
        <div className="fixed inset-0 scanlines z-[100] opacity-10 mix-blend-overlay pointer-events-none" />
        <Header />
        <Breadcrumbs className="mx-auto max-w-6xl px-4 pt-3" />
        <main className="flex-1">
          <PageTransition>{children}</PageTransition>
        </main>
        <KeyboardShortcutsOverlay />
        <CommandPalette />
      </div>
    </AuthErrorBoundary>
  );
}
