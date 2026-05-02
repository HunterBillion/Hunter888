"use client";

import { ThemeProvider as NextThemesProvider } from "next-themes";
import { NotificationWSProvider } from "@/providers/NotificationWSProvider";
import { Toaster } from "@/components/ui/Toaster";

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
        {/*
          Sonner toast surface. Required for any `toast.success/error/...`
          call across the app — without this mount, every toast (autosave
          errors, OAuth unlink failures, validation messages on
          /clients/pipeline + /consent) is silently dropped. The component
          existed at components/ui/Toaster.tsx for months but was never
          rendered. Mount here so it's available on every page.
        */}
        <Toaster />
      </NotificationWSProvider>
    </NextThemesProvider>
  );
}
