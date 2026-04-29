"use client";

/**
 * DuelChat — пиксельный чат дуэли.
 *
 * 2026-04-29 (Фаза 2 редизайна арены): полная замена терминал-стиля
 * (TrafficLights / $-prompt / pvp-chat — xhunter / font-mono) на
 * пиксель-аркадные речевые баблы с аватарами по тирам.
 *
 * API не сломан — все обязательные пропсы прежние (messages, myRole, input,
 * onInputChange, onSend, disabled, opponentStatus, scores). Добавлены два
 * опциональных пропса selfTier / opponentTier — без них рамки аватаров
 * нейтральные (как при unranked). Parent (apps/web/src/app/pvp/duel/[id]/page.tsx)
 * подключит их в Фазе 3, когда будет добавлен FighterCard.
 */

import { useEffect, useRef, useMemo, useState } from "react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { Send } from "lucide-react";
import { type PvPRankTier, PVP_RANK_COLORS, normalizeRankTier } from "@/types";

/* ── Constants ──────────────────────────────────────────── */
const MAX_MESSAGE_LENGTH = 2000;
/** Скорость typewriter-эффекта для входящих AI/opponent-сообщений. */
const TYPEWRITER_MS_PER_CHAR = 28;

/* ── Sanitizer (defense-in-depth for WS messages) ──────── */
function sanitizeMessageText(text: string): string {
  if (!text || typeof text !== "string") return "";
  const stripped = text.replace(/<[^>]*>/g, "");
  return stripped.length > MAX_MESSAGE_LENGTH
    ? stripped.slice(0, MAX_MESSAGE_LENGTH) + "…"
    : stripped;
}

function formatMessageTime(ts: string): string {
  try {
    const d = new Date(ts);
    if (isNaN(d.getTime())) return "";
    return d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

/* ── Types ──────────────────────────────────────────────── */
interface Message {
  id: string;
  sender_role: "seller" | "client";
  text: string;
  round: number;
  timestamp: string;
}

interface DuelScores {
  selling_score: number;
  acting_score: number;
  legal_accuracy: number;
}

type ConnectionStatus = "online" | "typing" | "offline" | "reconnecting";

interface Props {
  messages: Message[];
  myRole: "seller" | "client";
  input: string;
  onInputChange: (value: string) => void;
  onSend: () => void;
  disabled?: boolean;
  /** Optional: opponent connection status */
  opponentStatus?: ConnectionStatus;
  /** Optional: current judge scores to show in header */
  scores?: DuelScores | null;
  /** Optional: own rank tier — определяет цвет рамки твоего аватара. */
  selfTier?: PvPRankTier | string;
  /** Optional: opponent rank tier — цвет рамки аватара соперника. */
  opponentTier?: PvPRankTier | string;
}

/* ── Helpers ────────────────────────────────────────────── */
function tierColor(tier?: PvPRankTier | string): string {
  if (!tier) return "var(--text-muted)";
  const norm = normalizeRankTier(typeof tier === "string" ? tier : tier);
  return PVP_RANK_COLORS[norm] ?? "var(--text-muted)";
}

function roleInitials(role: "seller" | "client"): string {
  return role === "seller" ? "ME" : "OP";
}

/**
 * useTypewriter — печатает текст по символу.
 * Уважает prefers-reduced-motion: сразу показывает финальный текст.
 * Если `enabled=false` — тоже мгновенно (для своих сообщений).
 */
function useTypewriter(text: string, enabled: boolean): string {
  const reduce = useReducedMotion();
  const [displayed, setDisplayed] = useState(enabled && !reduce ? "" : text);

  useEffect(() => {
    if (!enabled || reduce) {
      setDisplayed(text);
      return;
    }
    setDisplayed("");
    let i = 0;
    const id = window.setInterval(() => {
      i += 1;
      setDisplayed(text.slice(0, i));
      if (i >= text.length) {
        window.clearInterval(id);
      }
    }, TYPEWRITER_MS_PER_CHAR);
    return () => window.clearInterval(id);
  }, [text, enabled, reduce]);

  return displayed;
}

/* ── Pixel Avatar ───────────────────────────────────────── */
/**
 * 56×56 пиксельный аватар. Без PNG — чисто CSS, чтобы не раздувать bundle.
 * Внутри: инициалы (ME / OP) на «stippled» фоне в цвет тира.
 * Рамка outline — тоже tier-color.
 */
function PixelAvatar({
  role,
  tier,
  side,
}: {
  role: "seller" | "client";
  tier?: PvPRankTier | string;
  side: "left" | "right";
}) {
  const color = tierColor(tier);
  return (
    <div
      aria-hidden
      className="shrink-0 relative flex items-center justify-center font-pixel"
      style={{
        width: 56,
        height: 56,
        outline: `3px solid ${color}`,
        outlineOffset: -3,
        background: `color-mix(in srgb, ${color} 12%, var(--bg-panel))`,
        backgroundImage: `repeating-linear-gradient(
          0deg,
          transparent 0,
          transparent 3px,
          color-mix(in srgb, ${color} 14%, transparent) 3px,
          color-mix(in srgb, ${color} 14%, transparent) 4px
        )`,
        boxShadow:
          side === "left"
            ? `3px 3px 0 0 ${color}`
            : `-3px 3px 0 0 ${color}`,
        color,
        fontSize: 18,
        letterSpacing: "0.05em",
        userSelect: "none",
      }}
    >
      {roleInitials(role)}
    </div>
  );
}

/* ── Pixel Spike Bubble ─────────────────────────────────── */
/**
 * Прямоугольный пиксель-бабл с треугольной «спайкой» к аватару.
 * Спайка — отдельный absolute div, повёрнутый на 45deg, с двумя видимыми
 * границами, чтобы шов с outline бабла был аккуратный.
 */
function PixelBubble({
  side,
  color,
  children,
}: {
  side: "left" | "right";
  color: string;
  children: React.ReactNode;
}) {
  // На left-side бабл стоит справа от аватара, спайка слева.
  // На right-side бабл стоит слева от аватара, спайка справа.
  const tailLeft = side === "left" ? -7 : "auto";
  const tailRight = side === "right" ? -7 : "auto";
  const tailBorder =
    side === "left"
      ? { borderLeft: `2px solid ${color}`, borderBottom: `2px solid ${color}` }
      : { borderRight: `2px solid ${color}`, borderTop: `2px solid ${color}` };

  return (
    <div
      className="relative max-w-[78%]"
      style={{
        background: "var(--bg-panel)",
        outline: `2px solid ${color}`,
        outlineOffset: -2,
        boxShadow: `3px 3px 0 0 ${color}`,
        padding: "10px 14px",
      }}
    >
      {/* tail */}
      <span
        aria-hidden
        className="absolute"
        style={{
          width: 12,
          height: 12,
          top: 16,
          left: tailLeft,
          right: tailRight,
          background: "var(--bg-panel)",
          transform: "rotate(45deg)",
          ...tailBorder,
        }}
      />
      {children}
    </div>
  );
}

/* ── Pixel Status Chip ──────────────────────────────────── */
function PixelStatusChip({ status }: { status: ConnectionStatus }) {
  const config: Record<ConnectionStatus, { label: string; color: string; pulse: boolean }> = {
    online: { label: "ONLINE", color: "var(--success)", pulse: false },
    typing: { label: "ПЕЧАТАЕТ", color: "var(--accent)", pulse: true },
    offline: { label: "OFFLINE", color: "var(--danger)", pulse: false },
    reconnecting: { label: "RECONNECT", color: "var(--warning)", pulse: true },
  };
  const c = config[status];
  return (
    <div
      className="inline-flex items-center gap-1.5 font-pixel"
      style={{
        padding: "3px 8px",
        background: "var(--bg-panel)",
        outline: `2px solid ${c.color}`,
        outlineOffset: -2,
        boxShadow: `2px 2px 0 0 ${c.color}`,
        color: c.color,
        fontSize: 11,
        letterSpacing: "0.12em",
        textTransform: "uppercase",
      }}
    >
      <span
        className={c.pulse ? "animate-pulse" : ""}
        style={{
          display: "inline-block",
          width: 6,
          height: 6,
          background: c.color,
        }}
      />
      {c.label}
    </div>
  );
}

/* ── Thinking dots (для пустого бабла «соперник думает») ── */
function ThinkingDots({ color }: { color: string }) {
  return (
    <span
      aria-hidden
      className="inline-flex items-center gap-1"
      role="presentation"
    >
      {[0, 1, 2].map((i) => (
        <motion.span
          key={i}
          style={{
            display: "inline-block",
            width: 5,
            height: 5,
            background: color,
          }}
          animate={{ opacity: [0.25, 1, 0.25] }}
          transition={{
            repeat: Infinity,
            duration: 1.1,
            delay: i * 0.2,
            ease: "easeInOut",
          }}
        />
      ))}
    </span>
  );
}

/* ── Single Message Row ─────────────────────────────────── */
function MessageRow({
  msg,
  isMine,
  selfTier,
  opponentTier,
  isLatestIncoming,
}: {
  msg: Message;
  isMine: boolean;
  selfTier?: PvPRankTier | string;
  opponentTier?: PvPRankTier | string;
  isLatestIncoming: boolean;
}) {
  const side: "left" | "right" = isMine ? "right" : "left";
  const tier = isMine ? selfTier : opponentTier;
  const color = tierColor(tier);
  const timeStr = formatMessageTime(msg.timestamp);

  // Typewriter — только для свежего входящего AI-сообщения.
  // Старые/исторические сообщения соперника отображаются мгновенно
  // (иначе при скролле в начало раунда зрелище становится мучительным).
  const displayed = useTypewriter(msg.text, !isMine && isLatestIncoming);

  // role="article" + aria-label позволяет screen reader-у адресно цитировать сообщение.
  const senderName =
    msg.sender_role === "seller" ? "Менеджер" : "Клиент";

  return (
    <motion.div
      role="article"
      aria-label={`${isMine ? "Вы" : "Соперник"} (${senderName}): ${msg.text}`}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22, ease: "easeOut" }}
      className={`flex items-start gap-3 ${
        side === "right" ? "flex-row-reverse" : "flex-row"
      }`}
    >
      <PixelAvatar role={msg.sender_role} tier={tier} side={side} />
      <PixelBubble side={side} color={color}>
        <div
          className="flex items-center justify-between gap-3 mb-1 font-pixel"
          style={{ fontSize: 11, letterSpacing: "0.14em", textTransform: "uppercase" }}
        >
          <span style={{ color }}>{isMine ? "ВЫ" : senderName}</span>
          {timeStr && (
            <span style={{ color: "var(--text-muted)", fontSize: 10 }}>
              {timeStr}
            </span>
          )}
        </div>
        <p
          className="leading-relaxed"
          style={{
            color: "var(--text-primary)",
            fontSize: 14,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            minHeight: "1.4em",
          }}
        >
          {displayed}
          {/* Каретка-блинкер во время печати */}
          {!isMine && isLatestIncoming && displayed.length < msg.text.length && (
            <motion.span
              aria-hidden
              style={{
                display: "inline-block",
                width: 7,
                height: 14,
                marginLeft: 2,
                background: color,
                verticalAlign: "text-bottom",
              }}
              animate={{ opacity: [0, 1, 0] }}
              transition={{ duration: 0.7, repeat: Infinity }}
            />
          )}
        </p>
      </PixelBubble>
    </motion.div>
  );
}

/* ── Typing bubble (соперник «думает») ──────────────────── */
function TypingBubble({ tier }: { tier?: PvPRankTier | string }) {
  const color = tierColor(tier);
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -4 }}
      className="flex items-start gap-3 flex-row"
      role="status"
      aria-live="polite"
      aria-label="Соперник набирает сообщение"
    >
      <PixelAvatar role="client" tier={tier} side="left" />
      <PixelBubble side="left" color={color}>
        <div
          className="flex items-center gap-2 font-pixel"
          style={{ fontSize: 12, letterSpacing: "0.14em", textTransform: "uppercase" }}
        >
          <span style={{ color }}>Думает</span>
          <ThinkingDots color={color} />
        </div>
      </PixelBubble>
    </motion.div>
  );
}

/* ── Score Header (pixelified) ──────────────────────────── */
function ScoreHeader({ scores }: { scores: DuelScores }) {
  const Cell = ({
    label,
    value,
    color,
  }: {
    label: string;
    value: number;
    color: string;
  }) => (
    <div className="flex items-baseline gap-1.5">
      <span
        className="font-pixel"
        style={{ color: "var(--text-muted)", fontSize: 10, letterSpacing: "0.14em" }}
      >
        {label}
      </span>
      <span
        className="font-pixel"
        style={{ color, fontSize: 18, letterSpacing: "0.04em" }}
      >
        {Math.round(value)}
      </span>
    </div>
  );
  return (
    <div
      className="flex items-center justify-center gap-6 px-4 py-2 shrink-0"
      style={{
        background: "var(--accent-muted)",
        borderBottom: "2px solid var(--accent)",
      }}
    >
      <Cell label="SELL" value={scores.selling_score} color="var(--accent)" />
      <span style={{ width: 2, height: 14, background: "var(--accent)" }} />
      <Cell label="ACT" value={scores.acting_score} color="var(--text-primary)" />
      <span style={{ width: 2, height: 14, background: "var(--accent)" }} />
      <Cell label="LEGAL" value={scores.legal_accuracy} color="var(--success)" />
    </div>
  );
}

/* ── Main Component ─────────────────────────────────────── */
export function DuelChat({
  messages,
  myRole,
  input,
  onInputChange,
  onSend,
  disabled,
  opponentStatus = "online",
  scores,
  selfTier,
  opponentTier,
}: Props) {
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const [isFocused, setIsFocused] = useState(false);

  const sanitizedMessages = useMemo(
    () => messages.map((msg) => ({ ...msg, text: sanitizeMessageText(msg.text) })),
    [messages],
  );

  // ID последнего входящего (от соперника) сообщения — для typewriter.
  const latestIncomingId = useMemo(() => {
    for (let i = sanitizedMessages.length - 1; i >= 0; i -= 1) {
      const m = sanitizedMessages[i];
      if (m.sender_role !== myRole) return m.id;
    }
    return null;
  }, [sanitizedMessages, myRole]);

  // Auto-scroll to latest message
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  };

  const charCount = input.length;
  const charWarning = charCount > 1800;
  const sendDisabled = disabled || !input.trim();

  return (
    <div
      className="flex h-full flex-col overflow-hidden"
      style={{
        background: "var(--bg-secondary)",
        outline: "2px solid var(--accent)",
        outlineOffset: -2,
        boxShadow: "4px 4px 0 0 var(--accent), 0 0 24px var(--accent-glow)",
      }}
    >
      {/* ── Pixel Title Bar (заменяет macOS terminal) ─────── */}
      <div
        className="flex items-center justify-between px-4 py-2.5 shrink-0"
        style={{
          background: "var(--bg-panel)",
          borderBottom: "2px solid var(--accent)",
        }}
      >
        <span
          className="font-pixel"
          style={{
            color: "var(--text-primary)",
            fontSize: 13,
            letterSpacing: "0.18em",
            textTransform: "uppercase",
          }}
        >
          ДИАЛОГ ДУЭЛИ
        </span>
        <PixelStatusChip status={opponentStatus} />
      </div>

      {/* ── Score Overlay (pixel) ─────────────────────────── */}
      {scores && <ScoreHeader scores={scores} />}

      {/* ── Messages Area ─────────────────────────────────── */}
      <div
        role="log"
        aria-live="polite"
        aria-label="История сообщений дуэли"
        className="flex-1 overflow-y-auto px-4 py-4 sm:px-5 sm:py-5"
        style={{
          background:
            "radial-gradient(ellipse at top, var(--accent-muted), transparent 60%)",
        }}
      >
        <div className="space-y-4">
          <AnimatePresence initial={false}>
            {sanitizedMessages.map((msg, index) => {
              const isMine = msg.sender_role === myRole;
              const previousRound =
                index > 0 ? sanitizedMessages[index - 1]?.round : null;
              return (
                <div key={msg.id}>
                  {/* Round separator — пиксельный */}
                  {(index === 0 || previousRound !== msg.round) && (
                    <div className="flex items-center gap-3 my-4">
                      <div
                        className="flex-1"
                        style={{
                          height: 2,
                          background:
                            "repeating-linear-gradient(to right, var(--accent) 0 6px, transparent 6px 10px)",
                        }}
                      />
                      <span
                        className="font-pixel"
                        style={{
                          color: "var(--accent)",
                          background: "var(--bg-panel)",
                          outline: "2px solid var(--accent)",
                          outlineOffset: -2,
                          boxShadow: "2px 2px 0 0 var(--accent)",
                          padding: "2px 10px",
                          fontSize: 11,
                          letterSpacing: "0.18em",
                          textTransform: "uppercase",
                        }}
                      >
                        Раунд {msg.round}
                      </span>
                      <div
                        className="flex-1"
                        style={{
                          height: 2,
                          background:
                            "repeating-linear-gradient(to right, var(--accent) 0 6px, transparent 6px 10px)",
                        }}
                      />
                    </div>
                  )}

                  <MessageRow
                    msg={msg}
                    isMine={isMine}
                    selfTier={selfTier}
                    opponentTier={opponentTier}
                    isLatestIncoming={msg.id === latestIncomingId}
                  />
                </div>
              );
            })}
          </AnimatePresence>

          <AnimatePresence>
            {opponentStatus === "typing" && (
              <TypingBubble tier={opponentTier} />
            )}
          </AnimatePresence>
        </div>
        <div ref={endRef} />
      </div>

      {/* ── Pixel Input Area (заменяет $-prompt) ──────────── */}
      <div
        className="shrink-0"
        style={{
          borderTop: "2px solid var(--accent)",
          background: "var(--bg-panel)",
        }}
      >
        <div className="flex items-end gap-2 p-3 sm:p-4">
          <div className="flex-1 min-w-0">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => {
                if (e.target.value.length <= MAX_MESSAGE_LENGTH) {
                  onInputChange(e.target.value);
                }
              }}
              onKeyDown={handleKeyDown}
              onFocus={() => setIsFocused(true)}
              onBlur={() => setIsFocused(false)}
              placeholder={
                disabled
                  ? "Жди раунд…"
                  : myRole === "seller"
                    ? "Твой ответ как менеджер…"
                    : "Ответ как клиент…"
              }
              disabled={disabled}
              rows={1}
              aria-label="Поле ввода сообщения"
              className="w-full min-h-[44px] max-h-28 resize-none outline-none"
              style={{
                color: "var(--text-primary)",
                caretColor: "var(--accent)",
                background: "var(--bg-secondary)",
                border: `2px solid ${isFocused ? "var(--accent)" : "var(--border-color)"}`,
                borderRadius: 0,
                padding: "10px 12px",
                fontFamily: "var(--font-geist-sans), sans-serif",
                fontSize: 14,
                lineHeight: 1.4,
                boxShadow: isFocused
                  ? "2px 2px 0 0 var(--accent)"
                  : "2px 2px 0 0 var(--border-color)",
                transition: "border-color 120ms, box-shadow 120ms",
              }}
            />
          </div>

          {/* Pixel Send Button (соответствует .ui-btn--primary паттерну) */}
          <motion.button
            onClick={onSend}
            disabled={sendDisabled}
            aria-label="Отправить сообщение"
            className="shrink-0 inline-flex items-center justify-center font-pixel"
            style={{
              width: 48,
              height: 48,
              background: sendDisabled ? "var(--bg-tertiary)" : "var(--accent)",
              color: sendDisabled ? "var(--text-muted)" : "#fff",
              border: `2px solid ${sendDisabled ? "var(--border-color)" : "var(--accent)"}`,
              borderRadius: 0,
              cursor: sendDisabled ? "not-allowed" : "pointer",
              boxShadow: sendDisabled
                ? "2px 2px 0 0 var(--border-color)"
                : "3px 3px 0 0 #000, 0 0 12px var(--accent-glow)",
              transition: "box-shadow 120ms, transform 120ms",
            }}
            whileHover={sendDisabled ? {} : { x: -1, y: -1 }}
            whileTap={sendDisabled ? {} : { x: 2, y: 2, boxShadow: "none" }}
          >
            <Send size={18} />
          </motion.button>
        </div>

        {/* Подсказка + счётчик */}
        {(charCount > 0 || isFocused) && (
          <div className="px-4 pb-2 flex items-center justify-between">
            <span
              className="font-pixel"
              style={{
                color: "var(--text-muted)",
                fontSize: 11,
                letterSpacing: "0.12em",
              }}
            >
              {isFocused ? "ENTER — ОТПРАВИТЬ · SHIFT+ENTER — НОВАЯ СТРОКА" : ""}
            </span>
            <span
              className="font-pixel"
              style={{
                color: charWarning ? "var(--danger)" : "var(--text-muted)",
                fontSize: 11,
                letterSpacing: "0.08em",
              }}
            >
              {charCount}/{MAX_MESSAGE_LENGTH}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
