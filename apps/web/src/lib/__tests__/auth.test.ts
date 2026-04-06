/**
 * Tests for auth utilities (token management).
 *
 * Verifies:
 * - In-memory token storage
 * - sessionStorage fallback for refresh token
 * - Marker cookie management
 * - isAuthenticated() check
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { getToken, getRefreshToken, setTokens, clearTokens, isAuthenticated } from "../auth";

describe("auth utilities", () => {
  beforeEach(() => {
    // Clean state before each test
    clearTokens();
    // Reset cookies
    document.cookie = "vh_authenticated=; path=/; max-age=0";
  });

  describe("getToken / setTokens", () => {
    it("returns null when no token is set", () => {
      expect(getToken()).toBeNull();
    });

    it("returns access token after setTokens", () => {
      setTokens("access-123", "refresh-456");
      expect(getToken()).toBe("access-123");
    });

    it("persists refresh token in sessionStorage", () => {
      setTokens("access-123", "refresh-456");
      expect(sessionStorage.getItem("vh_rt")).toBe("refresh-456");
    });

    it("sets marker cookie on setTokens", () => {
      setTokens("access-123", "refresh-456");
      expect(document.cookie).toContain("vh_authenticated=1");
    });
  });

  describe("getRefreshToken", () => {
    it("returns in-memory refresh token first", () => {
      setTokens("a", "refresh-mem");
      expect(getRefreshToken()).toBe("refresh-mem");
    });

    it("falls back to sessionStorage when in-memory is cleared", () => {
      sessionStorage.setItem("vh_rt", "refresh-storage");
      // Clear only in-memory (not full clearTokens which also clears storage)
      clearTokens();
      sessionStorage.setItem("vh_rt", "refresh-storage");
      expect(getRefreshToken()).toBe("refresh-storage");
    });

    it("returns null when nothing is available", () => {
      expect(getRefreshToken()).toBeNull();
    });
  });

  describe("clearTokens", () => {
    it("clears access token", () => {
      setTokens("a", "r");
      clearTokens();
      expect(getToken()).toBeNull();
    });

    it("clears refresh token from memory and sessionStorage", () => {
      setTokens("a", "r");
      clearTokens();
      expect(getRefreshToken()).toBeNull();
      expect(sessionStorage.getItem("vh_rt")).toBeNull();
    });

    it("removes marker cookie", () => {
      setTokens("a", "r");
      clearTokens();
      expect(document.cookie).not.toContain("vh_authenticated=1");
    });
  });

  describe("isAuthenticated", () => {
    it("returns false when nothing is set", () => {
      expect(isAuthenticated()).toBe(false);
    });

    it("returns true when marker cookie is present", () => {
      document.cookie = "vh_authenticated=1; path=/";
      expect(isAuthenticated()).toBe(true);
    });

    it("returns true when in-memory token exists", () => {
      setTokens("tok", "ref");
      // Even if cookie was somehow cleared, in-memory token counts
      expect(isAuthenticated()).toBe(true);
    });
  });
});
