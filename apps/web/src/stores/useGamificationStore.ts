import { create } from "zustand";
import { api } from "@/lib/api";
import type { Achievement } from "@/types";

interface GamificationState {
  level: number;
  currentXP: number;
  nextLevelXP: number;
  totalXP: number;
  streak: number;
  achievements: Achievement[];
  loading: boolean;
  error: string | null;
  _fetchTs: number;

  fetchProgress: () => Promise<void>;
  invalidate: () => void;
}

const CACHE_TTL = 60_000; // 1 min

export const useGamificationStore = create<GamificationState>((set, get) => ({
  level: 1,
  currentXP: 0,
  nextLevelXP: 100,
  totalXP: 0,
  streak: 0,
  achievements: [],
  loading: false,
  error: null,
  _fetchTs: 0,

  fetchProgress: async () => {
    const now = Date.now();
    if (now - get()._fetchTs < CACHE_TTL) return;

    set({ loading: true, error: null });
    try {
      const raw = await api.get("/gamification/me/progress");
      // Validate response is an object before destructuring (#11)
      if (!raw || typeof raw !== "object") {
        set({ loading: false, _fetchTs: Date.now() });
        return;
      }
      const data = raw as Record<string, unknown>;
      set({
        level: typeof data.level === "number" ? data.level : 1,
        currentXP: typeof data.xp_current_level === "number" ? data.xp_current_level : 0,
        nextLevelXP: typeof data.xp_next_level === "number" ? data.xp_next_level : 100,
        totalXP: typeof data.total_xp === "number" ? data.total_xp : 0,
        streak: typeof data.streak_days === "number" ? data.streak_days : 0,
        achievements: Array.isArray(data.achievements) ? (data.achievements as Achievement[]) : [],
        loading: false,
        _fetchTs: Date.now(),
      });
    } catch (e) {
      set({ loading: false, error: (e as Error).message });
    }
  },

  invalidate: () => set({ _fetchTs: 0 }),
}));
