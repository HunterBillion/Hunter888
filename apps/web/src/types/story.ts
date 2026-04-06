/**
 * Story-mode WebSocket message types and related interfaces.
 * Used by training/[id] page for multi-call story sessions.
 */

// ─── Human Factors & Consequences ────────────────────────────────────────────

export interface HumanFactor {
  factor: string;
  intensity: number;  // 0.0-1.0
  since_call: number; // call number when activated
}

export interface ConsequenceEvent {
  call: number;
  type: string;       // "trust_broken", "reputation_loss", etc.
  severity: number;   // 0.0-1.0
  detail: string;
}

export interface StoryletEvent {
  storylet_id: string;
  impact: string;     // "anxiety+30", "trust-20", etc.
}

export interface PreCallBrief {
  story_id: string;
  call_number: number;
  total_calls: number;
  client_name: string;
  scenario_title: string;
  context: string;         // narrative context for this call
  active_factors: HumanFactor[];
  previous_consequences: ConsequenceEvent[];
  personality_hint: string | null;
  suggested_approach: string | null;
}

// ─── Story WS Messages (Server → Client) ────────────────────────────────────

export interface WSStoryStarted {
  type: "story.started";
  data: {
    story_id: string;
    story_name: string;
    total_calls: number;
    client_name: string;
    personality_profile: Record<string, unknown>;
  };
}

export interface WSPreCallBrief {
  type: "story.pre_call_brief";
  data: PreCallBrief;
}

export interface WSBetweenCallsEvent {
  type: "story.between_calls";
  data: {
    story_id: string;
    events: Array<{
      event_type: string;
      title: string;
      content: string;
      severity: number | null;
    }>;
  };
}

export interface WSStoryCallReady {
  type: "story.call_ready";
  data: {
    story_id: string;
    call_number: number;
    session_id: string;
  };
}

export interface WSStoryCallReport {
  type: "story.call_report";
  data: {
    story_id: string;
    call_number: number;
    score: number;
    key_moments: string[];
    consequences: ConsequenceEvent[];
    memories_created: number;
  };
}

export interface WSStoryStateDelta {
  type: "story.state_delta";
  data: {
    story_id: string;
    call_number: number;
    active_factors: HumanFactor[];
    new_consequence: ConsequenceEvent | null;
    consequences_count: number;
    tension: number;
  };
}

export interface WSStoryProgress {
  type: "story.progress";
  data: {
    story_id: string;
    call_number: number;
    total_calls: number;
    game_status: string;
    tension: number;
  };
}

export interface WSStoryCompleted {
  type: "story.completed";
  data: {
    story_id: string;
    final_status: string;
    total_score: number;
    calls_completed: number;
  };
}

// ─── PvP WS Messages (Server → Client) ──────────────────────────────────────

export interface WSPvPMatchFound {
  type: "match.found";
  data: {
    duel_id: string;
    opponent_rating: number;
    difficulty: string;
    is_pve: boolean;
  };
}

export interface WSPvPDuelBrief {
  type: "duel.brief";
  data: {
    duel_id: string;
    your_role: "seller" | "client";
    archetype: string | null;
    character_brief: { name: string; brief: string; behavior: string } | null;
    human_factors: Record<string, unknown> | null;
    difficulty: string;
    scenario_title: string | null;
    round_number: number;
    time_limit_seconds: number;
  };
}

export interface WSPvPRoundStart {
  type: "round.start";
  data: {
    round: 1 | 2;
    your_role: "seller" | "client";
    archetype: string | null;
    time_limit: number;
  };
}

export interface WSPvPDuelMessage {
  type: "duel.message";
  data: {
    sender_role: "seller" | "client";
    text: string;
    round: number;
  };
}

export interface WSPvPJudgeScore {
  type: "judge.score";
  data: {
    selling_score: number;
    acting_score: number;
    legal_accuracy: number;
  };
}

export interface WSPvPDuelResult {
  type: "duel.result";
  data: {
    duel_id: string;
    player1_total: number;
    player2_total: number;
    winner_id: string | null;
    is_draw: boolean;
    player1_rating_delta: number;
    player2_rating_delta: number;
    summary: string;
  };
}

// ─── Union type for all story/pvp WS messages ──────────────────────────────

export type StoryWSMessage =
  | WSStoryStarted
  | WSPreCallBrief
  | WSBetweenCallsEvent
  | WSStoryCallReady
  | WSStoryStateDelta
  | WSStoryCallReport
  | WSStoryProgress
  | WSStoryCompleted;

export type PvPWSMessage =
  | WSPvPMatchFound
  | WSPvPDuelBrief
  | WSPvPRoundStart
  | WSPvPDuelMessage
  | WSPvPJudgeScore
  | WSPvPDuelResult;
