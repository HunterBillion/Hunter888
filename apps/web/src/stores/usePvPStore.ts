import { create } from "zustand";
import { api } from "@/lib/api";
import type { PvPRating, PvPDuel, DuelBrief, PvPLeaderboardEntry, PvPSeason } from "@/types";

type QueueStatus = "idle" | "searching" | "matched" | "in_duel";

interface PvPMessage {
  id: string;
  sender_role: "seller" | "client";
  text: string;
  round: number;
  timestamp: string;
}

interface JudgeScore {
  selling_score: number;
  acting_score: number;
  legal_accuracy: number;
}

interface DuelResult {
  duel_id: string;
  player1_total: number;
  player2_total: number;
  winner_id: string | null;
  is_draw: boolean;
  is_pve: boolean;
  rating_change_applied: boolean;
  player1_rating_delta: number;
  player2_rating_delta: number;
  summary: string;
}

interface PvPState {
  // Rating
  rating: PvPRating | null;
  ratingLoading: boolean;

  // Queue
  queueStatus: QueueStatus;
  queuePosition: number;
  estimatedWait: number;
  pvEOffer: string | null;
  matchedOpponentRating: number | null;

  // Duel
  currentDuel: PvPDuel | null;
  duelBrief: DuelBrief | null;
  myRole: "seller" | "client" | null;
  roundNumber: number;
  timeRemaining: number;
  messages: PvPMessage[];
  judgeScore: JudgeScore | null;
  duelResult: DuelResult | null;

  // History
  myDuels: PvPDuel[];
  duelsLoading: boolean;

  // Season
  activeSeason: PvPSeason | null;

  // Leaderboard
  leaderboard: PvPLeaderboardEntry[];
  leaderboardTotal: number;
  leaderboardLoading: boolean;

  // Actions
  fetchRating: () => Promise<void>;
  fetchMyDuels: () => Promise<void>;
  fetchLeaderboard: (tier?: string, limit?: number) => Promise<void>;
  fetchActiveSeason: () => Promise<void>;
  setQueueStatus: (status: QueueStatus) => void;
  setQueuePosition: (pos: number, est: number) => void;
  setMatchedOpponentRating: (rating: number | null) => void;
  resetQueue: () => void;
  setPvEOffer: (msg: string | null) => void;
  setDuelBrief: (brief: DuelBrief) => void;
  setMyRole: (role: "seller" | "client") => void;
  setRoundNumber: (n: number) => void;
  setTimeRemaining: (t: number) => void;
  addMessage: (msg: PvPMessage) => void;
  replaceMessages: (messages: PvPMessage[]) => void;
  setJudgeScore: (score: JudgeScore) => void;
  setDuelResult: (result: DuelResult) => void;
  resetDuel: () => void;
  _msgCounter: number;
  nextMsgId: () => string;
}

export const usePvPStore = create<PvPState>((set, get) => ({
  rating: null,
  ratingLoading: false,
  queueStatus: "idle",
  queuePosition: 0,
  estimatedWait: 0,
  pvEOffer: null,
  matchedOpponentRating: null,
  currentDuel: null,
  duelBrief: null,
  myRole: null,
  roundNumber: 0,
  timeRemaining: 600,
  messages: [],
  judgeScore: null,
  duelResult: null,
  myDuels: [],
  duelsLoading: false,
  activeSeason: null,
  leaderboard: [],
  leaderboardTotal: 0,
  leaderboardLoading: false,
  _msgCounter: 0,

  fetchRating: async () => {
    set({ ratingLoading: true });
    try {
      const data = await api.get("/pvp/rating/me");
      set({ rating: data, ratingLoading: false });
    } catch {
      set({ ratingLoading: false });
    }
  },

  fetchMyDuels: async () => {
    set({ duelsLoading: true });
    try {
      const data = await api.get("/pvp/duels/me?limit=20");
      set({ myDuels: Array.isArray(data) ? data : [], duelsLoading: false });
    } catch {
      set({ duelsLoading: false });
    }
  },

  fetchLeaderboard: async (tier, limit = 50) => {
    set({ leaderboardLoading: true });
    try {
      const params = new URLSearchParams({ limit: String(limit) });
      if (tier && tier !== "all") params.set("tier", tier);
      const data = await api.get(`/pvp/leaderboard?${params}`);
      set({
        leaderboard: data.entries || [],
        leaderboardTotal: data.total_players || 0,
        leaderboardLoading: false,
      });
    } catch {
      set({ leaderboardLoading: false });
    }
  },

  fetchActiveSeason: async () => {
    try {
      const data = await api.get("/pvp/season/active");
      set({ activeSeason: data || null });
    } catch {}
  },

  setQueueStatus: (queueStatus) => set({ queueStatus }),
  setQueuePosition: (queuePosition, estimatedWait) => set({ queuePosition, estimatedWait }),
  setMatchedOpponentRating: (matchedOpponentRating) => set({ matchedOpponentRating }),
  resetQueue: () => set({
    queueStatus: "idle",
    queuePosition: 0,
    estimatedWait: 0,
    pvEOffer: null,
    matchedOpponentRating: null,
  }),
  setPvEOffer: (pvEOffer) => set({ pvEOffer }),
  setDuelBrief: (duelBrief) => set({ duelBrief, queueStatus: "in_duel" }),
  setMyRole: (myRole) => set({ myRole }),
  setRoundNumber: (roundNumber) => set({ roundNumber }),
  setTimeRemaining: (timeRemaining) => set({ timeRemaining }),
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  replaceMessages: (messages) => set({ messages }),
  setJudgeScore: (judgeScore) => set({ judgeScore }),
  setDuelResult: (duelResult) => set({ duelResult }),
  resetDuel: () => set({
    queueStatus: "idle",
    queuePosition: 0,
    estimatedWait: 0,
    pvEOffer: null,
    matchedOpponentRating: null,
    currentDuel: null,
    duelBrief: null,
    myRole: null,
    roundNumber: 0,
    timeRemaining: 600,
    messages: [],
    judgeScore: null,
    duelResult: null,
  }),
  nextMsgId: () => {
    const c = get()._msgCounter + 1;
    set({ _msgCounter: c });
    return `pvp-${c}`;
  },
}));
