import { PageSkeleton, LoadingTip } from "@/components/ui/Skeleton";

export default function HomeLoading() {
  return (
    <>
      <PageSkeleton />
      <LoadingTip />
    </>
  );
}
