/**
 * Real-time audio analyser using Web Audio API.
 * Replaces the fake sine-wave simulation in useTTS.
 * Returns actual RMS audio level from an HTMLAudioElement.
 */

import { useCallback, useEffect, useRef, useState } from "react";

interface AudioAnalyserState {
  audioLevel: number;       // 0-1, real RMS level
  isSpeaking: boolean;      // Above threshold = speaking
  frequencyData: Uint8Array | null;
}

interface UseAudioAnalyserOptions {
  fftSize?: number;         // Default 256
  smoothing?: number;       // 0-1, default 0.8
  threshold?: number;       // 0-1, below = silence. Default 0.05
}

export function useAudioAnalyser(options: UseAudioAnalyserOptions = {}) {
  const { fftSize = 256, smoothing = 0.8, threshold = 0.05 } = options;

  const [state, setState] = useState<AudioAnalyserState>({
    audioLevel: 0,
    isSpeaking: false,
    frequencyData: null,
  });

  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const sourceRef = useRef<MediaElementAudioSourceNode | null>(null);
  const animFrameRef = useRef<number>(0);
  const connectedElementRef = useRef<HTMLAudioElement | null>(null);

  const connectToAudio = useCallback(
    (audioElement: HTMLAudioElement) => {
      // Don't reconnect same element
      if (connectedElementRef.current === audioElement) return;

      // Cleanup previous connection
      disconnect();

      try {
        const ctx = audioContextRef.current || new AudioContext();
        audioContextRef.current = ctx;

        if (ctx.state === "suspended") {
          ctx.resume();
        }

        const source = ctx.createMediaElementSource(audioElement);
        const analyser = ctx.createAnalyser();
        analyser.fftSize = fftSize;
        analyser.smoothingTimeConstant = smoothing;

        source.connect(analyser);
        analyser.connect(ctx.destination); // Still play through speakers

        sourceRef.current = source;
        analyserRef.current = analyser;
        connectedElementRef.current = audioElement;

        // Start analysis loop
        const dataArray = new Uint8Array(analyser.frequencyBinCount);

        const analyze = () => {
          if (!analyserRef.current) return;
          analyserRef.current.getByteFrequencyData(dataArray);

          // Calculate RMS
          let sum = 0;
          for (let i = 0; i < dataArray.length; i++) {
            const normalized = dataArray[i] / 255;
            sum += normalized * normalized;
          }
          const rms = Math.sqrt(sum / dataArray.length);
          const level = Math.min(1, rms * 2.5); // Boost for sensitivity

          setState({
            audioLevel: level,
            isSpeaking: level > threshold,
            frequencyData: new Uint8Array(dataArray),
          });

          animFrameRef.current = requestAnimationFrame(analyze);
        };

        animFrameRef.current = requestAnimationFrame(analyze);
      } catch (e) {
        // Web Audio API not supported or already connected
        console.warn("[useAudioAnalyser] Failed to connect:", e);
      }
    },
    [fftSize, smoothing, threshold]
  );

  const disconnect = useCallback(() => {
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = 0;
    }
    // Don't close AudioContext — it can't be reused after closing
    // Just disconnect nodes
    if (sourceRef.current) {
      try {
        sourceRef.current.disconnect();
      } catch {
        // Already disconnected
      }
      sourceRef.current = null;
    }
    if (analyserRef.current) {
      try {
        analyserRef.current.disconnect();
      } catch {
        // Already disconnected
      }
      analyserRef.current = null;
    }
    connectedElementRef.current = null;
    setState({ audioLevel: 0, isSpeaking: false, frequencyData: null });
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      disconnect();
      if (audioContextRef.current && audioContextRef.current.state !== "closed") {
        audioContextRef.current.close();
      }
    };
  }, [disconnect]);

  return {
    ...state,
    connectToAudio,
    disconnect,
  };
}
