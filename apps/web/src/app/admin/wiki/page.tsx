"use client";

import { useRouter } from "next/navigation";
import { ShieldCheck, Loader2 } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { isAdmin } from "@/lib/guards";
import AuthLayout from "@/components/layout/AuthLayout";
import dynamic from "next/dynamic";
import { DashboardSkeleton } from "@/components/ui/Skeleton";

const WikiDashboard = dynamic(
  () => import("@/components/dashboard/WikiDashboard").then((m) => m.WikiDashboard),
  { loading: () => <DashboardSkeleton />, ssr: false }
);

export default function AdminWikiPage() {
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();

  const accessDenied = !authLoading && user != null && !isAdmin(user);

  if (accessDenied) {
    return (
      <AuthLayout>
        <div style={{ maxWidth: 600, margin: "4rem auto", textAlign: "center", padding: "2rem" }}>
          <ShieldCheck size={48} style={{ color: "var(--danger)", margin: "0 auto 1rem" }} />
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "#fff" }}>
            Доступ запрещён
          </h1>
          <p style={{ color: "var(--text-muted)", marginTop: "0.5rem" }}>
            Wiki менеджеров доступна только администраторам.
          </p>
          <button
            onClick={() => router.push("/home")}
            style={{
              marginTop: "1.5rem",
              padding: "0.75rem 2rem",
              background: "rgba(255,255,255,0.06)",
              border: "1px solid rgba(255,255,255,0.1)",
              borderRadius: 8,
              color: "#e0e0e0",
              cursor: "pointer",
              fontSize: "0.9rem",
            }}
          >
            На главную
          </button>
        </div>
      </AuthLayout>
    );
  }

  if (authLoading) {
    return (
      <AuthLayout>
        <div style={{ textAlign: "center", padding: "6rem 2rem" }}>
          <Loader2 size={36} style={{ animation: "spin 1s linear infinite", color: "var(--warning)" }} />
          <p style={{ color: "var(--text-muted)", marginTop: "1rem" }}>Загрузка...</p>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout>
      <div style={{ padding: "2rem 1rem" }}>
        <WikiDashboard />
      </div>
    </AuthLayout>
  );
}
