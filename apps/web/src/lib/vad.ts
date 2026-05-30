/**
 * Voice-activity detection (VAD) — pure dB-energy state machine.
 *
 * Why this exists (Phase 2, 2026-05-30): barge-in (the manager talking over
 * the AI) must work in *every* browser, not just Chrome. Chrome gives us the
 * Web Speech API, which bundles its own VAD + transcription. Safari / Firefox /
 * Brave don't expose it, so the call page previously fell back to push-to-talk
 * — you had to hold a button, which means no real barge-in.
 *
 * The key insight: **barge-in is a voice-activity event, not a transcription
 * event.** To know the manager interrupted you only need "is someone speaking
 * right now", not *what* they said. That we can compute client-side, for free,
 * in any browser, from the audio energy the mic analyser already produces — no
 * paid streaming-STT round-trip. The actual transcript still comes from the
 * existing MediaRecorder → backend-Whisper (`audio.end`) path afterwards.
 *
 * This module is the latency-critical decision core, kept pure (no DOM, no
 * audio APIs) so it can be unit-tested deterministically by feeding a sequence
 * of (dB, timestamp) samples. The hook (`useMicrophone`) owns the AnalyserNode
 * and feeds dB into `vadStep` each animation frame.
 *
 * dB scale: matches `useMicrophone.computeAudioLevel`, i.e. `20*log10(rms)`
 * with rms in (0,1], so values are negative. Silence sits around −50…−60 dB,
 * speech around −30…−20 dB. The default onset threshold (−38 dB) sits just
 * above the existing noise gate (−35 dB) so room tone never trips it.
 */

export interface VadConfig {
  /** dB at/above which a sample counts as "energy present" (speech-ish). */
  onsetThresholdDb: number;
  /**
   * Sustained energy for at least this long ⇒ declare speech onset. Guards
   * against single-frame spikes (a click, a chair creak) firing a false
   * barge-in. Short enough that the interrupt still feels instant.
   */
  onsetMs: number;
  /**
   * Silence (energy below threshold) for at least this long ⇒ declare the
   * utterance ended. This is the gap we treat as "they stopped talking" so we
   * can cut the recording and ship it to Whisper. Too short → we chop mid
   * sentence on natural pauses; too long → laggy reply.
   */
  hangoverMs: number;
}

/**
 * Defaults tuned for Russian conversational speech on a typical laptop mic.
 * onset −38 dB / 120 ms: fires within ~2 animation frames of real speech but
 * ignores transients. hangover 700 ms: rides over inter-word pauses, cuts on a
 * genuine end-of-turn silence.
 */
export const DEFAULT_VAD_CONFIG: VadConfig = {
  onsetThresholdDb: -38,
  onsetMs: 120,
  hangoverMs: 700,
};

export type VadPhase = "silence" | "speech";

export interface VadState {
  phase: VadPhase;
  /**
   * Timestamp (ms) at which the current run of above-threshold samples began,
   * or null while below threshold. Used to measure the onset hold.
   */
  aboveSinceTs: number | null;
  /** Timestamp (ms) of the most recent above-threshold sample. Drives hangover. */
  lastAboveTs: number;
}

/** Edge emitted by a single VAD step, or null when phase is unchanged. */
export type VadEvent = "onset" | "end" | null;

export interface VadStepResult {
  next: VadState;
  event: VadEvent;
}

/** Fresh machine in the silence phase. */
export function vadInit(): VadState {
  return { phase: "silence", aboveSinceTs: null, lastAboveTs: 0 };
}

/**
 * Advance the VAD machine by one sample.
 *
 * Pure: same (state, db, now, cfg) always yields the same result. Feed it the
 * analyser dB every frame; act on the returned `event`:
 *   - "onset": speech just started (→ fire barge-in, begin recording)
 *   - "end":   speech just ended after the hangover (→ stop + ship recording)
 *   - null:    no transition
 *
 * @param s   previous state (start from `vadInit()`)
 * @param db  current energy in dB (negative; see module docstring)
 * @param now monotonic timestamp in ms (e.g. performance.now())
 * @param cfg thresholds (defaults in DEFAULT_VAD_CONFIG)
 */
export function vadStep(
  s: VadState,
  db: number,
  now: number,
  cfg: VadConfig = DEFAULT_VAD_CONFIG,
): VadStepResult {
  const above = db >= cfg.onsetThresholdDb;

  if (above) {
    const aboveSinceTs = s.aboveSinceTs ?? now;
    const heldFor = now - aboveSinceTs;
    // Onset only from silence, and only once energy has been sustained long
    // enough to be speech rather than a transient.
    if (s.phase === "silence" && heldFor >= cfg.onsetMs) {
      return {
        next: { phase: "speech", aboveSinceTs, lastAboveTs: now },
        event: "onset",
      };
    }
    return {
      next: { phase: s.phase, aboveSinceTs, lastAboveTs: now },
      event: null,
    };
  }

  // Below threshold: any onset progress is discarded (a lone spike can't
  // accumulate into an onset across a silent gap).
  if (s.phase === "speech") {
    const silentFor = now - s.lastAboveTs;
    if (silentFor >= cfg.hangoverMs) {
      return {
        next: { phase: "silence", aboveSinceTs: null, lastAboveTs: s.lastAboveTs },
        event: "end",
      };
    }
  }
  return {
    next: { phase: s.phase, aboveSinceTs: null, lastAboveTs: s.lastAboveTs },
    event: null,
  };
}
