"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";

/**
 * Web Push subscription management hook (Task X6).
 *
 * Usage:
 *   const { isSupported, isSubscribed, subscribe, unsubscribe, sendTest } = useWebPush();
 *
 * Flow:
 * 1. Check browser support (Notification + ServiceWorker + PushManager)
 * 2. Register service worker (/sw-push.js)
 * 3. Fetch VAPID public key from API
 * 4. Subscribe to push via PushManager.subscribe()
 * 5. Send subscription to backend
 */

type PushState = "unsupported" | "denied" | "prompt" | "subscribed" | "unsubscribed" | "loading";

export function useWebPush() {
  const [state, setState] = useState<PushState>("loading");
  const [error, setError] = useState<string | null>(null);
  const swRegistration = useRef<ServiceWorkerRegistration | null>(null);

  // ── Check support & existing subscription ──
  useEffect(() => {
    if (typeof window === "undefined") return;

    if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
      setState("unsupported");
      return;
    }

    if (Notification.permission === "denied") {
      setState("denied");
      return;
    }

    // Register SW and check existing subscription
    navigator.serviceWorker
      .register("/sw-push.js")
      .then((reg) => {
        swRegistration.current = reg;
        return reg.pushManager.getSubscription();
      })
      .then((sub) => {
        setState(sub ? "subscribed" : "unsubscribed");
      })
      .catch((err) => {
        logger.error("SW registration failed:", err);
        setState("unsupported");
      });
  }, []);

  // ── Subscribe ──
  const subscribe = useCallback(async () => {
    if (!swRegistration.current) return;
    setError(null);
    setState("loading");

    try {
      // 1. Request notification permission
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        setState("denied");
        return;
      }

      // 2. Get VAPID key from API
      const { public_key } = await api.get("/notifications/push/vapid-key");
      if (!public_key) {
        setError("Web Push не настроен на сервере");
        setState("unsubscribed");
        return;
      }

      // 3. Subscribe via PushManager
      const applicationServerKey = urlBase64ToUint8Array(public_key);
      const pushSub = await swRegistration.current.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: applicationServerKey.buffer as ArrayBuffer,
      });

      // 4. Send subscription to backend
      const subJson = pushSub.toJSON();
      await api.post("/notifications/push/subscribe", {
        endpoint: subJson.endpoint,
        keys: subJson.keys,
      });

      setState("subscribed");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Ошибка подписки";
      setError(msg);
      setState("unsubscribed");
    }
  }, []);

  // ── Unsubscribe ──
  const unsubscribe = useCallback(async () => {
    if (!swRegistration.current) return;
    setError(null);

    try {
      const sub = await swRegistration.current.pushManager.getSubscription();
      if (sub) {
        // Remove from backend
        await api.post("/notifications/push/unsubscribe", {
          endpoint: sub.endpoint,
        });
        // Unsubscribe locally
        await sub.unsubscribe();
      }
      setState("unsubscribed");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Ошибка отписки";
      setError(msg);
    }
  }, []);

  // ── Test push ──
  const sendTest = useCallback(async () => {
    try {
      await api.post("/notifications/push/test", {});
    } catch {
      setError("Ошибка отправки тестового пуша");
    }
  }, []);

  return {
    state,
    isSupported: state !== "unsupported",
    isSubscribed: state === "subscribed",
    isDenied: state === "denied",
    isLoading: state === "loading",
    error,
    subscribe,
    unsubscribe,
    sendTest,
  };
}

// ── Utility: Convert VAPID base64url key to Uint8Array ──
function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; i++) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}
