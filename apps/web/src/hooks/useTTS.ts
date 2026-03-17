"use client";

import { useCallback, useEffect, useRef, useState } from "react";

interface UseTTSOptions {
  lang?: string;
  rate?: number;
  pitch?: number;
}

interface UseTTSReturn {
  speak: (text: string) => void;
  stop: () => void;
  speaking: boolean;
  enabled: boolean;
  setEnabled: (v: boolean) => void;
  supported: boolean;
}

export function useTTS(options: UseTTSOptions = {}): UseTTSReturn {
  const { lang = "ru-RU", rate = 1.0, pitch = 1.0 } = options;
  const [speaking, setSpeaking] = useState(false);
  const [enabled, setEnabled] = useState(true);
  const [supported, setSupported] = useState(false);
  const voiceRef = useRef<SpeechSynthesisVoice | null>(null);

  useEffect(() => {
    if (typeof window === "undefined" || !window.speechSynthesis) {
      setSupported(false);
      return;
    }
    setSupported(true);

    const pickVoice = () => {
      const voices = window.speechSynthesis.getVoices();
      // Prefer Russian voices
      const ruVoice =
        voices.find((v) => v.lang.startsWith("ru") && v.localService) ||
        voices.find((v) => v.lang.startsWith("ru")) ||
        voices[0];
      voiceRef.current = ruVoice || null;
    };

    pickVoice();
    window.speechSynthesis.onvoiceschanged = pickVoice;

    return () => {
      window.speechSynthesis.cancel();
    };
  }, []);

  const speak = useCallback(
    (text: string) => {
      if (!enabled || !supported || !text.trim()) return;

      // Cancel any ongoing speech
      window.speechSynthesis.cancel();

      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = lang;
      utterance.rate = rate;
      utterance.pitch = pitch;
      if (voiceRef.current) {
        utterance.voice = voiceRef.current;
      }

      utterance.onstart = () => setSpeaking(true);
      utterance.onend = () => setSpeaking(false);
      utterance.onerror = () => setSpeaking(false);

      window.speechSynthesis.speak(utterance);
    },
    [enabled, supported, lang, rate, pitch],
  );

  const stop = useCallback(() => {
    if (supported) {
      window.speechSynthesis.cancel();
      setSpeaking(false);
    }
  }, [supported]);

  return { speak, stop, speaking, enabled, setEnabled, supported };
}
