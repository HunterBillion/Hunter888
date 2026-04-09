import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Тренировка | X Hunter",
  description: "Выбор сценария и начало тренировки с ИИ-клиентом",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
