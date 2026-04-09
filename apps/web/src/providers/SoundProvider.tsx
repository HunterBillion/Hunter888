"use client";

import {
  createContext,
  useCallback,
  useContext,
  useRef,
  type ReactNode,
} from "react";
import type { SoundName } from "@/hooks/useSound";
import { useSound } from "@/hooks/useSound";

interface SoundContextValue {
  play: (name: SoundName) => void;
}

const SoundContext = createContext<SoundContextValue>({
  play: () => {},
});

/**
 * SoundProvider — wraps the app to provide a global `play` function.
 *
 * Handles the browser AudioContext "user gesture" requirement by
 * lazily initializing the AudioContext on the first user interaction.
 * All sound calls before the first gesture are silently ignored.
 */
export function SoundProvider({ children }: { children: ReactNode }) {
  const { playSound } = useSound();
  const gestureRef = useRef(false);
  const ctxRef = useRef<AudioContext | null>(null);

  // Ensure AudioContext is created/resumed on the first user gesture
  const ensureContext = useCallback(() => {
    if (gestureRef.current) return;
    gestureRef.current = true;

    try {
      if (!ctxRef.current) {
        ctxRef.current = new AudioContext();
      }
      if (ctxRef.current.state === "suspended") {
        ctxRef.current.resume().catch(() => {});
      }
    } catch {
      // AudioContext unavailable — sounds will degrade silently
    }
  }, []);

  const play = useCallback(
    (name: SoundName) => {
      ensureContext();
      playSound(name);
    },
    [ensureContext, playSound],
  );

  return (
    <SoundContext.Provider value={{ play }}>
      <div
        onClickCapture={ensureContext}
        onKeyDownCapture={ensureContext}
        onTouchStartCapture={ensureContext}
        style={{ display: "contents" }}
      >
        {children}
      </div>
    </SoundContext.Provider>
  );
}

/** Access the global sound player from any component */
export function useSoundContext() {
  return useContext(SoundContext);
}
