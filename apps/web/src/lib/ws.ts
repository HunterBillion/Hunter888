import { getToken } from "./auth";
import { logger } from "./logger";
import { getWsBaseUrl } from "./public-origin";

// For same-origin HTTPS + reverse proxy, set NEXT_PUBLIC_WS_URL=wss://your-domain.com

/** Reconnect config */
const MAX_RETRIES = 8;
const BASE_DELAY_MS = 500;
const MAX_DELAY_MS = 30_000;
const JITTER_FACTOR = 0.3;

function backoffDelay(attempt: number): number {
  const exponential = Math.min(BASE_DELAY_MS * 2 ** attempt, MAX_DELAY_MS);
  const jitter = exponential * JITTER_FACTOR * Math.random();
  return exponential + jitter;
}

/**
 * Create a WebSocket connection with authentication and automatic reconnect.
 * Token is NOT sent in URL (security: prevents token leak in logs/referrer).
 *
 * Returns an object with the WebSocket instance and a cleanup function.
 * Call cleanup() to prevent further reconnection attempts.
 */
export function createReconnectingWebSocket(
  path: string,
  callbacks?: {
    onOpen?: () => void;
    onClose?: (ev: CloseEvent) => void;
    onError?: (ev: Event) => void;
    onMessage?: (data: unknown) => void;
    onReconnecting?: (attempt: number) => void;
    onReconnectFailed?: () => void;
  },
): { ws: WebSocket; cleanup: () => void } {
  let attempt = 0;
  let disposed = false;
  let currentWs: WebSocket;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  function connect(): WebSocket {
    const url = `${getWsBaseUrl()}${path}`;
    const ws = new WebSocket(url);
    currentWs = ws;

    ws.addEventListener("open", () => {
      attempt = 0; // Reset on successful connection
      const token = getToken();
      if (token) {
        ws.send(JSON.stringify({ type: "auth", data: { token } }));
      }
      callbacks?.onOpen?.();
    });

    ws.addEventListener("message", (ev) => {
      try {
        const data = JSON.parse(ev.data as string);
        callbacks?.onMessage?.(data);
      } catch {
        logger.error("Failed to parse WebSocket message");
      }
    });

    ws.addEventListener("close", (ev) => {
      callbacks?.onClose?.(ev);
      // Don't reconnect on intentional close (1000) or auth failure (4001)
      if (disposed || ev.code === 1000 || ev.code === 4001) return;
      scheduleReconnect();
    });

    ws.addEventListener("error", (ev) => {
      callbacks?.onError?.(ev);
    });

    return ws;
  }

  function scheduleReconnect() {
    if (disposed || attempt >= MAX_RETRIES) {
      logger.warn(`[WS] Reconnect failed after ${attempt} attempts`);
      callbacks?.onReconnectFailed?.();
      return;
    }

    const delay = backoffDelay(attempt);
    attempt++;
    logger.log(`[WS] Reconnecting in ${Math.round(delay)}ms (attempt ${attempt}/${MAX_RETRIES})`);
    callbacks?.onReconnecting?.(attempt);

    reconnectTimer = setTimeout(() => {
      if (!disposed) connect();
    }, delay);
  }

  function cleanup() {
    disposed = true;
    if (reconnectTimer) clearTimeout(reconnectTimer);
    if (currentWs && currentWs.readyState !== WebSocket.CLOSED) {
      currentWs.close(1000);
    }
  }

  const ws = connect();
  return { ws, cleanup };
}

/**
 * Create a simple WebSocket connection (no auto-reconnect).
 * Kept for backward compatibility.
 */
export function createWebSocket(path: string): WebSocket {
  const url = `${getWsBaseUrl()}${path}`;
  const ws = new WebSocket(url);

  ws.addEventListener("open", () => {
    const token = getToken();
    if (token) {
      ws.send(JSON.stringify({ type: "auth", data: { token } }));
    }
  }, { once: true });

  return ws;
}
