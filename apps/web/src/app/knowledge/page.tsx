"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  BookOpen,
  Zap,
  MessageSquare,
  Tag,
  Swords,
  ArrowRight,
  Loader2,
  Trophy,
  Search,
  Brain,
  Target,
  Clock,
  CheckCircle2,
  BarChart3,
} from "lucide-react";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";
import AuthLayout from "@/components/layout/AuthLayout";
import {
  useKnowledgeStore,
  type QuizMode,
  type CategoryProgress,
} from "@/stores/useKnowledgeStore";

/* ─── Mode Cards Config ──────────────────────────────────────────────────── */

const MODES: {
  id: QuizMode;
  label: string;
  description: string;
  icon: typeof Brain;
  color: string;
  gradient: string;
}[] = [
  {
    id: "free_dialog",
    label: "Свободный диалог",
    description: "AI задаёт вопросы по всем темам. Без ограничений по времени и количеству.",
    icon: MessageSquare,
    color: "#8B5CF6",
    gradient: "linear-gradient(135deg, rgba(139,92,246,0.15), rgba(139,92,246,0.05))",
  },
  {
    id: "blitz",
    label: "Блиц",
    description: "20 вопросов за 5 минут. Быстрые ответы, максимальная концентрация.",
    icon: Zap,
    color: "#F59E0B",
    gradient: "linear-gradient(135deg, rgba(245,158,11,0.15), rgba(245,158,11,0.05))",
  },
  {
    id: "themed",
    label: "По теме",
    description: "Выберите категорию и углубитесь в конкретную тему базы знаний.",
    icon: Tag,
    color: "#00FF66",
    gradient: "linear-gradient(135deg, rgba(0,255,102,0.12), rgba(0,255,102,0.04))",
  },
];

/* ─── Knowledge Page Content ─────────────────────────────────────────────── */

function KnowledgePageContent() {
  const router = useRouter();
  const store = useKnowledgeStore();

  const [selectedMode, setSelectedMode] = useState<QuizMode>("free_dialog");
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [categories, setCategories] = useState<CategoryProgress[]>([]);
  const [categoriesLoading, setCategoriesLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  // Fetch categories on mount
  useEffect(() => {
    setCategoriesLoading(true);
    api
      .get("/knowledge/categories")
      .then((data) => {
        const cats: CategoryProgress[] = Array.isArray(data)
          ? data
          : data?.categories ?? [];
        setCategories(cats);
        store.setCategories(cats);
      })
      .catch((err) => {
        logger.error("Failed to fetch knowledge categories:", err);
        // Use mock categories if API not ready
        const mockCats: CategoryProgress[] = [
          { category: "Продукт", totalAnswers: 45, correctAnswers: 38, masteryPct: 84 },
          { category: "Возражения", totalAnswers: 30, correctAnswers: 21, masteryPct: 70 },
          { category: "Скрипты", totalAnswers: 20, correctAnswers: 16, masteryPct: 80 },
          { category: "CRM и процессы", totalAnswers: 15, correctAnswers: 9, masteryPct: 60 },
          { category: "Конкуренты", totalAnswers: 10, correctAnswers: 5, masteryPct: 50 },
          { category: "Юридические аспекты", totalAnswers: 8, correctAnswers: 7, masteryPct: 87 },
        ];
        setCategories(mockCats);
        store.setCategories(mockCats);
      })
      .finally(() => setCategoriesLoading(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-dismiss error
  useEffect(() => {
    if (startError) {
      const t = setTimeout(() => setStartError(null), 5000);
      return () => clearTimeout(t);
    }
  }, [startError]);

  const handleStart = async () => {
    setStarting(true);
    setStartError(null);

    try {
      const body: Record<string, unknown> = { mode: selectedMode };
      if (selectedMode === "themed" && selectedCategory) {
        body.category = selectedCategory;
      }
      const session = await api.post("/knowledge/sessions", body);
      store.init(selectedMode, selectedCategory ?? undefined);
      store.setSessionId(session.id);
      router.push(`/knowledge/${session.id}`);
    } catch (err) {
      logger.error("Failed to start knowledge quiz:", err);
      const message =
        err instanceof Error ? err.message : "Не удалось начать квиз";
      setStartError(message);
      setStarting(false);
    }
  };

  const overallMastery =
    categories.length > 0
      ? Math.round(
          categories.reduce((sum, c) => sum + c.masteryPct, 0) / categories.length,
        )
      : 0;

  const totalAnswers = categories.reduce((s, c) => s + c.totalAnswers, 0);
  const totalCorrect = categories.reduce((s, c) => s + c.correctAnswers, 0);

  return (
    <AuthLayout>
      <div className="relative panel-grid-bg min-h-screen">
        {/* Error toast */}
        <AnimatePresence>
          {startError && (
            <motion.div
              initial={{ opacity: 0, y: -20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              className="fixed top-4 left-1/2 z-50 -translate-x-1/2"
            >
              <div
                className="glass-panel flex items-center gap-3 px-5 py-3 text-sm font-mono"
                style={{ borderColor: "var(--neon-red, #FF3333)", color: "var(--neon-red, #FF3333)" }}
              >
                {startError}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="app-page">
          {/* Header */}
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
            <div className="flex items-center gap-2">
              <Brain size={20} style={{ color: "var(--accent)" }} />
              <h1
                className="font-display text-2xl font-bold tracking-[0.15em]"
                style={{ color: "var(--text-primary)" }}
              >
                БАЗА ЗНАНИЙ
              </h1>
            </div>
            <p
              className="mt-2 font-mono text-xs tracking-wider"
              style={{ color: "var(--text-muted)" }}
            >
              ПРОВЕРЬТЕ СВОИ ЗНАНИЯ ПО ПРОДУКТУ И СКРИПТАМ
            </p>
          </motion.div>

          {/* Stats Overview */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4"
          >
            {[
              {
                icon: Target,
                label: "Общее владение",
                value: `${overallMastery}%`,
                color: overallMastery >= 75 ? "#00FF66" : overallMastery >= 50 ? "#F59E0B" : "#FF3333",
              },
              {
                icon: CheckCircle2,
                label: "Правильных",
                value: String(totalCorrect),
                color: "#00FF66",
              },
              {
                icon: BarChart3,
                label: "Всего ответов",
                value: String(totalAnswers),
                color: "var(--accent)",
              },
              {
                icon: BookOpen,
                label: "Категорий",
                value: String(categories.length),
                color: "#8B5CF6",
              },
            ].map((stat) => {
              const Icon = stat.icon;
              return (
                <div
                  key={stat.label}
                  className="glass-panel p-4"
                  style={{ borderColor: "rgba(255,255,255,0.06)" }}
                >
                  <div className="flex items-center gap-2">
                    <Icon size={14} style={{ color: stat.color }} />
                    <span
                      className="font-mono text-[10px] uppercase tracking-widest"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {stat.label}
                    </span>
                  </div>
                  <div
                    className="mt-2 font-display text-2xl font-bold"
                    style={{ color: stat.color }}
                  >
                    {stat.value}
                  </div>
                </div>
              );
            })}
          </motion.div>

          {/* Mode Selection */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.15 }}
            className="mt-8"
          >
            <div
              className="font-mono text-[10px] uppercase tracking-[0.22em]"
              style={{ color: "var(--accent)" }}
            >
              РЕЖИМ КВИЗА
            </div>
            <div className="mt-3 grid gap-4 sm:grid-cols-3">
              {MODES.map((mode, i) => {
                const Icon = mode.icon;
                const active = selectedMode === mode.id;
                return (
                  <motion.button
                    key={mode.id}
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.2 + i * 0.05 }}
                    onClick={() => {
                      setSelectedMode(mode.id);
                      if (mode.id !== "themed") setSelectedCategory(null);
                    }}
                    className="relative overflow-hidden rounded-2xl border p-5 text-left transition-all"
                    style={{
                      background: active ? mode.gradient : "rgba(255,255,255,0.02)",
                      borderColor: active
                        ? `${mode.color}55`
                        : "rgba(255,255,255,0.06)",
                      boxShadow: active
                        ? `0 0 30px ${mode.color}15`
                        : "none",
                    }}
                  >
                    {active && (
                      <div
                        className="absolute top-0 left-0 right-0 h-[2px]"
                        style={{
                          background: `linear-gradient(90deg, transparent, ${mode.color}, transparent)`,
                        }}
                      />
                    )}
                    <div className="flex items-center gap-3">
                      <div
                        className="flex h-10 w-10 items-center justify-center rounded-xl"
                        style={{
                          background: `${mode.color}18`,
                          border: `1px solid ${mode.color}30`,
                        }}
                      >
                        <Icon size={20} style={{ color: mode.color }} />
                      </div>
                      <div>
                        <div
                          className="font-display font-semibold"
                          style={{
                            color: active ? mode.color : "var(--text-primary)",
                          }}
                        >
                          {mode.label}
                        </div>
                      </div>
                    </div>
                    <p
                      className="mt-3 text-sm leading-relaxed"
                      style={{ color: "var(--text-secondary)" }}
                    >
                      {mode.description}
                    </p>
                    {mode.id === "blitz" && (
                      <div className="mt-3 flex items-center gap-1.5">
                        <Clock size={12} style={{ color: mode.color }} />
                        <span
                          className="font-mono text-[10px]"
                          style={{ color: mode.color }}
                        >
                          5:00
                        </span>
                        <span
                          className="font-mono text-[10px]"
                          style={{ color: "var(--text-muted)" }}
                        >
                          / 20 вопросов
                        </span>
                      </div>
                    )}
                  </motion.button>
                );
              })}
            </div>
          </motion.div>

          {/* Category Grid (themed mode) */}
          <AnimatePresence mode="wait">
            {selectedMode === "themed" && (
              <motion.div
                key="categories"
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.3 }}
                className="mt-6 overflow-hidden"
              >
                <div
                  className="font-mono text-[10px] uppercase tracking-[0.22em]"
                  style={{ color: "var(--accent)" }}
                >
                  ВЫБЕРИТЕ ТЕМУ
                </div>
                {categoriesLoading ? (
                  <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {[1, 2, 3, 4, 5, 6].map((i) => (
                      <div
                        key={i}
                        className="glass-panel p-5 animate-pulse"
                      >
                        <div className="h-5 w-2/3 rounded bg-[var(--input-bg)]" />
                        <div className="mt-3 h-2 w-full rounded bg-[var(--input-bg)]" />
                        <div className="mt-2 h-3 w-1/3 rounded bg-[var(--input-bg)]" />
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {categories.map((cat, i) => {
                      const active = selectedCategory === cat.category;
                      const masteryColor =
                        cat.masteryPct >= 75
                          ? "#00FF66"
                          : cat.masteryPct >= 50
                            ? "#F59E0B"
                            : "#FF3333";
                      return (
                        <motion.button
                          key={cat.category}
                          initial={{ opacity: 0, y: 10 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{ delay: i * 0.04 }}
                          onClick={() => setSelectedCategory(cat.category)}
                          className="relative overflow-hidden rounded-xl border p-4 text-left transition-all"
                          style={{
                            background: active
                              ? "rgba(139,92,246,0.1)"
                              : "rgba(255,255,255,0.02)",
                            borderColor: active
                              ? "rgba(139,92,246,0.4)"
                              : "rgba(255,255,255,0.06)",
                          }}
                        >
                          {active && (
                            <div
                              className="absolute top-0 left-0 right-0 h-[2px]"
                              style={{
                                background:
                                  "linear-gradient(90deg, transparent, #8B5CF6, transparent)",
                              }}
                            />
                          )}
                          <div className="flex items-center justify-between">
                            <span
                              className="font-display font-semibold text-sm"
                              style={{ color: "var(--text-primary)" }}
                            >
                              {cat.category}
                            </span>
                            <span
                              className="font-mono text-xs font-bold"
                              style={{ color: masteryColor }}
                            >
                              {cat.masteryPct}%
                            </span>
                          </div>
                          {/* Progress bar */}
                          <div
                            className="mt-3 h-1.5 w-full overflow-hidden rounded-full"
                            style={{ background: "rgba(255,255,255,0.06)" }}
                          >
                            <motion.div
                              initial={{ width: 0 }}
                              animate={{ width: `${cat.masteryPct}%` }}
                              transition={{ duration: 0.6, delay: i * 0.05 }}
                              className="h-full rounded-full"
                              style={{ background: masteryColor }}
                            />
                          </div>
                          <div
                            className="mt-2 flex items-center gap-3 font-mono text-[10px]"
                            style={{ color: "var(--text-muted)" }}
                          >
                            <span>
                              {cat.correctAnswers}/{cat.totalAnswers} верно
                            </span>
                          </div>
                        </motion.button>
                      );
                    })}
                  </div>
                )}
              </motion.div>
            )}
          </AnimatePresence>

          {/* PvP Arena Section */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="mt-8 overflow-hidden rounded-2xl"
            style={{
              background:
                "linear-gradient(135deg, rgba(5,5,6,0.95), rgba(18,18,22,0.94))",
              border: "1px solid rgba(245,158,11,0.18)",
              boxShadow: "0 18px 45px rgba(0,0,0,0.28)",
            }}
          >
            <div className="p-6">
              <div className="flex items-center gap-3">
                <div
                  className="flex h-10 w-10 items-center justify-center rounded-xl"
                  style={{
                    background: "rgba(245,158,11,0.12)",
                    border: "1px solid rgba(245,158,11,0.3)",
                  }}
                >
                  <Swords size={20} style={{ color: "#F59E0B" }} />
                </div>
                <div>
                  <div
                    className="font-mono text-[10px] uppercase tracking-[0.28em]"
                    style={{ color: "#F59E0B" }}
                  >
                    PVP АРЕНА
                  </div>
                  <h2
                    className="font-display text-lg font-bold tracking-[0.06em]"
                    style={{ color: "var(--text-primary)" }}
                  >
                    Вызовите коллегу на дуэль знаний
                  </h2>
                </div>
              </div>
              <p
                className="mt-3 max-w-2xl text-sm leading-relaxed"
                style={{ color: "var(--text-secondary)" }}
              >
                Оба игрока получают одинаковые вопросы. Побеждает тот, кто
                ответит правильнее и быстрее. Результаты попадают в лидерборд.
              </p>
              <div className="mt-5 flex flex-wrap gap-3">
                <motion.button
                  onClick={() => {
                    setSelectedMode("pvp");
                    // PvP matching would be handled via WS
                  }}
                  className="flex items-center gap-2 rounded-xl border px-5 py-3 font-mono text-xs tracking-[0.12em] transition-all"
                  style={{
                    borderColor: "rgba(245,158,11,0.3)",
                    background: "rgba(245,158,11,0.1)",
                    color: "#F59E0B",
                  }}
                  whileHover={{
                    background: "rgba(245,158,11,0.18)",
                    borderColor: "rgba(245,158,11,0.5)",
                  }}
                  whileTap={{ scale: 0.98 }}
                >
                  <Search size={14} />
                  Найти соперника
                </motion.button>
                <motion.button
                  className="flex items-center gap-2 rounded-xl border px-5 py-3 font-mono text-xs tracking-[0.12em] transition-all"
                  style={{
                    borderColor: "rgba(255,255,255,0.08)",
                    background: "rgba(255,255,255,0.03)",
                    color: "var(--text-secondary)",
                  }}
                  whileHover={{ background: "rgba(255,255,255,0.06)" }}
                  whileTap={{ scale: 0.98 }}
                >
                  <Trophy size={14} />
                  Рейтинг PvP
                </motion.button>
              </div>
            </div>
          </motion.div>

          {/* Start Button */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.35 }}
            className="mt-8 pb-10"
          >
            <motion.button
              onClick={handleStart}
              disabled={
                starting ||
                (selectedMode === "themed" && !selectedCategory)
              }
              className="vh-btn-primary flex w-full items-center justify-center gap-3 rounded-2xl py-4 text-base font-semibold tracking-wider disabled:opacity-40 disabled:cursor-not-allowed"
              whileTap={{ scale: 0.98 }}
            >
              {starting ? (
                <Loader2 size={20} className="animate-spin" />
              ) : (
                <>
                  <Brain size={20} />
                  {selectedMode === "themed" && !selectedCategory
                    ? "Выберите тему для начала"
                    : selectedMode === "blitz"
                      ? "Запустить блиц"
                      : selectedMode === "pvp"
                        ? "Начать поиск соперника"
                        : "Начать квиз"}
                  <ArrowRight size={18} />
                </>
              )}
            </motion.button>
          </motion.div>
        </div>
      </div>
    </AuthLayout>
  );
}

export default function KnowledgePage() {
  return (
    <Suspense
      fallback={
        <AuthLayout>
          <div className="relative panel-grid-bg min-h-screen" />
        </AuthLayout>
      }
    >
      <KnowledgePageContent />
    </Suspense>
  );
}
