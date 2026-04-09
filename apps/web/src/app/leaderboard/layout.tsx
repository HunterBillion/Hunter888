import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Лидерборд | X Hunter",
  description: "Рейтинг лучших менеджеров",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
