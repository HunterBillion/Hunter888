"use client";

import { ThemeProvider as NextThemesProvider } from "next-themes";
import { NotificationWSProvider } from "@/providers/NotificationWSProvider";

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
      storageKey="vh-theme"
    >
      <NotificationWSProvider>
        {children}
      </NotificationWSProvider>
    </NextThemesProvider>
  );
}
