"use client";

import { useEffect, useRef, useMemo } from "react";
import { motion } from "framer-motion";
import { Send } from "lucide-react";

/**
 * Defense-in-depth text sanitizer for PvP chat messages.
 * React JSX auto-escapes, but since messages come from other users via WS,
 * we strip any embedded HTML/script tags and limit length as extra protection.
 */
const MAX_MESSAGE_LENGTH = 2000;
function sanitizeMessageText(text: string): string {
  if (!text || typeof text !== "string") return "";
  // Strip HTML tags (defense-in-depth — React doesn't render them, but belt-and-suspenders)
  const stripped = text.replace(/<[^>]*>/g, "");
  // Truncate excessively long messages
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

interface Message {
  id: string;
  sender_role: "seller" | "client";
  text: string;
  round: number;
  timestamp: string;
}

interface Props {
  messages: Message[];
  myRole: "seller" | "client";
  input: string;
  onInputChange: (value: string) => void;
  onSend: () => void;
  disabled?: boolean;
}

export function DuelChat({ messages, myRole, input, onInputChange, onSend, disabled }: Props) {
  const endRef = useRef<HTMLDivElement>(null);

  // Pre-sanitize all messages (memoized to avoid re-processing on every render)
  const sanitizedMessages = useMemo(
    () => messages.map((msg) => ({ ...msg, text: sanitizeMessageText(msg.text) })),
    [messages],
  );

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

  return (
    <div
      className="flex h-full flex-col overflow-hidden rounded-[28px] border"
      style={{
        borderColor: "var(--glass-border)",
        background: "linear-gradient(180deg, rgba(18,18,30,0.86), rgba(8,8,16,0.98))",
      }}
    >
      {/* Header — player roles */}
      <div
        className="flex items-center justify-between border-b px-5 py-3"
        style={{
          borderColor: "rgba(255,255,255,0.06)",
          background: "linear-gradient(90deg, rgba(99,102,241,0.12), rgba(0,255,148,0.08))",
        }}
      >
        <div className="flex items-center gap-2">
          <div
            className="h-2 w-2 rounded-full"
            style={{ background: myRole === "seller" ? "var(--accent)" : "var(--info)" }}
          />
          <span className="text-xs font-mono uppercase tracking-wider" style={{ color: "var(--text-secondary)" }}>
            {myRole === "seller" ? "Вы: Менеджер" : "Вы: Клиент"}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
            {myRole === "seller" ? "Оппонент: Клиент" : "Оппонент: Менеджер"}
          </span>
          <div
            className="h-2 w-2 rounded-full"
            style={{ background: myRole === "seller" ? "var(--info)" : "var(--accent)" }}
          />
        </div>
      </div>

      {/* Messages area */}
      <div className="pvp-pyramid-grid flex-1 overflow-y-auto p-4 sm:p-6">
        <div className="space-y-3">
          {sanitizedMessages.map((msg, index) => {
            const isMine = msg.sender_role === myRole;
            const previousRound = index > 0 ? sanitizedMessages[index - 1]?.round : null;
            const timeStr = formatMessageTime(msg.timestamp);

            return (
              <div key={msg.id}>
                {(index === 0 || previousRound !== msg.round) && (
                  <div className="flex justify-center my-3">
                    <div
                      className="rounded-full px-4 py-1.5 text-xs font-mono uppercase tracking-widest"
                      style={{ background: "rgba(99,102,241,0.1)", color: "var(--accent)", border: "1px solid rgba(99,102,241,0.2)" }}
                    >
                      Раунд {msg.round}
                    </div>
                  </div>
                )}

                <motion.div
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.2 }}
                  className={`flex ${isMine ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className="max-w-[82%] px-4 py-3"
                    style={{
                      borderRadius: isMine ? "16px 16px 4px 16px" : "16px 16px 16px 4px",
                      background: isMine
                        ? "linear-gradient(135deg, rgba(99,102,241,0.3), rgba(55,48,163,0.18))"
                        : "linear-gradient(135deg, rgba(42,52,74,0.6), rgba(18,26,41,0.4))",
                      borderLeft: isMine ? "none" : "3px solid rgba(125,211,252,0.4)",
                      borderRight: isMine ? "3px solid rgba(139,92,246,0.5)" : "none",
                      backdropFilter: "blur(8px)",
                    }}
                  >
                    <div className="flex items-center justify-between gap-3 mb-1.5">
                      <span className="text-xs font-mono uppercase tracking-wider" style={{
                        color: isMine ? "rgba(139,92,246,0.8)" : "rgba(125,211,252,0.7)",
                      }}>
                        {msg.sender_role === "seller" ? "Менеджер" : "Клиент"}
                      </span>
                      {timeStr && (
                        <span className="text-xs font-mono" style={{ color: "rgba(255,255,255,0.3)" }}>
                          {timeStr}
                        </span>
                      )}
                    </div>
                    <p className="text-sm leading-relaxed" style={{ color: "#F5F7FB" }}>
                      {msg.text}
                    </p>
                  </div>
                </motion.div>
              </div>
            );
          })}
        </div>
        <div ref={endRef} />
      </div>

      {/* Input area */}
      <div
        className="border-t p-4 sm:p-5"
        style={{ borderColor: "rgba(255,255,255,0.06)", background: "rgba(5,8,18,0.88)" }}
      >
        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={(e) => {
              if (e.target.value.length <= MAX_MESSAGE_LENGTH) {
                onInputChange(e.target.value);
              }
            }}
            onKeyDown={handleKeyDown}
            placeholder={disabled ? "Ожидание..." : myRole === "seller" ? "Ваш ответ как менеджер..." : "Ответьте как клиент..."}
            disabled={disabled}
            rows={1}
            className="glow-input flex-1 min-h-[48px] max-h-28 resize-none"
          />
          <motion.button
            onClick={onSend}
            disabled={disabled || !input.trim()}
            aria-label="Отправить сообщение"
            className="btn-neon shrink-0 flex h-[48px] w-[48px] items-center justify-center rounded-2xl text-white"
            style={{ opacity: disabled || !input.trim() ? 0.4 : 1 }}
            whileTap={{ scale: 0.95 }}
          >
            <Send size={16} />
          </motion.button>
        </div>
        {/* Character counter */}
        {charCount > 0 && (
          <div className="mt-1.5 text-right">
            <span
              className="text-xs font-mono"
              style={{ color: charWarning ? "var(--neon-red)" : "var(--text-muted)" }}
            >
              {charCount}/{MAX_MESSAGE_LENGTH}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
