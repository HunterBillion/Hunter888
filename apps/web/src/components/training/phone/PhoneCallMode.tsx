"use client";

/**
 * PhoneCallMode — full-screen "live call" UI for training sessions.
 *
 * Phase 2.10 (2026-04-19). User feedback: the default chat layout didn't
 * feel like a live phone call. This component presents a FaceTime/iPhone-
 * style full-screen experience on `/training/[id]/call`:
 *
 *   - Scene backdrop driven by CharacterBuilder's `bg_noise` choice
 *     (office / street / home-ish / neutral), so the "фон" decision from
 *     the builder actually reaches the user's eyes.
 *   - Large central avatar (TalkingHeadAvatar or Jarvis fallback) that
 *     lip-syncs to the TTS `audioLevel` from `useTTS`.
 *   - Elapsed call duration timer.
 *   - Three iPhone-style controls: mute, speaker toggle, hangup.
 *   - The CrystalMic for user voice input remains — V1 keeps the explicit
 *     tap-to-speak UX rather than implementing full-duplex VAD streaming
 *     (documented as a Phase 3 follow-up in the plan).
 *
 * The component is deliberately thin: it reads store state, renders, and
 * calls back to props for navigation / hangup. No WS wiring lives here;
 * the route `/training/[id]/call/page.tsx` reuses the existing session
 * page's connection by mounting this view on top of the same store.
 */

import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Mic, MicOff, Volume2, Volume1, PhoneOff } from "lucide-react";
import type { EmotionState } from "@/types";
import { EMOTION_MAP } from "@/types";
import type { ClientCardData } from "@/components/training/ClientCard";

// Scene backdrops — each value comes from CharacterBuilder's NOISES array.
// We map audio-noise tags to visual scenes: an "office" noise implies
// the client is calling from an office, "street" = outdoors, "children" or
// "tv" = home, "none" = neutral backdrop.
const SCENE_GRADIENTS: Record<string, string> = {
  office:
    "linear-gradient(135deg, #1b2a3a 0%, #2a3f57 45%, #0f1822 100%)",
  street:
    "linear-gradient(135deg, #2c2626 0%, #433436 45%, #0b0a0a 100%)",
  children:
    "linear-gradient(135deg, #3c2238 0%, #5a2d55 45%, #1a1420 100%)",
  tv:
    "linear-gradient(135deg, #2a1f3d 0%, #3d2e56 45%, #150f22 100%)",
  none:
    "linear-gradient(135deg, #0e0e14 0%, #16161f 45%, #05050a 100%)",
};

const SCENE_LABEL: Record<string, string> = {
  office: "Офис",
  street: "Улица",
  children: "Дом",
  tv: "Дом",
  none: "Звонок",
};

interface Props {
  characterName: string;
  emotion: EmotionState;
  /** Call-connection state drives the status line ("Соединение…" / "В сети"). */
  sessionState: "connecting" | "briefing" | "ready" | "completed";
  /** 0-1 current audio amplitude — for ring pulse, from useTTS hook. */
  audioLevel?: number;
  /** Call duration in seconds. */
  elapsed: number;
  /** Mic muted (user-side). */
  muted: boolean;
  /** Speaker on speaker-mode (louder). */
  speakerOn: boolean;
  /** Scene background id, usually from session.custom_bg_noise. */
  sceneId?: string | null;
  /** Optional client card; used for avatar/name fallback. */
  clientCard?: ClientCardData | null;
  onToggleMute: () => void;
  onToggleSpeaker: () => void;
  onHangup: () => void;
  /** Optional render slot for the mic button (the existing CrystalMic). */
  micSlot?: React.ReactNode;
  /** Current output volume (0..1). If undefined, slider is not rendered. */
  volume?: number;
  /** Called when the user drags the volume slider. */
  onVolumeChange?: (v: number) => void;

  // --- Coaching overlays (NEW 2026-04-21): feature-parity with chat ---
  /** 7-step BFL script — current stage number, label, completion list. */
  stage?: {
    current: number;          // 1..total
    label?: string;           // "Приветствие" / "Контакт" / ...
    completed: number[];      // completed stage numbers
    total: number;            // usually 7
  };
  /**
   * Most-recent coach whisper. Persists until a newer one arrives (no
   * auto-dismiss on voice: user can't re-glance when they're speaking).
   * Tap → expands full details panel.
   */
  coachingHint?: {
    message: string;
    priority?: "low" | "medium" | "high";
    icon?: string;
    type?: string;
  } | null;
}

function formatElapsed(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export function PhoneCallMode({
  characterName,
  emotion,
  sessionState,
  audioLevel = 0,
  elapsed,
  muted,
  speakerOn,
  sceneId,
  clientCard,
  onToggleMute,
  onToggleSpeaker,
  onHangup,
  micSlot,
  volume,
  onVolumeChange,
  stage,
  coachingHint,
}: Props) {
  const sceneKey = (sceneId || "none") in SCENE_GRADIENTS ? (sceneId || "none") : "none";
  const sceneGradient = SCENE_GRADIENTS[sceneKey];
  const sceneLabel = SCENE_LABEL[sceneKey];
  const ec = EMOTION_MAP[emotion] || EMOTION_MAP.cold;

  // Volume popover state: the speaker/volume button acts as a disclosure
  // trigger. First tap opens a slider popover above it; second tap hides.
  // Auto-closes on outside tap (see effect below). Only enabled when the
  // parent wired `volume` + `onVolumeChange` — otherwise speaker button
  // retains its legacy preset-toggle behavior.
  const [showVolumePopover, setShowVolumePopover] = useState(false);
  useEffect(() => {
    if (!showVolumePopover) return;
    const close = (e: MouseEvent) => {
      const t = e.target as HTMLElement;
      if (t.closest("[data-volume-popover], [data-volume-button]")) return;
      setShowVolumePopover(false);
    };
    window.addEventListener("click", close);
    return () => window.removeEventListener("click", close);
  }, [showVolumePopover]);

  // Gentle ambient animation so the scene feels alive when the AI isn't
  // actively speaking. Intensity scales with audioLevel when present.
  const breathingScale = useMemo(() => 1 + Math.min(0.08, audioLevel * 0.12), [audioLevel]);

  // Status line reflects both WS lifecycle and TTS activity.
  const statusLine = sessionState === "connecting"
    ? "Соединение…"
    : sessionState === "completed"
    ? "Звонок завершён"
    : audioLevel > 0.05
    ? "Говорит…"
    : "В сети";

  return (
    <div
      className="fixed inset-0 flex flex-col overflow-hidden text-white"
      style={{
        background: sceneGradient,
        backgroundAttachment: "fixed",
      }}
    >
      {/* Ambient radial vignette tied to emotion glow for subtle mood. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          background: `radial-gradient(ellipse at 50% 30%, ${ec.glow} 0%, transparent 55%)`,
          opacity: 0.45,
        }}
      />

      {/* Top meta row. */}
      <div className="relative z-10 flex items-start justify-between px-6 pt-5">
        <div className="flex flex-col">
          <span className="text-xs uppercase tracking-wider opacity-70">
            {sceneLabel}
          </span>
          <span className="font-mono text-xl mt-0.5" style={{ color: ec.color }}>
            {formatElapsed(elapsed)}
          </span>
        </div>
        <div className="flex flex-col items-end">
          <span className="text-xs uppercase tracking-wider opacity-70">
            {statusLine}
          </span>
          <span
            className="mt-1 rounded-full px-2 py-0.5 text-[10px] uppercase tracking-wider"
            style={{
              // `EmotionConfig` doesn't have `bg`/`border` — derive from
              // the base `color` with alpha so callers don't need an
              // extra helper module.
              background: `${ec.color}22`,
              color: ec.color,
              border: `1px solid ${ec.color}55`,
            }}
          >
            {ec.label}
          </span>
        </div>
      </div>

      {/*
        Stage teleprompter (2026-04-21 feature-parity with chat):
        thin inline strip showing 7-dot progress + current stage label.
        Reads tiny vertical space, does not overlap avatar, keeps the
        "where am I in the sales script" context present at all times.
      */}
      {stage && stage.total > 0 && (
        <div
          role="progressbar"
          aria-valuemin={1}
          aria-valuemax={stage.total}
          aria-valuenow={stage.current}
          aria-valuetext={`Этап ${stage.current} из ${stage.total}${stage.label ? `: ${stage.label}` : ""}`}
          className="relative z-10 mx-auto mt-3 flex w-[min(560px,calc(100vw-48px))] items-center gap-3 rounded-full bg-black/30 px-4 py-1.5 text-xs backdrop-blur-sm ring-1 ring-white/5"
        >
          <span className="font-mono tabular-nums text-white/70">
            {stage.current}/{stage.total}
          </span>
          <div className="flex flex-1 items-center gap-1">
            {Array.from({ length: stage.total }, (_, i) => i + 1).map((n) => {
              const done = stage.completed.includes(n);
              const isCur = n === stage.current;
              return (
                <span
                  key={n}
                  className="h-1.5 flex-1 rounded-full transition-colors"
                  style={{
                    background: done
                      ? "rgba(61, 220, 132, 0.8)"
                      : isCur
                      ? "rgba(255, 255, 255, 0.6)"
                      : "rgba(255, 255, 255, 0.12)",
                    boxShadow: isCur ? "0 0 8px rgba(255,255,255,0.4)" : "none",
                  }}
                />
              );
            })}
          </div>
          {stage.label && (
            <span className="truncate text-white/80" style={{ maxWidth: 140 }}>
              {stage.label}
            </span>
          )}
        </div>
      )}

      {/* Central avatar + ring. */}
      <div className="relative z-10 flex flex-1 flex-col items-center justify-center">
        <motion.div
          className="relative flex items-center justify-center"
          animate={{ scale: breathingScale }}
          transition={{ duration: 0.35 }}
        >
          {/* Outer pulse ring. */}
          <motion.div
            aria-hidden
            className="absolute rounded-full"
            animate={{
              scale: [1, 1 + Math.max(0.03, audioLevel * 0.35), 1],
              opacity: [0.55, 0.85, 0.55],
            }}
            transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
            style={{
              width: 280,
              height: 280,
              border: `2px solid ${ec.color}`,
              boxShadow: `0 0 48px ${ec.glow}`,
            }}
          />
          {/* Inner avatar disc. */}
          <div
            className="flex items-center justify-center rounded-full"
            style={{
              width: 220,
              height: 220,
              background: "rgba(255,255,255,0.04)",
              border: `3px solid ${ec.color}`,
              boxShadow: `inset 0 0 24px ${ec.glow}`,
              fontSize: 80,
              fontWeight: 700,
              color: ec.color,
              letterSpacing: "-0.02em",
            }}
          >
            {(characterName || "K").charAt(0).toUpperCase()}
          </div>
        </motion.div>

        <div className="mt-8 text-center">
          <div className="text-2xl font-semibold tracking-wide">{characterName}</div>
          {clientCard?.city && (
            <div className="mt-1 text-sm opacity-60">
              {clientCard.city}
              {clientCard.age ? `, ${clientCard.age} лет` : ""}
            </div>
          )}
        </div>
      </div>

      {/*
        Coach Pill (2026-04-21): floating rail over controls row that
        shows the latest whisper.coaching message. Stays visible until
        the next whisper replaces it (voice users can't re-glance mid-
        sentence, auto-dismiss is wrong here). Priority dot colors
        match the chat WhisperPanel conventions.
      */}
      {coachingHint && coachingHint.message && (
        <div className="relative z-10 px-6 pb-2">
          <div
            className="mx-auto flex max-w-md items-center gap-2.5 rounded-full bg-black/45 px-4 py-2 text-left ring-1 ring-white/10 backdrop-blur-md"
            aria-live="polite"
          >
            <span
              aria-hidden
              className="h-2 w-2 flex-shrink-0 rounded-full"
              style={{
                background:
                  coachingHint.priority === "high"
                    ? "#ef4444"
                    : coachingHint.priority === "medium"
                    ? "#f59e0b"
                    : "#60a5fa",
                boxShadow: `0 0 8px ${
                  coachingHint.priority === "high"
                    ? "rgba(239,68,68,0.6)"
                    : coachingHint.priority === "medium"
                    ? "rgba(245,158,11,0.6)"
                    : "rgba(96,165,250,0.6)"
                }`,
              }}
            />
            <span className="flex-1 text-sm text-white/95 leading-snug">
              {coachingHint.message}
            </span>
          </div>
        </div>
      )}

      {/* Controls row. */}
      <div className="relative z-10 pb-10 pt-6">
        {/*
          Volume popover (2026-04-21): parent passes volume + onVolumeChange.
          Tapping the speaker button now TOGGLES a slider popover anchored
          above the button, instead of flipping between two hardcoded
          levels. Backwards-compatible: if parent doesn't pass volume,
          we fall back to onToggleSpeaker on click like before.
        */}
        {typeof volume === "number" && onVolumeChange && showVolumePopover && (
          <div data-volume-popover className="mx-auto mb-4 max-w-md px-8">
            <div className="relative flex items-center gap-3 rounded-2xl bg-black/40 px-4 py-3 backdrop-blur-md ring-1 ring-white/10">
              <button
                type="button"
                onClick={() => onVolumeChange(volume > 0 ? 0 : 0.7)}
                aria-label={volume > 0 ? "Выключить звук" : "Включить звук"}
                className="flex h-8 w-8 items-center justify-center rounded-full text-white/80 transition hover:bg-white/10"
              >
                {volume === 0 ? <Volume1 size={18} /> : <Volume2 size={18} />}
              </button>
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={volume}
                onChange={(e) => onVolumeChange(parseFloat(e.target.value))}
                aria-label="Громкость"
                className="h-1 flex-1 cursor-pointer appearance-none rounded-full bg-white/20 accent-white"
              />
              <span className="min-w-[3ch] text-right font-mono text-xs text-white/60">
                {Math.round(volume * 100)}%
              </span>
            </div>
          </div>
        )}
        <div className="mx-auto flex max-w-md items-center justify-between px-10">
          {/*
            2026-04-21 layout fix — was previously two separate mic buttons:
            a mute-toggle here (which flipped a React state that nothing
            else read, i.e. dead) AND a real push-to-talk mic rendered in
            the micSlot below. That looked like duplicated UI to the user.
            Now: if the parent supplies micSlot, THAT becomes the left-most
            button — single source of truth for mic control. Parents that
            don't wire micSlot get the legacy mute-toggle as a fallback
            (backwards-compat for older callers).
          */}
          {micSlot ? (
            // The provided slot is expected to own its own flex-col button
            // layout (see call/page.tsx). Render it directly so the ring
            // stays symmetrical with the other two CallButtons.
            micSlot
          ) : (
            <CallButton
              label={muted ? "Вкл микрофон" : "Выкл микрофон"}
              onClick={onToggleMute}
              active={muted}
            >
              {muted ? <MicOff size={26} /> : <Mic size={26} />}
            </CallButton>
          )}

          <CallHangup onClick={onHangup} />

          <span data-volume-button>
            <CallButton
              label={typeof volume === "number" ? `Звук ${Math.round(volume * 100)}%` : (speakerOn ? "Обычный звук" : "Громкая связь")}
              onClick={() => {
                if (typeof volume === "number" && onVolumeChange) {
                  setShowVolumePopover((v) => !v);
                } else {
                  onToggleSpeaker();
                }
              }}
              active={typeof volume === "number" ? showVolumePopover : speakerOn}
            >
              {(typeof volume === "number" ? (volume > 0 ? true : false) : speakerOn) ? <Volume2 size={26} /> : <Volume1 size={26} />}
            </CallButton>
          </span>
        </div>
      </div>
    </div>
  );
}

function CallButton({
  children,
  onClick,
  label,
  active,
}: {
  children: React.ReactNode;
  onClick: () => void;
  label: string;
  active?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className="flex flex-col items-center gap-1.5"
    >
      <span
        className="flex h-16 w-16 items-center justify-center rounded-full transition-all duration-150 active:scale-95"
        style={{
          background: active ? "rgba(255,255,255,0.9)" : "rgba(255,255,255,0.12)",
          color: active ? "#0b0b14" : "#fff",
          border: "1px solid rgba(255,255,255,0.18)",
          backdropFilter: "blur(8px)",
        }}
      >
        {children}
      </span>
      <span className="text-[10px] uppercase tracking-wider opacity-70">
        {label}
      </span>
    </button>
  );
}

function CallHangup({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label="Завершить звонок"
      className="flex flex-col items-center gap-1.5"
    >
      <motion.span
        whileTap={{ scale: 0.9 }}
        className="flex h-16 w-16 items-center justify-center rounded-full"
        style={{
          background: "#ff3355",
          color: "#fff",
          boxShadow: "0 8px 28px rgba(255,51,85,0.5)",
        }}
      >
        <PhoneOff size={26} />
      </motion.span>
      <span className="text-[10px] uppercase tracking-wider text-red-300/80">
        Завершить
      </span>
    </button>
  );
}
