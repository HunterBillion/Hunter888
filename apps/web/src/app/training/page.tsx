"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { logger } from "@/lib/logger";
// 2026-04-20: cleaned unused imports left over from the 2026-04-18
// "Рекомендуемые" tab removal. AppIcon, ScenarioDossierCard, getTierColor,
// Lock, Info, ARCHETYPE_GROUPS, ArchetypeInfo, GROUP_ICONS, Sparkles,
// TrendingUp were all only referenced by the dead RecommendedTab function
// (also removed below).
import {
  Clock,
  Loader2,
  ArrowRight,
  Inbox,
  Users,
  Puzzle,
  BookOpen,
  ClipboardList,
  Filter,
  AlertTriangle,
  Target,
  Share2,
  RotateCcw,
  Sparkles,
} from "lucide-react";
import { useNotificationStore } from "@/stores/useNotificationStore";
import { PixelFaceIcon } from "@/components/pixel/PixelFaceIcon";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import AuthLayout from "@/components/layout/AuthLayout";
import CharacterBuilder from "@/components/training/CharacterBuilder";
import { useTrainingStore } from "@/stores/useTrainingStore";
import { ARCHETYPES, getDifficultyColor } from "@/lib/archetypes";
import { ArchetypeCard } from "@/components/training/ArchetypeCard";
import { ScenarioCatalogCard } from "@/components/training/ScenarioCatalogCard";
import { PixelInfoButton } from "@/components/ui/PixelInfoButton";
import type { Scenario } from "@/types";
import { Skeleton } from "@/components/ui/Skeleton";

// 2026-04-18: вкладка "Рекомендуемые" убрана из /training — она сбивала
// пользователя с главного flow. Из /home кнопка "Рекомендуемые" теперь
// ведёт в /training?tab=scenarios (та же логика подбора работает там же).
type Tab = "scenarios" | "assigned" | "builder" | "saved";

type PixelFace = "mask" | "check" | "gear" | "briefcase";

const TABS: { id: Tab; label: string; icon: React.ComponentType<{ size: number; style?: React.CSSProperties }>; pixelFace: PixelFace }[] = [
  { id: "scenarios", label: "Сценарии", icon: BookOpen, pixelFace: "mask" },
  { id: "assigned", label: "Назначенные", icon: ClipboardList, pixelFace: "check" },
  { id: "builder", label: "Конструктор", icon: Puzzle, pixelFace: "gear" },
  { id: "saved", label: "Мои клиенты", icon: Users, pixelFace: "briefcase" },
];

const TYPE_FILTERS = [
  { key: "all", label: "Все" },
  { key: "cold", label: "Холодные" },
  { key: "warm", label: "Тёплые" },
  { key: "in", label: "Входящие" },
  { key: "special", label: "Особые" },
  { key: "follow_up", label: "Повторный звонок" },
  { key: "crisis", label: "Кризис" },
  { key: "compliance", label: "Комплаенс" },
  { key: "multi_party", label: "Мультипарти" },
] as const;

const DIFF_FILTERS = [
  { key: "all", label: "Любая" },
  { key: "easy", label: "Лёгкая (1-3)" },
  { key: "medium", label: "Средняя (4-6)" },
  { key: "hard", label: "Сложная (7-10)" },
] as const;

function getDifficultyConfig(d: number) {
  if (d <= 3) return { label: "Легко", emoji: "🟢", color: "var(--success)", bg: "rgba(61,220,132,0.08)", border: "rgba(61,220,132,0.2)", desc: "Клиент лояльный, мало возражений" };
  if (d <= 6) return { label: "Средне", emoji: "🟡", color: "var(--warning)", bg: "rgba(245,158,11,0.08)", border: "rgba(245,158,11,0.2)", desc: "Стандартные возражения и ловушки" };
  if (d <= 8) return { label: "Сложно", emoji: "🔴", color: "var(--danger)", bg: "var(--danger-muted)", border: "rgba(229,72,77,0.2)", desc: "Агрессивный клиент, каскад ловушек" };
  return { label: "Босс", emoji: "💀", color: "var(--danger)", bg: "rgba(255,0,85,0.1)", border: "rgba(255,0,85,0.3)", desc: "Максимальная сложность, все ловушки" };
}

function TrainingPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  // Extract tab param as string to avoid unstable searchParams object reference
  const tabParam = searchParams.get("tab");
  const [tab, setTab] = useState<Tab>("scenarios");
  // Track both scenario id and optional archetype code so RecommendedTab
  // (where multiple cards can share the same matched scenario) lights up
  // the spinner ONLY on the specific card the user clicked.
  const [starting, setStarting] = useState<{ scenarioId: string; archCode?: string } | null>(null);
  const [startError, setStartError] = useState<string | null>(null);
  const [storyCalls, setStoryCalls] = useState<number>(3);
  // showInfoModal state removed 2026-04-18 \u2014 replaced by PixelInfoButton component.

  const fetchScenarios = useTrainingStore((s) => s.fetchScenarios);
  const fetchAssigned = useTrainingStore((s) => s.fetchAssigned);
  const assigned = useTrainingStore((s) => s.assigned);

  useEffect(() => {
    fetchScenarios();
    fetchAssigned();
  }, [fetchScenarios, fetchAssigned]);

  useEffect(() => {
    // Legacy ?tab=recommended (из /home или старых ссылок) маршрутизирует на scenarios.
    if (tabParam === "recommended") {
      setTab("scenarios");
    } else if (tabParam === "assigned" || tabParam === "builder" || tabParam === "saved" || tabParam === "scenarios") {
      setTab(tabParam);
    }
  }, [tabParam]);

  // Auto-dismiss error after 5 seconds
  useEffect(() => {
    if (startError) {
      const t = setTimeout(() => setStartError(null), 5000);
      return () => clearTimeout(t);
    }
  }, [startError]);

  // Phase F (2026-04-20) — unified start handler. Owner feedback:
  // «в СРМ карточке должен быть выбор чат или звонок» → кнопки теперь
  // прямо в ScenarioDossierCard. startTraining = chat; startTrainingCall
  // = voice. Оба POST'ят на /training/sessions одинаково, расходятся
  // только на шаге router.push — chat → /training/[id], call →
  // /training/[id]/call.
  const performStart = async (scenarioId: string, mode: "chat" | "call") => {
    setStarting({ scenarioId });
    setStartError(null);
    try {
      // TZ-2 §6.2/6.3 — canonical mode + legacy fallback. No real_client →
      // training_simulation runtime_type.
      const session = await api.post("/training/sessions", {
        scenario_id: scenarioId,
        mode,
        runtime_type: "training_simulation",
        custom_session_mode: mode, // legacy compat
      });
      const target = mode === "call"
        ? `/training/${session.id}/call`
        : `/training/${session.id}`;
      router.push(target);
    } catch (err) {
      logger.error("Failed to start training:", err);
      if (
        err instanceof ApiError &&
        err.status === 409 &&
        err.detail?.code === "profile_incomplete"
      ) {
        router.push("/onboarding");
        return;
      }
      if (
        err instanceof ApiError &&
        err.status === 409 &&
        err.detail &&
        err.detail.code === "session_already_active"
      ) {
        const existingId = err.detail.existing_session_id;
        if (typeof existingId === "string" && existingId.length > 0) {
          setStartError("У тебя уже есть активная тренировка — открываю её.");
          const target = mode === "call"
            ? `/training/${existingId}/call`
            : `/training/${existingId}`;
          setTimeout(() => router.push(target), 600);
          return;
        }
      }
      const message = err instanceof Error ? err.message : "Не удалось начать тренировку";
      if (message.includes("consent") || message.includes("согласи")) {
        router.push("/consent");
        return;
      }
      setStartError(message);
      setStarting(null);
    }
  };

  const startTraining = (scenarioId: string) => void performStart(scenarioId, "chat");
  const startTrainingCall = (scenarioId: string) => void performStart(scenarioId, "call");

  const startStoryTraining = (scenarioId: string, calls = 3) => {
    router.push(`/training/${scenarioId}?mode=story&calls=${calls}`);
  };

  const overdueCount = assigned.filter((a) => new Date(a.deadline) < new Date()).length;
  const assignedCount = assigned.length;

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
                className="glass-panel flex items-center gap-3 px-5 py-3 text-sm"
                style={{ borderColor: "var(--danger)", color: "var(--danger)" }}
              >
                <AlertTriangle size={16} />
                {startError}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="app-page">
          {/* Header */}
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
            <div className="flex items-start justify-between">
              <div>
                <h1 className="font-display text-2xl font-bold tracking-wide" style={{ color: "var(--text-primary)" }}>
                  Тренировки
                </h1>
                <p className="mt-1 text-sm" style={{ color: "var(--text-muted)" }}>
                  Выберите формат и сложность тренировки
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Link href="/training/archetypes">
                  <motion.button
                    className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium"
                    style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)", color: "var(--text-secondary)" }}
                    whileTap={{ scale: 0.97 }}
                  >
                    <BookOpen size={12} /> Каталог архетипов
                  </motion.button>
                </Link>
                <PixelInfoButton
                  title="Тренировки"
                  sections={[
                    { icon: Target, label: "Рекомендуемые", text: "AI подобрал сценарии под ваш уровень и слабые места" },
                    { icon: BookOpen, label: "Сценарии", text: "60 готовых сценариев в 8 группах — от холодных звонков до кризисных" },
                    { icon: ClipboardList, label: "Назначенные", text: "Задания от руководителя с дедлайнами" },
                    { icon: Puzzle, label: "Конструктор", text: "Соберите клиента из 100 архетипов, 25 профессий и 20 источников" },
                    { icon: Users, label: "Мои клиенты", text: "Сохранённые конфигурации для повторного использования" },
                  ]}
                  footer="Выберите сценарий → Начать → Общайтесь с AI голосом/текстом → разбор"
                />
              </div>
            </div>
          </motion.div>

          {/* PR-G: removed the "Пресет истории" duplicate.
              Pre-PR-G the user saw TWO controls for the same
              storyCalls value: this top bar AND the X3/X4/X5 cards
              inside the AI Story Mode banner (rendered by
              ScenariosTab). Pilot users said it read as inconsistency
              ("which is the source of truth?"). The in-banner cards
              already explain WHY each choice (3 звонка / 4 / 5),
              so they win — this top bar just repeated the active
              value. The banner stays the only place to change it. */}

          {/* Tabs */}
          <div className="mt-6 flex gap-1 rounded-xl p-1 overflow-x-auto" style={{ background: "var(--input-bg)" }}>
            {TABS.map((t) => {
              const Icon = t.icon;
              const active = tab === t.id;
              return (
                <button
                  key={t.id}
                  onClick={() => setTab(t.id)}
                  className="relative flex-1 flex items-center justify-center gap-2 sm:gap-2.5 rounded-lg px-2 sm:px-4 py-2.5 text-sm font-medium tracking-wide transition-colors whitespace-nowrap min-w-0"
                  style={{ color: active ? "var(--text-primary)" : "var(--text-muted)" }}
                >
                  {active && (
                    <motion.div
                      layoutId="activeTab"
                      className="absolute inset-0 rounded-lg"
                      style={{ background: "var(--glass-bg)", border: "1px solid var(--glass-border)" }}
                      transition={{ type: "spring", stiffness: 380, damping: 32, layout: { duration: 0.25 } }}
                    />
                  )}
                  <span className="relative z-10 flex items-center gap-2">
                    <PixelFaceIcon face={t.pixelFace} size={28} style={{ opacity: active ? 1 : 0.6 }} />
                    <span className="font-pixel text-[15px] uppercase leading-none tracking-wide">{t.label}</span>
                    {/* Badge for assigned tab */}
                    {t.id === "assigned" && assignedCount > 0 && (
                      <span
                        className="min-w-[18px] h-[18px] flex items-center justify-center rounded-full text-xs font-bold text-white px-1"
                        style={{ background: overdueCount > 0 ? "var(--danger)" : "var(--accent)" }}
                      >
                        {assignedCount}
                      </span>
                    )}
                  </span>
                </button>
              );
            })}
          </div>

          {/* Tab content */}
          <div style={{ overflow: "hidden" }}>
          <AnimatePresence mode="wait" initial={false}>
            {/* Вкладка "Рекомендуемые" убрана 2026-04-18 — логика AI-подбора
                перенесена в ScenariosTab через параметр. RecommendedTab-функция
                ниже оставлена в коде для истории; не используется. */}

            {tab === "scenarios" && (
              <motion.div key="scenarios" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.18 }}>
                <ScenariosTab
                  starting={starting}
                  storyCalls={storyCalls}
                  onStoryCallsChange={setStoryCalls}
                  onStart={startTraining}
                  onStartCall={startTrainingCall}
                  onStartStory={startStoryTraining}
                />
              </motion.div>
            )}

            {tab === "assigned" && (
              <motion.div key="assigned" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.18 }}>
                <AssignedTab onStart={startTraining} onStartCall={startTrainingCall} onStartStory={startStoryTraining} starting={starting} storyCalls={storyCalls} />
              </motion.div>
            )}

            {tab === "builder" && (
              <motion.div key="builder" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.18 }}>
                <CharacterBuilder storyCalls={storyCalls} />
              </motion.div>
            )}

            {tab === "saved" && (
              <motion.div key="saved" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.18 }}>
                <SavedTab storyCalls={storyCalls} />
              </motion.div>
            )}
          </AnimatePresence>
          </div>
        </div>
      </div>
    </AuthLayout>
  );
}

export default function TrainingPage() {
  return (
    <Suspense fallback={<AuthLayout><div className="relative panel-grid-bg min-h-screen" /></AuthLayout>}>
      <TrainingPageContent />
    </Suspense>
  );
}

/* ─── Scenarios Tab with Filters ──────────────────────────────────────────── */
/*
 * 2026-04-20: the `RecommendedTab` function that used to live here was dead
 * code — it had been dropped from the render tree in the 2026-04-18 refactor
 * and the accompanying comment said "оставлена в коде для истории".
 * Removed entirely along with its exclusive imports. Recommendation logic
 * now lives inside `ScenariosTab` (see `?tab=scenarios` entry flow).
 */

function ScenariosTab({
  starting,
  storyCalls,
  onStoryCallsChange,
  onStart,
  onStartCall,
  onStartStory,
}: {
  starting: { scenarioId: string; archCode?: string } | null;
  storyCalls: number;
  onStoryCallsChange: (calls: number) => void;
  onStart: (id: string, archCode?: string) => void;
  onStartCall?: (id: string) => void;
  onStartStory: (id: string, calls?: number) => void;
}) {
  const { scenariosLoading, typeFilter, difficultyFilter, setTypeFilter, setDifficultyFilter, filteredScenarios } = useTrainingStore();
  const filtered = filteredScenarios();

  if (scenariosLoading) {
    return (
      <div className="mt-6 grid gap-5 sm:grid-cols-2">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="glass-panel p-6 space-y-4 relative overflow-hidden rounded-2xl">
            <Skeleton height={6} width="100%" rounded="0" className="absolute top-0 left-0 right-0" />
            <div className="flex items-start gap-3">
              <Skeleton width={56} height={56} rounded="16px" />
              <div className="flex-1 space-y-2">
                <Skeleton height={20} width="66%" />
                <Skeleton height={12} width="100%" />
              </div>
              <Skeleton width={48} height={24} rounded="8px" />
            </div>
            <Skeleton height={16} width="75%" />
            <div className="flex gap-1">
              {[...Array(10)].map((_, j) => <Skeleton key={j} height={8} className="flex-1" rounded="999px" />)}
            </div>
            <div className="flex gap-2">
              <Skeleton width={80} height={24} rounded="8px" />
              <Skeleton width={80} height={24} rounded="8px" />
              <Skeleton width={64} height={24} rounded="8px" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Skeleton height={48} rounded="12px" />
              <Skeleton height={48} rounded="12px" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <>
      {/* AI Story Mode banner — PR-E polish: added Sparkles icon + violet
          glow on the active call-count card so the active option pops
          (was: barely-visible 1px border around active option). The
          left-side description and right-side option grid are unchanged
          structurally — pilot feedback was «чисто визуально можно
          улучшить не сильно». */}
      <div
        className="mt-6 overflow-hidden rounded-2xl"
        style={{
          background: "linear-gradient(135deg, rgba(5,5,6,0.95), rgba(18,18,22,0.94))",
          border: "1px solid var(--accent-muted)",
          boxShadow: "0 18px 45px rgba(0,0,0,0.28)",
        }}
      >
        <div className="grid gap-6 px-5 py-5 md:grid-cols-[1.1fr_0.9fr] md:px-6">
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide" style={{ color: "var(--accent)" }}>
              <Sparkles size={14} />
              <span>AI Story Mode</span>
            </div>
            <h2 className="mt-3 font-display text-2xl font-bold tracking-widest" style={{ color: "var(--text-primary)" }}>
              История клиента на несколько звонков
            </h2>
            <p className="mt-3 max-w-2xl text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
              Этот режим показывает развитие одного кейса в динамике: сохраняется контекст прошлых разговоров, меняются приоритеты клиента, а ваши решения влияют на следующий контакт.
            </p>
          </div>
          <div className="grid gap-3 sm:grid-cols-3 md:grid-cols-1">
            {[
              { label: "3 звонка", calls: 3, text: "Базовая история с быстрым развитием клиента." },
              { label: "4 звонка", calls: 4, text: "Больше времени на ошибки, давление и разворот сценария." },
              { label: "5 звонков", calls: 5, text: "Полная дуга клиента с памятью и накопленными эффектами." },
            ].map((item) => {
              const active = storyCalls === item.calls;
              return (
                <button
                  key={item.calls}
                  onClick={() => onStoryCallsChange(item.calls)}
                  className="rounded-xl px-4 py-3 text-left transition-all"
                  style={{
                    background: active ? "var(--accent-muted)" : "rgba(255,255,255,0.03)",
                    border: active ? "2px solid var(--accent)" : "1px solid rgba(255,255,255,0.08)",
                    boxShadow: active ? "0 0 18px -4px var(--accent)" : "none",
                  }}
                >
                  <div className="text-sm font-semibold" style={{ color: active ? "var(--accent)" : "var(--text-primary)" }}>
                    {item.label}
                  </div>
                  <div className="mt-1 text-sm leading-relaxed" style={{ color: "var(--text-muted)" }}>
                    {item.text}
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* ── Filters ──────────────────────────────────── */}
      <div className="mt-6 flex flex-wrap items-center gap-5">
        <div className="flex items-center gap-2.5">
          <Filter size={14} style={{ color: "var(--text-muted)" }} />
          <span className="text-sm font-semibold tracking-wider" style={{ color: "var(--text-secondary)" }}>Тип:</span>
          <div className="flex gap-1.5">
            {TYPE_FILTERS.map((f) => (
              <button
                key={f.key}
                onClick={() => setTypeFilter(f.key as typeof typeFilter)}
                className="rounded-lg px-3 py-1.5 text-xs font-medium transition-all"
                style={{
                  background: typeFilter === f.key ? "var(--accent-muted)" : "var(--input-bg)",
                  border: `1px solid ${typeFilter === f.key ? "var(--accent)" : "var(--border-color)"}`,
                  color: typeFilter === f.key ? "var(--accent)" : "var(--text-muted)",
                }}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          <span className="text-sm font-semibold tracking-wider" style={{ color: "var(--text-secondary)" }}>Сложность:</span>
          <div className="flex gap-1.5">
            {DIFF_FILTERS.map((f) => (
              <button
                key={f.key}
                onClick={() => setDifficultyFilter(f.key as typeof difficultyFilter)}
                className="rounded-lg px-3 py-1.5 text-xs font-medium transition-all"
                style={{
                  background: difficultyFilter === f.key ? "var(--accent-muted)" : "var(--input-bg)",
                  border: `1px solid ${difficultyFilter === f.key ? "var(--accent)" : "var(--border-color)"}`,
                  color: difficultyFilter === f.key ? "var(--accent)" : "var(--text-muted)",
                }}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── Scenario Grid ──────────────────────────────
          2026-04-18: ScenarioDossierCard был вторым разнящимся дизайном —
          заменён на унифицированный ArchetypeCard size="full". Для каждого
          сценария ищем связанный архетип по archetype_code (если нет —
          берём первый архетип с подходящей сложностью). Теперь /training
          (сценарии), /training (конструктор превью) и /training/archetypes
          используют ОДИН компонент и один визуальный язык. */}
      {filtered.length === 0 ? (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mt-16 flex flex-col items-center">
          <Inbox size={40} style={{ color: "var(--text-muted)" }} />
          {/* 2026-04-20: the previous copy claimed "Сценарии загружаются"
              in this branch, but the `scenariosLoading` gate above already
              returns the skeleton grid while loading — so by the time we
              hit this branch, loading is definitively done. The three real
              states are: filters too narrow, filters clear but catalog is
              empty, or filters clear and user hit an edge (no scenarios at
              all). The copy now distinguishes them honestly. */}
          <p className="mt-3 text-sm text-center max-w-sm" style={{ color: "var(--text-muted)" }}>
            {typeFilter !== "all" || difficultyFilter !== "all"
              ? "Ничего не найдено по выбранным фильтрам. Попробуйте сбросить их или выбрать другие."
              : "Пока нет доступных сценариев. Загляните позже или напишите руководителю."}
          </p>
          {(typeFilter !== "all" || difficultyFilter !== "all") && (
            <button
              onClick={() => {
                setTypeFilter("all");
                setDifficultyFilter("all");
              }}
              className="mt-4 text-sm underline decoration-dotted underline-offset-4"
              style={{ color: "var(--accent)" }}
            >
              Сбросить фильтры
            </button>
          )}
        </motion.div>
      ) : (
        <div className="mt-6 grid gap-5 grid-cols-1 md:grid-cols-2 lg:grid-cols-3 items-stretch">
          {filtered.map((scenario) => {
            const scenarioArch = (scenario as { archetype_code?: string }).archetype_code;
            const arch =
              (scenarioArch && ARCHETYPES.find((a) => a.code === scenarioArch)) ||
              [...ARCHETYPES].sort(
                (a, b) => Math.abs(a.difficulty - scenario.difficulty) - Math.abs(b.difficulty - scenario.difficulty)
              )[0];
            if (!arch) return null;
            // 2026-05-05 redesign: replaced uniform ArchetypeCard size="full"
            // with ScenarioCatalogCard — type-driven palette + difficulty
            // meter + clear primary action + collapsible weakness. Old
            // ArchetypeCard stays for /training/archetypes gallery and
            // constructor preview.
            return (
              <ScenarioCatalogCard
                key={scenario.id}
                arch={arch}
                scenario={scenario}
                isStarting={starting?.scenarioId === scenario.id}
                onStart={onStart}
                onStartCall={onStartCall ? (sid) => onStartCall(sid) : undefined}
                onStartStory={onStartStory}
                storyCalls={storyCalls}
              />
            );
          })}
        </div>
      )}
    </>
  );
}

/* ─── Assigned Trainings Tab ──────────────────────────────────────────────── */

function AssignedTab({
  onStart,
  onStartCall,
  onStartStory,
  starting,
  storyCalls,
}: {
  onStart: (id: string, archCode?: string) => void;
  onStartCall?: (id: string) => void;
  onStartStory: (id: string, calls?: number) => void;
  starting: { scenarioId: string; archCode?: string } | null;
  storyCalls: number;
}) {
  const { assigned, assignedLoading } = useTrainingStore();

  // 2026-04-22 (hotfix): useState + useEffect for recentHome USED TO live
  // AFTER the `if (assignedLoading) return …` early-return below. That
  // violated Rules of Hooks — on first render (assignedLoading === true)
  // those two hooks didn't run, on second render they did, so React
  // counted different hook totals between renders and threw Minified
  // React error #310 ("Rendered more hooks than during the previous
  // render"). Moved above the gate so hook order is stable.
  const [recentHome, setRecentHome] = useState<Array<{
    id: string; scenario_title: string; score_total: number | null;
    duration_seconds: number | null; ended_at: string | null;
  }>>([]);

  useEffect(() => {
    api.get<Array<{ id: string; scenario_title: string; score_total: number | null; duration_seconds: number | null; ended_at: string | null }>>("/training/recent-home?days=7")
      .then(setRecentHome)
      .catch((err) => logger.error("[training] recent-home fetch failed:", err));
  }, []);

  if (assignedLoading) {
    return (
      <div className="mt-8 space-y-4">
        {[1, 2].map((i) => (
          <div key={i} className="glass-panel p-5 animate-pulse">
            <div className="h-5 w-1/2 rounded bg-[var(--input-bg)]" />
            <div className="mt-3 h-3 w-1/3 rounded bg-[var(--input-bg)]" />
          </div>
        ))}
      </div>
    );
  }

  if (assigned.length === 0 && recentHome.length === 0) {
    return (
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mt-16 flex flex-col items-center">
        <ClipboardList size={40} style={{ color: "var(--text-muted)" }} />
        <p className="mt-3 text-sm" style={{ color: "var(--text-muted)" }}>
          Нет назначенных охот
        </p>
        <p className="mt-1 text-xs" style={{ color: "var(--text-muted)" }}>
          РОП может назначить вам сценарий
        </p>
      </motion.div>
    );
  }

  const now = new Date();

  return (
    <div className="mt-8 space-y-4">
      {assigned.map((item, i) => {
        const deadline = new Date(item.deadline);
        const isOverdue = deadline < now;
        const daysLeft = Math.ceil((deadline.getTime() - now.getTime()) / 86_400_000);
        const isStarting = starting?.scenarioId === item.scenario_id;

        return (
          <motion.div
            key={item.id}
            initial={{ opacity: 0, x: -12 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.08 }}
            className="glass-panel p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4"
            style={{
              borderLeft: `3px solid ${isOverdue ? "var(--danger)" : "var(--accent)"}`,
            }}
          >
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <h3 className="font-display font-semibold truncate" style={{ color: "var(--text-primary)" }}>
                  {item.scenario_title}
                </h3>
                {isOverdue && (
                  <AlertTriangle size={16} style={{ color: "var(--danger)", flexShrink: 0 }} />
                )}
              </div>
              <div className="mt-1.5 flex items-center gap-3 text-xs" style={{ color: "var(--text-muted)" }}>
                <span className="flex items-center gap-1">
                  <Clock size={11} />
                  {isOverdue ? (
                    <span style={{ color: "var(--danger)" }}>
                      Просрочено на {Math.abs(daysLeft)} дн.
                    </span>
                  ) : daysLeft <= 1 ? (
                    <span style={{ color: "var(--warning)" }}>Сегодня!</span>
                  ) : (
                    <span>Осталось {daysLeft} дн.</span>
                  )}
                </span>
                <span>До: {deadline.toLocaleDateString("ru-RU", { day: "numeric", month: "short" })}</span>
              </div>
            </div>

            <div className="flex shrink-0 gap-2">
              <motion.button
                onClick={() => onStart(item.scenario_id)}
                disabled={isStarting}
                className="btn-neon flex items-center gap-2"
                whileTap={{ scale: 0.97 }}
              >
                {isStarting ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <>
                    Начать
                    <ArrowRight size={14} />
                  </>
                )}
              </motion.button>
              <motion.button
                onClick={() => onStartStory(item.scenario_id, storyCalls)}
                className="btn-neon flex items-center gap-2"
                style={{ borderColor: "var(--accent-glow)", color: "var(--accent)" }}
                whileTap={{ scale: 0.97 }}
              >
                AI x{storyCalls}
              </motion.button>
            </div>
          </motion.div>
        );
      })}

      {/* ── Recent home sessions ─────────────────────────────────────── */}
      {recentHome.length > 0 && (
        <>
          <div className="mt-8 mb-3 flex items-center gap-2">
            <Clock size={14} style={{ color: "var(--text-muted)" }} />
            <span className="font-mono text-xs uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
              Недавние звонки с главной
            </span>
          </div>
          {recentHome.map((s, i) => (
            <motion.div
              key={s.id}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: i * 0.05 }}
              className="glass-panel p-4 mb-2 flex items-center justify-between cursor-pointer hover:opacity-80 transition-opacity"
              style={{ borderLeft: "3px solid var(--text-muted)" }}
              onClick={() => window.location.href = `/results/${s.id}`}
            >
              <div className="min-w-0">
                <h4 className="font-display text-sm font-medium truncate" style={{ color: "var(--text-primary)" }}>
                  {s.scenario_title}
                </h4>
                <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                  {s.ended_at ? new Date(s.ended_at).toLocaleDateString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : ""}
                  {s.duration_seconds ? ` · ${Math.round(s.duration_seconds / 60)} мин` : ""}
                </span>
              </div>
              {s.score_total != null && (
                <span className="font-mono font-bold text-sm shrink-0 ml-3" style={{ color: s.score_total >= 70 ? "var(--color-green, #22c55e)" : s.score_total >= 40 ? "var(--warning)" : "var(--danger)" }}>
                  {Math.round(s.score_total)}%
                </span>
              )}
            </motion.div>
          ))}
        </>
      )}
    </div>
  );
}

/* ─── Saved Characters Tab ─────────────────────────────────────────────────── */

function SavedTab({ storyCalls }: { storyCalls: number }) {
  const { savedCharacters, savedLoading, fetchSavedCharacters } = useTrainingStore();
  const router = useRouter();
  // 2026-04-23 Sprint 6 — retrain deep link: ?retrain_from=<sessionId>&char=<customCharId>.
  // Shown above the grid as a RetrainBadge when the matching saved char exists.
  const searchParamsSaved = useSearchParams();
  const retrainFrom = searchParamsSaved.get("retrain_from");
  const retrainChar = searchParamsSaved.get("char");
  const [starting, setStarting] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  // Card refs keyed by char id so we can scroll the matched card into view.
  const cardRefs = useRef<Record<string, HTMLDivElement | null>>({});

  useEffect(() => {
    fetchSavedCharacters();
  }, [fetchSavedCharacters]);

  // 2026-04-21: saved characters carry all 11 builder fields (+ tone).
  // Previously buildStoryUrl forwarded only archetype/profession/lead/
  // difficulty, so replaying a saved "Кидала · офис · shouty · night"
  // client through AI-x mode silently dropped 7 of his defining traits.
  // Now the URL mirrors the full CustomCharacter row so the session
  // reproduces what the manager saved.
  type SavedCharFull = {
    id?: string;
    archetype: string;
    profession: string;
    lead_source: string;
    difficulty: number;
    family_preset?: string | null;
    creditors_preset?: string | null;
    debt_stage?: string | null;
    debt_range?: string | null;
    emotion_preset?: string | null;
    bg_noise?: string | null;
    time_of_day?: string | null;
    client_fatigue?: string | null;
    tone?: string | null;
  };

  const buildStoryUrl = (scenarioId: string, char: SavedCharFull) => {
    const params = new URLSearchParams({
      mode: "story",
      calls: String(storyCalls),
      custom_archetype: char.archetype,
      custom_profession: char.profession,
      custom_lead_source: char.lead_source,
      custom_difficulty: String(char.difficulty),
    });
    // Null values stored on the server become missing query params — the
    // server re-interprets those as "use archetype default".
    const extra: Record<string, string | null | undefined> = {
      custom_family_preset: char.family_preset,
      custom_creditors_preset: char.creditors_preset,
      custom_debt_stage: char.debt_stage,
      custom_debt_range: char.debt_range,
      custom_emotion_preset: char.emotion_preset,
      custom_bg_noise: char.bg_noise,
      custom_time_of_day: char.time_of_day,
      custom_fatigue: char.client_fatigue,
      custom_tone: char.tone,
    };
    for (const [key, val] of Object.entries(extra)) {
      if (val) params.set(key, val);
    }
    return `/training/${scenarioId}?${params.toString()}`;
  };

  const handleStart = async (
    char: SavedCharFull,
    storyMode = false,
  ) => {
    const charKey = char.id || char.archetype;
    setStarting(charKey);
    try {
      const scenarios = await api.get("/scenarios/");
      let scenarioId: string | undefined;
      if (scenarios.length) {
        const sorted = [...scenarios].sort(
          (a: { difficulty: number }, b: { difficulty: number }) =>
            Math.abs(a.difficulty - char.difficulty) - Math.abs(b.difficulty - char.difficulty),
        );
        scenarioId = sorted[0].id;
      }
      if (storyMode && scenarioId) {
        router.push(buildStoryUrl(scenarioId, char));
        return;
      }
      // 2026-04-21: send the full CustomCharacter payload + the FK so the
      // session links to the saved row (and end_session can then update
      // play_count/best_score/avg_score/last_played_at).
      // TZ-2 §6.2/6.3: CharacterBuilder always starts a chat-mode
      // simulation (no real client linkage at this entry point).
      const session = await api.post("/training/sessions", {
        ...(scenarioId ? { scenario_id: scenarioId } : {}),
        ...(char.id ? { custom_character_id: char.id } : {}),
        mode: "chat",
        runtime_type: "training_simulation",
        custom_session_mode: "chat", // legacy compat
        custom_archetype: char.archetype,
        custom_profession: char.profession,
        custom_lead_source: char.lead_source,
        custom_difficulty: char.difficulty,
        custom_family_preset: char.family_preset ?? undefined,
        custom_creditors_preset: char.creditors_preset ?? undefined,
        custom_debt_stage: char.debt_stage ?? undefined,
        custom_debt_range: char.debt_range ?? undefined,
        custom_emotion_preset: char.emotion_preset ?? undefined,
        custom_bg_noise: char.bg_noise ?? undefined,
        custom_time_of_day: char.time_of_day ?? undefined,
        custom_fatigue: char.client_fatigue ?? undefined,
        custom_tone: char.tone ?? undefined,
      });
      router.push(`/training/${session.id}`);
    } catch (err) {
      // Phase F (2026-04-20) — same 409 rescue as startTraining.
      if (
        err instanceof ApiError &&
        err.status === 409 &&
        err.detail?.code === "profile_incomplete"
      ) {
        router.push("/onboarding");
        return;
      }
      if (
        err instanceof ApiError &&
        err.status === 409 &&
        err.detail &&
        err.detail.code === "session_already_active"
      ) {
        const existingId = err.detail.existing_session_id;
        if (typeof existingId === "string" && existingId.length > 0) {
          router.push(`/training/${existingId}`);
          return;
        }
      }
      setStarting(null);
    }
  };

  const handleDelete = async (id: string) => {
    setDeleting(id);
    try {
      await api.delete(`/characters/custom/${id}`);
      fetchSavedCharacters();
    } catch {
      // ignore
    } finally {
      setDeleting(null);
    }
  };

  // 2026-04-21: the backend has had /characters/custom/{id}/share since
  // constructor v2 but nothing in the UI exposed it — the share_code
  // column sat empty for every user. Now a Share button next to each
  // saved character calls that endpoint, appends the returned code to
  // the current origin's /characters/shared/ URL, and drops it on the
  // clipboard with a toast. No auth required to resolve a shared code,
  // so teams can copy-paste a link without exposing credentials.
  const handleShare = async (id: string, name: string) => {
    try {
      // api.post signature is (path, body, opts?) — the /share endpoint
      // doesn't need a body, so pass an empty object rather than omit.
      const res = await api.post<{ share_code: string }>(`/characters/custom/${id}/share`, {});
      const code = res.share_code;
      if (!code) throw new Error("No share code returned");
      const url = `${window.location.origin}/characters/shared/${code}`;
      try {
        await navigator.clipboard.writeText(url);
        useNotificationStore.getState().addToast({
          title: "Ссылка скопирована",
          body: `«${name}» → ${url}`,
          type: "success",
        });
      } catch {
        // Clipboard denied — still show the URL so the user can copy manually.
        useNotificationStore.getState().addToast({
          title: "Ссылка на персонажа",
          body: url,
          type: "info",
        });
      }
      fetchSavedCharacters();
    } catch (e) {
      logger.error("Share failed:", e);
      useNotificationStore.getState().addToast({
        title: "Не удалось поделиться",
        body: e instanceof Error ? e.message : "Попробуйте ещё раз",
        type: "error",
      });
    }
  };

  // 2026-04-23 Sprint 6 — match the saved char referenced by ?char=<id>.
  // Passed as `SavedCharFull` to RetrainBadge (it has everything the POST
  // body needs via char.id; see `handleStart` for payload shape).
  const matchedRetrainChar: SavedCharFull | null =
    retrainFrom && retrainChar
      ? ((savedCharacters.find((c) => c.id === retrainChar) as SavedCharFull | undefined) ?? null)
      : null;

  // Scroll the matched card into view once the data arrived.
  useEffect(() => {
    if (matchedRetrainChar && matchedRetrainChar.id) {
      const el = cardRefs.current[matchedRetrainChar.id];
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [matchedRetrainChar?.id, savedCharacters.length]);

  if (savedLoading) {
    return (
      <div className="mt-8 grid gap-4 sm:grid-cols-2">
        {[1, 2].map((i) => (
          <div key={i} className="glass-panel p-5 animate-pulse">
            <div className="h-5 w-2/3 rounded bg-[var(--input-bg)]" />
            <div className="mt-3 h-3 w-1/2 rounded bg-[var(--input-bg)]" />
          </div>
        ))}
      </div>
    );
  }

  if (savedCharacters.length === 0) {
    return (
      <div className="mt-16 flex flex-col items-center">
        <Users size={40} style={{ color: "var(--text-muted)" }} />
        <p className="mt-3 text-sm" style={{ color: "var(--text-muted)" }}>
          Сохранённые персонажи появятся здесь
        </p>
        <p className="mt-1 text-xs" style={{ color: "var(--text-muted)" }}>
          Создайте первого в Конструкторе
        </p>
      </div>
    );
  }

  return (
    <div className="mt-8">
      {/* 2026-04-23 Sprint 6 — Retrain banner when we landed here from
          /results → "Повторить с тем же клиентом" (custom-character path). */}
      {matchedRetrainChar && retrainFrom && (
        <RetrainBadge
          character={matchedRetrainChar}
          sessionId={retrainFrom}
          onDismiss={() => router.replace("/training?tab=saved")}
        />
      )}
      <div className="grid gap-4 sm:grid-cols-2">
      {savedCharacters.map((char, i) => {
        return (
          <motion.div
            key={char.id}
            ref={(el) => {
              cardRefs.current[char.id] = el;
            }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: i * 0.05 }}
            className="glass-panel p-5 relative overflow-hidden"
            style={
              matchedRetrainChar?.id === char.id
                ? { boxShadow: "0 0 0 2px var(--accent), 0 4px 20px color-mix(in srgb, var(--accent) 30%, transparent)" }
                : undefined
            }
          >
            <div className="absolute top-0 left-0 right-0 h-[2px]" style={{ background: "linear-gradient(90deg, transparent, var(--accent), transparent)" }} />
            <h3 className="font-display font-semibold" style={{ color: "var(--text-primary)" }}>
              {char.name}
            </h3>
            <div className="mt-2 flex items-center gap-2 flex-wrap">
              <span className="rounded-full px-2 py-0.5 text-xs font-medium" style={{ background: "var(--accent-muted)", color: "var(--accent)", border: "1px solid var(--accent)" }}>
                {char.archetype}
              </span>
              <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                {char.lead_source}
              </span>
            </div>
            <div className="mt-4 flex gap-2">
              <motion.button
                onClick={() => handleStart(char, false)}
                disabled={starting === (char.id || char.archetype)}
                className="btn-neon flex-1 flex items-center justify-center gap-2 text-xs"
                whileTap={{ scale: 0.97 }}
              >
                {starting === (char.id || char.archetype) ? <Loader2 size={14} className="animate-spin" /> : <><ArrowRight size={14} /> Тренироваться</>}
              </motion.button>
              <motion.button
                onClick={() => handleStart(char, true)}
                disabled={starting === (char.id || char.archetype)}
                className="btn-neon flex items-center justify-center gap-2 px-3 text-xs"
                style={{ borderColor: "var(--accent-glow)", color: "var(--accent)" }}
                whileTap={{ scale: 0.97 }}
              >
                AI x{storyCalls}
              </motion.button>
              <motion.button
                onClick={() => handleShare(char.id, char.name)}
                className="btn-neon px-3 text-xs"
                style={{ color: "var(--text-secondary)", borderColor: "var(--border-color)" }}
                whileTap={{ scale: 0.97 }}
                title="Поделиться — создать ссылку для коллег"
              >
                <Share2 size={12} />
              </motion.button>
              <motion.button
                onClick={() => {
                  if (window.confirm(`Удалить персонажа "${char.name}"?`)) {
                    handleDelete(char.id);
                  }
                }}
                disabled={deleting === char.id}
                className="btn-neon px-3 text-xs"
                style={{ color: "var(--danger)", borderColor: "rgba(229,72,77,0.3)" }}
                whileTap={{ scale: 0.97 }}
              >
                {deleting === char.id ? <Loader2 size={12} className="animate-spin" /> : "×"}
              </motion.button>
            </div>
          </motion.div>
        );
      })}
      </div>
    </div>
  );
}

/* ─── Retrain Badge (Sprint 6) ──────────────────────────────────────────────
   Shown above the saved-characters grid when the user lands on
   /training?tab=saved&retrain_from=<id>&char=<id>. Clones the source
   session with the same custom character and jumps into the new session.
   Default target is the chat route — call-mode repeat for constructor
   sessions is rare (the CRM card path handles voice).                       */

interface RetrainBadgeProps {
  character: {
    id?: string;
    name?: string;
    archetype: string;
  };
  sessionId: string;
  onDismiss: () => void;
}

function RetrainBadge({ character, sessionId, onDismiss }: RetrainBadgeProps) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);

  const handleStart = async () => {
    if (loading) return;
    setLoading(true);
    try {
      const payload: Record<string, unknown> = {
        clone_from_session_id: sessionId,
      };
      if (character.id) payload.custom_character_id = character.id;
      const session = await api.post<{ id: string }>("/training/sessions", payload);
      if (!session?.id) throw new Error("Сервер не вернул id сессии");
      router.push(`/training/${session.id}`);
    } catch (e) {
      logger.error("[RetrainBadge] clone failed:", e);
      if (
        e instanceof ApiError &&
        e.status === 409 &&
        e.detail?.code === "profile_incomplete"
      ) {
        router.push("/onboarding");
        return;
      }
      useNotificationStore.getState().addToast({
        title: "Не удалось повторить сеанс",
        body: e instanceof Error ? e.message : "Попробуйте ещё раз",
        type: "error",
      });
      setLoading(false);
    }
  };

  const displayName = character.name || character.archetype;

  return (
    <motion.div
      initial={{ opacity: 0, y: -12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28 }}
      className="glass-panel rounded-2xl p-4 mb-5 flex items-center gap-3 flex-wrap"
      style={{
        borderLeft: "3px solid var(--accent)",
        boxShadow: "0 2px 14px color-mix(in srgb, var(--accent) 18%, transparent)",
      }}
    >
      <RotateCcw size={16} style={{ color: "var(--accent)" }} />
      <div className="flex-1 min-w-[200px]">
        <div className="font-display text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
          Повторите сеанс с {displayName}
        </div>
        <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
          Те же параметры, тот же клиент.
        </div>
      </div>
      <motion.button
        type="button"
        onClick={handleStart}
        disabled={loading}
        whileTap={{ scale: 0.97 }}
        className="btn-neon flex items-center justify-center gap-2 px-4 text-xs font-semibold"
        style={{ color: "var(--accent)", borderColor: "var(--accent)" }}
      >
        {loading ? <Loader2 size={14} className="animate-spin" /> : <ArrowRight size={14} />}
        Начать
      </motion.button>
      <button
        type="button"
        onClick={onDismiss}
        className="text-xs px-2 py-1 rounded-md transition hover:opacity-100 opacity-60"
        style={{ color: "var(--text-muted)" }}
      >
        Закрыть
      </button>
    </motion.div>
  );
}
