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

  // PR-26 (2026-05-08): TTS озвучка отключена по фидбэку юзера —
  // «убери звук, не нужна озвучка сколько секунд и так далее».
  // audioUrl игнорируется, кнопки play/pause не показываются.
  useEffect(() => {
    setAudioReady(false);
    setIsPlaying(false);
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
          background: "rgba(5,5,10,0.86)",
          backgroundImage: `
            radial-gradient(ellipse 60% 50% at 50% 30%, color-mix(in srgb, ${meta.tone} 14%, transparent) 0%, transparent 70%),
            radial-gradient(ellipse at top, rgba(107,77,199,0.10) 0%, transparent 55%),
            repeating-linear-gradient(0deg, transparent 0, transparent 31px, rgba(255,255,255,0.018) 31px, rgba(255,255,255,0.018) 32px),
            repeating-linear-gradient(90deg, transparent 0, transparent 31px, rgba(255,255,255,0.018) 31px, rgba(255,255,255,0.018) 32px)
          `,
          backdropFilter: "blur(8px)",
          WebkitBackdropFilter: "blur(8px)",
          WebkitFontSmoothing: "antialiased",
          MozOsxFontSmoothing: "grayscale",
        } as React.CSSProperties}
      >
        {/* PR-23: glass-arena card вместо pixel-arcade. */}
        <motion.div
          initial={{ scale: 0.95, y: 12, opacity: 0 }}
          animate={{ scale: 1, y: 0, opacity: 1 }}
          exit={{ scale: 0.92, opacity: 0 }}
          transition={{ type: "spring", stiffness: 280, damping: 24 }}
          className="w-full max-w-3xl relative flex flex-col rounded-3xl"
          style={{
            minHeight: "min(82vh, 780px)",
            maxHeight: "94vh",
            background: "linear-gradient(135deg, rgba(15,15,20,0.96) 0%, rgba(15,15,20,0.88) 100%)",
            border: "1px solid color-mix(in srgb, var(--accent) 40%, transparent)",
            boxShadow: `0 32px 80px color-mix(in srgb, var(--accent) 24%, transparent), 0 0 0 1px color-mix(in srgb, var(--accent) 18%, transparent), inset 0 1px 0 rgba(255,255,255,0.08)`,
            backdropFilter: "blur(24px) saturate(1.4)",
            WebkitBackdropFilter: "blur(24px) saturate(1.4)",
            overflow: "hidden",
          }}
        >
          {/* Title bar — glass */}
          <div
            className="flex items-center justify-between px-6 py-4 shrink-0"
            style={{
              borderBottom: "1px solid var(--glass-border, rgba(255,255,255,0.08))",
              background: "linear-gradient(180deg, color-mix(in srgb, var(--accent) 8%, transparent) 0%, transparent 100%)",
            }}
          >
            <div
              className="font-display font-bold uppercase"
              style={{ color: "var(--accent)", fontSize: 18, letterSpacing: "0.14em", textShadow: "0 0 14px var(--accent-glow)" }}
            >
              ▶ Новое дело · {caseId}
            </div>
            <div
              className="font-display font-bold uppercase rounded-xl px-3 py-1.5"
              style={{
                color: meta.tone,
                background: `linear-gradient(135deg, color-mix(in srgb, ${meta.tone} 18%, transparent) 0%, color-mix(in srgb, ${meta.tone} 4%, transparent) 100%)`,
                border: `1px solid color-mix(in srgb, ${meta.tone} 45%, transparent)`,
                boxShadow: `0 4px 14px color-mix(in srgb, ${meta.tone} 22%, transparent), inset 0 1px 0 rgba(255,255,255,0.06)`,
                fontSize: 11,
                letterSpacing: "0.14em",
              }}
            >
              {meta.label}
            </div>
          </div>

          {/* Personality banner — glass */}
          <div
            className="px-6 py-2.5 font-display font-bold uppercase shrink-0"
            style={{
              background: "color-mix(in srgb, var(--accent) 6%, transparent)",
              color: "var(--accent)",
              borderBottom: "1px solid var(--glass-border, rgba(255,255,255,0.06))",
              fontSize: 12,
              letterSpacing: "0.16em",
            }}
          >
            ▶ Ведёт дело: <span style={{ color: "var(--text-primary)", letterSpacing: "0.06em" }}>{personalityLabel}</span>
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
            style={{
              borderTop: "1px solid var(--glass-border, rgba(255,255,255,0.06))",
              background: "linear-gradient(0deg, rgba(0,0,0,0.32) 0%, transparent 100%)",
            }}
          >
            <div className="flex items-center gap-3" style={{ color: "var(--text-muted)", fontSize: 13 }}>
              <span className="font-display font-bold uppercase" style={{ letterSpacing: "0.14em", fontSize: 11 }}>
                Вопросов:{" "}
                <span className="font-display font-bold tabular-nums" style={{ color: "var(--text-primary)", fontSize: 20, letterSpacing: 0 }}>
                  {totalQuestions}
                </span>
              </span>
              {/* Audio controls — glass round buttons */}
              {audioUrl && audioReady && (
                <div className="flex items-center gap-2">
                  <motion.button
                    whileTap={{ scale: 0.94 }}
                    whileHover={{ y: -1 }}
                    onClick={togglePlay}
                    aria-label={isPlaying ? "Пауза" : "Воспроизвести"}
                    className="flex items-center justify-center rounded-xl"
                    style={{
                      width: 40, height: 40,
                      background: isPlaying
                        ? "linear-gradient(135deg, var(--accent) 0%, color-mix(in srgb, var(--accent) 78%, black) 100%)"
                        : "rgba(255,255,255,0.04)",
                      color: isPlaying ? "#fff" : "var(--accent)",
                      border: `1px solid ${isPlaying ? "color-mix(in srgb, var(--accent) 60%, white)" : "rgba(255,255,255,0.12)"}`,
                      boxShadow: isPlaying
                        ? "0 4px 14px color-mix(in srgb, var(--accent) 36%, transparent), inset 0 1px 0 rgba(255,255,255,0.18)"
                        : "0 2px 6px rgba(0,0,0,0.2), inset 0 1px 0 rgba(255,255,255,0.04)",
                      backdropFilter: "blur(20px)",
                      cursor: "pointer",
                    }}
                  >
                    {isPlaying ? <Pause size={16} /> : <Play size={16} />}
                  </motion.button>
                  <motion.button
                    whileTap={{ scale: 0.94 }}
                    whileHover={{ y: -1 }}
                    onClick={toggleMute}
                    aria-label={muted ? "Включить звук" : "Заглушить"}
                    className="flex items-center justify-center rounded-xl"
                    style={{
                      width: 40, height: 40,
                      background: "rgba(255,255,255,0.04)",
                      color: "var(--text-muted)",
                      border: "1px solid rgba(255,255,255,0.12)",
                      backdropFilter: "blur(20px)",
                      cursor: "pointer",
                    }}
                  >
                    {muted ? <VolumeX size={16} /> : <Volume2 size={16} />}
                  </motion.button>
                </div>
              )}
              {audioUrl && !audioReady && (
                <span className="font-mono uppercase" style={{ color: "var(--text-muted)", fontSize: 11, letterSpacing: "0.12em" }}>
                  ● Загрузка озвучки…
                </span>
              )}
            </div>
            <motion.button
              whileHover={{ y: -2 }}
              whileTap={{ scale: 0.97 }}
              onClick={onAccept}
              className="font-display font-bold uppercase rounded-2xl"
              style={{
                height: 56,
                padding: "0 36px",
                background: "linear-gradient(135deg, var(--accent) 0%, color-mix(in srgb, var(--accent) 78%, black) 100%)",
                color: "#fff",
                border: "1px solid color-mix(in srgb, var(--accent) 60%, white)",
                boxShadow: "0 12px 32px color-mix(in srgb, var(--accent) 40%, transparent), inset 0 1px 0 rgba(255,255,255,0.22)",
                fontSize: 16,
                letterSpacing: "0.18em",
                cursor: "pointer",
              }}
            >
              ▶ В дело
            </motion.button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
