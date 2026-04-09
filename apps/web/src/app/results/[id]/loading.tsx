import { ResultsSkeleton, LoadingTip } from "@/components/ui/Skeleton";

export default function ResultsLoading() {
  return (
    <>
      <ResultsSkeleton />
      <LoadingTip />
    </>
  );
}
