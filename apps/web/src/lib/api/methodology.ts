/**
 * Per-team methodology playbooks — TZ-8 PR-C client.
 *
 * Endpoints from `app/api/methodology.py`:
 *   GET    /methodology/chunks                 — list (filterable)
 *   GET    /methodology/chunks/{chunk_id}      — single
 *   POST   /methodology/chunks                  — create
 *   PUT    /methodology/chunks/{chunk_id}       — partial update (PATCH-shape)
 *   DELETE /methodology/chunks/{chunk_id}       — hard delete (prefer status=outdated)
 *   PATCH  /methodology/chunks/{chunk_id}/status — governance transition
 *
 * Validation limits mirror app/schemas/methodology.py — single source
 * of truth on the server, surface-level UX caps here so the form
 * gives feedback without an API round-trip.
 */
import { api } from "@/lib/api";

// ── Vocabularies (kept in lock-step with the Python enum / Literal) ──

export type MethodologyKind =
  | "opener"
  | "objection"
  | "closing"
  | "discovery"
  | "persona_tone"
  | "counter_fact"
  | "process"
  | "other";

export const METHODOLOGY_KINDS: readonly MethodologyKind[] = [
  "opener",
  "objection",
  "closing",
  "discovery",
  "persona_tone",
  "counter_fact",
  "process",
  "other",
] as const;

/** UI labels — Russian, mirrors the language of the team panel. */
export const KIND_LABEL_RU: Record<MethodologyKind, string> = {
  opener: "Открытие",
  objection: "Возражения",
  closing: "Закрытие",
  discovery: "Квалификация",
  persona_tone: "Тон под персону",
  counter_fact: "Контр-факт",
  process: "Процедура",
  other: "Другое",
};

export type KnowledgeStatus = "actual" | "disputed" | "outdated" | "needs_review";

export const KNOWLEDGE_STATUSES: readonly KnowledgeStatus[] = [
  "actual",
  "disputed",
  "outdated",
  "needs_review",
] as const;

export const STATUS_LABEL_RU: Record<KnowledgeStatus, string> = {
  actual: "Актуально",
  disputed: "Спорно",
  outdated: "Устарело",
  needs_review: "Нужен пересмотр",
};

/** Tailwind colour classes for the status chip. */
export const STATUS_CLASSES: Record<KnowledgeStatus, string> = {
  actual: "bg-green-100 text-green-800 ring-1 ring-green-300",
  disputed: "bg-amber-100 text-amber-800 ring-1 ring-amber-300",
  outdated: "bg-gray-100 text-gray-700 ring-1 ring-gray-300",
  needs_review: "bg-orange-100 text-orange-800 ring-1 ring-orange-300",
};

// ── Validation caps (match Python schema) ──

export const TITLE_MAX = 200;
export const BODY_MIN = 10;
export const BODY_MAX = 10_000;
export const LIST_FIELD_MAX = 20;
export const LIST_ITEM_MAX = 60;

// ── Resource shapes ──

export interface MethodologyChunk {
  id: string;
  team_id: string;
  author_id: string | null;
  title: string;
  body: string;
  kind: MethodologyKind;
  tags: string[];
  keywords: string[];
  knowledge_status: KnowledgeStatus;
  last_reviewed_at: string | null;
  last_reviewed_by: string | null;
  review_due_at: string | null;
  /**
   * True when the embedding worker hasn't computed the vector yet.
   * The UI shows a small "indexing…" pill instead of pretending the
   * chunk is already retrievable.
   */
  embedding_pending: boolean;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface MethodologyChunkList {
  items: MethodologyChunk[];
  total: number;
}

export interface MethodologyChunkCreate {
  title: string;
  body: string;
  kind: MethodologyKind;
  tags?: string[];
  keywords?: string[];
}

export interface MethodologyChunkPatch {
  title?: string;
  body?: string;
  kind?: MethodologyKind;
  tags?: string[];
  keywords?: string[];
}

export interface MethodologyStatusPatch {
  status: KnowledgeStatus;
  /** Required when transitioning to ``disputed`` or ``outdated``. */
  note?: string | null;
}

// ── REST calls ──

export interface ListMethodologyParams {
  team_id?: string;
  kind?: MethodologyKind;
  /**
   * Filter by status. ``visible_only`` is a separate convenience —
   * use exactly one of the two.
   */
  status?: KnowledgeStatus;
  /** Show only rows that surface in RAG (actual + disputed). */
  visible_only?: boolean;
}

export const listMethodology = (
  params: ListMethodologyParams = {},
): Promise<MethodologyChunkList> => {
  const search = new URLSearchParams();
  if (params.team_id) search.set("team_id", params.team_id);
  if (params.kind) search.set("kind", params.kind);
  if (params.status) search.set("status", params.status);
  if (params.visible_only) search.set("visible_only", "true");
  const qs = search.toString();
  return api.get<MethodologyChunkList>(
    `/methodology/chunks${qs ? `?${qs}` : ""}`,
  );
};

export const getMethodology = (chunkId: string): Promise<MethodologyChunk> =>
  api.get<MethodologyChunk>(`/methodology/chunks/${chunkId}`);

export const createMethodology = (
  body: MethodologyChunkCreate,
): Promise<MethodologyChunk> =>
  api.post<MethodologyChunk>("/methodology/chunks", body);

export const updateMethodology = (
  chunkId: string,
  patch: MethodologyChunkPatch,
): Promise<MethodologyChunk> =>
  api.put<MethodologyChunk>(`/methodology/chunks/${chunkId}`, patch);

export const deleteMethodology = (chunkId: string): Promise<void> =>
  api.delete<void>(`/methodology/chunks/${chunkId}`);

export const patchMethodologyStatus = (
  chunkId: string,
  body: MethodologyStatusPatch,
): Promise<MethodologyChunk> =>
  api.patch<MethodologyChunk>(`/methodology/chunks/${chunkId}/status`, body);

// ── Client-side validation helpers ──

/** Validate a create payload. Returns a list of human-readable issues
 *  (empty when valid). Used by the form to gate the submit button.
 */
export function validateCreate(
  body: MethodologyChunkCreate,
): string[] {
  const issues: string[] = [];
  const title = body.title.trim();
  if (title.length === 0) issues.push("Заголовок не может быть пустым");
  if (title.length > TITLE_MAX) issues.push(`Заголовок ≤ ${TITLE_MAX} символов`);
  const bod = body.body.trim();
  if (bod.length < BODY_MIN) issues.push(`Тело ≥ ${BODY_MIN} символов`);
  if (bod.length > BODY_MAX) issues.push(`Тело ≤ ${BODY_MAX} символов`);
  if (!METHODOLOGY_KINDS.includes(body.kind))
    issues.push("Неизвестный тип");
  if ((body.tags?.length ?? 0) > LIST_FIELD_MAX)
    issues.push(`Тегов ≤ ${LIST_FIELD_MAX}`);
  if ((body.keywords?.length ?? 0) > LIST_FIELD_MAX)
    issues.push(`Ключевых слов ≤ ${LIST_FIELD_MAX}`);
  return issues;
}

/** Whether a status transition from ``from_`` to ``to`` is permitted
 *  by the lifecycle graph in the Python ``KnowledgeStatus`` enum.
 *
 *  Mirrors the comment in ``app/models/knowledge_status.py``. The
 *  server is authoritative; this is just for greying out illegal
 *  buttons in the UI.
 */
export function isStatusTransitionAllowed(
  from_: KnowledgeStatus,
  to: KnowledgeStatus,
): boolean {
  if (from_ === to) return false;
  if (from_ === "outdated") return false; // soft-deleted, no recovery
  // actual → any of {disputed, outdated, needs_review (auto only, but
  // the UI may want to surface a manual flip too)}
  if (from_ === "actual") return ["disputed", "outdated", "needs_review"].includes(to);
  // needs_review → actual | outdated
  if (from_ === "needs_review") return ["actual", "outdated"].includes(to);
  // disputed → actual | outdated
  if (from_ === "disputed") return ["actual", "outdated"].includes(to);
  return false;
}
