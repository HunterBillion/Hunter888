"use client";

/**
 * ArenaAudioPlayer (Phase 2.8, 2026-04-19)
 *
 * Arcade-styled play/pause control for round narration audio emitted by
 * the server via `pvp.audio_ready`. Designed to share visual language with
 * the existing quiz-v2 case-intro player but with neon gaming palette
 * (orange/magenta/cyan pulsing ring, pixel font).
 *
 * Drops the arcade narration "Раунд N, время X сек" on top of the existing
 * round UI. Autoplay is attempted; on failure (browser blocked autoplay),
 * a manual Play button is exposed.
 */

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Play, Pause, Volume2, VolumeX } from "lucide-react";

interface Props {
  /** data-URL or regular URL of the audio, null when no audio yet. */
  audioUrl: string | null;
  /** Optional label above the control, e.g. "РАУНД 1". */
  label?: string;
  /** Auto-play on first mount if the browser allows. */
  autoplay?: boolean;
}

export function ArenaAudioPlayer({ audioUrl, label, autoplay = true }: Props) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(false);
  const [autoplayFailed, setAutoplayFailed] = useState(false);

  // When a new audio URL arrives, reset and attempt to play.
  useEffect(() => {
    if (!audioUrl || !audioRef.current) return;
    const el = audioRef.current;
    el.src = audioUrl;
    el.muted = muted;
    if (!autoplay) return;
    el.play()
      .then(() => {
        setPlaying(true);
        setAutoplayFailed(false);
      })
      .catch(() => setAutoplayFailed(true));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [audioUrl]);

  if (!audioUrl) return null;

  const toggle = () => {
    const el = audioRef.current;
    if (!el) return;
    if (playing) {
      el.pause();
    } else {
      el.play().catch(() => {});
    }
  };

  return (
    <AnimatePresence>
      <motion.div
        key={audioUrl}
        initial={{ opacity: 0, y: -6, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, scale: 0.94 }}
        transition={{ duration: 0.2 }}
        className="flex items-center gap-3 rounded-2xl px-3 py-2"
        style={{
          background: "rgba(0,0,0,0.55)",
          border: "2px solid #ff3ec8",
          boxShadow:
            "0 0 14px rgba(255,62,200,0.45), inset 0 0 6px rgba(255,210,80,0.25)",
        }}
      >
        {label && (
          <span
            className="font-pixel text-[10px] uppercase tracking-wider"
            style={{ color: "#ffd650" }}
          >
            {label}
          </span>
        )}

        <motion.button
          type="button"
          onClick={toggle}
          aria-label={playing ? "Пауза" : "Воспроизвести"}
          whileTap={{ scale: 0.9 }}
          animate={
            playing
              ? { boxShadow: ["0 0 4px #ff3ec8", "0 0 16px #ff3ec8", "0 0 4px #ff3ec8"] }
              : { boxShadow: "0 0 4px rgba(255,62,200,0.4)" }
          }
          transition={{ duration: 1.1, repeat: Infinity }}
          className="flex h-8 w-8 items-center justify-center rounded-full"
          style={{
            background: "linear-gradient(135deg, #ff3ec8 0%, #ffd650 100%)",
            color: "#0b0b14",
          }}
        >
          {playing ? <Pause size={14} /> : <Play size={14} />}
        </motion.button>

        <button
          type="button"
          onClick={() => {
            setMuted((m) => {
              const next = !m;
              if (audioRef.current) audioRef.current.muted = next;
              return next;
            });
          }}
          aria-label={muted ? "Включить звук" : "Выключить звук"}
          className="flex h-8 w-8 items-center justify-center rounded-full transition-colors hover:bg-white/10"
          style={{ color: "#ffd650" }}
        >
          {muted ? <VolumeX size={14} /> : <Volume2 size={14} />}
        </button>

        {autoplayFailed && (
          <span
            className="text-[10px] uppercase tracking-wider"
            style={{ color: "#ff3ec8" }}
          >
            нажми play
          </span>
        )}

        <audio
          ref={audioRef}
          preload="auto"
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onEnded={() => setPlaying(false)}
          style={{ display: "none" }}
        />
      </motion.div>
    </AnimatePresence>
  );
}
