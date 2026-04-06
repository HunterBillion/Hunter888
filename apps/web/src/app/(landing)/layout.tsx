import { LandingLayout } from "@/components/landing/LandingLayout";

export default function Layout({ children }: { children: React.ReactNode }) {
  return <LandingLayout>{children}</LandingLayout>;
}
