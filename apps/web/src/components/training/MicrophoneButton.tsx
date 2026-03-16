"use client";

import type { RecordingState, MicrophonePermissionState } from "@/types";

interface MicrophoneButtonProps {
  recordingState: RecordingState;
  permissionState: MicrophonePermissionState;
  audioLevel: number; // 0-100
  onToggle: () => void;
  disabled?: boolean;
}

export default function MicrophoneButton({
  recordingState,
  permissionState,
  audioLevel,
  onToggle,
  disabled = false,
}: MicrophoneButtonProps) {
  const isRecording = recordingState === "recording";
  const isProcessing = recordingState === "processing";
  const isDenied = permissionState === "denied";

  const statusText = isDenied
    ? "Микрофон заблокирован"
    : isProcessing
      ? "Обработка..."
      : isRecording
        ? "Говорите..."
        : "Нажмите для записи";

  // Audio level ring: maps 0-100 to ring scale
  const ringScale = isRecording ? 1 + (audioLevel / 100) * 0.4 : 1;
  const ringOpacity = isRecording ? 0.15 + (audioLevel / 100) * 0.35 : 0;

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative flex items-center justify-center">
        {/* Audio level ring */}
        <div
          className="absolute h-16 w-16 rounded-full bg-red-500 transition-transform duration-75"
          style={{
            transform: `scale(${ringScale})`,
            opacity: ringOpacity,
          }}
        />

        {/* Pulse animation when recording */}
        {isRecording && (
          <div className="absolute h-14 w-14 animate-ping rounded-full bg-red-400 opacity-20" />
        )}

        {/* Main button */}
        <button
          onClick={onToggle}
          disabled={disabled || isProcessing || isDenied}
          className={`relative z-10 flex h-14 w-14 items-center justify-center rounded-full transition-all duration-200 ${
            isRecording
              ? "bg-red-600 text-white shadow-lg shadow-red-200 hover:bg-red-700"
              : isProcessing
                ? "bg-gray-400 text-white cursor-wait"
                : isDenied
                  ? "bg-gray-300 text-gray-500 cursor-not-allowed"
                  : "bg-gray-100 text-gray-700 hover:bg-gray-200 shadow-sm"
          } disabled:opacity-60`}
          title={statusText}
        >
          {isProcessing ? (
            <svg
              className="h-6 w-6 animate-spin"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
              />
            </svg>
          ) : isRecording ? (
            /* Stop icon (square) */
            <svg
              className="h-6 w-6"
              fill="currentColor"
              viewBox="0 0 24 24"
            >
              <rect x="6" y="6" width="12" height="12" rx="2" />
            </svg>
          ) : (
            /* Microphone icon */
            <svg
              className="h-6 w-6"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth="1.5"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z"
              />
            </svg>
          )}
        </button>
      </div>

      <span
        className={`text-xs font-medium ${
          isRecording
            ? "text-red-600"
            : isProcessing
              ? "text-gray-500"
              : isDenied
                ? "text-red-500"
                : "text-gray-500"
        }`}
      >
        {statusText}
      </span>
    </div>
  );
}
