/**
 * Service Worker for Web Push Notifications (Task X6).
 *
 * Handles:
 * - Push event → show notification with title, body, icon, actions
 * - Notification click → open/focus the app at the specified URL
 * - Notification close → analytics (optional)
 */

/* eslint-disable no-restricted-globals */

const APP_NAME = "Hunter888";

// ── Push Event ──
self.addEventListener("push", (event) => {
  if (!event.data) return;

  let payload;
  try {
    payload = event.data.json();
  } catch {
    payload = { title: APP_NAME, body: event.data.text() };
  }

  const {
    title = APP_NAME,
    body = "",
    icon = "/icon-192.png",
    badge = "/badge-72.png",
    tag = "default",
    url = "/",
    data = {},
  } = payload;

  const options = {
    body,
    icon,
    badge,
    tag,
    renotify: true,
    requireInteraction: false,
    vibrate: [100, 50, 100],
    data: { url, ...data },
    actions: [
      { action: "open", title: "Открыть" },
      { action: "dismiss", title: "Закрыть" },
    ],
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

// ── Notification Click ──
self.addEventListener("notificationclick", (event) => {
  event.notification.close();

  if (event.action === "dismiss") return;

  const urlToOpen = event.notification.data?.url || "/";

  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
      // Focus existing tab if open
      for (const client of clientList) {
        if (client.url.includes(self.location.origin) && "focus" in client) {
          client.navigate(urlToOpen);
          return client.focus();
        }
      }
      // Open new tab
      return clients.openWindow(urlToOpen);
    }),
  );
});

// ── Notification Close (analytics) ──
self.addEventListener("notificationclose", (_event) => {
  // Could send analytics event here
});

// ── Service Worker Install ──
self.addEventListener("install", () => {
  self.skipWaiting();
});

// ── Service Worker Activate ──
self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});
