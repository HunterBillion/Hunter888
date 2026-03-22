"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { motion } from "framer-motion";
import { Loader2, AlertCircle, CheckCircle } from "lucide-react";
import { api } from "@/lib/api";
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
      .then((data: { access_token: string; refresh_token: string }) => {
        setTokens(data.access_token, data.refresh_token);
        // Invalidate auth store so /home fetches fresh user with correct preferences
        useAuthStore.getState().invalidate();
        setStatus("success");
        setTimeout(() => router.replace("/home"), 800);
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
            <CheckCircle size={32} className="mx-auto" style={{ color: "var(--neon-green, #00FF66)" }} />
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
            <AlertCircle size={32} className="mx-auto" style={{ color: "var(--neon-red, #FF3333)" }} />
            <p className="mt-4 font-display text-lg font-bold" style={{ color: "var(--text-primary)" }}>
              Ошибка входа
            </p>
            <p className="mt-2 text-sm" style={{ color: "var(--text-secondary)" }}>
              {errorMsg}
            </p>
            <motion.button
              onClick={() => router.replace("/login")}
              className="vh-btn-primary mt-6"
              whileTap={{ scale: 0.97 }}
            >
              Вернуться к входу
            </motion.button>
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
