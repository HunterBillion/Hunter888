import { create } from "zustand";
import { api } from "@/lib/api";
import { clearTokens, getToken } from "@/lib/auth";
import { resetConsentCache } from "@/components/layout/AuthLayout";
import type { User } from "@/types";

const ACCENT_CLASSES = ["accent-blue", "accent-emerald", "accent-amber", "accent-rose"];

/**
 * Single source of truth for UI preferences.
 * localStorage is ONLY used for preventing flash on initial load.
 * Store state always wins over localStorage.
 */
function applyUIPreferences(prefs: Record<string, unknown> | null | undefined) {
  if (typeof window === "undefined") return;
  if (!prefs) return;

  const html = document.documentElement;
  const body = document.body;

  const accent = (prefs.accent_color as string) || "violet";
  ACCENT_CLASSES.forEach((c) => html.classList.remove(c));
  if (accent !== "violet") {
    html.classList.add(`accent-${accent}`);
  }
  try { localStorage.setItem("vh-accent", accent); } catch {}

  const compact = prefs.compact_mode === true;
  body.classList.toggle("compact-mode", compact);
  try { localStorage.setItem("vh-compact", compact ? "1" : "0"); } catch {}
}

/** Apply from localStorage ONLY on first load (prevents flash before API responds) */
function applyFromLocalStorage() {
  if (typeof window === "undefined") return;
  try {
    const accent = localStorage.getItem("vh-accent");
    if (accent && accent !== "violet") {
      document.documentElement.classList.add(`accent-${accent}`);
    }
    const compact = localStorage.getItem("vh-compact");
    if (compact === "1") {
      document.body.classList.add("compact-mode");
    }
  } catch {}
}

applyFromLocalStorage();

interface AuthState {
  user: User | null;
  loading: boolean;
  _fetchPromise: Promise<User | null> | null;
  _fetchTs: number;
  /** Monotonic counter — increments on every preference change to prevent stale overwrites */
  _prefsVersion: number;

  fetchUser: () => Promise<User | null>;
  invalidate: () => void;
  updatePreferences: (prefs: Record<string, unknown>) => void;
  logout: () => Promise<void>;
  setUser: (user: User | null) => void;
}

const CACHE_TTL = 30_000;

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  loading: true,
  _fetchPromise: null,
  _fetchTs: 0,
  _prefsVersion: 0,

  fetchUser: async () => {
    const state = get();
    const now = Date.now();

    // Return in-flight promise (dedup)
    if (state._fetchPromise && now - state._fetchTs < CACHE_TTL) {
      return state._fetchPromise;
    }
    // Return cached user
    if (state.user && now - state._fetchTs < CACHE_TTL) {
      set({ loading: false });
      return state.user;
    }

    const token = getToken();
    if (!token) {
      set({ user: null, loading: false });
      return null;
    }

    const versionBefore = state._prefsVersion;

    const promise = api.get("/auth/me").then((u: User) => {
      // Only apply server preferences if no local update happened during fetch
      // This prevents the race: save prefs → fetch returns old data → overwrites
      const current = get();
      if (current._prefsVersion === versionBefore) {
        applyUIPreferences(u.preferences as Record<string, unknown> | null);
        set({ user: u, loading: false, _fetchPromise: null });
      } else {
        // Local prefs were updated while fetch was in flight — keep local, update user object only
        const mergedUser = { ...u, preferences: current.user?.preferences ?? u.preferences };
        set({ user: mergedUser, loading: false, _fetchPromise: null });
      }
      return get().user;
    }).catch(() => {
      set({ user: null, loading: false, _fetchPromise: null });
      return null;
    });

    set({ _fetchPromise: promise, _fetchTs: now, loading: true });
    return promise;
  },

  invalidate: () => {
    set({ _fetchPromise: null, _fetchTs: 0 });
  },

  updatePreferences: (prefs) => {
    const user = get().user;
    if (!user) return;
    const merged = { ...((user.preferences as Record<string, unknown>) || {}), ...prefs };
    // Increment version to guard against concurrent fetchUser overwriting
    set({
      user: { ...user, preferences: merged },
      _fetchTs: Date.now(), // Mark as "fresh" — no need to refetch immediately
      _prefsVersion: get()._prefsVersion + 1,
    });
    applyUIPreferences(merged);
  },

  logout: async () => {
    try { await api.post("/auth/logout", {}); } catch {}
    set({ user: null, loading: false, _fetchPromise: null, _fetchTs: 0, _prefsVersion: 0 });
    clearTokens();
    resetConsentCache();
    try {
      localStorage.removeItem("vh-accent");
      localStorage.removeItem("vh-compact");
    } catch {}
    ACCENT_CLASSES.forEach((c) => document.documentElement.classList.remove(c));
    document.body.classList.remove("compact-mode");
  },

  setUser: (user) => set({ user }),
}));
