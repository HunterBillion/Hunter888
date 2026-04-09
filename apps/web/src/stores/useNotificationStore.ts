import { create } from "zustand";

export interface NotificationItem {
  id: string;
  title: string;
  body: string;
  type: string;
  client_id?: string;
  read: boolean;
  created_at: string;
}

export interface Toast {
  id: string;
  title: string;
  body: string;
  type: string;
  ts: number;
  dedupe_key?: string;
  challenger_id?: string;
  challenger_name?: string;
}

interface NotificationState {
  items: NotificationItem[];
  unread: number;
  wsConnected: boolean;
  toasts: Toast[];

  setItems: (items: NotificationItem[]) => void;
  addNotification: (item: NotificationItem) => void;
  markRead: (id: string) => void;
  setUnread: (n: number) => void;
  setWsConnected: (connected: boolean) => void;
  addToast: (toast: Omit<Toast, "id" | "ts">) => void;
  removeToast: (id: string) => void;
  clear: () => void;
}

let _toastCounter = 0;

/**
 * Cross-tab notification sync via BroadcastChannel.
 * When a notification is marked read in one tab, all other tabs update too.
 */
const _channel = typeof BroadcastChannel !== "undefined"
  ? new BroadcastChannel("vh-notifications")
  : null;

export const useNotificationStore = create<NotificationState>((set) => {
  // Listen for cross-tab messages
  _channel?.addEventListener("message", (e) => {
    if (e.data?.type === "mark-read") {
      set((s) => ({
        items: s.items.map((i) => (i.id === e.data.id ? { ...i, read: true } : i)),
        unread: Math.max(0, s.unread - 1),
      }));
    }
    if (e.data?.type === "dismiss-toast") {
      set((s) => ({ toasts: s.toasts.filter((t) => t.id !== e.data.id) }));
    }
  });

  return {
  items: [],
  unread: 0,
  wsConnected: false,
  toasts: [],

  setItems: (items) => set({ items }),
  addNotification: (item) =>
    set((s) => ({
      items: [item, ...s.items.filter((existing) => existing.id !== item.id)].slice(0, 50),
      unread:
        s.items.some((existing) => existing.id === item.id)
          ? s.unread
          : s.unread + (item.read ? 0 : 1),
    })),
  markRead: (id) => {
    set((s) => ({
      items: s.items.map((i) => (i.id === id ? { ...i, read: true } : i)),
      unread: Math.max(0, s.unread - 1),
    }));
    // Broadcast to other tabs
    _channel?.postMessage({ type: "mark-read", id });
  },
  setUnread: (n) => set({ unread: n }),
  setWsConnected: (connected) => set({ wsConnected: connected }),
  addToast: (toast) => {
    const id = `toast-${++_toastCounter}`;
    set((s) => {
      const dedupeKey = toast.dedupe_key || `${toast.type}:${toast.title}:${toast.body}`;
      const filtered = s.toasts.filter((t) => (t.dedupe_key || `${t.type}:${t.title}:${t.body}`) !== dedupeKey);
      return {
        toasts: [...filtered, { ...toast, id, ts: Date.now(), dedupe_key: dedupeKey }].slice(-5),
      };
    });
    // Auto-dismiss after 5s
    setTimeout(() => {
      set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }));
    }, 5000);
  },
  removeToast: (id) => {
    set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }));
    _channel?.postMessage({ type: "dismiss-toast", id });
  },
  clear: () => set({ items: [], unread: 0, wsConnected: false, toasts: [] }),
};
});
