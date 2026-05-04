/**
 * Hang-up coordinator — encapsulates the post-hangup race-safety dance
 * that lives in the training page.
 *
 * Three independent code paths in `apps/web/src/app/training/[id]/page.tsx`
 * fire `session.end` and want to navigate to `/results/<sid>`:
 *
 *   1. user clicks the bottom-bar "Завершить" button   → `handleEnd`
 *   2. user clicks "К результатам" in the HangupModal  → modal `onResults`
 *   3. backend emits `client.hangup` and 3s later we auto-finalise
 *
 * Without coordination two of them collide on every hangup:
 *   - backend logs `error: session_completed` for the second send,
 *   - the apparent latency of the redirect drifts by 10–60s (the second
 *     send confuses the WS round-trip timing).
 *
 * This module owns the dedupe ref + the 5s safety-net redirect timer
 * and exposes the four primitives the page calls in:
 *   - `markEndSent()`      — returns true ⇒ caller should send; false ⇒ skip
 *   - `armFallback(...)`   — schedule the 5s redirect (idempotent)
 *   - `cancelFallback(...)` — success path (session.ended arrived)
 *   - `resetForNewSession()` — story-mode multi-call: clear the slate
 *
 * Pure module. No React, no DOM. The page wires it through useRef so it
 * survives renders. The test file exercises this module directly.
 *
 * 2026-05-04 (PR #226 v2 — extracted to be testable in isolation).
 */

export interface HangupCoordinatorState {
  endSent: boolean;
  fallbackTimer: ReturnType<typeof setTimeout> | null;
}

export const HANGUP_FALLBACK_MS = 5000;

export const createHangupCoordinatorState = (): HangupCoordinatorState => ({
  endSent: false,
  fallbackTimer: null,
});

/**
 * Mark that we are about to send `session.end`. Returns true on first
 * call, false on every subsequent call. The caller uses the return
 * value to decide whether to actually call `sendMessage`.
 *
 *   if (markEndSent(state)) sendMessage({ type: "session.end", data: {} });
 */
export const markEndSent = (state: HangupCoordinatorState): boolean => {
  if (state.endSent) return false;
  state.endSent = true;
  return true;
};

export interface ArmFallbackOptions {
  /** Session id to navigate to (`/results/<sid>`). */
  sessionId: string;
  /** Called after HANGUP_FALLBACK_MS if `cancelFallback` was not called. */
  onFire: (sessionId: string) => void;
  /** Optional override (tests pass a custom delay). Defaults to HANGUP_FALLBACK_MS. */
  delayMs?: number;
  /** Optional logger override. Defaults to console.warn. */
  logFire?: (payload: { sessionId: string; ms: number }) => void;
}

/**
 * Schedule the 5s safety-net redirect. Idempotent — calling twice
 * just resets the timer.
 */
export const armFallback = (
  state: HangupCoordinatorState,
  opts: ArmFallbackOptions,
): void => {
  if (state.fallbackTimer) clearTimeout(state.fallbackTimer);
  const delay = opts.delayMs ?? HANGUP_FALLBACK_MS;
  state.fallbackTimer = setTimeout(() => {
    state.fallbackTimer = null;
    // Telemetry — fired = session.ended did NOT arrive in time. We
    // dashboard this rate; non-zero means a backend regression.
    const log =
      opts.logFire ??
      ((payload) => {
        // eslint-disable-next-line no-console
        console.warn("[hangup] fallback fired", payload);
      });
    log({ sessionId: opts.sessionId, ms: delay });
    opts.onFire(opts.sessionId);
  }, delay);
};

export interface CancelFallbackOptions {
  /** Session id (only used for telemetry). */
  sessionId?: string;
  /** Why we're cancelling. "ack" emits an info log; "unmount" stays silent. */
  reason: "ack" | "unmount";
  /** Optional logger override. Defaults to console.info. */
  logCancel?: (payload: { sessionId: string }) => void;
}

/**
 * Cancel the pending fallback timer. Called by:
 *   - the `session.ended` WS handler (success path) with reason="ack",
 *   - the unmount cleanup with reason="unmount" (silent).
 */
export const cancelFallback = (
  state: HangupCoordinatorState,
  opts: CancelFallbackOptions,
): void => {
  if (!state.fallbackTimer) return;
  clearTimeout(state.fallbackTimer);
  state.fallbackTimer = null;
  if (opts.reason === "ack") {
    const log =
      opts.logCancel ??
      ((payload) => {
        // eslint-disable-next-line no-console
        console.info("[hangup] fallback cancelled (ack arrived)", payload);
      });
    log({ sessionId: opts.sessionId ?? "" });
  }
};

/**
 * Reset the dedupe slate for a new session. Called from:
 *   - `session.started` handler (story-mode call N+1),
 *   - `session.resumed` handler,
 *   - the routeId-change effect (belt-and-suspenders).
 *
 * Story-mode reuses the same component instance across multiple
 * back-to-back calls. Without this reset, `endSent` stays true forever
 * after the first hangup and call N+1 silently drops `session.end`.
 */
export const resetForNewSession = (state: HangupCoordinatorState): void => {
  state.endSent = false;
  if (state.fallbackTimer) {
    clearTimeout(state.fallbackTimer);
    state.fallbackTimer = null;
  }
};
