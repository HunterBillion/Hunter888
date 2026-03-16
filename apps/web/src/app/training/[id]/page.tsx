"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useMicrophone } from "@/hooks/useMicrophone";
import ChatMessage from "@/components/training/ChatMessage";
import MicrophoneButton from "@/components/training/MicrophoneButton";
import TranscriptionIndicator from "@/components/training/TranscriptionIndicator";
import EmotionIndicator from "@/components/training/EmotionIndicator";
import type {
  ChatBubble,
  EmotionState,
  SessionState,
  TranscriptionState,
} from "@/types";

export default function TrainingSessionPage() {
  const params = useParams();
  const router = useRouter();
  const sessionId = params.id as string;

  // Chat state
  const [messages, setMessages] = useState<ChatBubble[]>([]);
  const [input, setInput] = useState("");
  const [emotion, setEmotion] = useState<EmotionState>("cold");
  const [characterName, setCharacterName] = useState("Клиент");
  const [sessionState, setSessionState] = useState<SessionState>("connecting");
  const [sttAvailable, setSttAvailable] = useState(true);

  // Timer
  const [elapsed, setElapsed] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Transcription
  const [transcription, setTranscription] = useState<TranscriptionState>({
    status: "idle",
    partial: "",
    final: "",
  });

  // Auto-scroll ref
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);

  // Message counter for generating IDs
  const msgCounterRef = useRef(0);

  const nextMsgId = () => {
    msgCounterRef.current += 1;
    return `msg-${msgCounterRef.current}`;
  };

  // WebSocket
  const { sendMessage, connectionState } = useWebSocket({
    onMessage: (data) => {
      switch (data.type) {
        case "session.ready":
          // Server is ready, now start the session
          break;

        case "session.started":
          setSessionState("ready");
          if (data.data.character_name) {
            setCharacterName(data.data.character_name as string);
          }
          if (data.data.initial_emotion) {
            setEmotion(data.data.initial_emotion as EmotionState);
          }
          break;

        case "character.response":
          setMessages((prev) => [
            ...prev,
            {
              id: nextMsgId(),
              role: "assistant",
              content: data.data.content as string,
              emotion: data.data.emotion as EmotionState | undefined,
              timestamp: new Date().toISOString(),
            },
          ]);
          if (data.data.emotion) {
            setEmotion(data.data.emotion as EmotionState);
          }
          break;

        case "session.ended":
          setSessionState("completed");
          if (timerRef.current) clearInterval(timerRef.current);
          // Navigate to results after a brief delay
          setTimeout(() => {
            router.push(`/results/${sessionId}`);
          }, 1500);
          break;

        case "transcription.result": {
          const text = data.data.text as string;
          const isEmpty = data.data.is_empty as boolean;

          if (isEmpty || !text) {
            setTranscription({ status: "idle", partial: "", final: "" });
          } else {
            setTranscription({
              status: "done",
              partial: "",
              final: text,
            });
            // Add the transcribed text as a user message in the chat
            setMessages((prev) => [
              ...prev,
              {
                id: nextMsgId(),
                role: "user",
                content: text,
                timestamp: new Date().toISOString(),
              },
            ]);
          }
          break;
        }

        case "stt.unavailable":
          setSttAvailable(false);
          if (mic.recordingState === "recording") {
            mic.stopRecording();
          }
          break;

        case "emotion.update":
          if (data.data.current) {
            setEmotion(data.data.current as EmotionState);
          }
          break;

        case "session.timeout":
          setSessionState("completed");
          if (timerRef.current) clearInterval(timerRef.current);
          break;

        case "error":
          console.error("Training error:", data.data.message);
          break;
      }
    },
  });

  // Microphone
  const micRef = useRef<ReturnType<typeof useMicrophone> | null>(null);

  const onSilenceTimeout = useCallback(() => {
    micRef.current?.stopRecording();
  }, []);

  const mic = useMicrophone({
    onChunk: (chunk) => {
      // Convert blob to base64 and send via WebSocket
      const reader = new FileReader();
      reader.onloadend = () => {
        const result = reader.result as string;
        // Strip the data URL prefix (e.g. "data:audio/webm;base64,")
        const base64 = result.includes(",") ? result.split(",")[1] : result;
        sendMessage({
          type: "audio.chunk",
          data: { audio: base64 },
        });
      };
      reader.readAsDataURL(chunk);
    },
    onSilenceTimeout,
  });

  // Keep micRef in sync
  micRef.current = mic;

  // Start session when connected
  useEffect(() => {
    if (connectionState === "connected" && sessionState === "connecting") {
      sendMessage({
        type: "session.start",
        data: { session_id: sessionId },
      });
    }
  }, [connectionState, sessionState, sessionId, sendMessage]);

  // Session state derived from connection
  useEffect(() => {
    if (connectionState === "connected" && sessionState === "connecting") {
      // Wait for session.ready from server
    } else if (
      connectionState === "disconnected" &&
      sessionState !== "completed"
    ) {
      setSessionState("connecting");
    }
  }, [connectionState, sessionState]);

  // Timer
  useEffect(() => {
    if (sessionState === "ready") {
      timerRef.current = setInterval(() => {
        setElapsed((prev) => prev + 1);
      }, 1000);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [sessionState]);

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, transcription]);

  // Format timer
  const formatTime = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  };

  // Handlers
  const handleSend = () => {
    const text = input.trim();
    if (!text || sessionState !== "ready") return;

    setMessages((prev) => [
      ...prev,
      {
        id: nextMsgId(),
        role: "user",
        content: text,
        timestamp: new Date().toISOString(),
      },
    ]);
    sendMessage({ type: "text.message", data: { content: text } });
    setInput("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleEnd = () => {
    sendMessage({ type: "session.end", data: {} });
  };

  const handleMicToggle = () => {
    if (mic.recordingState === "recording") {
      mic.stopRecording();
      sendMessage({ type: "audio.end", data: {} });
    } else {
      mic.startRecording();
    }
  };

  // Session state indicator
  const sessionStateLabel: Record<SessionState, string> = {
    connecting: "Подключение...",
    ready: "Готов",
    completed: "Завершено",
  };

  const sessionStateColor: Record<SessionState, string> = {
    connecting: "text-yellow-600",
    ready: "text-green-600",
    completed: "text-gray-500",
  };

  return (
    <div className="flex h-screen flex-col bg-gray-50">
      {/* Top bar */}
      <header className="flex items-center justify-between border-b border-gray-200 bg-white px-4 py-2.5 sm:px-6 xl:px-8">
        <div className="flex items-center gap-3">
          <div>
            <h1 className="text-sm font-semibold text-gray-900 sm:text-base xl:text-lg">
              {characterName}
            </h1>
            <span
              className={`text-xs font-medium ${sessionStateColor[sessionState]}`}
            >
              {sessionStateLabel[sessionState]}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-3 sm:gap-4">
          <EmotionIndicator emotion={emotion} />

          <div className="hidden items-center gap-1.5 rounded-md bg-gray-100 px-3 py-1.5 sm:flex">
            <svg
              className="h-4 w-4 text-gray-500"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth="1.5"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            <span className="text-sm font-mono text-gray-700">
              {formatTime(elapsed)}
            </span>
          </div>

          <button
            onClick={handleEnd}
            disabled={sessionState !== "ready"}
            className="rounded-md bg-red-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-600 disabled:opacity-50 sm:px-4 sm:text-sm xl:px-5 xl:py-2"
          >
            Завершить
          </button>
        </div>
      </header>

      {/* Chat area */}
      <div
        ref={chatContainerRef}
        className="flex-1 overflow-y-auto px-4 py-4 sm:px-6 xl:px-8"
      >
        <div className="mx-auto max-w-2xl space-y-3 xl:max-w-3xl">
          {!sttAvailable && sessionState === "ready" && (
            <div className="flex items-center gap-2 rounded-lg border border-yellow-300 bg-yellow-50 px-4 py-2.5 text-sm text-yellow-800">
              <svg className="h-5 w-5 shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
              </svg>
              Распознавание речи недоступно. Используйте текстовый ввод.
            </div>
          )}

          {messages.length === 0 && sessionState === "ready" && (
            <div className="py-12 text-center text-sm text-gray-400">
              Начните диалог, отправив сообщение{sttAvailable ? " или используя микрофон" : ""}
            </div>
          )}

          {messages.length === 0 && sessionState === "connecting" && (
            <div className="flex flex-col items-center justify-center py-12">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-gray-300 border-t-blue-600" />
              <span className="mt-3 text-sm text-gray-500">
                Подключение к сессии...
              </span>
            </div>
          )}

          {messages.map((msg) => (
            <ChatMessage key={msg.id} message={msg} />
          ))}

          {/* Transcription indicator */}
          {transcription.status !== "idle" && (
            <TranscriptionIndicator state={transcription} />
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Bottom input area */}
      <div className="border-t border-gray-200 bg-white px-4 py-3 sm:px-6 xl:px-8">
        <div className="mx-auto flex max-w-2xl items-end gap-3 xl:max-w-3xl">
          {/* Microphone button */}
          <MicrophoneButton
            recordingState={mic.recordingState}
            permissionState={mic.permissionState}
            audioLevel={mic.audioLevel}
            onToggle={handleMicToggle}
            disabled={sessionState !== "ready" || !sttAvailable}
          />

          {/* Text input */}
          <div className="flex flex-1 items-end gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                sessionState === "ready"
                  ? "Введите сообщение..."
                  : "Ожидание подключения..."
              }
              disabled={sessionState !== "ready"}
              rows={1}
              className="max-h-32 min-h-[40px] flex-1 resize-none rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:bg-gray-50 disabled:text-gray-400"
              style={{
                height: "auto",
                minHeight: "40px",
              }}
              onInput={(e) => {
                const target = e.target as HTMLTextAreaElement;
                target.style.height = "auto";
                target.style.height =
                  Math.min(target.scrollHeight, 128) + "px";
              }}
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || sessionState !== "ready"}
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
            >
              <svg
                className="h-5 w-5"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth="1.5"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5"
                />
              </svg>
            </button>
          </div>
        </div>
      </div>

      {/* Completed overlay */}
      {sessionState === "completed" && (
        <div className="absolute inset-0 z-50 flex items-center justify-center bg-black/30">
          <div className="rounded-xl bg-white px-8 py-6 text-center shadow-xl">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-green-100">
              <svg
                className="h-6 w-6 text-green-600"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth="2"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M4.5 12.75l6 6 9-13.5"
                />
              </svg>
            </div>
            <h2 className="mt-3 text-lg font-semibold text-gray-900">
              Тренировка завершена
            </h2>
            <p className="mt-1 text-sm text-gray-500">
              Переход к результатам...
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
