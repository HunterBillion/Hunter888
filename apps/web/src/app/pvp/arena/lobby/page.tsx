"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { motion, AnimatePresence } from "framer-motion";
import {
  Bot,
  Loader2,
  Search,
  Swords,
  Trophy,
  Users,
  X,
  Zap,
} from "lucide-react";
import { BackButton } from "@/components/ui/BackButton";
import AuthLayout from "@/components/layout/AuthLayout";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useAuthStore } from "@/stores/useAuthStore";
import { useKnowledgeStore } from "@/stores/useKnowledgeStore";
import { useSound } from "@/hooks/useSound";
import { useReducedMotion } from "@/hooks/useReducedMotion";

/* ── Constants ───────────────────────────────────────────────────────────── */

const CHALLENGE_TIMEOUT_SEC = 60;

type LobbyPhase =
  | "idle"
  | "connecting"
  | "searching"
  | "player_joined"
  | "match_ready"
  | "no_opponents"
  | "error";

/* ── Main Page ───────────────────────────────────────────────────────────── */

export default function ArenaLobbyPageWrapper() {
  return (
    <Suspense fallback={<div className="flex h-screen items-center justify-center"><div className="text-lg text-[var(--text-muted)]">Loading...</div></div>}>
      <ArenaLobbyPage />
    </Suspense>
  );
}

function ArenaLobbyPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const reducedMotion = useReducedMotion();
  const { playSound } = useSound();

  const user = useAuthStore((s) => s.user);
  const userId = user?.id || "";
  const username = user?.full_name || user?.email || "";

  const maxPlayers = parseInt(searchParams.get("mode") || "2", 10) === 4 ? 4 : 2;
  const category = searchParams.get("category") || undefined;

  const [phase, setPhase] = useState<LobbyPhase>("idle");
  const [challengeId, setChallengeId] = useState<string | null>(null);
  const [playersJoined, setPlayersJoined] = useState(1); // challenger counts as 1
  const [elapsed, setElapsed] = useState(0);
  const [matchSessionId, setMatchSessionId] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [matchPlayers, setMatchPlayers] = useState<
    { user_id: string; name: string; is_bot: boolean }[]
  >([]);

  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const searchStartRef = useRef<number | null>(null);
  const autoStarted = useRef(false);

  const store = useKnowledgeStore();

  /* ── WebSocket ─────────────────────────────────────────────────────────── */

  const handleMessage = useCallback(
    (msg: { type: string; data?: Record<string, unknown> }) => {
      const data: Record<string, unknown> = { ...msg, ...(msg.data || {}) };
      const type = msg.type;

      switch (type) {
        case "pvp.searching": {
          setChallengeId(data.challenge_id as string);
          setPhase("searching");
          searchStartRef.current = Date.now();
          break;
        }

        case "pvp.player_joined": {
          const count = (data.players_count as number) || playersJoined + 1;
          setPlayersJoined(count);
          setPhase("player_joined");
          playSound("challenge", 0.4);
          break;
        }

        case "pvp.match_ready": {
          const sid = data.session_id as string;
          const players = (data.players as { user_id: string; name: string; is_bot: boolean }[]) || [];
          setMatchSessionId(sid);
          setMatchPlayers(players);
          setPhase("match_ready");
          playSound("challenge", 0.5);

          // Reset PvP store for fresh match
          store.resetPvP();

          // Navigate to match after brief countdown
          setTimeout(() => {
            router.push(`/pvp/arena/${sid}`);
          }, 2000);
          break;
        }

        case "pvp.no_opponents": {
          setPhase("no_opponents");
          break;
        }

        case "pvp.bot_joined": {
          const botName = data.bot_name as string;
          setMatchPlayers((prev) => [
            ...prev,
            { user_id: data.bot_id as string, name: botName, is_bot: true },
          ]);
          playSound("challenge", 0.3);
          break;
        }

        case "pvp.search_cancelled": {
          setPhase("idle");
          setChallengeId(null);
          setPlayersJoined(1);
          break;
        }

        case "error": {
          setPhase("error");
          setErrorMsg((data.message as string) || "Unknown error");
          break;
        }
      }
    },
    [playersJoined, playSound, router, store],
  );

  const { sendMessage, isConnected, connectionState } = useWebSocket({
    path: "/ws/knowledge",
    onMessage: handleMessage,
    autoConnect: true,
  });

  /* ── Auto-start search once connected ──────────────────────────────────── */

  useEffect(() => {
    if (isConnected && !autoStarted.current && phase === "idle") {
      autoStarted.current = true;
      setPhase("connecting");

      // Small delay to let WS stabilize
      const t = setTimeout(() => {
        sendMessage({
          type: "pvp.find_opponent",
          data: { max_players: maxPlayers, category },
        });
      }, 300);
      return () => clearTimeout(t);
    }
  }, [isConnected, phase, sendMessage, maxPlayers, category]);

  /* ── Elapsed timer ─────────────────────────────────────────────────────── */

  useEffect(() => {
    if (phase === "searching" || phase === "player_joined") {
      timerRef.current = setInterval(() => {
        if (searchStartRef.current) {
          setElapsed(Math.floor((Date.now() - searchStartRef.current) / 1000));
        }
      }, 1000);
    } else {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [phase]);

  /* ── Actions ───────────────────────────────────────────────────────────── */

  const handleCancel = useCallback(() => {
    sendMessage({ type: "pvp.cancel_search" });
    setPhase("idle");
    setChallengeId(null);
    setPlayersJoined(1);
    setElapsed(0);
    router.push("/pvp");
  }, [sendMessage, router]);

  const handlePlayWithBot = useCallback(() => {
    sendMessage({ type: "pvp.play_with_bot" });
    setPhase("connecting");
  }, [sendMessage]);

  const handleRetry = useCallback(() => {
    setPhase("idle");
    autoStarted.current = false;
    setErrorMsg(null);
    setChallengeId(null);
    setPlayersJoined(1);
    setElapsed(0);
  }, []);

  /* ── Progress ──────────────────────────────────────────────────────────── */

  const progress = Math.min(100, Math.round((elapsed / CHALLENGE_TIMEOUT_SEC) * 100));
  const remaining = Math.max(0, CHALLENGE_TIMEOUT_SEC - elapsed);

  /* ── Render ────────────────────────────────────────────────────────────── */

  return (
    <AuthLayout>
      <div className="relative arena-grid-bg min-h-screen flex items-center justify-center">
        {/* Back button */}
        <div className="absolute top-6 left-6">
          <BackButton href="/pvp" label="К арене" />
        </div>

        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="glass-panel max-w-md w-full mx-4 p-8 text-center relative overflow-hidden"
        >
          {/* Top accent line */}
          <div
            className="absolute top-0 left-0 right-0 h-[2px]"
            style={{
              background:
                maxPlayers === 4
                  ? "linear-gradient(90deg, transparent, #F59E0B, transparent)"
                  : "linear-gradient(90deg, transparent, #EF4444, transparent)",
            }}
          />

          {/* Header */}
          <div className="mb-6">
            <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full mb-4"
              style={{
                background: maxPlayers === 4 ? "rgba(245,158,11,0.1)" : "rgba(239,68,68,0.1)",
                border: `2px solid ${maxPlayers === 4 ? "rgba(245,158,11,0.2)" : "rgba(239,68,68,0.2)"}`,
              }}
            >
              {maxPlayers === 4 ? (
                <Users size={28} style={{ color: "var(--warning)" }} />
              ) : (
                <Swords size={28} style={{ color: "var(--danger)" }} />
              )}
            </div>
            <h2
              className="font-display text-xl font-bold tracking-wider"
              style={{ color: "var(--text-primary)" }}
            >
              {maxPlayers === 4 ? "КОМАНДНЫЙ БОЙ" : "ДУЭЛЬ 1 НА 1"}
            </h2>
            <p className="mt-1 font-mono text-xs" style={{ color: "var(--text-muted)" }}>
              АРЕНА ЗНАНИЙ · 10 РАУНДОВ · {maxPlayers} ИГРОКА
            </p>
          </div>

          <AnimatePresence mode="wait">
            {/* ── Connecting / Idle ── */}
            {(phase === "idle" || phase === "connecting") && (
              <motion.div
                key="connecting"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="py-8"
              >
                <Loader2
                  size={32}
                  className="mx-auto animate-spin"
                  style={{ color: "var(--accent)" }}
                />
                <p className="mt-4 text-sm" style={{ color: "var(--text-secondary)" }}>
                  {connectionState === "connected" ? "Создаём вызов..." : "Подключение..."}
                </p>
              </motion.div>
            )}

            {/* ── Searching ── */}
            {(phase === "searching" || phase === "player_joined") && (
              <motion.div
                key="searching"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
              >
                {/* Search animation — smooth pulsing rings */}
                <div className="relative mx-auto w-24 h-24 mb-6">
                  <motion.div
                    className="absolute inset-0 rounded-full border-2 border-dashed"
                    style={{
                      borderColor: maxPlayers === 4 ? "var(--warning)" : "var(--danger)",
                      opacity: 0.6,
                    }}
                    animate={reducedMotion ? {} : { rotate: 360, scale: [1, 1.04, 1] }}
                    transition={
                      reducedMotion
                        ? {}
                        : { rotate: { duration: 8, repeat: Infinity, ease: "linear" }, scale: { duration: 2, repeat: Infinity, ease: "easeInOut" } }
                    }
                  />
                  <motion.div
                    className="absolute inset-3 rounded-full border"
                    style={{ borderColor: "rgba(124,106,232,0.25)" }}
                    animate={reducedMotion ? {} : { rotate: -360, opacity: [0.3, 0.6, 0.3] }}
                    transition={
                      reducedMotion
                        ? {}
                        : { rotate: { duration: 12, repeat: Infinity, ease: "linear" }, opacity: { duration: 3, repeat: Infinity, ease: "easeInOut" } }
                    }
                  />
                  <div className="absolute inset-0 flex items-center justify-center">
                    <motion.div
                      animate={reducedMotion ? {} : { scale: [1, 1.08, 1] }}
                      transition={reducedMotion ? {} : { duration: 2, repeat: Infinity, ease: "easeInOut" }}
                    >
                      <Search size={28} style={{ color: "var(--accent)" }} />
                    </motion.div>
                  </div>
                </div>

                <p className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                  Поиск соперников...
                </p>

                {/* Player counter for 4-player */}
                {maxPlayers === 4 && (
                  <div className="mt-3 flex items-center justify-center gap-2">
                    <Users size={14} style={{ color: "var(--text-muted)" }} />
                    <span className="font-mono text-xs" style={{ color: "var(--text-secondary)" }}>
                      {playersJoined} / {maxPlayers} игроков
                    </span>
                  </div>
                )}

                {phase === "player_joined" && (
                  <motion.p
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="mt-2 text-xs"
                    style={{ color: "var(--success)" }}
                  >
                    Игрок присоединился!
                  </motion.p>
                )}

                {/* Timer & progress */}
                <div className="mt-4 space-y-2">
                  <div className="flex justify-between text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                    <span>{elapsed}с</span>
                    <span>{remaining}с осталось</span>
                  </div>
                  <div className="h-1 rounded-full overflow-hidden" style={{ background: "var(--input-bg)" }}>
                    <motion.div
                      className="h-full rounded-full"
                      style={{
                        background: `linear-gradient(90deg, ${maxPlayers === 4 ? "var(--warning)" : "var(--danger)"}, var(--accent))`,
                        width: `${progress}%`,
                      }}
                      transition={{ duration: 0.5 }}
                    />
                  </div>
                </div>

                {/* Cancel button */}
                <motion.button
                  whileTap={{ scale: 0.97 }}
                  onClick={handleCancel}
                  className="mt-6 flex items-center justify-center gap-2 mx-auto px-6 py-2.5 rounded-lg text-xs font-mono"
                  style={{
                    background: "rgba(255,255,255,0.05)",
                    border: "1px solid var(--glass-border)",
                    color: "var(--text-secondary)",
                  }}
                >
                  <X size={14} /> Отменить поиск
                </motion.button>
              </motion.div>
            )}

            {/* ── Match Ready ── */}
            {phase === "match_ready" && (
              <motion.div
                key="match_ready"
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0 }}
                className="py-4"
              >
                <motion.div
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  transition={{ type: "spring", stiffness: 180, damping: 14 }}
                  className="mx-auto flex h-16 w-16 items-center justify-center rounded-full mb-4"
                  style={{ background: "rgba(61,220,132,0.1)", border: "2px solid rgba(61,220,132,0.3)" }}
                >
                  <Zap size={28} style={{ color: "var(--success)" }} />
                </motion.div>

                <h3
                  className="font-display text-lg font-bold"
                  style={{ color: "var(--success)" }}
                >
                  СОПЕРНИК НАЙДЕН!
                </h3>

                {/* Player cards */}
                <div className="mt-4 space-y-2">
                  {matchPlayers.map((p) => (
                    <div
                      key={p.user_id}
                      className="flex items-center gap-3 px-4 py-2 rounded-lg text-left"
                      style={{
                        background: p.user_id === userId ? "rgba(124,106,232,0.1)" : "rgba(255,255,255,0.03)",
                        border: `1px solid ${p.user_id === userId ? "rgba(124,106,232,0.2)" : "var(--glass-border)"}`,
                      }}
                    >
                      <div
                        className="w-8 h-8 rounded-full flex items-center justify-center text-sm"
                        style={{ background: "var(--input-bg)" }}
                      >
                        {p.is_bot ? <Bot size={14} /> : p.name.charAt(0).toUpperCase()}
                      </div>
                      <div>
                        <p className="text-xs font-medium" style={{ color: "var(--text-primary)" }}>
                          {p.name}
                        </p>
                        <p className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                          {p.is_bot ? "AI Соперник" : p.user_id === userId ? "Вы" : "Игрок"}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>

                <p className="mt-4 text-xs font-mono animate-pulse" style={{ color: "var(--text-muted)" }}>
                  Матч начинается...
                </p>
              </motion.div>
            )}

            {/* ── No Opponents ── */}
            {phase === "no_opponents" && (
              <motion.div
                key="no_opponents"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="py-4"
              >
                <div
                  className="mx-auto flex h-16 w-16 items-center justify-center rounded-full mb-4"
                  style={{ background: "rgba(245,158,11,0.1)", border: "2px solid rgba(245,158,11,0.2)" }}
                >
                  <Users size={28} style={{ color: "var(--warning)" }} />
                </div>

                <h3 className="font-display text-lg font-bold" style={{ color: "var(--text-primary)" }}>
                  Соперники не найдены
                </h3>
                <p className="mt-2 text-xs" style={{ color: "var(--text-muted)" }}>
                  Сейчас нет доступных игроков. Можете сыграть с AI-соперником!
                </p>

                <div className="mt-6 space-y-3">
                  <motion.button
                    whileTap={{ scale: 0.97 }}
                    onClick={handlePlayWithBot}
                    className="btn-neon w-full flex items-center justify-center gap-2 py-3"
                  >
                    <Bot size={16} /> Играть с AI
                  </motion.button>

                  <motion.button
                    whileTap={{ scale: 0.97 }}
                    onClick={handleRetry}
                    className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg text-xs font-mono"
                    style={{
                      background: "rgba(255,255,255,0.05)",
                      border: "1px solid var(--glass-border)",
                      color: "var(--text-secondary)",
                    }}
                  >
                    <Search size={14} /> Повторить поиск
                  </motion.button>

                  <button
                    onClick={() => router.push("/pvp")}
                    className="w-full text-center text-xs py-2"
                    style={{ color: "var(--text-muted)" }}
                  >
                    Вернуться в лобби
                  </button>
                </div>
              </motion.div>
            )}

            {/* ── Error ── */}
            {phase === "error" && (
              <motion.div
                key="error"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="py-4"
              >
                <div
                  className="mx-auto flex h-16 w-16 items-center justify-center rounded-full mb-4"
                  style={{ background: "rgba(239,68,68,0.1)", border: "2px solid rgba(239,68,68,0.2)" }}
                >
                  <X size={28} style={{ color: "var(--danger)" }} />
                </div>

                <h3 className="text-lg font-bold" style={{ color: "var(--danger)" }}>
                  Ошибка
                </h3>
                <p className="mt-2 text-xs" style={{ color: "var(--text-muted)" }}>
                  {errorMsg || "Не удалось создать матч"}
                </p>

                <div className="mt-6 space-y-3">
                  <motion.button
                    whileTap={{ scale: 0.97 }}
                    onClick={handleRetry}
                    className="btn-neon w-full flex items-center justify-center gap-2 py-3"
                  >
                    Попробовать снова
                  </motion.button>
                  <button
                    onClick={() => router.push("/pvp")}
                    className="w-full text-center text-xs py-2"
                    style={{ color: "var(--text-muted)" }}
                  >
                    Вернуться в лобби
                  </button>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>
      </div>
    </AuthLayout>
  );
}
