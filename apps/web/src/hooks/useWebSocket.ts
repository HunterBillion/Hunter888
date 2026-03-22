"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { logger } from "@/lib/logger";
import { createWebSocket } from "@/lib/ws";
import type { WSConnectionState, WSMessage } from "@/types";

interface UseWebSocketOptions {
  path?: string;
  onMessage?: (data: WSMessage) => void;
  onError?: (error: Event) => void;
  autoConnect?: boolean;
}

const HEARTBEAT_INTERVAL = 30_000; // 30 seconds
const MAX_RECONNECT_DELAY = 30_000; // 30 seconds max
const INITIAL_RECONNECT_DELAY = 1_000; // 1 second

export function useWebSocket({
  path = "/ws/training",
  onMessage,
  onError,
  autoConnect = true,
}: UseWebSocketOptions = {}) {
  const [connectionState, setConnectionState] =
    useState<WSConnectionState>("disconnected");

  const wsRef = useRef<WebSocket | null>(null);
  const onMessageRef = useRef(onMessage);
  const onErrorRef = useRef(onError);
  const reconnectDelayRef = useRef(INITIAL_RECONNECT_DELAY);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const heartbeatTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const messageQueueRef = useRef<unknown[]>([]);
  const mountedRef = useRef(true);
  const manualCloseRef = useRef(false);
  const pathRef = useRef(path);

  // Keep callback refs up to date
  onMessageRef.current = onMessage;
  onErrorRef.current = onError;
  pathRef.current = path;

  const clearTimers = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (heartbeatTimerRef.current) {
      clearInterval(heartbeatTimerRef.current);
      heartbeatTimerRef.current = null;
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

  const flushQueue = useCallback(() => {
    while (
      messageQueueRef.current.length > 0 &&
      wsRef.current?.readyState === WebSocket.OPEN
    ) {
      const msg = messageQueueRef.current.shift();
      wsRef.current.send(JSON.stringify(msg));
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

    manualCloseRef.current = false;
    setConnectionState("connecting");

    try {
      const ws = createWebSocket(pathRef.current);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!mountedRef.current) return;
        setConnectionState("connected");
        reconnectDelayRef.current = INITIAL_RECONNECT_DELAY;
        startHeartbeat();
        flushQueue();
      };

      ws.onmessage = (event) => {
        if (!mountedRef.current) return;
        try {
          const data = JSON.parse(event.data);
          // Ignore pong messages
          if (data.type === "pong") return;
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
        setConnectionState("disconnected");

        // 1008 = Policy Violation (auth denied) — redirect to login
        if (event.code === 1008) {
          window.location.href = "/login";
          return;
        }

        // Auto-reconnect with exponential backoff unless manually closed
        if (!manualCloseRef.current) {
          const delay = reconnectDelayRef.current;
          reconnectTimerRef.current = setTimeout(() => {
            if (mountedRef.current && !manualCloseRef.current) {
              connect();
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
  }, [clearTimers, startHeartbeat, flushQueue]);

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

  const sendMessage = useCallback((data: unknown) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    } else {
      // Buffer messages while reconnecting
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
