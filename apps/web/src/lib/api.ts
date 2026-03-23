import { clearTokens, getToken, getRefreshToken, setTokens } from "./auth";
import { useAuthStore } from "@/stores/useAuthStore";
import { getApiBaseUrl } from "./public-origin";

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
  if (!refreshToken) return false;

  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10_000);

    const res = await fetch(`${apiPrefix()}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
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

  _refreshPromise = _doRefresh().finally(() => {
    _refreshPromise = null;
  });

  return _refreshPromise;
}

async function request(path: string, options: RequestInit = {}) {
  const token = getToken();

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((options.headers as Record<string, string>) || {}),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
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
      message = body.detail.message || JSON.stringify(body.detail);
    }
    throw new ApiError(message, response.status);
  }

  if (response.status === 204) return null;
  return response.json();
}

async function uploadFile(path: string, file: File) {
  const formData = new FormData();
  formData.append("file", file);

  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(`${apiPrefix()}${path}`, {
      method: "POST",
      headers,
      body: formData,
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
        body: formData,
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

export const api = {
  get: (path: string) => request(path),
  post: (path: string, body: unknown) =>
    request(path, { method: "POST", body: JSON.stringify(body) }),
  put: (path: string, body: unknown) =>
    request(path, { method: "PUT", body: JSON.stringify(body) }),
  patch: (path: string, body?: unknown) =>
    request(path, { method: "PATCH", body: body ? JSON.stringify(body) : undefined }),
  delete: (path: string) => request(path, { method: "DELETE" }),
  upload: (path: string, file: File) => uploadFile(path, file),
};
