import { clearTokens, getToken, getRefreshToken, setTokens } from "./auth";
import { useAuthStore } from "@/stores/useAuthStore";
import { getApiBaseUrl } from "./public-origin";

/** Read the csrf_token cookie set by the backend on login/refresh. */
function getCsrfToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

const _CSRF_METHODS = new Set(["POST", "PUT", "DELETE", "PATCH"]);

function apiPrefix(): string {
  return `${getApiBaseUrl()}/api`;
}

/**
 * ApiError — adds the raw structured detail from the server body so
 * callers can branch on well-known error codes (e.g. 409
 * `session_already_active` carries `existing_session_id`).
 *
 * Phase F (2026-04-20): added `detail` field. Callers that don't need
 * the structured payload can still use `.message` and `.status` as
 * before — contract is strictly backward compatible.
 */
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public detail: Record<string, unknown> | null = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * Token refresh mutex — ensures only ONE refresh request is in-flight at a time.
 * All concurrent 401 handlers (from request(), uploadFile(), etc.) wait for the
 * same promise instead of firing parallel refresh calls.
 *
 * Includes a 10-second timeout to prevent deadlocks if the refresh hangs.
 */
let _refreshPromise: Promise<boolean> | null = null;

/**
 * Auth-failure circuit breaker — once a refresh fails (tokens fully expired),
 * skip all subsequent API calls to prevent a cascade of 401 errors in console.
 * Resets when new tokens are set (login / successful refresh).
 */
let _authFailed = false;

async function _doRefresh(): Promise<boolean> {
  const refreshToken = getRefreshToken();
  // Even without in-memory token, the httpOnly refresh_token cookie may
  // still be present — send the request and let the backend check the cookie.
  const hasMarkerCookie = typeof document !== "undefined" && document.cookie.includes("vh_authenticated=");
  if (!refreshToken && !hasMarkerCookie) return false;

  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10_000);

    const res = await fetch(`${apiPrefix()}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(refreshToken ? { refresh_token: refreshToken } : {}),
      credentials: "include",
      signal: controller.signal,
    });

    clearTimeout(timeout);

    if (!res.ok) return false;

    const data = await res.json();
    setTokens(data.access_token, data.refresh_token, data.csrf_token);
    _authFailed = false; // Reset circuit breaker — we have fresh tokens
    try { useAuthStore.getState().invalidate(); } catch { /* store may not be mounted */ }
    return true;
  } catch {
    return false;
  }
}

async function handleTokenRefresh(): Promise<boolean> {
  // If a refresh is already in-flight, piggyback on its promise
  if (_refreshPromise) return _refreshPromise;

  _refreshPromise = _doRefresh()
    .catch(() => {
      // Safety: if _doRefresh throws unexpectedly, clear promise and return false
      return false;
    })
    .finally(() => {
      _refreshPromise = null;
    });

  return _refreshPromise;
}

/** Exported for WebSocket pre-auth token refresh. */
export const tryRefreshToken = handleTokenRefresh;

/** Reset auth-failure circuit breaker (call after successful login). */
export function resetAuthCircuitBreaker() {
  _authFailed = false;
}

/**
 * Surface a single "Сессия истекла" toast before bouncing to /login.
 *
 * Phase C (2026-04-20) fix for BUG-5: the refresh-failure path used to
 * redirect silently, leaving users confused about why they were logged
 * out. The lazy ``import("sonner")`` keeps the toast dependency out of
 * every api.ts consumer's bundle when unused, and the one-shot guard
 * prevents duplicate toasts when multiple parallel requests race to the
 * 401 branch.
 */
let _sessionExpiredToasted = false;
function notifySessionExpired() {
  if (_sessionExpiredToasted) return;
  _sessionExpiredToasted = true;
  // Fire-and-forget; sonner is loaded at the app root via <Toaster />.
  import("sonner")
    .then(({ toast }) => {
      toast.error("Сессия истекла — войдите снова.", {
        duration: 4500,
      });
    })
    .catch(() => {
      // toast lib unavailable — silent fallback
    });
}

/**
 * Default hard-timeout for any client fetch — 30 seconds.
 *
 * Phase C hardening (2026-04-20). Without this, a stalled server (e.g.
 * LLM back-pressure, DB lock) leaves the browser spinner running for the
 * platform's default 2-minute fetch timeout, which users interpret as "app
 * is broken". 30 s is higher than any legitimate REST latency for this
 * product — anything longer should come through WebSocket events.
 */
const DEFAULT_FETCH_TIMEOUT_MS = 30_000;

/**
 * Wrap `fetch` with:
 *  1. a hard timeout (``DEFAULT_FETCH_TIMEOUT_MS``), and
 *  2. merge of a caller-supplied ``AbortSignal`` so that component
 *     unmount / react-query cancel still aborts in-flight requests.
 *
 * Returns the Response. On timeout, throws the native DOMException with
 * name "AbortError" — same contract as the user's own abort.
 */
async function fetchWithTimeout(
  url: string,
  init: RequestInit = {},
  timeoutMs = DEFAULT_FETCH_TIMEOUT_MS,
): Promise<Response> {
  const timeoutCtrl = new AbortController();
  const timeoutId = setTimeout(() => timeoutCtrl.abort(new DOMException(
    "Request timeout (30s)", "TimeoutError",
  )), timeoutMs);

  // Forward external abort (e.g. React StrictMode unmount) into the
  // timeout controller so the in-flight fetch is cancelled cleanly.
  const external = init.signal;
  const forwardAbort = () => timeoutCtrl.abort(external?.reason);
  if (external) {
    if (external.aborted) {
      clearTimeout(timeoutId);
      throw external.reason instanceof Error
        ? external.reason
        : new DOMException("Aborted", "AbortError");
    }
    external.addEventListener("abort", forwardAbort, { once: true });
  }

  try {
    return await fetch(url, { ...init, signal: timeoutCtrl.signal });
  } finally {
    clearTimeout(timeoutId);
    if (external) external.removeEventListener("abort", forwardAbort);
  }
}

async function request(path: string, options: RequestInit = {}): Promise<unknown> {
  // Circuit breaker: if auth already failed (refresh expired), skip API call
  // to prevent a cascade of 401 errors flooding the console.
  if (_authFailed) {
    throw new ApiError("Unauthorized", 401);
  }

  const token = getToken();

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((options.headers as Record<string, string>) || {}),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  // Attach CSRF token for state-changing methods (matches CSRFMiddleware on backend)
  const method = (options.method || "GET").toUpperCase();
  if (_CSRF_METHODS.has(method)) {
    const csrfToken = getCsrfToken();
    if (csrfToken) {
      headers["X-CSRF-Token"] = csrfToken;
    }
  }

  let response: Response;
  try {
    response = await fetchWithTimeout(`${apiPrefix()}${path}`, {
      ...options,
      headers,
      credentials: "include", // Send httpOnly cookies
    });
  } catch {
    throw new ApiError("Сервер недоступен. Проверьте подключение.", 0);
  }

  // On 401, try refresh token before giving up
  if (response.status === 401) {
    const refreshed = await handleTokenRefresh();
    if (refreshed) {
      // Retry with new token
      const newToken = getToken();
      if (newToken) {
        headers["Authorization"] = `Bearer ${newToken}`;
      }
      response = await fetchWithTimeout(`${apiPrefix()}${path}`, {
        ...options,
        headers,
        credentials: "include",
      });
    }

    if (response.status === 401) {
      _authFailed = true; // Trip circuit breaker — stop all parallel requests
      clearTokens();
      notifySessionExpired();
      window.location.href = "/login";
      throw new ApiError("Unauthorized", 401);
    }
  }

  // On 403 CSRF error, refresh token (which also refreshes the CSRF cookie) and retry once
  if (response.status === 403 && _CSRF_METHODS.has(method)) {
    const body403 = await response.json().catch(() => ({}));
    const detail = typeof body403.detail === "string" ? body403.detail : "";
    if (detail.toLowerCase().includes("csrf")) {
      const refreshed = await handleTokenRefresh();
      if (refreshed) {
        // Re-read the CSRF cookie after refresh
        const newCsrf = getCsrfToken();
        if (newCsrf) {
          headers["X-CSRF-Token"] = newCsrf;
        }
        const newToken = getToken();
        if (newToken) {
          headers["Authorization"] = `Bearer ${newToken}`;
        }
        response = await fetchWithTimeout(`${apiPrefix()}${path}`, {
          ...options,
          headers,
          credentials: "include",
        });
      }
    }
  }

  // Rate limit handling
  if (response.status === 429) {
    // Phase C (2026-04-20) — distinguish between "too many requests" (IP
    // rate-limit) and "plan limit reached" (daily quota). The latter has
    // a structured body `{detail: {feature, plan, limit, used, message}}`
    // emitted by `app/core/deps.py::_plan_limit_payload`. We broadcast
    // a CustomEvent so the globally-mounted PlanLimitModal can render
    // an upsell dialog instead of a generic toast.
    const body429 = await response.clone().json().catch(() => ({}));
    const detail = body429?.detail;
    if (
      detail &&
      typeof detail === "object" &&
      typeof detail.feature === "string" &&
      typeof detail.plan === "string"
    ) {
      if (typeof window !== "undefined") {
        window.dispatchEvent(
          new CustomEvent("plan-limit-reached", {
            detail: {
              feature: String(detail.feature),
              plan: String(detail.plan),
              limit: Number(detail.limit ?? 0),
              used: Number(detail.used ?? 0),
              message: String(detail.message ?? "Лимит плана"),
            },
          }),
        );
      }
      throw new ApiError(String(detail.message ?? "Лимит плана"), 429);
    }
    const retryAfter = response.headers.get("Retry-After");
    const waitSec = retryAfter ? parseInt(retryAfter, 10) : 30;
    throw new ApiError(
      `Слишком много запросов. Подождите ${waitSec} секунд.`,
      429,
    );
  }

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    let message = "Request failed";
    // Phase F (2026-04-20): extract raw structured detail so callers
    // can branch on code (e.g. 409 `session_already_active` needs
    // `existing_session_id` from the backend payload).
    let detail: Record<string, unknown> | null = null;
    if (typeof body.detail === "string") {
      message = body.detail;
    } else if (Array.isArray(body.detail)) {
      message = body.detail.map((e: { msg?: string }) => e.msg).join(", ");
    } else if (body.detail && typeof body.detail === "object") {
      // Handle structured error details (e.g. consent check returns { message, redirect })
      // Avoid JSON.stringify to prevent leaking internal structure to end users
      message = (body.detail as { message?: string }).message || "Ошибка запроса";
      detail = body.detail as Record<string, unknown>;
    }
    throw new ApiError(message, response.status, detail);
  }

  if (response.status === 204) return null;
  return response.json();
}

async function uploadFile(path: string, file: File): Promise<unknown> {
  // Factory: FormData body is consumed on first fetch — must recreate for retries
  const createBody = () => {
    const fd = new FormData();
    fd.append("file", file);
    return fd;
  };

  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  // Attach CSRF token for POST upload (matches CSRFMiddleware on backend)
  const csrfToken = getCsrfToken();
  if (csrfToken) headers["X-CSRF-Token"] = csrfToken;

  let response: Response;
  try {
    response = await fetchWithTimeout(`${apiPrefix()}${path}`, {
      method: "POST",
      headers,
      body: createBody(),
      credentials: "include",
    });
  } catch {
    throw new ApiError("Сервер недоступен. Проверьте подключение.", 0);
  }

  if (response.status === 401) {
    const refreshed = await handleTokenRefresh();
    if (refreshed) {
      const newToken = getToken();
      if (newToken) headers["Authorization"] = `Bearer ${newToken}`;
      const newCsrf = getCsrfToken();
      if (newCsrf) headers["X-CSRF-Token"] = newCsrf;
      response = await fetchWithTimeout(`${apiPrefix()}${path}`, {
        method: "POST",
        headers,
        body: createBody(),
        credentials: "include",
      });
    }
    if (response.status === 401) {
      _authFailed = true;
      clearTokens();
      notifySessionExpired();
      window.location.href = "/login";
      throw new ApiError("Unauthorized", 401);
    }
  }

  // On 403 CSRF error, refresh token (which also refreshes the CSRF cookie) and retry once
  if (response.status === 403) {
    const body403 = await response.json().catch(() => ({}));
    const detail = typeof body403.detail === "string" ? body403.detail : "";
    if (detail.toLowerCase().includes("csrf")) {
      const refreshed = await handleTokenRefresh();
      if (refreshed) {
        const newCsrf = getCsrfToken();
        if (newCsrf) headers["X-CSRF-Token"] = newCsrf;
        const newToken = getToken();
        if (newToken) headers["Authorization"] = `Bearer ${newToken}`;
        response = await fetchWithTimeout(`${apiPrefix()}${path}`, {
          method: "POST",
          headers,
          body: createBody(),
          credentials: "include",
        });
      }
    }
  }

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const message = typeof body.detail === "string" ? body.detail : "Upload failed";
    throw new ApiError(message, response.status);
  }

  return response.json();
}

/* eslint-disable @typescript-eslint/no-explicit-any */
/**
 * Typed API client (#19).
 * Generic overloads allow callers to specify the expected response type:
 *   const user = await api.get<User>("/auth/me");
 * Without explicit type, defaults to `any` for backward compatibility.
 */
// Phase C hardening (2026-04-20): AbortSignal forwarded through every
// mutation (put/patch/delete), not just get/post. This lets React Query
// cancel in-flight updates on unmount, and lets components wire Escape /
// navigation to abort long-running requests without leaking.
export const api = {
  get: <T = any>(path: string, opts?: { signal?: AbortSignal }): Promise<T> =>
    request(path, { signal: opts?.signal }) as Promise<T>,
  post: <T = any>(path: string, body: unknown, opts?: { signal?: AbortSignal }): Promise<T> =>
    request(path, { method: "POST", body: JSON.stringify(body), signal: opts?.signal }) as Promise<T>,
  put: <T = any>(path: string, body: unknown, opts?: { signal?: AbortSignal }): Promise<T> =>
    request(path, { method: "PUT", body: JSON.stringify(body), signal: opts?.signal }) as Promise<T>,
  patch: <T = any>(path: string, body?: unknown, opts?: { signal?: AbortSignal }): Promise<T> =>
    request(path, {
      method: "PATCH",
      body: body ? JSON.stringify(body) : undefined,
      signal: opts?.signal,
    }) as Promise<T>,
  delete: <T = any>(path: string, opts?: { signal?: AbortSignal }): Promise<T> =>
    request(path, { method: "DELETE", signal: opts?.signal }) as Promise<T>,
  upload: <T = any>(path: string, file: File): Promise<T> =>
    uploadFile(path, file) as Promise<T>,
};
