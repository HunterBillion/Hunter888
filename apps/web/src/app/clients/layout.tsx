import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Клиенты | X Hunter",
  description: "Управление клиентской базой",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
