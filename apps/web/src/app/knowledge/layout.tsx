import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "База знаний | XHunter",
  description: "Проверьте свои знания по продукту, скриптам и возражениям",
};

export default function KnowledgeLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
