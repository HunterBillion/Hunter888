import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "История | X Hunter",
  description: "История тренировочных сессий",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
