/**
 * Auth utilities — httpOnly cookies (primary) + in-memory cache (current tab).
 *
 * Tokens are stored exclusively in httpOnly cookies set by the backend.
 * This prevents XSS attacks from stealing tokens via JavaScript.
 *
 * The in-memory cache (_accessToken) holds the current token for the
 * Authorization header on API requests — it is populated on login/refresh
 * and cleared on logout. It does NOT persist across page reloads; on
 * reload the client calls /auth/refresh using the httpOnly refresh_token cookie.
 *
 * localStorage is NOT used — storing JWT tokens in localStorage violates OWASP
 * guidance and makes them accessible to any injected script.
 */

// In-memory token cache — lives only for the current tab session.
let _accessToken: string | null = null;
let _refreshToken: string | null = null;

export function getToken(): string | null {
  // httpOnly cookies can't be read by JS — that's the point.
  // Return the in-memory copy for Bearer header on API requests.
  return _accessToken;
}

export function getRefreshToken(): string | null {
  // In-memory only — no sessionStorage fallback to reduce XSS token theft surface.
  // On page reload, the httpOnly refresh_token cookie handles re-auth automatically.
  return _refreshToken;
}

export function setTokens(accessToken: string, refreshToken: string): void {
  _accessToken = accessToken;
  _refreshToken = refreshToken;
  // Set marker cookie so Next.js middleware knows user is authenticated.
  // This is NOT the auth token — just a presence flag (not httpOnly so middleware can read it).
  if (typeof window !== "undefined") {
    try {
      document.cookie = "vh_authenticated=1; path=/; max-age=604800; samesite=lax";
    } catch {}
  }
}

export function clearTokens(): void {
  _accessToken = null;
  _refreshToken = null;
  // Clear the JS-readable marker cookie to prevent redirect loops.
  // The httpOnly access_token/refresh_token cookies are cleared by the
  // server /auth/logout endpoint via Set-Cookie headers.
  if (typeof window !== "undefined") {
    try {
      document.cookie = "vh_authenticated=; path=/; max-age=0; samesite=lax";
    } catch {}
  }
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
