import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Профиль | X Hunter",
  description: "Ваш профиль и достижения",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
