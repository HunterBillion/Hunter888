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
      const data = await api.get("/gamification/me/progress");
      set({
        level: data.level ?? 1,
        currentXP: data.xp_current_level ?? 0,
        nextLevelXP: data.xp_next_level ?? 100,
        totalXP: data.total_xp ?? 0,
        streak: data.streak_days ?? 0,
        achievements: data.achievements ?? [],
        loading: false,
        _fetchTs: Date.now(),
      });
    } catch (e) {
      set({ loading: false, error: (e as Error).message });
    }
  },

  invalidate: () => set({ _fetchTs: 0 }),
}));
