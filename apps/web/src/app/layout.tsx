import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Тренажер Продаж",
  description: "Платформа для обучения менеджеров через AI-аватаров",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ru">
      <body className="min-h-screen bg-gray-50 text-gray-900 antialiased">
        {children}
      </body>
    </html>
  );
}
