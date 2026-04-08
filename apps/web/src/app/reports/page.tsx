"use client";

import { useAuth } from "@/hooks/useAuth";
import AuthLayout from "@/components/layout/AuthLayout";
import { BackButton } from "@/components/ui/BackButton";
import { ReportsDashboard } from "@/components/dashboard/ReportsDashboard";

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
