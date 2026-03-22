"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { logger } from "@/lib/logger";
import type { MicrophonePermissionState, RecordingState } from "@/types";

const NOISE_GATE_THRESHOLD = 30; // dB threshold
const SILENCE_TIMEOUT_MS = 30_000; // 30 seconds auto-stop
const TIMESLICE_MS = 250; // chunk interval
const ANALYSER_FFT_SIZE = 256;

interface UseMicrophoneOptions {
  onChunk?: (chunk: Blob) => void;
  onSilenceTimeout?: () => void;
}

interface UseMicrophoneReturn {
  recordingState: RecordingState;
  permissionState: MicrophonePermissionState;
  audioLevel: number; // 0-100 scale for visual indicator
  isSupported: boolean;
  startRecording: () => Promise<boolean>;
  stopRecording: () => Blob | null;
  requestPermission: () => Promise<boolean>;
}

export function useMicrophone(
  options: UseMicrophoneOptions = {},
): UseMicrophoneReturn {
  const [recordingState, setRecordingState] = useState<RecordingState>("idle");
  const [permissionState, setPermissionState] =
    useState<MicrophonePermissionState>("prompt");
  const [audioLevel, setAudioLevel] = useState(0);
  const isSupported =
    typeof window !== "undefined" &&
    typeof navigator !== "undefined" &&
    !!navigator.mediaDevices?.getUserMedia &&
    typeof MediaRecorder !== "undefined";

  const optionsRef = useRef(options);
  optionsRef.current = options;

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const animFrameRef = useRef<number>(0);
  const silenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSoundTimeRef = useRef<number>(Date.now());

  // Check permission state on mount
  useEffect(() => {
    if (typeof navigator === "undefined" || !navigator.permissions) return;

    navigator.permissions
      .query({ name: "microphone" as PermissionName })
      .then((status) => {
        setPermissionState(
          status.state === "granted"
            ? "granted"
            : status.state === "denied"
              ? "denied"
              : "prompt",
        );
        status.onchange = () => {
          setPermissionState(
            status.state === "granted"
              ? "granted"
              : status.state === "denied"
                ? "denied"
                : "prompt",
          );
        };
      })
      .catch(() => {
        // permissions API not supported, leave as prompt
      });
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      cancelAnimationFrame(animFrameRef.current);
      if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
      }
      if (audioContextRef.current) {
        audioContextRef.current.close().catch(() => {});
      }
    };
  }, []);

  const computeAudioLevel = useCallback(() => {
    const analyser = analyserRef.current;
    if (!analyser) return;

    const dataArray = new Uint8Array(analyser.frequencyBinCount);
    analyser.getByteFrequencyData(dataArray);

    // Compute RMS-like value from frequency data
    let sum = 0;
    for (let i = 0; i < dataArray.length; i++) {
      sum += dataArray[i];
    }
    const avg = sum / dataArray.length;

    // Convert to 0-100 scale (byte values are 0-255)
    const level = Math.min(100, Math.round((avg / 255) * 100 * 2));
    setAudioLevel(level);

    // Compute dB for noise gate
    const rms =
      Math.sqrt(
        dataArray.reduce((s, v) => s + (v / 255) * (v / 255), 0) /
          dataArray.length,
      ) || 0.0001;
    const dB = 20 * Math.log10(rms);

    return { level, dB };
  }, []);

  const monitorAudio = useCallback(() => {
    const result = computeAudioLevel();
    if (result && result.dB >= -((100 - NOISE_GATE_THRESHOLD) / 100) * 50) {
      lastSoundTimeRef.current = Date.now();
    }

    // Check silence timeout
    const silenceDuration = Date.now() - lastSoundTimeRef.current;
    if (silenceDuration >= SILENCE_TIMEOUT_MS) {
      optionsRef.current.onSilenceTimeout?.();
      return; // Stop monitoring
    }

    animFrameRef.current = requestAnimationFrame(monitorAudio);
  }, [computeAudioLevel]);

  const requestPermission = useCallback(async (): Promise<boolean> => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((t) => t.stop());
      setPermissionState("granted");
      return true;
    } catch (err) {
      logger.error("Microphone permission denied:", err);
      if (
        err instanceof DOMException &&
        (err.name === "NotAllowedError" || err.name === "PermissionDeniedError")
      ) {
        setPermissionState("denied");
      } else {
        setPermissionState("error");
      }
      return false;
    }
  }, []);

  const startRecording = useCallback(async () => {
    if (!isSupported) {
      setPermissionState("error");
      return false;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      streamRef.current = stream;
      setPermissionState("granted");

      // Set up AnalyserNode for audio level monitoring
      const audioContext = new AudioContext();
      audioContextRef.current = audioContext;
      const source = audioContext.createMediaStreamSource(stream);
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = ANALYSER_FFT_SIZE;
      analyser.smoothingTimeConstant = 0.8;
      source.connect(analyser);
      analyserRef.current = analyser;

      // Set up MediaRecorder
      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm";

      const mediaRecorder = new MediaRecorder(stream, { mimeType });

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          // Check noise gate: only forward chunks above threshold
          const result = computeAudioLevel();
          const aboveGate =
            !result ||
            result.dB >= -((100 - NOISE_GATE_THRESHOLD) / 100) * 50;

          chunksRef.current.push(event.data);

          if (aboveGate) {
            optionsRef.current.onChunk?.(event.data);
          }
        }
      };

      mediaRecorder.onerror = () => {
        setRecordingState("idle");
      };

      chunksRef.current = [];
      mediaRecorder.start(TIMESLICE_MS);
      mediaRecorderRef.current = mediaRecorder;
      lastSoundTimeRef.current = Date.now();
      setRecordingState("recording");

      // Start audio monitoring loop
      animFrameRef.current = requestAnimationFrame(monitorAudio);
      return true;
    } catch (err) {
      logger.error("Failed to start recording:", err);
      if (
        err instanceof DOMException &&
        (err.name === "NotAllowedError" || err.name === "PermissionDeniedError")
      ) {
        setPermissionState("denied");
      } else {
        setPermissionState("error");
      }
      setRecordingState("idle");
      return false;
    }
  }, [computeAudioLevel, isSupported, monitorAudio]);

  const stopRecording = useCallback((): Blob | null => {
    cancelAnimationFrame(animFrameRef.current);
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }

    const mediaRecorder = mediaRecorderRef.current;
    if (!mediaRecorder || mediaRecorder.state === "inactive") {
      setRecordingState("idle");
      setAudioLevel(0);
      return null;
    }

    mediaRecorder.stop();
    mediaRecorderRef.current = null;

    // Stop all tracks
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }

    // Close audio context
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }
    analyserRef.current = null;

    setRecordingState("processing");
    setAudioLevel(0);

    const blob = new Blob(chunksRef.current, { type: "audio/webm" });
    chunksRef.current = [];

    // Reset to idle after a moment (caller can set to processing longer if needed)
    setTimeout(() => setRecordingState("idle"), 100);

    return blob;
  }, []);

  return {
    recordingState,
    permissionState,
    audioLevel,
    isSupported,
    startRecording,
    stopRecording,
    requestPermission,
  };
}
