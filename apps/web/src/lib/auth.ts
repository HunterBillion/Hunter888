/**
 * Auth utilities — httpOnly cookies (primary) + localStorage (fallback for migration).
 *
 * In production, tokens are stored in httpOnly cookies set by the backend.
 * The frontend only needs to know IF the user is authenticated (via `vh_authenticated` cookie).
 * Tokens in localStorage are kept temporarily for backward compatibility.
 */

const ACCESS_TOKEN_KEY = "ai_trainer_access_token";
const REFRESH_TOKEN_KEY = "ai_trainer_refresh_token";

// In-memory cache (for backward compat during migration)
let _accessToken: string | null = null;
let _refreshToken: string | null = null;

export function getToken(): string | null {
  // httpOnly cookies can't be read by JS — that's the point.
  // For Bearer header fallback, check in-memory / localStorage.
  if (_accessToken) return _accessToken;
  if (typeof window === "undefined") return null;
  try {
    const stored = localStorage.getItem(ACCESS_TOKEN_KEY);
    if (stored) {
      _accessToken = stored;
      _refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
    }
  } catch {}
  return _accessToken;
}

export function getRefreshToken(): string | null {
  if (_refreshToken) return _refreshToken;
  if (typeof window === "undefined") return null;
  try {
    return localStorage.getItem(REFRESH_TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setTokens(accessToken: string, refreshToken: string): void {
  _accessToken = accessToken;
  _refreshToken = refreshToken;
  // Still persist to localStorage for backward compat (will be removed in next release)
  if (typeof window !== "undefined") {
    try {
      localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
      localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
    } catch {}
  }
}

export function clearTokens(): void {
  _accessToken = null;
  _refreshToken = null;
  if (typeof window !== "undefined") {
    try {
      localStorage.removeItem(ACCESS_TOKEN_KEY);
      localStorage.removeItem(REFRESH_TOKEN_KEY);
    } catch {}
    // Clear the JS-readable marker cookie to prevent redirect loops.
    // The httpOnly access_token/refresh_token cookies can only be cleared
    // by the server (via Set-Cookie), so we clear what we can.
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
