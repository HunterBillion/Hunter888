"use client";

import { useEffect, useState, useRef, Component, type ReactNode, type ErrorInfo } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { logger } from "@/lib/logger";
import { Loader2, RefreshCw, AlertTriangle } from "lucide-react";
import { getToken, getRefreshToken, setTokens } from "@/lib/auth";
import { api } from "@/lib/api";
import { getApiBaseUrl } from "@/lib/public-origin";
import Header from "./Header";
// 2026-04-20: Breadcrumbs вернулись — но теперь авто-генератор по
// pathname, а не ручной компонент. Рендерится только на вложенных
// страницах (/training/[id], /pvp/duel/[id], /admin/audit-log, ...),
// на корневых (/home, /pvp) ничего не добавляет.
import { AutoBreadcrumbs } from "./AutoBreadcrumbs";
import { KeyboardShortcutsOverlay } from "@/components/ui/KeyboardShortcutsOverlay";
import { CommandPalette } from "@/components/ui/CommandPalette";
import { PlanLimitModal } from "@/components/billing/PlanLimitModal";
import { ScreenShakeProvider } from "@/components/ui/ScreenShake";
import { LLMDegradationBanner } from "@/components/ui/LLMDegradationBanner";
import { CelebrationListener } from "@/components/gamification/CelebrationListener";
import dynamic from "next/dynamic";

const PixelGridBackground = dynamic(
  () => import("@/components/pixel/PixelGridBackground").then((m) => m.PixelGridBackground),
  { ssr: false },
);

/** Check if vh_authenticated marker cookie exists (survives page reload). */
function hasAuthMarkerCookie(): boolean {
  if (typeof document === "undefined") return false;
  return document.cookie.includes("vh_authenticated=");
}

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
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full mb-4" style={{ background: "var(--danger-muted)" }}>
              <AlertTriangle size={24} />
            </div>
            <h2 className="font-display text-lg font-bold mb-2" style={{ color: "var(--text-primary)" }}>
              Что-то пошло не так
            </h2>
            <p className="text-sm mb-4" style={{ color: "var(--text-muted)" }}>
              {this.state.error?.message || "Произошла непредвиденная ошибка"}
            </p>
            <button
              type="button"
              onClick={() => {
                // 2026-05-03: don't full-reload — just clear the boundary
                // and let React re-render. Full reload kills auth bootstrap
                // + WS reconnect for what is often a transient component
                // error.
                this.setState({ hasError: false, error: null });
              }}
              className="inline-flex items-center justify-center gap-2 font-bold tracking-wide uppercase rounded-xl px-5 py-2.5 text-sm transition-all duration-200 mx-auto" style={{ background: "var(--glass-bg)", color: "var(--text-primary)", border: "1px solid var(--accent)" }}
            >
              <RefreshCw size={14} />
              Попробовать снова
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
  // Always start with "loading" on both server and client — using typeof window
  // in a useState initializer causes SSR/client hydration mismatch because the
  // server never has window. The useEffect boot below handles all auth logic.
  const [state, setState] = useState<"loading" | "ready" | "redirecting" | "error">("loading");
  const [errorMessage, setErrorMessage] = useState("");
  const retryCount = useRef(0);
  const didRun = useRef(false);

  // Animated background toggle (localStorage, dark-mode only on platform)
  const [showAnimBg, setShowAnimBg] = useState(false);
  useEffect(() => {
    try {
      const disabled = localStorage.getItem("vh-animated-bg") === "0";
      const isDark = document.documentElement.classList.contains("dark");
      setShowAnimBg(!disabled && isDark);
    } catch {}
    const obs = new MutationObserver(() => {
      const isDark = document.documentElement.classList.contains("dark");
      const disabled = localStorage.getItem("vh-animated-bg") === "0";
      setShowAnimBg(!disabled && isDark);
    });
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);

  useEffect(() => {
    if (didRun.current) return;
    didRun.current = true;

    const boot = async () => {
      let token = getToken();

      // After full-page reload the in-memory token is gone, but httpOnly
      // refresh_token cookie may still be valid. Try to restore the session
      // before giving up and redirecting to /login.
      if (!token && hasAuthMarkerCookie()) {
        try {
          const storedRefreshToken = getRefreshToken();
          const res = await fetch(`${getApiBaseUrl()}/api/auth/refresh`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(storedRefreshToken ? { refresh_token: storedRefreshToken } : {}),
            credentials: "include",
          });
          if (res.ok) {
            const data = await res.json();
            if (data.access_token) {
              setTokens(data.access_token, data.refresh_token, data.csrf_token);
              token = data.access_token;
            }
          }
        } catch {
          // Refresh failed — will redirect to login below
        }
      }

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

      try {
        const data = await api.get("/consent/status");
        _consentChecked = true;
        _consentOk = data.all_accepted;
        if (data.all_accepted) {
          setState("ready");
        } else {
          setState("redirecting");
          router.replace("/consent");
        }
      } catch (err: unknown) {
        logger.error("[AuthLayout] consent error:", err);
        _consentChecked = false;
        _consentOk = false;
        setState("error");
        setErrorMessage(err instanceof Error ? err.message : "Не удалось проверить статус согласия");
      }
    };

    boot();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps -- mount-only initialization; boot fn is intentionally excluded

  if (state === "error") {
    return (
      <div className="flex min-h-screen items-center justify-center" style={{ background: "var(--bg-primary)" }}>
        <div className="glass-panel max-w-md px-8 py-6 text-center">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full mb-4" style={{ background: "var(--danger-muted)" }}>
            <AlertTriangle size={24} />
          </div>
          <h2 className="font-display text-lg font-bold mb-2" style={{ color: "var(--text-primary)" }}>
            Ошибка подключения
          </h2>
          <p className="text-sm mb-4" style={{ color: "var(--text-muted)" }}>
            {errorMessage || "Не удалось подключиться к серверу"}
          </p>
          <button
            onClick={() => {
              const MAX_RETRIES = 5;
              if (retryCount.current >= MAX_RETRIES) {
                setErrorMessage("Слишком много попыток. Перезагрузите страницу.");
                return;
              }
              retryCount.current += 1;
              // Reset state and re-run the full boot flow (including token refresh)
              didRun.current = false;
              _consentChecked = false;
              _consentOk = false;
              setState("loading");
              setErrorMessage("");
              // Exponential backoff: 200ms, 400ms, 800ms, 1600ms, 3200ms
              const delay = Math.min(200 * Math.pow(2, retryCount.current - 1), 5000);
              setTimeout(() => {
                didRun.current = false;
                const fullRetry = async () => {
                  let token = getToken();
                  if (!token && hasAuthMarkerCookie()) {
                    try {
                      const storedRefreshToken = getRefreshToken();
                      const res = await fetch(`${getApiBaseUrl()}/api/auth/refresh`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify(storedRefreshToken ? { refresh_token: storedRefreshToken } : {}),
                        credentials: "include",
                      });
                      if (res.ok) {
                        const data = await res.json();
                        if (data.access_token) {
                          setTokens(data.access_token, data.refresh_token, data.csrf_token);
                          token = data.access_token;
                        }
                      }
                    } catch { /* continue without token */ }
                  }
                  if (!token) { setState("redirecting"); router.replace("/login"); return; }
                  if (!requireConsent) { setState("ready"); retryCount.current = 0; return; }
                  try {
                    const data = await api.get("/consent/status");
                    _consentChecked = true;
                    _consentOk = data.all_accepted;
                    setState(data.all_accepted ? "ready" : "redirecting");
                    if (data.all_accepted) retryCount.current = 0;
                    if (!data.all_accepted) router.replace("/consent");
                  } catch {
                    setState("error");
                    setErrorMessage("Сервер по-прежнему недоступен");
                  }
                };
                fullRetry();
              }, delay);
            }}
            className="inline-flex items-center justify-center gap-2 font-bold tracking-wide uppercase rounded-xl px-5 py-2.5 text-sm transition-all duration-200 mx-auto" style={{ background: "var(--glass-bg)", color: "var(--text-primary)", border: "1px solid var(--accent)" }}
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
          <Loader2
            size={28}
            className="animate-spin"
            style={{ color: "var(--accent)", opacity: 0.6 }}
          />
          <span className="font-mono text-xs" style={{ color: "var(--text-muted)" }}>
            {state === "loading" ? "Загрузка..." : "Перенаправление..."}
          </span>
        </motion.div>
      </div>
    );
  }

  return (
    <AuthErrorBoundary>
      <ScreenShakeProvider>
        {/* Root background — body-level solid color, no stacking context */}
        <div className="flex min-h-screen flex-col" style={{ background: "var(--bg-primary)" }}>

          {/* ── Grid background — static fallback + animated canvas ── */}
          <div className="app-grid-layer" aria-hidden="true" />
          {showAnimBg && <PixelGridBackground variant="platform" />}


          <Header />
          <LLMDegradationBanner />
          <CelebrationListener />
          <main className="flex-1" style={{ position: "relative", zIndex: 1, minHeight: "calc(100vh - 200px)", overflow: "clip" }}>
            <div className="app-page pt-3">
              <AutoBreadcrumbs />
            </div>
            {children}
          </main>
          <KeyboardShortcutsOverlay />
          <CommandPalette />
          <PlanLimitModal />
        </div>
      </ScreenShakeProvider>
    </AuthErrorBoundary>
  );
}
