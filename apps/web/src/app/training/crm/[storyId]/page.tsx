import { redirect } from "next/navigation";

/**
 * Backward-compat redirect: /training/crm/[storyId] → /stories/[storyId]
 * (see sibling comment in ../page.tsx)
 */
export default async function TrainingCrmStoryRedirect({
  params,
}: {
  params: Promise<{ storyId: string }>;
}) {
  const { storyId } = await params;
  redirect(`/stories/${storyId}`);
}
