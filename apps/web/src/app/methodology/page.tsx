// Legacy `/methodology` → `/dashboard?tab=content` redirect.
//
// Two historical layers stack here:
//   1. Pre-2026-04-26: a standalone `/methodology` page existed for the
//      retired methodologist role.
//   2. 2026-05-05: the in-dashboard tab was renamed `methodology` →
//      `content` so business users stop reading the URL as something
//      they don't own. Anyone landing here from a stale bookmark / email
//      signature / handbook PDF gets bounced to the canonical place in
//      one hop.
import { redirect } from "next/navigation";

export default function MethodologyRedirectPage() {
  redirect("/dashboard?tab=content");
}
