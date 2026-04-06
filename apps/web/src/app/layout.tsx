import type { Metadata, Viewport } from "next";
import { headers } from "next/headers";
import { Providers } from "@/components/providers/Providers";
import "./globals.css";

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
    { media: "(prefers-color-scheme: dark)", color: "#050505" },
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
        {/* G2: Preload critical fonts */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          rel="preload"
          href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@300;400;500;700&display=swap"
          as="style"
          nonce={nonce}
          suppressHydrationWarning
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@300;400;500;700&display=swap"
          rel="stylesheet"
          nonce={nonce}
          suppressHydrationWarning
        />
      </head>
      <body className="min-h-screen antialiased">
        <Providers>
          {children}
        </Providers>
      </body>
    </html>
  );
}
