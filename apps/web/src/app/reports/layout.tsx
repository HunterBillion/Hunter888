import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Отчёты | X Hunter",
  description: "Отчёты по работе команды",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
