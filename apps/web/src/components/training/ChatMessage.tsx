"use client";

import { motion } from "framer-motion";
import { type EmotionState, EMOTION_MAP, type ChatBubble } from "@/types";
import { sanitizeText } from "@/lib/sanitize";

function emotionColors(emotion: EmotionState) {
  const e = EMOTION_MAP[emotion] || EMOTION_MAP.cold;
  return {
    text: e.color,
    bg: e.color + "22", // 13% opacity — slightly more visible
    border: e.color + "44", // 27% opacity
    glow: e.color + "18", // 9% for subtle glow
  };
}

const KEYWORDS = [
  "ROI", "рентабельность", "контракт", "договор", "цена", "стоимость",
  "бюджет", "скидка", "условия", "предложение", "выгода", "прибыль",
  "инвестиция", "окупаемость", "результат", "гарантия",
  // Bankruptcy-specific (127-ФЗ)
  "банкротство", "должник", "кредитор", "арбитражный", "реструктуризация",
  "списание", "задолженность", "приставы", "взыскание", "127-ФЗ",
];

function highlightKeywords(text: string): React.ReactNode[] {
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
  showEmotion?: boolean;
}

export default function ChatMessage({ message, showEmotion = true }: ChatMessageProps) {
  const isUser = message.role === "user";
  const ec = message.emotion ? emotionColors(message.emotion) : null;
  const isFallback = message.is_fallback;

  return (
    <motion.div
      initial={{ opacity: 0, y: 6, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
      className={`flex flex-col ${isUser ? "items-end" : "items-start"} w-full group`}
    >
      {/* Role + timestamp header */}
      <span
        className="font-mono text-xs mb-1.5 tracking-wide select-none flex items-center gap-2"
        style={{
          color: isUser ? "var(--accent)" : (ec?.text || "var(--text-secondary)"),
        }}
      >
        {isUser ? "ВЫ" : "КЛИЕНТ"}
        {/* Emotion dot indicator */}
        {!isUser && message.emotion && (
          <span
            className={`emotion-dot emotion-dot--${message.emotion}`}
            style={{ width: 7, height: 7 }}
          />
        )}
        <span className="opacity-50 group-hover:opacity-80 transition-opacity text-xs">
          {new Date(message.timestamp).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}
        </span>
      </span>

      {/* Message bubble */}
      <div
        className={`
          max-w-[88%] rounded-2xl px-4 py-3
          text-[15px] leading-relaxed
          break-words hyphens-auto
          ${isUser ? "rounded-tr-md" : "rounded-tl-md"}
          ${isFallback ? "opacity-70 italic" : ""}
          transition-shadow duration-300
        `}
        style={{
          background: isUser
            ? "var(--accent-muted)"
            : (ec?.bg || "var(--input-bg)"),
          border: `1px solid ${isUser
            ? "var(--border-hover)"
            : (ec?.border || "var(--border-color)")}`,
          color: "var(--text-primary)",
          boxShadow: !isUser && ec
            ? `0 2px 16px ${ec.glow}`
            : undefined,
        }}
      >
        {highlightKeywords(message.content)}
      </div>

      {/* Emotion badge */}
      {showEmotion && message.emotion && !isUser && (
        <motion.span
          initial={{ opacity: 0, scale: 0.85 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.1 }}
          className="mt-0.5 rounded-full px-2 py-0.5 font-mono text-xs uppercase tracking-wider select-none"
          style={{
            background: ec?.bg,
            color: ec?.text,
            border: `1px solid ${ec?.border}`,
          }}
        >
          {EMOTION_MAP[message.emotion]?.label || message.emotion}
        </motion.span>
      )}
    </motion.div>
  );
}
