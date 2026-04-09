import type { Metadata, Viewport } from "next";
import { headers } from "next/headers";
import { Geist, Geist_Mono } from "next/font/google";
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
    <html lang="ru" suppressHydrationWarning>
      <head>
        {/* CSP nonce — available to client scripts via document.querySelector */}
        <meta property="csp-nonce" content={nonce} />
        {/* Fonts loaded via next/font/google (Geist Sans + Geist Mono) */}
        {/* Noto Color Emoji for consistent emoji rendering */}
        <link
          href="https://fonts.googleapis.com/css2?family=Noto+Color+Emoji&display=swap"
          rel="stylesheet"
          nonce={nonce}
          suppressHydrationWarning
        />
      </head>
      <body className={`${geistSans.variable} ${geistMono.variable} min-h-screen antialiased`}>
        <Providers>
          {children}
        </Providers>
      </body>
    </html>
  );
}
