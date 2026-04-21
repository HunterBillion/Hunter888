import { create } from "zustand";
import { api } from "@/lib/api";
import { useNotificationStore } from "@/stores/useNotificationStore";

interface CompositeScores {
  confidence: number;
  stress_resistance: number;
  adaptability: number;
  empathy: number;
}

interface OceanTraits {
  openness: number;
  conscientiousness: number;
  extraversion: number;
  agreeableness: number;
  neuroticism: number;
}

interface BehaviorProfile {
  user_id: string;
  composite_scores: CompositeScores;
  ocean: OceanTraits;
  performance_by_emotion: {
    under_hostility: number | null;
    under_stress: number | null;
    with_empathy: number | null;
  };
  archetype_scores: Record<string, number>;
  sessions_analyzed: number;
  recent_snapshots: {
    session_id: string;
    session_type: string;
    confidence: number;
    stress: number;
    adaptability: number;
    messages: number;
    created_at: string | null;
  }[];
}

interface TrendEntry {
  period_start: string | null;
  period_end: string | null;
  direction: "improving" | "stable" | "declining" | "stagnating";
  score_delta: number;
  skill_trends: Record<string, { direction: string; delta: number }> | null;
  alert_severity: "info" | "warning" | "critical" | null;
  alert_message: string | null;
  sessions_count: number;
  predicted_score_7d: number | null;
}

interface DailyAdvice {
  id: string;
  title: string;
  body: string;
  category: string;
  priority: number;
  action_type: string | null;
  action_data: Record<string, unknown> | null;
  source_analysis: Record<string, unknown> | null;
  date: string | null;
}

interface TeamAlert {
  user_id: string;
  direction: string;
  severity: string | null;
  message: string | null;
  score_delta: number;
  sessions_count: number;
  period_end: string | null;
  seen: boolean;
}

interface BehaviorState {
  profile: BehaviorProfile | null;
  profileLoading: boolean;

  trends: TrendEntry[];
  trendsLoading: boolean;

  dailyAdvice: DailyAdvice | null;
  adviceLoading: boolean;

  teamAlerts: TeamAlert[];
  alertsLoading: boolean;

  fetchProfile: (userId?: string) => Promise<void>;
  fetchTrends: (userId?: string, limit?: number) => Promise<void>;
  fetchDailyAdvice: () => Promise<void>;
  markAdviceActed: (adviceId: string) => Promise<void>;
  fetchTeamAlerts: (unseenOnly?: boolean) => Promise<void>;
  markAlertSeen: (alertId: string) => Promise<void>;
}

export const useBehaviorStore = create<BehaviorState>((set) => ({
  profile: null,
  profileLoading: false,
  trends: [],
  trendsLoading: false,
  dailyAdvice: null,
  adviceLoading: false,
  teamAlerts: [],
  alertsLoading: false,

  fetchProfile: async (userId?: string) => {
    set({ profileLoading: true });
    try {
      const params = userId ? `?user_id=${userId}` : "";
      const data = await api.get(`/behavior/profile${params}`);
      set({ profile: data, profileLoading: false });
    } catch {
      set({ profileLoading: false });
    }
  },

  fetchTrends: async (userId?: string, limit = 12) => {
    set({ trendsLoading: true });
    try {
      const params = new URLSearchParams({ limit: String(limit) });
      if (userId) params.set("user_id", userId);
      const data = await api.get(`/behavior/trends?${params}`);
      set({ trends: data.trends || [], trendsLoading: false });
    } catch {
      set({ trendsLoading: false });
    }
  },

  fetchDailyAdvice: async () => {
    set({ adviceLoading: true });
    try {
      const data = await api.get("/behavior/daily-advice");
      set({ dailyAdvice: data.advice || null, adviceLoading: false });
    } catch {
      set({ adviceLoading: false });
    }
  },

  markAdviceActed: async (adviceId: string) => {
    try {
      await api.post(`/behavior/daily-advice/${adviceId}/acted`, {});
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Не удалось сохранить отметку";
      useNotificationStore.getState().addToast({
        title: "Не сохранено",
        body: msg,
        type: "error",
      });
    }
  },

  fetchTeamAlerts: async (unseenOnly = true) => {
    set({ alertsLoading: true });
    try {
      const data = await api.get(
        `/behavior/team-alerts?unseen_only=${unseenOnly}`,
      );
      set({ teamAlerts: data.alerts || [], alertsLoading: false });
    } catch {
      set({ alertsLoading: false });
    }
  },

  markAlertSeen: async (alertId: string) => {
    try {
      await api.post(`/behavior/team-alerts/${alertId}/seen`, {});
      set((state) => ({
        teamAlerts: state.teamAlerts.map((a) =>
          a.user_id === alertId ? { ...a, seen: true } : a,
        ),
      }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Не удалось отметить прочитанным";
      useNotificationStore.getState().addToast({
        title: "Не сохранено",
        body: msg,
        type: "error",
      });
    }
  },
}));
