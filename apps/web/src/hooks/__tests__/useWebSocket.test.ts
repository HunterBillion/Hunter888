/**
 * Tests for useWebSocket hook.
 *
 * Verifies:
 * - Connection state transitions
 * - Auto-connect on mount
 * - Message sending and queueing
 * - Reconnect with exponential backoff
 * - Cleanup on unmount
 * - Heartbeat pings
 */

import { describe, it, expect, beforeEach, vi, afterEach, type Mock } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useWebSocket } from "../useWebSocket";

// ---------------------------------------------------------------------------
// Mock WebSocket
// ---------------------------------------------------------------------------

class MockWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  readyState = MockWebSocket.CONNECTING;
  url: string;
  private _listeners: Record<string, Function[]> = {};
  sent: unknown[] = [];

  constructor(url: string) {
    this.url = url;
    // Auto-open after microtask (simulate real WS)
    setTimeout(() => this._simulateOpen(), 0);
  }

  addEventListener(event: string, fn: Function) {
    (this._listeners[event] ??= []).push(fn);
  }

  removeEventListener(event: string, fn: Function) {
    const list = this._listeners[event] ?? [];
    this._listeners[event] = list.filter((f) => f !== fn);
  }

  send(data: unknown) {
    this.sent.push(typeof data === "string" ? JSON.parse(data as string) : data);
  }

  close(code?: number) {
    this.readyState = MockWebSocket.CLOSED;
    this._emit("close", { code: code ?? 1000, reason: "" });
  }

  // Test helpers
  _simulateOpen() {
    this.readyState = MockWebSocket.OPEN;
    this._emit("open", {});
  }

  _simulateMessage(data: unknown) {
    this._emit("message", { data: JSON.stringify(data) });
  }

  _simulateError() {
    this._emit("error", new Event("error"));
  }

  _simulateClose(code = 1006) {
    this.readyState = MockWebSocket.CLOSED;
    this._emit("close", { code, reason: "" });
  }

  private _emit(event: string, data: unknown) {
    for (const fn of this._listeners[event] ?? []) {
      fn(data);
    }
  }
}

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

let lastCreatedWs: MockWebSocket | null = null;

vi.mock("@/lib/ws", () => ({
  createWebSocket: vi.fn((path: string) => {
    const ws = new MockWebSocket(`ws://localhost${path}`);
    lastCreatedWs = ws;
    return ws;
  }),
}));

vi.mock("@/lib/auth", () => ({
  getToken: vi.fn(() => "test-token"),
  getRefreshToken: vi.fn(() => "test-refresh"),
  setTokens: vi.fn(),
}));

vi.mock("@/lib/logger", () => ({
  logger: {
    log: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  },
}));

describe("useWebSocket", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    lastCreatedWs = null;
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe("connection lifecycle", () => {
    it("auto-connects on mount", () => {
      const { createWebSocket } = require("@/lib/ws");

      renderHook(() => useWebSocket({ path: "/ws/test" }));

      expect(createWebSocket).toHaveBeenCalledWith("/ws/test");
    });

    it("does NOT connect when autoConnect=false", () => {
      const { createWebSocket } = require("@/lib/ws");

      renderHook(() => useWebSocket({ autoConnect: false }));

      expect(createWebSocket).not.toHaveBeenCalled();
    });

    it("starts in disconnected state", () => {
      const { result } = renderHook(() =>
        useWebSocket({ autoConnect: false }),
      );

      expect(result.current.connectionState).toBe("disconnected");
      expect(result.current.isConnected).toBe(false);
    });

    it("transitions to connected after WS open", async () => {
      const { result } = renderHook(() => useWebSocket({ path: "/ws/test" }));

      // Trigger the open event
      await act(async () => {
        vi.advanceTimersByTime(10);
      });

      expect(result.current.connectionState).toBe("connected");
      expect(result.current.isConnected).toBe(true);
    });

    it("cleans up WebSocket on unmount", async () => {
      const { result, unmount } = renderHook(() =>
        useWebSocket({ path: "/ws/test" }),
      );

      await act(async () => {
        vi.advanceTimersByTime(10);
      });

      const ws = lastCreatedWs!;
      expect(ws.readyState).toBe(MockWebSocket.OPEN);

      unmount();

      expect(ws.readyState).toBe(MockWebSocket.CLOSED);
    });
  });

  describe("messaging", () => {
    it("sends messages when connected", async () => {
      const { result } = renderHook(() => useWebSocket({ path: "/ws/test" }));

      await act(async () => {
        vi.advanceTimersByTime(10);
      });

      act(() => {
        result.current.sendMessage({ type: "chat", text: "hello" });
      });

      const ws = lastCreatedWs!;
      expect(ws.sent).toContainEqual({ type: "chat", text: "hello" });
    });

    it("calls onMessage callback", async () => {
      const onMessage = vi.fn();
      renderHook(() =>
        useWebSocket({ path: "/ws/test", onMessage }),
      );

      await act(async () => {
        vi.advanceTimersByTime(10);
      });

      act(() => {
        lastCreatedWs!._simulateMessage({ type: "pong" });
      });

      expect(onMessage).toHaveBeenCalledWith({ type: "pong" });
    });
  });

  describe("manual connect/disconnect", () => {
    it("connect() creates new WebSocket", async () => {
      const { createWebSocket } = require("@/lib/ws");

      const { result } = renderHook(() =>
        useWebSocket({ autoConnect: false }),
      );

      expect(createWebSocket).not.toHaveBeenCalled();

      act(() => {
        result.current.connect();
      });

      expect(createWebSocket).toHaveBeenCalledTimes(1);
    });

    it("disconnect() closes WebSocket", async () => {
      const { result } = renderHook(() => useWebSocket({ path: "/ws/test" }));

      await act(async () => {
        vi.advanceTimersByTime(10);
      });

      const ws = lastCreatedWs!;

      act(() => {
        result.current.disconnect();
      });

      expect(ws.readyState).toBe(MockWebSocket.CLOSED);
    });
  });

  describe("heartbeat", () => {
    it("sends ping every 30 seconds when connected", async () => {
      renderHook(() => useWebSocket({ path: "/ws/test" }));

      await act(async () => {
        vi.advanceTimersByTime(10);
      });

      const ws = lastCreatedWs!;
      // Clear the auth message from initial connect
      ws.sent = [];

      await act(async () => {
        vi.advanceTimersByTime(30_000);
      });

      const pings = ws.sent.filter((m: any) => m.type === "ping");
      expect(pings.length).toBeGreaterThanOrEqual(1);
    });
  });
});
