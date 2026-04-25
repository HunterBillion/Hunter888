import { PageSkeleton, LoadingTip } from "@/components/ui/Skeleton";

export default function StoriesLoading() {
  return (
    <>
      <PageSkeleton />
      <LoadingTip />
    </>
  );
}
