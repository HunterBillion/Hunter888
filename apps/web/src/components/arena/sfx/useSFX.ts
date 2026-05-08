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
import { getEffectiveVolume } from "@/hooks/useSound";

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
// 2026-05-03: bridge с глобальным mute из useSound.ts (Phase 8 sound engine).
// Settings UI пишет в эти ключи; useSFX (legacy движок для tick/heartbeat) ДО
// этой правки их игнорировал — пользователь жал «Mute» в /settings, а tick
// всё равно играл. Теперь читаем ВСЕ три ключа: если ХОТЬ ОДИН говорит muted
// — звук не играет.
const GLOBAL_MUTE_KEYS = ["vh-sounds-muted", "vh_sound", STORAGE_KEY] as const;

// 2026-05-08: per-sound base volume (нормализация громкости между файлами,
// чтобы tick не оглушал, а correct звучал заметно). Финальная громкость
// перевычисляется на каждом play(): master × sfx × baseVolume.
const BASE_VOLUMES: Record<SFXName, number> = {
  correct: 0.85,
  wrong: 0.85,
  round_start: 0.9,
  round_end: 0.9,
  tick: 0.5,
  hint: 0.7,
};

// Module-scoped audio cache — shared across all useSFX() callers.
const cache: Partial<Record<SFXName, HTMLAudioElement>> = {};

function getOrCreate(name: SFXName): HTMLAudioElement | null {
  if (typeof window === "undefined") return null;
  if (cache[name]) return cache[name] as HTMLAudioElement;
  const el = new Audio(SFX_URLS[name]);
  el.preload = "auto";
  // Initial volume — overwritten on every play() with the live
  // master × sfx × base computation.
  el.volume = BASE_VOLUMES[name];
  cache[name] = el;
  return el;
}

function readMuted(): boolean {
  if (typeof window === "undefined") return false;
  // 2026-05-03: читаем ВСЕ глобальные mute-ключи. Если любой выставлен — mute.
  // Также — если master volume == 0 в localStorage, считаем что муто.
  for (const key of GLOBAL_MUTE_KEYS) {
    const v = window.localStorage.getItem(key);
    if (v === "1" || v === "off") return true;
  }
  const master = window.localStorage.getItem("vh-vol-master");
  if (master !== null && Number(master) === 0) return true;
  return false;
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
        // 2026-05-08: расчитываем громкость на каждом play() — пользователь
        // мог сдвинуть слайдер «Master» или «Эффекты» в /settings прямо
        // во время матча. До этой правки громкость была захардкожена
        // (0.5 / 0.8) и слайдеры на неё не действовали.
        el.volume = getEffectiveVolume("sfx", BASE_VOLUMES[name]);
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
    el.volume = getEffectiveVolume("sfx", BASE_VOLUMES[name]);
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
