"use client";

import { Suspense, useEffect, useState, useCallback, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { Loader2 } from "lucide-react";
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
import { PixelIcon } from "@/components/pvp/PixelIcon";
import { CharacterPicker } from "@/components/pvp/CharacterPicker";
import { KnowledgeBaseBrowser } from "@/components/pvp/KnowledgeBaseBrowser";
import { HonestNavigator } from "@/components/pvp/HonestNavigator";
import { TopPlayersPanel } from "@/components/pvp/TopPlayersPanel";
import { ArenaLivePanel } from "@/components/pvp/ArenaLivePanel";
import { HistoryPanel } from "@/components/pvp/HistoryPanel";
import { KnowledgeBasePanel } from "@/components/pvp/KnowledgeBasePanel";
import { LobbyMascot } from "@/components/pvp/LobbyMascot";

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
                {/* PR-16: «Персонаж» переехал из collapsible под центром
                    в иконку рядом с info button. Открывается popover'ом
                    через нативный <details>; на mobile collapsible
                    остаётся как fallback (см. main column). */}
                <details className="hidden lg:block relative group">
                  <summary
                    className="cursor-pointer select-none list-none inline-flex items-center justify-center w-10 h-10 transition-colors"
                    style={{
                      background: pickedCharacterId
                        ? "color-mix(in srgb, var(--accent) 14%, transparent)"
                        : "var(--bg-panel)",
                      color: pickedCharacterId ? "var(--accent)" : "var(--text-muted)",
                      border: `2px solid ${pickedCharacterId ? "var(--accent)" : "var(--border-color)"}`,
                      borderRadius: 0,
                    }}
                    title={pickedCharacterId ? "Персонаж выбран" : "Выбрать кастомного клиента"}
                    aria-label="Персонаж"
                  >
                    <PixelIcon name="robot" size={18} color="currentColor" />
                  </summary>
                  <div
                    className="absolute right-0 top-full mt-2 z-30 w-[320px] p-3"
                    style={{
                      background: "var(--bg-panel)",
                      border: "2px solid var(--accent)",
                      borderRadius: 0,
                      boxShadow: "4px 4px 0 0 #000, 0 0 16px var(--accent-glow)",
                    }}
                  >
                    <CharacterPicker
                      selectedId={pickedCharacterId}
                      onPick={setPickedCharacterId}
                      disabled={store.queueStatus !== "idle"}
                    />
                  </div>
                </details>
                <PixelInfoButton
                  title="Как устроена Арена"
                  sections={[
                    { icon: Sword, label: "Дуэль с ботом", text: "Жми «Дуэль» — подберём AI-клиента (10 архетипов: скептик, тревожный, скандалист и др.). 2 раунда: ты продаёшь и оцениваешь, потом меняетесь. Если кто-то живой в очереди — попадёшь на него вместо бота." },
                    { icon: Lightning, label: "Блиц 20×60", text: "20 вопросов по ФЗ-127, по 60 секунд на каждый. Personality «Шоумен» — даёт ответы пожёстче, но прощает скоростные неточности. Нужны быстрые рефлексы." },
                    { icon: Target, label: "По теме", text: "Выбираешь категорию закона (10 тем) или «Все темы (ФЗ-127)» — и идёт квиз с разбором. После каждого ответа AI-судья объясняет ошибку и ссылается на статью; не согласен — жми «Пожаловаться», методолог увидит." },
                    { icon: Trophy, label: "Рейтинг", text: "Первые 10 дуэлей — калибровка, рейтинг прыгает. Потом стабильная Glicko-2: 8 тиров Iron → Grandmaster. Peak tier не теряется. Отменённые / прерванные дуэли в рейтинг не идут." },
                    { icon: Sparkle, label: "После боя", text: "AI-судья разбирает оба раунда: что сработало, где провалил. Плюс очки XP и Arena Points (AP). Не согласен с оценкой — нажми «Оспорить» (rejudge через cloud-LLM)." },
                  ]}
                  footer="Короткий путь: один из 3 блоков выше → бой/квиз → разбор → рейтинг"
                />
              </div>
            </div>
          </motion.div>

          {/* Season banner */}
          {store.activeSeason && (() => {
            const s = store.activeSeason;
            const end = new Date(s.end_date);
            const now = Date.now();
            const msLeft = end.getTime() - now;
            const daysLeft = Math.max(0, Math.ceil(msLeft / 86_400_000));
            const top1 = (s.top_rewards ?? []).find((t) => t.rank === 1);
            const endLabel = end.toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
            return (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.1 }}
                className="mt-4 p-3 flex items-center flex-wrap gap-x-4 gap-y-2"
                style={{
                  background: "color-mix(in srgb, var(--gf-xp) 10%, var(--bg-panel))",
                  outline: "2px solid var(--gf-xp)",
                  outlineOffset: -2,
                  boxShadow: "3px 3px 0 0 var(--gf-xp)",
                  borderRadius: 0,
                }}
              >
                <span className="flex items-center gap-2">
                  <PixelIcon name="bolt" size={16} color="var(--gf-xp)" />
                  <span
                    className="font-pixel uppercase"
                    style={{ color: "var(--gf-xp)", fontSize: 12, letterSpacing: "0.14em" }}
                  >
                    {s.name}
                  </span>
                </span>
                {msLeft > 0 && (
                  <span
                    className="font-pixel uppercase"
                    style={{ color: "var(--text-muted)", fontSize: 11, letterSpacing: "0.14em" }}
                  >
                    · до {endLabel} ({daysLeft} {daysLeft === 1 ? "день" : daysLeft < 5 ? "дня" : "дней"})
                  </span>
                )}
                {top1 && (
                  <span
                    className="font-pixel uppercase"
                    style={{ color: "var(--gf-xp)", fontSize: 11, letterSpacing: "0.14em" }}
                  >
                    · топ-1 = {top1.ap} AP
                  </span>
                )}
              </motion.div>
            );
          })()}

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

          {/* PR-16 (2026-05-07): 3-column layout. Раньше центр был узкой
              max-w-3xl колонкой с 250px воздуха слева и справа — теперь
              боковые колонки заполнены живыми виджетами:
                LEFT  — TopPlayersPanel (top-3) + ArenaLivePanel (live)
                CENTER — HonestNavigator (3 mode plates)
                RIGHT — HistoryPanel (5 last duels) + KnowledgeBasePanel
              «Персонаж» переехал в icon-button на header (рядом с info).
              Deep-link `?tab=knowledge_base` переключает центр на
              full-screen RAG-browser (старый flow для admin/sharing). */}
          {tab === "knowledge_base" ? (
            <motion.div
              key="rag-fullscreen"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.18 }}
              className="mt-6 mx-auto max-w-5xl"
            >
              <button
                type="button"
                onClick={() => { setTab("history"); router.replace("/pvp", { scroll: false }); }}
                className="mb-3 inline-flex items-center gap-2 font-pixel uppercase text-[11px] px-3 py-1.5"
                style={{
                  color: "var(--text-muted)",
                  border: "1px solid var(--border-color)",
                  background: "transparent",
                  letterSpacing: "0.16em",
                }}
              >
                ← К арене
              </button>
              <KnowledgeBaseBrowser />
            </motion.div>
          ) : (
            <div className="mt-6 grid gap-4 lg:grid-cols-[220px_1fr_220px] xl:grid-cols-[240px_1fr_240px]">
              {/* LEFT sidebar — desktop only, ниже плиток на mobile */}
              <aside className="order-2 lg:order-1 flex flex-col gap-4 min-w-0">
                <TopPlayersPanel />
                <ArenaLivePanel />
              </aside>

              {/* CENTER — main interaction zone */}
              <div className="order-1 lg:order-2 flex flex-col gap-6 min-w-0">
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

                {/* Character picker — collapsed under center plates.
                    На десктопе уехала иконка ⚙️ в header, но collapsible
                    оставляем как fallback для мобильных и для тех, кто
                    привык к старому flow. */}
                <details className="group lg:hidden">
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
              </div>

              {/* RIGHT sidebar — desktop only, ниже на mobile */}
              <aside className="order-3 flex flex-col gap-4 min-w-0">
                <HistoryPanel />
                <KnowledgeBasePanel />
              </aside>
            </div>
          )}
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

      {/* PR-10 (2026-05-07): LobbyMascot animates between DOM-anchors
          (mode-tile hover, fixed-corner home) via Framer Motion. The
          state is forced when the queue is active so cheer/walk wins
          over the auto-hover idle/walk derivation. */}
      <LobbyMascot
        forcedState={
          store.queueStatus === "matched"
            ? "cheer"
            : store.queueStatus === "searching"
              ? "walk"
              : undefined  // let LobbyMascot auto-derive from anchor target
        }
      />

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
