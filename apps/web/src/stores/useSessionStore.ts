import { create } from "zustand";
import type {
  ChatBubble,
  EmotionState,
  SessionState,
  TranscriptionState,
  ObjectionHint,
  CheckpointHint,
} from "@/types";
import type { HumanFactor, ConsequenceEvent, PreCallBrief } from "@/types/story";
import type { CheckpointInfo } from "@/components/training/ScriptAdherence";
import type { TrapEvent } from "@/components/training/TrapNotification";
import type { ClientCardData } from "@/components/training/ClientCard";

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

  // Client card
  clientCard: ClientCardData | null;
  miniCardExpanded: boolean;

  // Script / scoring
  scriptScore: number;
  checkpointsHit: number;
  checkpointsTotal: number;
  checkpoints: CheckpointInfo[];

  // Talk/listen
  talkTime: number;
  listenTime: number;

  // Traps
  activeTrap: TrapEvent | null;
  trapsFell: number;
  trapsDodged: number;
  trapNetScore: number;

  // Hints
  objectionHint: ObjectionHint | null;
  checkpointHint: CheckpointHint | null;

  // Transcription
  transcription: TranscriptionState;

  // Input
  input: string;

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
  setSessionState: (state: SessionState) => void;
  setEmotion: (emotion: EmotionState) => void;
  setCharacterName: (name: string) => void;
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
  setClientCard: (card: ClientCardData | null) => void;
  setMiniCardExpanded: (expanded: boolean) => void;
  setScriptScore: (score: number) => void;
  setCheckpointsHit: (hit: number) => void;
  setCheckpointsTotal: (total: number) => void;
  setCheckpoints: (cps: CheckpointInfo[]) => void;
  setTalkTime: (time: number) => void;
  setListenTime: (time: number) => void;
  setActiveTrap: (trap: TrapEvent | null) => void;
  addTrapFell: () => void;
  addTrapDodged: () => void;
  adjustTrapNetScore: (delta: number) => void;
  setObjectionHint: (hint: ObjectionHint | null) => void;
  setCheckpointHint: (hint: CheckpointHint | null) => void;
  setTranscription: (t: TranscriptionState) => void;
  setInput: (input: string) => void;
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
  clientCard: null as ClientCardData | null,
  miniCardExpanded: false,
  scriptScore: 0,
  checkpointsHit: 0,
  checkpointsTotal: 0,
  checkpoints: [] as CheckpointInfo[],
  talkTime: 0,
  listenTime: 0,
  activeTrap: null as TrapEvent | null,
  trapsFell: 0,
  trapsDodged: 0,
  trapNetScore: 0,
  objectionHint: null as ObjectionHint | null,
  checkpointHint: null as CheckpointHint | null,
  transcription: { status: "idle", partial: "", final: "" } as TranscriptionState,
  input: "",
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
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  setSessionState: (sessionState) => set({ sessionState }),
  setEmotion: (emotion) => set({ emotion }),
  setCharacterName: (characterName) => set({ characterName }),
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
  setClientCard: (clientCard) => set({ clientCard }),
  setMiniCardExpanded: (miniCardExpanded) => set({ miniCardExpanded }),
  setScriptScore: (scriptScore) => set({ scriptScore }),
  setCheckpointsHit: (checkpointsHit) => set({ checkpointsHit }),
  setCheckpointsTotal: (checkpointsTotal) => set({ checkpointsTotal }),
  setCheckpoints: (checkpoints) => set({ checkpoints }),
  setTalkTime: (talkTime) => set({ talkTime }),
  setListenTime: (listenTime) => set({ listenTime }),
  setActiveTrap: (activeTrap) => set({ activeTrap }),
  addTrapFell: () => set((s) => ({ trapsFell: s.trapsFell + 1 })),
  addTrapDodged: () => set((s) => ({ trapsDodged: s.trapsDodged + 1 })),
  adjustTrapNetScore: (delta) =>
    set((s) => ({ trapNetScore: Math.max(-10, Math.min(10, s.trapNetScore + delta)) })),
  setObjectionHint: (objectionHint) => set({ objectionHint }),
  setCheckpointHint: (checkpointHint) => set({ checkpointHint }),
  setTranscription: (transcription) => set({ transcription }),
  setInput: (input) => set({ input }),
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
      clientCard: null,
      miniCardExpanded: false,
      scriptScore: 0,
      checkpointsHit: 0,
      checkpointsTotal: 0,
      checkpoints: [],
      talkTime: 0,
      listenTime: 0,
      activeTrap: null,
      trapsFell: 0,
      trapsDodged: 0,
      trapNetScore: 0,
      objectionHint: null,
      checkpointHint: null,
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
