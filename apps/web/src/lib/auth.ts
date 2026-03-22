/**
 * Auth utilities — dual storage: in-memory (primary) + localStorage (persistence).
 *
 * In-memory cache avoids reading localStorage on every request.
 * localStorage ensures tokens survive page navigation and refreshes.
 *
 * For maximum security in production, switch to httpOnly cookies
 * set by the backend — then localStorage can be removed entirely.
 */

const ACCESS_TOKEN_KEY = "ai_trainer_access_token";
const REFRESH_TOKEN_KEY = "ai_trainer_refresh_token";

// In-memory cache (fast reads, avoids localStorage on every call)
let _accessToken: string | null = null;
let _refreshToken: string | null = null;

export function getToken(): string | null {
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
  }
}
