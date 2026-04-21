"use client";

import { useRef, useState } from "react";
import { motion } from "framer-motion";
import { type EmotionState, EMOTION_MAP, type ChatBubble } from "@/types";
import { sanitizeText } from "@/lib/sanitize";
import { MessageActionMenu } from "@/components/training/MessageActionMenu";

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
  /** 2026-04-18: Telegram-style tap → action menu. If omitted, message is read-only. */
  onTogglePin?: () => void;
  /** Called when user picks "Ответить" — caller should quote content in input. */
  onReply?: (content: string) => void;
}

export default function ChatMessage({
  message,
  showEmotion = false,
  onTogglePin,
  onReply,
}: ChatMessageProps) {
  const isUser = message.role === "user";
  const ec = message.emotion ? emotionColors(message.emotion) : null;
  const isFallback = message.is_fallback;

  // 2026-04-18: Telegram-style action menu — tap bubble to open
  const bubbleRef = useRef<HTMLDivElement>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [anchor, setAnchor] = useState<{ x: number; y: number; width: number; height: number } | null>(null);

  const openMenu = () => {
    const el = bubbleRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    setAnchor({ x: rect.left, y: rect.top, width: rect.width, height: rect.height });
    setMenuOpen(true);
  };
  const closeMenu = () => setMenuOpen(false);

  return (
    <motion.div
      id={`msg-${message.id}`}
      initial={{ opacity: 0, y: 6, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
      className={`flex flex-col ${isUser ? "items-end" : "items-start"} w-full group`}
    >
      {/* Role + timestamp header */}
      <span
        className="text-xs font-semibold mb-1.5 tracking-wide uppercase select-none flex items-center gap-2"
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

      {/* Message bubble — 2026-04-18: tap opens Telegram-style action menu */}
      <div
        ref={bubbleRef}
        onClick={onTogglePin ? openMenu : undefined}
        className={`
          max-w-[88%] rounded-2xl px-4 py-3
          text-[15px] leading-relaxed
          break-words hyphens-auto
          ${isUser ? "rounded-tr-md" : "rounded-tl-md"}
          ${isFallback ? "opacity-70 italic" : ""}
          ${message.pinned ? "pinned-bubble" : ""}
          ${onTogglePin ? "cursor-pointer" : ""}
          transition-shadow duration-300
        `}
        style={{
          background: isUser
            ? "var(--accent-muted)"
            : (ec?.bg || "var(--input-bg)"),
          border: `${message.pinned ? 2 : 1}px solid ${message.pinned
            ? "var(--accent)"
            : isUser
              ? "var(--border-hover)"
              : (ec?.border || "var(--border-color)")}`,
          color: "var(--text-primary)",
          boxShadow: message.pinned
            ? "3px 3px 0 0 var(--accent)"
            : !isUser && ec ? `0 2px 16px ${ec.glow}` : undefined,
        }}
      >
        {/*
          2026-04-19 Phase 2.6: inline blockquote when this bubble is a
          quote-reply to an older message. The preview is cached on the
          bubble so we don't have to refetch the quoted content.
        */}
        {message.quotedPreview && (
          <blockquote
            className="mb-2 px-3 py-1.5 text-[13px] opacity-80 italic"
            style={{
              borderLeft: "3px solid var(--accent)",
              background: "rgba(0,0,0,0.12)",
              borderRadius: 6,
            }}
            title={message.quotedMessageId}
          >
            {message.quotedPreview.length > 180
              ? message.quotedPreview.slice(0, 180) + "…"
              : message.quotedPreview}
          </blockquote>
        )}

        {highlightKeywords(message.content)}

        {/*
          2026-04-19 Phase 2.6: media attachment, typically a generated
          image sent by the AI client via the MCP `generate_image` tool.
          Rendered inline beneath the text so the manager sees the visual
          reference alongside what the character said about it.
        */}
        {message.mediaUrl && (
          <div className="mt-2">
            <img
              src={message.mediaUrl}
              alt={message.mediaCaption || "Вложение"}
              loading="lazy"
              className="max-w-full rounded-lg"
              style={{
                maxHeight: 360,
                border: "1px solid var(--border-color)",
                background: "#000",
              }}
            />
            {message.mediaCaption && (
              <div
                className="mt-1 text-xs italic"
                style={{ color: "var(--text-secondary)" }}
              >
                {message.mediaCaption}
              </div>
            )}
          </div>
        )}

        {/* Pin indicator — small corner marker, only visible when pinned */}
        {message.pinned && (
          <span
            aria-hidden
            className="inline-block ml-2 align-middle font-pixel text-[10px] uppercase tracking-wider"
            style={{
              color: "var(--accent)",
              padding: "2px 6px",
              background: "var(--accent-muted)",
              border: "1px solid var(--accent)",
              borderRadius: 0,
            }}
          >
            📌 ЗАКР
          </span>
        )}
      </div>

      {/* Action menu (conditionally rendered when open) */}
      {onTogglePin && (
        <MessageActionMenu
          open={menuOpen}
          anchor={anchor}
          isPinned={!!message.pinned}
          onReply={() => {
            if (onReply) onReply(message.content);
          }}
          onTogglePin={onTogglePin}
          onCopy={() => {
            try {
              navigator.clipboard?.writeText(message.content);
            } catch { /* noop */ }
          }}
          onClose={closeMenu}
        />
      )}

      {/* Emotion badge */}
      {showEmotion && message.emotion && !isUser && (
        <motion.span
          initial={{ opacity: 0, scale: 0.85 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.1 }}
          className="mt-0.5 rounded-full px-2 py-0.5 text-xs font-medium uppercase tracking-wide select-none"
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
