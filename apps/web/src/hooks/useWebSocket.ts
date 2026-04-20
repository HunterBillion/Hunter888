"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { logger } from "@/lib/logger";
import { getRefreshToken, getToken, setTokens } from "@/lib/auth";
import { getApiBaseUrl } from "@/lib/public-origin";
import { createWebSocket } from "@/lib/ws";
import type { WSConnectionState, WSMessage } from "@/types";

interface UseWebSocketOptions {
  path?: string;
  onMessage?: (data: WSMessage) => void;
  onError?: (error: Event) => void;
  autoConnect?: boolean;
  /** Session ID for resume after reconnect (from useSessionStore) */
  sessionId?: string | null;
  /** Last received sequence number for message replay */
  lastSequenceNumber?: number | null;
}

const HEARTBEAT_INTERVAL = 30_000; // 30 seconds
const MAX_RECONNECT_DELAY = 30_000; // 30 seconds max
const INITIAL_RECONNECT_DELAY = 1_000; // 1 second
const TOKEN_REFRESH_INTERVAL = 25 * 60 * 1000; // 25 minutes (token TTL = 30 min)
// 2026-04-20: cap reconnect attempts. Before, the loop spun forever with
// exponential backoff maxed at 30s — that's 2 retries per minute, per tab,
// indefinitely, until the user closed the page. That's real battery drain
// on mobile and zero user feedback about what's happening. 8 attempts gives
// ~2 minutes of recovery window (1+2+4+8+16+30+30+30s) before we surface
// "permanently disconnected" and let the UI offer a manual reconnect.
const MAX_RECONNECT_ATTEMPTS = 8;

export function useWebSocket({
  path = "/ws/training",
  onMessage,
  onError,
  autoConnect = true,
  sessionId = null,
  lastSequenceNumber = null,
}: UseWebSocketOptions = {}) {
  const [connectionState, setConnectionState] =
    useState<WSConnectionState>("disconnected");

  const wsRef = useRef<WebSocket | null>(null);
  const onMessageRef = useRef(onMessage);
  const onErrorRef = useRef(onError);
  const reconnectDelayRef = useRef(INITIAL_RECONNECT_DELAY);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const heartbeatTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const tokenRefreshTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const messageQueueRef = useRef<unknown[]>([]);
  const mountedRef = useRef(true);
  const manualCloseRef = useRef(false);
  const pathRef = useRef(path);
  /** True after first successful connect — subsequent connects are reconnects */
  const hasConnectedRef = useRef(false);
  const sessionIdRef = useRef(sessionId);
  const lastSeqRef = useRef(lastSequenceNumber);
  // BUG-9 fix: ref to always call the latest connect() from setTimeout callbacks
  const connectRef = useRef<() => void>(() => {});

  // Keep refs up to date
  onMessageRef.current = onMessage;
  onErrorRef.current = onError;
  pathRef.current = path;
  sessionIdRef.current = sessionId;
  lastSeqRef.current = lastSequenceNumber;

  const clearTimers = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (heartbeatTimerRef.current) {
      clearInterval(heartbeatTimerRef.current);
      heartbeatTimerRef.current = null;
    }
    if (tokenRefreshTimerRef.current) {
      clearInterval(tokenRefreshTimerRef.current);
      tokenRefreshTimerRef.current = null;
    }
  }, []);

  const startHeartbeat = useCallback(() => {
    if (heartbeatTimerRef.current) {
      clearInterval(heartbeatTimerRef.current);
    }
    heartbeatTimerRef.current = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: "ping" }));
      }
    }, HEARTBEAT_INTERVAL);
  }, []);

  const startTokenRefresh = useCallback(() => {
    if (tokenRefreshTimerRef.current) {
      clearInterval(tokenRefreshTimerRef.current);
    }
    tokenRefreshTimerRef.current = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        const refreshToken = getRefreshToken();
        if (refreshToken) {
          wsRef.current.send(
            JSON.stringify({
              type: "auth.refresh",
              data: { refresh_token: refreshToken },
            }),
          );
          logger.log("[WS] Proactive token refresh sent");
        }
      }
    }, TOKEN_REFRESH_INTERVAL);
  }, []);

  const flushQueue = useCallback(() => {
    while (
      messageQueueRef.current.length > 0 &&
      wsRef.current?.readyState === WebSocket.OPEN
    ) {
      const msg = messageQueueRef.current.shift();
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  /**
   * Try REST token refresh, then reconnect WS. Used when WS closes with 1008.
   */
  const refreshAndReconnect = useCallback(async () => {
    try {
      const refreshToken = getRefreshToken();
      if (!refreshToken) {
        window.location.href = "/login";
        return;
      }

      // Use the same origin inference as api.ts (handles LAN / non-localhost)
      const apiBase = getApiBaseUrl();
      const res = await fetch(`${apiBase}/api/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
        credentials: "include",
      });

      if (!res.ok) {
        window.location.href = "/login";
        return;
      }

      const data = await res.json();
      setTokens(data.access_token, data.refresh_token, data.csrf_token);
      logger.log("[WS] Token refreshed via REST, reconnecting...");
      // Reconnect will happen automatically via connect()
    } catch {
      logger.error("[WS] REST token refresh failed, redirecting to login");
      window.location.href = "/login";
    }
  }, []);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;
    if (
      wsRef.current &&
      (wsRef.current.readyState === WebSocket.OPEN ||
        wsRef.current.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }
    // Close any lingering connection in CLOSING state to prevent duplicates
    if (wsRef.current && wsRef.current.readyState !== WebSocket.CLOSED) {
      wsRef.current.close();
    }

    manualCloseRef.current = false;
    // 2026-04-20: explicit connect() — either first mount or user clicked
    // "reconnect" after MAX_RECONNECT_ATTEMPTS. Either way give this call a
    // fresh budget; the auto-reconnect branch in `ws.onclose` is what does
    // the counting, not this entry.
    reconnectAttemptsRef.current = 0;
    reconnectDelayRef.current = INITIAL_RECONNECT_DELAY;
    const isReconnect = hasConnectedRef.current;
    setConnectionState(isReconnect ? "reconnecting" : "connecting");

    try {
      const ws = createWebSocket(pathRef.current);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!mountedRef.current) return;
        setConnectionState("connected");
        reconnectDelayRef.current = INITIAL_RECONNECT_DELAY;
        // 2026-04-20: reset retry counter so a later transient drop gets
        // the full MAX_RECONNECT_ATTEMPTS budget again.
        reconnectAttemptsRef.current = 0;
        hasConnectedRef.current = true;
        startHeartbeat();
        startTokenRefresh();

        // If this is a reconnect and we have an active session — send resume
        if (isReconnect && sessionIdRef.current) {
          ws.send(
            JSON.stringify({
              type: "session.resume",
              data: {
                session_id: sessionIdRef.current,
                last_sequence_number: lastSeqRef.current ?? null,
              },
            }),
          );
          logger.log("[WS] Sent session.resume for", sessionIdRef.current);
        }

        flushQueue();
      };

      ws.onmessage = (event) => {
        if (!mountedRef.current) return;
        try {
          const data = JSON.parse(event.data);
          // Ignore pong messages
          if (data.type === "pong") return;

          // Handle token refresh responses internally
          if (data.type === "auth.refreshed") {
            setTokens(data.data.access_token, data.data.refresh_token, data.data.csrf_token);
            logger.log("[WS] Token refreshed via WS");
            return;
          }
          if (data.type === "auth.refresh_error") {
            if (data.data.reason === "refresh_expired") {
              logger.error("[WS] Refresh token expired, redirecting to login");
              window.location.href = "/login";
            }
            return;
          }

          onMessageRef.current?.(data);
        } catch {
          logger.error("Failed to parse WebSocket message");
        }
      };

      ws.onerror = (event) => {
        if (!mountedRef.current) return;
        setConnectionState("error");
        onErrorRef.current?.(event);
      };

      ws.onclose = (event) => {
        if (!mountedRef.current) return;
        clearTimers();

        // 4001 = Superseded by newer connection — don't reconnect
        if (event.code === 4001) {
          setConnectionState("disconnected");
          return;
        }

        // 1008 = Policy Violation (auth denied) — try REST refresh first
        if (event.code === 1008) {
          setConnectionState("reconnecting");
          refreshAndReconnect().then(() => {
            if (mountedRef.current && !manualCloseRef.current) {
              // BUG-9 fix: use connectRef to avoid stale closure
              reconnectTimerRef.current = setTimeout(() => {
                if (mountedRef.current && !manualCloseRef.current) {
                  connectRef.current();
                }
              }, 500);
            }
          });
          return;
        }

        setConnectionState("disconnected");

        // Auto-reconnect with exponential backoff unless manually closed
        if (!manualCloseRef.current) {
          // 2026-04-20: cap reconnect attempts so a dead socket doesn't spin
          // forever (battery + orphan fetches on mobile). After the cap we
          // stay in "disconnected" so the UI can show a reconnect banner
          // and let the user retry on demand.
          if (reconnectAttemptsRef.current >= MAX_RECONNECT_ATTEMPTS) {
            logger.warn(
              "[WS] max reconnect attempts (%d) exhausted — giving up until manual retry",
              MAX_RECONNECT_ATTEMPTS,
            );
            return;
          }
          reconnectAttemptsRef.current += 1;
          setConnectionState("reconnecting");
          const delay = reconnectDelayRef.current;
          // BUG-9 fix: use connectRef to avoid stale closure
          reconnectTimerRef.current = setTimeout(() => {
            if (mountedRef.current && !manualCloseRef.current) {
              connectRef.current();
            }
          }, delay);
          // Exponential backoff: double the delay, cap at max
          reconnectDelayRef.current = Math.min(
            delay * 2,
            MAX_RECONNECT_DELAY,
          );
        }
      };
    } catch {
      setConnectionState("error");
    }
  }, [clearTimers, startHeartbeat, startTokenRefresh, flushQueue, refreshAndReconnect]);

  // BUG-9 fix: keep ref always pointing to latest connect
  connectRef.current = connect;

  const disconnect = useCallback(() => {
    manualCloseRef.current = true;
    clearTimers();
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setConnectionState("disconnected");
    messageQueueRef.current = [];
  }, [clearTimers]);

  const MAX_QUEUE_SIZE = 50;

  const sendMessage = useCallback((data: unknown) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    } else {
      // Buffer messages while reconnecting, cap at MAX_QUEUE_SIZE to prevent memory leak (#16)
      if (messageQueueRef.current.length >= MAX_QUEUE_SIZE) {
        messageQueueRef.current.shift(); // drop oldest
      }
      messageQueueRef.current.push(data);
    }
  }, []);

  // Auto-connect on mount
  useEffect(() => {
    mountedRef.current = true;
    if (autoConnect) {
      connect();
    }
    return () => {
      mountedRef.current = false;
      clearTimers();
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [autoConnect, connect, clearTimers]);

  // For backwards compatibility
  const isConnected = connectionState === "connected";

  return {
    connectionState,
    isConnected,
    sendMessage,
    connect,
    disconnect,
  };
}
