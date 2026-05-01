"use client";

/**
 * DuelChat — пиксельный чат дуэли.
 *
 * 2026-04-29 Фаза 2 (PR #103): полная замена терминал-стиля на пиксельные
 * речевые баблы.
 * 2026-04-29 polish: уникальные SVG-портреты вместо инициалов, hover-lift,
 * own-bubble accent-tint, bigger digits, max-h на длинных сообщениях,
 * delivered ✓, wrap-aware score header, exit-анимация typing-bubble,
 * новые опциональные пропсы (deliveredIds).
 */

import { useEffect, useRef, useMemo, useState } from "react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { Send } from "lucide-react";
import { type PvPRankTier, PVP_RANK_COLORS, normalizeRankTier } from "@/types";
// 2026-05-01: 12-portrait avatar library (Phase 9)
import {
  PixelPortrait,
  type PixelAvatarCode,
} from "./PixelAvatarLibrary";

/* ── Constants ──────────────────────────────────────────── */
const MAX_MESSAGE_LENGTH = 2000;
/** Скорость typewriter-эффекта для входящих AI/opponent-сообщений. */
const TYPEWRITER_MS_PER_CHAR = 28;
/** Высота, выше которой длинное сообщение получит внутренний скролл. */
const LONG_MESSAGE_MAX_PX = 280;

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
  opponentStatus?: ConnectionStatus;
  scores?: DuelScores | null;
  selfTier?: PvPRankTier | string;
  opponentTier?: PvPRankTier | string;
  /** ID-сообщений, для которых сервер подтвердил доставку. Опционально. */
  deliveredIds?: string[];
  /** Авто-фокус инпута при маунте. По умолчанию false. */
  autoFocus?: boolean;
  /**
   * 2026-05-01: явные коды аватаров из 12-portrait library.
   * selfAvatar — твой портрет (rookie/operator/senior/lead).
   * opponentAvatar — портрет соперника (8 client-кодов).
   * Если не передано — fallback на operator/grandma по myRole.
   */
  selfAvatar?: PixelAvatarCode;
  opponentAvatar?: PixelAvatarCode;
}

/* ── Helpers ────────────────────────────────────────────── */
function tierColor(tier?: PvPRankTier | string): string {
  if (!tier) return "var(--text-muted)";
  const norm = normalizeRankTier(typeof tier === "string" ? tier : tier);
  return PVP_RANK_COLORS[norm] ?? "var(--text-muted)";
}

/**
 * useTypewriter — печатает текст по символу.
 * Уважает prefers-reduced-motion: сразу показывает финальный текст.
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

/* ── Pixel Avatar wrapper ───────────────────────────────────
 * 2026-05-01: SPRITE_MANAGER/SPRITE_CLIENT удалены отсюда. 12 спрайтов
 * живут в PixelAvatarSprites.ts. PixelPortrait сам рендерит 16×16 SVG
 * + применяет tier для player-литералов. Здесь — только tier-color рамка.
 * ───────────────────────────────────────────────────────── */

function PixelAvatar({
  code,
  tier,
  side,
}: {
  code: PixelAvatarCode;
  tier?: PvPRankTier | string;
  side: "left" | "right";
}) {
  const color = tierColor(tier);
  return (
    <div
      aria-hidden
      className="shrink-0 relative overflow-hidden"
      style={{
        width: 56,
        height: 56,
        outline: `3px solid ${color}`,
        outlineOffset: -3,
        background: `color-mix(in srgb, ${color} 18%, var(--bg-panel))`,
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
      }}
    >
      <PixelPortrait code={code} tier={tier} size={56} />
    </div>
  );
}

/* ── Pixel Spike Bubble ─────────────────────────────────── */
function PixelBubble({
  side,
  color,
  tinted,
  hoverable = true,
  children,
}: {
  side: "left" | "right";
  color: string;
  tinted: boolean;
  hoverable?: boolean;
  children: React.ReactNode;
}) {
  const tailLeft = side === "left" ? -7 : "auto";
  const tailRight = side === "right" ? -7 : "auto";
  const tailBorder =
    side === "left"
      ? { borderLeft: `2px solid ${color}`, borderBottom: `2px solid ${color}` }
      : { borderRight: `2px solid ${color}`, borderTop: `2px solid ${color}` };

  // Tinted = own bubble (мягкий fill в цвет тира). Чужой — нейтральный bg-panel.
  const bg = tinted
    ? `color-mix(in srgb, ${color} 14%, var(--bg-panel))`
    : "var(--bg-panel)";

  return (
    <motion.div
      whileHover={hoverable ? { x: -1, y: -1 } : undefined}
      transition={{ type: "spring", stiffness: 500, damping: 30 }}
      className="relative max-w-[78%]"
      style={{
        background: bg,
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
          background: bg,
          transform: "rotate(45deg)",
          ...tailBorder,
        }}
      />
      {children}
    </motion.div>
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
        padding: "3px 10px",
        background: "var(--bg-panel)",
        outline: `2px solid ${c.color}`,
        outlineOffset: -2,
        boxShadow: `2px 2px 0 0 ${c.color}`,
        color: c.color,
        fontSize: 13,
        letterSpacing: "0.14em",
        textTransform: "uppercase",
      }}
    >
      <span
        className={c.pulse ? "animate-pulse" : ""}
        style={{
          display: "inline-block",
          width: 7,
          height: 7,
          background: c.color,
        }}
      />
      {c.label}
    </div>
  );
}

/* ── Thinking dots ───────────────────────────────────────── */
function ThinkingDots({ color }: { color: string }) {
  return (
    <span aria-hidden className="inline-flex items-center gap-1" role="presentation">
      {[0, 1, 2].map((i) => (
        <motion.span
          key={i}
          style={{
            display: "inline-block",
            width: 6,
            height: 6,
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
  selfAvatar,
  opponentAvatar,
  isLatestIncoming,
  isDelivered,
}: {
  msg: Message;
  isMine: boolean;
  selfTier?: PvPRankTier | string;
  opponentTier?: PvPRankTier | string;
  selfAvatar: PixelAvatarCode;
  opponentAvatar: PixelAvatarCode;
  isLatestIncoming: boolean;
  isDelivered: boolean;
}) {
  const side: "left" | "right" = isMine ? "right" : "left";
  const tier = isMine ? selfTier : opponentTier;
  const avatarCode = isMine ? selfAvatar : opponentAvatar;
  const color = tierColor(tier);
  const timeStr = formatMessageTime(msg.timestamp);
  const displayed = useTypewriter(msg.text, !isMine && isLatestIncoming);
  const senderName = msg.sender_role === "seller" ? "Менеджер" : "Клиент";

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
      <PixelAvatar code={avatarCode} tier={tier} side={side} />
      <PixelBubble side={side} color={color} tinted={isMine}>
        <div
          className="flex items-center justify-between gap-3 mb-1 font-pixel"
          style={{ fontSize: 13, letterSpacing: "0.14em", textTransform: "uppercase" }}
        >
          <span style={{ color }}>{isMine ? "ВЫ" : senderName}</span>
          {timeStr && (
            <span style={{ color: "var(--text-muted)", fontSize: 12 }}>
              {timeStr}
            </span>
          )}
        </div>
        <div
          className="leading-relaxed"
          style={{
            color: "var(--text-primary)",
            fontSize: 15,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            minHeight: "1.4em",
            maxHeight: LONG_MESSAGE_MAX_PX,
            overflowY: "auto",
          }}
        >
          {displayed}
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
        </div>
        {/* Delivered tick (только для своих, и только если есть подтверждение) */}
        {isMine && isDelivered && (
          <div
            className="font-pixel"
            style={{
              marginTop: 4,
              textAlign: "right",
              color,
              fontSize: 12,
              letterSpacing: "0.04em",
            }}
            aria-label="Доставлено"
          >
            ✓
          </div>
        )}
      </PixelBubble>
    </motion.div>
  );
}

/* ── Typing bubble (соперник «думает») ──────────────────── */
function TypingBubble({
  tier,
  opponentAvatar,
}: {
  tier?: PvPRankTier | string;
  opponentAvatar: PixelAvatarCode;
}) {
  const color = tierColor(tier);
  return (
    <motion.div
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -8, transition: { duration: 0.18 } }}
      transition={{ duration: 0.22 }}
      className="flex items-start gap-3 flex-row"
      role="status"
      aria-live="polite"
      aria-label="Соперник набирает сообщение"
    >
      <PixelAvatar code={opponentAvatar} tier={tier} side="left" />
      <PixelBubble side="left" color={color} tinted={false} hoverable={false}>
        <div
          className="flex items-center gap-2 font-pixel"
          style={{ fontSize: 14, letterSpacing: "0.14em", textTransform: "uppercase" }}
        >
          <span style={{ color }}>Думает</span>
          <ThinkingDots color={color} />
        </div>
      </PixelBubble>
    </motion.div>
  );
}

/* ── Score Header (pixelified, wrap-aware) ──────────────── */
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
    <div className="flex flex-col items-center justify-center">
      <span
        className="font-pixel"
        style={{ color: "var(--text-muted)", fontSize: 11, letterSpacing: "0.18em" }}
      >
        {label}
      </span>
      <span
        className="font-pixel"
        style={{ color, fontSize: 26, letterSpacing: "0.04em", lineHeight: 1.1 }}
      >
        {Math.round(value)}
      </span>
    </div>
  );
  return (
    <div
      className="grid grid-cols-3 items-center px-4 py-2 shrink-0 gap-2"
      style={{
        background: "var(--accent-muted)",
        borderBottom: "2px solid var(--accent)",
      }}
    >
      <Cell label="SELL" value={scores.selling_score} color="var(--accent)" />
      <Cell label="ACT" value={scores.acting_score} color="var(--text-primary)" />
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
  deliveredIds,
  autoFocus = false,
  selfAvatar,
  opponentAvatar,
}: Props) {
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const [isFocused, setIsFocused] = useState(false);

  // Resolve avatars: explicit prop > sensible default by role.
  // 2026-05-01: дефолты — operator (player) и grandma (default client demographics).
  const resolvedSelfAvatar: PixelAvatarCode = selfAvatar ?? "operator";
  const resolvedOpponentAvatar: PixelAvatarCode = opponentAvatar ?? "grandma";

  const sanitizedMessages = useMemo(
    () => messages.map((msg) => ({ ...msg, text: sanitizeMessageText(msg.text) })),
    [messages],
  );

  const deliveredSet = useMemo(
    () => new Set(deliveredIds ?? []),
    [deliveredIds],
  );

  const latestIncomingId = useMemo(() => {
    for (let i = sanitizedMessages.length - 1; i >= 0; i -= 1) {
      const m = sanitizedMessages[i];
      if (m.sender_role !== myRole) return m.id;
    }
    return null;
  }, [sanitizedMessages, myRole]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (autoFocus && inputRef.current && !disabled) {
      inputRef.current.focus();
    }
  }, [autoFocus, disabled]);

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
            fontSize: 15,
            letterSpacing: "0.18em",
            textTransform: "uppercase",
          }}
        >
          ДИАЛОГ ДУЭЛИ
        </span>
        <PixelStatusChip status={opponentStatus} />
      </div>

      {scores && <ScoreHeader scores={scores} />}

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
                          padding: "3px 12px",
                          fontSize: 14,
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
                    selfAvatar={resolvedSelfAvatar}
                    opponentAvatar={resolvedOpponentAvatar}
                    isLatestIncoming={msg.id === latestIncomingId}
                    isDelivered={deliveredSet.has(msg.id)}
                  />
                </div>
              );
            })}
          </AnimatePresence>

          <AnimatePresence mode="wait">
            {opponentStatus === "typing" && (
              <TypingBubble tier={opponentTier} opponentAvatar={resolvedOpponentAvatar} />
            )}
          </AnimatePresence>
        </div>
        <div ref={endRef} />
      </div>

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
                fontSize: 15,
                lineHeight: 1.4,
                boxShadow: isFocused
                  ? "2px 2px 0 0 var(--accent)"
                  : "2px 2px 0 0 var(--border-color)",
                transition: "border-color 120ms, box-shadow 120ms",
              }}
            />
          </div>

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
            <Send size={20} />
          </motion.button>
        </div>

        {/* Char-counter — только когда есть текст. Подсказка про Enter удалена
            (по запросу: «убрал тупые слова»). Длина важна, hint про Enter — нет. */}
        {charCount > 0 && (
          <div className="px-4 pb-2 flex items-center justify-end">
            <span
              className="font-pixel"
              style={{
                color: charWarning ? "var(--danger)" : "var(--text-muted)",
                fontSize: 13,
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
