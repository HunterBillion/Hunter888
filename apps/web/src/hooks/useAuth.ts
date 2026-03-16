"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { clearTokens, getToken } from "@/lib/auth";
import type { User } from "@/types";

export function useAuth() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      setLoading(false);
      router.replace("/login");
      return;
    }

    api
      .get("/auth/me")
      .then(setUser)
      .catch(() => {
        clearTokens();
        router.replace("/login");
      })
      .finally(() => setLoading(false));
  }, [router]);

  const logout = () => {
    clearTokens();
    router.replace("/login");
  };

  return { user, loading, logout };
}
