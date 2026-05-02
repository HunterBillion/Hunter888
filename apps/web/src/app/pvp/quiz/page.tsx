// B5-12: redirect for stale `/pvp/quiz` (no sessionId) bookmarks.
//
// The quiz route only ever has meaning at `/pvp/quiz/[sessionId]/`
// (that page handles the active quiz). Visitors who clicked an
// outdated link or stripped the sessionId from the URL would have
// landed on a Next.js 404 — now they land on the arena hub which
// is where they would start a fresh quiz from anyway.
import { redirect } from "next/navigation";

export default function PvPQuizIndexPage() {
  redirect("/pvp");
}
