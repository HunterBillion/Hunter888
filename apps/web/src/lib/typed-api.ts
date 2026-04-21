/**
 * Typed API client — wraps `api.get/post/patch/...` with schema types generated
 * from FastAPI's OpenAPI spec.
 *
 * Why: prevents field-name mismatches (e.g. backend returns `avg_score` but frontend
 * reads `stats.average_score` → silently 0) and wrong method/URL combos — the
 * TypeScript compiler catches them before runtime.
 *
 * Usage:
 *   import { typedApi } from "@/lib/typed-api";
 *   const stats = await typedApi.get("/users/{user_id}/stats", { user_id: "..." });
 *   //    ^^^^^ typed as UserStatsResponse, autocomplete works
 *   console.log(stats.avg_score); // ✅ known field
 *   console.log(stats.average_score); // ❌ TS error — field doesn't exist
 *
 * Regenerate types after any backend schema change:
 *   npm run types:gen
 */

import { api } from "./api";
import type { paths } from "@/types/api";

/** Extract the response body type for a given path + method. */
type OkResponse<P extends keyof paths, M extends keyof paths[P]> =
  paths[P][M] extends { responses: { 200: { content: { "application/json": infer T } } } }
    ? T
    : paths[P][M] extends { responses: { 200: infer R } }
      ? R extends { content: { "application/json": infer T } } ? T : never
      : never;

/** Extract the request body type for POST/PATCH/PUT. */
type RequestBody<P extends keyof paths, M extends keyof paths[P]> =
  paths[P][M] extends { requestBody: { content: { "application/json": infer T } } }
    ? T
    : paths[P][M] extends { requestBody?: { content: { "application/json": infer T } } }
      ? T | undefined
      : undefined;

/** Substitute {param} placeholders AND strip the /api prefix (api.ts adds it itself). */
function fillPath(template: string, params?: Record<string, string | number>): string {
  let filled = template.startsWith("/api/") ? template.slice(4) : template;
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      filled = filled.replace(`{${key}}`, encodeURIComponent(String(value)));
    }
  }
  return filled;
}

export const typedApi = {
  get: <P extends keyof paths>(
    path: P & string,
    pathParams?: Record<string, string | number>,
  ): Promise<OkResponse<P, "get">> =>
    api.get(fillPath(path, pathParams)) as Promise<OkResponse<P, "get">>,

  post: <P extends keyof paths>(
    path: P & string,
    body?: RequestBody<P, "post">,
    pathParams?: Record<string, string | number>,
  ): Promise<OkResponse<P, "post">> =>
    api.post(fillPath(path, pathParams), body as unknown) as Promise<OkResponse<P, "post">>,

  patch: <P extends keyof paths>(
    path: P & string,
    body?: RequestBody<P, "patch">,
    pathParams?: Record<string, string | number>,
  ): Promise<OkResponse<P, "patch">> =>
    api.patch(fillPath(path, pathParams), body as unknown) as Promise<OkResponse<P, "patch">>,

  put: <P extends keyof paths>(
    path: P & string,
    body: RequestBody<P, "put">,
    pathParams?: Record<string, string | number>,
  ): Promise<OkResponse<P, "put">> =>
    api.put(fillPath(path, pathParams), body) as Promise<OkResponse<P, "put">>,

  delete: <P extends keyof paths>(
    path: P & string,
    pathParams?: Record<string, string | number>,
  ): Promise<OkResponse<P, "delete">> =>
    api.delete(fillPath(path, pathParams)) as Promise<OkResponse<P, "delete">>,
};

/** Convenience type-only helpers — import these when you need the exact shape. */
export type ApiPaths = paths;
export type { components } from "@/types/api";
