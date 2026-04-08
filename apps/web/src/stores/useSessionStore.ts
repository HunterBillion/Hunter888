import { create } from "zustand";
import type {
  ChatBubble,
  CoachingWhisper,
  EmotionState,
  SessionState,
  TranscriptionState,
  ObjectionHint,
  CheckpointHint,
  StageUpdate,
  HangupData,
} from "@/types";
import type { HumanFactor, ConsequenceEvent, PreCallBrief } from "@/types/story";
import type { CheckpointInfo } from "@/components/training/ScriptAdherence";
import type { TrapEvent } from "@/components/training/TrapNotification";
import type { ClientCardData } from "@/components/training/ClientCard";

export type DifficultyMode = "normal" | "boss" | "safe" | "coaching" | "challenge" | "onboarding";
export type DifficultyTrend = "rising" | "falling" | "stable";

export interface DifficultyUpdate {
  effective_difficulty: number;
  modifier: number;
  mode: DifficultyMode;
  good_streak: number;
  bad_streak: number;
  had_comeback: boolean;
  trend: DifficultyTrend;
}

interface SessionStore {
  // Session identity
  sessionId: string;

  // Messages
  messages: ChatBubble[];
  _msgCounter: number;

  // Session state
  sessionState: SessionState;
  connectionState: string;
  emotion: EmotionState;
  characterName: string;
  archetypeCode: string;
  characterGender: "M" | "F" | "neutral";
  scenarioTitle: string;
  isTyping: boolean;
  elapsed: number;

  // Input modes
  textMode: boolean;
  sttAvailable: boolean;
  micActive: boolean;
  micChecked: boolean;

  // Modals
  showAbortModal: boolean;
  showSilenceModal: boolean;
  silenceWarning: boolean;
  showHangupModal: boolean;
  hangupData: HangupData | null;
  hangupWarning: string | null;

  // Client card
  clientCard: ClientCardData | null;
  miniCardExpanded: boolean;

  // Script / scoring
  scriptScore: number;
  checkpointsHit: number;
  checkpointsTotal: number;
  checkpoints: CheckpointInfo[];
  /** Title of the most recently matched checkpoint (for toast/flash) */
  newCheckpoint: string | null;
  /** True while session is active — scores are preliminary */
  isPreliminaryScore: boolean;

  // Talk/listen
  talkTime: number;
  listenTime: number;

  // Traps
  activeTrap: TrapEvent | null;
  trapsFell: number;
  trapsDodged: number;
  trapNetScore: number;

  // Stage tracking
  currentStage: number;
  currentStageName: string;
  stageLabel: string;
  stagesCompleted: number[];
  totalStages: number;
  stageConfidence: number;

  // Hints
  objectionHint: ObjectionHint | null;
  checkpointHint: CheckpointHint | null;

  // Coaching whispers
  whispers: CoachingWhisper[];
  whispersEnabled: boolean;

  // Real-time scores (from score.hint)
  realtimeScores: {
    objection_handling: number;
    communication: number;
    human_factor: number;
    realtime_estimate: number;
    max_possible: number;
  } | null;

  // Trap history (persistent log)
  trapHistory: TrapEvent[];

  // Emotion history (for live sparkline)
  emotionHistory: { state: EmotionState; timestamp: number }[];

  // Difficulty change reason
  difficultyReason: string | null;

  // Transcription
  transcription: TranscriptionState;

  // Input
  input: string;

  // Adaptive difficulty
  effectiveDifficulty: number;
  difficultyModifier: number;
  difficultyMode: DifficultyMode;
  difficultyTrend: DifficultyTrend;
  goodStreak: number;
  badStreak: number;
  hadComeback: boolean;

  // Story mode
  storyId: string | null;
  storyMode: boolean;
  preCallBrief: PreCallBrief | null;
  humanFactors: HumanFactor[];
  consequences: ConsequenceEvent[];
  callNumber: number;
  totalCalls: number;
  showPreCallBrief: boolean;
  showBetweenCalls: boolean;
  betweenCallsEvents: Array<{ event_type: string; title: string; content: string; severity: number | null }>;

  // Actions
  init: (sessionId: string) => void;
  reset: () => void;
  nextMsgId: () => string;
  addMessage: (msg: ChatBubble) => void;
  sortMessagesBySequence: () => void;
  setSessionState: (state: SessionState) => void;
  setConnectionState: (state: string) => void;
  setEmotion: (emotion: EmotionState) => void;
  setCharacterName: (name: string) => void;
  setArchetypeCode: (code: string) => void;
  setCharacterGender: (gender: "M" | "F" | "neutral") => void;
  setScenarioTitle: (title: string) => void;
  setIsTyping: (typing: boolean) => void;
  setElapsed: (elapsed: number) => void;
  tickElapsed: () => void;
  setTextMode: (mode: boolean) => void;
  setSttAvailable: (available: boolean) => void;
  setMicActive: (active: boolean) => void;
  setMicChecked: (checked: boolean) => void;
  setShowAbortModal: (show: boolean) => void;
  setShowSilenceModal: (show: boolean) => void;
  setSilenceWarning: (warn: boolean) => void;
  setShowHangupModal: (show: boolean) => void;
  setHangupData: (data: HangupData | null) => void;
  setHangupWarning: (msg: string | null) => void;
  setClientCard: (card: ClientCardData | null) => void;
  setMiniCardExpanded: (expanded: boolean) => void;
  setScriptScore: (score: number) => void;
  setCheckpointsHit: (hit: number) => void;
  setCheckpointsTotal: (total: number) => void;
  setCheckpoints: (cps: CheckpointInfo[]) => void;
  setNewCheckpoint: (cp: string | null) => void;
  setIsPreliminaryScore: (preliminary: boolean) => void;
  setTalkTime: (time: number) => void;
  setListenTime: (time: number) => void;
  setActiveTrap: (trap: TrapEvent | null) => void;
  addTrapFell: () => void;
  addTrapDodged: () => void;
  adjustTrapNetScore: (delta: number) => void;
  setStageUpdate: (data: StageUpdate) => void;
  setObjectionHint: (hint: ObjectionHint | null) => void;
  setCheckpointHint: (hint: CheckpointHint | null) => void;
  addWhisper: (w: CoachingWhisper) => void;
  setWhispersEnabled: (enabled: boolean) => void;
  setRealtimeScores: (scores: SessionStore["realtimeScores"]) => void;
  addTrapToHistory: (trap: TrapEvent) => void;
  addEmotionToHistory: (state: EmotionState) => void;
  setDifficultyReason: (reason: string | null) => void;
  setTranscription: (t: TranscriptionState) => void;
  setInput: (input: string) => void;
  // Difficulty actions
  setDifficultyUpdate: (data: DifficultyUpdate) => void;
  // Story actions
  setStoryMode: (storyId: string, totalCalls: number) => void;
  setPreCallBrief: (brief: PreCallBrief | null) => void;
  setHumanFactors: (factors: HumanFactor[]) => void;
  addConsequence: (c: ConsequenceEvent) => void;
  setCallNumber: (n: number) => void;
  setShowPreCallBrief: (show: boolean) => void;
  setShowBetweenCalls: (show: boolean) => void;
  setBetweenCallsEvents: (events: Array<{ event_type: string; title: string; content: string; severity: number | null }>) => void;
  resetCallState: () => void;
}

const INITIAL_STATE = {
  sessionId: "",
  messages: [] as ChatBubble[],
  _msgCounter: 0,
  sessionState: "connecting" as SessionState,
  connectionState: "disconnected",
  emotion: "cold" as EmotionState,
  characterName: "Клиент",
  archetypeCode: "skeptic",
  characterGender: "M" as const,
  scenarioTitle: "",
  isTyping: false,
  elapsed: 0,
  textMode: false,
  sttAvailable: true,
  micActive: false,
  micChecked: false,
  showAbortModal: false,
  showSilenceModal: false,
  silenceWarning: false,
  showHangupModal: false,
  hangupData: null as HangupData | null,
  hangupWarning: null as string | null,
  clientCard: null as ClientCardData | null,
  miniCardExpanded: false,
  scriptScore: 0,
  checkpointsHit: 0,
  checkpointsTotal: 0,
  checkpoints: [] as CheckpointInfo[],
  newCheckpoint: null as string | null,
  isPreliminaryScore: true,
  talkTime: 0,
  listenTime: 0,
  activeTrap: null as TrapEvent | null,
  trapsFell: 0,
  trapsDodged: 0,
  trapNetScore: 0,
  currentStage: 1,
  currentStageName: "greeting",
  stageLabel: "Приветствие",
  stagesCompleted: [] as number[],
  totalStages: 7,
  stageConfidence: 1.0,
  objectionHint: null as ObjectionHint | null,
  checkpointHint: null as CheckpointHint | null,
  whispers: [] as CoachingWhisper[],
  whispersEnabled: true,
  realtimeScores: null as SessionStore["realtimeScores"],
  trapHistory: [] as TrapEvent[],
  emotionHistory: [] as { state: EmotionState; timestamp: number }[],
  difficultyReason: null as string | null,
  transcription: { status: "idle", partial: "", final: "" } as TranscriptionState,
  input: "",
  // Adaptive difficulty
  effectiveDifficulty: 5,
  difficultyModifier: 0,
  difficultyMode: "normal" as DifficultyMode,
  difficultyTrend: "stable" as DifficultyTrend,
  goodStreak: 0,
  badStreak: 0,
  hadComeback: false,
  // Story mode
  storyId: null as string | null,
  storyMode: false,
  preCallBrief: null as PreCallBrief | null,
  humanFactors: [] as HumanFactor[],
  consequences: [] as ConsequenceEvent[],
  callNumber: 0,
  totalCalls: 0,
  showPreCallBrief: false,
  showBetweenCalls: false,
  betweenCallsEvents: [] as Array<{ event_type: string; title: string; content: string; severity: number | null }>,
};

export const useSessionStore = create<SessionStore>((set, get) => ({
  ...INITIAL_STATE,

  init: (sessionId) => set({ ...INITIAL_STATE, sessionId }),
  reset: () => set(INITIAL_STATE),
  nextMsgId: () => {
    const counter = get()._msgCounter + 1;
    set({ _msgCounter: counter });
    return `msg-${counter}`;
  },
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg].slice(-500) })),
  sortMessagesBySequence: () =>
    set((s) => ({
      messages: [...s.messages].sort((a, b) => {
        const seqA = a.sequenceNumber ?? 0;
        const seqB = b.sequenceNumber ?? 0;
        return seqA - seqB;
      }),
    })),
  setSessionState: (sessionState) => set({ sessionState }),
  setConnectionState: (connectionState) => set({ connectionState }),
  setEmotion: (emotion) => set({ emotion }),
  setCharacterName: (characterName) => set({ characterName }),
  setArchetypeCode: (archetypeCode: string) => set({ archetypeCode }),
  setCharacterGender: (characterGender: "M" | "F" | "neutral") => set({ characterGender }),
  setScenarioTitle: (scenarioTitle) => set({ scenarioTitle }),
  setIsTyping: (isTyping) => set({ isTyping }),
  setElapsed: (elapsed) => set({ elapsed }),
  tickElapsed: () => set((s) => ({ elapsed: s.elapsed + 1 })),
  setTextMode: (textMode) => set({ textMode }),
  setSttAvailable: (sttAvailable) => set({ sttAvailable }),
  setMicActive: (micActive) => set({ micActive }),
  setMicChecked: (micChecked) => set({ micChecked }),
  setShowAbortModal: (showAbortModal) => set({ showAbortModal }),
  setShowSilenceModal: (showSilenceModal) => set({ showSilenceModal }),
  setSilenceWarning: (silenceWarning) => set({ silenceWarning }),
  setShowHangupModal: (showHangupModal) => set({ showHangupModal }),
  setHangupData: (hangupData) => set({ hangupData }),
  setHangupWarning: (hangupWarning) => set({ hangupWarning }),
  setClientCard: (clientCard) => set({ clientCard }),
  setMiniCardExpanded: (miniCardExpanded) => set({ miniCardExpanded }),
  setScriptScore: (scriptScore) => set({ scriptScore }),
  setCheckpointsHit: (checkpointsHit) => set({ checkpointsHit }),
  setCheckpointsTotal: (checkpointsTotal) => set({ checkpointsTotal }),
  setCheckpoints: (checkpoints) => set({ checkpoints }),
  setNewCheckpoint: (newCheckpoint) => set({ newCheckpoint }),
  setIsPreliminaryScore: (isPreliminaryScore) => set({ isPreliminaryScore }),
  setTalkTime: (talkTime) => set({ talkTime }),
  setListenTime: (listenTime) => set({ listenTime }),
  setActiveTrap: (activeTrap) => set({ activeTrap }),
  addTrapFell: () => set((s) => ({ trapsFell: s.trapsFell + 1 })),
  addTrapDodged: () => set((s) => ({ trapsDodged: s.trapsDodged + 1 })),
  adjustTrapNetScore: (delta) =>
    set((s) => ({ trapNetScore: Math.max(-10, Math.min(10, s.trapNetScore + delta)) })),
  setStageUpdate: (data) => set({
    currentStage: data.stage_number,
    currentStageName: data.stage_name,
    stageLabel: data.stage_label,
    stagesCompleted: data.stages_completed,
    totalStages: data.total_stages,
    stageConfidence: data.confidence,
  }),
  setObjectionHint: (objectionHint) => set({ objectionHint }),
  setCheckpointHint: (checkpointHint) => set({ checkpointHint }),
  addWhisper: (w) => set((s) => ({ whispers: [w, ...s.whispers].slice(0, 3) })),
  setWhispersEnabled: (whispersEnabled) => set({ whispersEnabled }),
  setRealtimeScores: (realtimeScores) => set({ realtimeScores }),
  addTrapToHistory: (trap) =>
    set((s) => ({
      // Cap at 200 entries to prevent unbounded memory growth on long sessions
      trapHistory: [...s.trapHistory.slice(-199), trap],
    })),
  addEmotionToHistory: (state) =>
    set((s) => ({
      emotionHistory: [...s.emotionHistory.slice(-14), { state, timestamp: Date.now() }],
    })),
  setDifficultyReason: (difficultyReason) => set({ difficultyReason }),
  setTranscription: (transcription) => set({ transcription }),
  setInput: (input) => set({ input }),
  // Difficulty actions
  setDifficultyUpdate: (data) => set({
    effectiveDifficulty: data.effective_difficulty,
    difficultyModifier: data.modifier,
    difficultyMode: data.mode,
    difficultyTrend: data.trend,
    goodStreak: data.good_streak,
    badStreak: data.bad_streak,
    hadComeback: data.had_comeback,
  }),
  // Story actions
  setStoryMode: (storyId, totalCalls) => set({ storyId, storyMode: true, totalCalls }),
  setPreCallBrief: (preCallBrief) => set({ preCallBrief }),
  setHumanFactors: (humanFactors) => set({ humanFactors }),
  addConsequence: (c) => set((s) => ({ consequences: [...s.consequences, c] })),
  setCallNumber: (callNumber) => set({ callNumber }),
  setShowPreCallBrief: (showPreCallBrief) => set({ showPreCallBrief }),
  setShowBetweenCalls: (showBetweenCalls) => set({ showBetweenCalls }),
  setBetweenCallsEvents: (betweenCallsEvents) => set({ betweenCallsEvents }),
  resetCallState: () =>
    set((s) => ({
      sessionId: s.sessionId,
      messages: [],
      _msgCounter: 0,
      sessionState: "connecting",
      connectionState: s.connectionState,
      emotion: "cold",
      characterName: s.characterName,
      archetypeCode: s.archetypeCode,
      characterGender: s.characterGender,
      scenarioTitle: s.scenarioTitle,
      isTyping: false,
      elapsed: 0,
      textMode: s.textMode,
      sttAvailable: s.sttAvailable,
      micActive: false,
      micChecked: s.micChecked,
      showAbortModal: false,
      showSilenceModal: false,
      silenceWarning: false,
      showHangupModal: false,
      hangupData: null,
      hangupWarning: null,
      clientCard: null,
      miniCardExpanded: false,
      scriptScore: 0,
      checkpointsHit: 0,
      checkpointsTotal: 0,
      checkpoints: [],
      newCheckpoint: null,
      isPreliminaryScore: true,
      talkTime: 0,
      listenTime: 0,
      activeTrap: null,
      trapsFell: 0,
      trapsDodged: 0,
      trapNetScore: 0,
      effectiveDifficulty: 5,
      difficultyModifier: 0,
      difficultyMode: "normal",
      difficultyTrend: "stable",
      goodStreak: 0,
      badStreak: 0,
      hadComeback: false,
      currentStage: 1,
      currentStageName: "greeting",
      stageLabel: "Приветствие",
      stagesCompleted: [],
      totalStages: 7,
      stageConfidence: 1.0,
      objectionHint: null,
      checkpointHint: null,
      whispersEnabled: s.whispersEnabled,
      whispers: [],
      realtimeScores: null,
      trapHistory: [],
      emotionHistory: [],
      difficultyReason: null,
      transcription: { status: "idle", partial: "", final: "" },
      input: "",
      storyId: s.storyId,
      storyMode: s.storyMode,
      preCallBrief: s.preCallBrief,
      humanFactors: s.humanFactors,
      consequences: s.consequences,
      callNumber: s.callNumber,
      totalCalls: s.totalCalls,
      showPreCallBrief: false,
      showBetweenCalls: false,
      betweenCallsEvents: s.betweenCallsEvents,
    })),
}));
