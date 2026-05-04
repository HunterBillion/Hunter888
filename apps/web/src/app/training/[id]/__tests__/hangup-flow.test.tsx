/**
 * Hangup-flow regression tests for PR #226 v2.
 *
 * What we're protecting:
 *   1. The dedupe ref blocks a second `session.end` send. Three code
 *      paths fire it (handleEnd / C3 auto-fire / HangupModal click);
 *      without dedupe two collide and the backend logs
 *      `error: session_completed`, drifting the redirect by 10–60s.
 *   2. The 5s `armFallback` timeout fires `router.replace("/results/<sid>")`
 *      so the user is never stuck if `session.ended` is delayed/dropped.
 *   3. An arriving `session.ended` cancels the pending fallback — no
 *      double-navigation.
 *   4. `resetForNewSession` lets story-mode call N+1 actually send
 *      `session.end` (otherwise the dedupe stays sticky forever).
 *
 * Why we test the coordinator and not the page component:
 *   The training page boots WS, audio, dynamic imports, framer-motion,
 *   Zustand store, viewport-dependent components. A full mount is slow
 *   and brittle. The race-safety logic was extracted into the pure
 *   `@/lib/hangupCoordinator` module precisely so it can be exercised
 *   in isolation. The page is a thin wrapper around these primitives —
 *   if the coordinator is correct AND the page calls the four wrappers
 *   in the right places (verified by grep + tsc), the contract holds.
 *
 * Pre-fix behaviour these tests would catch:
 *   - test "second send is blocked": pre-fix, both calls returned true
 *     and the page would have sent `session.end` twice → test fails.
 *   - test "fallback fires after 5s": pre-fix, no fallback existed at
 *     all → test fails.
 *   - test "ack cancels fallback": pre-fix, ack-handler had no cancel
 *     hook → test fails.
 *   - test "reset re-arms a new session": pre-fix, the dedupe ref was
 *     never reset → second markEndSent returned false → test fails.
 *
 * Per CLAUDE.md §4.6 each test pins a real symptom that paid time in
 * production (PR #226 critic findings #1, #2, #3, #4, #5, #7).
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import {
  createHangupCoordinatorState,
  markEndSent,
  armFallback,
  cancelFallback,
  resetForNewSession,
  HANGUP_FALLBACK_MS,
  type HangupCoordinatorState,
} from "@/lib/hangupCoordinator";

describe("hangupCoordinator (PR #226 v2 race-safety)", () => {
  let state: HangupCoordinatorState;

  beforeEach(() => {
    state = createHangupCoordinatorState();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
  });

  // ─── #1 dedupe ──────────────────────────────────────────────────────

  it("markEndSent returns true on first call, false on every subsequent call", () => {
    expect(markEndSent(state)).toBe(true);
    expect(markEndSent(state)).toBe(false);
    expect(markEndSent(state)).toBe(false);
  });

  it("dedupe survives across the three caller paths (button + auto-fire + modal)", () => {
    // Simulate handleEnd button click.
    const sendButton = markEndSent(state);
    // 3s later C3 auto-fire would run.
    const sendAutoFire = markEndSent(state);
    // User then clicks "К результатам" too.
    const sendModal = markEndSent(state);

    expect(sendButton).toBe(true);   // we DO send on the button.
    expect(sendAutoFire).toBe(false); // auto-fire MUST NOT collide.
    expect(sendModal).toBe(false);    // modal MUST NOT collide.
  });

  // ─── #2 armFallback fires when nothing else does ────────────────────

  it("armFallback fires onFire after HANGUP_FALLBACK_MS when not cancelled", () => {
    const onFire = vi.fn();
    const logFire = vi.fn();
    armFallback(state, { sessionId: "sess-A", onFire, logFire });

    // Just before the deadline — must NOT have fired yet.
    vi.advanceTimersByTime(HANGUP_FALLBACK_MS - 1);
    expect(onFire).not.toHaveBeenCalled();

    // At the deadline — fires exactly once.
    vi.advanceTimersByTime(1);
    expect(onFire).toHaveBeenCalledTimes(1);
    expect(onFire).toHaveBeenCalledWith("sess-A");

    // Telemetry payload — dashboard reads sessionId + ms.
    expect(logFire).toHaveBeenCalledWith({
      sessionId: "sess-A",
      ms: HANGUP_FALLBACK_MS,
    });
  });

  it("armFallback respects custom delayMs (used by tests; defaults to 5s in prod)", () => {
    const onFire = vi.fn();
    armFallback(state, { sessionId: "sess-B", onFire, delayMs: 100 });
    vi.advanceTimersByTime(99);
    expect(onFire).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(onFire).toHaveBeenCalledTimes(1);
  });

  it("re-arming armFallback resets the timer (idempotent, no double-fire)", () => {
    const onFire = vi.fn();
    armFallback(state, { sessionId: "sess-C", onFire });
    vi.advanceTimersByTime(3000);
    // Re-arm — the original 5s window is discarded, a new 5s starts.
    armFallback(state, { sessionId: "sess-C", onFire });
    vi.advanceTimersByTime(3000);
    // Total elapsed = 6000ms but only 3000ms since the latest arm —
    // must NOT have fired yet.
    expect(onFire).not.toHaveBeenCalled();
    vi.advanceTimersByTime(2000);
    // Now 5000ms since the latest arm → fires.
    expect(onFire).toHaveBeenCalledTimes(1);
  });

  // ─── #3 ack cancels fallback ────────────────────────────────────────

  it("an arriving session.ended (cancelFallback ack) cancels the pending fallback", () => {
    const onFire = vi.fn();
    const logCancel = vi.fn();
    armFallback(state, { sessionId: "sess-D", onFire });

    // 2s later session.ended arrives — page calls cancelFallback("ack").
    vi.advanceTimersByTime(2000);
    cancelFallback(state, { reason: "ack", sessionId: "sess-D", logCancel });

    // Run out the rest of the budget — fallback must NOT fire.
    vi.advanceTimersByTime(HANGUP_FALLBACK_MS);
    expect(onFire).not.toHaveBeenCalled();
    // Telemetry — dashboard's denominator for fire-rate.
    expect(logCancel).toHaveBeenCalledWith({ sessionId: "sess-D" });
  });

  it("cancelFallback with reason=unmount stays silent (no log on normal page exit)", () => {
    const onFire = vi.fn();
    const logCancel = vi.fn();
    armFallback(state, { sessionId: "sess-E", onFire });
    cancelFallback(state, { reason: "unmount", logCancel });
    expect(logCancel).not.toHaveBeenCalled();
    vi.advanceTimersByTime(HANGUP_FALLBACK_MS);
    expect(onFire).not.toHaveBeenCalled();
  });

  it("cancelFallback is a safe no-op when no timer is armed", () => {
    const logCancel = vi.fn();
    expect(() =>
      cancelFallback(state, { reason: "ack", sessionId: "sess-F", logCancel }),
    ).not.toThrow();
    expect(logCancel).not.toHaveBeenCalled();
  });

  // ─── #4 story-mode reset ────────────────────────────────────────────

  it("resetForNewSession lets call N+1 send session.end (story-mode regression)", () => {
    // Call 1 — fires, dedupe locks.
    expect(markEndSent(state)).toBe(true);
    expect(markEndSent(state)).toBe(false);

    // Backend opens call 2 (session.started). Page calls
    // resetForNewSession.
    resetForNewSession(state);

    // Call 2's hangup should be allowed to fire session.end.
    expect(markEndSent(state)).toBe(true);
    expect(markEndSent(state)).toBe(false);
  });

  it("resetForNewSession also clears any in-flight fallback timer", () => {
    const onFire = vi.fn();
    armFallback(state, { sessionId: "sess-G-call1", onFire });

    // Mid-flight, a new session starts (story mode call N+1).
    vi.advanceTimersByTime(2000);
    resetForNewSession(state);

    // The old call's fallback must NOT fire (would navigate to the
    // wrong session id).
    vi.advanceTimersByTime(HANGUP_FALLBACK_MS);
    expect(onFire).not.toHaveBeenCalled();
  });

  // ─── End-to-end happy-path scenario ─────────────────────────────────

  it("end-to-end: hangup → arm → ack → no fire, no double-send", () => {
    const onFire = vi.fn();
    const logFire = vi.fn();
    const logCancel = vi.fn();

    // 1. handleEnd fires.
    const ok1 = markEndSent(state);
    expect(ok1).toBe(true);
    armFallback(state, { sessionId: "sess-H", onFire, logFire });

    // 2. 3s later, C3 auto-fire would run — must be blocked.
    vi.advanceTimersByTime(3000);
    const ok2 = markEndSent(state);
    expect(ok2).toBe(false);

    // 3. Backend ack arrives at 3.5s.
    vi.advanceTimersByTime(500);
    cancelFallback(state, {
      reason: "ack",
      sessionId: "sess-H",
      logCancel,
    });

    // 4. Run out the rest of forever — nothing else fires.
    vi.advanceTimersByTime(60_000);
    expect(onFire).not.toHaveBeenCalled();
    expect(logFire).not.toHaveBeenCalled();
    expect(logCancel).toHaveBeenCalledTimes(1);
  });

  // ─── End-to-end fallback-fires scenario ─────────────────────────────

  it("end-to-end: hangup → arm → no ack → fallback fires + telemetry warn", () => {
    const onFire = vi.fn();
    const logFire = vi.fn();

    markEndSent(state);
    armFallback(state, { sessionId: "sess-I", onFire, logFire });

    // session.ended NEVER arrives (WS drop / backend hang).
    vi.advanceTimersByTime(HANGUP_FALLBACK_MS);

    expect(onFire).toHaveBeenCalledTimes(1);
    expect(onFire).toHaveBeenCalledWith("sess-I");
    expect(logFire).toHaveBeenCalledTimes(1);
    expect(logFire).toHaveBeenCalledWith({
      sessionId: "sess-I",
      ms: HANGUP_FALLBACK_MS,
    });
  });
});
