"use client";

import { Suspense, useEffect, useState, useCallback, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { Swords, ArrowRight, Loader2, Trophy, Zap, BookOpen, Brain, Clock, Target, ShoppingBag, Lock } from "lucide-react";
import AuthLayout from "@/components/layout/AuthLayout";
import { api } from "@/lib/api";
import { useWebSocket } from "@/hooks/useWebSocket";
import { usePvPStore } from "@/stores/usePvPStore";
import { useNotificationStore } from "@/stores/useNotificationStore";
import { RatingCard } from "@/components/pvp/RatingCard";
import { MatchmakingOverlay } from "@/components/pvp/MatchmakingOverlay";
import { FriendsPanel } from "@/components/pvp/FriendsPanel";
import { logger } from "@/lib/logger";

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
  const [tab, setTab] = useState<"arena" | "knowledge" | "history" | "shop">(
    tabParam === "knowledge" ? "knowledge" : tabParam === "shop" ? "shop" : "arena"
  );
  const [quizMode, setQuizMode] = useState<"free_dialog" | "blitz" | "themed" | null>(null);
  const [quizCategory, setQuizCategory] = useState<string | null>(categoryParam || null);
  const [quizStarting, setQuizStarting] = useState(false);
  const [aiPersonality, setAiPersonality] = useState<string | null>(null);
  const [pveAccepting, setPveAccepting] = useState(false);
  const inviteSentRef = useRef(false);
  const autoPvERef = useRef(false);
  const searchStartedAtRef = useRef<number | null>(null);

  useEffect(() => {
    store.fetchRating();
    store.fetchMyDuels();
    store.fetchActiveSeason();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps -- mount-only init; store actions are stable Zustand refs

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
    sendMessage({ type: "queue.join" });
  }, [sendMessage, store]);

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

    api.post("/pvp/accept-pve", {})
      .then((data) => {
        const duelId = (data as { duel_id?: string })?.duel_id;
        if (!duelId) {
          autoPvERef.current = false;
          setPveAccepting(false);
          return;
        }
        store.resetQueue();
        store.setQueueStatus("matched");
        router.push(`/pvp/duel/${duelId}`);
      })
      .catch((err) => {
        logger.error("Auto PvE match failed:", err);
        autoPvERef.current = false;
        useNotificationStore.getState().addToast({
          title: "Ошибка подбора",
          body: "Не удалось найти PvE-соперника. Попробуйте позже.",
          type: "error",
        });
      })
      .finally(() => {
        setPveAccepting(false);
      });
  }, [store.queueStatus, store.estimatedWait, router, store]);

  const formatTime = (iso: string) => {
    const d = new Date(iso);
    return d.toLocaleDateString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  };

  return (
    <AuthLayout>
      <div className="relative arena-grid-bg min-h-screen">
        <div className="mx-auto max-w-6xl px-4 py-8">
          {/* PvP-4 fix: connection status banner */}
          {connectionState !== "connected" && (
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              className="mb-4 flex items-center gap-3 rounded-2xl border px-4 py-3 text-sm"
              style={{
                borderColor: connectionState === "error" ? "rgba(255,42,109,0.3)" : "rgba(255,180,0,0.3)",
                background: connectionState === "error" ? "rgba(255,42,109,0.08)" : "rgba(255,180,0,0.08)",
                color: connectionState === "error" ? "#FF889B" : "#FFB400",
              }}
            >
              <Loader2 size={16} className="animate-spin" />
              {connectionState === "error"
                ? "Не удалось подключиться к серверу PvP. Проверьте, что бэкенд запущен."
                : connectionState === "reconnecting"
                  ? "Переподключение к серверу PvP..."
                  : "Подключение к серверу PvP..."}
            </motion.div>
          )}
          {/* Header */}
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Swords size={28} style={{ color: "var(--accent)" }} />
                <div>
                  <h1 className="font-display text-2xl sm:text-3xl font-black tracking-wide" style={{ color: "var(--text-primary)" }}>
                    PVP Арена
                  </h1>
                  <p className="text-xs font-mono mt-0.5" style={{ color: "var(--text-muted)" }}>
                    Дуэли 1 на 1 · Glicko-2 рейтинг
                  </p>
                </div>
              </div>
              <motion.button
                onClick={() => router.push("/pvp/leaderboard")}
                className="btn-neon flex items-center gap-2 text-xs"
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
                  className="btn-neon w-full flex items-center justify-center gap-3 text-lg py-5"
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
                {(["arena", "knowledge", "history", "shop"] as const).map((t) => (
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
                    <span className="relative z-10 flex items-center gap-1">
                      {t === "shop" && <ShoppingBag size={12} />}
                      {t === "arena" ? "Дуэли" : t === "knowledge" ? "Знания ФЗ-127" : t === "shop" ? "Магазин" : "История"}
                    </span>
                  </button>
                ))}
              </div>

              {/* Arena (Duels) */}
              <AnimatePresence mode="wait">
                {tab === "arena" && (
                  <motion.div key="arena" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
                    <div className="space-y-4">
                      {/* PvP Mode Selection */}
                      <div>
                        <p className="text-xs font-mono tracking-wider mb-2" style={{ color: "var(--text-muted)" }}>РЕЖИМЫ PVP</p>
                        <div className="grid grid-cols-2 gap-2">
                          {([
                            { code: "classic", name: "Классическая дуэль", desc: "2 раунда, смена ролей", icon: "\u2694\uFE0F", level: 5 },
                            { code: "rapid", name: "Rapid Fire", desc: "5 мини-раундов по 2 мин", icon: "\u26A1", level: 9 },
                            { code: "gauntlet", name: "Гантлет", desc: "3-5 дуэлей подряд", icon: "\uD83C\uDFF0", level: 10 },
                            { code: "team2v2", name: "Team 2v2", desc: "Команда из 2 продавцов", icon: "\uD83D\uDC65", level: 12 },
                          ] as const).map((mode) => {
                            const userLevel = store.rating ? Math.max(1, Math.floor(store.rating.total_duels / 2) + 1) : 1;
                            const locked = userLevel < mode.level;
                            return (
                              <motion.div
                                key={mode.code}
                                whileHover={locked ? {} : { scale: 1.02 }}
                                className="glass-panel rounded-xl p-3 text-left relative"
                                style={{ opacity: locked ? 0.5 : 1, cursor: locked ? "not-allowed" : "default" }}
                              >
                                {locked && <Lock size={14} className="absolute top-2 right-2" style={{ color: "var(--text-muted)" }} />}
                                <span className="text-lg">{mode.icon}</span>
                                <p className="mt-1 text-sm font-medium" style={{ color: "var(--text-primary)" }}>{mode.name}</p>
                                <p className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>{mode.desc}</p>
                                {locked && <p className="text-xs font-mono mt-1" style={{ color: "var(--warning)" }}>Ур. {mode.level}</p>}
                              </motion.div>
                            );
                          })}
                        </div>
                      </div>

                      {/* PvE Mode Selection */}
                      <div>
                        <p className="text-xs font-mono tracking-wider mb-2" style={{ color: "var(--text-muted)" }}>РЕЖИМЫ PVE</p>
                        <div className="grid grid-cols-2 gap-2">
                          {([
                            { code: "standard", name: "Стандартный бот", desc: "Обычная PvE дуэль", icon: "\uD83E\uDD16", level: 3 },
                            { code: "ladder", name: "Bot Ladder", desc: "5 ботов, рост сложности", icon: "\uD83D\uDCF6", level: 9 },
                            { code: "boss", name: "Boss Rush", desc: "3 уникальных босса", icon: "\uD83D\uDC80", level: 10 },
                            { code: "mirror", name: "Mirror Match", desc: "Играй против себя", icon: "\uD83E\uDE9E", level: 15 },
                          ] as const).map((mode) => {
                            const userLevel = store.rating ? Math.max(1, Math.floor(store.rating.total_duels / 2) + 1) : 1;
                            const locked = userLevel < mode.level;
                            return (
                              <motion.div
                                key={mode.code}
                                whileHover={locked ? {} : { scale: 1.02 }}
                                className="glass-panel rounded-xl p-3 text-left relative"
                                style={{ opacity: locked ? 0.5 : 1, cursor: locked ? "not-allowed" : "default" }}
                              >
                                {locked && <Lock size={14} className="absolute top-2 right-2" style={{ color: "var(--text-muted)" }} />}
                                <span className="text-lg">{mode.icon}</span>
                                <p className="mt-1 text-sm font-medium" style={{ color: "var(--text-primary)" }}>{mode.name}</p>
                                <p className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>{mode.desc}</p>
                                {locked && <p className="text-xs font-mono mt-1" style={{ color: "var(--warning)" }}>Ур. {mode.level}</p>}
                              </motion.div>
                            );
                          })}
                        </div>
                      </div>

                      {/* Quick info */}
                      <div className="glass-panel p-4 flex items-center gap-3">
                        <Swords size={18} style={{ color: "var(--accent)" }} />
                        <div>
                          <p className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>Голосовая дуэль</p>
                          <p className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                            Два раунда · смена ролей · Glicko-2 рейтинг
                          </p>
                        </div>
                      </div>

                      {/* How it works */}
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                        {[
                          { step: "01", title: "Подбор", desc: "Система находит соперника по рейтингу" },
                          { step: "02", title: "2 раунда", desc: "Вы и соперник по очереди продаёте и оцениваете" },
                          { step: "03", title: "Результат", desc: "ИИ-судья выносит вердикт, рейтинг обновляется" },
                        ].map((item) => (
                          <div key={item.step} className="glass-panel p-4 flex flex-col">
                            <span className="font-mono text-xs tracking-wider" style={{ color: "var(--accent)" }}>{item.step}</span>
                            <p className="text-sm font-medium mt-1" style={{ color: "var(--text-primary)" }}>{item.title}</p>
                            <p className="text-xs mt-0.5 flex-1" style={{ color: "var(--text-muted)" }}>{item.desc}</p>
                          </div>
                        ))}
                      </div>

                      {/* Recent duels preview */}
                      {store.myDuels.length > 0 && (
                        <div>
                          <p className="text-xs font-mono tracking-wider mb-2" style={{ color: "var(--text-muted)" }}>ПОСЛЕДНИЕ ДУЭЛИ</p>
                          <div className="space-y-2">
                            {store.myDuels.slice(0, 3).map((duel) => {
                              const isP1 = store.rating?.user_id === duel.player1_id;
                              const isWinner = duel.winner_id === store.rating?.user_id;
                              return (
                                <div
                                  key={duel.id}
                                  className="glass-panel p-3 flex items-center gap-3 cursor-pointer"
                                  style={{ borderLeft: `3px solid ${duel.is_draw ? "var(--warning)" : isWinner ? "var(--neon-green)" : "var(--neon-red)"}` }}
                                  onClick={() => router.push(`/pvp/duel/${duel.id}`)}
                                >
                                  <span className="text-xs font-medium" style={{ color: isWinner ? "var(--neon-green)" : duel.is_draw ? "var(--warning)" : "var(--neon-red)" }}>
                                    {duel.is_draw ? "Ничья" : isWinner ? "Победа" : "Поражение"}
                                  </span>
                                  <span className="text-xs font-mono ml-auto" style={{ color: "var(--text-muted)" }}>
                                    {DUEL_STATUS_LABELS[duel.status] || duel.status}
                                  </span>
                                  <ArrowRight size={12} style={{ color: "var(--text-muted)" }} />
                                </div>
                              );
                            })}
                          </div>
                          {store.myDuels.length > 3 && (
                            <button
                              onClick={() => setTab("history")}
                              className="mt-2 text-xs font-mono"
                              style={{ color: "var(--accent)" }}
                            >
                              Вся история →
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Knowledge ФЗ-127 */}
              <AnimatePresence mode="wait">
                {tab === "knowledge" && (
                  <motion.div key="knowledge" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
                    <div className="space-y-4">
                      {/* Mode selection */}
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                        {([
                          { mode: "free_dialog" as const, icon: BookOpen, label: "Свободный диалог", desc: "Без ограничений", color: "#6366F1" },
                          { mode: "blitz" as const, icon: Clock, label: "Блиц", desc: "20 × 60 сек", color: "#F59E0B" },
                          { mode: "themed" as const, icon: Target, label: "По теме", desc: "10 категорий", color: "#10B981" },
                        ]).map(({ mode, icon: Icon, label, desc, color }) => (
                          <motion.button
                            key={mode}
                            whileHover={{ scale: 1.02 }}
                            whileTap={{ scale: 0.98 }}
                            onClick={() => { setQuizMode(mode); setQuizCategory(null); }}
                            className="glass-panel rounded-xl p-4 text-left transition-all"
                            style={{
                              borderColor: quizMode === mode ? color : "var(--glass-border)",
                              boxShadow: quizMode === mode ? `0 0 0 1px ${color}, 0 0 12px ${color}20` : "none",
                            }}
                          >
                            <Icon size={20} style={{ color }} />
                            <p className="mt-2 text-sm font-medium" style={{ color: "var(--text-primary)" }}>{label}</p>
                            <p className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>{desc}</p>
                          </motion.button>
                        ))}
                      </div>

                      {/* Category selection for themed mode */}
                      {quizMode === "themed" && (
                        <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }}>
                          <p className="text-xs font-mono mb-2" style={{ color: "var(--text-secondary)" }}>ВЫБЕРИТЕ КАТЕГОРИЮ:</p>
                          <div className="grid grid-cols-2 gap-2">
                            {[
                              { id: "eligibility", label: "Условия подачи" },
                              { id: "procedure", label: "Порядок процедуры" },
                              { id: "property", label: "Имущество" },
                              { id: "consequences", label: "Последствия" },
                              { id: "costs", label: "Расходы" },
                              { id: "creditors", label: "Кредиторы" },
                              { id: "documents", label: "Документы" },
                              { id: "timeline", label: "Сроки" },
                              { id: "court", label: "Суд" },
                              { id: "rights", label: "Права должника" },
                            ].map((cat) => (
                              <button
                                key={cat.id}
                                onClick={() => setQuizCategory(cat.id)}
                                className="rounded-lg px-3 py-2 text-left text-xs font-mono transition-all"
                                style={{
                                  background: quizCategory === cat.id ? "rgba(16,185,129,0.15)" : "var(--input-bg)",
                                  color: quizCategory === cat.id ? "#10B981" : "var(--text-secondary)",
                                  border: quizCategory === cat.id ? "1px solid rgba(16,185,129,0.3)" : "1px solid transparent",
                                }}
                              >
                                {cat.label}
                              </button>
                            ))}
                          </div>
                        </motion.div>
                      )}

                      {/* V2: AI Personality selector */}
                      {quizMode && quizMode !== "blitz" && (
                        <motion.div
                          initial={{ opacity: 0, y: 8 }}
                          animate={{ opacity: 1, y: 0 }}
                        >
                          <p className="text-xs font-mono tracking-wider mb-2" style={{ color: "var(--text-muted)" }}>
                            ЭКЗАМЕНАТОР
                          </p>
                          <div className="grid grid-cols-2 gap-2">
                            {([
                              { id: "professor", emoji: "\uD83C\uDF93", name: "Профессор Кодексов", desc: "Академичный, с юмором" },
                              { id: "detective", emoji: "\uD83D\uDD0D", name: "Арбитражный Следопыт", desc: "Кейсы и расследования" },
                            ] as const).map(({ id, emoji, name, desc }) => (
                              <button
                                key={id}
                                onClick={() => setAiPersonality(aiPersonality === id ? null : id)}
                                className="rounded-lg p-3 text-left text-xs transition-all"
                                style={{
                                  background: aiPersonality === id ? "rgba(99,102,241,0.15)" : "var(--input-bg)",
                                  color: aiPersonality === id ? "#6366F1" : "var(--text-secondary)",
                                  border: aiPersonality === id ? "1px solid rgba(99,102,241,0.3)" : "1px solid transparent",
                                }}
                              >
                                <span className="text-lg mr-1">{emoji}</span>
                                <span className="font-medium">{name}</span>
                                <p className="mt-1 text-xs" style={{ color: "var(--text-muted)" }}>{desc}</p>
                              </button>
                            ))}
                          </div>
                        </motion.div>
                      )}

                      {/* Blitz mode: show auto-assigned personality */}
                      {quizMode === "blitz" && (
                        <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                          <span className="text-lg mr-1">&#x26A1;</span> Ваш ведущий — <strong>Блиц-Мастер</strong>
                        </p>
                      )}

                      {/* Start quiz button */}
                      {quizMode && (quizMode !== "themed" || quizCategory) && (
                        <motion.button
                          initial={{ opacity: 0, y: 8 }}
                          animate={{ opacity: 1, y: 0 }}
                          whileTap={{ scale: 0.98 }}
                          disabled={quizStarting}
                          className="btn-neon w-full flex items-center justify-center gap-2 py-3"
                          onClick={async () => {
                            setQuizStarting(true);
                            try {
                              const res = await api.post("/knowledge/sessions", {
                                mode: quizMode,
                                category: quizCategory,
                                ai_personality: quizMode === "blitz" ? "showman" : aiPersonality,
                              }) as { id?: string; session_id?: string };
                              const sid = res?.id || res?.session_id;
                              if (sid) {
                                router.push(`/pvp/quiz/${sid}?mode=${quizMode}${quizCategory ? `&category=${quizCategory}` : ""}${aiPersonality ? `&personality=${aiPersonality}` : ""}`);
                              } else {
                                useNotificationStore.getState().addToast({ title: "Ошибка", body: "Не удалось создать сессию. Попробуйте ещё раз.", type: "error" });
                              }
                            } catch (e) {
                              logger.error("Failed to start quiz:", e);
                              useNotificationStore.getState().addToast({ title: "Ошибка", body: "Не удалось начать тест. Проверьте подключение.", type: "error" });
                            } finally {
                              setQuizStarting(false);
                            }
                          }}
                        >
                          {quizStarting ? <Loader2 size={16} className="animate-spin" /> : <Brain size={16} />}
                          Начать тест
                        </motion.button>
                      )}

                      {/* Tournament widget */}
                      <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        className="mt-4 rounded-xl p-4 cursor-pointer"
                        style={{
                          background: "linear-gradient(135deg, rgba(255,215,0,0.06), rgba(255,165,0,0.03))",
                          border: "1px solid rgba(255,215,0,0.15)",
                        }}
                        onClick={() => router.push("/pvp/tournament")}
                      >
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-lg">{"\uD83C\uDFC6"}</span>
                          <span className="text-sm font-bold" style={{ color: "#FFD700" }}>Турнир недели</span>
                          <span className="ml-auto text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                            Подробнее →
                          </span>
                        </div>
                        <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                          Соревнуйтесь за призы и место на подиуме
                        </p>
                      </motion.div>

                      {/* PvP Arena Knowledge Section */}
                      <div className="mt-6 pt-4" style={{ borderTop: "1px solid var(--glass-border)" }}>
                        <p className="text-xs font-mono tracking-wider mb-3" style={{ color: "var(--text-muted)" }}>
                          PVP АРЕНА ЗНАНИЙ
                        </p>
                        <div className="grid grid-cols-2 gap-3">
                          <motion.button
                            whileHover={{ scale: 1.02 }}
                            whileTap={{ scale: 0.98 }}
                            onClick={() => {
                              // Navigate to knowledge WS and send pvp.find_opponent
                              router.push("/pvp/arena/lobby?mode=2");
                            }}
                            className="glass-panel rounded-xl p-4 text-left"
                            style={{ borderColor: "var(--neon-red)", borderWidth: 1 }}
                          >
                            <Swords size={20} style={{ color: "var(--neon-red)" }} />
                            <p className="mt-2 text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                              Дуэль 1 на 1
                            </p>
                            <p className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                              2 игрока · 10 раундов
                            </p>
                          </motion.button>
                          <motion.button
                            whileHover={{ scale: 1.02 }}
                            whileTap={{ scale: 0.98 }}
                            onClick={() => {
                              router.push("/pvp/arena/lobby?mode=4");
                            }}
                            className="glass-panel rounded-xl p-4 text-left"
                            style={{ borderColor: "var(--warning)", borderWidth: 1 }}
                          >
                            <Trophy size={20} style={{ color: "var(--warning)" }} />
                            <p className="mt-2 text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                              Командный бой
                            </p>
                            <p className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                              4 игрока · 10 раундов
                            </p>
                          </motion.button>
                        </div>
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

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
                          const ratingApplied = duel.rating_change_applied && !duel.is_pve;

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
                                  <span className="font-mono text-xs px-1.5 py-0.5 rounded" style={{ background: "var(--input-bg)", color: "var(--text-muted)" }}>
                                    {DUEL_STATUS_LABELS[duel.status] || duel.status}
                                  </span>
                                  {duel.is_pve && <span className="font-mono text-xs" style={{ color: "var(--warning)" }}>PvE</span>}
                                </div>
                                <div className="mt-1 font-mono text-xs" style={{ color: "var(--text-muted)" }}>
                                  {formatTime(duel.created_at)} · {Math.round(myScore)} vs {Math.round(oppScore)}
                                </div>
                              </div>
                              <div
                                className="font-mono text-sm font-bold"
                                style={{ color: ratingApplied ? (myDelta >= 0 ? "var(--neon-green)" : "var(--neon-red)") : "var(--warning)" }}
                              >
                                {ratingApplied ? `${myDelta >= 0 ? "+" : ""}${Math.round(myDelta)}` : "Без рейтинга"}
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

              {/* Shop */}
              <AnimatePresence mode="wait">
                {tab === "shop" && (
                  <motion.div key="shop" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
                    <div className="space-y-4">
                      <div className="flex items-center gap-2">
                        <span className="text-2xl font-bold" style={{ color: "var(--text-primary)" }}>
                          {store.rating?.total_duels ? store.rating.total_duels * 15 : 0}
                        </span>
                        <span className="text-sm font-mono" style={{ color: "var(--text-muted)" }}>Arena Points</span>
                      </div>
                      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                        {([
                          { code: "hint_pack_3", name: "3 подсказки", cost: 50, icon: "\uD83D\uDCA1" },
                          { code: "replay_token", name: "Токен реплея", cost: 80, icon: "\uD83D\uDD04" },
                          { code: "xp_boost_2h", name: "XP Boost 2ч", cost: 120, icon: "\uD83D\uDE80" },
                          { code: "avatar_frame_gold", name: "Рамка Gold", cost: 200, icon: "\uD83D\uDDBC\uFE0F" },
                          { code: "scenario_unlock", name: "Разблокировка сценария", cost: 300, icon: "\uD83D\uDD13" },
                          { code: "title_duelist", name: 'Титул "Дуэлянт"', cost: 500, icon: "\uD83C\uDFC5" },
                        ]).map((item) => (
                          <motion.div
                            key={item.code}
                            whileHover={{ scale: 1.02 }}
                            className="glass-panel rounded-xl p-4 flex flex-col"
                          >
                            <span className="text-2xl mb-2">{item.icon}</span>
                            <h3 className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>{item.name}</h3>
                            <p className="text-xs font-mono mt-1" style={{ color: "var(--accent)" }}>{item.cost} AP</p>
                            <motion.button
                              whileTap={{ scale: 0.95 }}
                              className="mt-3 w-full py-2 rounded-lg font-mono text-xs font-bold uppercase tracking-wider"
                              style={{ background: "var(--accent)", color: "#fff" }}
                              onClick={() => {
                                useNotificationStore.getState().addToast({
                                  title: "Покупка",
                                  body: `${item.name} будет доступен после интеграции магазина.`,
                                  type: "info",
                                });
                              }}
                            >
                              Купить
                            </motion.button>
                          </motion.div>
                        ))}
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            <FriendsPanel onChallengeSent={() => {
              store.setQueueStatus("searching");
            }} />
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
            opponentRating={store.matchedOpponentRating ?? undefined}
            onCancel={handleCancelQueue}
          />
        )}
      </AnimatePresence>

      {/* PvE offer modal — legacy fallback */}
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
                    store.resetQueue();
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
                  className="flex-1 py-2.5 rounded-xl font-mono text-xs font-bold uppercase tracking-wider btn-neon"
                  onClick={() => {
                    sendMessage({ type: "queue.leave" });
                    store.resetQueue();
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
