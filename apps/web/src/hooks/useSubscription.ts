"use client";

/**
 * useSubscription — fetch + cache the user's current plan + entitlement.
 *
 * Phase C (2026-04-20). Wraps `GET /api/subscription` which returns:
 *   { plan, is_trial, trial_days_remaining, is_seed_account,
 *     expires_at, usage: {sessions_today, sessions_limit, ...},
 *     features: {ai_coach, wiki_full_access, export_reports, ...} }
 *
 * Contracts:
 *   • Elevated roles (admin/rop/methodologist) are server-promoted to
 *     `master` plan regardless of payment — the chip + upsell flow must
 *     hide itself for these roles (see `isElevated()`).
 *   • Refresh is MANUAL on 429: callers of api.ts can pass along a
 *     `X-Plan-Feature` header to force re-fetch; we also expose
 *     `refresh()` so the PlanLimitModal can refetch after upgrade.
 *   • Failures are soft: if the endpoint 500s we expose `plan="scout"`
 *     + `features={}` defaults so UI falls back to the most restrictive
 *     state rather than flashing a fake premium badge.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";

export type PlanType = "scout" | "ranger" | "hunter" | "master";

export interface SubscriptionUsage {
  sessions_today: number;
  sessions_limit: number;
  pvp_today: number;
  pvp_limit: number;
  rag_today: number;
  rag_limit: number;
}

export interface SubscriptionFeatures {
  ai_coach: boolean;
  wiki_full_access: boolean;
  export_reports: boolean;
  voice_cloning: boolean;
  team_management: boolean;
  team_challenge: boolean;
  priority_matchmaking: boolean;
  analytics: string;
  tournaments: string;
  llm_priority: string;
}

export interface SubscriptionState {
  plan: PlanType;
  is_trial: boolean;
  trial_days_remaining: number;
  is_seed_account: boolean;
  expires_at: string | null;
  usage: SubscriptionUsage;
  features: SubscriptionFeatures;
}

const DEFAULT_STATE: SubscriptionState = {
  plan: "scout",
  is_trial: false,
  trial_days_remaining: 0,
  is_seed_account: false,
  expires_at: null,
  usage: {
    sessions_today: 0,
    sessions_limit: 3,
    pvp_today: 0,
    pvp_limit: 2,
    rag_today: 0,
    rag_limit: 5,
  },
  features: {
    ai_coach: false,
    wiki_full_access: false,
    export_reports: false,
    voice_cloning: false,
    team_management: false,
    team_challenge: false,
    priority_matchmaking: false,
    analytics: "basic",
    tournaments: "leaderboard",
    llm_priority: "low",
  },
};

export function useSubscription(): {
  data: SubscriptionState | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
} {
  const [data, setData] = useState<SubscriptionState | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const mountedRef = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const resp = await api.get<SubscriptionState>("/subscription");
      if (!mountedRef.current) return;
      setData({ ...DEFAULT_STATE, ...resp });
      setError(null);
    } catch (e) {
      if (!mountedRef.current) return;
      logger.warn("useSubscription fetch failed", e);
      setError(e instanceof Error ? e.message : "failed");
      // Don't null out previous data if we had some — let the UI keep
      // showing stale state rather than flapping.
      setData((prev) => prev ?? DEFAULT_STATE);
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    refresh();
    return () => {
      mountedRef.current = false;
    };
  }, [refresh]);

  return { data, loading, error, refresh };
}

/**
 * Is this role server-promoted to master? Used to hide plan-related UI
 * (chip + upsell modal) because the plan is effectively not their axis
 * of experience — they have everything by virtue of their role.
 */
export function isElevatedRole(
  role: string | null | undefined,
): boolean {
  // `methodologist` retired 2026-04-26 — kept here so any stale JWT token
  // issued before the cutover keeps Master plan exemption until refresh.
  // B3.2 will drop it after token rotation completes.
  return role === "admin" || role === "rop" || role === "methodologist";
}
