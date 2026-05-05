/**
 * Regression tests for the dashboard tab/sub-tab routing helpers.
 *
 * These cases were the most regression-prone surface of the 2026-05-05
 * dashboard refactor — once you rename a top-level tab, three things
 * have to keep working forever:
 *   1. legacy URLs from emails/bookmarks/history
 *   2. retired ids that may still be hitting the page
 *   3. unknown garbage that should never strand the user
 */
import { describe, it, expect } from "vitest";
import {
  resolveTabParam,
  resolveSystemSub,
  TAB_ALIASES,
  SYSTEM_SUB_ALIASES,
} from "../dashboard-tabs";

describe("resolveTabParam", () => {
  it("returns null when there's no tab in the URL", () => {
    expect(resolveTabParam(null)).toBeNull();
    expect(resolveTabParam("")).toBeNull();
  });

  it("passes canonical tab ids through unchanged", () => {
    for (const id of ["overview", "team", "tournament", "audit", "content", "reports", "system"]) {
      expect(resolveTabParam(id)).toBe(id);
    }
  });

  it("remaps legacy ids to canonical ids", () => {
    expect(resolveTabParam("methodology")).toBe("content");
    expect(resolveTabParam("analytics")).toBe("team");
    expect(resolveTabParam("activity")).toBe("audit");
  });

  it("falls back to overview for retired ids (e.g. scoring)", () => {
    // `scoring` was removed as a placeholder sub-tab on 2026-05-05;
    // a stale ?tab=scoring URL should land on overview, not blank.
    expect(resolveTabParam("scoring")).toBe("overview");
  });

  it("falls back to overview for completely unknown ids", () => {
    expect(resolveTabParam("garbage")).toBe("overview");
    expect(resolveTabParam("WIKI")).toBe("overview"); // case-sensitive on purpose
    expect(resolveTabParam("../etc/passwd")).toBe("overview");
  });

  it("legacy alias map matches the documented set", () => {
    expect(Object.keys(TAB_ALIASES).sort()).toEqual([
      "activity",
      "analytics",
      "methodology",
    ]);
  });
});

describe("resolveSystemSub", () => {
  it("defaults to users when no sub is given", () => {
    expect(resolveSystemSub(null)).toBe("users");
    expect(resolveSystemSub("")).toBe("users");
  });

  it("passes canonical sub ids through unchanged", () => {
    expect(resolveSystemSub("users")).toBe("users");
    expect(resolveSystemSub("events")).toBe("events");
    expect(resolveSystemSub("health")).toBe("health");
  });

  it("remaps legacy sub ids to canonical", () => {
    expect(resolveSystemSub("client_domain")).toBe("events");
    expect(resolveSystemSub("runtime")).toBe("health");
  });

  it("falls back to users for unknown ids", () => {
    expect(resolveSystemSub("garbage")).toBe("users");
    expect(resolveSystemSub("scoring")).toBe("users"); // unrelated retired id
  });

  it("system alias map matches the documented set", () => {
    expect(Object.keys(SYSTEM_SUB_ALIASES).sort()).toEqual([
      "client_domain",
      "runtime",
    ]);
  });
});
