"use client";

/**
 * QuizCaseIntro — full-screen pixel-arcade case briefing card.
 *
 * Shown ONCE at the start of a quiz_v2 session (when the backend emits
 * `case.intro` over the WS). User reads the case (optionally listens via
 * TTS if enabled), then clicks "В дело" to unveil the first question.
 *
 * 2026-04-18: created as part of quiz_v2 narrative redesign.
 */

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Play, Pause, Volume2, VolumeX } from "lucide-react";

interface QuizCaseIntroProps {
  caseId: string;
  complexity: "simple" | "tangled" | "adversarial";
  introText: string;           // multi-line narrative from presentation.py
  totalQuestions: number;
  personality: "professor" | "detective" | "blitz";
  audioUrl?: string | null;    // optional TTS audio (populated later in Э2)
  onAccept: () => void;        // user clicked "В дело"
}

const COMPLEXITY_META = {
  simple: { label: "Стандартное дело", tone: "var(--success)" },
  tangled: { label: "Запутанное дело", tone: "var(--warning)" },
  adversarial: { label: "Противоборство", tone: "var(--danger)" },
} as const;

export function QuizCaseIntro({
  caseId,
  complexity,
  introText,
  totalQuestions,
  personality,
  audioUrl,
  onAccept,
}: QuizCaseIntroProps) {
  const meta = COMPLEXITY_META[complexity];
  const personalityLabel =
    personality === "detective" ? "АРБИТРАЖНЫЙ СЛЕДОПЫТ" :
    personality === "professor" ? "ПРОФЕССОР КОДЕКСОВ" :
    "БЛИЦ-МАСТЕР";

  // Audio state — autoplay may be blocked by Chrome; surface Play button.
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [audioReady, setAudioReady] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [muted, setMuted] = useState(false);

  useEffect(() => {
    if (!audioUrl) {
      setAudioReady(false);
      return;
    }
    // Build <audio> element; try autoplay (comes from user click on "Start" so
    // browser usually allows it). Fall back to Play button if blocked.
    const a = new Audio(audioUrl);
    audioRef.current = a;
    a.onended = () => setIsPlaying(false);
    a.onplay = () => setIsPlaying(true);
    a.onpause = () => setIsPlaying(false);
    a.oncanplaythrough = () => setAudioReady(true);
    a.play()
      .then(() => setIsPlaying(true))
      .catch(() => setIsPlaying(false));
    return () => {
      a.pause();
      a.src = "";
      audioRef.current = null;
    };
  }, [audioUrl]);

  const togglePlay = () => {
    const a = audioRef.current;
    if (!a) return;
    if (a.paused) a.play().catch(() => {/* noop */});
    else a.pause();
  };
  const toggleMute = () => {
    const a = audioRef.current;
    if (!a) return;
    a.muted = !a.muted;
    setMuted(a.muted);
  };

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-[300] flex items-center justify-center p-2 sm:p-6"
        style={{
          background: "rgba(0,0,0,0.92)",
          backgroundImage: `
            radial-gradient(ellipse at top, rgba(107,77,199,0.15) 0%, transparent 55%),
            repeating-linear-gradient(0deg, transparent 0, transparent 23px, rgba(107,77,199,0.05) 23px, rgba(107,77,199,0.05) 24px),
            repeating-linear-gradient(90deg, transparent 0, transparent 23px, rgba(107,77,199,0.05) 23px, rgba(107,77,199,0.05) 24px)
          `,
        }}
      >
        {/* 2026-04-18: enlarged from max-w-xl → nearly fullscreen (max-w-3xl, min-h 82vh).
            User feedback: "карточка маленькая, не видно ничего". */}
        <motion.div
          initial={{ scale: 0.95, y: 12, opacity: 0 }}
          animate={{ scale: 1, y: 0, opacity: 1 }}
          exit={{ scale: 0.92, opacity: 0 }}
          transition={{ type: "spring", stiffness: 280, damping: 24 }}
          className="w-full max-w-3xl relative flex flex-col"
          style={{
            minHeight: "min(82vh, 780px)",
            maxHeight: "94vh",
            background: "var(--bg-panel)",
            border: "3px solid var(--accent)",
            borderRadius: 0,
            boxShadow: "8px 8px 0 0 var(--accent), 8px 8px 0 4px rgba(0,0,0,0.45), 0 0 48px var(--accent-glow)",
          }}
        >
          {/* Title bar — chunky */}
          <div
            className="flex items-center justify-between px-6 py-5 shrink-0"
            style={{ borderBottom: "3px solid var(--accent)", background: "rgba(107,77,199,0.08)" }}
          >
            <div
              className="font-pixel uppercase tracking-wider"
              style={{ color: "var(--accent)", fontSize: 20, textShadow: "0 0 8px var(--accent-glow)" }}
            >
              ▶ НОВОЕ ДЕЛО · {caseId}
            </div>
            <div
              className="font-pixel uppercase tracking-wider px-3 py-1.5"
              style={{
                color: meta.tone,
                border: `2px solid ${meta.tone}`,
                background: "var(--input-bg)",
                borderRadius: 0,
                boxShadow: `3px 3px 0 0 ${meta.tone}`,
                fontSize: 12,
              }}
            >
              {meta.label}
            </div>
          </div>

          {/* Personality banner */}
          <div
            className="px-6 py-3 font-pixel uppercase tracking-wider shrink-0"
            style={{
              background: "var(--accent-muted)",
              color: "var(--accent)",
              borderBottom: "2px solid var(--accent)",
              fontSize: 14,
            }}
          >
            ▶ Ведёт дело: <span style={{ color: "var(--text-primary)", letterSpacing: "0.1em" }}>{personalityLabel}</span>
          </div>

          {/* Narrative body — the main show */}
          <div className="flex-1 min-h-0 overflow-y-auto px-6 sm:px-10 py-6 sm:py-8">
            <p
              className="whitespace-pre-line leading-[1.7]"
              style={{
                color: "var(--text-primary)",
                fontFamily: "var(--font-mono, monospace)",
                fontSize: 17,
              }}
            >
              {introText}
            </p>
          </div>

          {/* Footer CTA — huge tap target for middle-aged users */}
          <div
            className="px-6 py-5 flex items-center justify-between gap-4 shrink-0 flex-wrap"
            style={{ borderTop: "3px solid var(--accent)", background: "rgba(0,0,0,0.25)" }}
          >
            <div className="font-pixel uppercase tracking-wider flex items-center gap-3" style={{ color: "var(--text-muted)", fontSize: 13 }}>
              <span>
                Вопросов:{" "}
                <span style={{ color: "var(--text-primary)", fontSize: 18 }}>{totalQuestions}</span>
              </span>
              {/* Audio controls — only shown when TTS audio is available */}
              {audioUrl && audioReady && (
                <div className="flex items-center gap-2">
                  <button
                    onClick={togglePlay}
                    aria-label={isPlaying ? "Пауза" : "Воспроизвести"}
                    className="flex items-center justify-center"
                    style={{
                      width: 40, height: 40,
                      background: isPlaying ? "var(--accent)" : "var(--input-bg)",
                      color: isPlaying ? "#fff" : "var(--accent)",
                      border: "2px solid var(--accent)",
                      borderRadius: 0,
                      boxShadow: "2px 2px 0 0 var(--accent-muted)",
                      cursor: "pointer",
                    }}
                  >
                    {isPlaying ? <Pause size={16} /> : <Play size={16} />}
                  </button>
                  <button
                    onClick={toggleMute}
                    aria-label={muted ? "Включить звук" : "Заглушить"}
                    className="flex items-center justify-center"
                    style={{
                      width: 40, height: 40,
                      background: "var(--input-bg)",
                      color: "var(--text-muted)",
                      border: "2px solid var(--border-color)",
                      borderRadius: 0,
                      boxShadow: "2px 2px 0 0 var(--border-color)",
                      cursor: "pointer",
                    }}
                  >
                    {muted ? <VolumeX size={16} /> : <Volume2 size={16} />}
                  </button>
                </div>
              )}
              {/* Hint that TTS is still loading */}
              {audioUrl && !audioReady && (
                <span className="font-pixel" style={{ color: "var(--text-muted)", fontSize: 11 }}>
                  ● ЗАГРУЗКА ОЗВУЧКИ…
                </span>
              )}
            </div>
            <motion.button
              whileHover={{ y: -2 }}
              whileTap={{ y: 3 }}
              onClick={onAccept}
              className="font-pixel uppercase tracking-wider"
              style={{
                height: 64,
                padding: "0 40px",
                background: "var(--accent)",
                color: "#fff",
                border: "3px solid var(--accent)",
                borderRadius: 0,
                boxShadow: "6px 6px 0 0 #000, 0 0 20px var(--accent-glow)",
                fontSize: 18,
                cursor: "pointer",
              }}
            >
              ▶ В ДЕЛО
            </motion.button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
