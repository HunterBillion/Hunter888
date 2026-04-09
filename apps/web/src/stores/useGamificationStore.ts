import { create } from "zustand";
import { api } from "@/lib/api";
import type { Achievement } from "@/types";

/** Dispatched on window when gamification milestones are reached */
export type GamificationEvent =
  | { type: "xp-gain"; amount: number }
  | { type: "level-up"; newLevel: number }
  | { type: "streak-milestone"; days: number };

function emitGamificationEvent(event: GamificationEvent) {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent("gamification", { detail: event }));
  }
}

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
      const prev = get();
      const newLevel = typeof data.level === "number" ? data.level : 1;
      const newTotalXP = typeof data.total_xp === "number" ? data.total_xp : 0;
      const newStreak = typeof data.streak_days === "number" ? data.streak_days : 0;

      set({
        level: newLevel,
        currentXP: typeof data.xp_current_level === "number" ? data.xp_current_level : 0,
        nextLevelXP: typeof data.xp_next_level === "number" ? data.xp_next_level : 100,
        totalXP: newTotalXP,
        streak: newStreak,
        achievements: Array.isArray(data.achievements) ? (data.achievements as Achievement[]) : [],
        loading: false,
        _fetchTs: Date.now(),
      });

      // Emit celebration events
      if (prev._fetchTs > 0) {
        if (newLevel > prev.level) {
          emitGamificationEvent({ type: "level-up", newLevel });
        }
        if (newTotalXP > prev.totalXP) {
          emitGamificationEvent({ type: "xp-gain", amount: newTotalXP - prev.totalXP });
        }
        if (newStreak > prev.streak && [7, 14, 30, 60, 100].includes(newStreak)) {
          emitGamificationEvent({ type: "streak-milestone", days: newStreak });
        }
      }
    } catch (e) {
      set({ loading: false, error: (e as Error).message });
    }
  },

  invalidate: () => set({ _fetchTs: 0 }),
}));
