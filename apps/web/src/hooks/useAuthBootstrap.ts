"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { getToken, getRefreshToken, setTokens } from "@/lib/auth";
import { getApiBaseUrl } from "@/lib/public-origin";
import { logger } from "@/lib/logger";

type AuthState = "loading" | "ready" | "redirecting";

function hasAuthMarkerCookie(): boolean {
  if (typeof document === "undefined") return false;
  return document.cookie.includes("vh_authenticated=");
}

/**
 * Auth bootstrap for fullscreen pages (training/[id], pvp/duel, pvp/quiz, etc.)
 * that are intentionally NOT wrapped in AuthLayout (to avoid Header/chrome).
 *
 * Handles the same auth flow as AuthLayout's boot():
 * 1. Check in-memory token
 * 2. If missing but cookie marker exists → try POST /auth/refresh
 * 3. If still no token → redirect to /login
 *
 * Returns { ready: true } when safe to proceed, { ready: false } while booting
 * or redirecting. Usage:
 *
 *   const { ready } = useAuthBootstrap();
 *   if (!ready) return <Loader />;
 */
export function useAuthBootstrap() {
  const router = useRouter();
  const [state, setState] = useState<AuthState>("loading");
  const didRun = useRef(false);

  useEffect(() => {
    if (didRun.current) return;
    didRun.current = true;

    const boot = async () => {
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
        } catch (err) {
          logger.warn("[useAuthBootstrap] refresh failed:", err);
        }
      }

      if (!token) {
        setState("redirecting");
        router.replace("/login");
        return;
      }

      setState("ready");
    };

    boot();
  }, [router]);

  return { ready: state === "ready", state };
}
