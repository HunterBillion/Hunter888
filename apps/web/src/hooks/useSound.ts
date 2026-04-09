"use client";

import { useCallback, useEffect, useRef } from "react";

type SoundName =
  | "success" | "epic" | "legendary" | "fail" | "levelup"
  // Arena sounds
  | "correct" | "incorrect" | "tick" | "challenge"
  | "match_start" | "victory" | "defeat" | "streak" | "rank_up"
  // PvP sounds
  | "pvpMatch" | "countdownTick"
  // Gamification sounds
  | "click" | "xp" | "levelUp" | "notification"
  // UI sounds
  | "hover";

export type { SoundName };

const SOUND_PATHS: Record<SoundName, string> = {
  success: "/sounds/success.mp3",
  epic: "/sounds/epic.mp3",
  legendary: "/sounds/legendary.mp3",
  fail: "/sounds/fail.mp3",
  levelup: "/sounds/levelup.mp3",
  // Arena
  correct: "/sounds/correct.mp3",
  incorrect: "/sounds/incorrect.mp3",
  tick: "/sounds/tick.mp3",
  challenge: "/sounds/challenge.mp3",
  match_start: "/sounds/match_start.mp3",
  victory: "/sounds/victory.mp3",
  defeat: "/sounds/defeat.mp3",
  streak: "/sounds/streak.mp3",
  rank_up: "/sounds/rank_up.mp3",
  // PvP
  pvpMatch: "",
  countdownTick: "",
  // Gamification
  click: "/sounds/click.mp3",
  xp: "/sounds/xp.mp3",
  levelUp: "/sounds/levelup.mp3",
  notification: "/sounds/notification.mp3",
  // UI
  hover: "",
};

// ─── Multi-layer procedural sound synthesis ──────────────────────────────────
// Each sound is a composition of multiple oscillator layers with envelopes,
// harmonics, noise, and effects to produce rich, game-quality audio.

interface OscLayer {
  freq: number;
  type: OscillatorType;
  gain: number;
  /** Frequency multiplier ramp over time (1.0 = no change) */
  freqRamp?: number;
  /** Delay before this layer starts (seconds) */
  delay?: number;
  /** Duration of this layer (seconds) */
  dur: number;
  /** Envelope: attack time in seconds */
  attack?: number;
  /** Envelope: decay position (0-1 of dur) where gain starts to fall */
  decayStart?: number;
}

interface SoundDesign {
  layers: OscLayer[];
  /** Add white noise burst (0-1 mix) */
  noiseMix?: number;
  noiseDur?: number;
  /** Total duration (for buffer size) */
  totalDur: number;
}

const SOUND_DESIGNS: Partial<Record<SoundName, SoundDesign>> = {
  // ── CORRECT: bright ascending double-chime ──
  correct: {
    totalDur: 0.35,
    layers: [
      { freq: 880, type: "sine", gain: 0.4, dur: 0.15, attack: 0.005 },
      { freq: 1320, type: "sine", gain: 0.3, dur: 0.2, delay: 0.08, attack: 0.005 },
      { freq: 1760, type: "sine", gain: 0.15, dur: 0.15, delay: 0.08 },
      // Shimmer harmonics
      { freq: 2640, type: "sine", gain: 0.08, dur: 0.12, delay: 0.1 },
    ],
  },

  // ── INCORRECT: descending buzzy tone ──
  incorrect: {
    totalDur: 0.4,
    layers: [
      { freq: 330, type: "square", gain: 0.2, dur: 0.35, freqRamp: 0.7 },
      { freq: 220, type: "sawtooth", gain: 0.15, dur: 0.3, delay: 0.05 },
      { freq: 165, type: "sine", gain: 0.2, dur: 0.25, delay: 0.1 },
    ],
    noiseMix: 0.05,
    noiseDur: 0.1,
  },

  // ── TICK: sharp metallic click ──
  tick: {
    totalDur: 0.08,
    layers: [
      { freq: 3000, type: "sine", gain: 0.3, dur: 0.02, attack: 0.001 },
      { freq: 6000, type: "sine", gain: 0.15, dur: 0.01, attack: 0.001 },
      { freq: 1500, type: "triangle", gain: 0.2, dur: 0.04 },
    ],
    noiseMix: 0.15,
    noiseDur: 0.02,
  },

  // ── CHALLENGE: dramatic alert fanfare ──
  challenge: {
    totalDur: 0.8,
    layers: [
      { freq: 440, type: "triangle", gain: 0.3, dur: 0.2, attack: 0.01 },
      { freq: 554, type: "triangle", gain: 0.3, dur: 0.2, delay: 0.15 },
      { freq: 659, type: "triangle", gain: 0.35, dur: 0.3, delay: 0.3 },
      // Sub bass
      { freq: 110, type: "sine", gain: 0.2, dur: 0.6, delay: 0.1 },
      // High shimmer
      { freq: 1318, type: "sine", gain: 0.1, dur: 0.4, delay: 0.3 },
    ],
  },

  // ── MATCH_START: epic countdown → GO burst ──
  match_start: {
    totalDur: 1.0,
    layers: [
      // Three countdown tones
      { freq: 440, type: "sine", gain: 0.25, dur: 0.12, attack: 0.005 },
      { freq: 440, type: "sine", gain: 0.25, dur: 0.12, delay: 0.2 },
      { freq: 440, type: "sine", gain: 0.25, dur: 0.12, delay: 0.4 },
      // GO! — major chord burst
      { freq: 523, type: "sine", gain: 0.35, dur: 0.4, delay: 0.6, attack: 0.005 },
      { freq: 659, type: "sine", gain: 0.25, dur: 0.35, delay: 0.6 },
      { freq: 784, type: "sine", gain: 0.2, dur: 0.3, delay: 0.62 },
      // Sub impact
      { freq: 65, type: "sine", gain: 0.3, dur: 0.3, delay: 0.6 },
    ],
    noiseMix: 0.08,
    noiseDur: 0.15,
  },

  // ── VICTORY: triumphant ascending major arpeggio ──
  victory: {
    totalDur: 1.2,
    layers: [
      { freq: 523, type: "sine", gain: 0.3, dur: 0.25, attack: 0.01 },
      { freq: 659, type: "sine", gain: 0.3, dur: 0.25, delay: 0.15 },
      { freq: 784, type: "sine", gain: 0.3, dur: 0.25, delay: 0.3 },
      { freq: 1047, type: "sine", gain: 0.35, dur: 0.5, delay: 0.45, attack: 0.01 },
      // Harmony backing
      { freq: 262, type: "triangle", gain: 0.15, dur: 0.8, delay: 0.3 },
      { freq: 392, type: "triangle", gain: 0.12, dur: 0.6, delay: 0.45 },
      // Sparkle top
      { freq: 2093, type: "sine", gain: 0.06, dur: 0.3, delay: 0.5 },
      { freq: 3136, type: "sine", gain: 0.04, dur: 0.2, delay: 0.55 },
    ],
  },

  // ── DEFEAT: somber descending minor progression ──
  defeat: {
    totalDur: 1.0,
    layers: [
      { freq: 392, type: "sine", gain: 0.25, dur: 0.3, attack: 0.02 },
      { freq: 330, type: "sine", gain: 0.25, dur: 0.3, delay: 0.2, freqRamp: 0.95 },
      { freq: 262, type: "sine", gain: 0.3, dur: 0.4, delay: 0.4, freqRamp: 0.9 },
      // Dark sub
      { freq: 82, type: "sawtooth", gain: 0.1, dur: 0.6, delay: 0.3 },
      // Minor third dissonance
      { freq: 311, type: "sine", gain: 0.1, dur: 0.3, delay: 0.45 },
    ],
  },

  // ── STREAK: power-up escalating tones ──
  streak: {
    totalDur: 0.6,
    layers: [
      { freq: 523, type: "sine", gain: 0.25, dur: 0.12, attack: 0.005 },
      { freq: 659, type: "sine", gain: 0.25, dur: 0.12, delay: 0.1 },
      { freq: 784, type: "sine", gain: 0.3, dur: 0.12, delay: 0.2 },
      { freq: 1047, type: "sine", gain: 0.35, dur: 0.2, delay: 0.3, freqRamp: 1.1 },
      // Power shimmer
      { freq: 2093, type: "sine", gain: 0.08, dur: 0.15, delay: 0.35 },
    ],
  },

  // ── RANK_UP: majestic fanfare with deep bass ──
  rank_up: {
    totalDur: 1.5,
    layers: [
      // Fanfare melody
      { freq: 392, type: "triangle", gain: 0.3, dur: 0.2, attack: 0.01 },
      { freq: 523, type: "triangle", gain: 0.3, dur: 0.2, delay: 0.18 },
      { freq: 659, type: "triangle", gain: 0.3, dur: 0.2, delay: 0.36 },
      { freq: 784, type: "sine", gain: 0.35, dur: 0.6, delay: 0.54, attack: 0.01 },
      // Sustained chord
      { freq: 523, type: "sine", gain: 0.2, dur: 0.6, delay: 0.6 },
      { freq: 659, type: "sine", gain: 0.15, dur: 0.5, delay: 0.65 },
      // Deep bass drum hit
      { freq: 60, type: "sine", gain: 0.35, dur: 0.3, delay: 0.54 },
      // Sparkle cascade
      { freq: 1568, type: "sine", gain: 0.06, dur: 0.3, delay: 0.7 },
      { freq: 2093, type: "sine", gain: 0.05, dur: 0.25, delay: 0.8 },
      { freq: 2637, type: "sine", gain: 0.04, dur: 0.2, delay: 0.9 },
    ],
  },

  // ── SUCCESS: rising chime — C5→G5 major, positive ──
  success: {
    totalDur: 0.4,
    layers: [
      { freq: 523, type: "sine", gain: 0.35, dur: 0.2, attack: 0.005 },
      { freq: 784, type: "sine", gain: 0.35, dur: 0.2, delay: 0.15, attack: 0.005 },
      // Shimmer harmonics
      { freq: 1047, type: "sine", gain: 0.1, dur: 0.15, delay: 0.15 },
      { freq: 1568, type: "sine", gain: 0.06, dur: 0.1, delay: 0.18 },
    ],
  },

  // ── EPIC: powerful boss-mode activation ──
  epic: {
    totalDur: 1.0,
    layers: [
      { freq: 110, type: "sawtooth", gain: 0.15, dur: 0.5, attack: 0.05 },
      { freq: 220, type: "triangle", gain: 0.2, dur: 0.6, delay: 0.1 },
      { freq: 330, type: "sine", gain: 0.25, dur: 0.5, delay: 0.2 },
      { freq: 440, type: "sine", gain: 0.3, dur: 0.4, delay: 0.35 },
      { freq: 660, type: "sine", gain: 0.2, dur: 0.3, delay: 0.5 },
    ],
    noiseMix: 0.06,
    noiseDur: 0.2,
  },

  // ── LEGENDARY: rare achievement cascading fanfare ──
  legendary: {
    totalDur: 1.5,
    layers: [
      { freq: 440, type: "sine", gain: 0.2, dur: 0.15 },
      { freq: 554, type: "sine", gain: 0.2, dur: 0.15, delay: 0.12 },
      { freq: 659, type: "sine", gain: 0.25, dur: 0.15, delay: 0.24 },
      { freq: 880, type: "sine", gain: 0.3, dur: 0.2, delay: 0.36 },
      { freq: 1047, type: "sine", gain: 0.35, dur: 0.6, delay: 0.5 },
      // Shimmer overtones
      { freq: 1760, type: "sine", gain: 0.08, dur: 0.4, delay: 0.6 },
      { freq: 2093, type: "sine", gain: 0.06, dur: 0.3, delay: 0.7 },
      { freq: 2637, type: "sine", gain: 0.05, dur: 0.2, delay: 0.8 },
      // Deep resonance
      { freq: 220, type: "triangle", gain: 0.15, dur: 0.8, delay: 0.4 },
    ],
  },

  // ── FAIL: descending tone 440→220Hz sweep, informational ──
  fail: {
    totalDur: 0.25,
    layers: [
      { freq: 440, type: "sine", gain: 0.3, dur: 0.2, freqRamp: 0.5, attack: 0.005 },
      // Soft sub layer for body
      { freq: 220, type: "triangle", gain: 0.12, dur: 0.15, delay: 0.05 },
    ],
  },

  // ── CLICK: short 800Hz blip, 50ms ──
  click: {
    totalDur: 0.05,
    layers: [
      { freq: 800, type: "sine", gain: 0.3, dur: 0.04, attack: 0.002 },
      { freq: 1600, type: "sine", gain: 0.1, dur: 0.02, attack: 0.001 },
    ],
  },

  // ── XP: quick ascending arpeggio C5-E5-G5, 150ms total ──
  xp: {
    totalDur: 0.18,
    layers: [
      { freq: 523, type: "sine", gain: 0.25, dur: 0.06, attack: 0.003 },
      { freq: 659, type: "sine", gain: 0.25, dur: 0.06, delay: 0.05, attack: 0.003 },
      { freq: 784, type: "sine", gain: 0.3, dur: 0.08, delay: 0.1, attack: 0.003 },
    ],
  },

  // ── LEVELUP (camelCase alias): major chord C4-E4-G4 held 500ms with fade ──
  levelUp: {
    totalDur: 0.6,
    layers: [
      { freq: 262, type: "sine", gain: 0.3, dur: 0.5, attack: 0.01, decayStart: 0.4 },
      { freq: 330, type: "sine", gain: 0.25, dur: 0.5, attack: 0.01, decayStart: 0.4 },
      { freq: 392, type: "sine", gain: 0.25, dur: 0.5, attack: 0.01, decayStart: 0.4 },
      // Octave shimmer
      { freq: 523, type: "sine", gain: 0.1, dur: 0.4, delay: 0.05, decayStart: 0.3 },
    ],
  },

  // ── NOTIFICATION: soft bell tone C6 (1047Hz), 300ms with harmonics ──
  notification: {
    totalDur: 0.4,
    layers: [
      { freq: 1047, type: "sine", gain: 0.3, dur: 0.3, attack: 0.005, decayStart: 0.15 },
      // Bell harmonics for reverb-like shimmer
      { freq: 2094, type: "sine", gain: 0.1, dur: 0.25, delay: 0.01, decayStart: 0.1 },
      { freq: 3141, type: "sine", gain: 0.05, dur: 0.2, delay: 0.02, decayStart: 0.08 },
      { freq: 523, type: "sine", gain: 0.08, dur: 0.35, delay: 0.005, decayStart: 0.2 },
    ],
  },

  // ── LEVELUP: ascending power chord ──
  levelup: {
    totalDur: 0.8,
    layers: [
      { freq: 262, type: "triangle", gain: 0.25, dur: 0.15 },
      { freq: 330, type: "triangle", gain: 0.25, dur: 0.15, delay: 0.1 },
      { freq: 392, type: "sine", gain: 0.3, dur: 0.15, delay: 0.2 },
      { freq: 523, type: "sine", gain: 0.35, dur: 0.35, delay: 0.3 },
      { freq: 784, type: "sine", gain: 0.15, dur: 0.25, delay: 0.35 },
    ],
  },

  // ── PVPMATCH: alert tone — 880Hz pulsed 3x, attention-grabbing ──
  pvpMatch: {
    totalDur: 0.5,
    layers: [
      { freq: 880, type: "sine", gain: 0.35, dur: 0.08, attack: 0.003 },
      { freq: 880, type: "sine", gain: 0.35, dur: 0.08, delay: 0.16, attack: 0.003 },
      { freq: 880, type: "sine", gain: 0.35, dur: 0.08, delay: 0.32, attack: 0.003 },
      // Subtle harmonic on last pulse
      { freq: 1760, type: "sine", gain: 0.1, dur: 0.06, delay: 0.33 },
    ],
  },

  // ── COUNTDOWNTICK: single 1000Hz blip, 30ms, low volume ──
  countdownTick: {
    totalDur: 0.04,
    layers: [
      { freq: 1000, type: "sine", gain: 0.15, dur: 0.03, attack: 0.001 },
    ],
  },

  // ── HOVER: very subtle 2000Hz blip, 20ms, barely audible ──
  hover: {
    totalDur: 0.03,
    layers: [
      { freq: 2000, type: "sine", gain: 0.05, dur: 0.02, attack: 0.001 },
    ],
  },
};

/**
 * Render a multi-layer sound design into an AudioBuffer.
 * Produces rich, game-quality audio using additive synthesis with
 * per-layer envelopes, frequency ramps, and optional noise.
 */
function _renderSoundDesign(ctx: AudioContext, design: SoundDesign): AudioBuffer {
  const sr = ctx.sampleRate;
  const totalSamples = Math.ceil(sr * design.totalDur);
  const buffer = ctx.createBuffer(1, totalSamples, sr);
  const output = buffer.getChannelData(0);

  for (const layer of design.layers) {
    const startSample = Math.floor((layer.delay ?? 0) * sr);
    const layerLen = Math.ceil(layer.dur * sr);
    const attack = layer.attack ?? 0.01;
    const attackSamples = Math.ceil(attack * sr);
    const decayStart = layer.decayStart ?? 0.3;
    const decaySample = Math.floor(decayStart * layerLen);

    for (let i = 0; i < layerLen; i++) {
      const idx = startSample + i;
      if (idx >= totalSamples) break;

      const t = i / sr;
      const freqMult = layer.freqRamp
        ? 1 + (layer.freqRamp - 1) * (t / layer.dur)
        : 1;
      const freq = layer.freq * freqMult;

      // ADSR envelope
      let env: number;
      if (i < attackSamples) {
        env = i / attackSamples; // Attack
      } else if (i < decaySample) {
        env = 1.0; // Sustain
      } else {
        env = Math.max(0, 1 - (i - decaySample) / (layerLen - decaySample)); // Release
      }

      // Oscillator
      const phase = 2 * Math.PI * freq * t;
      let sample = 0;
      switch (layer.type) {
        case "sine":
          sample = Math.sin(phase);
          break;
        case "square":
          sample = Math.sin(phase) > 0 ? 0.7 : -0.7;
          break;
        case "triangle":
          sample = 2 * Math.abs(2 * ((freq * t) % 1) - 1) - 1;
          break;
        case "sawtooth":
          sample = 2 * ((freq * t) % 1) - 1;
          break;
      }

      output[idx] += sample * env * layer.gain;
    }
  }

  // Optional noise layer
  if (design.noiseMix && design.noiseDur) {
    const noiseLen = Math.ceil(design.noiseDur * sr);
    for (let i = 0; i < noiseLen && i < totalSamples; i++) {
      const env = Math.max(0, 1 - i / noiseLen);
      output[i] += (Math.random() * 2 - 1) * design.noiseMix * env;
    }
  }

  // Soft clip to prevent distortion
  for (let i = 0; i < totalSamples; i++) {
    output[i] = Math.tanh(output[i]);
  }

  return buffer;
}

/**
 * Thin wrapper over Web Audio API for game sound effects.
 * Respects user mute preference (localStorage "vh-sounds-muted").
 *
 * Features:
 * - Loads .mp3 files from /sounds/ if available
 * - Falls back to multi-layer procedural synthesis (rich, game-quality)
 * - Caches decoded AudioBuffers for instant replay
 * - Soft-clip output prevents distortion
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
    // Check mute (support both legacy and new keys)
    try {
      if (localStorage.getItem("vh-sounds-muted") === "1") return;
      if (localStorage.getItem("vh_sound") === "off") return;
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
        try {
          const response = await fetch(path);
          if (!response.ok) throw new Error("not found");
          const arrayBuffer = await response.arrayBuffer();
          buffer = await ctx.decodeAudioData(arrayBuffer);
        } catch {
          // MP3 file missing — use multi-layer procedural synthesis
          const design = SOUND_DESIGNS[name];
          if (design) {
            buffer = _renderSoundDesign(ctx, design);
          } else {
            // Ultimate fallback: simple beep
            const sr = ctx.sampleRate;
            buffer = ctx.createBuffer(1, Math.ceil(sr * 0.15), sr);
            const data = buffer.getChannelData(0);
            for (let i = 0; i < data.length; i++) {
              data[i] = Math.sin(2 * Math.PI * 440 * (i / sr)) * Math.max(0, 1 - i / data.length) * 0.3;
            }
          }
        }
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
