import { PageSkeleton, LoadingTip } from "@/components/ui/Skeleton";

export default function WikiLoading() {
  return (
    <>
      <PageSkeleton />
      <LoadingTip />
    </>
  );
}
