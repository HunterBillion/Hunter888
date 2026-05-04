"use client";

import { Suspense, useEffect, useState, useCallback, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowRight, Loader2, Lock } from "lucide-react";
import { Sword, Trophy, Lightning, Brain, Target, Sparkle } from "@phosphor-icons/react";
import { PixelInfoButton } from "@/components/ui/PixelInfoButton";
import AuthLayout from "@/components/layout/AuthLayout";
import { api } from "@/lib/api";
import { useWebSocket } from "@/hooks/useWebSocket";
import { usePvPStore } from "@/stores/usePvPStore";
import { useNotificationStore } from "@/stores/useNotificationStore";
import { RatingCard } from "@/components/pvp/RatingCard";
import { MatchmakingOverlay } from "@/components/pvp/MatchmakingOverlay";
import { FriendsPanel } from "@/components/pvp/FriendsPanel";
import { AppIcon } from "@/components/ui/AppIcon";
import { logger } from "@/lib/logger";
// Phase B (2026-04-20): Duolingo-style weekly league hero widget
import { LeagueHeroCard } from "@/components/pvp/LeagueHeroCard";
// 2026-05-04: revive DailyDrillCard on /pvp hero. Was disabled on /home
// behind a `false &&` gate but the backend (/gamification/daily-drill +
// /complete) is fully implemented — chest reward, streak celebration,
// freeze logic. Free entry-point for new users: "сегодня сделай эту
// 3-минутную симуляцию".
import DailyDrillCard from "@/components/gamification/DailyDrillCard";
// 2026-04-29: pixel unification — единый формат карточек режимов + pixel-иконки.
import { PixelModeCard } from "@/components/pvp/PixelModeCard";
import { PixelIcon, type PixelIconName } from "@/components/pvp/PixelIcon";
// Issue #169 — custom-character picker (PR #142 backend endpoint).
import { CharacterPicker } from "@/components/pvp/CharacterPicker";
// 2026-05-04: full-RAG transparency view ("видеть всё что AI знает").
import { KnowledgeBaseBrowser } from "@/components/pvp/KnowledgeBaseBrowser";

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
  // 3.1: Pre-select knowledge tab + category from URL params
  const tabParam = searchParams.get("tab");
  const categoryParam = searchParams.get("category");
  const [tab, setTab] = useState<"arena" | "knowledge" | "history" | "rag">(
    tabParam === "knowledge" ? "knowledge"
      : tabParam === "history" ? "history"
      : tabParam === "rag" ? "rag"
      : "arena"
  );
  // showInfoModal state removed 2026-04-18 — now handled by PixelInfoButton component.
  const [quizMode, setQuizMode] = useState<"free_dialog" | "blitz" | "themed" | null>(null);
  const [quizCategory, setQuizCategory] = useState<string | null>(categoryParam || null);
  const [quizStarting, setQuizStarting] = useState(false);
  const [aiPersonality, setAiPersonality] = useState<string | null>(null);
  const [pveAccepting, setPveAccepting] = useState(false);
  // Issue #169 — selected custom-character preset id (or null = random
  // legacy behaviour). Forwarded to ``queue.join`` so the matchmaker
  // can route the duel to the chosen archetype.
  const [pickedCharacterId, setPickedCharacterId] = useState<string | null>(null);
  const [arenaPoints, setArenaPoints] = useState<number>(0);
  const inviteSentRef = useRef(false);
  const autoPvERef = useRef(false);
  const searchStartedAtRef = useRef<number | null>(null);

  useEffect(() => {
    store.fetchRating();
    store.fetchMyDuels();
    store.fetchActiveSeason();
    api.get("/progression/arena-points")
      .then((data: Record<string, unknown>) => {
        if (typeof data?.arena_points === "number") setArenaPoints(data.arena_points);
      })
      .catch((err) => logger.error("[pvp] arena-points fetch failed:", err));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps -- mount-only init; store actions are stable Zustand refs

  // 2026-04-20: auto-refetch рейтинга при возврате на /pvp
  // (из /pvp/duel/[id], /pvp/quiz/*). Раньше юзер проходил
  // калибровку, возвращался — а шкала «Калибровка 0/10» оставалась прежней
  // до ручного reload. Теперь каждый раз когда вкладка снова видима,
  // перетягиваем rating + myDuels + arena-points.
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState !== "visible") return;
      store.fetchRating();
      store.fetchMyDuels();
      api.get("/progression/arena-points")
        .then((data: Record<string, unknown>) => {
          if (typeof data?.arena_points === "number") setArenaPoints(data.arena_points);
        })
        .catch((err) => logger.error("[pvp] arena-points fetch failed:", err));
    };
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", onVisible);
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", onVisible);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

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
          store.setQueueStatus("matched");
          store.setPvEOffer(null);
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
    // Issue #169 — forward picked custom character id (or omit for random).
    const payload: Record<string, unknown> = { type: "queue.join" };
    if (pickedCharacterId) payload.character_id = pickedCharacterId;
    sendMessage(payload);
  }, [sendMessage, store, pickedCharacterId]);

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
    setPveAccepting(true);

    const controller = new AbortController();
    api.post("/pvp/accept-pve", {}, { signal: controller.signal })
      .then((data) => {
        if (controller.signal.aborted) return;
        const duelId = (data as { duel_id?: string })?.duel_id;
        if (!duelId) {
          // 2026-04-20: раньше молча возвращали — юзер зависал с overlay
          // «Ищем соперника…» навсегда. Теперь: сбрасываем очередь +
          // показываем тост, чтобы был visible feedback.
          autoPvERef.current = false;
          setPveAccepting(false);
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
      })
      .finally(() => {
        if (!controller.signal.aborted) setPveAccepting(false);
      });

    return () => controller.abort();
  }, [store.queueStatus, store.estimatedWait, router, store]);

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
        {/* 2026-05-04: extra bottom padding on /pvp — without it the
            last panel (history list / friends panel) sat flush against
            the viewport bottom edge. ~3cm of breathing room. */}
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
                {/* 2026-05-03: ⚔️ эмодзи → PixelIcon (единственное эмодзи на странице, выпадало из стиля) */}
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
                    { icon: Sword, label: "С чего начать", text: "Жми «Найти соперника» — подберём равного по уровню. Если очередь пустая — отправим к боту автоматически." },
                    { icon: Target, label: "3 вкладки ниже", text: "«Дуэли» — играть в реальном времени. «Знания ФЗ-127» — тренируй право (квизы и голосом). «История» — все твои прошлые бои + разборы." },
                    { icon: Lightning, label: "Режимы дуэли (PvP)", text: "Классическая — 2 раунда со сменой ролей. Скоростной — 5 мини-раундов по 2 мин. Испытание — 3-5 дуэлей подряд. 2v2 — в паре против пары (открывается с ур. 12)." },
                    { icon: Sparkle, label: "Режимы без людей (PvE)", text: "Стандартный бот, лестница ботов (5 штук растёт сложность), штурм боссов, зеркальный матч против своего стиля." },
                    { icon: Trophy, label: "Рейтинг и калибровка", text: "Первые 10 дуэлей — калибровка, рейтинг прыгает. Потом стабильная Glicko-2 система: 8 тиров Iron → Grandmaster. Peak tier не теряется." },
                    { icon: Brain, label: "После боя", text: "AI-судья разбирает оба раунда: что сработало, где провалил. Плюс очки XP и Arena Points (AP) для покупок. Твоя история — во вкладке «История»." },
                  ]}
                  footer="Короткий путь: «Найти соперника» → бой → разбор → рейтинг"
                />
                {/* Кнопка «Рейтинг» — pixel (2026-05-03). Header дублирует
                    /pvp/leaderboard, но эта кнопка остаётся как accent CTA
                    рядом с info-button — частый use-case на лобби. */}
                <motion.button
                  onClick={() => router.push("/pvp/leaderboard")}
                  whileHover={{ x: -1, y: -1 }}
                  whileTap={{ x: 2, y: 2 }}
                  className="flex items-center gap-2 font-pixel"
                  style={{
                    padding: "8px 14px",
                    background: "var(--bg-panel)",
                    color: "var(--accent)",
                    border: "2px solid var(--accent)",
                    borderRadius: 0,
                    fontSize: 12,
                    letterSpacing: "0.16em",
                    textTransform: "uppercase",
                    boxShadow: "3px 3px 0 0 var(--accent)",
                    cursor: "pointer",
                  }}
                >
                  <PixelIcon name="shield" size={14} color="var(--accent)" />
                  Рейтинг
                </motion.button>
              </div>
            </div>
          </motion.div>

          {/* Info modal replaced 2026-04-18 by unified <PixelInfoButton /> above */}

          {/* Season banner — pixel (2026-05-03) */}
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

          {/* Rating failed — pixel retry (2026-05-03) */}
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

          {/* Rating card. Tutorial removed 2026-05-03: first-time users
              see the rating card directly and click "Найти соперника"; if
              the queue is empty they auto-fall to PvE per matchmaker logic. */}
          {store.rating && !store.ratingLoading && (
            <div className="mt-6">
              <RatingCard rating={store.rating} />

              {/* Arena Points — pixel chip (2026-05-03) */}
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

              {/* 2026-05-04: Daily drill — primary daily entry-point.
                  Above the league widget because the league updates
                  weekly, while the drill is the "что сделать сегодня"
                  CTA. New users see ONE pulsing CTA rather than
                  scanning 8+ options. */}
              <div className="mt-4">
                <DailyDrillCard
                  drillStreak={store.rating ? Math.max(0, store.rating.current_streak ?? 0) : 0}
                />
              </div>

              {/* Phase B — Weekly League hero widget (Duolingo cohort) */}
              <div className="mt-4">
                <LeagueHeroCard />
              </div>

              {/* 2026-05-02: «Быстро →» строка УДАЛЕНА полностью (была введена
                  2026-04-20). Пользователь: «никто не понимает зачем это надо,
                  они потворяют основные панели навигации». Тренировка/Лига/
                  Команды/Турнир/Ошибки уже доступны из Header — дубликаты
                  на странице лобби только мешают. */}
            </div>
          )}

          <div className="mt-6 grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
            <div className="space-y-6">

              {/* Find Match button */}
              {/* 2026-04-20: убрано y-смещение (12 → 0). Раньше кнопка
                  "вылетала" из потока — на странице было 55+ motion.div
                  с разными y (±8, ±12, ±20) и слагерами, пользователь:
                  «всё вылетает сверху вниз». Теперь все блоки fade-in
                  одной короткой длительностью без translate. */}
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.18, delay: 0.08 }}
              >
                <motion.button
                  onClick={handleFindMatch}
                  disabled={store.queueStatus !== "idle"}
                  className="btn-neon w-full flex items-center justify-center gap-3 text-lg py-5"
                  whileHover={{ scale: 1.01 }}
                  whileTap={{ scale: 0.98 }}
                >
                  {store.queueStatus !== "idle" ? (
                    <Loader2 size={20} className="animate-spin" />
                  ) : (
                    <>
                      <Sword weight="duotone" size={22} /> Найти соперника
                    </>
                  )}
                </motion.button>
              </motion.div>

              {/* Issue #169 — character picker. Custom presets created
                  in CharacterBuilder + presets shared by colleagues
                  (is_shared=true) appear here. ``null`` = random
                  archetype (legacy default). */}
              <div className="mt-3">
                <CharacterPicker
                  selectedId={pickedCharacterId}
                  onPick={setPickedCharacterId}
                  disabled={store.queueStatus !== "idle"}
                />
              </div>

              {/* Tabs — pixel chips. 2026-05-04: added "База ФЗ-127" tab
                  (RAG transparency view) per user request "видеть всё
                  что AI знает". */}
              <div className="flex flex-wrap gap-2">
                {(["arena", "knowledge", "rag", "history"] as const).map((t) => {
                  const active = tab === t;
                  const label =
                    t === "arena" ? "Дуэли"
                    : t === "knowledge" ? "Знания ФЗ-127"
                    : t === "rag" ? "База ФЗ-127"
                    : "История";
                  const icon: PixelIconName =
                    t === "arena" ? "sword"
                    : t === "knowledge" ? "book"
                    : t === "rag" ? "book"
                    : "ladder";
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

              {/* Arena (Duels) */}
              <AnimatePresence mode="wait">
                {tab === "arena" && (
                  <motion.div key="arena" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.18 }}>
                    <div className="space-y-4">
                      {/* 2026-05-04 cleanup: removed 8 dead mode cards
                          (4 PvP + 4 PvE). They had no `onClick` — clicking
                          them did literally nothing. 6 of 8 were also
                          shown locked at lvl 5/8/12, which scared new
                          users into thinking the platform was broken.
                          The single working entrypoint is the
                          "Найти соперника" button above; matchmaking
                          server picks PvP/PvE automatically.

                          When per-mode duels are reintroduced (story
                          modes, boss raids, etc), they should be
                          live functional cards with onClick → queue.join
                          payload extension, NOT cosmetic placeholders. */}

                      {/* How it works — pixel cards (was glass-panel) */}
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                        {[
                          { step: "01", title: "Подбор", desc: "Система находит соперника по рейтингу" },
                          { step: "02", title: "2 раунда", desc: "Вы и соперник по очереди продаёте и оцениваете" },
                          { step: "03", title: "Результат", desc: "ИИ-судья выносит вердикт, рейтинг обновляется" },
                        ].map((item) => (
                          <div
                            key={item.step}
                            className="flex flex-col p-4"
                            style={{
                              background: "var(--bg-panel)",
                              outline: "2px solid var(--border-color)",
                              outlineOffset: -2,
                              boxShadow: "3px 3px 0 0 var(--border-color)",
                              borderRadius: 0,
                            }}
                          >
                            <span className="font-pixel text-xs tracking-widest" style={{ color: "var(--accent)", letterSpacing: "0.18em" }}>{item.step}</span>
                            <p className="font-pixel text-sm uppercase mt-1.5" style={{ color: "var(--text-primary)", letterSpacing: "0.1em" }}>{item.title}</p>
                            <p className="text-xs mt-1 flex-1" style={{ color: "var(--text-muted)" }}>{item.desc}</p>
                          </div>
                        ))}
                      </div>

                      {/* 2026-04-20: блок "Последние дуэли" удалён.
                          Был дубль с вкладкой "История" — пользователь:
                          «у нас есть отдельная панель история, не надо
                          повторять где-то». Всё доступно в табе History. */}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Knowledge ФЗ-127 */}
              <AnimatePresence mode="wait">
                {tab === "knowledge" && (
                  <motion.div key="knowledge" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.18 }}>
                    <div className="space-y-4">
                      {/* Quiz mode selection — pixel unified (2026-04-29) */}
                      <div>
                        <p className="font-pixel text-xs uppercase tracking-wider mb-2" style={{ color: "var(--text-muted)" }}>▸ ВЫБЕРИ КВИЗ</p>
                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                          {([
                            { mode: "free_dialog" as const, icon: "book" as PixelIconName, label: "Свободный диалог", desc: "Без ограничений", color: "var(--accent)" },
                            { mode: "blitz" as const, icon: "bolt" as PixelIconName, label: "Блиц", desc: "20 × 60 сек", color: "var(--warning)" },
                            { mode: "themed" as const, icon: "target" as PixelIconName, label: "По теме", desc: "10 категорий", color: "var(--success)" },
                          ] as const).map(({ mode, icon, label, desc, color }) => (
                            <PixelModeCard
                              key={mode}
                              iconName={icon}
                              name={label}
                              desc={desc}
                              accent={color}
                              active={quizMode === mode}
                              onClick={() => { setQuizMode(mode); setQuizCategory(null); }}
                            />
                          ))}
                        </div>
                      </div>

                      {/* ═══ Category selection — pixel chips (2026-05-02) ═══ */}
                      {quizMode === "themed" && (
                        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.18 }}>
                          <p className="font-pixel text-xs uppercase tracking-wider mb-2" style={{ color: "var(--success)" }}>
                            ▸ ВЫБЕРИ ТЕМУ {quizCategory && <span className="ml-2" style={{ color: "var(--accent)" }}>● {quizCategory}</span>}
                          </p>
                          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                            {([
                              { id: "eligibility", label: "Условия подачи", icon: "book" as PixelIconName },
                              { id: "procedure", label: "Порядок процедуры", icon: "ladder" as PixelIconName },
                              { id: "property", label: "Имущество", icon: "castle" as PixelIconName },
                              { id: "consequences", label: "Последствия", icon: "skull" as PixelIconName },
                              { id: "costs", label: "Расходы", icon: "target" as PixelIconName },
                              { id: "creditors", label: "Кредиторы", icon: "group" as PixelIconName },
                              { id: "documents", label: "Документы", icon: "book" as PixelIconName },
                              { id: "timeline", label: "Сроки", icon: "bolt" as PixelIconName },
                              { id: "court", label: "Суд", icon: "castle" as PixelIconName },
                              { id: "rights", label: "Права должника", icon: "shield" as PixelIconName },
                            ] as const).map((cat) => {
                              const active = quizCategory === cat.id;
                              return (
                                <motion.button
                                  key={cat.id}
                                  type="button"
                                  whileHover={active ? {} : { x: -1, y: -1 }}
                                  whileTap={{ x: 2, y: 2, transition: { duration: 0.05 } }}
                                  transition={{ type: "spring", stiffness: 600, damping: 30 }}
                                  onClick={() => setQuizCategory(cat.id)}
                                  className="flex items-center gap-2 px-3 py-2 text-left relative"
                                  style={{
                                    background: active
                                      ? "color-mix(in srgb, var(--success) 14%, var(--bg-panel))"
                                      : "var(--bg-panel)",
                                    border: `2px solid ${active ? "var(--success)" : "var(--border-color)"}`,
                                    borderRadius: 0,
                                    boxShadow: active
                                      ? "3px 3px 0 0 var(--success), 0 0 12px color-mix(in srgb, var(--success) 35%, transparent)"
                                      : "2px 2px 0 0 var(--border-color)",
                                    cursor: "pointer",
                                    transition: "background 120ms",
                                  }}
                                >
                                  <PixelIcon name={cat.icon} size={20} color={active ? "var(--success)" : "var(--text-muted)"} />
                                  <span
                                    className="font-pixel uppercase"
                                    style={{
                                      color: active ? "var(--success)" : "var(--text-primary)",
                                      fontSize: 11,
                                      letterSpacing: "0.1em",
                                      lineHeight: 1.15,
                                    }}
                                  >
                                    {cat.label}
                                  </span>
                                  {active && (
                                    <span
                                      aria-hidden
                                      className="absolute top-1 right-1 font-pixel text-[9px]"
                                      style={{ color: "var(--success)" }}
                                    >▶ OK</span>
                                  )}
                                </motion.button>
                              );
                            })}
                          </div>
                        </motion.div>
                      )}

                      {/* ═══ AI Examiner selector — pixel mode cards (2026-05-02) ═══ */}
                      {quizMode && quizMode !== "blitz" && (
                        <motion.div
                          initial={{ opacity: 0, y: 8 }}
                          animate={{ opacity: 1, y: 0 }}
                        >
                          <p className="font-pixel text-xs uppercase tracking-wider mb-2" style={{ color: "var(--text-muted)" }}>
                            ▸ ВЫБЕРИ ЭКЗАМЕНАТОРА
                          </p>
                          <div className="grid grid-cols-2 gap-2">
                            {([
                              { id: "professor", icon: "book" as PixelIconName, name: "Профессор Кодексов", desc: "Академичный, с юмором" },
                              { id: "detective", icon: "target" as PixelIconName, name: "Арбитражный Следопыт", desc: "Кейсы и расследования" },
                            ] as const).map(({ id, icon, name, desc }) => (
                              <PixelModeCard
                                key={id}
                                iconName={icon}
                                name={name}
                                desc={desc}
                                accent="var(--accent)"
                                active={aiPersonality === id}
                                onClick={() => setAiPersonality(aiPersonality === id ? null : id)}
                              />
                            ))}
                          </div>
                        </motion.div>
                      )}

                      {/* Blitz mode: pixel auto-assigned badge */}
                      {quizMode === "blitz" && (
                        <div
                          className="inline-flex items-center gap-2 px-3 py-2 font-pixel text-xs uppercase tracking-wide"
                          style={{
                            background: "color-mix(in srgb, var(--warning) 12%, var(--bg-panel))",
                            color: "var(--warning)",
                            border: "2px solid var(--warning)",
                            borderRadius: 0,
                            boxShadow: "3px 3px 0 0 var(--warning)",
                            letterSpacing: "0.14em",
                          }}
                        >
                          <PixelIcon name="bolt" size={14} color="var(--warning)" />
                          ЭКЗАМЕНАТОР: БЛИЦ-МАСТЕР (авто)
                        </div>
                      )}

                      {/* ═══ Start quiz button ═══ */}
                      {quizMode && (quizMode !== "themed" || quizCategory) && (
                        <motion.button
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                          transition={{ duration: 0.18 }}
                          whileTap={{ scale: 0.98 }}
                          disabled={quizStarting}
                          className="w-full flex items-center justify-center gap-2 py-3 font-pixel text-sm uppercase tracking-wider"
                          style={{
                            background: "var(--accent)",
                            color: "#fff",
                            border: "2px solid var(--accent)",
                            borderRadius: 0,
                            boxShadow: "4px 4px 0 0 #000, 0 0 16px var(--accent-glow)",
                            transition: "box-shadow 120ms, transform 120ms",
                            opacity: quizStarting ? 0.6 : 1,
                          }}
                          onClick={async () => {
                            setQuizStarting(true);
                            // 2026-04-20: soft watchdog — через 10 сек
                            // форсируем сброс, чтобы кнопка не залипла
                            // даже если api.post висит в бэкграунде
                            // (fetch сам отменится на 30 сек — слишком
                            // долго для пользователя).
                            const watchdog = setTimeout(() => {
                              setQuizStarting(false);
                              useNotificationStore.getState().addToast({
                                title: "Таймаут",
                                body: "Сервер долго отвечает. Попробуйте ещё раз.",
                                type: "warning",
                              });
                            }, 10_000);
                            try {
                              const res = await api.post("/knowledge/sessions", {
                                mode: quizMode,
                                category: quizCategory,
                                ai_personality: quizMode === "blitz" ? "showman" : aiPersonality,
                              }) as { id?: string; session_id?: string };
                              clearTimeout(watchdog);
                              const sid = res?.id || res?.session_id;
                              if (sid) {
                                router.push(`/pvp/quiz/${sid}?mode=${quizMode}${quizCategory ? `&category=${quizCategory}` : ""}${aiPersonality ? `&personality=${aiPersonality}` : ""}`);
                              } else {
                                useNotificationStore.getState().addToast({ title: "Ошибка", body: "Не удалось создать сессию. Попробуйте ещё раз.", type: "error" });
                              }
                            } catch (e) {
                              clearTimeout(watchdog);
                              logger.error("Failed to start quiz:", e);
                              useNotificationStore.getState().addToast({ title: "Ошибка", body: "Не удалось начать тест. Проверьте подключение.", type: "error" });
                            } finally {
                              clearTimeout(watchdog);
                              setQuizStarting(false);
                            }
                          }}
                        >
                          {quizStarting ? <Loader2 size={16} className="animate-spin" /> : <Brain weight="duotone" size={16} />}
                          ▶ НАЧАТЬ ТЕСТ
                        </motion.button>
                      )}

                      {/* 2026-05-03 deep-cleanup:
                          1) «Турнир недели» виджет — УДАЛЁН.
                             Был дубль /pvp/tournament из Header. Привязка к
                             ФЗ-127 искусственная.
                          2) «PvP арена знаний» (Дуэль 1 на 1 / Командный бой)
                             — УДАЛЕНО. Это был второй набор PvP-режимов в табе
                             про право, путал пользователей. Основные PvP/PvE
                             режимы — в табе «Дуэли». Сценарий /pvp/arena/lobby
                             доступен через прямой URL если кому-то нужен. */}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* База ФЗ-127 — RAG transparency view (2026-05-04) */}
              <AnimatePresence mode="wait">
                {tab === "rag" && (
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
                      /* History items — pixel cards (2026-05-03) */
                      <div className="mt-6 space-y-3">
                        {store.myDuels.map((duel, i) => {
                          const isP1 = store.rating?.user_id === duel.player1_id;
                          const myScore = isP1 ? duel.player1_total : duel.player2_total;
                          const oppScore = isP1 ? duel.player2_total : duel.player1_total;
                          const myDelta = isP1 ? duel.player1_rating_delta : duel.player2_rating_delta;
                          const isWinner = duel.winner_id === store.rating?.user_id;
                          const ratingApplied = duel.rating_change_applied && !duel.is_pve;
                          const accent = duel.is_draw ? "var(--warning)" : isWinner ? "var(--success)" : "var(--danger)";

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
                                    {duel.is_draw ? "Ничья" : isWinner ? "Победа" : "Поражение"}
                                  </span>
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

            <FriendsPanel onChallengeSent={() => {
              store.setQueueStatus("searching");
            }} />
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

      {/* 2026-05-03 deep-cleanup: PvE-offer модалка УДАЛЕНА.
          Это был legacy fallback по WS-сообщению `pve.offer`, но handler
          выше (case "pve.offer") сразу вызывает store.setPvEOffer(null) —
          модалка фактически unreachable, dead code. Если в будущем
          понадобится PvE-offer flow, возрождать через MatchmakingOverlay
          с pixel-стилем, не возвращать старую glass-panel модалку. */}
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
