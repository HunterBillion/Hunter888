import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Центр | X Hunter",
  description: "Главная панель — тренировки, рекомендации, прогресс",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
