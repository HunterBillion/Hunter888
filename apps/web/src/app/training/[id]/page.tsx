"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useWebSocket } from "@/hooks/useWebSocket";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  emotion?: string;
}

export default function TrainingSessionPage() {
  const params = useParams();
  const router = useRouter();
  const sessionId = params.id as string;
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [emotion, setEmotion] = useState("cold");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const { sendMessage, isConnected } = useWebSocket({
    onMessage: (data) => {
      if (data.type === "character.response") {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: data.data.content, emotion: data.data.emotion },
        ]);
        if (data.data.emotion) setEmotion(data.data.emotion);
      }
      if (data.type === "session.ended") {
        router.push(`/results/${sessionId}`);
      }
    },
  });

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (isConnected) {
      sendMessage({ type: "session.start", data: { session_id: sessionId } });
    }
  }, [isConnected, sessionId, sendMessage]);

  const handleSend = () => {
    if (!input.trim()) return;
    setMessages((prev) => [...prev, { role: "user", content: input }]);
    sendMessage({ type: "text.message", data: { content: input } });
    setInput("");
  };

  const handleEnd = () => {
    sendMessage({ type: "session.end", data: {} });
  };

  const emotionColors: Record<string, string> = {
    cold: "bg-blue-100 text-blue-800",
    warming: "bg-yellow-100 text-yellow-800",
    open: "bg-green-100 text-green-800",
  };

  return (
    <div className="flex h-screen flex-col">
      {/* Header */}
      <header className="flex items-center justify-between border-b bg-white px-6 py-3">
        <h1 className="text-lg font-semibold">Тренировка</h1>
        <div className="flex items-center gap-4">
          <span className={`rounded-full px-3 py-1 text-xs font-medium ${emotionColors[emotion] || emotionColors.cold}`}>
            {emotion === "cold" ? "Холодный" : emotion === "warming" ? "Теплеет" : "Открыт"}
          </span>
          <button
            onClick={handleEnd}
            className="rounded-md bg-red-500 px-4 py-1.5 text-sm text-white hover:bg-red-600"
          >
            Завершить
          </button>
        </div>
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        <div className="mx-auto max-w-2xl space-y-4">
          {messages.map((msg, i) => (
            <div
              key={i}
              className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[80%] rounded-lg px-4 py-2 ${
                  msg.role === "user"
                    ? "bg-primary-600 text-white"
                    : "bg-gray-100 text-gray-900"
                }`}
              >
                {msg.content}
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input */}
      <div className="border-t bg-white px-6 py-4">
        <div className="mx-auto flex max-w-2xl gap-3">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            placeholder="Введите сообщение..."
            className="flex-1 rounded-md border border-gray-300 px-4 py-2 focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim()}
            className="rounded-md bg-primary-600 px-6 py-2 text-white hover:bg-primary-700 disabled:opacity-50"
          >
            Отправить
          </button>
        </div>
      </div>
    </div>
  );
}
