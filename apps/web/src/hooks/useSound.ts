"use client";

/**
 * useSound — единый игровой звуковой движок.
 *
 * 2026-05-01 (Фаза 8): добавлены категории, master/category volume,
 * RMS-нормализация громкости между звуками (раньше у каждого был свой
 * gain в layers — отсюда разница «громко/тихо/не слышно»). Теперь:
 *
 *   final_amplitude = master * category[name] * normalized[name] * volumeArg
 *
 * Где:
 *   - master         — глобальный регулятор пользователя (0..1)
 *   - category       — отдельный регулятор для группы (sfx/ambient/ui/system)
 *   - normalized     — поправка для каждого звука к единому ~peak уровню
 *   - volumeArg      — необязательный per-call коэффициент (для drama)
 *
 * Все три ползунка хранятся в localStorage; компонент <SoundSettings />
 * на /settings обеспечивает UI.
 *
 * Backwards compatibility: старая сигнатура `playSound(name, volume?)`
 * продолжает работать. Старые ключи `vh-sounds-muted` и `vh_sound`
 * читаются как мастер-mute.
 */

import { useCallback, useEffect, useRef, useSyncExternalStore } from "react";

type SoundName =
  | "success" | "epic" | "legendary" | "fail" | "levelup"
  // Arena sounds
  | "correct" | "incorrect" | "tick" | "challenge"
  | "match_start" | "victory" | "defeat" | "streak" | "rank_up"
  // Phase 8 — new arena combat sounds
  | "heartbeat" | "hit" | "ko" | "swap"
  // PvP sounds
  | "pvpMatch" | "countdownTick"
  // Gamification sounds
  | "click" | "xp" | "levelUp" | "notification"
  // UI sounds
  | "hover";

export type { SoundName };

type SoundCategory = "sfx" | "ui" | "ambient" | "system";

/* ── Volume Storage Keys ─────────────────────────────────────────────── */
export const VOL_KEYS = {
  master: "vh-vol-master",
  sfx: "vh-vol-sfx",
  ui: "vh-vol-ui",
  ambient: "vh-vol-ambient",
  // legacy mute toggles — keep both for back-compat
  legacyMuted: "vh-sounds-muted",
  legacyOff: "vh_sound",
} as const;

/** Дефолтные уровни (0..1). Подобраны эмпирически — комфортно по громкости. */
const DEFAULT_VOLUMES = {
  master: 0.7,
  sfx: 0.85,
  ui: 0.6,
  ambient: 0.4,
};

/* ── Reactive volume store ───────────────────────────────────────────── */
type VolKey = keyof typeof VOL_KEYS;

function readVolume(key: VolKey, fallback: number): number {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = localStorage.getItem(VOL_KEYS[key]);
    if (!raw) return fallback;
    const n = Number(raw);
    if (Number.isFinite(n) && n >= 0 && n <= 1) return n;
    return fallback;
  } catch {
    return fallback;
  }
}

function writeVolume(key: VolKey, value: number) {
  if (typeof window === "undefined") return;
  try {
    const clamped = Math.max(0, Math.min(1, value));
    localStorage.setItem(VOL_KEYS[key], String(clamped));
    // Notify subscribers in same tab (storage event only fires in OTHER tabs)
    window.dispatchEvent(new CustomEvent("vh-volume-change"));
  } catch { /* private mode */ }
}

const subscribers = new Set<() => void>();
function subscribe(cb: () => void) {
  subscribers.add(cb);
  const onStorage = () => cb();
  window.addEventListener("storage", onStorage);
  window.addEventListener("vh-volume-change", onStorage);
  return () => {
    subscribers.delete(cb);
    window.removeEventListener("storage", onStorage);
    window.removeEventListener("vh-volume-change", onStorage);
  };
}

/** Hook: returns current volumes from storage, re-renders on change. */
export function useVolumes() {
  const snap = useSyncExternalStore(
    subscribe,
    () => JSON.stringify({
      master: readVolume("master", DEFAULT_VOLUMES.master),
      sfx: readVolume("sfx", DEFAULT_VOLUMES.sfx),
      ui: readVolume("ui", DEFAULT_VOLUMES.ui),
      ambient: readVolume("ambient", DEFAULT_VOLUMES.ambient),
    }),
    () => JSON.stringify(DEFAULT_VOLUMES),
  );
  const parsed = JSON.parse(snap) as { master: number; sfx: number; ui: number; ambient: number };
  return parsed;
}

/** Set master volume (0..1). */
export function setMasterVolume(v: number) { writeVolume("master", v); }
export function setCategoryVolume(c: SoundCategory, v: number) {
  if (c === "system") return; // system isn't user-configurable
  writeVolume(c, v);
}

export function isMutedGlobal(): boolean {
  if (typeof window === "undefined") return false;
  try {
    if (localStorage.getItem(VOL_KEYS.legacyMuted) === "1") return true;
    if (localStorage.getItem(VOL_KEYS.legacyOff) === "off") return true;
    if (readVolume("master", DEFAULT_VOLUMES.master) === 0) return true;
    return false;
  } catch { return false; }
}

export function setMutedGlobal(muted: boolean) {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(VOL_KEYS.legacyMuted, muted ? "1" : "0");
    window.dispatchEvent(new CustomEvent("vh-volume-change"));
  } catch { /* private */ }
}

/* ── Sound Designs ───────────────────────────────────────────────────── */

interface OscLayer {
  freq: number;
  type: OscillatorType;
  gain: number;
  freqRamp?: number;
  delay?: number;
  dur: number;
  attack?: number;
  decayStart?: number;
}

interface SoundDesign {
  layers: OscLayer[];
  noiseMix?: number;
  noiseDur?: number;
  totalDur: number;
  /** Логическая категория для регулятора пользователя. Default "sfx". */
  category?: SoundCategory;
  /**
   * Поправка громкости для нормализации между звуками. Подобрана так,
   * что у всех звуков примерно одинаковый peak. Default 1.0.
   * <1 уменьшает звук, >1 увеличивает.
   */
  normalize?: number;
}

const SOUND_DESIGNS: Partial<Record<SoundName, SoundDesign>> = {
  /* ═══ Arena combat ═══ */
  correct: {
    totalDur: 0.35,
    category: "sfx", normalize: 1.0,
    layers: [
      { freq: 880, type: "sine", gain: 0.4, dur: 0.15, attack: 0.005 },
      { freq: 1320, type: "sine", gain: 0.3, dur: 0.2, delay: 0.08, attack: 0.005 },
      { freq: 1760, type: "sine", gain: 0.15, dur: 0.15, delay: 0.08 },
      { freq: 2640, type: "sine", gain: 0.08, dur: 0.12, delay: 0.1 },
    ],
  },
  incorrect: {
    totalDur: 0.4,
    category: "sfx", normalize: 1.1,
    layers: [
      { freq: 330, type: "square", gain: 0.2, dur: 0.35, freqRamp: 0.7 },
      { freq: 220, type: "sawtooth", gain: 0.15, dur: 0.3, delay: 0.05 },
      { freq: 165, type: "sine", gain: 0.2, dur: 0.25, delay: 0.1 },
    ],
    noiseMix: 0.05, noiseDur: 0.1,
  },
  tick: {
    totalDur: 0.08,
    category: "ui", normalize: 1.4,
    layers: [
      { freq: 3000, type: "sine", gain: 0.3, dur: 0.02, attack: 0.001 },
      { freq: 6000, type: "sine", gain: 0.15, dur: 0.01, attack: 0.001 },
      { freq: 1500, type: "triangle", gain: 0.2, dur: 0.04 },
    ],
    noiseMix: 0.15, noiseDur: 0.02,
  },
  challenge: {
    totalDur: 0.8,
    category: "sfx", normalize: 0.85,
    layers: [
      { freq: 440, type: "triangle", gain: 0.3, dur: 0.2, attack: 0.01 },
      { freq: 554, type: "triangle", gain: 0.3, dur: 0.2, delay: 0.15 },
      { freq: 659, type: "triangle", gain: 0.35, dur: 0.3, delay: 0.3 },
      { freq: 110, type: "sine", gain: 0.2, dur: 0.6, delay: 0.1 },
      { freq: 1318, type: "sine", gain: 0.1, dur: 0.4, delay: 0.3 },
    ],
  },
  match_start: {
    totalDur: 1.0,
    category: "sfx", normalize: 0.85,
    layers: [
      { freq: 440, type: "sine", gain: 0.25, dur: 0.12, attack: 0.005 },
      { freq: 440, type: "sine", gain: 0.25, dur: 0.12, delay: 0.2 },
      { freq: 440, type: "sine", gain: 0.25, dur: 0.12, delay: 0.4 },
      { freq: 523, type: "sine", gain: 0.35, dur: 0.4, delay: 0.6, attack: 0.005 },
      { freq: 659, type: "sine", gain: 0.25, dur: 0.35, delay: 0.6 },
      { freq: 784, type: "sine", gain: 0.2, dur: 0.3, delay: 0.62 },
      { freq: 65, type: "sine", gain: 0.3, dur: 0.3, delay: 0.6 },
    ],
    noiseMix: 0.08, noiseDur: 0.15,
  },
  victory: {
    totalDur: 1.2,
    category: "sfx", normalize: 0.9,
    layers: [
      { freq: 523, type: "sine", gain: 0.3, dur: 0.25, attack: 0.01 },
      { freq: 659, type: "sine", gain: 0.3, dur: 0.25, delay: 0.15 },
      { freq: 784, type: "sine", gain: 0.3, dur: 0.25, delay: 0.3 },
      { freq: 1047, type: "sine", gain: 0.35, dur: 0.5, delay: 0.45, attack: 0.01 },
      { freq: 262, type: "triangle", gain: 0.15, dur: 0.8, delay: 0.3 },
      { freq: 392, type: "triangle", gain: 0.12, dur: 0.6, delay: 0.45 },
      { freq: 2093, type: "sine", gain: 0.06, dur: 0.3, delay: 0.5 },
      { freq: 3136, type: "sine", gain: 0.04, dur: 0.2, delay: 0.55 },
    ],
  },
  defeat: {
    totalDur: 1.0,
    category: "sfx", normalize: 1.0,
    layers: [
      { freq: 392, type: "sine", gain: 0.25, dur: 0.3, attack: 0.02 },
      { freq: 330, type: "sine", gain: 0.25, dur: 0.3, delay: 0.2, freqRamp: 0.95 },
      { freq: 262, type: "sine", gain: 0.3, dur: 0.4, delay: 0.4, freqRamp: 0.9 },
      { freq: 82, type: "sawtooth", gain: 0.1, dur: 0.6, delay: 0.3 },
      { freq: 311, type: "sine", gain: 0.1, dur: 0.3, delay: 0.45 },
    ],
  },
  streak: {
    totalDur: 0.6,
    category: "sfx", normalize: 0.95,
    layers: [
      { freq: 523, type: "sine", gain: 0.25, dur: 0.12, attack: 0.005 },
      { freq: 659, type: "sine", gain: 0.25, dur: 0.12, delay: 0.1 },
      { freq: 784, type: "sine", gain: 0.3, dur: 0.12, delay: 0.2 },
      { freq: 1047, type: "sine", gain: 0.35, dur: 0.2, delay: 0.3, freqRamp: 1.1 },
      { freq: 2093, type: "sine", gain: 0.08, dur: 0.15, delay: 0.35 },
    ],
  },
  rank_up: {
    totalDur: 1.5,
    category: "sfx", normalize: 0.8,
    layers: [
      { freq: 392, type: "triangle", gain: 0.3, dur: 0.2, attack: 0.01 },
      { freq: 523, type: "triangle", gain: 0.3, dur: 0.2, delay: 0.18 },
      { freq: 659, type: "triangle", gain: 0.3, dur: 0.2, delay: 0.36 },
      { freq: 784, type: "sine", gain: 0.35, dur: 0.6, delay: 0.54, attack: 0.01 },
      { freq: 523, type: "sine", gain: 0.2, dur: 0.6, delay: 0.6 },
      { freq: 659, type: "sine", gain: 0.15, dur: 0.5, delay: 0.65 },
      { freq: 60, type: "sine", gain: 0.35, dur: 0.3, delay: 0.54 },
      { freq: 1568, type: "sine", gain: 0.06, dur: 0.3, delay: 0.7 },
      { freq: 2093, type: "sine", gain: 0.05, dur: 0.25, delay: 0.8 },
      { freq: 2637, type: "sine", gain: 0.04, dur: 0.2, delay: 0.9 },
    ],
  },

  /* ═══ Phase 8 — new arena combat ═══ */
  // HEARTBEAT — глухой удар сердца, звучит на ≤5 сек таймера
  heartbeat: {
    totalDur: 0.4,
    category: "sfx", normalize: 1.4,
    layers: [
      // первый "lub"
      { freq: 60, type: "sine", gain: 0.5, dur: 0.08, attack: 0.005 },
      { freq: 100, type: "sine", gain: 0.3, dur: 0.06, attack: 0.005 },
      // короткая пауза, "dub"
      { freq: 70, type: "sine", gain: 0.4, dur: 0.08, delay: 0.13, attack: 0.005 },
      { freq: 110, type: "sine", gain: 0.25, dur: 0.06, delay: 0.13, attack: 0.005 },
    ],
    noiseMix: 0.04, noiseDur: 0.05,
  },
  // HIT — удар, когда судья присуждает очко
  hit: {
    totalDur: 0.25,
    category: "sfx", normalize: 1.0,
    layers: [
      // initial impact (sub punch)
      { freq: 80, type: "sine", gain: 0.5, dur: 0.08, attack: 0.001, freqRamp: 0.5 },
      // metallic ring
      { freq: 800, type: "triangle", gain: 0.25, dur: 0.12, delay: 0.01, attack: 0.001 },
      // bright tail
      { freq: 1600, type: "sine", gain: 0.15, dur: 0.1, delay: 0.02 },
      { freq: 2400, type: "sine", gain: 0.08, dur: 0.06, delay: 0.03 },
    ],
    noiseMix: 0.25, noiseDur: 0.05,
  },
  // KO — большой драматичный «BOOM» для PvPVictoryScreen Phase 1
  ko: {
    totalDur: 1.4,
    category: "sfx", normalize: 0.7,
    layers: [
      // огромный sub-impact
      { freq: 50, type: "sine", gain: 0.7, dur: 0.4, attack: 0.001, freqRamp: 0.4 },
      { freq: 90, type: "sine", gain: 0.5, dur: 0.3, attack: 0.001, freqRamp: 0.5 },
      // explosion ring
      { freq: 300, type: "sawtooth", gain: 0.3, dur: 0.5, delay: 0.02, freqRamp: 0.6 },
      { freq: 600, type: "triangle", gain: 0.25, dur: 0.4, delay: 0.04 },
      // descending wail
      { freq: 1200, type: "sine", gain: 0.15, dur: 0.6, delay: 0.1, freqRamp: 0.5 },
      // brass-like fanfare tail
      { freq: 220, type: "triangle", gain: 0.2, dur: 0.8, delay: 0.3 },
      { freq: 330, type: "triangle", gain: 0.18, dur: 0.7, delay: 0.35 },
      { freq: 440, type: "triangle", gain: 0.15, dur: 0.6, delay: 0.4 },
    ],
    noiseMix: 0.35, noiseDur: 0.15,
  },
  // SWAP — звук смены ролей между раундами
  swap: {
    totalDur: 0.5,
    category: "sfx", normalize: 1.0,
    layers: [
      // нисходящий sweep (старая роль уходит)
      { freq: 800, type: "sine", gain: 0.3, dur: 0.2, freqRamp: 0.5, attack: 0.005 },
      // восходящий sweep (новая роль приходит)
      { freq: 400, type: "sine", gain: 0.3, dur: 0.25, delay: 0.18, freqRamp: 1.8, attack: 0.005 },
      // accent pop
      { freq: 1200, type: "triangle", gain: 0.15, dur: 0.1, delay: 0.4 },
    ],
  },

  /* ═══ Existing reward / UI sounds ═══ */
  success: {
    totalDur: 0.4,
    category: "sfx", normalize: 0.95,
    layers: [
      { freq: 523, type: "sine", gain: 0.35, dur: 0.2, attack: 0.005 },
      { freq: 784, type: "sine", gain: 0.35, dur: 0.2, delay: 0.15, attack: 0.005 },
      { freq: 1047, type: "sine", gain: 0.1, dur: 0.15, delay: 0.15 },
      { freq: 1568, type: "sine", gain: 0.06, dur: 0.1, delay: 0.18 },
    ],
  },
  epic: {
    totalDur: 1.0,
    category: "sfx", normalize: 0.85,
    layers: [
      { freq: 110, type: "sawtooth", gain: 0.15, dur: 0.5, attack: 0.05 },
      { freq: 220, type: "triangle", gain: 0.2, dur: 0.6, delay: 0.1 },
      { freq: 330, type: "sine", gain: 0.25, dur: 0.5, delay: 0.2 },
      { freq: 440, type: "sine", gain: 0.3, dur: 0.4, delay: 0.35 },
      { freq: 660, type: "sine", gain: 0.2, dur: 0.3, delay: 0.5 },
    ],
    noiseMix: 0.06, noiseDur: 0.2,
  },
  legendary: {
    totalDur: 1.5,
    category: "sfx", normalize: 0.8,
    layers: [
      { freq: 440, type: "sine", gain: 0.2, dur: 0.15 },
      { freq: 554, type: "sine", gain: 0.2, dur: 0.15, delay: 0.12 },
      { freq: 659, type: "sine", gain: 0.25, dur: 0.15, delay: 0.24 },
      { freq: 880, type: "sine", gain: 0.3, dur: 0.2, delay: 0.36 },
      { freq: 1047, type: "sine", gain: 0.35, dur: 0.6, delay: 0.5 },
      { freq: 1760, type: "sine", gain: 0.08, dur: 0.4, delay: 0.6 },
      { freq: 2093, type: "sine", gain: 0.06, dur: 0.3, delay: 0.7 },
      { freq: 2637, type: "sine", gain: 0.05, dur: 0.2, delay: 0.8 },
      { freq: 220, type: "triangle", gain: 0.15, dur: 0.8, delay: 0.4 },
    ],
  },
  fail: {
    totalDur: 0.25,
    category: "sfx", normalize: 1.05,
    layers: [
      { freq: 440, type: "sine", gain: 0.3, dur: 0.2, freqRamp: 0.5, attack: 0.005 },
      { freq: 220, type: "triangle", gain: 0.12, dur: 0.15, delay: 0.05 },
    ],
  },
  click: {
    totalDur: 0.05,
    category: "ui", normalize: 1.6,
    layers: [
      { freq: 800, type: "sine", gain: 0.3, dur: 0.04, attack: 0.002 },
      { freq: 1600, type: "sine", gain: 0.1, dur: 0.02, attack: 0.001 },
    ],
  },
  xp: {
    totalDur: 0.18,
    category: "ui", normalize: 1.2,
    layers: [
      { freq: 523, type: "sine", gain: 0.25, dur: 0.06, attack: 0.003 },
      { freq: 659, type: "sine", gain: 0.25, dur: 0.06, delay: 0.05, attack: 0.003 },
      { freq: 784, type: "sine", gain: 0.3, dur: 0.08, delay: 0.1, attack: 0.003 },
    ],
  },
  levelUp: {
    totalDur: 0.6,
    category: "ui", normalize: 0.95,
    layers: [
      { freq: 262, type: "sine", gain: 0.3, dur: 0.5, attack: 0.01, decayStart: 0.4 },
      { freq: 330, type: "sine", gain: 0.25, dur: 0.5, attack: 0.01, decayStart: 0.4 },
      { freq: 392, type: "sine", gain: 0.25, dur: 0.5, attack: 0.01, decayStart: 0.4 },
      { freq: 523, type: "sine", gain: 0.1, dur: 0.4, delay: 0.05, decayStart: 0.3 },
    ],
  },
  notification: {
    totalDur: 0.4,
    category: "ui", normalize: 1.0,
    layers: [
      { freq: 1047, type: "sine", gain: 0.3, dur: 0.3, attack: 0.005, decayStart: 0.15 },
      { freq: 2094, type: "sine", gain: 0.1, dur: 0.25, delay: 0.01, decayStart: 0.1 },
      { freq: 3141, type: "sine", gain: 0.05, dur: 0.2, delay: 0.02, decayStart: 0.08 },
      { freq: 523, type: "sine", gain: 0.08, dur: 0.35, delay: 0.005, decayStart: 0.2 },
    ],
  },
  levelup: {
    totalDur: 0.8,
    category: "sfx", normalize: 0.95,
    layers: [
      { freq: 262, type: "triangle", gain: 0.25, dur: 0.15 },
      { freq: 330, type: "triangle", gain: 0.25, dur: 0.15, delay: 0.1 },
      { freq: 392, type: "sine", gain: 0.3, dur: 0.15, delay: 0.2 },
      { freq: 523, type: "sine", gain: 0.35, dur: 0.35, delay: 0.3 },
      { freq: 784, type: "sine", gain: 0.15, dur: 0.25, delay: 0.35 },
    ],
  },
  pvpMatch: {
    totalDur: 0.5,
    category: "sfx", normalize: 0.9,
    layers: [
      { freq: 880, type: "sine", gain: 0.35, dur: 0.08, attack: 0.003 },
      { freq: 880, type: "sine", gain: 0.35, dur: 0.08, delay: 0.16, attack: 0.003 },
      { freq: 880, type: "sine", gain: 0.35, dur: 0.08, delay: 0.32, attack: 0.003 },
      { freq: 1760, type: "sine", gain: 0.1, dur: 0.06, delay: 0.33 },
    ],
  },
  countdownTick: {
    totalDur: 0.04,
    category: "ui", normalize: 2.0,
    layers: [
      { freq: 1000, type: "sine", gain: 0.15, dur: 0.03, attack: 0.001 },
    ],
  },
  hover: {
    totalDur: 0.03,
    category: "ui", normalize: 3.0,
    layers: [
      { freq: 2000, type: "sine", gain: 0.05, dur: 0.02, attack: 0.001 },
    ],
  },
};

/* ── Render ──────────────────────────────────────────────────────────── */
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
      const freqMult = layer.freqRamp ? 1 + (layer.freqRamp - 1) * (t / layer.dur) : 1;
      const freq = layer.freq * freqMult;

      let env: number;
      if (i < attackSamples) env = i / attackSamples;
      else if (i < decaySample) env = 1.0;
      else env = Math.max(0, 1 - (i - decaySample) / (layerLen - decaySample));

      const phase = 2 * Math.PI * freq * t;
      let sample = 0;
      switch (layer.type) {
        case "sine": sample = Math.sin(phase); break;
        case "square": sample = Math.sin(phase) > 0 ? 0.7 : -0.7; break;
        case "triangle": sample = 2 * Math.abs(2 * ((freq * t) % 1) - 1) - 1; break;
        case "sawtooth": sample = 2 * ((freq * t) % 1) - 1; break;
      }
      output[idx] += sample * env * layer.gain;
    }
  }

  if (design.noiseMix && design.noiseDur) {
    const noiseLen = Math.ceil(design.noiseDur * sr);
    for (let i = 0; i < noiseLen && i < totalSamples; i++) {
      const env = Math.max(0, 1 - i / noiseLen);
      output[i] += (Math.random() * 2 - 1) * design.noiseMix * env;
    }
  }

  for (let i = 0; i < totalSamples; i++) output[i] = Math.tanh(output[i]);
  return buffer;
}

/* ── Hook ────────────────────────────────────────────────────────────── */
export function useSound() {
  const ctxRef = useRef<AudioContext | null>(null);
  const cacheRef = useRef<Map<string, AudioBuffer>>(new Map());

  const getContext = useCallback(() => {
    if (!ctxRef.current || ctxRef.current.state === "closed") {
      ctxRef.current = new AudioContext();
    }
    return ctxRef.current;
  }, []);

  useEffect(() => {
    return () => {
      if (ctxRef.current && ctxRef.current.state !== "closed") {
        ctxRef.current.close().catch(() => {});
        ctxRef.current = null;
      }
      cacheRef.current.clear();
    };
  }, []);

  const playSound = useCallback(async (name: SoundName, volume = 1.0) => {
    if (isMutedGlobal()) return;
    const design = SOUND_DESIGNS[name];
    if (!design) return;

    // Compute final amplitude
    const master = readVolume("master", DEFAULT_VOLUMES.master);
    const cat = design.category ?? "sfx";
    let categoryVol = DEFAULT_VOLUMES.sfx;
    if (cat === "sfx") categoryVol = readVolume("sfx", DEFAULT_VOLUMES.sfx);
    else if (cat === "ui") categoryVol = readVolume("ui", DEFAULT_VOLUMES.ui);
    else if (cat === "ambient") categoryVol = readVolume("ambient", DEFAULT_VOLUMES.ambient);
    // "system" — ignores user category sliders
    const norm = design.normalize ?? 1.0;
    const finalAmp = master * categoryVol * norm * volume;
    if (finalAmp <= 0) return;

    try {
      const ctx = getContext();
      if (ctx.state === "suspended") await ctx.resume();

      let buffer = cacheRef.current.get(name);
      if (!buffer) {
        buffer = _renderSoundDesign(ctx, design);
        cacheRef.current.set(name, buffer);
      }

      const source = ctx.createBufferSource();
      const gain = ctx.createGain();
      source.buffer = buffer;
      gain.gain.value = finalAmp;
      source.connect(gain).connect(ctx.destination);
      source.start();
    } catch { /* audio unavailable */ }
  }, [getContext]);

  const setMuted = useCallback((muted: boolean) => setMutedGlobal(muted), []);
  const isMuted = useCallback(() => isMutedGlobal(), []);

  return { playSound, setMuted, isMuted };
}
