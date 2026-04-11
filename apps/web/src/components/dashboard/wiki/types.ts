import { Warning, TrendUp, Lightning } from "@phosphor-icons/react";

/* ─── Types ─── */

export interface ManagerWikiSummary {
  wiki_id: string;
  manager_id: string;
  manager_name: string;
  manager_role: string;
  status: string;
  sessions_ingested: number;
  patterns_discovered: number;
  pages_count: number;
  total_tokens_used: number;
  last_ingest_at: string | null;
  created_at: string | null;
}

export interface WikiPageItem {
  id: string;
  page_path: string;
  page_type: string;
  version: number;
  tags: string[];
  updated_at: string | null;
}

export interface WikiPageContent {
  id: string;
  page_path: string;
  content: string;
  page_type: string;
  version: number;
  tags: string[];
  source_sessions: string[];
}

export interface PatternItem {
  id: string;
  pattern_code: string;
  category: string;
  description: string;
  sessions_in_pattern: number;
  is_confirmed: boolean;
  mitigation_technique: string | null;
  impact_on_score_delta: number | null;
}

export interface TechniqueItem {
  id: string;
  technique_code: string;
  technique_name: string;
  description: string;
  success_rate: number;
  success_count: number;
  attempt_count: number;
  applicable_to_archetype: string | null;
  how_to_apply: string | null;
}

export interface WikiLogEntry {
  id: string;
  action: string;
  description: string | null;
  pages_modified: number;
  pages_created: number;
  patterns_discovered: string[];
  tokens_used: number;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  error_msg: string | null;
}

export interface GlobalStats {
  total_wikis: number;
  total_sessions_ingested: number;
  total_patterns_discovered: number;
  total_pages: number;
  total_tokens_used: number;
}

export interface SchedulerStatus {
  running: boolean;
  last_ingest_run: string | null;
  last_daily_run: string | null;
  last_weekly_run: string | null;
  stats: {
    total_ingests: number;
    total_daily_syntheses: number;
    total_weekly_syntheses: number;
    errors: number;
  };
  config: {
    ingest_interval_hours: number;
    daily_synthesis_hour_utc: number;
    weekly_synthesis_day: string;
    weekly_synthesis_hour_utc: number;
  };
}

export interface WikiChartData {
  period_days: number;
  daily_sessions: { date: string; sessions: number; avg_score: number }[];
  pattern_distribution: { category: string; count: number }[];
  wiki_activity: { date: string; ingests: number; pages_created: number; pages_modified: number }[];
  top_managers: { manager_id: string; name: string; sessions: number; patterns: number; pages: number }[];
}

export interface EnrichedProfile {
  manager_id: string;
  name: string;
  training: {
    total_sessions: number;
    avg_score: number;
    best_score: number;
    total_hours: number;
    recent_14d_sessions: number;
    recent_14d_avg_score: number;
    score_trend: { score: number; date: string }[];
  };
  skills: Record<string, number>;
  pipeline: Record<string, any>;
  wiki: { exists: boolean; pages_count: number; sessions_ingested: number; patterns_discovered: number };
  patterns_summary: {
    total: number;
    weaknesses: number;
    strengths: number;
    top_weaknesses: { code: string; description: string; sessions: number }[];
    top_strengths: { code: string; description: string; sessions: number }[];
  };
  techniques_summary: {
    total: number;
    best: { code: string; name: string; success_rate: number; attempts: number }[];
  };
}

export interface CompareManager {
  manager_id: string;
  name: string;
  sessions_total: number;
  avg_score: number;
  best_score: number;
  worst_score: number;
  score_layers: Record<string, number>;
  skills: Record<string, number>;
  patterns_total: number;
  patterns_by_category: Record<string, number>;
  patterns: { code: string; category: string; description: string; sessions_count: number; confirmed: boolean }[];
  techniques_total: number;
  techniques: { code: string; name: string; success_rate: number; attempts: number }[];
  wiki_pages: number;
  wiki_sessions_ingested: number;
}

export type View = "list" | "detail";
export type DetailTab = "pages" | "patterns" | "techniques" | "log" | "charts" | "profile";

/* ─── Category config ─── */

export const CATEGORY_CONFIG: Record<string, { label: string; color: string; icon: typeof Warning }> = {
  weakness: { label: "Слабость", color: "var(--danger)", icon: Warning },
  strength: { label: "Сила", color: "var(--success)", icon: TrendUp },
  quirk: { label: "Особенность", color: "var(--warning)", icon: Lightning },
  misconception: { label: "Заблуждение", color: "var(--accent)", icon: Warning },
};

export const ACTION_LABELS: Record<string, string> = {
  ingest_session: "Анализ сессии",
  daily_synthesis: "Дневной синтез",
  weekly_synthesis: "Недельный синтез",
  monthly_review: "Месячный обзор",
  lint_pass: "Lint pass",
  manual_edit: "Ручная правка",
  rebuild_page: "Перестроение страницы",
  pattern_discovered: "Новый паттерн",
  technique_discovered: "Новая техника",
};
