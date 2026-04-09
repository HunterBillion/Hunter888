import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Уведомления | X Hunter",
  description: "Уведомления и оповещения",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
