/**
 * API / WebSocket origins for the browser.
 *
 * Docker images often bake NEXT_PUBLIC_* as localhost:8000. If the user opens the UI
 * via LAN IP or hostname, fetch/ws to localhost points at the client machine — broken.
 * When env still matches the default localhost URLs, we infer the same host as the page + port 8000.
 *
 * For production behind a reverse proxy, set NEXT_PUBLIC_API_URL / NEXT_PUBLIC_WS_URL explicitly
 * (they win over inference).
 */

const DEFAULT_API_BASE = "http://localhost:8000";
const DEFAULT_WS_BASE = "ws://localhost:8000";

function stripTrailingSlash(s: string): string {
  return s.replace(/\/$/, "");
}

function isBakedDefaultApiUrl(url: string | undefined): boolean {
  if (!url?.trim()) return true;
  const u = stripTrailingSlash(url.trim());
  return u === stripTrailingSlash(DEFAULT_API_BASE) || u === "http://127.0.0.1:8000";
}

function isBakedDefaultWsUrl(url: string | undefined): boolean {
  if (!url?.trim()) return true;
  const u = stripTrailingSlash(url.trim());
  return u === stripTrailingSlash(DEFAULT_WS_BASE) || u === "ws://127.0.0.1:8000";
}

/** REST API origin without `/api` suffix. */
export function getApiBaseUrl(): string {
  const baked = process.env.NEXT_PUBLIC_API_URL?.trim();

  // Warn if using HTTP in production (insecure)
  if (typeof window !== "undefined" && process.env.NODE_ENV === "production") {
    const url = baked || DEFAULT_API_BASE;
    if (url.startsWith("http://") && !url.includes("localhost") && !url.includes("127.0.0.1")) {
      console.warn(
        "[SECURITY] API URL uses HTTP in production. This is insecure — use HTTPS. URL:",
        url,
      );
    }
  }

  if (typeof window !== "undefined") {
    if (baked && !isBakedDefaultApiUrl(baked)) {
      return stripTrailingSlash(baked);
    }
    const host = window.location.hostname;
    if (host !== "localhost" && host !== "127.0.0.1") {
      return stripTrailingSlash(`${window.location.protocol}//${host}:8000`);
    }
  }

  return stripTrailingSlash(baked || DEFAULT_API_BASE);
}

/** WebSocket origin without path (e.g. ws://host:8000). Uses wss on https pages. */
export function getWsBaseUrl(): string {
  const baked = process.env.NEXT_PUBLIC_WS_URL?.trim();

  if (typeof window !== "undefined") {
    if (baked && !isBakedDefaultWsUrl(baked)) {
      return stripTrailingSlash(baked);
    }
    const host = window.location.hostname;
    if (host !== "localhost" && host !== "127.0.0.1") {
      const wsProto = window.location.protocol === "https:" ? "wss:" : "ws:";
      return stripTrailingSlash(`${wsProto}//${host}:8000`);
    }
  }

  return stripTrailingSlash(baked || DEFAULT_WS_BASE);
}
