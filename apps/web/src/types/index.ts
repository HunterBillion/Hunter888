export interface Scenario {
  id: string;
  title: string;
  description: string;
  scenario_type: string;
  difficulty: number;
  estimated_duration_minutes: number;
}

export interface TrainingSession {
  id: string;
  scenario_id: string;
  status: "active" | "completed" | "abandoned" | "error";
  started_at: string;
  ended_at: string | null;
  score_total: number | null;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  emotion_state: EmotionState | null;
  sequence_number: number;
  created_at: string;
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  team?: string;
}

export type UserRole = "manager" | "rop" | "methodologist" | "admin";

// Emotion states for character
export type EmotionState = "cold" | "warming" | "open";

// Consent
export interface ConsentStatus {
  accepted: boolean;
  accepted_at: string | null;
}

// Profile / password change
export interface PasswordChangeRequest {
  old_password: string;
  new_password: string;
}

export interface TrainingStats {
  total_sessions: number;
  completed_sessions: number;
  average_score: number | null;
  best_score: number | null;
  total_duration_minutes: number;
}

// WebSocket message types
export type WSConnectionState = "connecting" | "connected" | "disconnected" | "error";

export interface WSMessage {
  type: string;
  data: Record<string, unknown>;
}

// Microphone
export type MicrophonePermissionState = "prompt" | "granted" | "denied" | "error";

export type RecordingState = "idle" | "recording" | "processing";

// Training session UI state
export type SessionState = "connecting" | "ready" | "completed";

// Chat message for UI (lighter than full ChatMessage)
export interface ChatBubble {
  id: string;
  role: "user" | "assistant";
  content: string;
  emotion?: EmotionState;
  timestamp: string;
}

// Transcription
export interface TranscriptionState {
  status: "idle" | "transcribing" | "done";
  partial: string;
  final: string;
}
