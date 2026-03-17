import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "VibeHunter — Neural Sales Environment",
  description: "AI-платформа обучения менеджеров через диалоговые симуляции",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ru" className="dark">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=Rajdhani:wght@300;400;500;600;700&family=JetBrains+Mono:wght@300;400;500;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="min-h-screen bg-vh-black text-white antialiased">
        {/* Scanline overlay */}
        <div className="pointer-events-none fixed inset-0 z-50 overflow-hidden opacity-[0.03]">
          <div className="absolute inset-x-0 h-[2px] animate-scanline bg-vh-purple" />
        </div>
        {children}
      </body>
    </html>
  );
}
