import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Арена PvP | X Hunter",
  description: "Соревнования между менеджерами",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
