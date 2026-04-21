"use client";

import { Loader2 } from "lucide-react";
import { useAuthBootstrap } from "@/hooks/useAuthBootstrap";

/**
 * Lightweight auth gate for fullscreen pages that intentionally don't use
 * AuthLayout (to avoid Header/chrome on gameplay screens: training session,
 * PvP duel, PvP arena, rapid-fire, gauntlet, team battle, quiz).
 *
 * Ensures the token is valid (runs refresh via cookie if needed) before
 * rendering children. Redirects to /login if unauthenticated.
 *
 * Does NOT check consent — consent guard is skipped for gameplay screens
 * because if the user is in an active match/session they've already passed
 * consent earlier in the flow.
 */
export function PageAuthGate({ children }: { children: React.ReactNode }) {
  const { ready } = useAuthBootstrap();

  if (!ready) {
    return (
      <div className="flex h-screen items-center justify-center" style={{ background: "var(--bg-primary)" }}>
        <Loader2 size={28} className="animate-spin" style={{ color: "var(--accent)" }} />
      </div>
    );
  }

  return <>{children}</>;
}
