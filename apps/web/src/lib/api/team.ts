/**
 * Team panel typed API client (TZ-Команда PR).
 *
 * Three endpoints share the /team prefix:
 *   POST /team/assignments/bulk      — bulk-assign training (rop+admin)
 *   GET  /team/analytics             — team-wide aggregates  (rop+admin)
 *   POST /team/users/import-csv      — bulk-create from CSV  (admin)
 */
import { api } from "@/lib/api";

export interface BulkAssignRowResult {
  user_id: string;
  status:
    | "assigned"
    | "skipped_other_team"
    | "skipped_user_not_found"
    | "error";
  assignment_id: string | null;
  error: string | null;
}

export interface BulkAssignResponse {
  scenario_id: string;
  total: number;
  assigned: number;
  skipped: number;
  errors: number;
  rows: BulkAssignRowResult[];
}

export const bulkAssignTraining = (
  scenarioId: string,
  userIds: string[],
  deadline?: string,
): Promise<BulkAssignResponse> =>
  api.post<BulkAssignResponse>("/team/assignments/bulk", {
    scenario_id: scenarioId,
    user_ids: userIds,
    deadline: deadline ?? null,
  });

export interface TeamAnalyticsManagerSummary {
  user_id: string;
  full_name: string;
  sessions_30d: number;
  avg_score_30d: number | null;
  days_since_last_session: number | null;
  is_active: boolean;
}

export interface TeamAnalyticsResponse {
  team_avg_score_30d: number | null;
  team_total_sessions_30d: number;
  managers_with_zero_sessions_30d: number;
  managers: TeamAnalyticsManagerSummary[];
}

export const fetchTeamAnalytics = (): Promise<TeamAnalyticsResponse> =>
  api.get<TeamAnalyticsResponse>("/team/analytics");

export interface CsvImportRowResult {
  line: number;
  email: string;
  status:
    | "created"
    | "skipped_duplicate_email"
    | "skipped_invalid"
    | "error";
  user_id: string | null;
  error: string | null;
}

export interface CsvImportResponse {
  total: number;
  created: number;
  skipped: number;
  errors: number;
  rows: CsvImportRowResult[];
}

export const importUsersCsv = (file: File): Promise<CsvImportResponse> =>
  api.uploadMultipart<CsvImportResponse>("/team/users/import-csv", () => {
    const fd = new FormData();
    fd.append("file", file);
    return fd;
  });
