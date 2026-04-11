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
import { Confetti } from "@/components/ui/Confetti";
import { useScreenShake } from "@/components/ui/ScreenShake";
import { api } from "@/lib/api";
import { ErrorBoundary } from "@/components/errors/ErrorBoundary";
import type { PvPDuel } from "@/types";

export default function DuelPageWrapper() {
  return (
    <ErrorBoundary>
      <DuelPage />
    </ErrorBoundary>
  );
}

function DuelPage() {
  const params = useParams();
  const router = useRouter();
  const duelId = params.id as string;
  const store = usePvPStore();
  const shake = useScreenShake();
  const [confettiTrigger, setConfettiTrigger] = useState(0);
  const [input, setInput] = useState("");
  const [duelMeta, setDuelMeta] = useState<PvPDuel | null>(null);
  const [statusNotice, setStatusNotice] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const restartTimer = (seconds: number) => {
    if (timerRef.current) clearInterval(timerRef.current);
    store.setTimeRemaining(seconds);
    timerRef.current = setInterval(() => {
      // Pause countdown when WS is disconnected — server keeps its own timer
      if (usePvPStore.getState().timeRemaining <= 0) {
        if (timerRef.current) clearInterval(timerRef.current);
        return;
      }
      usePvPStore.setState({ timeRemaining: usePvPStore.getState().timeRemaining - 1 });
    }, 1000);
  };

  const { sendMessage, connectionState } = useWebSocket({
    path: "/ws/pvp",
    onMessage: (data) => {
      // Validate message has expected structure (#10)
      const d = data.data && typeof data.data === "object" ? data.data as Record<string, unknown> : {};

      switch (data.type) {
        case "duel.brief":
          store.setDuelBrief(d as unknown as import("@/types").DuelBrief);
          if (typeof d.your_role === "string") store.setMyRole(d.your_role as "seller" | "client");
          break;

        case "round.start":
          store.setRoundNumber(Number(d.round || 1));
          if (typeof d.your_role === "string") store.setMyRole(d.your_role as "seller" | "client");
          restartTimer(Number(d.time_limit || 0));
          setStatusNotice(null);
          break;

        case "round.swap":
          store.setRoundNumber(0); // swap indicator
          if (timerRef.current) clearInterval(timerRef.current);
          break;

        case "duel.state":
          store.setRoundNumber(Number(d.round_number || 1));
          if (typeof d.your_role === "string") store.setMyRole(d.your_role as "seller" | "client");
          store.replaceMessages(
            Array.isArray(d.messages)
              ? (d.messages as Array<Record<string, unknown>>).map((msg) => ({
                  id: store.nextMsgId(),
                  sender_role: msg.sender_role as "seller" | "client",
                  text: String(msg.text || ""),
                  round: Number(msg.round || d.round_number || 1),
                  timestamp:
                    typeof msg.timestamp === "string"
                      ? msg.timestamp
                      : typeof msg.timestamp === "number"
                        ? new Date((msg.timestamp as number) * 1000).toISOString()
                        : new Date().toISOString(),
                }))
              : [],
          );
          restartTimer(Number(d.time_remaining || d.time_limit || 0));
          setStatusNotice("Соединение восстановлено");
          break;

        case "duel.message":
          store.addMessage({
            id: store.nextMsgId(),
            sender_role: (typeof d.sender_role === "string" ? d.sender_role : "client") as "seller" | "client",
            text: String(d.text || ""),
            round: Number(d.round || 1),
            timestamp: new Date().toISOString(),
          });
          break;

        case "judge.score":
          store.setJudgeScore({
            selling_score: Number(d.selling_score || 0),
            acting_score: Number(d.acting_score || 0),
            legal_accuracy: Number(d.legal_accuracy || 0),
          });
          break;

        case "round.time_up":
          if (timerRef.current) clearInterval(timerRef.current);
          store.setTimeRemaining(0);
          break;

        case "duel.result": {
          if (timerRef.current) clearInterval(timerRef.current);
          // Celebration effects
          const winnerId = typeof d.winner_id === "string" ? d.winner_id : null;
          const userId = usePvPStore.getState().rating?.user_id;
          const isWin = userId != null && winnerId === userId;
          const isDraw = Boolean(d.is_draw);
          if (isWin) {
            setConfettiTrigger((c) => c + 1);
            shake("victory");
          } else if (!isDraw) {
            shake("error");
          }
          store.setDuelResult({
            duel_id: String(d.duel_id || ""),
            player1_total: Number(d.player1_total || 0),
            player2_total: Number(d.player2_total || 0),
            winner_id: typeof d.winner_id === "string" ? d.winner_id : null,
            is_draw: Boolean(d.is_draw),
            is_pve: Boolean(d.is_pve),
            rating_change_applied: Boolean(d.rating_change_applied),
            player1_rating_delta: Number(d.player1_rating_delta || 0),
            player2_rating_delta: Number(d.player2_rating_delta || 0),
            summary: String(d.summary || ""),
            player1_breakdown: d.player1_breakdown && typeof d.player1_breakdown === "object"
              ? d.player1_breakdown as import("@/stores/usePvPStore").PlayerBreakdown : null,
            player2_breakdown: d.player2_breakdown && typeof d.player2_breakdown === "object"
              ? d.player2_breakdown as import("@/stores/usePvPStore").PlayerBreakdown : null,
            turning_point: d.turning_point && typeof d.turning_point === "object"
              ? d.turning_point as { round?: number; description?: string } : null,
          });
          break;
        }

        case "opponent.disconnected":
          setStatusNotice(`Соперник переподключается. Ждём ${String(d.seconds_remaining || 60)} сек.`);
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
  }, [duelId]); // eslint-disable-line react-hooks/exhaustive-deps -- store.resetDuel is a stable Zustand action

  // Send ready on connect
  // Pause timer when disconnected — server keeps its own timer
  useEffect(() => {
    if (connectionState !== "connected" && timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, [connectionState]);

  useEffect(() => {
    if (connectionState === "connected") {
      sendMessage({ type: "duel.ready", duel_id: duelId });
    }
  }, [connectionState, duelId, sendMessage]);

  useEffect(() => {
    if (connectionState !== "connected") return;
    if (store.duelBrief || store.duelResult) return;

    const id = setInterval(() => {
      if (!usePvPStore.getState().duelBrief && !usePvPStore.getState().duelResult) {
        sendMessage({ type: "duel.ready", duel_id: duelId });
      }
    }, 1500);

    return () => clearInterval(id);
  }, [connectionState, duelId, sendMessage, store.duelBrief, store.duelResult]);

  useEffect(() => {
    const controller = new AbortController();
    api.get(`/pvp/duels/${duelId}`, { signal: controller.signal })
      .then((data) => setDuelMeta(data as PvPDuel))
      .catch((err) => { if (!controller.signal.aborted) logger.error("Failed to load duel meta:", err); });
    if (!store.rating) {
      store.fetchRating();
    }
    return () => controller.abort();
  }, [duelId]);

  // Cleanup
  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  const handleSend = () => {
    // #6 fix: sanitize input — strip control chars, cap length
    // eslint-disable-next-line no-control-regex
    const text = input.trim().replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F\u200B-\u200F\uFEFF]/g, "").slice(0, 2000);
    if (!text || !store.myRole || store.roundNumber === 0) return;
    sendMessage({ type: "duel.message", text });
    setInput("");
  };

  // Deduplicate duel.message — backend echo arrives after optimistic add would cause double.
  // Currently we rely on backend echo only. If bot fails, user still sees their own messages.

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
    const userId = store.rating?.user_id;
    const isP1 = duelMeta ? duelMeta.player1_id === userId : true;
    const myTotal = isP1 ? store.duelResult.player1_total : store.duelResult.player2_total;
    const oppTotal = isP1 ? store.duelResult.player2_total : store.duelResult.player1_total;
    const isWinner = userId != null && store.duelResult.winner_id === userId;

    return (<>
      <DuelResult
        myTotal={myTotal}
        opponentTotal={oppTotal}
        isWinner={isWinner}
        isDraw={store.duelResult.is_draw}
        isPvE={store.duelResult.is_pve}
        ratingChangeApplied={store.duelResult.rating_change_applied}
        myRatingDelta={isP1 ? store.duelResult.player1_rating_delta : store.duelResult.player2_rating_delta}
        summary={store.duelResult.summary}
        myBreakdown={isP1 ? store.duelResult.player1_breakdown : store.duelResult.player2_breakdown}
        opponentBreakdown={isP1 ? store.duelResult.player2_breakdown : store.duelResult.player1_breakdown}
        turningPoint={store.duelResult.turning_point}
        onClose={() => {
          store.resetDuel();
          router.push("/pvp");
        }}
      />
      {confettiTrigger > 0 && <Confetti trigger={confettiTrigger} />}
    </>);
  }

  return (
    <div className="flex h-screen flex-col" style={{ background: "var(--bg-primary)" }}>

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

      {/* Connection status */}
      {connectionState !== "connected" && (
        <div className="px-4 pt-3 z-20">
          <div
            className="rounded-xl px-4 py-2 text-xs font-mono flex items-center gap-2"
            style={{
              background: connectionState === "reconnecting" ? "rgba(245,158,11,0.1)" : "rgba(239,68,68,0.1)",
              color: connectionState === "reconnecting" ? "var(--warning)" : "var(--danger)",
              border: `1px solid ${connectionState === "reconnecting" ? "rgba(245,158,11,0.2)" : "rgba(239,68,68,0.2)"}`,
            }}
          >
            <div className="w-2 h-2 rounded-full animate-pulse" style={{ background: connectionState === "reconnecting" ? "var(--warning)" : "var(--danger)" }} />
            {connectionState === "reconnecting" ? "Переподключение..." : "Нет связи с сервером"}
          </div>
        </div>
      )}

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

      {/* Character brief for client role */}
      {store.myRole === "client" && store.duelBrief?.character_brief && (
        <div className="mx-4 mb-2 cyber-card px-3 py-2.5 z-20">
          <div className="flex items-center gap-2 mb-1.5">
            <span className="status-badge status-badge--online" style={{ fontSize: "12px" }}>
              ВАША РОЛЬ
            </span>
            <span className="text-xs font-mono font-bold" style={{ color: "var(--accent)" }}>
              {store.duelBrief.character_brief.name}
            </span>
          </div>
          <p className="text-xs leading-relaxed mb-1" style={{ color: "var(--text-secondary)" }}>
            {store.duelBrief.character_brief.brief}
          </p>
          <p className="text-xs italic" style={{ color: "var(--text-muted)" }}>
            {store.duelBrief.character_brief.behavior}
          </p>
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
              <div className="font-mono text-xs uppercase" style={{ color: "var(--text-muted)" }}>Продажи</div>
              <div className="font-bold" style={{ color: "var(--accent)" }}>{Math.round(store.judgeScore.selling_score)}</div>
            </div>
            <div className="text-center">
              <div className="font-mono text-xs uppercase" style={{ color: "var(--text-muted)" }}>Актёрство</div>
              <div className="font-bold" style={{ color: "var(--rank-gold)" }}>{Math.round(store.judgeScore.acting_score)}</div>
            </div>
            <div className="text-center">
              <div className="font-mono text-xs uppercase" style={{ color: "var(--text-muted)" }}>Юр. точность</div>
              <div className="font-bold" style={{ color: "var(--success)" }}>{Math.round(store.judgeScore.legal_accuracy)}</div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
