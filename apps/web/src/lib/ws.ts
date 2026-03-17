import { getToken } from "./auth";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

/**
 * Create a WebSocket connection and authenticate via first message.
 * Token is NOT sent in URL (security: prevents token leak in logs/referrer).
 */
export function createWebSocket(path: string): WebSocket {
  const url = `${WS_URL}${path}`;
  const ws = new WebSocket(url);

  // Send auth message as first message after connection opens
  ws.addEventListener("open", () => {
    const token = getToken();
    if (token) {
      ws.send(JSON.stringify({
        type: "auth",
        data: { token },
      }));
    }
  }, { once: true });

  return ws;
}
