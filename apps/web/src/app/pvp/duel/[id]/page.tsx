"use client";

import { useEffect, useState, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { logger } from "@/lib/logger";
import { Swords, Loader2, LogOut } from "lucide-react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useAuthBootstrap } from "@/hooks/useAuthBootstrap";
import { usePvPStore } from "@/stores/usePvPStore";
import { useNotificationStore } from "@/stores/useNotificationStore";
import { DuelChat } from "@/components/pvp/DuelChat";
// 2026-05-01: 12-portrait avatar library
import {
  usePlayerAvatar,
  resolveOpponentAvatar,
} from "@/components/pvp/PixelAvatarLibrary";
import { useGamificationStore } from "@/stores/useGamificationStore";
import { DuelResult } from "@/components/pvp/DuelResult";
import { PvPVictoryScreen } from "@/components/pvp/PvPVictoryScreen";
import { Confetti } from "@/components/ui/Confetti";
import { useScreenShake } from "@/components/ui/ScreenShake";
import { api } from "@/lib/api";
import { sanitizeText } from "@/lib/sanitize";
import { ErrorBoundary } from "@/components/errors/ErrorBoundary";
import type { PvPDuel } from "@/types";
// Sprint 4 (2026-04-20): sfx pack — duel-tuned cues (round start / result)
import { useSFX } from "@/components/arena/sfx/useSFX";
// Phase A (2026-04-20): visual parity with Arena Quiz —
//  • CoachingCard shows what the player SHOULD have said post-round
//  • ArenaAudioPlayer renders TTS narration from pvp.audio_ready
//  • useLifelines wires hint/skip quota (Duel: 0/1/0) to the REST API
//  • useSpeechRecognition gives a floating mic that appends to chat input
//  (CountdownOverlay 3-2-1 removed 2026-05-03 per user feedback.)
import { CoachingCard, type CoachingPayload } from "@/components/arena/reveal/CoachingCard";
import { ArenaAudioPlayer } from "@/components/pvp/ArenaAudioPlayer";
import { useLifelines } from "@/components/arena/hooks/useLifelines";
import { useSpeechRecognition } from "@/hooks/useSpeechRecognition";
import { themeFor } from "@/components/arena/themes";
import { Mic, MicOff, Lightbulb, SkipForward } from "lucide-react";
// PR-3 Phase A (2026-05-05): wire arena visuals so the page stops
// looking like a generic /training chat. User reported "ПвП выглядит
// как тренировка" on duel 02bd9a42 — VsBanner + ArenaBackground +
// explicit role badges close that gap without rewriting the page.
import { VsBanner } from "@/components/pvp/VsBanner";
import { ArenaBackground } from "@/components/pvp/ArenaBackground";

export default function DuelPageWrapper() {
  return (
    <ErrorBoundary>
      <DuelPage />
    </ErrorBoundary>
  );
}

function DuelPage() {
  const { ready: authReady } = useAuthBootstrap();
  const params = useParams();
  const router = useRouter();
  const duelId = params.id as string;
  const store = usePvPStore();
  const shake = useScreenShake();
  const sfx = useSFX();
  // 2026-05-01: подписка на level (вместо snapshot getState) — если игрок
  // сделал level-up прямо в дуэли (редкий, но возможный кейс на финале
  // последнего раунда), аватар обновится без ручного refetch.
  const playerLevel = useGamificationStore((s) => s.level);
  const selfAvatar = usePlayerAvatar(playerLevel);
  const [confettiTrigger, setConfettiTrigger] = useState(0);
  const [showVictoryScreen, setShowVictoryScreen] = useState(true);
  const [input, setInput] = useState("");
  const [duelMeta, setDuelMeta] = useState<PvPDuel | null>(null);
  const [statusNotice, setStatusNotice] = useState<string | null>(null);
  const [showExitConfirm, setShowExitConfirm] = useState(false);
  const [loadTimeout, setLoadTimeout] = useState(false);
  const [earlyExit, setEarlyExit] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Phase A (2026-04-20) — Arena visual parity (CoachingCard, Countdown,
  // ArenaAudioPlayer, lifelines, microphone)
  const theme = themeFor("duel");
  const lifelines = useLifelines({
    sessionId: duelId || null,
    mode: "duel",
    enabled: !!duelId,
  });
  const [coachingOpen, setCoachingOpen] = useState(false);
  const [coachingPayload, setCoachingPayload] = useState<CoachingPayload | null>(null);
  // Issue #168 — surfaces backend PR #120 ``judge.degraded`` event so
  // the player knows the score is a neutral fallback (LLM down /
  // JSON parse fail / all providers in circuit-breaker), not a real
  // verdict. Cleared on the next round so the banner doesn't linger.
  const [judgeDegraded, setJudgeDegraded] = useState<
    { round_number: number; reason: string } | null
  >(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  // PR-3 Phase A: VS-banner overlay shown for ~2.2s when duel.brief lands
  // for the first time. Gives the player a clear "арена начинается" beat
  // instead of dropping them into a chat that looks like /training.
  const [vsOpen, setVsOpen] = useState(false);
  const vsTriggeredRef = useRef(false);
  const speech = useSpeechRecognition({
    lang: "ru-RU",
    onResult: (text) => setInput((prev) => (prev ? `${prev} ${text}`.trim() : text)),
    onInterim: () => void 0,
    onError: () => void 0,
  });
  const micActive = speech.status === "listening" || speech.status === "processing";

  // 2026-04-18 fix: REST pre-check. If duel is already cancelled/completed
  // before WS hands us a duel.brief we were stuck on "ПОДКЛЮЧЕНИЕ К АРЕНЕ..."
  // forever. Fetch current status; if terminal — show clear exit UI.
  useEffect(() => {
    if (!duelId || !authReady) return;
    let aborted = false;
    (async () => {
      try {
        const meta = await api.get<PvPDuel>(`/pvp/duels/${duelId}`);
        if (aborted) return;
        setDuelMeta(meta);
        if (meta?.status === "cancelled") {
          setEarlyExit("Эта дуэль уже отменена.");
        } else if (meta?.status === "completed") {
          setEarlyExit("Эта дуэль уже завершена.");
        }
      } catch (e) {
        logger.warn("Failed to pre-fetch duel status", e);
      }
    })();
    return () => { aborted = true; };
  }, [duelId, authReady]);

  // Safety timeout: if WS hasn't delivered duel.brief/duel.state within 18s,
  // show "Cannot connect" escape hatch instead of an infinite spinner.
  //
  // History:
  //   - 10s → 6s on 2026-05-03 (user complained about "infinite loading")
  //   - 6s → 18s on 2026-05-05 (PR-1) — prod audit found 7/11 duels
  //     cancelled because the bot opener LLM call inside _start_round can
  //     legitimately take up to _BOT_LLM_TIMEOUT=15s on a cold local stack.
  //     Showing "Cannot connect" at 6s was racing the bot's first reply
  //     and pushing users to close the tab → 60s reconnect-grace fired →
  //     duel cancelled with terminal_outcome=NULL. 18s gives the bot
  //     LLM (15s) plus 3s for round/judge dispatch to land before we
  //     blame the network.
  useEffect(() => {
    if (store.duelBrief || store.duelResult || earlyExit) return;
    const t = setTimeout(() => setLoadTimeout(true), 18000);
    return () => clearTimeout(t);
  }, [store.duelBrief, store.duelResult, earlyExit]);

  // PR-3 Phase A: trigger VS-banner the first time duel.brief lands.
  // ``vsTriggeredRef`` guards against re-trigger on reconnect (duel.state
  // also surfaces brief data) so the banner doesn't pop up mid-round.
  useEffect(() => {
    if (!store.duelBrief || vsTriggeredRef.current || store.duelResult) return;
    vsTriggeredRef.current = true;
    setVsOpen(true);
  }, [store.duelBrief, store.duelResult]);

  // 2026-04-20: mountedRef — защита от зависших таймеров после unmount.
  // restartTimer может быть вызван асинхронно WS-сообщением (round.start),
  // которое пришло УЖЕ ПОСЛЕ того как юзер ушёл со страницы. Раньше
  // setInterval жил в памяти и продолжал мутировать usePvPStore
  // каждую секунду. Теперь — guard при каждом тике + при создании.
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  const restartTimer = (seconds: number) => {
    if (timerRef.current) clearInterval(timerRef.current);
    if (!mountedRef.current) return; // не стартуем таймер после unmount
    store.setTimeRemaining(seconds);
    timerRef.current = setInterval(() => {
      if (!mountedRef.current) {
        if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
        return;
      }
      // Pause countdown when WS is disconnected — server keeps its own timer
      if (usePvPStore.getState().timeRemaining <= 0) {
        if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
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
          // Issue #168 — clear the degraded-judge banner when a new
          // round starts. Each banner is scoped to a single round.
          setJudgeDegraded(null);
          // 2026-05-03: pre-round 3-2-1 countdown removed per user feedback —
          // no countdowns anywhere in the arena flow.
          sfx.play("round_start");
          break;

        // Phase A — accept TTS narration URL and render ArenaAudioPlayer
        case "pvp.audio_ready":
          if (typeof d.audio_url === "string") setAudioUrl(d.audio_url);
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
          // 2026-05-05 hotfix: pass through ``client_msg_id`` and
          // ``server_msg_id`` from the echo payload so usePvPStore.addMessage
          // can dedup the optimistic render. Backend ws/pvp.py:1996 emits
          // ``client_msg_id`` when the sender originated the message; without
          // forwarding it here every user message rendered twice (optimistic
          // bubble + WS echo as a fresh row) — the visible "дублирует" bug
          // user reported on duel 02bd9a42.
          store.addMessage({
            id: store.nextMsgId(),
            sender_role: (typeof d.sender_role === "string" ? d.sender_role : "client") as "seller" | "client",
            text: String(d.text || ""),
            round: Number(d.round || 1),
            timestamp: new Date().toISOString(),
            client_msg_id: typeof d.client_msg_id === "string" ? d.client_msg_id : undefined,
            server_msg_id: typeof d.server_msg_id === "string" ? d.server_msg_id : undefined,
          });
          break;

        case "judge.score": {
          const selling = Number(d.selling_score || 0);
          const acting = Number(d.acting_score || 0);
          const legal = Number(d.legal_accuracy || 0);
          const avg = (selling + acting + legal) / 3;
          store.setJudgeScore({
            selling_score: selling,
            acting_score: acting,
            legal_accuracy: legal,
          });
          // Subtle cue tied to judge verdict — tick for pass, wrong for fail
          if (avg >= 60) sfx.play("tick");
          else if (avg < 40) sfx.play("wrong");
          // Phase A — unpack coaching payload and open the CoachingCard so
          // the player sees what they SHOULD have said + статьи.
          const coaching = (d as Record<string, unknown>).coaching as
            | { tip?: string; ideal_reply?: string; key_articles?: string[] }
            | undefined;
          const summary = (d as Record<string, unknown>).summary as
            | { seller_flags?: string[]; legal_details?: Array<Record<string, unknown>> }
            | undefined;
          if (coaching && (coaching.tip || coaching.ideal_reply || (coaching.key_articles?.length ?? 0) > 0)) {
            setCoachingPayload({
              tip: String(coaching.tip ?? ""),
              idealReply: String(coaching.ideal_reply ?? ""),
              keyArticles: Array.isArray(coaching.key_articles) ? coaching.key_articles : [],
              flags: Array.isArray(summary?.seller_flags) ? summary?.seller_flags : [],
              legalDetails: Array.isArray(summary?.legal_details) ? (summary?.legal_details as CoachingPayload["legalDetails"]) : [],
              scoreNormalised: Math.round(((selling + legal) / 70) * 100),
            });
            setCoachingOpen(true);
          }
          break;
        }

        case "round.time_up":
          if (timerRef.current) clearInterval(timerRef.current);
          store.setTimeRemaining(0);
          break;

        case "judge.degraded": {
          // Issue #168 — backend PR #120 explicit fallback signal.
          // Pin the round + reason; the banner clears in the
          // round-change effect below.
          const roundNum = Number(d.round_number ?? d.round ?? 0);
          const reason = String(d.reason ?? "llm_error");
          setJudgeDegraded({ round_number: roundNum, reason });
          break;
        }

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
            sfx.play("correct");
            sfx.play("round_end");
          } else if (!isDraw) {
            shake("error");
            sfx.play("wrong");
          } else {
            sfx.play("round_end");
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

        case "ap.earned": {
          const apAmount = Number(d.amount || 0);
          if (apAmount > 0) {
            window.dispatchEvent(new CustomEvent("gamification", {
              detail: { type: "xp-gain", amount: apAmount },
            }));
          }
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
            // 2026-05-03: also surface as a toast — the inline status
            // banner is easy to miss above the chat scroll.
            useNotificationStore.getState().addToast({
              type: "error",
              title: "Ошибка дуэли",
              body: data.data.detail,
            });
          }
          break;
      }
    },
  });

  useEffect(() => {
    store.resetDuel();
  }, [duelId]); // eslint-disable-line react-hooks/exhaustive-deps -- store.resetDuel is a stable Zustand action

  // Sprint 4 — preload the sfx pack so first cue fires instantly
  useEffect(() => {
    sfx.prime();
  }, [sfx]);

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
    // Issue #167 — optimistic add + server-echo reconcile via client_msg_id.
    const clientMsgId =
      typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
        ? crypto.randomUUID()
        : `c-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;

    store.addMessage({
      id: store.nextMsgId(),
      sender_role: store.myRole,
      text,
      round: store.roundNumber,
      timestamp: new Date().toISOString(),
      client_msg_id: clientMsgId,
      pending: true,
    });
    sendMessage({ type: "duel.message", text, client_msg_id: clientMsgId });
    setInput("");
  };

  // Deduplicate duel.message — backend echo arrives after optimistic add would cause double.
  // Currently we rely on backend echo only. If bot fails, user still sees their own messages.

  // ═══ Loading / early-exit / safety-timeout state ═══ (2026-04-18)
  if (!store.duelBrief && !store.duelResult) {
    // Terminal duel (REST pre-check) — show clear exit UI.
    if (earlyExit) {
      return (
        <div
          className="flex h-screen flex-col items-center justify-center px-6 text-center"
          style={{ background: "var(--bg-primary)" }}
        >
          <div
            className="p-6 max-w-md w-full"
            style={{
              background: "var(--bg-panel)",
              border: "2px solid var(--danger)",
              borderRadius: 0,
              boxShadow: "4px 4px 0 0 var(--danger)",
            }}
          >
            <div className="font-pixel text-sm uppercase tracking-widest mb-3" style={{ color: "var(--danger)" }}>
              ✖ ДУЭЛЬ НЕДОСТУПНА
            </div>
            <p className="text-base mb-5" style={{ color: "var(--text-primary)" }}>{earlyExit}</p>
            <button
              onClick={() => router.push("/pvp")}
              className="w-full py-3 px-4 font-pixel text-sm uppercase tracking-widest"
              style={{
                background: "var(--accent)",
                color: "#fff",
                border: "2px solid var(--accent)",
                borderRadius: 0,
                boxShadow: "3px 3px 0 0 #000",
              }}
            >
              ▶ ВЕРНУТЬСЯ НА АРЕНУ
            </button>
          </div>
        </div>
      );
    }

    // Safety timeout — WS never delivered state.
    if (loadTimeout) {
      return (
        <div
          className="flex h-screen flex-col items-center justify-center px-6 text-center"
          style={{ background: "var(--bg-primary)" }}
        >
          <div
            className="p-6 max-w-md w-full"
            style={{
              background: "var(--bg-panel)",
              border: "2px solid var(--warning)",
              borderRadius: 0,
              boxShadow: "4px 4px 0 0 var(--warning)",
            }}
          >
            <div className="font-pixel text-sm uppercase tracking-widest mb-3" style={{ color: "var(--warning)" }}>
              ⚠ НЕТ СВЯЗИ С АРЕНОЙ
            </div>
            <p className="text-base mb-5" style={{ color: "var(--text-primary)" }}>
              Не удалось подключиться к дуэли. Возможно, соперник вышел или сервер недоступен.
            </p>
            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => { setLoadTimeout(false); router.refresh(); }}
                className="flex-1 py-3 px-4 font-pixel text-sm uppercase tracking-widest"
                style={{
                  background: "var(--input-bg)",
                  color: "var(--text-primary)",
                  border: "2px solid var(--border-color)",
                  borderRadius: 0,
                  boxShadow: "2px 2px 0 0 var(--border-color)",
                }}
              >
                ↻ ПОВТОР
              </button>
              <button
                onClick={() => router.push("/pvp")}
                className="flex-1 py-3 px-4 font-pixel text-sm uppercase tracking-widest"
                style={{
                  background: "var(--accent)",
                  color: "#fff",
                  border: "2px solid var(--accent)",
                  borderRadius: 0,
                  boxShadow: "3px 3px 0 0 #000",
                }}
              >
                ▶ НА АРЕНУ
              </button>
            </div>
          </div>
        </div>
      );
    }

    // Normal loading state — pixel-styled.
    // 2026-05-03: добавлена кнопка «Назад на арену» в самом spinner-е, чтобы
    // пользователь мог уйти не дожидаясь 10-сек таймаута. Раньше «вечная
    // загрузка» — теперь всегда есть escape hatch.
    return (
      <div
        className="flex h-screen flex-col items-center justify-center px-6 gap-5"
        style={{
          background: "var(--bg-primary)",
          backgroundImage: `
            repeating-linear-gradient(0deg, transparent 0, transparent 23px, rgba(107,77,199,0.04) 23px, rgba(107,77,199,0.04) 24px),
            repeating-linear-gradient(90deg, transparent 0, transparent 23px, rgba(107,77,199,0.04) 23px, rgba(107,77,199,0.04) 24px)
          `,
        }}
      >
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ duration: 1.5, repeat: Infinity, ease: "linear" }}
          style={{
            width: 48,
            height: 48,
            border: "4px solid var(--accent)",
            borderTopColor: "transparent",
            borderRadius: 0,
          }}
        />
        <span className="font-pixel text-sm uppercase tracking-widest text-center" style={{ color: "var(--accent)", textShadow: "0 0 6px var(--accent-glow)" }}>
          ▶ ПОДКЛЮЧЕНИЕ К АРЕНЕ
        </span>
        <button
          onClick={() => router.push("/pvp")}
          className="mt-4 px-5 py-2.5 font-pixel text-xs uppercase tracking-widest"
          style={{
            background: "transparent",
            color: "var(--text-muted)",
            border: "2px solid var(--border-color)",
            borderRadius: 0,
            boxShadow: "2px 2px 0 0 var(--border-color)",
            cursor: "pointer",
          }}
        >
          ← Назад на арену
        </button>
        <div className="mt-2 flex gap-1">
          {[0, 1, 2, 3].map((i) => (
            <motion.span
              key={i}
              style={{ width: 6, height: 6, background: "var(--accent)", borderRadius: 0 }}
              animate={{ opacity: [0.2, 1, 0.2] }}
              transition={{ duration: 1, repeat: Infinity, delay: i * 0.15 }}
            />
          ))}
        </div>
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
    const myRatingDelta = isP1 ? store.duelResult.player1_rating_delta : store.duelResult.player2_rating_delta;

    // Phase 1: Victory Screen (full-screen reveal), then Phase 2: DuelResult (detailed breakdown)
    if (showVictoryScreen) {
      return (
        <AnimatePresence>
          <PvPVictoryScreen
            isWinner={isWinner}
            isDraw={store.duelResult.is_draw}
            myScore={myTotal}
            opponentScore={oppTotal}
            ratingDelta={myRatingDelta}
            onContinue={() => setShowVictoryScreen(false)}
          />
        </AnimatePresence>
      );
    }

    return (<>
      <DuelResult
        myTotal={myTotal}
        opponentTotal={oppTotal}
        isWinner={isWinner}
        isDraw={store.duelResult.is_draw}
        isPvE={store.duelResult.is_pve}
        ratingChangeApplied={store.duelResult.rating_change_applied}
        myRatingDelta={myRatingDelta}
        summary={store.duelResult.summary}
        duelId={duelId}
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

  if (!authReady) {
    return (
      <div className="flex h-screen items-center justify-center" style={{ background: "var(--bg-primary)" }}>
        <Loader2 size={28} className="animate-spin" style={{ color: "var(--accent)" }} />
      </div>
    );
  }

  // PR-3 Phase A: derive labels for VsBanner + role badges.
  const myName = store.duelBrief?.you?.name || "ВЫ";
  const oppName = store.duelBrief?.opponent?.name || (store.duelBrief?.is_pve ? "БОТ" : "СОПЕРНИК");
  const myTier = store.duelBrief?.you?.tier;
  const oppTier = store.duelBrief?.opponent?.tier;
  const myRoleLabel = store.myRole === "seller" ? "ПРОДАВЕЦ" : store.myRole === "client" ? "КЛИЕНТ" : "—";
  const oppRoleLabel = store.myRole === "seller" ? "КЛИЕНТ" : store.myRole === "client" ? "ПРОДАВЕЦ" : "—";

  return (
    <ArenaBackground tier={myTier} className="flex h-screen flex-col">

      {/* PR-3 Phase A: VS-banner overlay on first duel.brief.
          Auto-closes after 2.2s; user can still see the chat under it
          (z-index 9000 covers everything but exit-confirm dialog). */}
      <VsBanner
        open={vsOpen}
        leftName={myName.toUpperCase()}
        rightName={oppName.toUpperCase()}
        leftTier={myTier}
        rightTier={oppTier}
        onDone={() => setVsOpen(false)}
      />

      {/* Exit confirmation overlay */}
      {showExitConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: "var(--overlay-bg)", backdropFilter: "blur(4px)" }}>
          <div className="rounded-xl p-6 max-w-sm w-full mx-4" style={{ background: "var(--bg-secondary)", border: "1px solid var(--border-color)" }}>
            <h3 className="text-lg font-bold mb-2" style={{ color: "var(--text-primary)" }}>Выйти из дуэли?</h3>
            <p className="text-sm mb-5" style={{ color: "var(--text-muted)" }}>Прогресс текущей дуэли будет потерян.</p>
            <div className="flex gap-3">
              <button
                onClick={() => setShowExitConfirm(false)}
                className="flex-1 py-2.5 rounded-lg text-sm font-medium"
                style={{ background: "var(--input-bg)", color: "var(--text-primary)", border: "1px solid var(--border-color)" }}
              >
                Остаться
              </button>
              <button
                onClick={() => {
                  sendMessage({ type: "duel.leave" });
                  store.resetDuel();
                  router.push("/pvp");
                }}
                className="flex-1 py-2.5 rounded-lg text-sm font-medium"
                style={{ background: "var(--danger)", color: "#fff" }}
              >
                Выйти
              </button>
            </div>
          </div>
        </div>
      )}

      {/* PR-3 Phase A header rebrand (2026-05-05): replace the tiny
          "PVE · БОТ vs <name>" line with two pixel-styled role badges so
          the player immediately reads "Я — продавец, оппонент — клиент"
          instead of mistaking the screen for /training. The mode pill
          (PVP/PVE) moves into the centre as a small subtitle so the
          screen real estate is dominated by the role contrast. */}
      <header
        className="h-16 shrink-0 flex items-center justify-between px-4 sm:px-6 z-20"
        style={{ background: "var(--glass-bg)", borderBottom: "1px solid var(--border-color)", backdropFilter: "blur(20px)" }}
      >
        {/* Left — exit + you (role + name) */}
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <button
            type="button"
            onClick={() => setShowExitConfirm(true)}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors shrink-0"
            style={{ background: "var(--danger-muted)", color: "var(--danger)", border: "1px solid var(--danger-muted)" }}
            title="Выйти из дуэли"
          >
            <LogOut size={14} />
            Выйти
          </button>
          <div className="flex flex-col leading-tight min-w-0">
            <span
              className="font-pixel text-[10px] sm:text-[11px] uppercase tracking-wider"
              style={{
                color: store.myRole === "seller" ? "var(--accent)" : "var(--magenta, #d946ef)",
                textShadow: "1px 1px 0 #000",
              }}
            >
              ВЫ · {myRoleLabel}
            </span>
            <span className="font-mono text-[11px] truncate" style={{ color: "var(--text-primary)" }}>
              {myName}
            </span>
          </div>
        </div>

        {/* Center — VS + mode pill */}
        <div className="flex flex-col items-center shrink-0 px-2">
          <Swords size={18} style={{ color: "var(--accent)" }} />
          <span
            className="font-pixel text-[9px] uppercase tracking-widest mt-0.5"
            style={{ color: "var(--text-muted)" }}
          >
            {store.duelBrief?.is_pve ? "PVE · БОТ" : "PVP · КЛАССИКА"}
          </span>
        </div>

        {/* Right — opponent (role + name + tier) */}
        <div className="flex items-center gap-3 min-w-0 flex-1 justify-end">
          <div className="flex flex-col leading-tight min-w-0 items-end">
            <span
              className="font-pixel text-[10px] sm:text-[11px] uppercase tracking-wider"
              style={{
                color: store.myRole === "seller" ? "var(--magenta, #d946ef)" : "var(--accent)",
                textShadow: "1px 1px 0 #000",
              }}
            >
              {oppRoleLabel} · {store.duelBrief?.is_pve ? "AI" : "ИГРОК"}
            </span>
            <span className="font-mono text-[11px] truncate flex items-center gap-1.5" style={{ color: "var(--text-primary)" }}>
              {store.duelBrief?.opponent?.name || "Подбор…"}
              {oppTier && (
                <span
                  className="px-1.5 py-0.5 text-[9px] uppercase tracking-widest rounded"
                  style={{
                    background: "var(--accent-muted)",
                    color: "var(--accent)",
                    border: "1px solid var(--accent)",
                  }}
                >
                  {oppTier}
                </span>
              )}
            </span>
          </div>
        </div>
      </header>
      {store.duelBrief?.archetype && (
        <div
          className="px-4 sm:px-6 py-1 text-[10px] sm:text-[11px] font-pixel uppercase tracking-widest text-center z-20"
          style={{
            color: "var(--text-secondary)",
            background: "rgba(0,0,0,0.25)",
            borderBottom: "1px solid var(--border-color)",
          }}
        >
          {store.duelBrief.scenario_title || "Сценарий"} · Архетип: {store.duelBrief.archetype}
        </div>
      )}

      {/* Connection status */}
      {connectionState !== "connected" && (
        <div className="px-4 pt-3 z-20">
          <div
            className="rounded-xl px-4 py-2 text-xs font-mono flex items-center gap-2"
            style={{
              background: connectionState === "reconnecting" ? "var(--warning-muted)" : "var(--danger-muted)",
              color: connectionState === "reconnecting" ? "var(--warning)" : "var(--danger)",
              border: `1px solid ${connectionState === "reconnecting" ? "var(--warning-muted)" : "var(--danger-muted)"}`,
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

      {/* Round indicator — 2026-05-03: countdown ring + mm:ss removed per user feedback. */}

      {/* Character brief for client role */}
      {store.myRole === "client" && store.duelBrief?.character_brief && (
        <div className="mx-4 mb-2 cyber-card px-3 py-2.5 z-20">
          <div className="flex items-center gap-2 mb-1.5">
            <span className="status-badge status-badge--online" style={{ fontSize: "14px" }}>
              ВАША РОЛЬ
            </span>
            <span className="text-xs font-mono font-bold" style={{ color: "var(--accent)" }}>
              {sanitizeText(store.duelBrief.character_brief.name)}
            </span>
          </div>
          {/* 2026-04-20: sanitizeText для ВСЕХ полей character_brief.
              character_brief приходит из WS сообщения duel.brief — если
              бэк (или скомпрометированный opponent) пришлёт
              <img onerror=...> — без санитизации это XSS. */}
          <p className="text-xs leading-relaxed mb-1" style={{ color: "var(--text-secondary)" }}>
            {sanitizeText(store.duelBrief.character_brief.brief)}
          </p>
          <p className="text-xs italic" style={{ color: "var(--text-muted)" }}>
            {sanitizeText(store.duelBrief.character_brief.behavior)}
          </p>
        </div>
      )}

      {/* Phase A — floating TTS narration player (pvp.audio_ready). */}
      {audioUrl && (
        <div className="mx-4 mt-1 flex justify-end z-20">
          <ArenaAudioPlayer
            audioUrl={audioUrl}
            label={`РАУНД ${store.roundNumber}`}
            autoplay={true}
          />
        </div>
      )}

      {/* Phase A — lifelines bar + mic sit above the DuelChat. */}
      {store.myRole === "seller" && store.roundNumber > 0 && (
        <div className="mx-4 mt-2 flex items-center gap-2 flex-wrap z-20">
          {lifelines.counts.hints > 0 && (
            <button
              type="button"
              onClick={() => lifelines.useHint(input || "Помоги с ответом")}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-semibold uppercase tracking-wider transition-all"
              style={{
                background: "#facc1518",
                color: "#facc15",
                border: "1px solid #facc1533",
              }}
              title="Подсказка — RAG-грунт по 127-ФЗ"
            >
              <Lightbulb size={12} />
              Подсказка
              <span className="font-mono opacity-80">×{lifelines.counts.hints}</span>
            </button>
          )}
          {lifelines.counts.skips > 0 && (
            <button
              type="button"
              onClick={async () => {
                const ok = await lifelines.useSkip();
                if (ok) {
                  setInput("");
                  sendMessage({ type: "duel.message", text: "__skip__" });
                }
              }}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-semibold uppercase tracking-wider transition-all"
              style={{
                background: "#94a3b818",
                color: "#94a3b8",
                border: "1px solid #94a3b833",
              }}
              title="Пропустить ход"
            >
              <SkipForward size={12} />
              Пропустить
              <span className="font-mono opacity-80">×{lifelines.counts.skips}</span>
            </button>
          )}
          {/* 2026-04-20: микрофон ВСЕГДА видим. Если API недоступен —
              disabled + tooltip. Раньше кнопка исчезала совсем и юзер
              не понимал "куда жать когда placeholder говорит про голос". */}
          <button
            type="button"
            onClick={() => (micActive ? speech.stopListening() : speech.startListening())}
            disabled={!speech.isSupported}
            className="ml-auto inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-semibold uppercase tracking-wider transition-all disabled:opacity-40"
            style={{
              background: micActive ? theme.accent : "transparent",
              color: micActive ? "#0b0b14" : theme.accent,
              border: `1px solid ${theme.accent}55`,
            }}
            title={
              !speech.isSupported
                ? "Голос недоступен — используйте Chrome/Edge на HTTPS"
                : micActive ? "Остановить" : "Говорить голосом"
            }
            aria-label={micActive ? "Остановить микрофон" : "Включить микрофон"}
          >
            {micActive ? <MicOff size={12} /> : <Mic size={12} />}
            {micActive ? "слушаю…" : "голос"}
          </button>
        </div>
      )}

      {/* Issue #168 — judge.degraded banner. Renders above the chat
          when the backend signalled a neutral fallback verdict so
          the player knows the displayed score is not a real LLM
          assessment. Cleared on round.start. */}
      {judgeDegraded && (
        <div
          role="alert"
          aria-live="polite"
          className="z-30 mx-3 mb-2 px-3 py-2 font-pixel"
          style={{
            background: "var(--warning-muted, #4a3a18)",
            border: "2px solid var(--warning, #f5a623)",
            outlineOffset: -2,
            boxShadow: "3px 3px 0 0 var(--warning, #f5a623)",
            color: "var(--warning, #f5a623)",
            fontSize: 13,
            letterSpacing: "0.06em",
            lineHeight: 1.45,
          }}
        >
          <strong style={{ marginRight: 6 }}>⚠ Резервная оценка</strong>
          <span style={{ color: "var(--text-primary)" }}>
            Раунд {judgeDegraded.round_number} оценён в fallback-режиме (
            {judgeDegraded.reason === "llm_error" && "AI-судья временно недоступен"}
            {judgeDegraded.reason === "json_parse" && "не удалось разобрать ответ AI"}
            {judgeDegraded.reason === "all_providers_down" && "все провайдеры AI отключены"}
            {!["llm_error", "json_parse", "all_providers_down"].includes(judgeDegraded.reason) &&
              `сбой: ${judgeDegraded.reason}`}
            ). Баллы могут не отражать реальную игру.
          </span>
        </div>
      )}

      {/* Chat area — scores integrated into terminal header */}
      <div className="flex-1 min-h-0 z-20">
        <DuelChat
          messages={store.messages}
          myRole={store.myRole || "seller"}
          input={input}
          onInputChange={setInput}
          onSend={handleSend}
          disabled={store.roundNumber === 0 || store.timeRemaining <= 0}
          opponentStatus={
            statusNotice?.includes("переподключается")
              ? "reconnecting"
              : connectionState !== "connected"
                ? "offline"
                : "online"
          }
          scores={store.judgeScore ?? undefined}
          // 2026-04-29 (Фаза 3): пробрасываем тир игрока, чтобы аватар/бабл
          // твоих сообщений покрасились по рангу. opponentTier пока не доступен
          // в payload — придёт в Фазе 7 (расширение match.found с opponent_tier).
          selfTier={store.rating?.rank_tier ?? undefined}
          // 2026-05-01 (12-portrait library): свой аватар — реактивный
          // hook usePlayerAvatar(level), соперник — по архетипу из duelBrief.
          selfAvatar={selfAvatar}
          opponentAvatar={resolveOpponentAvatar(store.duelBrief?.archetype ?? null)}
        />
      </div>

      {/* 2026-05-03: pre-round 3..2..1 overlay removed per user feedback. */}
      <CoachingCard
        open={coachingOpen}
        accentColor={theme.accent}
        payload={coachingPayload}
        onDismiss={() => setCoachingOpen(false)}
      />
    </ArenaBackground>
  );
}
