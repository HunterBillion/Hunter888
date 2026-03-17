"use client";

import type { RecordingState, MicrophonePermissionState } from "@/types";

interface MicrophoneButtonProps {
  recordingState: RecordingState;
  permissionState: MicrophonePermissionState;
  audioLevel: number;
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
        : "Push to Transmit";

  const ringScale = isRecording ? 1 + (audioLevel / 100) * 0.4 : 1;
  const ringOpacity = isRecording ? 0.15 + (audioLevel / 100) * 0.35 : 0;

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative flex items-center justify-center">
        {/* Audio level ring — crystal purple */}
        <div
          className="absolute h-16 w-16 rounded-full bg-vh-purple transition-transform duration-75"
          style={{
            transform: `scale(${ringScale})`,
            opacity: ringOpacity,
          }}
        />

        {/* Pulse animation when recording */}
        {isRecording && (
          <div className="absolute h-14 w-14 animate-ping rounded-full bg-vh-purple opacity-20" />
        )}

        {/* Main button — crystal mic style */}
        <button
          onClick={onToggle}
          disabled={disabled || isProcessing || isDenied}
          className={`relative z-10 flex h-14 w-14 items-center justify-center rounded-full transition-all duration-200 ${
            isRecording
              ? "bg-vh-purple text-white shadow-lg shadow-vh-purple/30 hover:bg-vh-darkPurple"
              : isProcessing
                ? "bg-gray-700 text-gray-400 cursor-wait"
                : isDenied
                  ? "bg-gray-800 text-gray-600 cursor-not-allowed"
                  : "bg-white/5 border border-white/20 text-gray-400 hover:bg-vh-purple/20 hover:text-vh-purple hover:border-vh-purple/40"
          } disabled:opacity-60`}
          title={statusText}
        >
          {isProcessing ? (
            <svg className="h-6 w-6 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          ) : isRecording ? (
            <svg className="h-6 w-6" fill="currentColor" viewBox="0 0 24 24">
              <rect x="6" y="6" width="12" height="12" rx="2" />
            </svg>
          ) : (
            <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z" />
            </svg>
          )}
        </button>
      </div>

      <span
        className={`text-xs font-medium ${
          isRecording
            ? "text-vh-purple"
            : isProcessing
              ? "text-gray-500"
              : isDenied
                ? "text-vh-red"
                : "text-gray-500"
        }`}
      >
        {statusText}
      </span>
    </div>
  );
}
