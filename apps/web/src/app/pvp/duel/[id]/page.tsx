"use client";

import { useEffect, useState, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { logger } from "@/lib/logger";
import { Swords, Loader2 } from "lucide-react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { usePvPStore } from "@/stores/usePvPStore";
import { DuelChat } from "@/components/pvp/DuelChat";
import { RoundIndicator } from "@/components/pvp/RoundIndicator";
import { DuelResult } from "@/components/pvp/DuelResult";
import { api } from "@/lib/api";
import type { PvPDuel } from "@/types";

export default function DuelPage() {
  const params = useParams();
  const router = useRouter();
  const duelId = params.id as string;
  const store = usePvPStore();
  const [input, setInput] = useState("");
  const [duelMeta, setDuelMeta] = useState<PvPDuel | null>(null);
  const [statusNotice, setStatusNotice] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const restartTimer = (seconds: number) => {
    if (timerRef.current) clearInterval(timerRef.current);
    store.setTimeRemaining(seconds);
    timerRef.current = setInterval(() => {
      const t = usePvPStore.getState().timeRemaining;
      if (t <= 0) {
        if (timerRef.current) clearInterval(timerRef.current);
        return;
      }
      usePvPStore.setState({ timeRemaining: t - 1 });
    }, 1000);
  };

  const { sendMessage, connectionState } = useWebSocket({
    path: "/ws/pvp",
    onMessage: (data) => {
      switch (data.type) {
        case "duel.brief":
          store.setDuelBrief(data.data as unknown as import("@/types").DuelBrief);
          store.setMyRole(data.data.your_role as "seller" | "client");
          break;

        case "round.start":
          store.setRoundNumber(data.data.round as number);
          store.setMyRole(data.data.your_role as "seller" | "client");
          restartTimer(data.data.time_limit as number);
          setStatusNotice(null);
          break;

        case "round.swap":
          store.setRoundNumber(0); // swap indicator
          if (timerRef.current) clearInterval(timerRef.current);
          break;

        case "duel.state":
          store.setRoundNumber(data.data.round_number as number);
          store.setMyRole(data.data.your_role as "seller" | "client");
          store.replaceMessages(
            Array.isArray(data.data.messages)
              ? (data.data.messages as Array<Record<string, unknown>>).map((msg) => ({
                  id: store.nextMsgId(),
                  sender_role: msg.sender_role as "seller" | "client",
                  text: String(msg.text || ""),
                  round: Number(msg.round || data.data.round_number || 1),
                  timestamp:
                    typeof msg.timestamp === "string"
                      ? msg.timestamp
                      : typeof msg.timestamp === "number"
                        ? new Date((msg.timestamp as number) * 1000).toISOString()
                        : new Date().toISOString(),
                }))
              : [],
          );
          restartTimer(Number(data.data.time_remaining || data.data.time_limit || 0));
          setStatusNotice("Соединение восстановлено");
          break;

        case "duel.message":
          store.addMessage({
            id: store.nextMsgId(),
            sender_role: data.data.sender_role as "seller" | "client",
            text: data.data.text as string,
            round: data.data.round as number,
            timestamp: new Date().toISOString(),
          });
          break;

        case "judge.score":
          store.setJudgeScore({
            selling_score: data.data.selling_score as number,
            acting_score: data.data.acting_score as number,
            legal_accuracy: data.data.legal_accuracy as number,
          });
          break;

        case "round.time_up":
          if (timerRef.current) clearInterval(timerRef.current);
          store.setTimeRemaining(0);
          break;

        case "duel.result":
          if (timerRef.current) clearInterval(timerRef.current);
          store.setDuelResult({
            duel_id: data.data.duel_id as string,
            player1_total: data.data.player1_total as number,
            player2_total: data.data.player2_total as number,
            winner_id: data.data.winner_id as string | null,
            is_draw: data.data.is_draw as boolean,
            is_pve: Boolean(data.data.is_pve),
            rating_change_applied: Boolean(data.data.rating_change_applied),
            player1_rating_delta: data.data.player1_rating_delta as number,
            player2_rating_delta: data.data.player2_rating_delta as number,
            summary: data.data.summary as string,
          });
          break;

        case "opponent.disconnected":
          setStatusNotice(`Соперник переподключается. Ждём ${String(data.data.seconds_remaining || 60)} сек.`);
          break;

        case "duel.resumed":
          setStatusNotice("Восстанавливаем дуэль...");
          break;

        case "duel.cancelled":
          if (timerRef.current) clearInterval(timerRef.current);
          setStatusNotice("Дуэль остановлена: соперник не вернулся");
          setTimeout(() => {
            store.resetDuel();
            router.push("/pvp");
          }, 1500);
          break;

        case "error":
          logger.error("PvP error:", data.data.detail);
          if (typeof data.data.detail === "string") {
            setStatusNotice(data.data.detail);
          }
          break;
      }
    },
  });

  useEffect(() => {
    store.resetDuel();
  }, [duelId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Send ready on connect
  useEffect(() => {
    if (connectionState === "connected") {
      sendMessage({ type: "duel.ready", duel_id: duelId });
    }
  }, [connectionState, duelId, sendMessage]);

  useEffect(() => {
    api.get(`/pvp/duels/${duelId}`)
      .then((data) => setDuelMeta(data as PvPDuel))
      .catch(() => null);
    if (!store.rating) {
      store.fetchRating();
    }
  }, [duelId]);

  // Cleanup
  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  const handleSend = () => {
    const text = input.trim();
    if (!text || !store.myRole || store.roundNumber === 0) return;
    sendMessage({ type: "duel.message", text });
    setInput("");
  };

  // Loading state
  if (!store.duelBrief && !store.duelResult) {
    return (
      <div className="flex h-screen flex-col items-center justify-center" style={{ background: "var(--bg-primary)" }}>
        <Loader2 size={24} className="animate-spin" style={{ color: "var(--accent)" }} />
        <span className="mt-4 font-mono text-xs tracking-widest" style={{ color: "var(--text-muted)" }}>
          ПОДКЛЮЧЕНИЕ К АРЕНЕ...
        </span>
      </div>
    );
  }

  // Result overlay
  if (store.duelResult) {
    const isP1 = duelMeta ? duelMeta.player1_id === store.rating?.user_id : true;
    const myTotal = isP1 ? store.duelResult.player1_total : store.duelResult.player2_total;
    const oppTotal = isP1 ? store.duelResult.player2_total : store.duelResult.player1_total;
    const isWinner = store.duelResult.winner_id === store.rating?.user_id;

    return (
      <DuelResult
        myTotal={myTotal}
        opponentTotal={oppTotal}
        isWinner={isWinner}
        isDraw={store.duelResult.is_draw}
        isPvE={store.duelResult.is_pve}
        ratingChangeApplied={store.duelResult.rating_change_applied}
        myRatingDelta={isP1 ? store.duelResult.player1_rating_delta : store.duelResult.player2_rating_delta}
        summary={store.duelResult.summary}
        onClose={() => {
          store.resetDuel();
          router.push("/pvp");
        }}
      />
    );
  }

  return (
    <div className="flex h-screen flex-col" style={{ background: "var(--bg-primary)" }}>
      {/* Scanlines */}
      <div className="fixed inset-0 scanlines z-[100] opacity-10 mix-blend-overlay pointer-events-none" />

      {/* Header */}
      <header
        className="h-14 shrink-0 flex items-center justify-between px-6 z-20"
        style={{ background: "var(--glass-bg)", borderBottom: "1px solid var(--border-color)", backdropFilter: "blur(20px)" }}
      >
        <div className="flex items-center gap-3">
          <Swords size={18} style={{ color: "var(--accent)" }} />
          <span className="font-display font-bold tracking-wider" style={{ color: "var(--text-primary)" }}>
            PVP ДУЭЛЬ
          </span>
        </div>
        <div className="font-mono text-xs" style={{ color: "var(--text-muted)" }}>
          {store.duelBrief?.scenario_title || "Сценарий"}
        </div>
      </header>

      {statusNotice && (
        <div className="px-4 pt-3 z-20">
          <div
            className="rounded-xl px-4 py-2 text-xs font-mono"
            style={{ background: "rgba(255,255,255,0.06)", color: "var(--text-secondary)", border: "1px solid rgba(255,255,255,0.08)" }}
          >
            {statusNotice}
          </div>
        </div>
      )}

      {/* Round indicator */}
      {store.myRole && (
        <div className="px-4 py-2 z-20">
          <RoundIndicator
            roundNumber={store.roundNumber}
            myRole={store.myRole}
            timeRemaining={store.timeRemaining}
          />
        </div>
      )}

      {/* Chat area */}
      <div className="flex-1 min-h-0 z-20">
        <DuelChat
          messages={store.messages}
          myRole={store.myRole || "seller"}
          input={input}
          onInputChange={setInput}
          onSend={handleSend}
          disabled={store.roundNumber === 0 || store.timeRemaining <= 0}
        />
      </div>

      {/* Judge score */}
      <AnimatePresence>
        {store.judgeScore && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="px-6 py-3 flex items-center justify-center gap-6 z-20"
            style={{ borderTop: "1px solid var(--border-color)", background: "var(--glass-bg)" }}
          >
            <div className="text-center">
              <div className="font-mono text-[9px] uppercase" style={{ color: "var(--text-muted)" }}>Продажи</div>
              <div className="font-bold" style={{ color: "var(--accent)" }}>{Math.round(store.judgeScore.selling_score)}</div>
            </div>
            <div className="text-center">
              <div className="font-mono text-[9px] uppercase" style={{ color: "var(--text-muted)" }}>Актёрство</div>
              <div className="font-bold" style={{ color: "#FFD700" }}>{Math.round(store.judgeScore.acting_score)}</div>
            </div>
            <div className="text-center">
              <div className="font-mono text-[9px] uppercase" style={{ color: "var(--text-muted)" }}>Юр. точность</div>
              <div className="font-bold" style={{ color: "var(--neon-green)" }}>{Math.round(store.judgeScore.legal_accuracy)}</div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
