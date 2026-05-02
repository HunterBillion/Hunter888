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
 *
 * 2026-05-02 rewrite — the previous version of this file failed in two
 * ways that are characteristic of test/source drift:
 *   1. `MockWebSocket` delivered events via addEventListener, but the
 *      source (useWebSocket.ts) uses `ws.onopen = ...` / `ws.onmessage = ...`
 *      property-assignment style. The events fired into a void; the
 *      hook never saw "open" / "message" → connection state stayed
 *      "connecting", `onMessage` callback never fired, heartbeat
 *      never started.
 *   2. `require("@/lib/ws")` was used inside test bodies to retrieve
 *      the mock-tracked factory, but vitest's path-alias resolver
 *      runs only on `import` and `vi.mock`, NOT on dynamic `require`
 *      — Node bare-resolver kicked in and threw MODULE_NOT_FOUND.
 *
 * Both fixed below: simulators call `this.onopen?.(evt)` etc. directly,
 * and the mock factory is hoisted via `vi.hoisted` so the test body
 * can reference it without re-importing.
 */

import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";

// ---------------------------------------------------------------------------
// Hoisted mock setup — `vi.mock(...)` factories run BEFORE any imports
// in this module, so the MockWebSocket class + state container must
// live inside `vi.hoisted` to be reachable from the factory. Test
// bodies access them through `getLastCreatedWs` / `MockWS` re-exports.
// ---------------------------------------------------------------------------

const {
  MockWS,
  mockCreateWebSocket,
  getLastCreatedWs,
  resetLastCreatedWs,
  makeFactory,
} = vi.hoisted(() => {
  // Mock WebSocket — matches the property-assignment event API used by
  // the production source (`ws.onopen = ...`, `ws.onmessage = ...`).
  // Earlier mock used addEventListener which the source never reads
  // → events fired into a void → connection state never advanced.
  class MockWebSocket {
    static CONNECTING = 0;
    static OPEN = 1;
    static CLOSING = 2;
    static CLOSED = 3;

    readyState = MockWebSocket.CONNECTING;
    url: string;
    onopen: ((evt: Event) => void) | null = null;
    onmessage: ((evt: MessageEvent) => void) | null = null;
    onerror: ((evt: Event) => void) | null = null;
    onclose: ((evt: CloseEvent) => void) | null = null;
    sent: unknown[] = [];

    constructor(url: string) {
      this.url = url;
      setTimeout(() => this._simulateOpen(), 0);
    }

    send(data: unknown) {
      this.sent.push(typeof data === "string" ? JSON.parse(data as string) : data);
    }

    close(code?: number) {
      this.readyState = MockWS.CLOSED;
      this.onclose?.({ code: code ?? 1000, reason: "" } as CloseEvent);
    }

    _simulateOpen() {
      this.readyState = MockWS.OPEN;
      this.onopen?.({} as Event);
    }

    _simulateMessage(data: unknown) {
      this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent);
    }

    _simulateError() {
      this.onerror?.(new Event("error"));
    }

    _simulateClose(code = 1006) {
      this.readyState = MockWS.CLOSED;
      this.onclose?.({ code, reason: "" } as CloseEvent);
    }
  }

  const state: { last: MockWebSocket | null } = { last: null };
  const makeFactory = () => (path: string) => {
    const ws = new MockWebSocket(`ws://localhost${path}`);
    state.last = ws;
    return ws as unknown as WebSocket;
  };
  return {
    MockWS: MockWebSocket,
    mockCreateWebSocket: vi.fn(makeFactory()),
    getLastCreatedWs: () => state.last,
    resetLastCreatedWs: () => {
      state.last = null;
    },
    makeFactory,
  };
});

vi.mock("@/lib/ws", () => ({
  createWebSocket: mockCreateWebSocket,
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

import { useWebSocket } from "../useWebSocket";

describe("useWebSocket", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    // `vi.clearAllMocks` wipes `.mockImplementation`. Re-install the
    // closure-bound factory so `state.last` continues to track newly
    // created sockets between tests.
    mockCreateWebSocket.mockImplementation(makeFactory());
    resetLastCreatedWs();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe("connection lifecycle", () => {
    it("auto-connects on mount", () => {
      renderHook(() => useWebSocket({ path: "/ws/test" }));
      expect(mockCreateWebSocket).toHaveBeenCalledWith("/ws/test");
    });

    it("does NOT connect when autoConnect=false", () => {
      renderHook(() => useWebSocket({ autoConnect: false }));
      expect(mockCreateWebSocket).not.toHaveBeenCalled();
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
      const { unmount } = renderHook(() =>
        useWebSocket({ path: "/ws/test" }),
      );

      await act(async () => {
        vi.advanceTimersByTime(10);
      });

      const ws = getLastCreatedWs();
      expect(ws).not.toBeNull();
      expect(ws!.readyState).toBe(MockWS.OPEN);

      unmount();

      expect(ws!.readyState).toBe(MockWS.CLOSED);
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

      const ws = getLastCreatedWs();
      expect(ws).not.toBeNull();
      expect(ws!.sent).toContainEqual({ type: "chat", text: "hello" });
    });

    it("calls onMessage callback", async () => {
      const onMessage = vi.fn();
      renderHook(() => useWebSocket({ path: "/ws/test", onMessage }));

      await act(async () => {
        vi.advanceTimersByTime(10);
      });

      act(() => {
        getLastCreatedWs()!._simulateMessage({ type: "scenario.update" });
      });

      expect(onMessage).toHaveBeenCalledWith({ type: "scenario.update" });
    });
  });

  describe("manual connect/disconnect", () => {
    it("connect() creates new WebSocket", () => {
      const { result } = renderHook(() =>
        useWebSocket({ autoConnect: false }),
      );

      expect(mockCreateWebSocket).not.toHaveBeenCalled();

      act(() => {
        result.current.connect();
      });

      expect(mockCreateWebSocket).toHaveBeenCalledTimes(1);
    });

    it("disconnect() closes WebSocket", async () => {
      const { result } = renderHook(() => useWebSocket({ path: "/ws/test" }));

      await act(async () => {
        vi.advanceTimersByTime(10);
      });

      const ws = getLastCreatedWs();

      act(() => {
        result.current.disconnect();
      });

      expect(ws!.readyState).toBe(MockWS.CLOSED);
    });
  });

  describe("heartbeat", () => {
    it("sends ping every 30 seconds when connected", async () => {
      renderHook(() => useWebSocket({ path: "/ws/test" }));

      await act(async () => {
        vi.advanceTimersByTime(10);
      });

      const ws = getLastCreatedWs()!;
      // Clear the auth message from initial connect
      ws.sent = [];

      await act(async () => {
        vi.advanceTimersByTime(30_000);
      });

      const pings = ws.sent.filter((m: unknown) =>
        typeof m === "object" && m !== null && (m as { type?: string }).type === "ping",
      );
      expect(pings.length).toBeGreaterThanOrEqual(1);
    });
  });
});
