/**
 * TZ-5 PR-2 — typed API client for the multi-route import surface.
 *
 * Three branches share one /imports endpoint with auto-classification:
 *   scenario        → ScenarioTemplate
 *   character       → custom_characters
 *   arena_knowledge → legal_knowledge_chunks
 *
 * The FE wizard calls `uploadImportMaterial(file, consent, forced?)`. The
 * backend classifier picks the route unless `forced` is set.
 */
import { api } from "@/lib/api";

export type ImportRouteType = "scenario" | "character" | "arena_knowledge";
export type ImportDraftStatus =
  | "extracting"
  | "ready"
  | "edited"
  | "converted"
  | "discarded"
  | "failed";

export interface ScenarioStepDraft {
  order: number;
  name: string;
  description: string;
  manager_goals: string[];
  expected_client_reaction: string | null;
}

export interface ScenarioPayload {
  title_suggested: string;
  summary: string;
  archetype_hint: string | null;
  steps: ScenarioStepDraft[];
  expected_objections: string[];
  success_criteria: string[];
  quotes_from_source: string[];
  confidence: number;
}

export interface CharacterPayload {
  name: string;
  archetype_hint: string | null;
  description: string;
  personality_traits: string[];
  typical_objections: string[];
  speech_patterns: string[];
  quotes_from_source: string[];
  confidence: number;
}

export interface ArenaKnowledgePayload {
  fact_text: string;
  law_article: string | null;
  category: string;
  difficulty_level: number;
  match_keywords: string[];
  common_errors: string[];
  correct_response_hint: string;
  quotes_from_source: string[];
  confidence: number;
}

// Discriminated union — the FE uses `route_type` to switch the editor.
export type ImportPayload = ScenarioPayload | CharacterPayload | ArenaKnowledgePayload;

export interface ImportDraft {
  id: string;
  attachment_id: string;
  attachment_filename: string | null;
  route_type: ImportRouteType;
  target_id: string | null;
  scenario_template_id: string | null;
  status: ImportDraftStatus;
  confidence: number;
  original_confidence: number | null;
  extracted_visible: boolean;
  extracted: ImportPayload | null;
  // Only present when ?include_raw=1; never in list responses.
  extracted_raw?: ImportPayload;
  download_url: string;
  source_text: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface ImportListResponse {
  drafts: ImportDraft[];
  total: number;
  page: number;
  page_size: number;
}

export interface ImportListParams {
  status?: ImportDraftStatus;
  route_type?: ImportRouteType;
  only_mine?: boolean;
  page?: number;
  page_size?: number;
}

export async function uploadImportMaterial(
  file: File,
  consent: boolean,
  forcedRouteType?: ImportRouteType,
): Promise<ImportDraft & { message?: string }> {
  return api.uploadMultipart<ImportDraft & { message?: string }>(
    "/rop/imports",
    () => {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("consent_152fz", String(consent));
      if (forcedRouteType) fd.append("forced_route_type", forcedRouteType);
      return fd;
    },
  );
}

export const listImports = (params: ImportListParams = {}): Promise<ImportListResponse> => {
  const qs = new URLSearchParams();
  if (params.status) qs.set("status", params.status);
  if (params.route_type) qs.set("route_type", params.route_type);
  if (params.only_mine) qs.set("only_mine", "true");
  if (params.page) qs.set("page", String(params.page));
  if (params.page_size) qs.set("page_size", String(params.page_size));
  const tail = qs.toString();
  return api.get<ImportListResponse>(`/rop/imports${tail ? "?" + tail : ""}`);
};

export const getImportDraft = (id: string, includeRaw = false): Promise<ImportDraft> =>
  api.get<ImportDraft>(`/rop/scenarios/drafts/${id}${includeRaw ? "?include_raw=1" : ""}`);

export const updateImportDraft = (
  id: string,
  body: { extracted?: ImportPayload; confidence?: number },
): Promise<ImportDraft> => api.put<ImportDraft>(`/rop/scenarios/drafts/${id}`, body);

export const convertScenarioDraft = (
  id: string,
): Promise<{ template_id: string; version_id: string; message: string }> =>
  api.post(`/rop/scenarios/drafts/${id}/create-scenario`, {});

export const approveCharacterDraft = (
  id: string,
): Promise<{ character_id: string; message: string }> =>
  api.post(`/rop/imports/${id}/approve-character`, {});

export const approveArenaKnowledgeDraft = (
  id: string,
): Promise<{ chunk_id: string; message: string }> =>
  api.post(`/rop/imports/${id}/approve-arena-knowledge`, {});

export const discardImportDraft = (
  id: string,
): Promise<{ id: string; status: "discarded" }> =>
  api.post(`/rop/scenarios/drafts/${id}/discard`, {});

export const reExtractDraft = (
  id: string,
  forcedRouteType?: ImportRouteType,
): Promise<ImportDraft> =>
  api.post<ImportDraft>(
    `/rop/imports/${id}/re-extract`,
    forcedRouteType ? { forced_route_type: forcedRouteType } : {},
  );

export const ROUTE_LABELS_RU: Record<ImportRouteType, string> = {
  scenario: "Сценарий звонка",
  character: "Персонаж в Конструктор",
  arena_knowledge: "Знание для Арены",
};

export const STATUS_LABELS_RU: Record<ImportDraftStatus, string> = {
  extracting: "Извлечение…",
  ready: "Готов к ревью",
  edited: "Отредактирован",
  converted: "Создано",
  discarded: "Отклонён",
  failed: "Ошибка",
};
