/**
 * Tests for useAuthStore (Zustand auth state).
 *
 * Verifies:
 * - fetchUser with caching (30s TTL)
 * - Request deduplication (in-flight promise reuse)
 * - Preference race condition protection (_prefsVersion)
 * - logout cleanup
 * - updatePreferences merging
 * - No-token fast path
 */

import { describe, it, expect, beforeEach, vi, type Mock } from "vitest";
import { act } from "@testing-library/react";

// Mock dependencies
vi.mock("@/lib/api", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

vi.mock("@/lib/auth", () => ({
  getToken: vi.fn(() => "test-token"),
  clearTokens: vi.fn(),
}));

vi.mock("@/components/layout/AuthLayout", () => ({
  resetConsentCache: vi.fn(),
}));

import { useAuthStore } from "../useAuthStore";
import { api } from "@/lib/api";
import { getToken, clearTokens } from "@/lib/auth";
import { resetConsentCache } from "@/components/layout/AuthLayout";

const mockUser = {
  id: "user-1",
  email: "test@example.com",
  full_name: "Test User",
  role: "manager",
  preferences: { accent_color: "blue", compact_mode: false },
};

describe("useAuthStore", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset store to clean state
    useAuthStore.setState({
      user: null,
      loading: true,
      _fetchPromise: null,
      _fetchTs: 0,
      _prefsVersion: 0,
    });
    (getToken as Mock).mockReturnValue("test-token");
  });

  describe("fetchUser", () => {
    it("fetches user from API and stores it", async () => {
      (api.get as Mock).mockResolvedValueOnce(mockUser);

      const user = await useAuthStore.getState().fetchUser();

      expect(api.get).toHaveBeenCalledWith("/auth/me");
      expect(user).toBeTruthy();
      expect(useAuthStore.getState().user?.email).toBe("test@example.com");
      expect(useAuthStore.getState().loading).toBe(false);
    });

    it("returns null and sets loading=false when no token", async () => {
      (getToken as Mock).mockReturnValue(null);

      const user = await useAuthStore.getState().fetchUser();

      expect(user).toBeNull();
      expect(useAuthStore.getState().loading).toBe(false);
      expect(api.get).not.toHaveBeenCalled();
    });

    it("returns cached user within TTL", async () => {
      (api.get as Mock).mockResolvedValueOnce(mockUser);

      // First fetch
      await useAuthStore.getState().fetchUser();
      // Second fetch — should NOT call API again
      const user = await useAuthStore.getState().fetchUser();

      expect(api.get).toHaveBeenCalledTimes(1);
      expect(user?.email).toBe("test@example.com");
    });

    it("deduplicates concurrent fetches", async () => {
      let resolveApi: (value: unknown) => void;
      (api.get as Mock).mockReturnValue(
        new Promise((r) => {
          resolveApi = r;
        }),
      );

      // Fire two concurrent fetches
      const p1 = useAuthStore.getState().fetchUser();
      const p2 = useAuthStore.getState().fetchUser();

      // They should share the same promise
      resolveApi!(mockUser);
      const [u1, u2] = await Promise.all([p1, p2]);

      expect(api.get).toHaveBeenCalledTimes(1);
      expect(u1).toBeTruthy();
      expect(u2).toBeTruthy();
    });

    it("handles API error gracefully", async () => {
      (api.get as Mock).mockRejectedValueOnce(new Error("Network error"));

      const user = await useAuthStore.getState().fetchUser();

      expect(user).toBeNull();
      expect(useAuthStore.getState().user).toBeNull();
      expect(useAuthStore.getState().loading).toBe(false);
    });
  });

  describe("updatePreferences", () => {
    it("merges preferences into current user", () => {
      useAuthStore.setState({ user: { ...mockUser } as any });

      useAuthStore.getState().updatePreferences({ accent_color: "emerald" });

      const prefs = useAuthStore.getState().user?.preferences as any;
      expect(prefs.accent_color).toBe("emerald");
      // Other prefs preserved
      expect(prefs.compact_mode).toBe(false);
    });

    it("increments _prefsVersion", () => {
      useAuthStore.setState({ user: { ...mockUser } as any, _prefsVersion: 0 });

      useAuthStore.getState().updatePreferences({ compact_mode: true });

      expect(useAuthStore.getState()._prefsVersion).toBe(1);
    });

    it("does nothing when no user", () => {
      useAuthStore.setState({ user: null, _prefsVersion: 0 });

      useAuthStore.getState().updatePreferences({ accent_color: "rose" });

      expect(useAuthStore.getState()._prefsVersion).toBe(0);
    });

    it("prevents fetch from overwriting local preferences", async () => {
      useAuthStore.setState({ user: { ...mockUser } as any, _prefsVersion: 0, _fetchTs: 0 });

      // Start a fetch that will resolve with OLD preferences
      let resolveApi: (value: unknown) => void;
      (api.get as Mock).mockReturnValue(
        new Promise((r) => {
          resolveApi = r;
        }),
      );

      const fetchPromise = useAuthStore.getState().fetchUser();

      // While fetch is in-flight, user changes preferences locally
      useAuthStore.getState().updatePreferences({ accent_color: "rose" });

      // Now resolve fetch with OLD data
      resolveApi!({ ...mockUser, preferences: { accent_color: "blue", compact_mode: false } });
      await fetchPromise;

      // Local preference should WIN (not overwritten by stale fetch)
      const prefs = useAuthStore.getState().user?.preferences as any;
      expect(prefs.accent_color).toBe("rose");
    });
  });

  describe("logout", () => {
    it("clears all state", async () => {
      useAuthStore.setState({
        user: { ...mockUser } as any,
        _prefsVersion: 5,
        _fetchTs: Date.now(),
      });
      (api.post as Mock).mockResolvedValueOnce({});

      await useAuthStore.getState().logout();

      const state = useAuthStore.getState();
      expect(state.user).toBeNull();
      expect(state.loading).toBe(false);
      expect(state._fetchPromise).toBeNull();
      expect(state._fetchTs).toBe(0);
      expect(state._prefsVersion).toBe(0);
    });

    it("calls clearTokens and resetConsentCache", async () => {
      useAuthStore.setState({ user: { ...mockUser } as any });
      (api.post as Mock).mockResolvedValueOnce({});

      await useAuthStore.getState().logout();

      expect(clearTokens).toHaveBeenCalled();
      expect(resetConsentCache).toHaveBeenCalled();
    });

    it("succeeds even if server logout fails", async () => {
      useAuthStore.setState({ user: { ...mockUser } as any });
      (api.post as Mock).mockRejectedValueOnce(new Error("Server down"));

      // Should not throw
      await useAuthStore.getState().logout();

      expect(useAuthStore.getState().user).toBeNull();
      expect(clearTokens).toHaveBeenCalled();
    });
  });

  describe("invalidate", () => {
    it("resets fetch timestamp so next fetchUser hits API", async () => {
      (api.get as Mock).mockResolvedValue(mockUser);

      // Populate cache
      await useAuthStore.getState().fetchUser();
      expect(api.get).toHaveBeenCalledTimes(1);

      // Invalidate
      useAuthStore.getState().invalidate();

      // Next fetch should hit API again
      await useAuthStore.getState().fetchUser();
      expect(api.get).toHaveBeenCalledTimes(2);
    });
  });

  describe("setUser", () => {
    it("directly sets user", () => {
      useAuthStore.getState().setUser(mockUser as any);
      expect(useAuthStore.getState().user?.email).toBe("test@example.com");
    });

    it("can set to null", () => {
      useAuthStore.setState({ user: mockUser as any });
      useAuthStore.getState().setUser(null);
      expect(useAuthStore.getState().user).toBeNull();
    });
  });
});
