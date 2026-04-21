"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { motion } from "framer-motion";
import { Loader2, AlertCircle, CheckCircle } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { api, resetAuthCircuitBreaker } from "@/lib/api";
import { setTokens } from "@/lib/auth";
import { useAuthStore } from "@/stores/useAuthStore";

function OAuthCallbackContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [errorMsg, setErrorMsg] = useState("");

  useEffect(() => {
    const code = searchParams.get("code");
    const state = searchParams.get("state");

    if (!code) {
      setStatus("error");
      setErrorMsg("Код авторизации не получен");
      return;
    }

    // Determine provider from state (format: "google:xxx" or "yandex:xxx")
    const provider = state?.split(":")[0] || "google";

    if (provider !== "google" && provider !== "yandex") {
      setStatus("error");
      setErrorMsg("Неизвестный провайдер OAuth");
      return;
    }

    api
      .post(`/auth/${provider}/callback`, { code, state })
      .then(async (data: { access_token: string; refresh_token: string; csrf_token?: string; must_change_password?: boolean }) => {
        setTokens(data.access_token, data.refresh_token, data.csrf_token);
        resetAuthCircuitBreaker();
        // Invalidate auth store so /home fetches fresh user with correct preferences
        useAuthStore.getState().invalidate();
        setStatus("success");

        let target = "/home";
        if (data.must_change_password) {
          target = "/change-password";
        } else {
          try {
            const consentStatus = await api.get<{ all_accepted: boolean }>("/consent/status");
            if (!consentStatus.all_accepted) target = "/consent";
          } catch { /* proceed to /home — AuthLayout will guard */ }
        }
        setTimeout(() => router.replace(target), 800);
      })
      .catch((err: unknown) => {
        setStatus("error");
        setErrorMsg(err instanceof Error ? err.message : "Ошибка авторизации");
      });
  }, [searchParams, router]);

  return (
    <div className="flex min-h-screen items-center justify-center" style={{ background: "var(--bg-primary)" }}>
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="glass-panel p-8 text-center max-w-sm"
      >
        {status === "loading" && (
          <>
            <Loader2 size={32} className="mx-auto animate-spin" style={{ color: "var(--accent)" }} />
            <p className="mt-4 font-mono text-sm" style={{ color: "var(--text-muted)" }}>
              АВТОРИЗАЦИЯ...
            </p>
          </>
        )}

        {status === "success" && (
          <>
            <CheckCircle size={32} className="mx-auto" style={{ color: "var(--success)" }} />
            <p className="mt-4 font-display text-lg font-bold" style={{ color: "var(--text-primary)" }}>
              Вход выполнен!
            </p>
            <p className="mt-1 text-sm" style={{ color: "var(--text-muted)" }}>
              Перенаправление...
            </p>
          </>
        )}

        {status === "error" && (
          <>
            <AlertCircle size={32} className="mx-auto" style={{ color: "var(--danger)" }} />
            <p className="mt-4 font-display text-lg font-bold" style={{ color: "var(--text-primary)" }}>
              Ошибка входа
            </p>
            <p className="mt-2 text-sm" style={{ color: "var(--text-secondary)" }}>
              {errorMsg}
            </p>
            <Button onClick={() => router.replace("/login")} className="mt-6">
              Вернуться к входу
            </Button>
          </>
        )}
      </motion.div>
    </div>
  );
}

export default function OAuthCallbackPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center" style={{ background: "var(--bg-primary)" }}>
          <Loader2 size={32} className="animate-spin" style={{ color: "var(--accent)" }} />
        </div>
      }
    >
      <OAuthCallbackContent />
    </Suspense>
  );
}
