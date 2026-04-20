"use client";

/**
 * usePowerUps — client state for Arena power-ups (×2 XP so far).
 *
 * Phase C (2026-04-20). Mirror of ``useLifelines`` but for active,
 * consumable modifiers. The flow:
 *
 *   1. ``init(sessionId, mode)`` on match start   → backend seeds quota
 *   2. ``activate(kind)``                         → debits a charge and
 *                                                   arms the next answer
 *   3. backend multiplies the next round's score  (see ws/knowledge.py)
 *   4. ``refresh()`` after round result           → syncs remaining
 *
 * The hook exposes a single ``activeKind`` value so the UI can render
 * a glow on the input while a power-up is armed.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";

export type ArenaPowerupMode = "arena" | "duel" | "rapid" | "pve" | "tournament";
export type PowerupKind = "doublexp"; // extend when we ship more

export interface PowerupCounts {
  doublexp: number;
}

export interface UsePowerUpsAPI {
  counts: PowerupCounts;
  activeKind: PowerupKind | null;
  loading: boolean;
  error: string | null;
  activate: (kind: PowerupKind) => Promise<boolean>;
  refresh: () => Promise<void>;
}

interface Options {
  sessionId: string | null;
  mode: ArenaPowerupMode;
  enabled?: boolean;
}

const ZERO: PowerupCounts = { doublexp: 0 };

interface RemainingResponse extends PowerupCounts {
  active: PowerupKind | null;
}

interface ActivateResponse {
  activated: boolean;
  active: PowerupKind | null;
  remaining: RemainingResponse;
}

export function usePowerUps({
  sessionId,
  mode,
  enabled = true,
}: Options): UsePowerUpsAPI {
  const [counts, setCounts] = useState<PowerupCounts>(ZERO);
  const [activeKind, setActiveKind] = useState<PowerupKind | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const initedRef = useRef<string | null>(null);

  // Seed quota on mount / when sessionId changes.
  useEffect(() => {
    if (!enabled || !sessionId) return;
    if (initedRef.current === sessionId) return;
    initedRef.current = sessionId;
    let aborted = false;
    (async () => {
      try {
        setLoading(true);
        const resp = await api.post<RemainingResponse>(
          "/arena/powerup/init",
          { session_id: sessionId, mode },
        );
        if (aborted) return;
        setCounts({ doublexp: resp?.doublexp ?? 0 });
        setActiveKind(resp?.active ?? null);
      } catch (e) {
        if (!aborted) logger.warn("usePowerUps.init failed", e);
      } finally {
        if (!aborted) setLoading(false);
      }
    })();
    return () => {
      aborted = true;
    };
  }, [sessionId, mode, enabled]);

  const refresh = useCallback(async () => {
    if (!enabled || !sessionId) return;
    try {
      const resp = await api.get<RemainingResponse>(
        `/arena/powerup/remaining?session_id=${encodeURIComponent(sessionId)}`,
      );
      setCounts({ doublexp: resp?.doublexp ?? 0 });
      setActiveKind(resp?.active ?? null);
    } catch (e) {
      logger.warn("usePowerUps.refresh failed", e);
    }
  }, [sessionId, enabled]);

  const activate = useCallback<UsePowerUpsAPI["activate"]>(
    async (kind) => {
      if (!enabled || !sessionId) return false;
      setError(null);
      try {
        const resp = await api.post<ActivateResponse>(
          "/arena/powerup/activate",
          { session_id: sessionId, kind },
        );
        if (!resp?.activated) {
          setError("Не удалось активировать");
          return false;
        }
        setCounts({ doublexp: resp.remaining?.doublexp ?? 0 });
        setActiveKind(resp.active ?? kind);
        return true;
      } catch (e: unknown) {
        // The server uses 409 for "no charges" / "already armed" and 503
        // for transient storage errors. Propagate a short human message.
        const msg = e instanceof Error ? e.message : "";
        if (msg.includes("Нет зарядов")) setError("Нет зарядов");
        else if (msg.includes("уже активно")) setError("Уже активно");
        else setError("Не удалось активировать");
        logger.warn("usePowerUps.activate failed", e);
        return false;
      }
    },
    [sessionId, enabled],
  );

  return { counts, activeKind, loading, error, activate, refresh };
}
