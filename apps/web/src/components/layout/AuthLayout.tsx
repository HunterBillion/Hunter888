"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getToken } from "@/lib/auth";
import { api } from "@/lib/api";
import Header from "./Header";

interface AuthLayoutProps {
  children: React.ReactNode;
  requireConsent?: boolean;
}

export default function AuthLayout({
  children,
  requireConsent = true,
}: AuthLayoutProps) {
  const router = useRouter();
  const [state, setState] = useState<"loading" | "ready" | "redirecting">(
    "loading",
  );

  useEffect(() => {
    const token = getToken();
    if (!token) {
      setState("redirecting");
      router.replace("/login");
      return;
    }

    if (!requireConsent) {
      setState("ready");
      return;
    }

    // Check consent status
    api
      .get("/consent/status")
      .then((data) => {
        if (data.all_accepted) {
          setState("ready");
        } else {
          setState("redirecting");
          router.replace("/consent");
        }
      })
      .catch(() => {
        // If endpoint not available, allow through
        setState("ready");
      });
  }, [router, requireConsent]);

  if (state === "loading" || state === "redirecting") {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-gray-700 border-t-vh-purple" />
          <span className="text-sm text-gray-500">
            {state === "loading" ? "Проверка авторизации..." : "Перенаправление..."}
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col">
      <Header />
      <main className="flex-1">{children}</main>
    </div>
  );
}
