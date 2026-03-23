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

  return (
    <div
      className="flex h-full flex-col overflow-hidden rounded-[28px] border"
      style={{
        borderColor: "var(--glass-border)",
        background: "linear-gradient(180deg, rgba(18,18,30,0.86), rgba(8,8,16,0.98))",
      }}
    >
      <div
        className="flex items-center justify-between border-b px-5 py-4"
        style={{
          borderColor: "rgba(255,255,255,0.06)",
          background: "linear-gradient(90deg, rgba(144,92,237,0.12), rgba(0,255,148,0.08))",
        }}
      >
        <div>
          <div className="text-[11px] font-mono uppercase tracking-[0.22em]" style={{ color: "rgba(255,255,255,0.72)" }}>
            Pyramid Link
          </div>
          <div className="mt-1 text-sm font-medium text-white">Тактический чат арены</div>
        </div>
        <div
          className="rounded-full px-3 py-1 text-[11px] font-mono uppercase tracking-[0.18em]"
          style={{ background: "rgba(255,255,255,0.08)", color: "rgba(255,255,255,0.72)" }}
        >
          {myRole === "seller" ? "Роль: менеджер" : "Роль: клиент"}
        </div>
      </div>

      <div className="pvp-pyramid-grid flex-1 overflow-y-auto p-4 sm:p-6">
        <div className="space-y-4">
          {sanitizedMessages.map((msg, index) => {
            const isMine = msg.sender_role === myRole;
            const previousRound = index > 0 ? sanitizedMessages[index - 1]?.round : null;

            return (
              <div key={msg.id}>
                {(index === 0 || previousRound !== msg.round) && (
                  <div className="flex justify-center">
                    <div
                      className="rounded-full px-3 py-1 text-[10px] font-mono uppercase tracking-[0.22em]"
                      style={{ background: "rgba(255,255,255,0.06)", color: "rgba(255,255,255,0.66)" }}
                    >
                      Раунд {msg.round}
                    </div>
                  </div>
                )}

                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  className={`mt-3 flex ${isMine ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={`pvp-message-pyramid max-w-[82%] px-5 py-4 ${isMine ? "pvp-message-pyramid--mine" : ""}`}
                    style={{
                      background: isMine
                        ? "linear-gradient(180deg, rgba(144,92,237,0.4), rgba(90,50,160,0.22))"
                        : "linear-gradient(180deg, rgba(42,52,74,0.7), rgba(18,26,41,0.48))",
                      border: `1px solid ${isMine ? "rgba(191,85,236,0.6)" : "rgba(125,211,252,0.28)"}`,
                      boxShadow: isMine ? "0 0 24px rgba(144,92,237,0.22)" : "0 0 20px rgba(125,211,252,0.1)",
                    }}
                  >
                    <div className="mb-2 text-[9px] font-mono uppercase tracking-[0.2em]" style={{ color: "rgba(255,255,255,0.56)" }}>
                      {msg.sender_role === "seller" ? "Менеджер" : "Клиент"}
                    </div>
                    <p className="text-sm leading-6" style={{ color: "#F5F7FB" }}>
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

      <div
        className="flex gap-2 border-t p-4 sm:p-5"
        style={{ borderColor: "rgba(255,255,255,0.06)", background: "rgba(5,8,18,0.88)" }}
      >
        <textarea
          value={input}
          onChange={(e) => onInputChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={disabled ? "Ожидание..." : myRole === "seller" ? "Ваш ответ как менеджер..." : "Ответьте как клиент..."}
          disabled={disabled}
          rows={1}
          className="vh-input flex-1 min-h-[48px] max-h-28 resize-none"
          style={{ background: "rgba(255,255,255,0.05)", color: "#F5F7FB" }}
        />
        <motion.button
          onClick={onSend}
          disabled={disabled || !input.trim()}
          className="shrink-0 flex h-[48px] w-[48px] items-center justify-center rounded-2xl text-white"
          style={{ background: "linear-gradient(180deg, #9E6AF4, #6B39D1)", opacity: disabled || !input.trim() ? 0.4 : 1 }}
          whileTap={{ scale: 0.95 }}
        >
          <Send size={16} />
        </motion.button>
      </div>
    </div>
  );
}
