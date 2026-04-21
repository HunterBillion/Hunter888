"use client";

import { ThemeProvider as NextThemesProvider } from "next-themes";
import { NotificationWSProvider } from "@/providers/NotificationWSProvider";

// Suppress THREE.js console noise (Clock deprecation + Color CSS var parsing)
if (typeof window !== "undefined") {
  const _origWarn = console.warn;
  console.warn = (...args: unknown[]) => {
    if (typeof args[0] === "string" && (args[0].includes("THREE.Clock") || args[0].includes("THREE.Color"))) return;
    _origWarn.apply(console, args);
  };
  // Suppress THREE.js WebGL context lost error (handled gracefully via fallback UI)
  const _origError = console.error;
  console.error = (...args: unknown[]) => {
    if (typeof args[0] === "string" && args[0].includes("THREE.WebGLRenderer: Context Lost")) return;
    _origError.apply(console, args);
  };
}

/**
 * Root providers wrapper.
 * Zustand stores don't need providers — they're global.
 * This wraps theme + WS notification connection.
 */
export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme="dark"
      enableSystem={false}
    >
      <NotificationWSProvider>
        {children}
      </NotificationWSProvider>
    </NextThemesProvider>
  );
}
