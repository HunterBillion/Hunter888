// B5-12: redirect `/methodology` → `/dashboard?tab=methodology`.
//
// Pre-2026-04-26 retirement of the methodologist role, the canonical
// surface was a top-level `/methodology` page. Post-retirement,
// methodology editing moved into the ROP dashboard tab. The old URL
// remained dead until this redirect — anyone with a stale bookmark
// (Anna's email signature, an old team handbook, etc.) now lands on
// the right place automatically.
import { redirect } from "next/navigation";

export default function MethodologyRedirectPage() {
  redirect("/dashboard?tab=methodology");
}
