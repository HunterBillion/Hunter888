"use client";

import { Suspense, useEffect, useState, useCallback, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowRight, Loader2 } from "lucide-react";
import { Sword, Trophy, Lightning, Target, Sparkle } from "@phosphor-icons/react";
import { PixelInfoButton } from "@/components/ui/PixelInfoButton";
import AuthLayout from "@/components/layout/AuthLayout";
import { api } from "@/lib/api";
import { useWebSocket } from "@/hooks/useWebSocket";
import { usePvPStore } from "@/stores/usePvPStore";
import { useNotificationStore } from "@/stores/useNotificationStore";
import { RatingCard } from "@/components/pvp/RatingCard";
import { MatchmakingOverlay } from "@/components/pvp/MatchmakingOverlay";
import { logger } from "@/lib/logger";
import { PixelIcon, type PixelIconName } from "@/components/pvp/PixelIcon";
import { CharacterPicker } from "@/components/pvp/CharacterPicker";
import { KnowledgeBaseBrowser } from "@/components/pvp/KnowledgeBaseBrowser";
import { HonestNavigator } from "@/components/pvp/HonestNavigator";
import { PixelMascot } from "@/components/pvp/PixelMascot";
import type { MascotState } from "@/components/pvp/PixelMascotSprites";

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
  const tabParam = searchParams.get("tab");
  const [tab, setTab] = useState<"history" | "knowledge_base">(
    tabParam === "knowledge_base" || tabParam === "rag" ? "knowledge_base" : "history"
  );
  const [quizStarting, setQuizStarting] = useState(false);
  const [pickedCharacterId, setPickedCharacterId] = useState<string | null>(null);
  const [arenaPoints, setArenaPoints] = useState<number>(0);
  const inviteSentRef = useRef(false);
  const autoPvERef = useRef(false);
  const searchStartedAtRef = useRef<number | null>(null);

  const fetchArenaPoints = useCallback(() => {
    api.get("/progression/arena-points")
      .then((data: Record<string, unknown>) => {
        if (typeof data?.arena_points === "number") setArenaPoints(data.arena_points);
      })
      .catch((err) => logger.error("[pvp] arena-points fetch failed:", err));
  }, []);

  useEffect(() => {
    store.fetchRating();
    store.fetchMyDuels();
    store.fetchActiveSeason();
    fetchArenaPoints();
  }, [fetchArenaPoints]); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-refetch rating + duels + AP when the tab becomes visible again
  // (e.g. user returned from /pvp/duel/[id] or /pvp/quiz/*). Без этого
  // «Калибровка 0/10» зависала до ручного reload.
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState !== "visible") return;
      store.fetchRating();
      store.fetchMyDuels();
      fetchArenaPoints();
    };
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", onVisible);
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", onVisible);
    };
  }, [fetchArenaPoints]); // eslint-disable-line react-hooks/exhaustive-deps

  // PvP WebSocket
  const { sendMessage, connectionState } = useWebSocket({
    path: "/ws/pvp",
    autoConnect: true,
    onMessage: (data) => {
      switch (data.type) {
        case "queue.joined":
          autoPvERef.current = false;
          searchStartedAtRef.current = Date.now();
          store.setQueueStatus("searching");
          if (typeof data.data.position === "number") {
            store.setQueuePosition(data.data.position as number, store.estimatedWait);
          }
          break;
        case "queue.status":
          store.setQueuePosition(
            (data.data.queue_size as number) ?? (data.data.position as number) ?? 0,
            data.data.estimated_remaining as number,
          );
          break;
        case "match.found":
          autoPvERef.current = false;
          searchStartedAtRef.current = null;
          store.setQueueStatus("matched");
          store.setMatchedOpponentRating(
            typeof data.data.opponent_rating === "number" ? (data.data.opponent_rating as number) : null,
          );
          // Navigate to duel page
          setTimeout(() => {
            router.push(`/pvp/duel/${data.data.duel_id}`);
          }, 2000);
          break;
        case "pve.offer":
          // Backend emits pve.offer on PvE match — FE just marks "matched";
          // duel.brief / match.found arrive next and redirect to the duel.
          store.setQueueStatus("matched");
          break;
        case "queue.left":
          autoPvERef.current = false;
          searchStartedAtRef.current = null;
          store.resetQueue();
          break;
      }
    },
  });

  const handleFindMatch = useCallback(() => {
    autoPvERef.current = false;
    searchStartedAtRef.current = Date.now();
    store.setQueueStatus("searching");
    const payload: Record<string, unknown> = { type: "queue.join" };
    if (pickedCharacterId) payload.character_id = pickedCharacterId;
    sendMessage(payload);
  }, [sendMessage, store, pickedCharacterId]);

  const startQuiz = useCallback(async (
    mode: "free_dialog" | "blitz" | "themed",
    category?: string,
  ) => {
    setQuizStarting(true);
    const watchdog = setTimeout(() => {
      setQuizStarting(false);
      useNotificationStore.getState().addToast({
        title: "Таймаут",
        body: "Сервер долго отвечает. Попробуйте ещё раз.",
        type: "warning",
      });
    }, 10_000);
    const personality = mode === "blitz" ? "showman" : "professor";
    try {
      const res = await api.post("/knowledge/sessions", {
        mode,
        category: category ?? null,
        ai_personality: personality,
        choices_format: true,
      }) as { id?: string; session_id?: string };
      clearTimeout(watchdog);
      const sid = res?.id || res?.session_id;
      if (sid) {
        const params = new URLSearchParams({ mode });
        if (category) params.set("category", category);
        params.set("personality", personality);
        params.set("choices_format", "1");
        router.push(`/pvp/quiz/${sid}?${params.toString()}`);
      } else {
        useNotificationStore.getState().addToast({
          title: "Ошибка",
          body: "Не удалось создать сессию. Попробуйте ещё раз.",
          type: "error",
        });
      }
    } catch (e) {
      clearTimeout(watchdog);
      logger.error("Failed to start quiz:", e);
      useNotificationStore.getState().addToast({
        title: "Ошибка",
        body: "Не удалось начать тест. Проверьте подключение.",
        type: "error",
      });
    } finally {
      clearTimeout(watchdog);
      setQuizStarting(false);
    }
  }, [router]);

  const handleCancelQueue = useCallback(() => {
    autoPvERef.current = false;
    searchStartedAtRef.current = null;
    sendMessage({ type: "queue.leave" });
    store.resetQueue();
  }, [sendMessage, store]);

  // Auto-accept PvP invitation when arriving with ?accept=challenger_id
  const acceptParam = searchParams.get("accept");
  useEffect(() => {
    if (!acceptParam || inviteSentRef.current || connectionState !== "connected") return;
    inviteSentRef.current = true;
    autoPvERef.current = false;
    searchStartedAtRef.current = Date.now();
    store.setQueueStatus("searching");
    sendMessage({ type: "queue.join", invitation_challenger_id: acceptParam });
    router.replace("/pvp", { scroll: false });
  }, [acceptParam, connectionState, sendMessage, router, store]);

  useEffect(() => {
    if (store.queueStatus !== "searching") return;
    const startedAt = searchStartedAtRef.current;
    if (!startedAt || Date.now() - startedAt < 58_000) return;
    if (store.estimatedWait > 0) return;
    if (autoPvERef.current) return;

    autoPvERef.current = true;

    const controller = new AbortController();
    api.post("/pvp/accept-pve", {}, { signal: controller.signal })
      .then((data) => {
        if (controller.signal.aborted) return;
        const duelId = (data as { duel_id?: string })?.duel_id;
        if (!duelId) {
          // No PvE opponent found — reset queue + toast (без этого
          // пользователь зависал с overlay «Ищем соперника…» навсегда).
          autoPvERef.current = false;
          store.resetQueue();
          useNotificationStore.getState().addToast({
            title: "Соперник не найден",
            body: "Попробуйте ещё раз через минуту.",
            type: "warning",
          });
          return;
        }
        store.resetQueue();
        store.setQueueStatus("matched");
        router.push(`/pvp/duel/${duelId}`);
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        logger.error("Auto PvE match failed:", err);
        autoPvERef.current = false;
        useNotificationStore.getState().addToast({
          title: "Ошибка подбора",
          body: "Не удалось найти PvE-соперника. Попробуйте позже.",
          type: "error",
        });
      });

    return () => controller.abort();
  }, [store.queueStatus, store.estimatedWait, router, store]);

  // Mascot state derived from queue lifecycle. Real DOM-anchor migration
  // (jumping between RatingCard / mode tiles / history) lands in the lobby
  // redesign PR; here the mascot just lives in a fixed corner.
  const mascotState: MascotState =
    store.queueStatus === "matched"
      ? "cheer"
      : store.queueStatus === "searching"
        ? "walk"
        : "idle";

  const formatTime = (iso: string) => {
    const d = new Date(iso);
    return d.toLocaleDateString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  };

  return (
    <AuthLayout>
      <motion.div
        className="relative arena-grid-bg min-h-screen"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.4, ease: "easeOut" }}
      >
        <div className="app-page pb-24 md:pb-32">
          {/* Connection status banner — smooth slide-in */}
          <AnimatePresence>
            {connectionState !== "connected" && (
              <motion.div
                initial={{ opacity: 0, height: 0, marginBottom: 0 }}
                animate={{ opacity: 1, height: "auto", marginBottom: 16 }}
                exit={{ opacity: 0, height: 0, marginBottom: 0 }}
                transition={{ duration: 0.3, ease: "easeOut" }}
                className="overflow-hidden"
              >
                <div
                  className="flex items-center gap-3 rounded-none pixel-border px-4 py-3 text-sm font-pixel"
                  style={{
                    "--pixel-border-color": connectionState === "error" ? "var(--danger)" : "var(--warning)",
                    background: connectionState === "error" ? "var(--danger-muted)" : "var(--warning-muted)",
                    color: connectionState === "error" ? "var(--danger)" : "var(--warning)",
                  } as React.CSSProperties}
                >
                  {connectionState === "error" ? (
                    <PixelIcon name="skull" size={16} color="var(--danger)" />
                  ) : (
                    <Loader2 size={16} className="animate-spin" />
                  )}
                  {connectionState === "error"
                    ? "ОШИБКА ПОДКЛЮЧЕНИЯ К PVP СЕРВЕРУ"
                    : connectionState === "reconnecting"
                      ? "ПЕРЕПОДКЛЮЧЕНИЕ..."
                      : "ПОДКЛЮЧЕНИЕ К PVP..."}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
          {/* Header */}
          <motion.div initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.3 }}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <PixelIcon name="sword" size={32} color="var(--accent)" />
                <div>
                  <h1 className="font-pixel text-xl sm:text-2xl uppercase tracking-widest pixel-glow" style={{ color: "var(--text-primary)" }}>
                    PVP Арена
                  </h1>
                  <p className="font-pixel text-xs mt-0.5 uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                    Дуэли 1 на 1 · Glicko-2 рейтинг
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <PixelInfoButton
                  title="Как устроена Арена"
                  sections={[
                    { icon: Sword, label: "Дуэль с ботом", text: "Жми «Дуэль с ботом» — подберём AI-клиента (10 архетипов: скептик, тревожный, скандалист и др.). 2 раунда: ты продаёшь и оцениваешь, потом меняетесь. Если кто-то живой в очереди — попадёшь на него вместо бота." },
                    { icon: Target, label: "Квиз ФЗ-127", text: "«Свободный» — 10 вопросов, без таймера. «Блиц» — 20×60 сек, на скорость. «По теме» — выбираешь 1 из 10 категорий, 15 вопросов. После каждого ответа — разбор от AI и ссылка на статью закона." },
                    { icon: Lightning, label: "База ФЗ-127", text: "Вкладка «База ФЗ-127» — RAG-источники, которые AI использует для проверки твоих ответов. Ищи по статье или категории." },
                    { icon: Trophy, label: "Рейтинг", text: "Первые 10 дуэлей — калибровка, рейтинг прыгает. Потом стабильная Glicko-2: 8 тиров Iron → Grandmaster. Peak tier не теряется." },
                    { icon: Sparkle, label: "После боя", text: "AI-судья разбирает оба раунда: что сработало, где провалил. Плюс очки XP и Arena Points (AP). Не согласен с оценкой — нажми «Оспорить» (rejudge через cloud-LLM)." },
                  ]}
                  footer="Короткий путь: один из 4 блоков выше → бой/квиз → разбор → рейтинг"
                />
              </div>
            </div>
          </motion.div>

          {/* Season banner */}
          {store.activeSeason && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.1 }}
              className="mt-4 p-3 flex items-center gap-3"
              style={{
                background: "color-mix(in srgb, var(--gf-xp) 10%, var(--bg-panel))",
                outline: "2px solid var(--gf-xp)",
                outlineOffset: -2,
                boxShadow: "3px 3px 0 0 var(--gf-xp)",
                borderRadius: 0,
              }}
            >
              <PixelIcon name="bolt" size={16} color="var(--gf-xp)" />
              <span
                className="font-pixel uppercase"
                style={{
                  color: "var(--gf-xp)",
                  fontSize: 12,
                  letterSpacing: "0.14em",
                }}
              >
                {store.activeSeason.name}
              </span>
            </motion.div>
          )}

          {/* Rating loading state */}
          {store.ratingLoading && (
            <div className="mt-6 flex items-center justify-center py-8">
              <Loader2 size={24} className="animate-spin" style={{ color: "var(--accent)" }} />
            </div>
          )}

          {/* Rating failed */}
          {!store.rating && !store.ratingLoading && (
            <div className="mt-6 flex flex-col items-center py-8 text-center">
              <p className="text-sm mb-3" style={{ color: "var(--text-muted)" }}>
                Не удалось загрузить рейтинг. Проверьте подключение к серверу.
              </p>
              <motion.button
                onClick={() => store.fetchRating()}
                whileHover={{ x: -1, y: -1 }}
                whileTap={{ x: 2, y: 2 }}
                className="font-pixel"
                style={{
                  padding: "8px 16px",
                  background: "var(--accent)",
                  color: "#fff",
                  border: "2px solid var(--accent)",
                  borderRadius: 0,
                  fontSize: 12,
                  letterSpacing: "0.18em",
                  textTransform: "uppercase",
                  boxShadow: "3px 3px 0 0 #000, 0 0 12px var(--accent-glow)",
                  cursor: "pointer",
                }}
              >
                Повторить
              </motion.button>
            </div>
          )}

          {/* Rating card */}
          {store.rating && !store.ratingLoading && (
            <div className="mt-6">
              <RatingCard rating={store.rating} />

              {/* Arena Points chip */}
              <div
                className="mt-3 inline-flex items-center gap-2 px-4 py-2"
                style={{
                  background: "color-mix(in srgb, var(--gf-xp) 12%, var(--bg-panel))",
                  outline: "2px solid var(--gf-xp)",
                  outlineOffset: -2,
                  boxShadow: "2px 2px 0 0 var(--gf-xp)",
                  borderRadius: 0,
                }}
              >
                <PixelIcon name="bolt" size={16} color="var(--gf-xp)" />
                <span
                  className="font-pixel"
                  style={{
                    color: "var(--gf-xp)",
                    fontSize: 18,
                    letterSpacing: "0.04em",
                    lineHeight: 1,
                  }}
                >
                  {arenaPoints}
                </span>
                <span
                  className="font-pixel uppercase"
                  style={{
                    color: "var(--text-muted)",
                    fontSize: 11,
                    letterSpacing: "0.14em",
                  }}
                >
                  Arena Points
                </span>
              </div>
            </div>
          )}

          <div className="mt-6 mx-auto max-w-3xl space-y-6">

              {/* HonestNavigator — 3 modes: Дуэль / Блиц / По теме. */}
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.18, delay: 0.08 }}
              >
                <HonestNavigator
                  disabled={store.queueStatus !== "idle" || quizStarting}
                  starting={quizStarting}
                  onDuel={handleFindMatch}
                  onQuiz={(mode, category) => startQuiz(mode, category)}
                />
              </motion.div>

              {/* Power-user character preset (Issue #169) — gear-icon
                  toggle, off by default. Activated state shows the
                  picker inline (collapsed otherwise to save space). */}
              <details className="group">
                <summary
                  className="cursor-pointer select-none inline-flex items-center gap-2 px-3 py-1.5 font-pixel uppercase"
                  style={{
                    color: "var(--text-muted)",
                    fontSize: 10,
                    letterSpacing: "0.14em",
                    background: "transparent",
                    border: "1px dashed var(--border-color)",
                    borderRadius: 0,
                  }}
                >
                  <PixelIcon name="robot" size={12} color="var(--text-muted)" />
                  Персонаж
                  {pickedCharacterId && (
                    <span style={{ color: "var(--accent)", fontSize: 9 }}>● выбран</span>
                  )}
                </summary>
                <div className="mt-3">
                  <CharacterPicker
                    selectedId={pickedCharacterId}
                    onPick={setPickedCharacterId}
                    disabled={store.queueStatus !== "idle"}
                  />
                </div>
              </details>

              {/* Tabs: «История» (my duels) и «База ФЗ-127» (RAG view). */}
              <div className="flex flex-wrap gap-2">
                {(["history", "knowledge_base"] as const).map((t) => {
                  const active = tab === t;
                  const label = t === "history" ? "История" : "База ФЗ-127";
                  const icon: PixelIconName = t === "history" ? "ladder" : "book";
                  return (
                    <motion.button
                      key={t}
                      type="button"
                      onClick={() => setTab(t)}
                      whileHover={active ? {} : { x: -1, y: -1 }}
                      whileTap={{ x: 2, y: 2, transition: { duration: 0.05 } }}
                      transition={{ type: "spring", stiffness: 600, damping: 30 }}
                      className="flex items-center gap-2 px-4 py-2.5 font-pixel relative"
                      style={{
                        background: active ? "var(--accent)" : "var(--bg-panel)",
                        color: active ? "#fff" : "var(--text-primary)",
                        border: `2px solid ${active ? "var(--accent)" : "var(--border-color)"}`,
                        borderRadius: 0,
                        fontSize: 13,
                        letterSpacing: "0.12em",
                        textTransform: "uppercase",
                        boxShadow: active
                          ? "3px 3px 0 0 #000, 0 0 12px var(--accent-glow)"
                          : "2px 2px 0 0 var(--border-color)",
                        cursor: "pointer",
                        transition: "background 120ms, color 120ms",
                      }}
                    >
                      <PixelIcon name={icon} size={16} color={active ? "#fff" : "var(--text-muted)"} />
                      {label}
                    </motion.button>
                  );
                })}
              </div>

              {/* База ФЗ-127 — RAG transparency view */}
              <AnimatePresence mode="wait">
                {tab === "knowledge_base" && (
                  <motion.div
                    key="rag"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.18 }}
                  >
                    <KnowledgeBaseBrowser />
                  </motion.div>
                )}
              </AnimatePresence>

              {/* History */}
              <AnimatePresence mode="wait">
                {tab === "history" && (
                  <motion.div key="history" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.18 }}>
                    {store.duelsLoading ? (
                      <div className="mt-8 flex justify-center">
                        <Loader2 size={20} className="animate-spin" style={{ color: "var(--accent)" }} />
                      </div>
                    ) : store.myDuels.length === 0 ? (
                      <div className="mt-12 text-center flex flex-col items-center gap-3">
                        <PixelIcon name="sword" size={32} color="var(--text-muted)" />
                        <p className="font-pixel text-xs uppercase" style={{ color: "var(--text-muted)", letterSpacing: "0.18em" }}>
                          Ещё нет дуэлей
                        </p>
                      </div>
                    ) : (
                      <div className="mt-6 space-y-3">
                        {store.myDuels.map((duel, i) => {
                          const isP1 = store.rating?.user_id === duel.player1_id;
                          const myScore = isP1 ? duel.player1_total : duel.player2_total;
                          const oppScore = isP1 ? duel.player2_total : duel.player1_total;
                          const myDelta = isP1 ? duel.player1_rating_delta : duel.player2_rating_delta;
                          const isWinner = duel.winner_id === store.rating?.user_id;
                          const ratingApplied = duel.rating_change_applied && !duel.is_pve;
                          const isCancelled = duel.status === "cancelled";
                          // Cancelled duels aren't a "loss" — render in muted state.
                          const accent = isCancelled
                            ? "var(--text-muted)"
                            : duel.is_draw
                              ? "var(--warning)"
                              : isWinner
                                ? "var(--success)"
                                : "var(--danger)";
                          const verdict = isCancelled
                            ? "Отменена"
                            : duel.is_draw
                              ? "Ничья"
                              : isWinner
                                ? "Победа"
                                : "Поражение";

                          return (
                            <motion.div
                              key={duel.id}
                              initial={{ opacity: 0 }}
                              animate={{ opacity: 1 }}
                              transition={{ delay: i * 0.05 }}
                              whileHover={{ x: -1, y: -1 }}
                              className="p-4 flex items-center gap-4 cursor-pointer"
                              style={{
                                background: "var(--bg-panel)",
                                outline: `2px solid ${accent}`,
                                outlineOffset: -2,
                                boxShadow: `3px 3px 0 0 ${accent}`,
                                borderRadius: 0,
                              }}
                              onClick={() => router.push(`/pvp/duel/${duel.id}`)}
                            >
                              <div className="flex-1">
                                <div className="flex items-center gap-2 flex-wrap">
                                  <span
                                    className="font-pixel uppercase"
                                    style={{
                                      color: accent,
                                      fontSize: 13,
                                      letterSpacing: "0.14em",
                                    }}
                                  >
                                    {verdict}
                                  </span>
                                  {!isCancelled && (
                                    <span
                                      className="font-pixel uppercase"
                                      style={{
                                        padding: "1px 6px",
                                        background: "var(--bg-secondary)",
                                        border: "1px solid var(--border-color)",
                                        color: "var(--text-muted)",
                                        fontSize: 10,
                                        letterSpacing: "0.12em",
                                      }}
                                    >
                                      {DUEL_STATUS_LABELS[duel.status] || duel.status}
                                    </span>
                                  )}
                                  {duel.is_pve && (
                                    <span
                                      className="font-pixel uppercase"
                                      style={{
                                        padding: "1px 6px",
                                        background: "color-mix(in srgb, var(--warning) 12%, transparent)",
                                        border: "1px solid var(--warning)",
                                        color: "var(--warning)",
                                        fontSize: 10,
                                        letterSpacing: "0.14em",
                                      }}
                                    >PvE</span>
                                  )}
                                </div>
                                <div
                                  className="mt-1 font-pixel"
                                  style={{
                                    color: "var(--text-muted)",
                                    fontSize: 12,
                                    letterSpacing: "0.04em",
                                  }}
                                >
                                  {formatTime(duel.created_at)} · {Math.round(myScore)} vs {Math.round(oppScore)}
                                </div>
                              </div>
                              <div
                                className="font-pixel"
                                style={{
                                  color: ratingApplied ? (myDelta >= 0 ? "var(--success)" : "var(--danger)") : "var(--warning)",
                                  fontSize: 16,
                                  letterSpacing: "0.04em",
                                }}
                              >
                                {ratingApplied ? `${myDelta >= 0 ? "+" : ""}${Math.round(myDelta)}` : "—"}
                              </div>
                              <ArrowRight size={16} style={{ color: "var(--text-muted)" }} />
                            </motion.div>
                          );
                        })}
                      </div>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>

          </div>
        </div>
      </motion.div>

      {/* Matchmaking overlay */}
      <AnimatePresence>
        {(store.queueStatus === "searching" || store.queueStatus === "matched") && (
          <MatchmakingOverlay
            status={store.queueStatus}
            position={store.queuePosition}
            estimatedWait={store.estimatedWait}
            opponentRating={store.matchedOpponentRating ?? undefined}
            onCancel={handleCancelQueue}
          />
        )}
      </AnimatePresence>

      {/* Pixel mascot — placeholder fixed corner. Anchor-migration TBD in lobby PR. */}
      <motion.div
        className="pointer-events-none fixed bottom-6 right-6 z-40 hidden md:block"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.5, duration: 0.4 }}
      >
        <PixelMascot state={mascotState} size={80} />
      </motion.div>

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
