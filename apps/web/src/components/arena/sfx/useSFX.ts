"use client";

/**
 * useSFX — shared sound-effect hook for Arena (all 5 modes).
 *
 * Sprint 1 (2026-04-20). Wires a tiny WAV pack under /public/sfx/* into
 * React so components can fire a cue with one line:
 *
 *   const sfx = useSFX();
 *   sfx.play("correct");
 *
 * Design:
 *   - Global `<audio>` cache keyed by name. Lazy-created on first play.
 *   - Respects a single muted state stored in localStorage so the mute
 *     toggle persists between matches.
 *   - No user-gesture requirement for already-loaded pool; Arena pages
 *     call `sfx.prime()` on mount (user just clicked "Start match") which
 *     primes the browser audio permission.
 *   - Never throws — failed plays are swallowed (sound is UX glitter,
 *     not critical path).
 */

import { useCallback, useMemo } from "react";

export type SFXName =
  | "correct"
  | "wrong"
  | "round_start"
  | "round_end"
  | "tick"
  | "hint";

const SFX_URLS: Record<SFXName, string> = {
  correct: "/sfx/correct.wav",
  wrong: "/sfx/wrong.wav",
  round_start: "/sfx/round_start.wav",
  round_end: "/sfx/round_end.wav",
  tick: "/sfx/tick.wav",
  hint: "/sfx/hint.wav",
};

const STORAGE_KEY = "hunter888:sfx_muted";

// Module-scoped audio cache — shared across all useSFX() callers.
const cache: Partial<Record<SFXName, HTMLAudioElement>> = {};

function getOrCreate(name: SFXName): HTMLAudioElement | null {
  if (typeof window === "undefined") return null;
  if (cache[name]) return cache[name] as HTMLAudioElement;
  const el = new Audio(SFX_URLS[name]);
  el.preload = "auto";
  el.volume = name === "tick" ? 0.5 : 0.8;
  cache[name] = el;
  return el;
}

function readMuted(): boolean {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(STORAGE_KEY) === "1";
}

function writeMuted(muted: boolean) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, muted ? "1" : "0");
}

export interface SFXApi {
  play: (name: SFXName) => void;
  prime: () => void;
  mute: () => void;
  unmute: () => void;
  toggleMute: () => boolean;
  isMuted: () => boolean;
}

export function useSFX(): SFXApi {
  return useMemo(
    () => ({
      play(name: SFXName) {
        if (readMuted()) return;
        const el = getOrCreate(name);
        if (!el) return;
        try {
          el.currentTime = 0;
          const p = el.play();
          if (p && typeof p.catch === "function") p.catch(() => void 0);
        } catch {
          /* swallow */
        }
      },
      prime() {
        // Preload all sounds quietly — triggers the autoplay permission
        // token on browsers that require a user gesture first.
        Object.keys(SFX_URLS).forEach((k) => getOrCreate(k as SFXName));
      },
      mute() {
        writeMuted(true);
      },
      unmute() {
        writeMuted(false);
      },
      toggleMute() {
        const next = !readMuted();
        writeMuted(next);
        return next;
      },
      isMuted() {
        return readMuted();
      },
    }),
    [],
  );
}

// Convenience bare functions for non-hook call-sites (emit from store etc.)
export const sfx = {
  play(name: SFXName) {
    if (readMuted()) return;
    const el = getOrCreate(name);
    if (!el) return;
    try {
      el.currentTime = 0;
      const p = el.play();
      if (p && typeof p.catch === "function") p.catch(() => void 0);
    } catch {
      /* swallow */
    }
  },
  isMuted: readMuted,
};
