import { create } from "zustand";
import { toast as sonnerToast } from "sonner";

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
    // 2026-05-05 — Plain toast routing was duplicated between this
    // legacy store and `sonner`. The store stays as the home for
    // *interactive* toasts (PvP duel invites with their own UI: Accept
    // / Decline action buttons rendered by NotificationBell), and
    // everything else goes through sonner (the project-wide default
    // toast surface, mounted in components/providers/Providers).
    //
    // Heuristic: a toast that carries a `challenger_id` or a real-time
    // `pvp_invitation` type is always interactive — keep it here.
    // Anything else (plain success/error/info from a click handler,
    // background fetch failure) is fire-and-forget — route to sonner so
    // the user sees ONE consistent toast style across the app.
    const isInteractive = toast.type === "pvp_invitation" || !!toast.challenger_id;
    if (!isInteractive) {
      // Map legacy `type` to sonner's named methods. Unknown types
      // (and empty / undefined) fall back to a neutral toast so we
      // never silently drop a notification.
      const t = toast.type;
      if (t === "error") sonnerToast.error(toast.title, toast.body ? { description: toast.body } : undefined);
      else if (t === "success") sonnerToast.success(toast.title, toast.body ? { description: toast.body } : undefined);
      else if (t === "warn" || t === "warning") sonnerToast.warning(toast.title, toast.body ? { description: toast.body } : undefined);
      else if (t === "info") sonnerToast.info(toast.title, toast.body ? { description: toast.body } : undefined);
      else sonnerToast(toast.title, toast.body ? { description: toast.body } : undefined);
      return;
    }

    // Interactive path (kept for PvP duel invites & similar):
    // dedupe + keep last 5 + auto-dismiss after 5s.
    const id = `toast-${++_toastCounter}`;
    set((s) => {
      const dedupeKey = toast.dedupe_key || `${toast.type}:${toast.title}:${toast.body}`;
      const filtered = s.toasts.filter((t) => (t.dedupe_key || `${t.type}:${t.title}:${t.body}`) !== dedupeKey);
      return {
        toasts: [...filtered, { ...toast, id, ts: Date.now(), dedupe_key: dedupeKey }].slice(-5),
      };
    });
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
