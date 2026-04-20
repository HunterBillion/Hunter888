"use client";

/**
 * ArenaAnswerInput — unified answer entry for all 5 Arena modes.
 *
 * Sprint 2 (2026-04-20). Features:
 *   - Text input with auto-resize
 *   - Mic button (uses ``useSpeechRecognition`` from training hooks)
 *     → appends recognised interim/final text into the input
 *   - Three lifeline buttons: Подсказка / Пропустить / 50-50
 *   - Enter to submit, Shift+Enter for newline
 *
 * Callers pass ``onSubmit`` with final text. Lifeline callbacks are
 * optional — mode-specific: e.g. tournaments disable all lifelines, PvE
 * enables hint+skip, Arena enables all three.
 */

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Mic, MicOff, Send, Lightbulb, SkipForward, Divide } from "lucide-react";
import { useSpeechRecognition } from "@/hooks/useSpeechRecognition";

export interface LifelineState {
  hintsLeft: number;       // -1 = disabled, ≥0 = count remaining
  skipsLeft: number;
  fiftyFiftysLeft: number;
}

interface Props {
  /** Placeholder text for the textarea. */
  placeholder?: string;
  /** Theme accent colour — comes from ArenaShell. */
  accentColor: string;
  /** Called with the final answer text when user hits Send / Enter. */
  onSubmit: (text: string) => void;
  /** Disabled after submit until next round (true = locked). */
  disabled?: boolean;

  lifelines?: LifelineState;
  onHint?: () => void;
  onSkip?: () => void;
  onFiftyFifty?: () => void;
}

export function ArenaAnswerInput({
  placeholder,
  accentColor,
  onSubmit,
  disabled = false,
  lifelines,
  onHint,
  onSkip,
  onFiftyFifty,
}: Props) {
  const [text, setText] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const speech = useSpeechRecognition({
    lang: "ru-RU",
    onResult: (finalText) => {
      setText((prev) => (prev ? `${prev} ${finalText}`.trim() : finalText));
    },
    onInterim: () => void 0,
    onError: () => void 0,
  });

  const micActive = speech.status === "listening" || speech.status === "processing";

  // 2026-04-20: голос — ключевая фича Арены, кнопка микрофона должна быть
  // ВСЕГДА на видном месте. Раньше при `!speech.isSupported` она вообще
  // не рендерилась → юзер читал "нажмите на микрофон", но микрофона нет.
  // Теперь кнопка всегда видна; если API недоступен — disabled с
  // tooltip-объяснением ("в этом браузере не работает").
  const effectivePlaceholder =
    placeholder ?? "Введи ответ или нажми микрофон…";

  // Autoresize textarea up to 4 rows
  useEffect(() => {
    const t = textareaRef.current;
    if (!t) return;
    t.style.height = "auto";
    t.style.height = `${Math.min(t.scrollHeight, 120)}px`;
  }, [text]);

  // Phase C (2026-04-20) — submit lock. Previous behaviour let a fast
  // double-tap / keyboard hold fire ``onSubmit`` twice before the parent
  // could disable the input. ``submittingRef`` flips synchronously inside
  // the click/Enter handler and auto-clears 400 ms later (covers the
  // round of React commit + WS roundtrip on typical networks).
  const submittingRef = useRef(false);
  const handleSubmit = () => {
    if (submittingRef.current) return;
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    submittingRef.current = true;
    try {
      onSubmit(trimmed);
    } finally {
      setText("");
      if (micActive) speech.stopListening();
      // Release the lock shortly after so the input is usable again if
      // the parent kept ``disabled`` false (e.g. turn-based roleplay
      // sends many messages per round).
      setTimeout(() => {
        submittingRef.current = false;
      }, 400);
    }
  };

  const handleKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const toggleMic = () => {
    if (micActive) {
      speech.stopListening();
    } else if (speech.isSupported) {
      speech.startListening();
    }
  };

  return (
    <div className="flex flex-col gap-2 max-w-3xl mx-auto w-full">
      {/* Lifelines row — only if any are configured */}
      {lifelines && (onHint || onSkip || onFiftyFifty) && (
        <div className="flex items-center gap-2 flex-wrap">
          {onHint && lifelines.hintsLeft >= 0 && (
            <LifelineButton
              icon={Lightbulb}
              label="Подсказка"
              remaining={lifelines.hintsLeft}
              accent="#facc15"
              disabled={disabled || lifelines.hintsLeft === 0}
              onClick={onHint}
            />
          )}
          {onSkip && lifelines.skipsLeft >= 0 && (
            <LifelineButton
              icon={SkipForward}
              label="Пропустить"
              remaining={lifelines.skipsLeft}
              accent="#94a3b8"
              disabled={disabled || lifelines.skipsLeft === 0}
              onClick={onSkip}
            />
          )}
          {onFiftyFifty && lifelines.fiftyFiftysLeft >= 0 && (
            <LifelineButton
              icon={Divide}
              label="50/50"
              remaining={lifelines.fiftyFiftysLeft}
              accent="#22d3ee"
              disabled={disabled || lifelines.fiftyFiftysLeft === 0}
              onClick={onFiftyFifty}
            />
          )}
          {/* Mic audio-level indicator — subtle ring grows with speech level */}
          <AnimatePresence>
            {micActive && (
              <motion.div
                className="flex items-center gap-1.5 ml-auto text-xs"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                style={{ color: accentColor }}
              >
                <motion.div
                  className="h-2 w-2 rounded-full"
                  style={{ background: accentColor }}
                  animate={{
                    scale: 1 + (speech.audioLevel / 100) * 1.2,
                    opacity: 0.6 + (speech.audioLevel / 100) * 0.4,
                  }}
                  transition={{ duration: 0.1 }}
                />
                <span className="font-mono font-semibold uppercase tracking-wider">
                  слушаю
                </span>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}

      {/* Main input row */}
      <div
        className="flex items-end gap-2 rounded-xl p-2"
        style={{
          background: "var(--input-bg)",
          border: `1px solid ${accentColor}33`,
          boxShadow: `0 0 0 2px ${accentColor}00`,
        }}
      >
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKey}
          placeholder={effectivePlaceholder}
          disabled={disabled}
          rows={1}
          className="flex-1 resize-none bg-transparent px-2 py-1.5 text-[15px] leading-relaxed outline-none"
          style={{ color: "var(--text-primary)" }}
          aria-label="Введи ответ"
        />

        <motion.button
          type="button"
          onClick={toggleMic}
          disabled={disabled || !speech.isSupported}
          className="flex h-10 w-10 items-center justify-center rounded-lg transition-colors disabled:opacity-40"
          style={{
            background: micActive ? accentColor : "transparent",
            color: micActive ? "#0b0b14" : accentColor,
            border: `1px solid ${accentColor}55`,
          }}
          animate={
            micActive
              ? { boxShadow: [
                  `0 0 0 0 ${accentColor}55`,
                  `0 0 0 6px ${accentColor}00`,
                  `0 0 0 0 ${accentColor}00`,
                ] }
              : undefined
          }
          transition={micActive ? { duration: 1.4, repeat: Infinity } : undefined}
          whileTap={{ scale: 0.9 }}
          title={
            !speech.isSupported
              ? "Голосовой ввод не поддерживается в этом браузере"
              : micActive
              ? "Остановить запись"
              : "Говорить голосом"
          }
          aria-label={
            !speech.isSupported
              ? "Микрофон недоступен"
              : micActive
              ? "Остановить микрофон"
              : "Включить микрофон"
          }
        >
          {micActive ? <MicOff size={17} /> : <Mic size={17} />}
        </motion.button>

        <motion.button
          type="button"
          onClick={handleSubmit}
          disabled={disabled || !text.trim()}
          className="flex h-10 w-10 items-center justify-center rounded-lg transition-all disabled:opacity-35"
          style={{
            background: accentColor,
            color: "#0b0b14",
            boxShadow: text.trim() ? `0 4px 12px ${accentColor}55` : undefined,
          }}
          whileTap={{ scale: 0.9 }}
          title="Отправить"
          aria-label="Send answer"
        >
          <Send size={17} />
        </motion.button>
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────
// Internal: single lifeline chip
// ────────────────────────────────────────────────────────────────────

function LifelineButton({
  icon: Icon,
  label,
  remaining,
  accent,
  disabled,
  onClick,
}: {
  icon: React.ComponentType<{ size?: number }>;
  label: string;
  remaining: number;
  accent: string;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-semibold uppercase tracking-wider transition-all disabled:opacity-35"
      style={{
        background: disabled ? "var(--input-bg)" : `${accent}18`,
        color: disabled ? "var(--text-muted)" : accent,
        border: `1px solid ${accent}33`,
      }}
      title={`${label}: осталось ${remaining}`}
    >
      <Icon size={12} />
      <span>{label}</span>
      <span
        className="ml-0.5 font-mono tabular-nums"
        style={{ color: accent, opacity: 0.8 }}
      >
        ×{remaining}
      </span>
    </button>
  );
}
