"use client";

import { useCallback, useEffect, useRef } from "react";

type SoundName = "success" | "epic" | "legendary" | "fail" | "levelup";

const SOUND_PATHS: Record<SoundName, string> = {
  success: "/sounds/success.mp3",
  epic: "/sounds/epic.mp3",
  legendary: "/sounds/legendary.mp3",
  fail: "/sounds/fail.mp3",
  levelup: "/sounds/levelup.mp3",
};

/**
 * Thin wrapper over Web Audio API for game sound effects.
 * Respects user mute preference (localStorage "vh-sounds-muted").
 *
 * Usage:
 * ```ts
 * const { playSound } = useSound();
 * playSound("success");
 * ```
 */
export function useSound() {
  const ctxRef = useRef<AudioContext | null>(null);
  const cacheRef = useRef<Map<string, AudioBuffer>>(new Map());

  const getContext = useCallback(() => {
    if (!ctxRef.current || ctxRef.current.state === "closed") {
      ctxRef.current = new AudioContext();
    }
    return ctxRef.current;
  }, []);

  // Cleanup: close AudioContext on unmount to prevent resource leak
  useEffect(() => {
    return () => {
      if (ctxRef.current && ctxRef.current.state !== "closed") {
        ctxRef.current.close().catch(() => {});
        ctxRef.current = null;
      }
      cacheRef.current.clear();
    };
  }, []);

  const playSound = useCallback(async (name: SoundName, volume = 0.5) => {
    // Check mute
    try {
      if (localStorage.getItem("vh-sounds-muted") === "1") return;
    } catch { /* localStorage may throw in private browsing */ }

    const path = SOUND_PATHS[name];
    if (!path) return;

    try {
      const ctx = getContext();

      // Resume if suspended (browser autoplay policy)
      if (ctx.state === "suspended") {
        await ctx.resume();
      }

      let buffer = cacheRef.current.get(name);

      if (!buffer) {
        const response = await fetch(path);
        const arrayBuffer = await response.arrayBuffer();
        buffer = await ctx.decodeAudioData(arrayBuffer);
        cacheRef.current.set(name, buffer);
      }

      const source = ctx.createBufferSource();
      const gain = ctx.createGain();
      source.buffer = buffer;
      gain.gain.value = volume;
      source.connect(gain).connect(ctx.destination);
      source.start();
    } catch {
      // Audio not available — silent fail
    }
  }, [getContext]);

  const setMuted = useCallback((muted: boolean) => {
    try {
      localStorage.setItem("vh-sounds-muted", muted ? "1" : "0");
    } catch { /* localStorage may throw in private browsing */ }
  }, []);

  const isMuted = useCallback(() => {
    try {
      return localStorage.getItem("vh-sounds-muted") === "1";
    } catch {
      return false;
    }
  }, []);

  return { playSound, setMuted, isMuted };
}
