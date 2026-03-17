/**
 * Auth utilities — cookie-based approach.
 *
 * Tokens are stored in httpOnly cookies by the API.
 * Frontend only needs to check auth status via /auth/me.
 * For WS auth, we get a short-lived token from /auth/ws-token.
 */

const ACCESS_TOKEN_KEY = "ai_trainer_access_token";
const REFRESH_TOKEN_KEY = "ai_trainer_refresh_token";

// Legacy localStorage support (for migration period)
export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function setTokens(accessToken: string, refreshToken: string): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

/**
 * Check if user is authenticated by calling /auth/me.
 * Returns true if the API responds with user data.
 */
export async function checkAuth(): Promise<boolean> {
  const token = getToken();
  if (!token) return false;

  try {
    const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const res = await fetch(`${API_URL}/api/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
      credentials: "include",
    });
    return res.ok;
  } catch {
    return false;
  }
}
