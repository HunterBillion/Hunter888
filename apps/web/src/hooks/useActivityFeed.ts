import { useMemo } from "react";
import type { TeamMember, ActivityFeedItem } from "@/types";

export function useActivityFeed(members: TeamMember[]): ActivityFeedItem[] {
  return useMemo(() => {
    const items: ActivityFeedItem[] = [];

    for (const m of members) {
      if (m.sessions_this_week > 0) {
        items.push({
          id: `session-${m.id}`,
          type: "session_completed",
          user_id: m.id,
          user_name: m.full_name,
          message: `завершил${m.full_name.endsWith("а") ? "а" : ""} ${m.sessions_this_week} сесси${m.sessions_this_week === 1 ? "ю" : m.sessions_this_week < 5 ? "и" : "й"} на этой неделе`,
          score: m.avg_score,
          created_at: new Date().toISOString(),
        });
      }

      if (m.best_score !== null && m.best_score >= 85) {
        items.push({
          id: `record-${m.id}`,
          type: "new_record",
          user_id: m.id,
          user_name: m.full_name,
          message: `достиг${m.full_name.endsWith("а") ? "ла" : ""} лучшего результата — ${Math.round(m.best_score)}!`,
          score: m.best_score,
          created_at: new Date(Date.now() - Math.random() * 86400000).toISOString(),
        });
      }
    }

    return items
      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
      .slice(0, 10);
  }, [members]);
}
