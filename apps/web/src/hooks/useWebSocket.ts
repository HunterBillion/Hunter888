"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createWebSocket } from "@/lib/ws";

interface UseWebSocketOptions {
  onMessage?: (data: { type: string; data: Record<string, unknown> }) => void;
  onError?: (error: Event) => void;
}

export function useWebSocket({ onMessage, onError }: UseWebSocketOptions = {}) {
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const onMessageRef = useRef(onMessage);
  const onErrorRef = useRef(onError);

  onMessageRef.current = onMessage;
  onErrorRef.current = onError;

  useEffect(() => {
    const ws = createWebSocket("/ws/training");
    wsRef.current = ws;

    ws.onopen = () => setIsConnected(true);

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onMessageRef.current?.(data);
      } catch {
        console.error("Failed to parse WebSocket message");
      }
    };

    ws.onerror = (event) => onErrorRef.current?.(event);

    ws.onclose = () => setIsConnected(false);

    return () => {
      ws.close();
    };
  }, []);

  const sendMessage = useCallback((data: unknown) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  return { sendMessage, isConnected };
}
