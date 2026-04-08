"use client";

import { useEffect, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/stores/useAuthStore";
import { getToken, getRefreshToken } from "@/lib/auth";

/**
 * Thin wrapper over useAuthStore for backward compatibility.
 * All state lives in Zustand; this hook adds router-based redirects.
 *
 * IMPORTANT: This hook runs inside AuthLayout children. After a hard
 * navigation the in-memory access token is always null — AuthLayout
 * restores it via refresh before rendering children. We must NOT
 * redirect to /login based solely on getToken() === null; check for
 * marker cookie / sessionStorage refresh token first.
 */
export function useAuth() {
  const router = useRouter();
  const { user, loading, fetchUser, logout: storeLogout } = useAuthStore();
  const didFetchRef = useRef(false);

  useEffect(() => {
    // Guard: only run once per mount to prevent loops from fetchUser reference changes
    if (didFetchRef.current) return;
    didFetchRef.current = true;

    const token = getToken();
    if (!token) {
      // After hard navigation, in-memory token is null but AuthLayout
      // may have just refreshed it (or is about to). If evidence of an
      // active session exists, don't redirect — AuthLayout handles auth.
      const hasMarker =
        typeof document !== "undefined" &&
        document.cookie.includes("vh_authenticated=");
      const hasRefresh = !!getRefreshToken();
      if (hasMarker || hasRefresh) {
        // Session exists — AuthLayout will set the token. Skip redirect.
        // Still try to fetch user once token becomes available.
        return;
      }
      router.replace("/login");
      return;
    }

    // Store handles dedup via TTL cache — safe to call on every mount
    fetchUser().then((u) => {
      if (!u) router.replace("/login");
    });
  }, [fetchUser, router]);

  // Reset guard on unmount so remount works correctly
  useEffect(() => {
    return () => { didFetchRef.current = false; };
  }, []);

  const logout = useCallback(async () => {
    await storeLogout();
    router.replace("/login");
  }, [router, storeLogout]);

  return { user, loading, logout };
}

/** @deprecated Use useAuthStore().invalidate() directly */
export function invalidateUserCache(): void {
  useAuthStore.getState().invalidate();
}
