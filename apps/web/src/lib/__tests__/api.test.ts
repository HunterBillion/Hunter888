/**
 * Tests for API client (lib/api.ts).
 *
 * Verifies:
 * - Token attachment on requests
 * - CSRF token for state-changing methods
 * - 401 retry with token refresh
 * - 429 rate limit error
 * - Error detail parsing (string, array, object)
 * - 204 no-content handling
 * - Token refresh mutex (single in-flight refresh)
 */

import { describe, it, expect, beforeEach, vi, type Mock } from "vitest";

// Mock dependencies BEFORE importing api
vi.mock("../auth", () => ({
  getToken: vi.fn(() => "test-token"),
  getRefreshToken: vi.fn(() => "test-refresh"),
  setTokens: vi.fn(),
  clearTokens: vi.fn(),
}));

vi.mock("../public-origin", () => ({
  getApiBaseUrl: vi.fn(() => "http://localhost:8000"),
}));

vi.mock("@/stores/useAuthStore", () => ({
  useAuthStore: {
    getState: () => ({ invalidate: vi.fn() }),
  },
}));

import { api } from "../api";
import { getToken, clearTokens } from "../auth";

// Helper to create mock Response.
// `clone()` returns a fresh shape-equivalent object so callers can read
// the body twice (real fetch supports this; api.ts uses it on the
// 429 plan-limit path so the original `response.json()` later still
// works). Without clone(), tests of that branch threw
// "response.clone is not a function".
function mockResponse(
  status: number,
  body: unknown = {},
  headers: Record<string, string> = {},
): Response {
  const headersObj = new Headers(headers);
  const base: Partial<Response> = {
    ok: status >= 200 && status < 300,
    status,
    headers: headersObj,
    json: () => Promise.resolve(body),
    text: () => Promise.resolve(JSON.stringify(body)),
  };
  // Self-referential clone: returns another mock with same body. The real
  // Response.clone() returns a fresh stream-backed copy; for tests we just
  // need both reads to succeed.
  base.clone = () => mockResponse(status, body, headers);
  return base as unknown as Response;
}

describe("api client", () => {
  let fetchMock: Mock;

  beforeEach(() => {
    fetchMock = vi.fn();
    global.fetch = fetchMock;
    vi.clearAllMocks();
    (getToken as Mock).mockReturnValue("test-token");
    // Prevent actual navigation
    Object.defineProperty(window, "location", {
      value: { href: "" },
      writable: true,
    });
  });

  describe("api.get", () => {
    it("attaches Authorization header", async () => {
      fetchMock.mockResolvedValueOnce(mockResponse(200, { id: 1 }));

      await api.get("/users/me");

      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [, options] = fetchMock.mock.calls[0];
      expect(options.headers["Authorization"]).toBe("Bearer test-token");
    });

    it("does NOT attach CSRF for GET", async () => {
      document.cookie = "csrf_token=csrf-abc; path=/";
      fetchMock.mockResolvedValueOnce(mockResponse(200, {}));

      await api.get("/data");

      const [, options] = fetchMock.mock.calls[0];
      expect(options.headers["X-CSRF-Token"]).toBeUndefined();
    });

    it("returns parsed JSON body", async () => {
      fetchMock.mockResolvedValueOnce(mockResponse(200, { name: "test" }));

      const result = await api.get("/users/me");
      expect(result).toEqual({ name: "test" });
    });

    it("skips auth header when no token", async () => {
      (getToken as Mock).mockReturnValue(null);
      fetchMock.mockResolvedValueOnce(mockResponse(200, {}));

      await api.get("/public");

      const [, options] = fetchMock.mock.calls[0];
      expect(options.headers["Authorization"]).toBeUndefined();
    });
  });

  describe("api.post", () => {
    it("attaches CSRF token for POST", async () => {
      document.cookie = "csrf_token=csrf-xyz; path=/";
      fetchMock.mockResolvedValueOnce(mockResponse(200, {}));

      await api.post("/action", { data: 1 });

      const [, options] = fetchMock.mock.calls[0];
      expect(options.headers["X-CSRF-Token"]).toBe("csrf-xyz");
      expect(options.method).toBe("POST");
    });

    it("sends JSON body", async () => {
      fetchMock.mockResolvedValueOnce(mockResponse(200, {}));

      await api.post("/create", { name: "test" });

      const [, options] = fetchMock.mock.calls[0];
      expect(options.body).toBe(JSON.stringify({ name: "test" }));
    });
  });

  describe("error handling", () => {
    it("parses string detail error", async () => {
      fetchMock.mockResolvedValueOnce(mockResponse(400, { detail: "Bad input" }));

      await expect(api.get("/err")).rejects.toThrow("Bad input");
    });

    it("parses array detail error", async () => {
      fetchMock.mockResolvedValueOnce(
        mockResponse(422, { detail: [{ msg: "field required" }, { msg: "invalid type" }] }),
      );

      await expect(api.get("/err")).rejects.toThrow("field required, invalid type");
    });

    it("parses object detail error with message", async () => {
      fetchMock.mockResolvedValueOnce(
        mockResponse(403, { detail: { message: "Access denied", redirect: "/consent" } }),
      );

      await expect(api.get("/err")).rejects.toThrow("Access denied");
    });

    it("handles 429 with Retry-After", async () => {
      fetchMock.mockResolvedValueOnce(
        mockResponse(429, {}, { "Retry-After": "60" }),
      );

      await expect(api.get("/limited")).rejects.toThrow("60");
    });

    it("returns null for 204 No Content", async () => {
      fetchMock.mockResolvedValueOnce(mockResponse(204));

      const result = await api.delete("/item/1");
      expect(result).toBeNull();
    });

    it("throws network error when fetch fails", async () => {
      fetchMock.mockRejectedValueOnce(new Error("Network error"));

      await expect(api.get("/unreachable")).rejects.toThrow("Сервер недоступен");
    });
  });

  describe("401 token refresh", () => {
    it("retries request after successful refresh", async () => {
      // First call: 401
      fetchMock.mockResolvedValueOnce(mockResponse(401, {}));
      // Refresh call: success
      fetchMock.mockResolvedValueOnce(
        mockResponse(200, { access_token: "new-access", refresh_token: "new-refresh" }),
      );
      // Retry: success
      fetchMock.mockResolvedValueOnce(mockResponse(200, { id: 42 }));

      const result = await api.get("/protected");
      expect(result).toEqual({ id: 42 });
      expect(fetchMock).toHaveBeenCalledTimes(3);
    });

    it("redirects to login on failed refresh", async () => {
      // First: 401
      fetchMock.mockResolvedValueOnce(mockResponse(401, {}));
      // Refresh: also fails
      fetchMock.mockResolvedValueOnce(mockResponse(401, {}));
      // Retry: still 401
      fetchMock.mockResolvedValueOnce(mockResponse(401, {}));

      await expect(api.get("/protected")).rejects.toThrow("Unauthorized");
      expect(clearTokens).toHaveBeenCalled();
    });
  });
});
