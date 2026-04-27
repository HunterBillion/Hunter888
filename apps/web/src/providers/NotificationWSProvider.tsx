"use client";

import { useEffect, useRef, useCallback } from "react";
import { getToken } from "@/lib/auth";
import { getWsBaseUrl } from "@/lib/public-origin";
import { useNotificationStore, type NotificationItem } from "@/stores/useNotificationStore";
import { usePolicyStore, type PolicySeverity } from "@/stores/usePolicyStore";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";

const MAX_RECONNECT_DELAY = 30_000;
const PING_INTERVAL = 30_000;

// Module-level flags — survive component remounts during SPA navigation.
// Prevents re-fetching notifications and re-connecting WS on every route change.
// BUG-4 fix: track which token the flags belong to — reset on user change.
let _initialFetchDone = false;
let _wsConnected = false;
let _lastTokenHash = "";

/**
 * Reset module-level flags on logout. Call this from clearTokens / logout handler
 * so that the next login (same or different user) re-fetches and re-connects.
 */
export function resetNotificationWSFlags(): void {
  _initialFetchDone = false;
  _wsConnected = false;
  _lastTokenHash = "";
}

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

    // BUG-4 fix: detect user change (different token) → reset module flags
    const tokenHash = token.slice(-16);
    if (_lastTokenHash && _lastTokenHash !== tokenHash) {
      _initialFetchDone = false;
      _wsConnected = false;
      // Close stale connection from previous user
      if (wsRef.current) {
        try { wsRef.current.close(); } catch {}
        wsRef.current = null;
      }
      useNotificationStore.getState().clear();
    }
    _lastTokenHash = tokenHash;

    // Already have a live WS from a previous mount — skip
    if (_wsConnected && wsRef.current && wsRef.current.readyState === WebSocket.OPEN) return;

    // FIX 19: Close any existing connection before opening a new one.
    // Prevents duplicate WS connections after rapid reconnect/token refresh.
    if (wsRef.current) {
      try { wsRef.current.close(); } catch {}
      wsRef.current = null;
    }

    try {
      const ws = new WebSocket(`${getWsBaseUrl()}/ws/notifications`);
      wsRef.current = ws;

      ws.onopen = () => {
        ws.send(JSON.stringify({ type: "auth", token }));
        reconnectAttempt.current = 0;
        _wsConnected = true;
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
              if ((msg.data?.unread_count ?? msg.unread_count) !== undefined) {
                s.setUnread(msg.data?.unread_count ?? msg.unread_count);
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

            // TZ-4 §10 / §13.4.1 — conversation policy audit fan-out.
            // The hook in ws/training.py emits one frame per violation
            // alongside a paired persona frame for identity-class
            // codes; the store fans out per-session so multiple open
            // tabs (e.g. PvP + CRM call) keep their counters separate.
            case "conversation.policy_violation_detected": {
              const sessionId = msg.data?.session_id;
              const severity = msg.data?.severity as PolicySeverity | undefined;
              if (typeof sessionId === "string" && severity) {
                usePolicyStore
                  .getState()
                  .recordPolicyViolation(
                    sessionId,
                    severity,
                    Boolean(msg.data?.enforce_active),
                  );
              }
              break;
            }

            // TZ-4 §9.3 — paired persona conflict frame; bumps the
            // dedicated badge counter and stashes the
            // ``attempted_field`` for tooltip consumption.
            case "persona.conflict_detected": {
              const sessionId = msg.data?.session_id;
              if (typeof sessionId === "string") {
                const af = msg.data?.attempted_field;
                usePolicyStore
                  .getState()
                  .recordPersonaConflict(
                    sessionId,
                    typeof af === "string" ? af : null,
                  );
              }
              break;
            }

            case "pong":
              break;
          }
        } catch {
          // ignore malformed
        }
      };

      ws.onclose = () => {
        // FIX 18: Clear ref immediately so no stale onmessage callbacks fire
        if (wsRef.current === ws) wsRef.current = null;
        _wsConnected = false;
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

  // Fetch initial notifications via REST — only once per browser session
  const fetchInitial = useCallback(() => {
    if (_initialFetchDone) return;
    const token = getToken();
    if (!token) return;
    _initialFetchDone = true;
    api.get("/notifications?limit=10")
      .then((data: unknown) => {
        if (!mountedRef.current) return;
        if (data && typeof data === "object" && "items" in data && Array.isArray((data as Record<string, unknown>).items)) {
          const items = (data as { items: Array<{ read: boolean }> }).items;
          useNotificationStore.getState().setItems(items as NotificationItem[]);
          const unread = items.filter((i) => !i.read).length;
          useNotificationStore.getState().setUnread(unread);
        }
      })
      .catch((err: unknown) => {
        // Non-critical: WS will provide live data; log for debugging
        if (mountedRef.current) {
          logger.error("Failed to fetch initial notifications:", err);
        }
      });
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    fetchInitial();
    connect();

    return () => {
      mountedRef.current = false;
      // Don't close WS on unmount — it survives SPA navigation via module-level refs.
      // Only cancel pending reconnect timers for this mount cycle.
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
    };
  }, [connect, fetchInitial]);

  return <>{children}</>;
}
