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

class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
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
    setTokens(data.access_token, data.refresh_token);
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

async function request(path: string, options: RequestInit = {}): Promise<unknown> {
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
    response = await fetch(`${apiPrefix()}${path}`, {
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
      response = await fetch(`${apiPrefix()}${path}`, {
        ...options,
        headers,
        credentials: "include",
      });
    }

    if (response.status === 401) {
      clearTokens();
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
        response = await fetch(`${apiPrefix()}${path}`, {
          ...options,
          headers,
          credentials: "include",
        });
      }
    }
  }

  // Rate limit handling
  if (response.status === 429) {
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
    if (typeof body.detail === "string") {
      message = body.detail;
    } else if (Array.isArray(body.detail)) {
      message = body.detail.map((e: { msg?: string }) => e.msg).join(", ");
    } else if (body.detail && typeof body.detail === "object") {
      // Handle structured error details (e.g. consent check returns { message, redirect })
      // Avoid JSON.stringify to prevent leaking internal structure to end users
      message = body.detail.message || "Ошибка запроса";
    }
    throw new ApiError(message, response.status);
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

  let response: Response;
  try {
    response = await fetch(`${apiPrefix()}${path}`, {
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
      response = await fetch(`${apiPrefix()}${path}`, {
        method: "POST",
        headers,
        body: createBody(),
        credentials: "include",
      });
    }
    if (response.status === 401) {
      clearTokens();
      window.location.href = "/login";
      throw new ApiError("Unauthorized", 401);
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
export const api = {
  get: <T = any>(path: string): Promise<T> => request(path) as Promise<T>,
  post: <T = any>(path: string, body: unknown, opts?: { signal?: AbortSignal }): Promise<T> =>
    request(path, { method: "POST", body: JSON.stringify(body), signal: opts?.signal }) as Promise<T>,
  put: <T = any>(path: string, body: unknown): Promise<T> =>
    request(path, { method: "PUT", body: JSON.stringify(body) }) as Promise<T>,
  patch: <T = any>(path: string, body?: unknown): Promise<T> =>
    request(path, { method: "PATCH", body: body ? JSON.stringify(body) : undefined }) as Promise<T>,
  delete: <T = any>(path: string): Promise<T> => request(path, { method: "DELETE" }) as Promise<T>,
  upload: <T = any>(path: string, file: File): Promise<T> => uploadFile(path, file) as Promise<T>,
};
