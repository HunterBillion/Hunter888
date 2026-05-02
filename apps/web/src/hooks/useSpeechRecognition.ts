"use client";

import { useCallback, useEffect, useRef, useState } from "react";

// Web Speech API types (not in all TS libs)
interface SpeechRecognitionEvent extends Event {
  results: SpeechRecognitionResultList;
  resultIndex: number;
}

interface SpeechRecognitionErrorEvent extends Event {
  error: string;
  message: string;
}

interface SpeechRecognitionInstance extends EventTarget {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  onstart: (() => void) | null;
  onaudiostart: (() => void) | null;
  onspeechstart: (() => void) | null;
}

declare global {
  interface Window {
    SpeechRecognition: new () => SpeechRecognitionInstance;
    webkitSpeechRecognition: new () => SpeechRecognitionInstance;
  }
}

export type SpeechStatus = "idle" | "listening" | "processing" | "error" | "unsupported";

// Web Speech API error codes we want to map for the UI. Anything outside
// this set falls into "unknown" so <MicStatusBanner> can still render a
// generic message instead of crashing on a missing key.
export type SpeechErrorCode =
  | "not-allowed"
  | "audio-capture"
  | "network"
  | "service-not-allowed"
  | "language-not-supported"
  | "bad-grammar"
  | "start-failed"
  | "unsupported"
  | "unknown";

const KNOWN_SPEECH_ERROR_CODES: ReadonlySet<string> = new Set([
  "not-allowed",
  "audio-capture",
  "network",
  "service-not-allowed",
  "language-not-supported",
  "bad-grammar",
  "start-failed",
  "unsupported",
]);

interface UseSpeechRecognitionOptions {
  lang?: string;
  onResult?: (text: string) => void;
  onInterim?: (text: string) => void;
  onError?: (error: string) => void;
}

interface UseSpeechRecognitionReturn {
  status: SpeechStatus;
  errorCode: SpeechErrorCode | null;
  isSupported: boolean;
  interimText: string;
  startListening: () => void;
  stopListening: () => void;
  audioLevel: number;
}

export function useSpeechRecognition(
  options: UseSpeechRecognitionOptions = {},
): UseSpeechRecognitionReturn {
  const { lang = "ru-RU" } = options;
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const [status, setStatus] = useState<SpeechStatus>("idle");
  const [errorCode, setErrorCode] = useState<SpeechErrorCode | null>(null);
  const [interimText, setInterimText] = useState("");
  const [audioLevel, setAudioLevel] = useState(0);

  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const contextRef = useRef<AudioContext | null>(null);
  const animRef = useRef(0);
  const isListeningRef = useRef(false);

  const isSupported = typeof window !== "undefined" && !!(window.SpeechRecognition || window.webkitSpeechRecognition);

  // Audio level monitoring (for visual feedback on CrystalMic)
  const startAudioMonitor = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      });
      streamRef.current = stream;
      const ctx = new AudioContext();
      contextRef.current = ctx;
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.8;
      source.connect(analyser);
      analyserRef.current = analyser;

      const monitor = () => {
        if (!analyserRef.current) return;
        const data = new Uint8Array(analyserRef.current.frequencyBinCount);
        analyserRef.current.getByteFrequencyData(data);
        const avg = data.reduce((s, v) => s + v, 0) / data.length;
        setAudioLevel(Math.min(100, Math.round((avg / 255) * 100 * 2)));
        if (isListeningRef.current) {
          animRef.current = requestAnimationFrame(monitor);
        }
      };
      animRef.current = requestAnimationFrame(monitor);
    } catch {
      // Audio monitoring is non-critical
    }
  }, []);

  const stopAudioMonitor = useCallback(() => {
    cancelAnimationFrame(animRef.current);
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    contextRef.current?.close().catch(() => {});
    contextRef.current = null;
    analyserRef.current = null;
    setAudioLevel(0);
  }, []);

  const startListening = useCallback(() => {
    if (!isSupported) {
      setStatus("unsupported");
      setErrorCode("unsupported");
      optionsRef.current.onError?.("unsupported");
      return;
    }
    setErrorCode(null);

    const SpeechRecognitionClass = window.SpeechRecognition || window.webkitSpeechRecognition;
    const recognition = new SpeechRecognitionClass();

    recognition.lang = lang;
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
      setStatus("listening");
      isListeningRef.current = true;
    };

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      let interim = "";
      let final = "";

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          final += transcript;
        } else {
          interim += transcript;
        }
      }

      if (interim) {
        setInterimText(interim);
        optionsRef.current.onInterim?.(interim);
      }

      if (final) {
        setInterimText("");
        optionsRef.current.onResult?.(final.trim());
      }
    };

    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      if (event.error === "no-speech") return; // Ignore no-speech — user just hasn't spoken yet
      if (event.error === "aborted") return; // Ignore manual abort

      setStatus("error");
      const code = (KNOWN_SPEECH_ERROR_CODES.has(event.error)
        ? event.error
        : "unknown") as SpeechErrorCode;
      setErrorCode(code);
      optionsRef.current.onError?.(event.error);

      // Permission denied or hardware capture failed — both are
      // unrecoverable on the same recognition instance. Stop the
      // auto-restart loop so we don't hot-loop on InvalidStateError.
      if (event.error === "not-allowed" || event.error === "audio-capture") {
        isListeningRef.current = false;
        stopAudioMonitor();
      }
    };

    recognition.onend = () => {
      // Auto-restart if still in listening mode (continuous mode may stop unexpectedly)
      if (isListeningRef.current) {
        try {
          recognition.start();
        } catch {
          setStatus("idle");
          isListeningRef.current = false;
          stopAudioMonitor();
        }
      } else {
        setStatus("idle");
        stopAudioMonitor();
      }
    };

    recognitionRef.current = recognition;

    try {
      recognition.start();
      startAudioMonitor();
    } catch {
      setStatus("error");
      setErrorCode("start-failed");
      isListeningRef.current = false;
      stopAudioMonitor();
      optionsRef.current.onError?.("start-failed");
    }
  }, [isSupported, lang, startAudioMonitor, stopAudioMonitor]);

  const stopListening = useCallback(() => {
    // Pilot symptom #2 — микрофон оставался активным после конца сессии,
    // браузер продолжал показывать индикатор в трее. Корни было два:
    //   а) ``recognition.stop()`` — это "graceful" stop, он ждёт онэнд
    //      и только потом отпускает внутренний mic-stream Web Speech API.
    //      На практике в Chrome tray-icon висит 1-3 секунды. ``abort()``
    //      освобождает немедленно.
    //   б) если юзер стартовал recognition ДО getUserMedia (например,
    //      разрешения ещё не выданы), то ``streamRef`` мог остаться в
    //      null, но Web Speech API свой внутренний поток всё равно
    //      открыл — его закрывает только abort/stop на recognition.
    // Плюс явный порядок: сначала выключаем auto-restart флаг, потом
    // abort, потом analyzer-stream tracks через stopAudioMonitor.
    isListeningRef.current = false;
    setInterimText("");

    if (recognitionRef.current) {
      try {
        recognitionRef.current.abort();
      } catch {
        // Already aborted / detached — nothing to clean on this side.
      }
      recognitionRef.current = null;
    }

    // Belt-and-braces: even if stopAudioMonitor already runs on unmount,
    // calling it here ensures the analyser stream/audio-context/anim
    // loop are released synchronously before the caller navigates away.
    stopAudioMonitor();
    setStatus("idle");
  }, [stopAudioMonitor]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      isListeningRef.current = false;
      if (recognitionRef.current) {
        try { recognitionRef.current.abort(); } catch { /* noop */ }
      }
      cancelAnimationFrame(animRef.current);
      streamRef.current?.getTracks().forEach((t) => t.stop());
      contextRef.current?.close().catch(() => {});
    };
  }, []);

  return {
    status,
    errorCode,
    isSupported,
    interimText,
    startListening,
    stopListening,
    audioLevel,
  };
}
