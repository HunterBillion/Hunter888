/**
 * VAD state-machine contract (Phase 2 — cross-browser barge-in).
 *
 * These pin the latency-critical decision core that lets the manager interrupt
 * the AI in Safari/Firefox/Brave (no Web Speech API there). The machine turns a
 * stream of mic-energy (dB) samples into "speech started" / "speech ended"
 * edges. Getting the edges right is what makes barge-in feel instant without
 * false-firing on coughs, clicks, or natural pauses.
 *
 * We drive it the same way the hook does: feed (dB, timestamp) samples in
 * order and assert the emitted events.
 */
import { describe, expect, it } from "vitest";

import {
  DEFAULT_VAD_CONFIG,
  vadInit,
  vadStep,
  type VadConfig,
  type VadEvent,
  type VadState,
} from "@/lib/vad";

const CFG: VadConfig = DEFAULT_VAD_CONFIG;
const LOUD = CFG.onsetThresholdDb + 8; // comfortably above threshold (speech)
const QUIET = CFG.onsetThresholdDb - 12; // comfortably below (room tone)

/** Run a [db, now] script through the machine, collecting emitted events. */
function run(
  samples: Array<[db: number, now: number]>,
  cfg: VadConfig = CFG,
): { events: VadEvent[]; state: VadState } {
  let state = vadInit();
  const events: VadEvent[] = [];
  for (const [db, now] of samples) {
    const { next, event } = vadStep(state, db, now, cfg);
    state = next;
    if (event) events.push(event);
  }
  return { events, state };
}

describe("vadStep — onset", () => {
  it("fires onset only after energy is sustained for onsetMs", () => {
    // Loud from t=0; onset should land at the first sample where the hold
    // (now - aboveSinceTs) >= onsetMs, not before.
    const { events } = run([
      [LOUD, 0], // aboveSince=0, held 0ms → no onset
      [LOUD, 60], // held 60ms (<120) → no onset
      [LOUD, 130], // held 130ms (>=120) → ONSET
      [LOUD, 200], // already speech → no second onset
    ]);
    expect(events).toEqual(["onset"]);
  });

  it("does NOT fire on a single loud spike followed by silence (cough/click)", () => {
    const { events, state } = run([
      [LOUD, 0], // spike begins
      [QUIET, 40], // gone before onsetMs → onset progress discarded
      [QUIET, 200],
      [QUIET, 1000],
    ]);
    expect(events).toEqual([]);
    expect(state.phase).toBe("silence");
  });

  it("requires a fresh sustained run after a spike — spikes don't accumulate", () => {
    const { events } = run([
      [LOUD, 0],
      [QUIET, 50], // resets aboveSince
      [LOUD, 100], // aboveSince=100
      [LOUD, 150], // held 50ms (<120)
      [LOUD, 230], // held 130ms (>=120) → ONSET
    ]);
    expect(events).toEqual(["onset"]);
  });

  it("onsetMs=0 fires immediately on the first loud sample", () => {
    const { events } = run([[LOUD, 0]], { ...CFG, onsetMs: 0 });
    expect(events).toEqual(["onset"]);
  });
});

describe("vadStep — end / hangover", () => {
  it("fires end only after silence persists for hangoverMs", () => {
    const { events } = run([
      [LOUD, 0],
      [LOUD, 130], // ONSET
      [QUIET, 200], // silent 70ms since lastAbove(130)
      [QUIET, 700], // silent 570ms (<700)
      [QUIET, 850], // silent 720ms (>=700) → END
    ]);
    expect(events).toEqual(["onset", "end"]);
  });

  it("rides over a short mid-utterance pause without ending", () => {
    const { events, state } = run([
      [LOUD, 0],
      [LOUD, 130], // ONSET
      [QUIET, 300], // brief pause (170ms < hangover)
      [LOUD, 500], // speech resumes, lastAbove=500
      [QUIET, 700], // 200ms since 500
      [LOUD, 900], // resumes again
      [QUIET, 1100],
    ]);
    expect(events).toEqual(["onset"]); // never ended
    expect(state.phase).toBe("speech");
  });

  it("a full utterance produces exactly one onset then one end", () => {
    const samples: Array<[number, number]> = [];
    // 1s of speech sampled every 50ms
    for (let t = 0; t <= 1000; t += 50) samples.push([LOUD, t]);
    // then 900ms of silence
    for (let t = 1050; t <= 1950; t += 50) samples.push([QUIET, t]);
    const { events, state } = run(samples);
    expect(events).toEqual(["onset", "end"]);
    expect(state.phase).toBe("silence");
  });

  it("can detect a second utterance after the first ends", () => {
    const samples: Array<[number, number]> = [
      [LOUD, 0],
      [LOUD, 130], // onset 1
      [QUIET, 200],
      [QUIET, 900], // end 1 (silent 700 since 130)
      [LOUD, 1000],
      [LOUD, 1130], // onset 2
      [QUIET, 1200],
      [QUIET, 1900], // end 2
    ];
    const { events } = run(samples);
    expect(events).toEqual(["onset", "end", "onset", "end"]);
  });
});

describe("vadStep — purity", () => {
  it("does not mutate the input state", () => {
    const s = vadInit();
    const frozen = Object.freeze({ ...s });
    expect(() => vadStep(frozen, LOUD, 0, CFG)).not.toThrow();
    // original object untouched
    expect(s).toEqual(vadInit());
  });
});
