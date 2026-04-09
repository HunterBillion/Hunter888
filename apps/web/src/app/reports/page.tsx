"use client";

import { useAuth } from "@/hooks/useAuth";
import AuthLayout from "@/components/layout/AuthLayout";
import { BackButton } from "@/components/ui/BackButton";
import dynamic from "next/dynamic";
import { DashboardSkeleton } from "@/components/ui/Skeleton";

const ReportsDashboard = dynamic(
  () => import("@/components/dashboard/ReportsDashboard").then((m) => m.ReportsDashboard),
  { loading: () => <DashboardSkeleton />, ssr: false }
);

export default function ReportsPage() {
  const { user } = useAuth();

  return (
    <AuthLayout>
      <div className="panel-grid-bg min-h-screen w-full">
        <div className="mx-auto" style={{ maxWidth: 800, padding: "24px 16px" }}>
          <BackButton href="/home" label="На главную" />
          <ReportsDashboard />
        </div>
      </div>
    </AuthLayout>
  );
}
