"use client";

import { useEffect, useRef, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Send, Wifi, WifiOff, MoreHorizontal } from "lucide-react";

/* ── Constants ──────────────────────────────────────────── */
const MAX_MESSAGE_LENGTH = 2000;

/* ── Sanitizer (defense-in-depth for WS messages) ──────── */
function sanitizeMessageText(text: string): string {
  if (!text || typeof text !== "string") return "";
  const stripped = text.replace(/<[^>]*>/g, "");
  return stripped.length > MAX_MESSAGE_LENGTH
    ? stripped.slice(0, MAX_MESSAGE_LENGTH) + "\u2026"
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
}

/* ── Subcomponents ──────────────────────────────────────── */

/** macOS-style traffic light dots */
function TrafficLights() {
  return (
    <div className="flex items-center gap-1.5 shrink-0">
      <span
        className="block w-[10px] h-[10px] rounded-full"
        style={{ background: "#ff5f57" }}
      />
      <span
        className="block w-[10px] h-[10px] rounded-full"
        style={{ background: "#febc2e" }}
      />
      <span
        className="block w-[10px] h-[10px] rounded-full"
        style={{ background: "#28c840" }}
      />
    </div>
  );
}

/** Status badge for opponent */
function StatusBadge({ status }: { status: ConnectionStatus }) {
  const config: Record<
    ConnectionStatus,
    { label: string; color: string; dot: string; pulse: boolean }
  > = {
    online: {
      label: "online",
      color: "rgba(40,200,64,0.15)",
      dot: "#28c840",
      pulse: false,
    },
    typing: {
      label: "typing\u2026",
      color: "var(--accent-muted)",
      dot: "var(--accent)",
      pulse: true,
    },
    offline: {
      label: "offline",
      color: "rgba(255,95,87,0.12)",
      dot: "#ff5f57",
      pulse: false,
    },
    reconnecting: {
      label: "reconnecting",
      color: "rgba(254,188,46,0.12)",
      dot: "#febc2e",
      pulse: true,
    },
  };

  const c = config[status];

  return (
    <div
      className="flex items-center gap-1.5 rounded-full px-2.5 py-1"
      style={{ background: c.color }}
    >
      <span
        className={`block w-[6px] h-[6px] rounded-full ${c.pulse ? "animate-pulse" : ""}`}
        style={{ background: c.dot }}
      />
      <span
        className="font-mono text-xs uppercase tracking-widest"
        style={{ color: "var(--text-muted)" }}
      >
        {c.label}
      </span>
    </div>
  );
}

/** Typing indicator dots animation */
function TypingDots() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -4 }}
      className="flex justify-start"
    >
      <div
        className="flex items-center gap-1 px-4 py-3"
        style={{
          borderRadius: "16px 16px 16px 4px",
          background: "var(--bg-tertiary)",
        }}
      >
        {[0, 1, 2].map((i) => (
          <motion.span
            key={i}
            className="block w-[5px] h-[5px] rounded-full"
            style={{ background: "var(--text-muted)" }}
            animate={{ opacity: [0.3, 1, 0.3] }}
            transition={{
              repeat: Infinity,
              duration: 1.2,
              delay: i * 0.2,
              ease: "easeInOut",
            }}
          />
        ))}
      </div>
    </motion.div>
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
}: Props) {
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const [isFocused, setIsFocused] = useState(false);

  const sanitizedMessages = useMemo(
    () => messages.map((msg) => ({ ...msg, text: sanitizeMessageText(msg.text) })),
    [messages],
  );

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

  const myLabel = myRole === "seller" ? "Менеджер" : "Клиент";
  const oppLabel = myRole === "seller" ? "Клиент" : "Менеджер";

  return (
    <div
      className="flex h-full flex-col overflow-hidden rounded-lg"
      style={{
        background: "var(--bg-secondary)",
        border: "1px solid var(--border-color)",
        boxShadow: "0 8px 32px var(--overlay-bg)",
      }}
    >
      {/* ── macOS Title Bar ───────────────────────────────── */}
      <div
        className="flex items-center px-3.5 py-2.5 shrink-0"
        style={{
          background: "var(--glass-bg)",
          borderBottom: "1px solid var(--border-color)",
        }}
      >
        <TrafficLights />

        {/* Centered terminal title */}
        <div className="flex-1 text-center">
          <span
            className="font-mono text-xs tracking-wide"
            style={{ color: "var(--text-muted)" }}
          >
            pvp-chat &mdash; xhunter
          </span>
        </div>

        {/* Balance spacer + opponent status */}
        <div className="flex items-center gap-2 shrink-0">
          <StatusBadge status={opponentStatus} />
        </div>
      </div>

      {/* ── Score Overlay Bar ─────────────────────────────── */}
      {scores && (
        <div
          className="flex items-center justify-center gap-6 px-4 py-2 shrink-0"
          style={{
            background: "var(--accent-muted)",
            borderBottom: "1px solid var(--border-color)",
          }}
        >
          <div className="flex items-center gap-2">
            <span
              className="font-mono text-xs uppercase tracking-widest"
              style={{ color: "var(--text-muted)" }}
            >
              sell
            </span>
            <span
              className="font-mono text-sm font-bold"
              style={{ color: "var(--accent)" }}
            >
              {Math.round(scores.selling_score)}
            </span>
          </div>
          <div
            className="w-px h-3"
            style={{ background: "var(--border-color)" }}
          />
          <div className="flex items-center gap-2">
            <span
              className="font-mono text-xs uppercase tracking-widest"
              style={{ color: "var(--text-muted)" }}
            >
              act
            </span>
            <span
              className="font-mono text-sm font-bold"
              style={{ color: "var(--text-primary)" }}
            >
              {Math.round(scores.acting_score)}
            </span>
          </div>
          <div
            className="w-px h-3"
            style={{ background: "var(--border-color)" }}
          />
          <div className="flex items-center gap-2">
            <span
              className="font-mono text-xs uppercase tracking-widest"
              style={{ color: "var(--text-muted)" }}
            >
              legal
            </span>
            <span
              className="font-mono text-sm font-bold"
              style={{ color: "#28c840" }}
            >
              {Math.round(scores.legal_accuracy)}
            </span>
          </div>
        </div>
      )}

      {/* ── Messages Area ─────────────────────────────────── */}
      <div
        className="flex-1 overflow-y-auto px-4 py-4 sm:px-5 sm:py-5"
        style={{
          background:
            "radial-gradient(ellipse at top, var(--accent-muted), transparent 60%)",
        }}
      >
        <div className="space-y-3">
          <AnimatePresence initial={false}>
            {sanitizedMessages.map((msg, index) => {
              const isMine = msg.sender_role === myRole;
              const previousRound =
                index > 0 ? sanitizedMessages[index - 1]?.round : null;
              const timeStr = formatMessageTime(msg.timestamp);

              return (
                <div key={msg.id}>
                  {/* Round separator */}
                  {(index === 0 || previousRound !== msg.round) && (
                    <div className="flex items-center gap-3 my-4">
                      <div
                        className="flex-1 h-px"
                        style={{ background: "var(--border-color)" }}
                      />
                      <span
                        className="font-mono text-xs uppercase tracking-wider px-3 py-1 rounded-full"
                        style={{
                          color: "var(--accent)",
                          background: "var(--accent-muted)",
                          border: "1px solid var(--border-color)",
                        }}
                      >
                        round {msg.round}
                      </span>
                      <div
                        className="flex-1 h-px"
                        style={{ background: "var(--border-color)" }}
                      />
                    </div>
                  )}

                  {/* Message bubble */}
                  <motion.div
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.25, ease: "easeOut" }}
                    className={`flex ${isMine ? "justify-end" : "justify-start"}`}
                  >
                    <div
                      className="max-w-[78%] group"
                      style={{
                        borderRadius: isMine
                          ? "14px 14px 4px 14px"
                          : "14px 14px 14px 4px",
                        padding: "10px 14px",
                        background: isMine
                          ? "var(--accent)"
                          : "var(--bg-tertiary)",
                        border: isMine
                          ? "none"
                          : "1px solid var(--border-color)",
                        color: isMine ? "#fff" : "var(--text-primary)",
                      }}
                    >
                      {/* Sender label + time */}
                      <div className="flex items-center justify-between gap-3 mb-1">
                        <span
                          className="font-mono text-xs uppercase tracking-widest font-semibold"
                          style={{
                            color: isMine
                              ? "rgba(255,255,255,0.65)"
                              : "var(--text-muted)",
                          }}
                        >
                          {msg.sender_role === "seller" ? myRole === "seller" ? "you" : oppLabel.toLowerCase() : myRole === "client" ? "you" : oppLabel.toLowerCase()}
                        </span>
                        {timeStr && (
                          <span
                            className="font-mono text-xs"
                            style={{
                              color: isMine
                                ? "rgba(255,255,255,0.4)"
                                : "var(--text-muted)",
                            }}
                          >
                            {timeStr}
                          </span>
                        )}
                      </div>
                      <p
                        className="text-sm leading-relaxed"
                        style={{
                          color: isMine ? "#fff" : "var(--text-primary)",
                        }}
                      >
                        {msg.text}
                      </p>
                    </div>
                  </motion.div>
                </div>
              );
            })}
          </AnimatePresence>

          {/* Typing indicator */}
          <AnimatePresence>
            {opponentStatus === "typing" && <TypingDots />}
          </AnimatePresence>
        </div>
        <div ref={endRef} />
      </div>

      {/* ── Terminal Input Area ────────────────────────────── */}
      <div
        className="shrink-0"
        style={{
          borderTop: "1px solid var(--border-color)",
          background: "var(--bg-secondary)",
        }}
      >
        <div className="flex items-end gap-2 p-3 sm:p-4">
          {/* $ prompt prefix */}
          <span
            className="font-mono text-sm font-bold shrink-0 pb-[14px]"
            style={{ color: isFocused ? "var(--accent)" : "var(--text-muted)" }}
          >
            $
          </span>

          {/* Text input */}
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
                  ? "waiting..."
                  : myRole === "seller"
                    ? "type your response as manager..."
                    : "respond as client..."
              }
              disabled={disabled}
              rows={1}
              className="w-full min-h-[44px] max-h-28 resize-none bg-transparent font-mono text-sm outline-none"
              style={{
                color: "var(--text-primary)",
                caretColor: "var(--accent)",
              }}
            />
          </div>

          {/* Send button */}
          <motion.button
            onClick={onSend}
            disabled={disabled || !input.trim()}
            aria-label="Отправить сообщение"
            className="shrink-0 flex items-center justify-center rounded-lg transition-colors"
            style={{
              width: 40,
              height: 40,
              background:
                disabled || !input.trim()
                  ? "var(--bg-tertiary)"
                  : "var(--accent)",
              color:
                disabled || !input.trim()
                  ? "var(--text-muted)"
                  : "#fff",
              cursor:
                disabled || !input.trim()
                  ? "not-allowed"
                  : "pointer",
            }}
            whileTap={
              disabled || !input.trim() ? {} : { scale: 0.92 }
            }
            whileHover={
              disabled || !input.trim()
                ? {}
                : { boxShadow: "0 0 16px var(--accent-glow)" }
            }
          >
            <Send size={15} />
          </motion.button>
        </div>

        {/* Character counter */}
        {charCount > 0 && (
          <div
            className="px-4 pb-2 flex items-center justify-between"
          >
            <span
              className="font-mono text-xs"
              style={{ color: "var(--text-muted)" }}
            >
              {isFocused ? "enter to send / shift+enter for newline" : ""}
            </span>
            <span
              className="font-mono text-xs"
              style={{
                color: charWarning ? "var(--danger)" : "var(--text-muted)",
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
