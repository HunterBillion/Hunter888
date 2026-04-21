/**
 * Auth utilities — httpOnly cookies (primary) + in-memory cache (current tab).
 *
 * Access tokens live ONLY in memory — never persisted to storage.
 * Refresh tokens use sessionStorage as a reload-safe fallback because the
 * httpOnly refresh_token cookie is scoped to Path=/api/auth/refresh on the
 * backend origin and is NOT sent on cross-origin requests from the frontend
 * (port 3000 → port 8000 in dev). sessionStorage is tab-scoped and cleared
 * on tab close, limiting the XSS exposure window.
 *
 * localStorage is NOT used — it persists across tabs/sessions and violates
 * OWASP guidance for token storage.
 */

const _SS_REFRESH_KEY = "vh_rt";

// In production behind a reverse proxy (same origin), the httpOnly refresh_token
// cookie works natively. In development (cross-origin ports 3000 → 8000),
// sessionStorage is used as a reload-safe fallback for the refresh token.
const _persistRefreshToken = process.env.NODE_ENV !== "production";

// In-memory token cache — lives only for the current tab session.
let _accessToken: string | null = null;
let _refreshToken: string | null = null;

export function getToken(): string | null {
  // httpOnly cookies can't be read by JS — that's the point.
  // Return the in-memory copy for Bearer header on API requests.
  return _accessToken;
}

export function getRefreshToken(): string | null {
  if (_refreshToken) return _refreshToken;
  // Fallback: sessionStorage survives page reloads within the same tab.
  if (_persistRefreshToken && typeof sessionStorage !== "undefined") {
    try {
      return sessionStorage.getItem(_SS_REFRESH_KEY);
    } catch { /* SSR or blocked */ }
  }
  return null;
}

export function setTokens(accessToken: string, refreshToken: string, csrfToken?: string): void {
  _accessToken = accessToken;
  _refreshToken = refreshToken;
  // Persist refresh token to sessionStorage for page-reload recovery (dev only).
  if (_persistRefreshToken && typeof sessionStorage !== "undefined") {
    try {
      sessionStorage.setItem(_SS_REFRESH_KEY, refreshToken);
    } catch { /* SSR or blocked */ }
  }
  // Set marker cookie so Next.js middleware knows user is authenticated.
  // This is NOT the auth token — just a presence flag (not httpOnly so middleware can read it).
  if (typeof window !== "undefined") {
    try {
      document.cookie = "vh_authenticated=1; path=/; max-age=604800; samesite=lax";
    } catch {}
    // Set CSRF token cookie via JS — cross-origin Set-Cookie from API (port 8000)
    // is silently dropped by browsers when the page is on port 3000.
    if (csrfToken) {
      try {
        document.cookie = `csrf_token=${encodeURIComponent(csrfToken)}; path=/; max-age=604800; samesite=lax`;
      } catch {}
    }
  }
}

export function clearTokens(): void {
  _accessToken = null;
  _refreshToken = null;
  if (_persistRefreshToken && typeof sessionStorage !== "undefined") {
    try { sessionStorage.removeItem(_SS_REFRESH_KEY); } catch {}
  }
  // Clear the JS-readable marker cookie to prevent redirect loops.
  // The httpOnly access_token/refresh_token cookies are cleared by the
  // server /auth/logout endpoint via Set-Cookie headers.
  if (typeof window !== "undefined") {
    try {
      document.cookie = "vh_authenticated=; path=/; max-age=0; samesite=lax";
    } catch {}
  }
  // Reset notification WS module flags so next login re-fetches and re-connects
  import("@/providers/NotificationWSProvider")
    .then(({ resetNotificationWSFlags }) => resetNotificationWSFlags())
    .catch(() => { /* provider not loaded yet — safe to skip */ });
}

/**
 * Check if user appears authenticated (via marker cookie or localStorage).
 * This does NOT validate the token — just a fast presence check.
 */
export function isAuthenticated(): boolean {
  if (typeof document !== "undefined" && document.cookie.includes("vh_authenticated=")) {
    return true;
  }
  return !!getToken();
}
