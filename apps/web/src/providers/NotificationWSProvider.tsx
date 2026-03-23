"use client";

import { useEffect, useRef, useCallback } from "react";
import { getToken } from "@/lib/auth";
import { getWsBaseUrl } from "@/lib/public-origin";
import { useNotificationStore } from "@/stores/useNotificationStore";
import { api } from "@/lib/api";

const MAX_RECONNECT_DELAY = 30_000;
const PING_INTERVAL = 30_000;

/**
 * Global WebSocket provider for notifications.
 * Mounts once in layout, writes to useNotificationStore.
 * Safe for public pages — does nothing without a token.
 */
export function NotificationWSProvider({ children }: { children: React.ReactNode }) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pingTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const reconnectAttempt = useRef(0);
  const mountedRef = useRef(true);

  const connect = useCallback(() => {
    const token = getToken();
    // No token = not authenticated, skip WS entirely
    if (!token) return;
    if (!mountedRef.current) return;

    try {
      const ws = new WebSocket(`${getWsBaseUrl()}/ws/notifications`);
      wsRef.current = ws;

      ws.onopen = () => {
        ws.send(JSON.stringify({ type: "auth", token }));
        reconnectAttempt.current = 0;
        // Start ping
        if (pingTimer.current) clearInterval(pingTimer.current);
        pingTimer.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "ping" }));
          }
        }, PING_INTERVAL);
      };

      ws.onmessage = (event) => {
        if (!mountedRef.current) return;
        try {
          const msg = JSON.parse(event.data);
          const s = useNotificationStore.getState();

          switch (msg.type) {
            case "auth.success":
              s.setWsConnected(true);
              if (msg.data?.unread_count !== undefined) {
                s.setUnread(msg.data.unread_count);
              }
              break;

            case "notification.new":
              if (msg.data) {
                s.addNotification({
                  id: msg.data.id || `n-${Date.now()}`,
                  title: msg.data.title || "",
                  body: msg.data.body || "",
                  type: msg.data.type || "system",
                  client_id: msg.data.client_id,
                  read: false,
                  created_at: msg.data.timestamp || new Date().toISOString(),
                });
                s.addToast({
                  title: msg.data.title || "Уведомление",
                  body: msg.data.body || "",
                  type: msg.data.type || "system",
                });
              }
              break;

            case "consent.received":
            case "consent.revoked":
              s.addToast({
                title: msg.type === "consent.received" ? "Согласие получено" : "Согласие отозвано",
                body: msg.data?.consent_type || "",
                type: "consent",
              });
              break;

            case "reminder.due":
              s.addToast({
                title: "Напоминание",
                body: msg.data?.message || msg.data?.client_name || "",
                type: "reminder",
              });
              break;

            case "pvp.invitation":
              if (msg.data?.challenger_id) {
                const notificationId = `pvp-invite:${msg.data.challenger_id}`;
                s.addNotification({
                  id: notificationId,
                  title: "Приглашение на PvP",
                  body: `${msg.data.challenger_name || "Коллега"} приглашает на дуэль!`,
                  type: "pvp_invitation",
                  read: false,
                  created_at: msg.timestamp || new Date().toISOString(),
                });
                s.addToast({
                  title: "Приглашение на PvP",
                  body: `${msg.data.challenger_name || "Коллега"} приглашает на дуэль!`,
                  type: "pvp_invitation",
                  dedupe_key: `pvp-invitation:${msg.data.challenger_id}`,
                  challenger_id: msg.data.challenger_id,
                  challenger_name: msg.data.challenger_name,
                });
              }
              break;

            case "pong":
              break;
          }
        } catch {
          // ignore malformed
        }
      };

      ws.onclose = () => {
        if (!mountedRef.current) return;
        useNotificationStore.getState().setWsConnected(false);
        if (pingTimer.current) clearInterval(pingTimer.current);
        // Only reconnect if we still have a token
        const currentToken = getToken();
        if (!currentToken) return;
        const delay = Math.min(1000 * Math.pow(2, reconnectAttempt.current), MAX_RECONNECT_DELAY);
        reconnectAttempt.current++;
        reconnectTimer.current = setTimeout(connect, delay);
      };

      ws.onerror = () => {
        ws.close();
      };
    } catch {
      // WebSocket constructor failed — skip
    }
  }, []);

  // Fetch initial notifications via REST (only if authenticated)
  const fetchInitial = useCallback(() => {
    const token = getToken();
    if (!token) return;
    api.get("/notifications?limit=10")
      .then((data) => {
        if (data?.items) {
          useNotificationStore.getState().setItems(data.items);
          const unread = data.items.filter((i: { read: boolean }) => !i.read).length;
          useNotificationStore.getState().setUnread(unread);
        }
      })
      .catch((err) => { console.error("Failed to fetch initial notifications:", err); });
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    fetchInitial();
    connect();

    return () => {
      mountedRef.current = false;
      if (wsRef.current) wsRef.current.close();
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      if (pingTimer.current) clearInterval(pingTimer.current);
    };
  }, [connect, fetchInitial]);

  return <>{children}</>;
}
