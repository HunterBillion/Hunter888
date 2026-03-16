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
  emotion_state: string | null;
  sequence_number: number;
  created_at: string;
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: "manager" | "rop" | "methodologist" | "admin";
  is_active: boolean;
}
