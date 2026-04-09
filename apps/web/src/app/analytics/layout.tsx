import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Аналитика | X Hunter",
  description: "Детальная аналитика навыков",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
