"use client";

import { useEffect, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/stores/useAuthStore";
import { getToken } from "@/lib/auth";

/**
 * Thin wrapper over useAuthStore for backward compatibility.
 * All state lives in Zustand; this hook adds router-based redirects.
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
