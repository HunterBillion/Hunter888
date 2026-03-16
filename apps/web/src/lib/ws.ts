import { getToken } from "./auth";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

export function createWebSocket(path: string): WebSocket {
  const token = getToken();
  const url = `${WS_URL}${path}${token ? `?token=${token}` : ""}`;
  return new WebSocket(url);
}
