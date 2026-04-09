import { ClientListSkeleton, LoadingTip } from "@/components/ui/Skeleton";

export default function ClientsLoading() {
  return (
    <>
      <ClientListSkeleton />
      <LoadingTip />
    </>
  );
}
