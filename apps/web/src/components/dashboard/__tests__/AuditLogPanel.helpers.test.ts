/**
 * Regression tests for AuditLogPanel helpers.
 *
 * Covers two production bugs that landed silently before this PR:
 *
 *   1. Russian pluralization. The previous `total < 5 ? "записи" : "записей"`
 *      ladder mislabels every count in {11..14, 21..24, 111..114, ...}.
 *   2. Local-date boundary for `<input type="date">`. The previous
 *      `new Date(s).toISOString()` produced UTC midnight, dropping the
 *      first 3 hours of the user-selected day in MSK.
 */
import { describe, it, expect } from "vitest";
import { pluralizeEntries, localDateBoundary } from "../AuditLogPanel";

describe("pluralizeEntries", () => {
  it("uses singular for n%10===1, except 11", () => {
    expect(pluralizeEntries(1)).toBe("запись");
    expect(pluralizeEntries(21)).toBe("запись");
    expect(pluralizeEntries(101)).toBe("запись");
    expect(pluralizeEntries(11)).toBe("записей");
  });

  it("uses 'записи' for n%10 in 2..4, except teens", () => {
    expect(pluralizeEntries(2)).toBe("записи");
    expect(pluralizeEntries(3)).toBe("записи");
    expect(pluralizeEntries(4)).toBe("записи");
    expect(pluralizeEntries(22)).toBe("записи");
    expect(pluralizeEntries(24)).toBe("записи");
    expect(pluralizeEntries(102)).toBe("записи");
    // teens still take 'записей'
    expect(pluralizeEntries(12)).toBe("записей");
    expect(pluralizeEntries(13)).toBe("записей");
    expect(pluralizeEntries(14)).toBe("записей");
  });

  it("uses 'записей' for 0, 5..20, and >24 mod ladder", () => {
    expect(pluralizeEntries(0)).toBe("записей");
    expect(pluralizeEntries(5)).toBe("записей");
    expect(pluralizeEntries(10)).toBe("записей");
    expect(pluralizeEntries(15)).toBe("записей");
    expect(pluralizeEntries(20)).toBe("записей");
    expect(pluralizeEntries(25)).toBe("записей");
    expect(pluralizeEntries(100)).toBe("записей");
  });
});

describe("localDateBoundary", () => {
  it("returns the local-day start as ISO for mode='start'", () => {
    const iso = localDateBoundary("2026-05-05", "start");
    const d = new Date(iso);
    expect(d.getFullYear()).toBe(2026);
    expect(d.getMonth()).toBe(4); // May → 4
    expect(d.getDate()).toBe(5);
    expect(d.getHours()).toBe(0);
    expect(d.getMinutes()).toBe(0);
  });

  it("returns the local-day end as ISO for mode='end'", () => {
    const iso = localDateBoundary("2026-05-05", "end");
    const d = new Date(iso);
    expect(d.getFullYear()).toBe(2026);
    expect(d.getMonth()).toBe(4);
    expect(d.getDate()).toBe(5);
    expect(d.getHours()).toBe(23);
    expect(d.getMinutes()).toBe(59);
    expect(d.getSeconds()).toBe(59);
  });

  it("does not throw on malformed input — returns the input verbatim", () => {
    // `<input type="date">` is gated upstream so this branch should never
    // be hit, but it must not throw if it ever does.
    expect(() => localDateBoundary("garbage", "start")).not.toThrow();
    expect(localDateBoundary("garbage", "start")).toBe("garbage");
  });
});
