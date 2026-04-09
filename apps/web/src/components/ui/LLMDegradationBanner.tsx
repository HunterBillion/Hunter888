"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle, X } from "lucide-react";
import { api } from "@/lib/api";

interface LLMStatus {
  status: "ok" | "offline" | "disabled" | "fallback";
  model: string | null;
  fallback: boolean;
  message: string | null;
}

/**
 * Banner shown when Local LLM (Mac Mini / Gemma) is unavailable.
 * Polls /monitoring/llm-status every 30s.
 * Also listens for WS notifications (system.llm_degraded / system.llm_restored).
 */
export function LLMDegradationBanner() {
  const [status, setStatus] = useState<LLMStatus | null>(null);
  const [dismissed, setDismissed] = useState(() => {
    if (typeof sessionStorage !== "undefined") {
      try { return sessionStorage.getItem("llm_banner_dismissed") === "1"; } catch {}
    }
    return false;
  });
  const [restored, setRestored] = useState(false);

  useEffect(() => {
    let mounted = true;
    let timer: ReturnType<typeof setInterval>;

    async function checkStatus() {
      try {
        const data = await api.get<LLMStatus>("/monitoring/llm-status");
        if (mounted) {
          // Detect restoration: was fallback, now ok
          if (status?.fallback && !data.fallback) {
            setRestored(true);
            setTimeout(() => setRestored(false), 5000);
          }
          setStatus(data);
          // Auto-dismiss when restored
          if (!data.fallback) {
            setDismissed(false);
            try { sessionStorage.removeItem("llm_banner_dismissed"); } catch {}
          }
        }
      } catch {
        // API not reachable — don't show banner (might be a network issue)
      }
    }

    checkStatus();
    timer = setInterval(checkStatus, 30_000);

    return () => {
      mounted = false;
      clearInterval(timer);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status?.fallback]);

  // Listen for WS notifications
  useEffect(() => {
    function handleWSMessage(event: CustomEvent<{ type: string }>) {
      const data = event.detail;
      if (data.type === "system.llm_degraded") {
        setStatus(prev => prev ? { ...prev, fallback: true, status: "fallback", message: "AI-сервер временно недоступен." } : null);
        setDismissed(false);
      } else if (data.type === "system.llm_restored") {
        setStatus(prev => prev ? { ...prev, fallback: false, status: "ok", message: null } : null);
        setRestored(true);
        setTimeout(() => setRestored(false), 5000);
      }
    }

    window.addEventListener("llm-status-change" as never, handleWSMessage as never);
    return () => window.removeEventListener("llm-status-change" as never, handleWSMessage as never);
  }, []);

  // Don't show if: no data, ok status, dismissed, or disabled
  if (!status) return null;
  if (status.status === "disabled") return null;

  // Show restoration toast
  if (restored && !status.fallback) {
    return (
      <div className="fixed top-16 left-1/2 -translate-x-1/2 z-50 animate-fade-in">
        <div className="flex items-center gap-2 rounded-lg border border-green-500/30 bg-green-500/10 px-4 py-2 text-sm text-green-400 backdrop-blur-sm">
          <CheckCircle className="h-4 w-4 shrink-0" />
          <span>AI-сервер восстановлен</span>
        </div>
      </div>
    );
  }

  // Don't show degradation banner if dismissed or not in fallback
  if (!status.fallback || dismissed) return null;

  return (
    <div className="relative z-50 border-b border-yellow-500/30 bg-yellow-500/10 px-4 py-2">
      <div className="mx-auto flex max-w-7xl items-center justify-between">
        <div className="flex items-center gap-2 text-sm text-yellow-400">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span>
            AI-сервер перезагружается. Чаты и PvP работают в облачном режиме.
          </span>
        </div>
        <button
          onClick={() => {
            setDismissed(true);
            try { sessionStorage.setItem("llm_banner_dismissed", "1"); } catch {}
          }}
          className="ml-4 rounded p-1 text-yellow-400/60 hover:text-yellow-400 transition-colors"
          aria-label="Закрыть"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
