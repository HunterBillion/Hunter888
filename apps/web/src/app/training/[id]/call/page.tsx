"use client";

/**
 * `/training/[id]/call` — full-screen "live call" view.
 *
 * Phase 2.10 (2026-04-19). This page is a companion view to the chat page
 * at `/training/[id]`. Switching between them is done via Next.js
 * client-side navigation so React state is preserved; however the WS
 * connection in the sibling chat page is NOT shared yet (tracked for
 * Phase 3 — shared provider). For V1 we accept that the session resumes
 * on the other side when the user switches back — existing backend
 * session.resume logic handles it.
 *
 * Data sources:
 *   - `useSessionStore` for session meta (characterName, emotion, callNumber, etc.)
 *   - `/api/training/sessions/{id}` GET to populate initial state if the
 *     store is cold (e.g. direct landing on /call without going through chat).
 *   - Query param `bg` lets us pass the CharacterBuilder `bg_noise` scene
 *     without a second round-trip to the API on first load.
 */

import { useEffect, useState, useRef } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useSessionStore } from "@/stores/useSessionStore";
import { PhoneCallMode } from "@/components/training/phone/PhoneCallMode";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";
import type { EmotionState } from "@/types";

interface SessionMeta {
  character_name?: string;
  scenario_title?: string;
  custom_bg_noise?: string | null;
  custom_params?: { bg_noise?: string | null } | null;
}

export default function TrainingCallPage() {
  const router = useRouter();
  const params = useParams();
  const searchParams = useSearchParams();
  const id = (Array.isArray(params?.id) ? params?.id[0] : params?.id) as string;

  const s = useSessionStore();

  const [sceneBg, setSceneBg] = useState<string | null>(
    searchParams?.get("bg") || null,
  );
  const [muted, setMuted] = useState(false);
  const [speakerOn, setSpeakerOn] = useState(false);
  const [audioLevel, setAudioLevel] = useState(0);
  const elapsedTickerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // If the store is empty (user deep-linked), pull session meta once so the
  // UI has a real name + background scene. Best-effort — we stay rendered
  // regardless of the API response.
  useEffect(() => {
    if (!id) return;
    if (s.characterName && s.characterName !== "Клиент" && sceneBg) return;

    (async () => {
      try {
        // `api.get` already unwraps the JSON response body, so we read
        // fields off the returned object directly (no `.data`).
        const meta = await api.get<SessionMeta>(`/training/sessions/${id}`);
        if (meta?.character_name) s.setCharacterName(meta.character_name);
        if (meta?.scenario_title) s.setScenarioTitle(meta.scenario_title);
        const bg =
          meta?.custom_bg_noise ||
          meta?.custom_params?.bg_noise ||
          null;
        if (bg) setSceneBg(bg);
      } catch (err) {
        logger.warn("[call] failed to hydrate session meta", err);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // Elapsed-timer — store already ticks during the chat session, but when
  // the user lands here directly we start our own interval so the UI isn't
  // frozen at 00:00.
  useEffect(() => {
    if (elapsedTickerRef.current) clearInterval(elapsedTickerRef.current);
    elapsedTickerRef.current = setInterval(() => {
      s.tickElapsed();
    }, 1000);
    return () => {
      if (elapsedTickerRef.current) clearInterval(elapsedTickerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // Subtle audio-level simulation when TTS activity can't be observed from
  // this page (the real audioLevel lives in useTTS inside the chat page).
  // In Phase 3 we'll promote useTTS to a shared provider and read the real
  // amplitude; for now we keep a gentle ambient pulse so the UI isn't dead.
  useEffect(() => {
    const h = setInterval(() => {
      // Pseudo-random walk bounded to [0, 0.4].
      setAudioLevel((v) => {
        const delta = (Math.random() - 0.5) * 0.2;
        return Math.max(0, Math.min(0.4, v + delta));
      });
    }, 300);
    return () => clearInterval(h);
  }, []);

  const onHangup = () => {
    // Return to the chat view; actual session end goes through the normal
    // abort/end flow owned by the chat page.
    router.push(`/training/${id}`);
  };

  return (
    <PhoneCallMode
      characterName={s.characterName || "Клиент"}
      emotion={s.emotion as EmotionState}
      sessionState={s.sessionState}
      audioLevel={audioLevel}
      elapsed={s.elapsed}
      muted={muted}
      speakerOn={speakerOn}
      sceneId={sceneBg}
      clientCard={s.clientCard}
      onToggleMute={() => setMuted((m) => !m)}
      onToggleSpeaker={() => setSpeakerOn((v) => !v)}
      onHangup={onHangup}
    />
  );
}
