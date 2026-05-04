// Redirect for stale `/pvp/team` (singular) bookmarks.
//
// The teams leaderboard now lives at `/leaderboard?tab=teams` (merged
// from the standalone `/pvp/teams` page in 2026-05-04 phase C). The
// `/pvp/team/[teamId]` dynamic route still exists for individual team
// views; this bare entry redirects to the unified leaderboard.
import { redirect } from "next/navigation";

export default function PvPTeamIndexPage() {
  redirect("/leaderboard?tab=teams");
}
