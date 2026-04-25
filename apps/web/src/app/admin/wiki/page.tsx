"use client";

/**
 * /admin/wiki — admin Wiki dashboard.
 *
 * Auth + AuthLayout are handled by the parent admin/layout.tsx — this
 * page renders only the dashboard content.
 */

import dynamic from "next/dynamic";
import { DashboardSkeleton } from "@/components/ui/Skeleton";

const WikiDashboard = dynamic(
  () => import("@/components/dashboard/WikiDashboard").then((m) => m.WikiDashboard),
  { loading: () => <DashboardSkeleton />, ssr: false }
);

export default function AdminWikiPage() {
  return <WikiDashboard />;
}
