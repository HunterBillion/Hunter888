import { PageSkeleton, LoadingTip } from "@/components/ui/Skeleton";

export default function AdminAuditLogLoading() {
  return (
    <>
      <PageSkeleton />
      <LoadingTip />
    </>
  );
}
