// B5-12: redirect for stale `/pvp/team` (singular) bookmarks.
//
// The teams hub is at `/pvp/teams` (plural). The `/pvp/team/[teamId]`
// dynamic route is for individual team views. A bare `/pvp/team`
// without a teamId previously 404'd; now it redirects to the hub.
import { redirect } from "next/navigation";

export default function PvPTeamIndexPage() {
  redirect("/pvp/teams");
}
