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
import { FriendsPanel } from "@/components/pvp/FriendsPanel";
import { AppIcon } from "@/components/ui/AppIcon";
import { logger } from "@/lib/logger";
// PR-B (2026-05-05): LeagueHeroCard, DailyDrillCard, PixelModeCard,
// Brain, Lock — больше не используются на /pvp (см. HonestNavigator + KILL).
import { PixelIcon, type PixelIconName } from "@/components/pvp/PixelIcon";
// Issue #169 — custom-character picker (PR #142 backend endpoint).
import { CharacterPicker } from "@/components/pvp/CharacterPicker";
// 2026-05-04: full-RAG transparency view ("видеть всё что AI знает").
import { KnowledgeBaseBrowser } from "@/components/pvp/KnowledgeBaseBrowser";
// PR-B (2026-05-05): single honest entry point — replaces PreCallWarmUpHero
// (4 фейк-кнопки), tab-Дуэли (3 текстовые карточки how-it-works), tab-Знания
// (3 mode + 10 cat + 2 personality = 60 комбинаций). См. комментарий в
// HonestNavigator.tsx для полного обоснования.
import { HonestNavigator } from "@/components/pvp/HonestNavigator";

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
  // PR-B (2026-05-05): tabs collapsed from 4 → 2 (history + knowledge_base).
  // Дуэли и Знания теперь живут в HonestNavigator выше табов (single primary
  // entry-point), поэтому таб для них не нужен. Legacy ?tab=knowledge / ?tab=arena
  // мапим на "history" (наиболее близкая landing-страница).
  const tabParam = searchParams.get("tab");
  const [tab, setTab] = useState<"history" | "knowledge_base">(
    tabParam === "knowledge_base" || tabParam === "rag" ? "knowledge_base" : "history"
  );
  const [quizStarting, setQuizStarting] = useState(false);
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
          // PR-cleanup (2026-05-05): pve.offer modal was removed earlier
          // (see comment block ниже — было setPvEOffer(null) для legacy
          // совместимости). Бэкенд эмитит этот case при матче в PvE,
          // FE просто отмечает статус "matched" — overlay показывает
          // спиннер, потом duel.brief/match.found приходят и редиректят.
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
    // Issue #169 — forward picked custom character id (or omit for random).
    const payload: Record<string, unknown> = { type: "queue.join" };
    if (pickedCharacterId) payload.character_id = pickedCharacterId;
    sendMessage(payload);
  }, [sendMessage, store, pickedCharacterId]);

  // PR-B (2026-05-05): inline quiz-start moved to a callable so the
  // HonestNavigator can fire it without re-implementing the watchdog +
  // session POST + redirect dance. ai_personality wired to "professor" by
  // default; "showman" for blitz keeps blitz UX unchanged. "detective"
  // dropped from FE — same backend RAG, only hint-style differs, was
  // never meaningfully chosen by pilot users.
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
        // PR-MC (2026-05-05): all 3 quiz cards now run in MC format —
        // 1 RAG-grounded correct option + 2 LLM-generated distractors,
        // rendered as 3 buttons in the quiz page. Free-text fallback
        // applies per-question if the enricher can't derive a correct
        // answer (very rare; chunk lacks correct_response_hint).
        choices_format: true,
      }) as { id?: string; session_id?: string };
      clearTimeout(watchdog);
      const sid = res?.id || res?.session_id;
      if (sid) {
        const params = new URLSearchParams({ mode });
        if (category) params.set("category", category);
        params.set("personality", personality);
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
                    { icon: Sword, label: "Дуэль с ботом", text: "Жми «Дуэль с ботом» — подберём AI-клиента (10 архетипов: скептик, тревожный, скандалист и др.). 2 раунда: ты продаёшь и оцениваешь, потом меняетесь. Если кто-то живой в очереди — попадёшь на него вместо бота." },
                    { icon: Target, label: "Квиз ФЗ-127", text: "«Свободный» — 10 вопросов, без таймера. «Блиц» — 20×60 сек, на скорость. «По теме» — выбираешь 1 из 10 категорий, 15 вопросов. После каждого ответа — разбор от AI и ссылка на статью закона." },
                    { icon: Lightning, label: "База ФЗ-127", text: "Вкладка «База ФЗ-127» — RAG-источники, которые AI использует для проверки твоих ответов. Ищи по статье или категории." },
                    { icon: Trophy, label: "Рейтинг", text: "Первые 10 дуэлей — калибровка, рейтинг прыгает. Потом стабильная Glicko-2: 8 тиров Iron → Grandmaster. Peak tier не теряется." },
                    { icon: Sparkle, label: "После боя", text: "AI-судья разбирает оба раунда: что сработало, где провалил. Плюс очки XP и Arena Points (AP). Не согласен с оценкой — нажми «Оспорить» (rejudge через cloud-LLM)." },
                  ]}
                  footer="Короткий путь: один из 4 блоков выше → бой/квиз → разбор → рейтинг"
                />
                {/* PR-B (2026-05-05): убрал кнопку «Рейтинг» — дубль
                    глобал-хедера, плюс RatingCard ниже уже линкует на
                    /pvp/leaderboard через footer-link. */}
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

              {/* PR-B (2026-05-05): DailyDrillCard + LeagueHeroCard
                  убраны с /pvp. DailyDrill уже отключён на /home (false &&
                  guard в home/page.tsx); LeagueHero доступен через
                  /leaderboard?tab=league напрямую. На /pvp оба только
                  шумели поверх RatingCard. */}

              {/* 2026-05-02: «Быстро →» строка УДАЛЕНА полностью (была введена
                  2026-04-20). Пользователь: «никто не понимает зачем это надо,
                  они потворяют основные панели навигации». Тренировка/Лига/
                  Команды/Турнир/Ошибки уже доступны из Header — дубликаты
                  на странице лобби только мешают. */}
            </div>
          )}

          <div className="mt-6 grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
            <div className="space-y-6">

              {/* PR-B (2026-05-05): the single honest navigator —
                  один блок с 4-мя реально различающимися режимами
                  (Дуэль / Квиз / Блиц / Тема). Заменяет PreCallWarmUpHero,
                  escape-button и контент бывших табов «Дуэли» и
                  «Знания ФЗ-127». См. HonestNavigator.tsx. */}
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

              {/* PR-B: CharacterPicker — power-user fea ture (Issue #169).
                  Спрятан под disclosure: 0% pilot-юзеров реально создавали
                  пресеты, но возможность остаётся. */}
              <details className="group">
                <summary
                  className="font-pixel uppercase cursor-pointer select-none flex items-center gap-2 px-3 py-2"
                  style={{
                    color: "var(--text-muted)",
                    fontSize: 11,
                    letterSpacing: "0.16em",
                    background: "rgba(0,0,0,0.2)",
                    border: "1px dashed var(--border-color)",
                    borderRadius: 0,
                  }}
                >
                  Расширенные настройки: персонаж
                </summary>
                <div className="mt-3">
                  <CharacterPicker
                    selectedId={pickedCharacterId}
                    onPick={setPickedCharacterId}
                    disabled={store.queueStatus !== "idle"}
                  />
                </div>
              </details>

              {/* Tabs — 2 чипа (PR-B 2026-05-05). Было 4: «Дуэли»
                  (контент = 3 текстовые карточки how-it-works → переехало
                  в InfoButton сверху) и «Знания ФЗ-127» (mode-cards +
                  category + personality → переехало в HonestNavigator).
                  Остаются только: «История» (мои дуэли) и «База ФЗ-127»
                  (RAG transparency view). */}
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

              {/* PR-B (2026-05-05): tab «Дуэли» содержал только 3 текстовые
                  карточки how-it-works — переехало в InfoButton сверху.
                  Сами дуэли стартуют через HonestNavigator выше табов. */}

              {/* PR-B: tab «Знания ФЗ-127» — содержимое (3 mode-card,
                  10 категорий, 2 personality, START button) переехало
                  в HonestNavigator. */}

              {/* База ФЗ-127 — RAG transparency view (2026-05-04) */}
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
