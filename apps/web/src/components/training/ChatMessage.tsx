"use client";

import { motion } from "framer-motion";
import { type EmotionState, EMOTION_MAP, type ChatBubble } from "@/types";
import { sanitizeText } from "@/lib/sanitize";

function emotionColors(emotion: EmotionState) {
  const e = EMOTION_MAP[emotion] || EMOTION_MAP.cold;
  return {
    text: e.color,
    bg: e.color + "1A", // 10% opacity hex
    border: e.color + "33", // 20% opacity hex
  };
}

const KEYWORDS = [
  "ROI", "рентабельность", "контракт", "договор", "цена", "стоимость",
  "бюджет", "скидка", "условия", "предложение", "выгода", "прибыль",
  "инвестиция", "окупаемость", "результат", "гарантия",
];

function highlightKeywords(text: string): React.ReactNode[] {
  // Sanitize before rendering to prevent XSS
  const safe = sanitizeText(text);
  const regex = new RegExp(`(${KEYWORDS.join("|")})`, "gi");
  const parts = safe.split(regex);
  return parts.map((part, i) => {
    if (KEYWORDS.some((kw) => kw.toLowerCase() === part.toLowerCase())) {
      return (
        <span key={i} className="kw-highlight">
          {part}
        </span>
      );
    }
    return part;
  });
}

interface ChatMessageProps {
  message: ChatBubble;
}

export default function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === "user";
  const ec = message.emotion ? emotionColors(message.emotion) : null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={`flex flex-col ${isUser ? "items-end" : "items-start"} w-full`}
    >
      <span
        className="font-mono text-[10px] mb-1 tracking-wider"
        style={{
          color: isUser ? "var(--accent)" : (ec?.text || "var(--text-muted)"),
        }}
      >
        {isUser ? "YOU" : "AI-CLIENT"}
        <span className="ml-2 opacity-50">
          [{new Date(message.timestamp).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}]
        </span>
      </span>

      <div
        className={`max-w-[85%] rounded-xl p-3 text-sm leading-relaxed ${
          isUser ? "rounded-tr-none" : "rounded-tl-none"
        }`}
        style={{
          background: isUser ? "var(--accent-muted)" : (ec?.bg || "var(--input-bg)"),
          border: `1px solid ${isUser ? "var(--border-hover)" : (ec?.border || "var(--border-color)")}`,
          color: "var(--text-primary)",
        }}
      >
        {highlightKeywords(message.content)}
      </div>

      {message.emotion && (
        <span
          className="mt-1 rounded-full px-2 py-0.5 font-mono text-[9px] uppercase tracking-wider"
          style={{
            background: ec?.bg,
            color: ec?.text,
            border: `1px solid ${ec?.border}`,
          }}
        >
          {EMOTION_MAP[message.emotion]?.label || message.emotion}
        </span>
      )}
    </motion.div>
  );
}
