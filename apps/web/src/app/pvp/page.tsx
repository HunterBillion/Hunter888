"use client";

import { Suspense, useEffect, useState, useCallback, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { Swords, ArrowRight, Clock, Loader2, Trophy, Zap } from "lucide-react";
import AuthLayout from "@/components/layout/AuthLayout";
import { api } from "@/lib/api";
import { useWebSocket } from "@/hooks/useWebSocket";
import { usePvPStore } from "@/stores/usePvPStore";
import { RatingCard } from "@/components/pvp/RatingCard";
import { MatchmakingOverlay } from "@/components/pvp/MatchmakingOverlay";
import { RankBadge } from "@/components/pvp/RankBadge";
import { FriendsPanel } from "@/components/pvp/FriendsPanel";
import type { PvPRankTier, DuelStatus } from "@/types";

const DUEL_STATUS_LABELS: Record<string, string> = {
  pending: "Ожидание",
  round_1: "Раунд 1",
  swap: "Смена ролей",
  round_2: "Раунд 2",
  judging: "Оценка",
  completed: "Завершён",
  cancelled: "Отменён",
  disputed: "Оспорен",
};

function PvPLobbyContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const store = usePvPStore();
  const [tab, setTab] = useState<"arena" | "history">("arena");
  const [pveAccepting, setPveAccepting] = useState(false);
  const inviteSentRef = useRef(false);

  useEffect(() => {
    store.fetchRating();
    store.fetchMyDuels();
    store.fetchActiveSeason();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // PvP WebSocket
  const { sendMessage, connectionState } = useWebSocket({
    path: "/ws/pvp",
    autoConnect: true,
    onMessage: (data) => {
      switch (data.type) {
        case "queue.joined":
          store.setQueueStatus("searching");
          break;
        case "queue.status":
          store.setQueuePosition(data.data.position as number, data.data.estimated_remaining as number);
          break;
        case "match.found":
          store.setQueueStatus("matched");
          // Navigate to duel page
          setTimeout(() => {
            router.push(`/pvp/duel/${data.data.duel_id}`);
          }, 2000);
          break;
        case "pve.offer":
          store.setPvEOffer((data.data?.message as string) ?? null);
          break;
        case "queue.left":
          store.setQueueStatus("idle");
          break;
      }
    },
  });

  const handleFindMatch = useCallback(() => {
    store.setQueueStatus("searching");
    sendMessage({ type: "queue.join" });
  }, [sendMessage, store]);

  const handleCancelQueue = useCallback(() => {
    sendMessage({ type: "queue.leave" });
    store.setQueueStatus("idle");
  }, [sendMessage, store]);

  // Auto-accept PvP invitation when arriving with ?accept=challenger_id
  const acceptParam = searchParams.get("accept");
  useEffect(() => {
    if (!acceptParam || inviteSentRef.current || connectionState !== "connected") return;
    inviteSentRef.current = true;
    store.setQueueStatus("searching");
    sendMessage({ type: "queue.join", invitation_challenger_id: acceptParam });
    router.replace("/pvp", { scroll: false });
  }, [acceptParam, connectionState, sendMessage, router, store]);

  const formatTime = (iso: string) => {
    const d = new Date(iso);
    return d.toLocaleDateString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  };

  return (
    <AuthLayout>
      <div className="relative arena-grid-bg min-h-screen">
        <div className="mx-auto max-w-6xl px-4 py-8">
          {/* Header */}
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
            <div className="flex items-center justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <Swords size={20} style={{ color: "var(--accent)" }} />
                  <h1 className="font-display text-2xl font-bold tracking-[0.15em]" style={{ color: "var(--text-primary)" }}>
                    PVP АРЕНА
                  </h1>
                </div>
                <p className="mt-1 font-mono text-xs tracking-wider" style={{ color: "var(--text-muted)" }}>
                  ДУЭЛИ 1 НА 1 · GLICKO-2 РЕЙТИНГ
                </p>
              </div>
              <motion.button
                onClick={() => router.push("/pvp/leaderboard")}
                className="vh-btn-outline flex items-center gap-2 text-xs"
                whileTap={{ scale: 0.97 }}
              >
                <Trophy size={14} /> Рейтинг
              </motion.button>
            </div>
          </motion.div>

          {/* Season banner */}
          {store.activeSeason && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 }}
              className="mt-4 rounded-xl p-3 flex items-center gap-3"
              style={{ background: "rgba(255,215,0,0.06)", border: "1px solid rgba(255,215,0,0.15)" }}
            >
              <Zap size={16} style={{ color: "#FFD700" }} />
              <span className="font-mono text-xs" style={{ color: "var(--text-secondary)" }}>
                {store.activeSeason.name}
              </span>
            </motion.div>
          )}

          {/* Rating card */}
          {store.rating && !store.ratingLoading && (
            <div className="mt-6">
              <RatingCard rating={store.rating} />
            </div>
          )}

          <div className="mt-6 grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
            <div className="space-y-6">

              {/* Find Match button */}
              <motion.div
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2 }}
              >
                <motion.button
                  onClick={handleFindMatch}
                  disabled={store.queueStatus !== "idle"}
                  className="vh-btn-primary w-full flex items-center justify-center gap-3 text-lg py-5"
                  whileHover={{ scale: 1.01 }}
                  whileTap={{ scale: 0.98 }}
                >
                  {store.queueStatus !== "idle" ? (
                    <Loader2 size={20} className="animate-spin" />
                  ) : (
                    <>
                      <Swords size={22} /> Найти соперника
                    </>
                  )}
                </motion.button>
              </motion.div>

              {/* Tabs */}
              <div className="flex gap-1 rounded-xl p-1" style={{ background: "var(--input-bg)" }}>
                {(["arena", "history"] as const).map((t) => (
                  <button
                    key={t}
                    onClick={() => setTab(t)}
                    className="relative flex-1 flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 font-mono text-xs tracking-wider"
                    style={{ color: tab === t ? "var(--text-primary)" : "var(--text-muted)" }}
                  >
                    {tab === t && (
                      <motion.div
                        layoutId="pvpTab"
                        className="absolute inset-0 rounded-lg"
                        style={{ background: "var(--glass-bg)", border: "1px solid var(--glass-border)" }}
                      />
                    )}
                    <span className="relative z-10">
                      {t === "arena" ? "Арена" : "История дуэлей"}
                    </span>
                  </button>
                ))}
              </div>

              {/* History */}
              <AnimatePresence mode="wait">
                {tab === "history" && (
                  <motion.div key="history" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
                    {store.duelsLoading ? (
                      <div className="mt-8 flex justify-center">
                        <Loader2 size={20} className="animate-spin" style={{ color: "var(--accent)" }} />
                      </div>
                    ) : store.myDuels.length === 0 ? (
                      <div className="mt-12 text-center">
                        <Swords size={32} style={{ color: "var(--text-muted)" }} />
                        <p className="mt-3 text-sm" style={{ color: "var(--text-muted)" }}>Ещё нет дуэлей</p>
                      </div>
                    ) : (
                      <div className="mt-6 space-y-3">
                        {store.myDuels.map((duel, i) => {
                          const isP1 = store.rating?.user_id === duel.player1_id;
                          const myScore = isP1 ? duel.player1_total : duel.player2_total;
                          const oppScore = isP1 ? duel.player2_total : duel.player1_total;
                          const myDelta = isP1 ? duel.player1_rating_delta : duel.player2_rating_delta;
                          const isWinner = duel.winner_id === store.rating?.user_id;

                          return (
                            <motion.div
                              key={duel.id}
                              initial={{ opacity: 0, x: -12 }}
                              animate={{ opacity: 1, x: 0 }}
                              transition={{ delay: i * 0.05 }}
                              className="glass-panel p-4 flex items-center gap-4 cursor-pointer"
                              style={{
                                borderLeft: `3px solid ${duel.is_draw ? "var(--warning)" : isWinner ? "var(--neon-green)" : "var(--neon-red)"}`,
                              }}
                              onClick={() => router.push(`/pvp/duel/${duel.id}`)}
                            >
                              <div className="flex-1">
                                <div className="flex items-center gap-2">
                                  <span className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                                    {duel.is_draw ? "Ничья" : isWinner ? "Победа" : "Поражение"}
                                  </span>
                                  <span className="font-mono text-[10px] px-1.5 py-0.5 rounded" style={{ background: "var(--input-bg)", color: "var(--text-muted)" }}>
                                    {DUEL_STATUS_LABELS[duel.status] || duel.status}
                                  </span>
                                  {duel.is_pve && <span className="font-mono text-[10px]" style={{ color: "var(--warning)" }}>PvE</span>}
                                </div>
                                <div className="mt-1 font-mono text-[10px]" style={{ color: "var(--text-muted)" }}>
                                  {formatTime(duel.created_at)} · {Math.round(myScore)} vs {Math.round(oppScore)}
                                </div>
                              </div>
                              <div
                                className="font-mono text-sm font-bold"
                                style={{ color: myDelta >= 0 ? "var(--neon-green)" : "var(--neon-red)" }}
                              >
                                {myDelta >= 0 ? "+" : ""}{Math.round(myDelta)}
                              </div>
                              <ArrowRight size={14} style={{ color: "var(--text-muted)" }} />
                            </motion.div>
                          );
                        })}
                      </div>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            <FriendsPanel onChallengeSent={() => store.setQueueStatus("searching")} />
          </div>
        </div>
      </div>

      {/* Matchmaking overlay */}
      <AnimatePresence>
        {(store.queueStatus === "searching" || store.queueStatus === "matched") && (
          <MatchmakingOverlay
            status={store.queueStatus}
            position={store.queuePosition}
            estimatedWait={store.estimatedWait}
            onCancel={handleCancelQueue}
          />
        )}
      </AnimatePresence>

      {/* PvE offer modal — после 60 сек без соперника */}
      <AnimatePresence>
        {store.pvEOffer && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[300] flex items-center justify-center p-4"
            style={{ background: "rgba(0,0,0,0.6)", backdropFilter: "blur(8px)" }}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              className="glass-panel rounded-2xl p-6 max-w-sm w-full"
              style={{ border: "1px solid rgba(255,215,0,0.2)" }}
            >
              <div className="flex items-center gap-2 mb-4">
                <Zap size={20} style={{ color: "var(--warning)" }} />
                <h3 className="font-display text-lg font-bold" style={{ color: "var(--text-primary)" }}>
                  Дуэль с AI-ботом
                </h3>
              </div>
              <p className="text-sm mb-6" style={{ color: "var(--text-secondary)" }}>
                {store.pvEOffer}
              </p>
              <div className="flex gap-3">
                <motion.button
                  whileTap={{ scale: 0.98 }}
                  className="flex-1 py-2.5 rounded-xl font-mono text-xs font-bold uppercase tracking-wider flex items-center justify-center gap-2"
                  style={{ background: "var(--neon-green)", color: "#000" }}
                  disabled={pveAccepting}
                  onClick={async () => {
                    if (pveAccepting) return;
                    store.setPvEOffer(null);
                    setPveAccepting(true);
                    try {
                      const data = (await api.post("/pvp/accept-pve", {})) as { duel_id?: string };
                      if (data?.duel_id) {
                        router.push(`/pvp/duel/${data.duel_id}`);
                        return;
                      }
                    } catch {
                      // Fallback to WS
                      sendMessage({ type: "pve.accept" });
                    } finally {
                      setPveAccepting(false);
                    }
                  }}
                >
                  {pveAccepting ? <Loader2 size={14} className="animate-spin" /> : "Играть с AI"}
                </motion.button>
                <motion.button
                  whileTap={{ scale: 0.98 }}
                  className="flex-1 py-2.5 rounded-xl font-mono text-xs font-bold uppercase tracking-wider vh-btn-outline"
                  onClick={() => {
                    sendMessage({ type: "queue.leave" });
                    store.setPvEOffer(null);
                    store.setQueueStatus("idle");
                  }}
                >
                  Отмена
                </motion.button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </AuthLayout>
  );
}

export default function PvPLobbyPage() {
  return (
    <Suspense fallback={
      <AuthLayout>
        <div className="arena-grid-bg min-h-screen flex items-center justify-center">
          <Loader2 size={24} className="animate-spin" style={{ color: "var(--accent)" }} />
        </div>
      </AuthLayout>
    }>
      <PvPLobbyContent />
    </Suspense>
  );
}
