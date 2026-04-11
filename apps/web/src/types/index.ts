// ============================================================================
// Hunter888 — Complete Type Definitions
// 1:1 mapping with backend Pydantic schemas + SQLAlchemy models
// ============================================================================

// ─── Enums & Literal Types ─────────────────────────────────────────────────

export type UserRole = "manager" | "rop" | "methodologist" | "admin";

/**
 * Full 10-state emotion system (synced with backend EmotionState enum).
 * Backend still sends LEGACY_MAP (5-state) via WS for backward compat,
 * but frontend now supports all 10 for display.
 */
export type EmotionState =
  | "cold" | "guarded" | "curious" | "considering" | "negotiating"
  | "deal" | "testing" | "callback" | "hostile" | "hangup"
  // Legacy aliases (backward compat with old WS messages)
  | "skeptical" | "warming" | "open";

export type ObjectionCategory = "price" | "trust" | "need" | "timing" | "competitor";

// DOC_08: Emotion v6 extensions
export type IntensityLevel = "low" | "medium" | "high";

export type CompoundEmotionCode =
  | "cold_curiosity" | "resigned_acceptance" | "desperate_hope" | "cautious_interest"
  | "grudging_respect" | "hopeful_anxiety" | "fake_warmth" | "volatile_anger";

export type MicroExpressionCode =
  | "surprise_flash" | "anger_spike" | "relief_moment"
  | "humor_break" | "shame_flash" | "doubt_flicker";

export type ArchetypeCode =
  // Group 1: RESISTANCE (10)
  | "skeptic" | "blamer" | "sarcastic" | "aggressive" | "hostile"
  | "stubborn" | "conspiracy" | "righteous" | "litigious" | "scorched_earth"
  // Group 2: EMOTIONAL (10)
  | "grateful" | "anxious" | "ashamed" | "overwhelmed" | "desperate"
  | "crying" | "guilty" | "mood_swinger" | "frozen" | "hysteric"
  // Group 3: CONTROL (10)
  | "pragmatic" | "shopper" | "negotiator" | "know_it_all" | "manipulator"
  | "lawyer_client" | "auditor" | "strategist" | "power_player" | "puppet_master"
  // Group 4: AVOIDANCE (10)
  | "passive" | "delegator" | "avoidant" | "paranoid"
  | "procrastinator" | "ghosting" | "deflector" | "agreeable_ghost" | "fortress" | "smoke_screen"
  // Group 5: SPECIAL (10)
  | "referred" | "returner" | "rushed" | "couple"
  | "elderly" | "young_debtor" | "foreign_speaker" | "intermediary" | "repeat_caller" | "celebrity"
  // Group 6: COGNITIVE (10)
  | "overthinker" | "concrete" | "storyteller" | "misinformed" | "selective_listener"
  | "black_white" | "memory_issues" | "technical" | "magical_thinker" | "lawyer_level_2"
  // Group 7: SOCIAL (10)
  | "family_man" | "influenced" | "reputation_guard" | "community_leader" | "breadwinner"
  | "divorced" | "guarantor" | "widow" | "caregiver" | "multi_debtor_family"
  // Group 8: TEMPORAL (10)
  | "just_fired" | "collector_call" | "court_notice" | "salary_arrest" | "pre_court"
  | "post_refusal" | "inheritance_trap" | "business_collapse" | "medical_crisis" | "criminal_risk"
  // Group 9: PROFESSIONAL (10)
  | "teacher" | "doctor" | "military" | "accountant" | "salesperson"
  | "it_specialist" | "government" | "journalist" | "psychologist" | "competitor_employee"
  // Group 10: COMPOUND (10)
  | "aggressive_desperate" | "manipulator_crying" | "know_it_all_paranoid" | "passive_aggressive"
  | "couple_disagreeing" | "elderly_paranoid" | "hysteric_litigious" | "puppet_master_lawyer"
  | "shifting" | "ultimate";

export type ArchetypeGroup =
  | "resistance" | "emotional" | "control" | "avoidance" | "special"
  | "cognitive" | "social" | "temporal" | "professional" | "compound";

export type ArchetypeTier = 1 | 2 | 3 | 4;

export type BehaviorTag =
  // Стиль общения
  | "yelling" | "silence" | "long_stories" | "monosyllabic" | "polite" | "rude"
  // Мотивация
  | "fear" | "anger" | "shame" | "hope" | "nihilism" | "pride"
  // Тактика
  | "manipulation" | "avoidance" | "confrontation" | "cooperation" | "deception"
  // Сложность
  | "legal_traps" | "emotional_pressure" | "time_pressure" | "information_warfare"
  // Контекст
  | "family" | "business" | "crisis" | "inheritance" | "criminal";

export type SkillCode =
  | "empathy" | "knowledge" | "objection_handling" | "stress_resistance" | "closing"
  | "qualification" | "time_management" | "adaptation" | "legal_knowledge" | "rapport_building";

export type ScenarioType =
  // Group A: Outbound Cold (10)
  | "cold_ad" | "cold_referral" | "cold_social" | "cold_database" | "cold_base"
  | "cold_partner" | "cold_premium" | "cold_event" | "cold_expired" | "cold_insurance"
  // Group B: Outbound Warm (10)
  | "warm_callback" | "warm_noanswer" | "warm_refused" | "warm_dropped"
  | "warm_repeat" | "warm_webinar" | "warm_vip" | "warm_ghosted" | "warm_complaint" | "warm_competitor"
  // Group C: Inbound (8)
  | "in_website" | "in_hotline" | "in_social" | "in_chatbot"
  | "in_partner" | "in_complaint" | "in_urgent" | "in_corporate"
  // Group D: Special (12)
  | "special_ghosted" | "special_urgent" | "special_guarantor" | "special_couple"
  | "upsell" | "rescue" | "special_inheritance" | "vip_debtor"
  | "special_psychologist" | "special_vip" | "special_medical" | "special_boss"
  // Group E: Follow-up (5)
  | "follow_up_first" | "follow_up_second" | "follow_up_third" | "follow_up_rescue" | "follow_up_memory"
  // Group F: Crisis (5)
  | "crisis_collector" | "crisis_pre_court" | "crisis_business" | "crisis_criminal" | "crisis_full"
  // Group G: Compliance (5)
  | "compliance_basic" | "compliance_docs" | "compliance_legal" | "compliance_advanced" | "compliance_full"
  // Group H: Multi-party (5)
  | "multi_party_basic" | "multi_party_lawyer" | "multi_party_creditors" | "multi_party_family" | "multi_party_full";

export type ScenarioGroup = "cold" | "warm" | "inbound" | "special" | "follow_up" | "crisis" | "compliance" | "multi_party";

export type LeadSource =
  // Холодные
  | "cold_base" | "cold_social" | "cold_event"
  // Тёплые
  | "website_form" | "social_media" | "webinar" | "warm_complaint" | "warm_competitor" | "lead_nurture" | "ad_retarget"
  // Входящие
  | "incoming" | "in_chat" | "chatbot" | "in_referral_direct" | "in_urgent"
  // Повторные
  | "referral" | "repeat_call" | "partner" | "churned" | "callback_scheduled";

export type LeadSourceGroup = "cold" | "warm" | "inbound" | "repeat";

export type ProfessionCategory =
  // Бюджет и государство
  | "budget" | "government" | "medical" | "education"
  // Силовые
  | "military" | "law_enforcement"
  // Бизнес и финансы
  | "entrepreneur" | "finance" | "freelancer"
  // Рабочие
  | "worker" | "construction" | "transport" | "agriculture"
  // IT и интеллектуальные
  | "it_office" | "science" | "creative"
  // Торговля и сервис
  | "trade_service" | "sports"
  // Особые
  | "pensioner" | "homemaker" | "student" | "unemployed" | "disabled" | "clergy" | "special";

export type ProfessionGroup =
  | "budget_gov" | "military_law" | "business" | "workers"
  | "intellectual" | "trade_sport" | "special_cat";

// ─── Constructor Step Types ──────────────────────────────────────────────────

export type FamilyPreset = "random" | "single" | "married" | "married_kids" | "divorced" | "widow";
export type CreditorsPreset = "random" | "1" | "2_3" | "4_5" | "6_plus";
export type DebtStage = "random" | "pre_court" | "court_started" | "execution" | "arrest";
export type DebtRange = "random" | "under_500k" | "500k_1m" | "1m_3m" | "3m_10m" | "over_10m";
export type EmotionPreset = "neutral" | "anxious" | "angry" | "hopeful" | "tired" | "rushed" | "trusting";
export type BackgroundNoise = "none" | "office" | "street" | "children" | "tv";
export type TimeOfDay = "morning" | "afternoon" | "evening" | "night";
export type ClientFatigue = "fresh" | "normal" | "tired" | "exhausted";

export type TrapCategory =
  | "legal" | "emotional" | "manipulative" | "expert"
  | "price" | "provocative" | "professional" | "procedural";

export type MasteryLevel = "untrained" | "beginner" | "intermediate" | "advanced" | "mastered";

// ─── Emotion UI Config ─────────────────────────────────────────────────────

interface EmotionConfig {
  label: string;
  labelRu: string;
  color: string;
  glow: string;
  value: number;
}

/**
 * Full 10-state + 3 legacy alias emotion map.
 * Values are ordered 0→100 for thermometer/timeline display.
 */
export const EMOTION_MAP: Record<string, EmotionConfig> = {
  // ── 10 backend states (ordered by emotional progression) ──
  cold:         { label: "COLD",        labelRu: "Холодный",      color: "#8A2BE2", glow: "rgba(138,43,226,0.4)",  value: 5  },
  hostile:      { label: "HOSTILE",     labelRu: "Враждебный",    color: "var(--danger)", glow: "rgba(229,72,77,0.4)",   value: 0  },
  hangup:       { label: "HANGUP",      labelRu: "Бросил трубку", color: "#666666", glow: "rgba(102,102,102,0.4)", value: 0  },
  guarded:      { label: "GUARDED",     labelRu: "Настороже",     color: "var(--info)", glow: "rgba(59,130,246,0.4)",  value: 20 },
  testing:      { label: "TESTING",     labelRu: "Проверяет",     color: "var(--warning)", glow: "rgba(245,158,11,0.4)",  value: 25 },
  curious:      { label: "CURIOUS",     labelRu: "Любопытен",     color: "var(--gf-xp)", glow: "color-mix(in srgb, var(--gf-xp) 40%, transparent)",   value: 40 },
  callback:     { label: "CALLBACK",    labelRu: "Перезвонит",    color: "var(--info)", glow: "rgba(96,165,250,0.4)",  value: 45 },
  considering:  { label: "CONSIDERING", labelRu: "Обдумывает",    color: "var(--accent)", glow: "color-mix(in srgb, var(--accent) 40%, transparent)",  value: 60 },
  negotiating:  { label: "NEGOTIATING", labelRu: "Торгуется",     color: "var(--accent-hover)", glow: "rgba(167,139,250,0.4)", value: 75 },
  deal:         { label: "DEAL SYNC",   labelRu: "Сделка",        color: "var(--success)", glow: "color-mix(in srgb, var(--success) 40%, transparent)",   value: 95 },

  // ── Legacy aliases (backend LEGACY_MAP sends these) ──
  skeptical:    { label: "SKEPTICAL",   labelRu: "Скептичный",    color: "var(--info)", glow: "rgba(59,130,246,0.4)",  value: 20 },
  warming:      { label: "WARMING",     labelRu: "Теплеет",       color: "var(--gf-xp)", glow: "color-mix(in srgb, var(--gf-xp) 40%, transparent)",   value: 40 },
  open:         { label: "OPEN",        labelRu: "Открытый",      color: "var(--accent)", glow: "color-mix(in srgb, var(--accent) 40%, transparent)",  value: 60 },
};

// ─── Auth ──────────────────────────────────────────────────────────────────

export interface RegisterRequest {
  email: string;
  password: string;
  full_name: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  must_change_password: boolean;
}

export interface PasswordChangeRequest {
  old_password: string;
  new_password: string;
}

export interface ForgotPasswordRequest {
  email: string;
}

export interface ResetPasswordRequest {
  token: string;
  new_password: string;
}

// ─── User ──────────────────────────────────────────────────────────────────

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  avatar_url?: string | null;
  preferences?: Record<string, unknown> | null;
  onboarding_completed?: boolean;
  google_id?: string | null;
  yandex_id?: string | null;
  team?: string;
}

export interface UserProfileResponse {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  team_name: string | null;
  is_active: boolean;
  avatar_url: string | null;
  created_at: string;
  total_sessions: number;
  avg_score: number | null;
}

export interface UserStatsResponse {
  total_sessions: number;
  completed_sessions: number;
  avg_score: number | null;
  best_score: number | null;
  sessions_this_week: number;
  total_duration_minutes: number;
  achievements_count: number;
}

export interface UserPreferences {
  team: string | null;
  experience_level: string | null;
  tts_enabled: boolean;
  notifications: boolean;
  training_mode: string | null;
}

export interface UserListItem {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  team_name?: string | null;
  is_active: boolean;
  avatar_url?: string | null;
  created_at: string;
}

export interface FriendItem {
  friendship_id: string;
  user_id: string;
  full_name: string;
  email: string;
  avatar_url?: string | null;
  role: UserRole;
  status: "accepted" | "pending" | "none";
  direction: "incoming" | "outgoing" | "none";
  created_at: string;
  accepted_at: string | null;
}

export interface FriendSearchResponse {
  items: FriendItem[];
}

// ─── Consent ───────────────────────────────────────────────────────────────

export interface ConsentStatus {
  all_accepted: boolean;
  consents: Array<{
    consent_type: string;
    version: string;
    accepted: boolean;
    created_at: string;
  }>;
  missing: string[];
}

// ─── Scenario & Character ──────────────────────────────────────────────────

export interface Scenario {
  id: string;
  title: string;
  description: string;
  scenario_type: string;
  difficulty: number;
  estimated_duration_minutes: number;
  character_name?: string | null;
}

export interface ScenarioDetail extends Scenario {
  character: {
    id: string;
    name: string;
    slug: string;
    description: string;
    difficulty: number;
    initial_emotion: string;
  };
  script: {
    id: string;
    title: string;
    checkpoints: Array<{
      order: number;
      description: string;
      weight: number;
    }>;
  };
}

// ─── Training Session ──────────────────────────────────────────────────────

export interface TrainingSession {
  id: string;
  scenario_id: string;
  status: "active" | "completed" | "abandoned" | "error";
  started_at: string;
  ended_at: string | null;
  duration_seconds: number | null;
  score_script_adherence: number | null;
  score_objection_handling: number | null;
  score_communication: number | null;
  score_anti_patterns: number | null;
  score_result: number | null;
  score_total: number | null;
  // Wave 5: L6-L10 direct score fields
  score_chain_traversal: number | null;
  score_trap_handling: number | null;
  score_human_factor: number | null;
  score_narrative: number | null;
  score_legal: number | null;
  scoring_details: Record<string, unknown> | null;
  emotion_timeline: Array<{ state: string; timestamp: number }> | null;
  feedback_text: string | null;
  client_story_id?: string | null;
  call_number_in_story?: number | null;
  custom_params?: Record<string, unknown> | null;
}

export interface StoryCallSummary {
  session_id: string;
  call_number: number;
  status: "active" | "completed" | "abandoned" | "error";
  started_at: string;
  ended_at: string | null;
  duration_seconds: number | null;
  score_total: number | null;
  score_human_factor: number | null;
  score_narrative: number | null;
  score_legal: number | null;
}

export interface StorySummary {
  id: string;
  story_name: string;
  total_calls_planned: number;
  current_call_number: number;
  is_completed: boolean;
  game_status: string;
  tension: number;
  tension_curve: number[];
  pacing: string | null;
  next_twist: string | null;
  active_factors: Array<Record<string, unknown>>;
  between_call_events: Array<Record<string, unknown>>;
  consequences: Array<Record<string, unknown>>;
  started_at: string | null;
  ended_at: string | null;
  created_at: string | null;
  completed_calls: number;
  avg_score: number | null;
  best_score: number | null;
  latest_session_id: string | null;
}

export interface HistoryEntry {
  kind: "story" | "session";
  sort_at: string;
  latest_session: TrainingSession;
  story: StorySummary | null;
  sessions: StoryCallSummary[];
  calls_completed: number;
  avg_score: number | null;
  best_score: number | null;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  emotion_state: EmotionState | null;
  sequence_number: number;
  created_at: string;
}

export interface TrapResultItem {
  name: string;
  caught: boolean;
  bonus: number | null;
  penalty: number | null;
  status?: string | null;
  client_phrase?: string | null;
  correct_example?: string | null;
  explanation?: string | null;
  law_reference?: string | null;
  correct_keywords?: string[] | null;
  wrong_keywords?: string[] | null;
  category?: string | null;
}

export interface SoftSkillsResult {
  avg_response_time_sec: number;
  talk_listen_ratio: number;
  name_usage_count: number;
  interruptions: number;
  avg_message_length: number;
}

export interface CheckpointResultItem {
  name: string;
  hit: boolean;
  time?: string;
}

export interface ScoreBreakdown {
  script_adherence?: {
    score: number;
    checkpoints?: CheckpointResultItem[];
  };
  objection_handling?: {
    score: number;
    details?: Record<string, unknown>;
  };
  communication?: {
    score: number;
    details?: Record<string, unknown>;
  };
  anti_patterns?: {
    score: number;
    triggered?: string[];
  };
  result?: {
    score: number;
    details?: Record<string, unknown>;
  };
}

export interface SessionResultResponse {
  session: TrainingSession;
  messages: ChatMessage[];
  score_breakdown: ScoreBreakdown | null;
  trap_results: TrapResultItem[] | null;
  soft_skills: SoftSkillsResult | null;
  client_card: ClientProfile | null;
  story: StorySummary | null;
  story_calls: StoryCallSummary[];
  // Wave 4-5 additions
  weak_legal_categories?: Array<{
    category: string;
    display_name: string;
    accuracy_pct: number;
    article_refs: string[];
  }> | null;
  promise_fulfillment?: Array<{
    text: string;
    call_number: number;
    fulfilled: boolean;
    impact: string;
  }> | null;
  // XP/level data from session.ended WS message
  xp_breakdown?: Record<string, number> | null;
  level_up?: boolean;
  new_level?: number | null;
  new_level_name?: string | null;
}

// ─── Client Profile (CRM card) ────────────────────────────────────────────

export interface Creditor {
  name: string;
  amount: number;
}

export interface ClientProfile {
  full_name: string;
  age: number;
  gender: string;
  city: string;
  archetype_code: string;
  profession_name?: string;
  education_level: string;
  legal_literacy: number;
  total_debt: number;
  creditors: Creditor[];
  income: number | null;
  income_type: string;
  property_list: Array<{ type: string; status: string }>;
  lead_source: string;
  call_history: Array<{ event: string; date?: string; note?: string }>;
  crm_notes: string | null;
  // Hidden fields (revealed post-session via ClientReveal)
  fears?: string[];
  soft_spot?: string | null;
  breaking_point?: string | null;
  hidden_objections?: string[];
  trust_level?: number;
  resistance_level?: number;
}

// ─── Trap Events (WS) ─────────────────────────────────────────────────────

export interface TrapEvent {
  trap_name: string;
  category: TrapCategory;
  status: "fell" | "dodged" | "partial" | "not_activated";
  score_delta: number;
  wrong_keywords: string[];
  correct_keywords: string[];
  client_phrase: string;
  correct_example: string;
}

// ─── Objection Hint (WS) ──────────────────────────────────────────────────

export interface ObjectionHint {
  category: ObjectionCategory;
  message: string;
}

// ─── Checkpoint Hint (WS) ──────────────────────────────────────────────────

export interface CheckpointHint {
  checkpoint: string;
  status: "not_reached" | "in_progress";
}

// ─── Stage Update (WS) ────────────────────────────────────────────────────

export interface StageUpdate {
  stage_number: number;       // 1-7
  stage_name: string;         // "greeting", "contact", etc.
  stage_label: string;        // "Приветствие", "Контакт", etc.
  total_stages: number;       // 7
  stages_completed: number[]; // [1, 2, 3]
  stage_scores: Record<string, number>;  // {"1": 0.8, "2": 0.6}
  confidence: number;         // 0-1
}

// ─── Hangup Data (WS) ─────────────────────────────────────────────────────

export interface HangupData {
  reason: string;
  hangupPhrase: string;
  canContinue: boolean;   // multi-call: can redial
  triggers: string[];
}

// ─── Score Update (WS) ────────────────────────────────────────────────────

export interface ScoreUpdate {
  script_score: number;
  checkpoints_hit: number;
  checkpoints_total: number;
  checkpoints: Array<{
    id: string;
    title: string;
    order: number;
    hit: boolean;
    score: number;
  }>;
  /** Title of newly matched checkpoint (for toast/flash) */
  new_checkpoint?: string;
  /** True while session is active (real-time, ~70% accuracy) */
  is_preliminary?: boolean;
}

// ─── Coaching Whisper (WS) ────────────────────────────────────────────────

export type WhisperType = "legal" | "emotion" | "stage" | "objection" | "transition";

export interface CoachingWhisper {
  type: WhisperType;
  message: string;
  stage: string;
  priority: "high" | "medium" | "low";
  icon: string;
  /** Timestamp when received (set on frontend) */
  timestamp: number;
}

// ─── Soft Skills Update (WS) ──────────────────────────────────────────────

export interface SoftSkillsUpdate {
  talk_ratio: number;
  avg_response_time: number;
  name_count: number;
}

// ─── Assigned Training ─────────────────────────────────────────────────────

export interface AssignedTraining {
  id: string;
  user_id: string;
  scenario_id: string;
  scenario_title?: string;
  assigned_by: string;
  deadline: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface AssignTrainingRequest {
  user_id: string;
  scenario_id: string;
  deadline?: string | null;
}

// ─── Analytics ─────────────────────────────────────────────────────────────

export interface WeakSpot {
  skill: string;
  sub_skill: string | null;
  avg_score: number;
  max_possible: number;
  pct: number;
  trend: string;
  trend_delta: number;
  archetype: string | null;
  recommendation: string;
}

export interface ProgressPoint {
  period_start: string;
  period_end: string;
  sessions_count: number;
  avg_total: number;
  avg_script: number;
  avg_objection: number;
  avg_communication: number;
  avg_anti_patterns: number;
  avg_result: number;
  best_score: number;
  worst_score: number;
}

export interface ArchetypeScore {
  archetype_slug: string;
  archetype_name: string;
  sessions_count: number;
  avg_score: number;
  best_score: number;
  worst_score: number;
  avg_script: number;
  avg_objection: number;
  avg_communication: number;
  avg_anti_patterns: number;
  avg_result: number;
  last_played: string | null;
  mastery_level: MasteryLevel;
}

export interface Recommendation {
  scenario_id: string;
  scenario_title: string;
  archetype_slug: string;
  scenario_type: string;
  difficulty: number;
  reason: string;
  priority: number;
}

export interface AnalyticsSnapshot {
  weak_spots: WeakSpot[];
  progress: ProgressPoint[];
  archetype_scores: ArchetypeScore[];
  recommendations: Recommendation[];
  insights: string[];
  meta: Record<string, unknown>;
}

// ─── Gamification ──────────────────────────────────────────────────────────

export interface Achievement {
  id: string;
  slug: string;
  title: string;
  description: string;
  icon_url?: string | null;
  earned_at?: string | null;
}

export interface GamificationProgress {
  total_xp: number;
  level: number;
  xp_current_level: number;
  xp_next_level: number;
  streak_days: number;
  achievements: Achievement[];
}

export interface LeaderboardEntry {
  rank: number;
  user_id: string;
  full_name: string;
  avatar_url?: string | null;
  sessions_count: number;
  total_score: number;
  avg_score: number;
}

export interface DailyChallenge {
  challenge: {
    type: string;
    title: string;
    description: string;
    xp_bonus: number;
    target?: number;
  };
  scenario: Scenario;
  date: string;
}

// ─── Dashboard ─────────────────────────────────────────────────────────────

export interface ManagerStats {
  total_sessions: number;
  completed_sessions: number;
  avg_score: number | null;
  best_score: number | null;
  sessions_this_week: number;
  total_duration_minutes: number;
}

export interface RecentSession {
  id: string;
  status: string;
  score_total: number | null;
  started_at: string | null;
  duration_seconds: number | null;
}

export interface DashboardRecommendation {
  scenario_id: string;
  title: string;
  archetype: string;
  difficulty: number;
  reason: string;
  tags: string[];
}

export interface DashboardAssignment {
  id: string;
  scenario_title: string;
  deadline: string | null;
}

export interface DashboardTournament {
  id: string;
  title: string;
  scenario_id: string;
  week_end: string;
  leaderboard: TournamentLeaderboardEntry[];
}

export interface DashboardManager {
  stats: ManagerStats;
  recent_sessions: RecentSession[];
  gamification: {
    total_xp: number;
    level: number;
    xp_current_level: number;
    xp_next_level: number;
    streak_days: number;
  };
  recommendations: DashboardRecommendation[];
  assignments: DashboardAssignment[];
  tournament: DashboardTournament | null;
}

export interface TeamStats {
  team_name: string;
  total_members: number;
  active_members: number;
  total_sessions: number;
  avg_score: number | null;
  best_performer: string | null;
  sessions_this_week: number;
}

export interface TeamMember {
  id: string;
  full_name: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  avatar_url?: string | null;
  total_sessions: number;
  avg_score: number | null;
  best_score: number | null;
  sessions_this_week: number;
}

export interface DashboardROP {
  team: {
    name: string;
    total_members: number;
    active_members: number;
  };
  stats: {
    total_sessions: number;
    avg_score: number | null;
    active_this_week: number;
    best_performer: string | null;
  };
  members: TeamMember[];
  tournament: DashboardTournament | null;
}

// ─── Tournament ────────────────────────────────────────────────────────────

export interface Tournament {
  id: string;
  title: string;
  description: string;
  scenario_id: string;
  week_start: string;
  week_end: string;
  is_active: boolean;
  max_attempts: number;
  bonus_xp_first: number;
  bonus_xp_second: number;
  bonus_xp_third: number;
}

export interface TournamentLeaderboardEntry {
  rank: number;
  user_id: string;
  full_name: string;
  avatar_url?: string | null;
  best_score: number;
  attempts: number;
  is_podium: boolean;
}

export interface TournamentResponse {
  tournament: Tournament;
  leaderboard: TournamentLeaderboardEntry[];
}

export interface ActiveTournamentResponse {
  tournament: (Omit<Tournament, "bonus_xp_first" | "bonus_xp_second" | "bonus_xp_third" | "is_active"> & { bonus_xp: [number, number, number] }) | null;
  leaderboard: TournamentLeaderboardEntry[];
}

export interface TournamentSubmitResponse {
  entry_id: string;
  attempt: number;
  score: number;
}

// ─── Custom Client Profile (Character Builder) ────────────────────────────

export interface CustomClientProfile {
  id: string;
  name: string;
  archetype_code: ArchetypeCode;
  profession_code: string;
  lead_source: LeadSource;
  difficulty: number;
  financial_profile: Record<string, unknown>;
  custom_traits: Record<string, unknown>;
  created_at?: string;
}

// ─── Training Stats (legacy, used in profile) ─────────────────────────────

export interface TrainingStats {
  total_sessions: number;
  completed_sessions: number;
  average_score: number | null;
  best_score: number | null;
  total_duration_minutes: number;
}

// ─── CRM Client ───────────────────────────────────────────────────────────

export type ClientStatus =
  | "new" | "contacted" | "interested" | "consultation"
  | "thinking" | "consent_given" | "contract_signed"
  | "in_process" | "paused" | "completed"
  | "lost" | "consent_revoked";

export const CLIENT_STATUS_LABELS: Record<ClientStatus, string> = {
  new: "Новый",
  contacted: "Контакт",
  interested: "Интерес",
  consultation: "Консультация",
  thinking: "Думает",
  consent_given: "Согласие",
  contract_signed: "Договор",
  in_process: "В процессе",
  paused: "Пауза",
  completed: "Завершён",
  lost: "Потерян",
  consent_revoked: "Отзыв согласия",
};

export const CLIENT_STATUS_COLORS: Record<ClientStatus, string> = {
  new: "var(--text-muted)",
  contacted: "var(--gf-xp)",
  interested: "var(--info)",
  consultation: "var(--accent)",
  thinking: "var(--accent-hover)",
  consent_given: "var(--success)",
  contract_signed: "var(--warning)",
  in_process: "var(--accent)",
  paused: "var(--text-muted)",
  completed: "var(--success)",
  lost: "var(--danger)",
  consent_revoked: "var(--danger)",
};

/** Active pipeline statuses shown on Kanban board (excludes terminal/special). */
export const PIPELINE_STATUSES: ClientStatus[] = [
  "new", "contacted", "interested", "consultation",
  "thinking", "consent_given", "contract_signed",
  "in_process", "completed",
];

/** Allowed status transitions per backend ALLOWED_STATUS_TRANSITIONS. */
export const ALLOWED_TRANSITIONS: Record<ClientStatus, ClientStatus[]> = {
  new: ["contacted", "lost"],
  contacted: ["interested", "consultation", "lost"],
  interested: ["consultation", "lost"],
  consultation: ["consent_given", "thinking", "lost"],
  thinking: ["consent_given", "lost"],
  consent_given: ["contract_signed", "consent_revoked"],
  contract_signed: ["in_process", "consent_revoked"],
  in_process: ["completed", "paused"],
  paused: ["in_process", "lost"],
  completed: [],
  lost: ["contacted"],
  consent_revoked: ["thinking", "lost"],
};

// ─── CRM Enums ────────────────────────────────────────────────────────────

export type InteractionType =
  | "outbound_call" | "inbound_call" | "sms_sent" | "whatsapp_sent"
  | "email_sent" | "meeting" | "status_change" | "consent_event"
  | "note" | "system";

export const INTERACTION_TYPE_LABELS: Record<InteractionType, string> = {
  outbound_call: "Исходящий звонок",
  inbound_call: "Входящий звонок",
  sms_sent: "SMS",
  whatsapp_sent: "WhatsApp",
  email_sent: "Email",
  meeting: "Встреча",
  status_change: "Смена статуса",
  consent_event: "Событие согласия",
  note: "Заметка",
  system: "Системное",
};

export type ConsentType =
  | "data_processing" | "contact_allowed" | "consultation_agreed"
  | "bfl_procedure" | "marketing";

export const CONSENT_TYPE_LABELS: Record<ConsentType, string> = {
  data_processing: "Обработка данных",
  contact_allowed: "Разрешение на связь",
  consultation_agreed: "Согласие на консультацию",
  bfl_procedure: "Процедура БФЛ",
  marketing: "Маркетинг",
};

export type ConsentChannel =
  | "phone_call" | "sms_link" | "web_form" | "whatsapp"
  | "in_person" | "email_link";

export const CONSENT_CHANNEL_LABELS: Record<ConsentChannel, string> = {
  phone_call: "Телефонный звонок",
  sms_link: "SMS-ссылка",
  web_form: "Веб-форма",
  whatsapp: "WhatsApp",
  in_person: "Лично",
  email_link: "Email-ссылка",
};

// ─── CRM Client Interfaces ───────────────────────────────────────────────

export interface CRMClient {
  id: string;
  manager_id: string | null;
  manager_name: string | null;
  full_name: string;
  phone: string | null;
  email: string | null;
  status: ClientStatus;
  is_active: boolean;
  debt_amount: number | null;
  debt_details: Record<string, unknown> | null;
  source: string | null;
  notes: string | null;
  next_contact_at: string | null;
  lost_reason: string | null;
  lost_count: number;
  last_status_change_at: string | null;
  created_at: string;
  updated_at: string;
  active_consents?: ClientConsent[];
  recent_interactions?: ClientInteraction[];
}

export interface CRMClientDetail extends CRMClient {
  interactions: ClientInteraction[];
  consents: ClientConsent[];
  creditors: Creditor[];
  income: number | null;
  city: string | null;
  tags: string[];
}

export interface ClientInteraction {
  id: string;
  client_id: string;
  manager_id: string | null;
  manager_name: string | null;
  interaction_type: InteractionType;
  content: string | null;
  result: string | null;
  duration_seconds: number | null;
  old_status: string | null;
  new_status: string | null;
  created_at: string;
}

export interface ClientConsent {
  id: string;
  client_id: string;
  consent_type: ConsentType | string;
  channel: ConsentChannel | string | null;
  legal_text_version: string | null;
  granted_at: string;
  revoked_at: string | null;
  revoked_reason: string | null;
  recorded_by: string | null;
  recorder_name: string | null;
  evidence_url: string | null;
  is_active: boolean;
  created_at: string;
}

export interface ClientListParams {
  status?: ClientStatus;
  search?: string;
  assigned_to?: string;
  page?: number;
  limit?: number;
}

export interface ClientListResponse {
  items: CRMClient[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export interface PipelineStats {
  status: ClientStatus;
  count: number;
  total_debt: number;
}

// ─── Activity Feed ────────────────────────────────────────────────────────

export type ActivityEventType =
  | "session_completed"
  | "new_record"
  | "rank_change"
  | "achievement_unlocked";

export interface ActivityFeedItem {
  id: string;
  type: ActivityEventType;
  user_id: string;
  user_name: string;
  message: string;
  score?: number | null;
  created_at: string;
}

// ─── Notifications ────────────────────────────────────────────────────────

export type NotificationType =
  | "reminder" | "assignment" | "achievement" | "system"
  | "status_change" | "consent" | "overdue";

export type NotificationChannel = "in_app" | "push" | "sms" | "whatsapp" | "email";

export type NotificationStatus = "pending" | "sent" | "delivered" | "read" | "failed";

export interface AppNotification {
  id: string;
  title: string;
  body: string | null;
  channel: NotificationChannel;
  status: NotificationStatus;
  client_id: string | null;
  client_name: string | null;
  read_at: string | null;
  created_at: string;
}

export interface NotificationListResponse {
  items: AppNotification[];
  total: number;
  unread_count: number;
}

export interface ReminderItem {
  id: string;
  manager_id: string;
  client_id: string;
  client_name: string | null;
  remind_at: string;
  message: string | null;
  is_completed: boolean;
  completed_at: string | null;
  auto_generated: boolean;
  created_at: string;
}

// ─── WebSocket ─────────────────────────────────────────────────────────────

export type WSConnectionState = "connecting" | "connected" | "disconnected" | "reconnecting" | "error";

export interface WSMessage {
  type: string;
  data: Record<string, unknown>;
}

// ─── v6: Session Resume + Token Refresh WS payloads ──────────────────────

export interface WSSessionResumed {
  session_id: string;
  elapsed_seconds: number;
  message_count: number;
  emotion: string;
}

export interface WSMessageReplay {
  role: "user" | "assistant";
  content: string;
  emotion?: string;
  sequence_number?: number;
  timestamp?: number;
}

export interface WSAuthRefreshed {
  access_token: string;
  refresh_token: string;
}

export interface WSAuthRefreshError {
  reason: "no_token" | "refresh_expired" | "invalid_token" | "user_mismatch" | "invalid_token_type";
}

// ─── Microphone ────────────────────────────────────────────────────────────

export type MicrophonePermissionState = "prompt" | "granted" | "denied" | "error";

export type RecordingState = "idle" | "recording" | "processing";

// ─── Training Session UI State ─────────────────────────────────────────────

export type SessionState = "connecting" | "briefing" | "ready" | "completed";

// ─── Chat UI ───────────────────────────────────────────────────────────────

export interface ChatBubble {
  id: string;
  role: "user" | "assistant";
  content: string;
  emotion?: EmotionState;
  timestamp: string;
  /** Backend sequence number (used for session resume replay) */
  sequenceNumber?: number;
  /** True if this message was replayed during session resume */
  isReplay?: boolean;
  /** True if this is a fallback response from the server */
  is_fallback?: boolean;
  /** True while this message is being streamed (content may be partial) */
  isStreaming?: boolean;
}

// ─── Transcription ─────────────────────────────────────────────────────────

export interface TranscriptionState {
  status: "idle" | "transcribing" | "done";
  partial: string;
  final: string;
}

// ─── WS Event Payloads (typed helpers for switch/case in training page) ───

export interface WSSessionStarted {
  session_id: string;
  scenario: Scenario;
  character: {
    name: string;
    slug: string;
    description: string;
  };
  client_profile: ClientProfile;
  initial_emotion: EmotionState;
}

export interface WSCharacterResponse {
  content: string;
  emotion: EmotionState;
  model?: string;
  latency_ms?: number;
  is_fallback?: boolean;
  is_silence_prompt?: boolean;
}

export interface WSTranscriptionResult {
  text: string;
  confidence: number;
  is_final: boolean;
  language: string;
}

export interface WSTtsAudio {
  audio_b64: string;
  format: string;
  text: string;
  emotion?: string;
  voice_params?: Record<string, unknown>;
  duration_ms?: number;
}

export interface WSTtsCoupleAudio {
  utterances: Array<{
    speaker: string;
    audio_b64: string;
    text: string;
  }>;
}

export interface WSEmotionUpdate {
  previous: EmotionState;
  current: EmotionState;
}

export interface WSSilenceTimeout {
  message: string;
  timeout_seconds: number;
}

export interface WSError {
  message: string;
  code: "error" | "rate_limit" | "session_not_found" | "auth_error";
}

// ─── Game CRM (Agent 7, spec 10.1-10.3) ──────────────────────────────────

export type GameEventType = "call" | "message" | "consequence" | "storylet" | "status_change" | "callback";

export type GameClientStatus =
  | "new" | "contacted" | "interested" | "thinking"
  | "consent_given" | "documents" | "contract_signed"
  | "in_process" | "completed" | "lost";

export const GAME_STATUS_LABELS: Record<GameClientStatus, string> = {
  new: "Новый",
  contacted: "Контакт",
  interested: "Интерес",
  thinking: "Думает",
  consent_given: "Согласие",
  documents: "Документы",
  contract_signed: "Договор",
  in_process: "В процессе",
  completed: "Завершён",
  lost: "Потерян",
};

export const GAME_STATUS_COLORS: Record<GameClientStatus, string> = {
  new: "var(--text-muted)",
  contacted: "var(--gf-xp)",
  interested: "var(--info)",
  thinking: "var(--accent-hover)",
  consent_given: "var(--success)",
  documents: "var(--warning)",
  contract_signed: "var(--warning)",
  in_process: "var(--accent)",
  completed: "var(--success)",
  lost: "var(--danger)",
};

export const GAME_EVENT_ICONS: Record<GameEventType, string> = {
  call: "📞",
  message: "💬",
  consequence: "⚡",
  storylet: "📖",
  status_change: "🔄",
  callback: "📅",
};

export const GAME_EVENT_LABELS: Record<GameEventType, string> = {
  call: "Звонок",
  message: "Сообщение",
  consequence: "Последствие",
  storylet: "Событие",
  status_change: "Смена статуса",
  callback: "Обратный звонок",
};

export interface GameTimelineEvent {
  id: string;
  timestamp: string;
  type: GameEventType;
  source: string;
  title: string;
  content: string | null;
  payload: Record<string, unknown>;
  severity: number | null;
  narrative_date: string | null;
  session_id: string | null;
  is_read: boolean;
}

export interface GameStory {
  id: string;
  story_name: string;
  total_calls_planned: number;
  current_call_number: number;
  is_completed: boolean;
  game_status: GameClientStatus;
  tension: number;
  event_count: number;
  calls_completed: number;
  avg_score: number | null;
  best_score: number | null;
  created_at: string | null;
  started_at: string | null;
}

export interface GameStoryDetail extends GameStory {
  user_id: string;
  client_profile_id: string | null;
  tension_curve: number[];
  pacing: string;
  next_twist: string | null;
  active_factors: unknown[];
  between_call_events: unknown[];
  consequences: unknown[];
  calls_completed: number;
  avg_score: number | null;
  best_score: number | null;
  personality_profile: Record<string, unknown>;
  ended_at: string | null;
}

export interface GamePortfolioStats {
  total_stories: number;
  completed: number;
  active: number;
  avg_score: number;
  total_calls: number;
  avg_calls_per_story: number;
  status_breakdown: Record<string, number>;
  recent_events: GameTimelineEvent[];
  trend: {
    direction: "up" | "down" | "stable";
    change_pct: number;
  };
  period: string;
}

// ─── PvP Arena ───────────────────────────────────────────────────────────────

export type PvPRankTier = "unranked" | "iron" | "bronze" | "silver" | "gold" | "platinum" | "diamond" | "master" | "grandmaster";

export type DuelStatus =
  | "pending" | "round_1" | "swap" | "round_2"
  | "judging" | "completed" | "cancelled" | "disputed";

export type DuelDifficulty = "easy" | "medium" | "hard";

export const PVP_RANK_LABELS: Record<PvPRankTier, string> = {
  unranked: "Без ранга",
  iron: "Железо",
  bronze: "Бронза",
  silver: "Серебро",
  gold: "Золото",
  platinum: "Платина",
  diamond: "Даймонд",
  master: "Мастер",
  grandmaster: "Грандмастер",
};

export const PVP_RANK_COLORS: Record<PvPRankTier, string> = {
  unranked: "var(--text-muted)",
  iron: "var(--text-muted)",
  bronze: "#B45309",
  silver: "var(--text-muted)",
  gold: "var(--warning)",
  platinum: "#22D3EE",
  diamond: "var(--info)",
  master: "var(--danger)",
  grandmaster: "#FF6B35",
};

export type RatingType = "training_duel" | "knowledge_arena";

export const PVP_DIFFICULTY_LABELS: Record<DuelDifficulty, string> = {
  easy: "Лёгкий",
  medium: "Средний",
  hard: "Сложный",
};

export interface PvPRating {
  user_id: string;
  rating: number;
  rd: number;
  volatility: number;
  rank_tier: PvPRankTier;
  rank_display: string;
  wins: number;
  losses: number;
  draws: number;
  total_duels: number;
  placement_done: boolean;
  placement_count: number;
  peak_rating: number;
  peak_tier: PvPRankTier;
  current_streak: number;
  best_streak: number;
  last_played: string | null;
}

export interface PvPDuel {
  id: string;
  player1_id: string;
  player2_id: string;
  status: DuelStatus;
  difficulty: DuelDifficulty;
  round_number: number;
  player1_total: number;
  player2_total: number;
  winner_id: string | null;
  is_draw: boolean;
  is_pve: boolean;
  duration_seconds: number;
  round_1_data: Record<string, unknown> | null;
  round_2_data: Record<string, unknown> | null;
  anti_cheat_flags: Record<string, unknown>[] | null;
  replay_url: string | null;
  player1_rating_delta: number;
  player2_rating_delta: number;
  rating_change_applied: boolean;
  created_at: string;
  completed_at: string | null;
}

export interface PvPLeaderboardEntry {
  rank: number;
  user_id: string;
  username: string;
  avatar_url?: string | null;
  rating: number;
  rank_tier: PvPRankTier;
  rank_display: string;
  wins: number;
  losses: number;
  total_duels: number;
  current_streak: number;
}

export interface PvPLeaderboardResponse {
  season: string | null;
  entries: PvPLeaderboardEntry[];
  total_players: number;
}

export interface PvPSeason {
  id: string;
  name: string;
  start_date: string;
  end_date: string;
  is_active: boolean;
  rewards: Record<string, unknown> | null;
}

export interface CharacterBrief {
  name: string;
  brief: string;
  behavior: string;
}

export interface DuelBrief {
  duel_id: string;
  your_role: "seller" | "client";
  archetype: string | null;
  character_brief: CharacterBrief | null;
  human_factors: Record<string, unknown> | null;
  difficulty: DuelDifficulty;
  scenario_title: string | null;
  round_number: number;
  time_limit_seconds: number;
}

// ─── Arena Knowledge PvP Types ─────────────────────────────────────────────

export interface ArenaPlayer {
  user_id: string;
  name: string;
  score: number;
  correct: number;
  is_bot: boolean;
  rating: number;
  rating_delta?: number;
}

export interface ArenaRoundResult {
  round_number: number;
  question: string;
  correct_answer: string;
  explanation: string;
  article_ref: string | null;
  players: {
    user_id: string;
    name: string;
    answer: string;
    score: number;
    speed_bonus: number;
    is_correct: boolean;
    comment: string;
  }[];
}

export interface ArenaFinalResults {
  rankings: (ArenaPlayer & { rank: number })[];
  total_rounds: number;
  contains_bot: boolean;
}

export interface ArenaChallenge {
  challenge_id: string;
  challenger_id: string;
  challenger_name: string;
  category: string | null;
  max_players: number;
}

// ─── Wave 5: Replay Mode ──────────────────────────────────────────────────

export interface IdealResponseResult {
  message_id: string;
  message_index: number;
  original_text: string;
  ideal_text: string;
  explanation: string;
  original_score_estimate: number | null;
  ideal_score_estimate: number | null;
  score_delta: number | null;
  layer_impact: Record<string, string> | null;
  original_emotion: string | null;
  ideal_emotion_prediction: string | null;
  emotion_explanation: string | null;
  trap_handling: Array<{
    trap: string;
    original: string;
    ideal: string;
    how?: string;
  }> | null;
}

// ─── DOC_17: Frontend UI Types ───────────────────────────────────────────────

export interface CheckpointMarker {
  id: string;
  code: string;
  name: string;
  description: string;
  progress: { current: number; required: number };
  status: "completed" | "in_progress" | "locked";
  xp_reward: number;
  category: string;
  recommended_scenario?: string;
}

export interface CheckpointProgressBarProps {
  level: number;
  levelName: string;
  currentXP: number;
  requiredXP: number;
  checkpoints: CheckpointMarker[];
}

export interface HunterCardData {
  nickname: string;
  level: number;
  levelName: string;
  pvpRank: string;
  pvpRating: number;
  wins: number;
  losses: number;
  knowledgeAccuracy: number;
  streak: number;
  featuredAchievements: string[];
  reputationTier: number;
  hunterScore: number;
  seasonName: string;
  skillRadar: Record<SkillCode, number>;
}

export interface CrossRecommendation {
  source: "correlation" | "pvp_weakness" | "gap_analysis" | "achievement";
  title: string;
  description: string;
  actions: Array<{ mode: string; label: string; params?: Record<string, unknown> }>;
  priority: "critical" | "high" | "medium" | "low";
}

export interface SeasonPassTier {
  tier: number;
  sp_required: number;
  reward_free: string | null;
  reward_premium: string | null;
  is_claimed: boolean;
}

export type PvPRankTierDisplay =
  | "iron_3" | "iron_2" | "iron_1"
  | "bronze_3" | "bronze_2" | "bronze_1"
  | "silver_3" | "silver_2" | "silver_1"
  | "gold_3" | "gold_2" | "gold_1"
  | "platinum_3" | "platinum_2" | "platinum_1"
  | "diamond_3" | "diamond_2" | "diamond_1"
  | "master_3" | "master_2" | "master_1"
  | "grandmaster" | "unranked";
