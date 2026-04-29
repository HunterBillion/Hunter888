import type { Metadata, Viewport } from "next";
import { headers } from "next/headers";
import { Geist, Geist_Mono, VT323, Pixelify_Sans } from "next/font/google";
import { ViewTransitions } from "next-view-transitions";
import { Providers } from "@/components/providers/Providers";
import "./globals.css";

const geistSans = Geist({
  subsets: ["latin", "cyrillic"],
  variable: "--font-geist-sans",
  display: "swap",
});

const geistMono = Geist_Mono({
  subsets: ["latin", "cyrillic"],
  variable: "--font-geist-mono",
  display: "swap",
});

const vt323 = VT323({
  weight: "400",
  subsets: ["latin", "latin-ext", "vietnamese"],
  variable: "--font-vt323",
  display: "swap",
});

// 2026-04-29: Pixelify Sans добавлен как Cyrillic-fallback для font-pixel.
// VT323 (наш основной pixel-шрифт) не поддерживает кириллицу, поэтому
// русский текст в .font-pixel падал на Geist Mono. Pixelify Sans поддерживает
// subset "cyrillic" — браузер автоматически подберёт глиф из этого шрифта,
// если VT323 не содержит запрашиваемый символ. Цепочка задана в pixel-ui.css.
const pixelifySans = Pixelify_Sans({
  weight: ["400", "500", "600", "700"],
  subsets: ["latin", "cyrillic"],
  variable: "--font-pixelify",
  display: "swap",
});

// G5: OG/Twitter meta tags
export const metadata: Metadata = {
  title: "X Hunter — Neural Sales Training",
  description: "AI-платформа обучения менеджеров по продажам через диалоговые симуляции с нейросетевыми клиентами",
  icons: {
    icon: "/icon-192.png",
    apple: "/icon-512.png",
  },
  // G1: PWA manifest
  manifest: "/manifest.json",
  // G5: Open Graph
  openGraph: {
    title: "X Hunter — Neural Sales Training",
    description: "AI-тренажёр продаж. Реалистичные клиенты, мгновенный фидбек, 5-слойный скоринг.",
    type: "website",
    siteName: "X Hunter",
    locale: "ru_RU",
  },
  // G5: Twitter
  twitter: {
    card: "summary_large_image",
    title: "X Hunter — Neural Sales Training",
    description: "AI-тренажёр продаж. Реалистичные клиенты, мгновенный фидбек.",
  },
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "X Hunter",
  },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "var(--bg-primary)" },
    { media: "(prefers-color-scheme: light)", color: "#fafafa" },
  ],
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
};

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // Read the per-request nonce set by middleware.ts for CSP.
  const nonce = (await headers()).get("x-nonce") ?? "";

  return (
    <html lang="ru" suppressHydrationWarning data-scroll-behavior="smooth">
      <head>
        {/* CSP nonce — available to client scripts via document.querySelector */}
        <meta property="csp-nonce" content={nonce} />
        {/* Fonts loaded via next/font/google (Geist Sans + Geist Mono) */}
        {/* View Transition CSS for smooth page navigation */}
        <style nonce={nonce} suppressHydrationWarning>{`
          ::view-transition-old(root) {
            animation: fade-out 0.15s ease-in;
          }
          ::view-transition-new(root) {
            animation: fade-in 0.15s ease-out;
          }
          @keyframes fade-out { from { opacity: 1; } to { opacity: 0; } }
          @keyframes fade-in { from { opacity: 0; } to { opacity: 1; } }
        `}</style>
      </head>
      <body className={`${geistSans.variable} ${geistMono.variable} ${vt323.variable} ${pixelifySans.variable} min-h-screen antialiased`}>
        <ViewTransitions>
          <Providers>
            {children}
          </Providers>
        </ViewTransitions>
      </body>
    </html>
  );
}
