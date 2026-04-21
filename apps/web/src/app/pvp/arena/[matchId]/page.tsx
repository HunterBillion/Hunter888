"use client";

import { useEffect, useCallback, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useKnowledgeStore } from "@/stores/useKnowledgeStore";
import { useAuthStore } from "@/stores/useAuthStore";
import PvPArenaMatch from "@/components/knowledge/PvPArenaMatch";
import type { ArenaRoundResult } from "@/types";
import { logger } from "@/lib/logger";
import { PageAuthGate } from "@/components/layout/PageAuthGate";

export default function ArenaMatchPageWrapper() {
  return (
    <PageAuthGate>
      <ArenaMatchPage />
    </PageAuthGate>
  );
}

function ArenaMatchPage() {
  const params = useParams();
  const router = useRouter();
  const matchId = params.matchId as string;
  const user = useAuthStore((s) => s.user);
  const userId = user?.id || "";

  const store = useKnowledgeStore();
  const storeRef = useRef(store);
  storeRef.current = store;

  const handleMessage = useCallback(
    (msg: { type: string; data?: Record<string, unknown> }) => {
      const s = storeRef.current;
      const data = msg.data || {};

      switch (msg.type) {
        case "pvp.round_question":
          s.setPvPRoundQuestion(
            data.question_text as string,
            (data.category as string) || null,
            (data.difficulty as number) || 3,
            data.round_number as number,
            (data.time_limit_seconds as number) || 45,
          );
          break;

        // 2026-04-19 Phase 2.8: arcade TTS narration. Backend pushes this
        // asynchronously after the round starts — we just stash the URL
        // and <ArenaAudioPlayer> autoplays it.
        case "pvp.audio_ready":
          s.setPvpArenaAudio((data.audio_url as string) || null);
          break;

        case "pvp.player_answered":
          if (data.user_id !== userId) {
            s.setOpponentAnswered(data.user_id as string);
          }
          break;

        case "pvp.round_result":
          s.addArenaRoundResult(data as unknown as ArenaRoundResult);
          break;

        case "pvp.scoreboard":
          s.updateArenaScoreboard(
            (data.players as { user_id: string; name: string; total_score: number; correct_count: number }[]).map(
              (p) => ({
                user_id: p.user_id,
                name: p.name,
                score: p.total_score,
                correct: p.correct_count,
                is_bot: false,
                rating: 1500,
              }),
            ),
          );
          break;

        case "pvp.final_results":
          s.setArenaFinalResults({
            rankings: (data.rankings as { user_id: string; name: string; score: number; correct: number; is_bot: boolean; rank: number; rating_delta?: number }[]).map(
              (r) => ({
                user_id: r.user_id,
                name: r.name,
                score: r.score,
                correct: r.correct || 0,
                is_bot: r.is_bot || false,
                rating: 1500,
                rating_delta: r.rating_delta || 0,
                rank: r.rank,
              }),
            ),
            total_rounds: data.total_rounds as number,
            contains_bot: data.contains_bot as boolean,
          });
          break;

        case "pvp.match_state_restore": {
          // Reconnect: restore full match state from server
          const restorePlayers = (data.players as { user_id: string; name: string; score: number; correct_count: number; is_bot: boolean }[]) || [];
          s.setPvPMatch(
            data.session_id as string,
            restorePlayers.map((p) => ({
              user_id: p.user_id,
              name: p.name,
              score: p.score,
              correct: p.correct_count || 0,
              is_bot: p.is_bot || false,
              rating: 1500,
            })),
            (data.total_rounds as number) || 10,
          );
          // Current round will be set when next pvp.round_question arrives
          logger.log("[Arena] Match state restored after reconnect, round", data.current_round);
          break;
        }

        case "pvp.player_disconnected":
          s.addDisconnectedPlayer(data.user_id as string);
          break;

        case "pvp.player_reconnected":
          s.removeDisconnectedPlayer(data.user_id as string);
          break;

        case "error":
          logger.error("[Arena]", data.message);
          break;
      }
    },
    [userId],
  );

  const { sendMessage, isConnected } = useWebSocket({
    path: "/ws/knowledge",
    onMessage: handleMessage,
  });

  // Redirect to pvp page if no match
  useEffect(() => {
    if (!matchId) {
      router.replace("/pvp");
    }
  }, [matchId, router]);

  if (!isConnected) {
    return (
      <div className="flex items-center justify-center h-screen glass-panel text-white">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-2 border-blue-500 border-t-transparent mx-auto mb-4" />
          <p className="text-gray-400">Подключение к матчу...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen">
      <PvPArenaMatch userId={userId} sendMessage={sendMessage} />
    </div>
  );
}
