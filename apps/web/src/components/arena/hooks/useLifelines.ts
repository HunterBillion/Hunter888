"use client";

/**
 * useLifelines — client-side state + REST wiring for Arena lifelines.
 *
 * Sprint 4 (2026-04-20). One hook per match. Keeps an in-memory mirror
 * of the server's (hints, skips, fiftys) counters plus `initialising`
 * state. Exposes three action functions: `useHint`, `useSkip`,
 * `useFifty`. Each POSTs to `/arena/lifeline/*`, updates the local
 * counters from the server reply, and returns server payload to caller.
 *
 * Graceful degradation: if the network is down, the hook just shows 0
 * remaining — player can keep playing normally without lifelines.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";

export type ArenaLifelineMode = "arena" | "duel" | "rapid" | "pve" | "tournament";

export interface LifelineCounts {
  hints: number;
  skips: number;
  fiftys: number;
}

export interface LifelineHintPayload {
  text: string;
  article: string | null;
  confidence: number;
}

export interface UseLifelinesAPI {
  /** Remaining tokens by kind. */
  counts: LifelineCounts;
  /** True while the first `init` request is in flight. */
  initialising: boolean;
  /** Last hint payload (persists until next hint or reset). */
  lastHint: LifelineHintPayload | null;
  /** Non-null if the last call errored. */
  error: string | null;
  /** Try to consume a hint token and fetch a RAG-grounded pointer. */
  useHint: (questionText: string) => Promise<LifelineHintPayload | null>;
  /** Try to consume a skip token. */
  useSkip: () => Promise<boolean>;
  /** Try to consume a 50/50 token. */
  useFifty: () => Promise<boolean>;
  /** Clear the last hint overlay. */
  dismissHint: () => void;
  /** Re-fetch counters from the server. */
  refresh: () => Promise<void>;
}

interface Options {
  /** Unique per match/session — REST key. Set null to disable. */
  sessionId: string | null;
  /** Mode determines server-side quota. */
  mode: ArenaLifelineMode;
  /** If false, the hook never issues network calls. */
  enabled?: boolean;
}

const ZERO: LifelineCounts = { hints: 0, skips: 0, fiftys: 0 };

export function useLifelines({ sessionId, mode, enabled = true }: Options): UseLifelinesAPI {
  const [counts, setCounts] = useState<LifelineCounts>(ZERO);
  const [initialising, setInitialising] = useState<boolean>(false);
  const [lastHint, setLastHint] = useState<LifelineHintPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const initedRef = useRef<string | null>(null);

  // Lazy-init on mount / when sessionId changes.
  useEffect(() => {
    if (!enabled || !sessionId) return;
    if (initedRef.current === sessionId) return;
    initedRef.current = sessionId;
    let aborted = false;
    (async () => {
      try {
        setInitialising(true);
        const resp = await api.post<LifelineCounts>("/arena/lifeline/init", {
          session_id: sessionId,
          mode,
        });
        if (aborted) return;
        setCounts({
          hints: resp?.hints ?? 0,
          skips: resp?.skips ?? 0,
          fiftys: resp?.fiftys ?? 0,
        });
      } catch (e) {
        if (aborted) return;
        logger.warn("useLifelines.init failed", e);
      } finally {
        if (!aborted) setInitialising(false);
      }
    })();
    return () => {
      aborted = true;
    };
  }, [sessionId, mode, enabled]);

  const refresh = useCallback(async () => {
    if (!enabled || !sessionId) return;
    try {
      const resp = await api.get<LifelineCounts>(
        `/arena/lifeline/remaining?session_id=${encodeURIComponent(sessionId)}`,
      );
      setCounts({
        hints: resp?.hints ?? 0,
        skips: resp?.skips ?? 0,
        fiftys: resp?.fiftys ?? 0,
      });
    } catch (e) {
      logger.warn("useLifelines.refresh failed", e);
    }
  }, [sessionId, enabled]);

  const useHint = useCallback<UseLifelinesAPI["useHint"]>(
    async (questionText) => {
      if (!enabled || !sessionId) return null;
      try {
        setError(null);
        type HintResp = {
          consumed: boolean;
          text: string;
          article: string | null;
          confidence: number;
          remaining: LifelineCounts;
        };
        const resp = await api.post<HintResp>("/arena/lifeline/hint", {
          session_id: sessionId,
          question_text: questionText,
        });
        if (!resp?.consumed) {
          setError("Нет подсказок");
          return null;
        }
        const payload: LifelineHintPayload = {
          text: resp.text,
          article: resp.article,
          confidence: resp.confidence,
        };
        setLastHint(payload);
        setCounts({
          hints: resp.remaining?.hints ?? 0,
          skips: resp.remaining?.skips ?? 0,
          fiftys: resp.remaining?.fiftys ?? 0,
        });
        return payload;
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : "Не удалось получить подсказку";
        setError(msg);
        logger.warn("useLifelines.useHint failed", e);
        return null;
      }
    },
    [sessionId, enabled],
  );

  const useSkip = useCallback<UseLifelinesAPI["useSkip"]>(async () => {
    if (!enabled || !sessionId) return false;
    try {
      setError(null);
      type SkipResp = { consumed: boolean; remaining: LifelineCounts };
      const resp = await api.post<SkipResp>("/arena/lifeline/skip", {
        session_id: sessionId,
      });
      if (!resp?.consumed) {
        setError("Нет пропусков");
        return false;
      }
      setCounts({
        hints: resp.remaining?.hints ?? 0,
        skips: resp.remaining?.skips ?? 0,
        fiftys: resp.remaining?.fiftys ?? 0,
      });
      return true;
    } catch (e) {
      logger.warn("useLifelines.useSkip failed", e);
      return false;
    }
  }, [sessionId, enabled]);

  const useFifty = useCallback<UseLifelinesAPI["useFifty"]>(async () => {
    if (!enabled || !sessionId) return false;
    try {
      setError(null);
      type FiftyResp = { consumed: boolean; remaining: LifelineCounts };
      const resp = await api.post<FiftyResp>("/arena/lifeline/fifty", {
        session_id: sessionId,
      });
      if (!resp?.consumed) {
        setError("Нет 50/50");
        return false;
      }
      setCounts({
        hints: resp.remaining?.hints ?? 0,
        skips: resp.remaining?.skips ?? 0,
        fiftys: resp.remaining?.fiftys ?? 0,
      });
      return true;
    } catch (e) {
      logger.warn("useLifelines.useFifty failed", e);
      return false;
    }
  }, [sessionId, enabled]);

  const dismissHint = useCallback(() => setLastHint(null), []);

  return {
    counts,
    initialising,
    lastHint,
    error,
    useHint,
    useSkip,
    useFifty,
    dismissHint,
    refresh,
  };
}
