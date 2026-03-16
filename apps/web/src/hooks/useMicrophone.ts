"use client";

import { useCallback, useRef, useState } from "react";

/**
 * Hook for capturing microphone audio.
 * Full implementation with audio streaming will be added in Phase 1, Week 4.
 */
export function useMicrophone() {
  const [isRecording, setIsRecording] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const startRecording = useCallback(
    async (onChunk?: (chunk: Blob) => void) => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const mediaRecorder = new MediaRecorder(stream, {
          mimeType: "audio/webm;codecs=opus",
        });

        mediaRecorder.ondataavailable = (event) => {
          if (event.data.size > 0) {
            chunksRef.current.push(event.data);
            onChunk?.(event.data);
          }
        };

        mediaRecorder.start(250); // 250ms chunks for streaming
        mediaRecorderRef.current = mediaRecorder;
        setIsRecording(true);
      } catch (err) {
        console.error("Failed to start recording:", err);
      }
    },
    [],
  );

  const stopRecording = useCallback((): Blob | null => {
    const mediaRecorder = mediaRecorderRef.current;
    if (!mediaRecorder) return null;

    mediaRecorder.stop();
    mediaRecorder.stream.getTracks().forEach((track) => track.stop());
    mediaRecorderRef.current = null;
    setIsRecording(false);

    const blob = new Blob(chunksRef.current, { type: "audio/webm" });
    chunksRef.current = [];
    return blob;
  }, []);

  return { isRecording, startRecording, stopRecording };
}
