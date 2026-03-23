import { create } from "zustand";

export type QuizMode = "free_dialog" | "blitz" | "themed" | "pvp";
export type QuizStatus = "idle" | "selecting" | "connecting" | "active" | "completed";

export interface QuizMessage {
  id: string;
  type: "question" | "answer" | "feedback" | "system" | "hint";
  content: string;
  isCorrect?: boolean;
  articleRef?: string;
  explanation?: string;
  category?: string;
  timestamp: number;
  userId?: string;
  userName?: string;
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

  // Actions
  init(mode: QuizMode, category?: string): void;
  setStatus(status: QuizStatus): void;
  setSessionId(id: string): void;
  nextMsgId(): string;
  addMessage(msg: Omit<QuizMessage, "id" | "timestamp">): void;
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

  reset: () => set(INITIAL_STATE),
}));
