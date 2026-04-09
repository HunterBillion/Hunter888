import { LeaderboardSkeleton, LoadingTip } from "@/components/ui/Skeleton";

export default function LeaderboardLoading() {
  return (
    <>
      <LeaderboardSkeleton />
      <LoadingTip />
    </>
  );
}
