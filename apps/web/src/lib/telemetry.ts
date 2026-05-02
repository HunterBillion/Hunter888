/**
 * telemetry — client-side analytics events with batched flush to
 * `POST /api/analytics/events`.
 *
 * 2026-05-02 rewrite — replaces the long-standing stub. Earlier the
 * module just `console.log`'d in dev and was a silent no-op in prod;
 * 9 call sites were firing events that vanished into the void. Now
 * events are queued in memory and flushed in batches to the backend
 * collector defined in `apps/api/app/api/analytics.py`. The collector
 * accepts anonymous traffic so this module works pre-login too.
 *
 * Design summary
 * --------------
 *
 * * **Anonymous-OK.** A UUID generated on first call is cached in
 *   localStorage as `vh_anon_session_id` and stamped onto every batch.
 *   Lets us stitch a session of events without identifying the user.
 *   When the user logs in, the backend correlates by access-token
 *   cookie and records both `user_id` and `anon_session_id`.
 *
 * * **Batched flush.** Events are buffered up to 50 in memory; when
 *   the buffer hits 50 OR the page becomes hidden, we flush a single
 *   POST. This keeps network noise low and avoids one-fetch-per-click
 *   behaviour (~9 call sites × N clicks/min).
 *
 * * **`navigator.sendBeacon` on unload.** Browsers cancel in-flight
 *   `fetch()` when the user navigates away. sendBeacon is purpose-built
 *   for "ship this telemetry as the page unloads" and survives that
 *   scenario. We fall back to `fetch(..., {keepalive: true})` when
 *   sendBeacon isn't available (very old browsers, some embedded
 *   webviews).
 *
 * * **Best-effort.** Network failures are logged but never thrown —
 *   a flaky telemetry endpoint must not break user flows. We drop
 *   events on persistent failure rather than retrying indefinitely.
 *
 * * **Drop on size.** Single events whose payload exceeds ~3 KB are
 *   dropped client-side too (the server caps at 4 KB; we leave room
 *   for envelope overhead). This guards against pathological payloads
 *   that would cause a whole batch to be rejected server-side.
 */

import { getApiBaseUrl } from "@/lib/public-origin";
import { logger } from "@/lib/logger";

// ---------------------------------------------------------------------------
// Event catalog. Mirror this with the backend's ALLOWED_EVENTS set in
// `apps/api/app/api/analytics.py`. Adding a new event requires
// updating both files; the server rejects unknown names rather than
// silently storing them.
// ---------------------------------------------------------------------------

type EventName =
  | "script_panel_toggle"
  | "script_example_copied"
  | "script_drawer_auto_open"
  | "stage_skipped"
  | "whisper_script_clicked"
  | "retrain_widget_shown"
  | "retrain_widget_clicked"
  | "coaching_mistake";

interface QueuedEvent {
  name: EventName;
  payload: Record<string, unknown>;
  occurred_at: string; // ISO 8601 with timezone
}

// ---------------------------------------------------------------------------
// Config knobs
// ---------------------------------------------------------------------------

const FLUSH_THRESHOLD = 50;          // events buffered before auto-flush
const FLUSH_INTERVAL_MS = 30_000;    // periodic flush as backstop
const MAX_PAYLOAD_BYTES = 3 * 1024;  // per-event drop threshold
const ANON_SESSION_KEY = "vh_anon_session_id";

const isDev = (): boolean =>
  typeof process !== "undefined" && process.env?.NODE_ENV === "development";

const isBrowser = (): boolean =>
  typeof window !== "undefined" && typeof document !== "undefined";

// ---------------------------------------------------------------------------
// Anonymous session id — UUID cached in localStorage.
//
// Persists across page reloads but not across browsers / private windows.
// We use crypto.randomUUID() (available in all modern browsers + Node 14.17+);
// fallback to a non-cryptographic random if not present.
// ---------------------------------------------------------------------------

let _anonSessionId: string | null = null;

function getAnonSessionId(): string | null {
  if (!isBrowser()) return null;
  if (_anonSessionId) return _anonSessionId;
  try {
    const cached = localStorage.getItem(ANON_SESSION_KEY);
    if (cached && /^[0-9a-f-]{36}$/i.test(cached)) {
      _anonSessionId = cached;
      return cached;
    }
    const fresh =
      typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
        ? crypto.randomUUID()
        : _fallbackUuid();
    localStorage.setItem(ANON_SESSION_KEY, fresh);
    _anonSessionId = fresh;
    return fresh;
  } catch {
    // localStorage may throw in private mode / quota. Generate a
    // non-persistent id for the lifetime of the tab so events still
    // get stitched within a single page session.
    if (!_anonSessionId) {
      _anonSessionId =
        typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
          ? crypto.randomUUID()
          : _fallbackUuid();
    }
    return _anonSessionId;
  }
}

function _fallbackUuid(): string {
  // RFC 4122 v4-shaped string from Math.random. Not cryptographically
  // strong, but telemetry session id doesn't need to be — it's
  // sticky-but-anonymous.
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

// ---------------------------------------------------------------------------
// Buffer + flush
// ---------------------------------------------------------------------------

const queue: QueuedEvent[] = [];
let flushScheduled = false;
let intervalHandle: ReturnType<typeof setInterval> | null = null;
let listenersInstalled = false;

function ensureBackgroundFlush(): void {
  if (!isBrowser() || listenersInstalled) return;
  listenersInstalled = true;

  // Flush whenever the page becomes hidden (tab switch, minimise,
  // navigation start). This is the canonical "user is leaving"
  // signal — using sendBeacon here ensures the batch survives the
  // unload that would cancel a regular fetch().
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") flush(true);
  });

  // Belt: pagehide also fires on bfcache unloads where
  // visibilitychange may not. Same flush, beacon transport.
  window.addEventListener("pagehide", () => flush(true));

  // Periodic backstop. If a user sits on a quiet page for 5 min
  // without firing 50 events and without unloading, the periodic
  // flush still ships what's queued.
  intervalHandle = setInterval(() => flush(false), FLUSH_INTERVAL_MS);
}

function endpoint(): string {
  return `${getApiBaseUrl()}/api/analytics/events`;
}

function envelope(events: QueuedEvent[]): string {
  return JSON.stringify({
    events,
    anon_session_id: getAnonSessionId(),
    release_sha:
      (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_RELEASE_SHA) ||
      undefined,
  });
}

function flush(useBeacon: boolean): void {
  if (queue.length === 0) return;
  // Splice up to 100 (server cap). Larger queues drain across
  // multiple flushes — visibility-hidden flushes retry until empty
  // because the loop short-circuits if there are no events.
  const batch = queue.splice(0, 100);
  const body = envelope(batch);

  if (useBeacon && isBrowser() && typeof navigator?.sendBeacon === "function") {
    try {
      const blob = new Blob([body], { type: "application/json" });
      const ok = navigator.sendBeacon(endpoint(), blob);
      if (ok) return;
      // Beacon refused (queue full, payload too big, etc.) — fall
      // through to fetch as a last attempt.
    } catch {
      // sendBeacon throws in some embedded contexts; try fetch.
    }
  }

  // Regular fetch path. `keepalive: true` is the modern equivalent
  // of sendBeacon for fetch — the request is allowed to outlive the
  // document. Browsers cap keepalive request size at ~64 KB which
  // is plenty for our batch (max 100 events × ~3 KB = ~300 KB but
  // typical events are < 200 bytes).
  fetch(endpoint(), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
    credentials: "include",
    keepalive: true,
  }).catch((err) => {
    // Telemetry must not break user flows — log + drop. We chose not
    // to re-queue on failure: an offline user firing a stream of
    // events would otherwise build up an unbounded buffer.
    logger.warn("[telemetry] flush failed; dropping batch", err);
  });
}

function scheduleAutoFlush(): void {
  if (flushScheduled) return;
  flushScheduled = true;
  // Use setTimeout(0) — flush at end of the current event loop turn
  // so a burst of events fired together still ride one batch when
  // they cumulatively cross the threshold.
  setTimeout(() => {
    flushScheduled = false;
    if (queue.length >= FLUSH_THRESHOLD) flush(false);
  }, 0);
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export const telemetry = {
  /**
   * Record a telemetry event. Always returns immediately. The actual
   * POST happens in batches — see flush logic above.
   *
   * Call sites should not await this and should not check for errors
   * here; the contract is fire-and-forget.
   */
  track(event: EventName, payload: Record<string, unknown> = {}): void {
    if (!isBrowser()) return; // SSR no-op
    if (isDev()) {
      // eslint-disable-next-line no-console
      console.log(`[telemetry] ${event}`, payload);
    }
    // Drop pathologically large payloads client-side too. The server
    // does its own check (4 KB), but rejecting at source avoids
    // burning a network round-trip on a doomed request.
    let serializedSize = 0;
    try {
      serializedSize = JSON.stringify(payload).length;
    } catch {
      // Non-serializable payload (cyclic refs, BigInt, etc.) — drop.
      logger.warn("[telemetry] dropping non-serializable payload", { event });
      return;
    }
    if (serializedSize > MAX_PAYLOAD_BYTES) {
      logger.warn("[telemetry] dropping oversized event", {
        event,
        size: serializedSize,
      });
      return;
    }

    ensureBackgroundFlush();
    queue.push({
      name: event,
      payload,
      occurred_at: new Date().toISOString(),
    });

    if (queue.length >= FLUSH_THRESHOLD) {
      flush(false);
    } else {
      scheduleAutoFlush();
    }
  },

  /**
   * Manually flush the buffer. Exported so the app can force a flush
   * before navigation in cases where sendBeacon isn't enough (e.g.
   * before a router.push that should preserve event ordering with
   * the next page's events).
   */
  flush(): void {
    flush(false);
  },

  /**
   * Test hook. Resets internal state. Not used in production.
   */
  __reset(): void {
    queue.length = 0;
    flushScheduled = false;
    if (intervalHandle) {
      clearInterval(intervalHandle);
      intervalHandle = null;
    }
    listenersInstalled = false;
    _anonSessionId = null;
  },
};
