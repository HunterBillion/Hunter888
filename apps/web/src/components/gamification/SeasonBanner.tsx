"use client";

/**
 * SeasonBanner — compact banner showing current season & chapter.
 * Click expands to show narrative intro text.
 */

import { useState, useEffect, useCallback } from "react";
import { BookOpen } from "lucide-react";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";

interface Chapter {
  number: number;
  name: string;
  description: string;
  narrative_intro: string;
  is_active: boolean;
  is_unlocked: boolean;
  unlocks_at: string | null;
  scenario_count: number;
}

interface SeasonData {
  active: boolean;
  name?: string;
  description?: string;
  theme?: string;
  chapters?: Chapter[];
  current_chapter?: {
    number: number;
    name: string;
    narrative_intro: string;
  };
}

export default function SeasonBanner() {
  const [data, setData] = useState<SeasonData | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchSeason = useCallback(async () => {
    try {
      const d = await api.get<SeasonData>("/gamification/season/active");
      setData(d);
    } catch (err) {
      logger.error("Failed to fetch season:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSeason();
  }, [fetchSeason]);

  if (loading || !data || !data.active) {
    return null;
  }

  const chapter = data.current_chapter;

  // Compact inline badge for embedding in panel headers
  return (
    <span className="inline-flex items-center gap-1.5 rounded-md bg-[var(--accent-muted)] px-2.5 py-1 text-xs font-medium text-[var(--accent)] cursor-default" title={chapter?.narrative_intro || data.description}>
      <BookOpen size={12} />
      {chapter ? `Глава ${chapter.number}: ${chapter.name}` : data.name}
    </span>
  );
}
