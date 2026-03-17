"use client";

import { useState } from "react";
import type { ChatBubble, EmotionState } from "@/types";
import EmotionIndicator from "./EmotionIndicator";

interface ChatMessageProps {
  message: ChatBubble;
}

export default function ChatMessage({ message }: ChatMessageProps) {
  const [showTimestamp, setShowTimestamp] = useState(false);
  const isUser = message.role === "user";

  const formattedTime = (() => {
    try {
      const date = new Date(message.timestamp);
      return date.toLocaleTimeString("ru-RU", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
    } catch {
      return "";
    }
  })();

  return (
    <div
      className={`flex ${isUser ? "justify-end" : "justify-start"}`}
      onMouseEnter={() => setShowTimestamp(true)}
      onMouseLeave={() => setShowTimestamp(false)}
    >
      <div
        className={`relative max-w-[80%] ${isUser ? "order-2" : "order-1"}`}
      >
        {/* Avatar for AI */}
        {!isUser && (
          <div className="mb-1 flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-full bg-vh-purple/20 border border-vh-purple/30 text-xs font-bold text-vh-purple">
              AI
            </div>
            {message.emotion && (
              <EmotionIndicator
                emotion={message.emotion as EmotionState}
              />
            )}
          </div>
        )}

        {/* Message bubble */}
        <div
          className={`rounded-2xl px-4 py-2.5 ${
            isUser
              ? "rounded-tr-sm bg-vh-purple text-white"
              : "rounded-tl-sm bg-white/5 border border-white/10 text-gray-200"
          }`}
        >
          <p className="whitespace-pre-wrap text-sm leading-relaxed">
            {message.content}
          </p>
        </div>

        {/* Timestamp on hover */}
        <div
          className={`mt-0.5 text-xs text-gray-600 transition-opacity duration-200 ${
            isUser ? "text-right" : "text-left"
          } ${showTimestamp ? "opacity-100" : "opacity-0"}`}
        >
          {formattedTime}
        </div>
      </div>
    </div>
  );
}
