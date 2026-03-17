"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useMicrophone } from "@/hooks/useMicrophone";
import ChatMessage from "@/components/training/ChatMessage";
import MicrophoneButton from "@/components/training/MicrophoneButton";
import TranscriptionIndicator from "@/components/training/TranscriptionIndicator";
import EmotionIndicator from "@/components/training/EmotionIndicator";
import VibeMeter from "@/components/training/VibeMeter";
import ScriptAdherence from "@/components/training/ScriptAdherence";
import TalkListenRatio from "@/components/training/TalkListenRatio";
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

  const [messages, setMessages] = useState<ChatBubble[]>([]);
  const [input, setInput] = useState("");
  const [emotion, setEmotion] = useState<EmotionState>("cold");
  const [characterName, setCharacterName] = useState("Клиент");
  const [sessionState, setSessionState] = useState<SessionState>("connecting");
  const [sttAvailable, setSttAvailable] = useState(true);
  const [isTyping, setIsTyping] = useState(false);
  const [showSilenceModal, setShowSilenceModal] = useState(false);

  // Scores (real-time)
  const [scriptScore, setScriptScore] = useState(0);
  const [talkTime, setTalkTime] = useState(0);
  const [listenTime, setListenTime] = useState(0);

  // Timer
  const [elapsed, setElapsed] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [transcription, setTranscription] = useState<TranscriptionState>({
    status: "idle",
    partial: "",
    final: "",
  });

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);
  const msgCounterRef = useRef(0);

  const nextMsgId = () => {
    msgCounterRef.current += 1;
    return `msg-${msgCounterRef.current}`;
  };

  const { sendMessage, connectionState } = useWebSocket({
    onMessage: (data) => {
      switch (data.type) {
        case "auth.success":
          // Authenticated, wait for session.ready
          break;

        case "session.ready":
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

        case "avatar.typing":
          setIsTyping(data.data.is_typing as boolean);
          break;

        case "character.response":
          setIsTyping(false);
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
          // Update listen time
          setListenTime((prev) => prev + 1);
          break;

        case "session.ended":
          setSessionState("completed");
          if (timerRef.current) clearInterval(timerRef.current);
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
            setTranscription({ status: "done", partial: "", final: text });
            setMessages((prev) => [
              ...prev,
              {
                id: nextMsgId(),
                role: "user",
                content: text,
                timestamp: new Date().toISOString(),
              },
            ]);
            setTalkTime((prev) => prev + 1);
          }
          break;
        }

        case "stt.unavailable":
        case "stt.error":
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

        case "score.update":
          if (data.data.script_score !== undefined) {
            setScriptScore(data.data.script_score as number);
          }
          break;

        case "silence.warning":
          // Avatar already said "Алло?" via character.response
          break;

        case "silence.timeout":
          setShowSilenceModal(true);
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
      const reader = new FileReader();
      reader.onloadend = () => {
        const result = reader.result as string;
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

  useEffect(() => {
    if (connectionState === "disconnected" && sessionState !== "completed") {
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
  }, [messages, transcription, isTyping]);

  const formatTime = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  };

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
    setTalkTime((prev) => prev + 1);
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

  const handleContinueSession = () => {
    setShowSilenceModal(false);
    sendMessage({ type: "silence.continue", data: {} });
  };

  const sessionStateColor: Record<SessionState, string> = {
    connecting: "text-yellow-400",
    ready: "text-vh-green",
    completed: "text-gray-500",
  };

  const sessionStateLabel: Record<SessionState, string> = {
    connecting: "CONNECTING...",
    ready: "LIVE",
    completed: "COMPLETED",
  };

  return (
    <div className="flex h-screen flex-col bg-vh-black">
      {/* Top bar */}
      <header className="flex items-center justify-between border-b border-white/10 bg-vh-black/90 backdrop-blur-sm px-4 py-2.5 sm:px-6">
        <div className="flex items-center gap-4">
          <div>
            <h1 className="text-sm font-display font-bold text-gray-100 sm:text-base tracking-wider">
              {characterName.toUpperCase()}
            </h1>
            <span className={`text-xs font-mono ${sessionStateColor[sessionState]}`}>
              {sessionStateLabel[sessionState]}
            </span>
          </div>
          <VibeMeter emotion={emotion} />
        </div>

        <div className="flex items-center gap-3 sm:gap-4">
          <ScriptAdherence progress={scriptScore} checkpointsHit={0} checkpointsTotal={0} />
          <TalkListenRatio talkPercent={talkTime + listenTime > 0 ? Math.round((talkTime / (talkTime + listenTime)) * 100) : 50} />

          <div className="hidden items-center gap-1.5 rounded-md bg-white/5 border border-white/10 px-3 py-1.5 sm:flex">
            <svg className="h-4 w-4 text-gray-500" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span className="text-sm font-mono text-gray-400">{formatTime(elapsed)}</span>
          </div>

          <button
            onClick={handleEnd}
            disabled={sessionState !== "ready"}
            className="rounded-lg bg-vh-red/20 border border-vh-red/40 px-3 py-1.5 text-xs font-medium text-vh-red hover:bg-vh-red/30 disabled:opacity-50 transition-colors sm:px-4 sm:text-sm"
          >
            Завершить
          </button>
        </div>
      </header>

      {/* Chat area */}
      <div ref={chatContainerRef} className="flex-1 overflow-y-auto px-4 py-4 sm:px-6">
        <div className="mx-auto max-w-2xl space-y-3 xl:max-w-3xl">
          {!sttAvailable && sessionState === "ready" && (
            <div className="flex items-center gap-2 rounded-lg border border-yellow-500/30 bg-yellow-500/10 px-4 py-2.5 text-sm text-yellow-400">
              <svg className="h-5 w-5 shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
              </svg>
              Распознавание речи недоступно. Используйте текстовый ввод.
            </div>
          )}

          {messages.length === 0 && sessionState === "ready" && (
            <div className="py-12 text-center text-sm text-gray-500">
              Начните диалог, отправив сообщение{sttAvailable ? " или используя микрофон" : ""}
            </div>
          )}

          {messages.length === 0 && sessionState === "connecting" && (
            <div className="flex flex-col items-center justify-center py-12">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-gray-700 border-t-vh-purple" />
              <span className="mt-3 text-sm text-gray-500">Подключение к сессии...</span>
            </div>
          )}

          {messages.map((msg) => (
            <ChatMessage key={msg.id} message={msg} />
          ))}

          {/* Typing indicator */}
          {isTyping && (
            <div className="flex items-center gap-2 text-sm text-gray-500">
              <div className="flex gap-1">
                <span className="h-2 w-2 rounded-full bg-vh-purple animate-bounce" style={{ animationDelay: "0ms" }} />
                <span className="h-2 w-2 rounded-full bg-vh-purple animate-bounce" style={{ animationDelay: "150ms" }} />
                <span className="h-2 w-2 rounded-full bg-vh-purple animate-bounce" style={{ animationDelay: "300ms" }} />
              </div>
              <span>{characterName} печатает...</span>
            </div>
          )}

          {transcription.status !== "idle" && (
            <TranscriptionIndicator state={transcription} />
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Bottom input area */}
      <div className="border-t border-white/10 bg-vh-black/90 backdrop-blur-sm px-4 py-3 sm:px-6">
        <div className="mx-auto flex max-w-2xl items-end gap-3 xl:max-w-3xl">
          <MicrophoneButton
            recordingState={mic.recordingState}
            permissionState={mic.permissionState}
            audioLevel={mic.audioLevel}
            onToggle={handleMicToggle}
            disabled={sessionState !== "ready" || !sttAvailable}
          />

          <div className="flex flex-1 items-end gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={sessionState === "ready" ? "Введите сообщение..." : "Ожидание подключения..."}
              disabled={sessionState !== "ready"}
              rows={1}
              className="vh-input max-h-32 min-h-[40px] flex-1 resize-none"
              style={{ height: "auto", minHeight: "40px" }}
              onInput={(e) => {
                const target = e.target as HTMLTextAreaElement;
                target.style.height = "auto";
                target.style.height = Math.min(target.scrollHeight, 128) + "px";
              }}
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || sessionState !== "ready"}
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-vh-purple text-white hover:bg-vh-darkPurple disabled:opacity-50 transition-colors"
            >
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
              </svg>
            </button>
          </div>
        </div>
      </div>

      {/* Completed overlay */}
      {sessionState === "completed" && (
        <div className="absolute inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="glass-panel px-8 py-6 text-center">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-vh-green/20">
              <svg className="h-6 w-6 text-vh-green" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
              </svg>
            </div>
            <h2 className="mt-3 text-lg font-display font-bold text-gray-100">
              ТРЕНИРОВКА ЗАВЕРШЕНА
            </h2>
            <p className="mt-1 text-sm text-gray-500">Переход к результатам...</p>
          </div>
        </div>
      )}

      {/* Silence timeout modal */}
      {showSilenceModal && (
        <div className="absolute inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="glass-panel px-8 py-6 text-center max-w-sm">
            <h2 className="text-lg font-display font-bold text-yellow-400">
              ВЫ ЕЩЁ ЗДЕСЬ?
            </h2>
            <p className="mt-2 text-sm text-gray-400">
              Вы давно молчите. Хотите продолжить тренировку?
            </p>
            <div className="mt-4 flex gap-3 justify-center">
              <button onClick={handleContinueSession} className="vh-btn-primary">
                Продолжить
              </button>
              <button onClick={handleEnd} className="vh-btn-outline">
                Завершить
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
