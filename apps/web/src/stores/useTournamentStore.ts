import { create } from "zustand";
import { api } from "@/lib/api";

export interface TournamentLeaderboardEntry {
  rank: number;
  user_id: string;
  full_name: string;
  avatar_url?: string;
  best_score: number;
  attempts: number;
  is_podium: boolean;
}

export interface TournamentData {
  id: string;
  title: string;
  description?: string;
  format?: "leaderboard" | "bracket";
  week_start: string;
  week_end: string;
  is_active: boolean;
  max_attempts: number;
  bonus_xp_first: number;
  bonus_xp_second: number;
  bonus_xp_third: number;
  registration_end?: string | null;
  current_round?: number;
  bracket_size?: number | null;
}

export interface BracketMatchData {
  id: string;
  match_index: number;
  player1_id: string | null;
  player2_id: string | null;
  player1_name: string;
  player2_name: string;
  winner_id: string | null;
  player1_score: number | null;
  player2_score: number | null;
  status: "pending" | "active" | "completed" | "bye";
  duel_id: string | null;
}

export interface BracketData {
  tournament_id: string;
  title: string;
  format: string;
  bracket_size: number;
  total_rounds: number;
  current_round: number;
  is_active: boolean;
  participants: {
    user_id: string;
    seed: number | null;
    full_name: string;
    rating_snapshot: number;
    eliminated_at_round: number | null;
    final_placement: number | null;
  }[];
  rounds: Record<string, BracketMatchData[]>;
}

interface TournamentState {
  // Data
  tournament: TournamentData | null;
  leaderboard: TournamentLeaderboardEntry[];
  bracket: BracketData | null;
  userBestScore: number | null;
  userAttempts: number;
  loading: boolean;
  error: string | null;

  // Actions
  fetchActive: () => Promise<void>;
  fetchLeaderboard: (tournamentId: string) => Promise<void>;
  fetchBracket: (tournamentId: string) => Promise<void>;
  registerForBracket: (tournamentId: string) => Promise<boolean>;
  reset: () => void;
}

export const useTournamentStore = create<TournamentState>((set) => ({
  tournament: null,
  leaderboard: [],
  bracket: null,
  userBestScore: null,
  userAttempts: 0,
  loading: false,
  error: null,

  fetchActive: async () => {
    set({ loading: true, error: null });
    try {
      const data = await api.get("/tournament/active") as {
        tournament: TournamentData | null;
        leaderboard: TournamentLeaderboardEntry[];
      };
      set({
        tournament: data.tournament,
        leaderboard: data.leaderboard || [],
        loading: false,
      });
    } catch {
      set({ loading: false, error: "Не удалось загрузить турнир" });
    }
  },

  fetchLeaderboard: async (tournamentId: string) => {
    try {
      const data = await api.get(`/tournament/leaderboard/${tournamentId}`) as TournamentLeaderboardEntry[];
      set({ leaderboard: data });
    } catch {
      // silent
    }
  },

  fetchBracket: async (tournamentId: string) => {
    set({ loading: true, error: null });
    try {
      const data = await api.get(`/tournament/bracket/${tournamentId}`) as BracketData;
      set({ bracket: data, loading: false });
    } catch {
      set({ loading: false, error: "Не удалось загрузить сетку турнира" });
    }
  },

  registerForBracket: async (tournamentId: string) => {
    try {
      await api.post(`/tournament/bracket/${tournamentId}/register`, {});
      return true;
    } catch {
      return false;
    }
  },

  reset: () => set({
    tournament: null,
    leaderboard: [],
    bracket: null,
    userBestScore: null,
    userAttempts: 0,
    loading: false,
    error: null,
  }),
}));
