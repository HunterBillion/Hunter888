import { create } from "zustand";
import { api } from "@/lib/api";
import type { ArenaPlayer, ArenaRoundResult, ArenaFinalResults, ArenaChallenge } from "@/types";

export type QuizMode = "free_dialog" | "blitz" | "themed" | "pvp";
export type QuizStatus = "idle" | "selecting" | "connecting" | "active" | "completed";

export type VerdictLevel = "correct" | "partial" | "off_topic" | "wrong";

export interface QuizMessage {
  id: string;
  type: "question" | "answer" | "feedback" | "system" | "hint" | "follow_up";
  content: string;
  isCorrect?: boolean;
  // 2026-05-04 FRONT-3: 4-bucket verdict for nuanced UI rendering.
  // Falls back to deriving from isCorrect when absent (legacy events).
  verdictLevel?: VerdictLevel;
  llmScore?: number; // 0-10, if backend provided it
  articleRef?: string;
  explanation?: string;
  correctAnswer?: string;   // 2026-04-18: expected answer, shown separately when answer is wrong
  category?: string;
  timestamp: number;
  userId?: string;
  userName?: string;
  // V2 fields
  personalityComment?: string;
  avatarEmoji?: string;
  speedBonus?: number;
}

export interface AIPersonality {
  name: string;
  displayName: string;
  avatarEmoji: string;
  greeting: string;
}

export interface CategoryProgress {
  category: string;
  totalAnswers: number;
  correctAnswers: number;
  masteryPct: number;
}

export interface PvPPlayer {
  userId: string;
  name: string;
  score: number;
  rank?: number;
}

// Block 5: Cross-module recommendation types
export interface ArenaRecommendation {
  category: string;
  accuracy: number;
  recommendation: string;
  priority: "critical" | "high" | "medium";
  suggested_action: string;
}

export interface ArenaLeaderboardEntry {
  user_id: string;
  username: string;
  rank: number;
  rank_tier?: string;
  score?: number;
  avg_score?: number;
  sessions_count?: number;
  wins?: number;
  losses?: number;
  streak?: number;
  rating?: number;
  total_score?: number;
}

export interface ArenaStats {
  overall_accuracy: number;
  total_quizzes: number;
  category_progress: CategoryProgress[];
  pvp_stats: {
    rating: number;
    rank_tier: string;
    wins: number;
    losses: number;
    current_streak: number;
  };
  weak_areas: string[];
  recommendations: ArenaRecommendation[];
}

interface KnowledgeState {
  // Session
  sessionId: string | null;
  mode: QuizMode;
  category: string | null;
  status: QuizStatus;

  // Progress
  currentQuestion: number;
  totalQuestions: number;
  correct: number;
  incorrect: number;
  skipped: number;
  score: number;

  // Chat
  messages: QuizMessage[];
  _msgCounter: number;

  // Timer (blitz)
  timeLeft: number | null;

  // Categories
  categories: CategoryProgress[];

  // PvP
  pvpPlayers: PvPPlayer[];
  challengeId: string | null;
  isSearching: boolean;

  // Input
  input: string;
  isTyping: boolean;

  // Results
  results: Record<string, unknown> | null;

  // V2: AI Personality
  aiPersonality: AIPersonality | null;

  // V2: Streak & adaptive difficulty
  streak: number;
  bestStreak: number;
  currentDifficulty: number;

  // V2: Follow-up
  pendingFollowUp: string | null;

  // PR-MC (2026-05-05): when present, the quiz page renders 3 buttons
  // instead of a textarea, and clicks send `{type:"answer", choice_index}`
  // instead of free text. Cleared on every new question / feedback so a
  // session that mixes formats works correctly.
  currentChoices: string[] | null;
  pickedChoiceIndex: number | null;
  setCurrentChoices(choices: string[] | null): void;
  setPickedChoiceIndex(idx: number | null): void;

  // Block 5: Cross-module stats
  arenaStats: ArenaStats | null;
  arenaStatsLoading: boolean;

  // Arena Leaderboard
  arenaLeaderboard: ArenaLeaderboardEntry[];
  arenaLeaderboardPeriod: "week" | "month" | "all";
  arenaLeaderboardLoading: boolean;
  arenaLeaderboardUserRank: Record<string, unknown> | null;

  // PvP Arena Match state
  pvpMatchId: string | null;
  pvpRound: number;
  pvpTotalRounds: number;
  pvpArenaPlayers: ArenaPlayer[];
  pvpRoundResults: ArenaRoundResult[];
  pvpMyAnswer: string;
  pvpMyAnswerSubmitted: boolean;
  pvpOpponentsAnswered: Record<string, boolean>;
  pvpTimeLeft: number;
  pvpFinalResults: ArenaFinalResults | null;
  pvpContainsBot: boolean;
  pvpCurrentQuestion: string | null;
  pvpCurrentCategory: string | null;
  pvpCurrentDifficulty: number;
  pvpDisconnectedPlayers: string[];
  pvpActiveChallenges: ArenaChallenge[];
  /**
   * 2026-04-19 Phase 2.8: arcade TTS narration for the current round,
   * populated by the `pvp.audio_ready` WS event. Reset on new round start.
   */
  pvpArenaAudioUrl: string | null;
  setPvpArenaAudio(url: string | null): void;

  // Actions
  init(mode: QuizMode, category?: string): void;
  setStatus(status: QuizStatus): void;
  setSessionId(id: string): void;
  nextMsgId(): string;
  addMessage(msg: Omit<QuizMessage, "id" | "timestamp">): void;
  appendToLastMessage(text: string): void;
  /**
   * Update the last feedback message in place, used when the final
   * `quiz.feedback` event arrives after the streaming `quiz.feedback.verdict`
   * + `quiz.feedback.chunk` sequence. Prevents the duplicate bubble bug
   * where verdict creates an empty bubble, chunks fill it, then final
   * adds a SECOND bubble with the same content. Returns true if a
   * feedback bubble was found and updated, false otherwise (caller can
   * fall back to addMessage).
   */
  finalizeLastFeedback(patch: Partial<QuizMessage>): boolean;
  updateProgress(p: {
    correct: number;
    incorrect: number;
    skipped: number;
    score: number;
    current: number;
    total: number;
  }): void;
  setTimeLeft(t: number | null): void;
  setCategories(cats: CategoryProgress[]): void;
  setPvPPlayers(players: PvPPlayer[]): void;
  setChallengeId(id: string | null): void;
  setIsSearching(v: boolean): void;
  setResults(r: Record<string, unknown>): void;
  setInput(input: string): void;
  setIsTyping(typing: boolean): void;
  tickTimer(): void;
  // V2 actions
  setAiPersonality(p: AIPersonality | null): void;
  setStreak(streak: number, bestStreak: number): void;
  setCurrentDifficulty(d: number): void;
  setPendingFollowUp(text: string | null): void;
  fetchArenaStats(): Promise<void>;
  fetchArenaLeaderboard(period?: "week" | "month" | "all"): Promise<void>;

  // PvP Arena actions
  setPvPMatch(matchId: string, players: ArenaPlayer[], totalRounds: number): void;
  setPvPRoundQuestion(question: string, category: string | null, difficulty: number, round: number, timeLimit: number): void;
  submitPvPAnswer(text: string): void;
  setOpponentAnswered(userId: string): void;
  addArenaRoundResult(result: ArenaRoundResult): void;
  updateArenaScoreboard(players: ArenaPlayer[]): void;
  setArenaFinalResults(results: ArenaFinalResults): void;
  addArenaChallenge(challenge: ArenaChallenge): void;
  removeArenaChallenge(challengeId: string): void;
  addDisconnectedPlayer(userId: string): void;
  removeDisconnectedPlayer(userId: string): void;
  tickPvPTimer(): void;
  resetPvP(): void;
  reset(): void;
}

const INITIAL_STATE = {
  sessionId: null as string | null,
  mode: "free_dialog" as QuizMode,
  category: null as string | null,
  status: "idle" as QuizStatus,

  currentQuestion: 0,
  totalQuestions: 0,
  correct: 0,
  incorrect: 0,
  skipped: 0,
  score: 0,

  messages: [] as QuizMessage[],
  _msgCounter: 0,

  timeLeft: null as number | null,

  categories: [] as CategoryProgress[],

  pvpPlayers: [] as PvPPlayer[],
  challengeId: null as string | null,
  isSearching: false,

  input: "",
  isTyping: false,

  results: null as Record<string, unknown> | null,

  // V2
  aiPersonality: null as AIPersonality | null,
  streak: 0,
  bestStreak: 0,
  currentDifficulty: 3,
  pendingFollowUp: null as string | null,
  currentChoices: null as string[] | null,
  pickedChoiceIndex: null as number | null,

  arenaStats: null as ArenaStats | null,
  arenaStatsLoading: false,

  arenaLeaderboard: [] as ArenaLeaderboardEntry[],
  arenaLeaderboardPeriod: "all" as "week" | "month" | "all",
  arenaLeaderboardLoading: false,
  arenaLeaderboardUserRank: null as Record<string, unknown> | null,

  // PvP Arena Match
  pvpMatchId: null as string | null,
  pvpRound: 0,
  pvpTotalRounds: 10,
  pvpArenaPlayers: [] as ArenaPlayer[],
  pvpRoundResults: [] as ArenaRoundResult[],
  pvpMyAnswer: "",
  pvpMyAnswerSubmitted: false,
  pvpOpponentsAnswered: {} as Record<string, boolean>,
  pvpTimeLeft: 0,
  pvpFinalResults: null as ArenaFinalResults | null,
  pvpContainsBot: false,
  pvpCurrentQuestion: null as string | null,
  pvpCurrentCategory: null as string | null,
  pvpCurrentDifficulty: 3,
  pvpDisconnectedPlayers: [] as string[],
  pvpActiveChallenges: [] as ArenaChallenge[],
  pvpArenaAudioUrl: null as string | null,
};

export const useKnowledgeStore = create<KnowledgeState>((set, get) => ({
  ...INITIAL_STATE,

  init: (mode, category) =>
    set({
      ...INITIAL_STATE,
      mode,
      category: category ?? null,
      status: "selecting",
    }),

  setStatus: (status) => set({ status }),
  setSessionId: (sessionId) => set({ sessionId }),

  nextMsgId: () => {
    const counter = get()._msgCounter + 1;
    set({ _msgCounter: counter });
    return `kmsg-${counter}`;
  },

  addMessage: (msg) => {
    const id = get().nextMsgId();
    const fullMsg: QuizMessage = { ...msg, id, timestamp: Date.now() };
    set((s) => ({ messages: [...s.messages, fullMsg] }));
  },

  // 2026-04-18: streaming feedback support — append tokens to last message.
  appendToLastMessage: (text: string) => {
    set((s) => {
      if (!s.messages.length) return s;
      const idx = s.messages.length - 1;
      const last = s.messages[idx];
      const updated: QuizMessage = {
        ...last,
        content: (last.content || "") + text,
        explanation: (last.explanation || "") + text,
      };
      return { messages: [...s.messages.slice(0, idx), updated] };
    });
  },

  finalizeLastFeedback: (patch) => {
    const { messages } = get();
    // Walk backwards — the streaming verdict bubble is the most recent
    // feedback in normal flow, but skip past unrelated trailing messages.
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].type === "feedback") {
        const merged: QuizMessage = { ...messages[i], ...patch };
        set({
          messages: [
            ...messages.slice(0, i),
            merged,
            ...messages.slice(i + 1),
          ],
        });
        return true;
      }
      // If a different message type sits between verdict and final
      // (shouldn't happen in current backend), bail and let caller fall
      // back so we never silently swallow a feedback event.
      if (messages[i].type === "question") return false;
    }
    return false;
  },

  updateProgress: (p) =>
    set({
      correct: p.correct,
      incorrect: p.incorrect,
      skipped: p.skipped,
      score: p.score,
      currentQuestion: p.current,
      totalQuestions: p.total,
    }),

  setTimeLeft: (timeLeft) => set({ timeLeft }),

  setCategories: (categories) => set({ categories }),

  setPvPPlayers: (pvpPlayers) => set({ pvpPlayers }),
  setChallengeId: (challengeId) => set({ challengeId }),
  setIsSearching: (isSearching) => set({ isSearching }),

  setResults: (results) => set({ results, status: "completed" }),

  setInput: (input) => set({ input }),
  setIsTyping: (isTyping) => set({ isTyping }),

  tickTimer: () =>
    set((s) => {
      if (s.timeLeft === null || s.timeLeft <= 0) return {};
      return { timeLeft: s.timeLeft - 1 };
    }),

  // V2 actions
  setAiPersonality: (aiPersonality) => set({ aiPersonality }),
  setStreak: (streak, bestStreak) => set({ streak, bestStreak }),
  setCurrentDifficulty: (currentDifficulty) => set({ currentDifficulty }),
  setPendingFollowUp: (pendingFollowUp) => set({ pendingFollowUp }),
  setCurrentChoices: (currentChoices) => set({ currentChoices, pickedChoiceIndex: null }),
  setPickedChoiceIndex: (pickedChoiceIndex) => set({ pickedChoiceIndex }),

  fetchArenaStats: async () => {
    set({ arenaStatsLoading: true });
    try {
      const data = await api.get<ArenaStats>("/dashboard/knowledge-stats");
      set({ arenaStats: data, arenaStatsLoading: false });
    } catch {
      set({ arenaStatsLoading: false });
    }
  },

  fetchArenaLeaderboard: async (period = "all") => {
    set({ arenaLeaderboardLoading: true, arenaLeaderboardPeriod: period });
    try {
      const data = await api.get<{ entries: ArenaLeaderboardEntry[]; user_rank: Record<string, unknown> | null }>(`/knowledge/arena/leaderboard?period=${period}`);
      set({
        arenaLeaderboard: data.entries || [],
        arenaLeaderboardUserRank: data.user_rank || null,
        arenaLeaderboardLoading: false,
      });
    } catch {
      set({ arenaLeaderboardLoading: false });
    }
  },

  // ── PvP Arena actions ──

  setPvPMatch: (matchId, players, totalRounds) =>
    set({
      pvpMatchId: matchId,
      pvpArenaPlayers: players,
      pvpTotalRounds: totalRounds,
      pvpRound: 0,
      pvpRoundResults: [],
      pvpFinalResults: null,
      pvpContainsBot: players.some((p) => p.is_bot),
      status: "active",
      mode: "pvp",
    }),

  setPvPRoundQuestion: (question, category, difficulty, round, timeLimit) =>
    set({
      pvpCurrentQuestion: question,
      pvpCurrentCategory: category,
      pvpCurrentDifficulty: difficulty,
      pvpRound: round,
      pvpTimeLeft: timeLimit,
      pvpMyAnswer: "",
      pvpMyAnswerSubmitted: false,
      pvpOpponentsAnswered: {},
      // 2026-04-19 Phase 2.8: reset arena audio on new round — the server
      // will re-emit `pvp.audio_ready` when its TTS task completes.
      pvpArenaAudioUrl: null,
    }),

  setPvpArenaAudio: (url) => set({ pvpArenaAudioUrl: url }),

  submitPvPAnswer: (text) =>
    set({ pvpMyAnswer: text, pvpMyAnswerSubmitted: true }),

  setOpponentAnswered: (userId) =>
    set((s) => ({
      pvpOpponentsAnswered: { ...s.pvpOpponentsAnswered, [userId]: true },
    })),

  addArenaRoundResult: (result) =>
    set((s) => ({
      pvpRoundResults: [...s.pvpRoundResults, result],
      pvpCurrentQuestion: null,
    })),

  updateArenaScoreboard: (players) =>
    set({ pvpArenaPlayers: players }),

  setArenaFinalResults: (results) =>
    set({ pvpFinalResults: results, status: "completed" }),

  addArenaChallenge: (challenge) =>
    set((s) => ({
      pvpActiveChallenges: [
        ...s.pvpActiveChallenges.filter((c) => c.challenge_id !== challenge.challenge_id),
        challenge,
      ],
    })),

  removeArenaChallenge: (challengeId) =>
    set((s) => ({
      pvpActiveChallenges: s.pvpActiveChallenges.filter((c) => c.challenge_id !== challengeId),
    })),

  addDisconnectedPlayer: (userId) =>
    set((s) => ({
      pvpDisconnectedPlayers: [...s.pvpDisconnectedPlayers, userId],
    })),

  removeDisconnectedPlayer: (userId) =>
    set((s) => ({
      pvpDisconnectedPlayers: s.pvpDisconnectedPlayers.filter((id) => id !== userId),
    })),

  tickPvPTimer: () =>
    set((s) => {
      if (s.pvpTimeLeft <= 0) return {};
      return { pvpTimeLeft: s.pvpTimeLeft - 1 };
    }),

  resetPvP: () =>
    set({
      pvpMatchId: null,
      pvpRound: 0,
      pvpTotalRounds: 10,
      pvpArenaPlayers: [],
      pvpRoundResults: [],
      pvpMyAnswer: "",
      pvpMyAnswerSubmitted: false,
      pvpOpponentsAnswered: {},
      pvpTimeLeft: 0,
      pvpFinalResults: null,
      pvpContainsBot: false,
      pvpCurrentQuestion: null,
      pvpCurrentCategory: null,
      pvpCurrentDifficulty: 3,
      pvpDisconnectedPlayers: [],
      pvpActiveChallenges: [],
      isSearching: false,
      challengeId: null,
    }),

  reset: () => set(INITIAL_STATE),
}));
