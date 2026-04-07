"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { logger } from "@/lib/logger";
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
  Sparkles,
  TrendingUp,
  Lock,
  Info,
} from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api";
import AuthLayout from "@/components/layout/AuthLayout";
import CharacterBuilder from "@/components/training/CharacterBuilder";
import { ScenarioDossierCard } from "@/components/training/ScenarioDossierCard";
import { useTrainingStore } from "@/stores/useTrainingStore";
import { ARCHETYPES, ARCHETYPE_GROUPS, getTierColor, getDifficultyColor } from "@/lib/archetypes";
import type { ArchetypeInfo } from "@/lib/archetypes";
import type { Scenario } from "@/types";

type Tab = "recommended" | "scenarios" | "assigned" | "builder" | "saved";

const TABS: { id: Tab; label: string; icon: React.ComponentType<{ size: number; style?: React.CSSProperties }> }[] = [
  { id: "recommended", label: "Рекомендуемые", icon: Target },
  { id: "scenarios", label: "Сценарии", icon: BookOpen },
  { id: "assigned", label: "Назначенные", icon: ClipboardList },
  { id: "builder", label: "Конструктор", icon: Puzzle },
  { id: "saved", label: "Мои клиенты", icon: Users },
];

const TYPE_FILTERS = [
  { key: "all", label: "Все" },
  { key: "cold", label: "Холодные" },
  { key: "warm", label: "Тёплые" },
  { key: "in", label: "Входящие" },
  { key: "special", label: "Особые" },
  { key: "follow_up", label: "Follow-up" },
  { key: "crisis", label: "Кризис" },
  { key: "compliance", label: "Комплаенс" },
  { key: "multi_party", label: "Мультипарти" },
] as const;

const DIFF_FILTERS = [
  { key: "all", label: "Любая" },
  { key: "easy", label: "1-3" },
  { key: "medium", label: "4-6" },
  { key: "hard", label: "7-10" },
] as const;

function getDifficultyConfig(d: number) {
  if (d <= 3) return { label: "Легко", emoji: "🟢", color: "var(--neon-green, #00FF94)", bg: "rgba(0,255,148,0.08)", border: "rgba(0,255,148,0.2)", desc: "Клиент лояльный, мало возражений" };
  if (d <= 6) return { label: "Средне", emoji: "🟡", color: "var(--warning)", bg: "rgba(245,158,11,0.08)", border: "rgba(245,158,11,0.2)", desc: "Стандартные возражения и ловушки" };
  if (d <= 8) return { label: "Сложно", emoji: "🔴", color: "var(--neon-red, #FF3333)", bg: "rgba(255,51,51,0.08)", border: "rgba(255,51,51,0.2)", desc: "Агрессивный клиент, каскад ловушек" };
  return { label: "Босс", emoji: "💀", color: "#FF0055", bg: "rgba(255,0,85,0.1)", border: "rgba(255,0,85,0.3)", desc: "Максимальная сложность, все ловушки" };
}

function TrainingPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  // Extract tab param as string to avoid unstable searchParams object reference
  const tabParam = searchParams.get("tab");
  const [tab, setTab] = useState<Tab>("recommended");
  const [starting, setStarting] = useState<string | null>(null);
  const [startError, setStartError] = useState<string | null>(null);
  const [storyCalls, setStoryCalls] = useState<number>(3);
  const [showInfoModal, setShowInfoModal] = useState(false);

  const fetchScenarios = useTrainingStore((s) => s.fetchScenarios);
  const fetchAssigned = useTrainingStore((s) => s.fetchAssigned);
  const assigned = useTrainingStore((s) => s.assigned);

  useEffect(() => {
    fetchScenarios();
    fetchAssigned();
  }, [fetchScenarios, fetchAssigned]);

  useEffect(() => {
    if (tabParam === "recommended" || tabParam === "assigned" || tabParam === "builder" || tabParam === "saved" || tabParam === "scenarios") {
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

  const startTraining = async (scenarioId: string) => {
    setStarting(scenarioId);
    setStartError(null);
    try {
      const session = await api.post("/training/sessions", { scenario_id: scenarioId });
      router.push(`/training/${session.id}`);
    } catch (err) {
      logger.error("Failed to start training:", err);
      const message = err instanceof Error ? err.message : "Не удалось начать тренировку";
      // Handle consent redirect hint from backend
      if (message.includes("consent") || message.includes("согласи")) {
        router.push("/consent");
        return;
      }
      setStartError(message);
      setStarting(null);
    }
  };

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
                className="glass-panel flex items-center gap-3 px-5 py-3 text-sm font-mono"
                style={{ borderColor: "var(--neon-red, #FF3333)", color: "var(--neon-red, #FF3333)" }}
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
                <Link href="/wiki">
                  <motion.button
                    className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-mono"
                    style={{ background: "rgba(245,158,11,0.1)", border: "1px solid rgba(245,158,11,0.25)", color: "#f59e0b" }}
                    whileTap={{ scale: 0.97 }}
                  >
                    <BookOpen size={12} /> Моя база знаний
                  </motion.button>
                </Link>
                <Link href="/training/archetypes">
                  <motion.button
                    className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-mono"
                    style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)", color: "var(--text-secondary)" }}
                    whileTap={{ scale: 0.97 }}
                  >
                    <BookOpen size={12} /> Каталог архетипов
                  </motion.button>
                </Link>
                <motion.button
                  onClick={() => setShowInfoModal(true)}
                  className="rounded-full p-2 transition-colors"
                  style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)" }}
                  whileTap={{ scale: 0.95 }}
                  title="Справка"
                >
                  <Info size={16} style={{ color: "var(--text-muted)" }} />
                </motion.button>
              </div>
            </div>
          </motion.div>

          {/* Info modal */}
          <AnimatePresence>
            {showInfoModal && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="fixed inset-0 z-[200] flex items-center justify-center p-4"
                style={{ background: "rgba(0,0,0,0.5)", backdropFilter: "blur(4px)" }}
                onClick={() => setShowInfoModal(false)}
              >
                <motion.div
                  initial={{ scale: 0.9, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  exit={{ scale: 0.9, opacity: 0 }}
                  className="glass-panel rounded-2xl p-6 max-w-md w-full"
                  onClick={(e) => e.stopPropagation()}
                >
                  <h3 className="text-lg font-bold mb-4" style={{ color: "var(--text-primary)" }}>Панель тренировки</h3>
                  <div className="space-y-3 text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                    <div className="space-y-2">
                      <div className="flex gap-2">
                        <Target size={16} className="shrink-0 mt-0.5" style={{ color: "var(--accent)" }} />
                        <div><strong style={{ color: "var(--text-primary)" }}>Рекомендуемые</strong> — AI подобрал сценарии под ваш уровень и слабые места</div>
                      </div>
                      <div className="flex gap-2">
                        <BookOpen size={16} className="shrink-0 mt-0.5" style={{ color: "var(--accent)" }} />
                        <div><strong style={{ color: "var(--text-primary)" }}>Сценарии</strong> — 60 готовых сценариев в 8 группах (от холодных звонков до кризисных)</div>
                      </div>
                      <div className="flex gap-2">
                        <ClipboardList size={16} className="shrink-0 mt-0.5" style={{ color: "var(--accent)" }} />
                        <div><strong style={{ color: "var(--text-primary)" }}>Назначенные</strong> — задания от руководителя с дедлайнами</div>
                      </div>
                      <div className="flex gap-2">
                        <Puzzle size={16} className="shrink-0 mt-0.5" style={{ color: "var(--accent)" }} />
                        <div><strong style={{ color: "var(--text-primary)" }}>Конструктор</strong> — соберите клиента из 100 архетипов, 25 профессий и 20 источников</div>
                      </div>
                      <div className="flex gap-2">
                        <Users size={16} className="shrink-0 mt-0.5" style={{ color: "var(--accent)" }} />
                        <div><strong style={{ color: "var(--text-primary)" }}>Мои клиенты</strong> — сохранённые конфигурации для повторного использования</div>
                      </div>
                    </div>

                    <div className="pt-2" style={{ borderTop: "1px solid var(--border-color)" }}>
                      <p className="font-bold mb-1.5" style={{ color: "var(--text-primary)" }}>Как начать:</p>
                      <ol className="list-decimal list-inside space-y-1">
                        <li>Выберите сценарий или создайте клиента в конструкторе</li>
                        <li>Нажмите &laquo;Начать&raquo; или &laquo;История Nx&raquo;</li>
                        <li>Общайтесь с AI-клиентом голосом или текстом</li>
                        <li>После завершения получите разбор и рекомендации</li>
                      </ol>
                    </div>

                    <Link
                      href="/training/archetypes"
                      className="block text-center mt-2 py-2 rounded-lg text-sm font-medium"
                      style={{ background: "var(--accent-muted)", color: "var(--accent)", border: "1px solid rgba(99,102,241,0.25)" }}
                      onClick={() => setShowInfoModal(false)}
                    >
                      Каталог архетипов — 100 типов клиентов
                    </Link>
                  </div>
                  <button
                    className="mt-3 w-full py-2 rounded-lg text-sm font-medium"
                    style={{ background: "var(--input-bg)", color: "var(--text-primary)", border: "1px solid var(--border-color)" }}
                    onClick={() => setShowInfoModal(false)}
                  >
                    Понятно
                  </button>
                </motion.div>
              </motion.div>
            )}
          </AnimatePresence>

          <div className="mt-5 flex flex-col sm:flex-row flex-wrap items-start sm:items-center justify-between gap-3 rounded-2xl px-4 py-3" style={{ background: "rgba(255,255,255,0.03)", border: "1px solid var(--border-color)" }}>
            <div>
              <div className="font-mono text-sm tracking-[0.22em]" style={{ color: "var(--accent)" }}>
                Story Preset
              </div>
              <div className="mt-1 text-sm" style={{ color: "var(--text-secondary)" }}>
                Выбран режим AI-story на <span style={{ color: "var(--text-primary)", fontWeight: 700 }}>{storyCalls}</span> звонка(ов) для всех запусков из панели.
              </div>
            </div>
            <div className="flex gap-2">
              {[3, 4, 5].map((calls) => (
                <button
                  key={calls}
                  onClick={() => setStoryCalls(calls)}
                  className="rounded-xl px-4 py-2 font-mono text-xs uppercase tracking-[0.14em] transition-all"
                  style={{
                    background: storyCalls === calls ? "rgba(99,102,241,0.14)" : "var(--input-bg)",
                    border: `1px solid ${storyCalls === calls ? "rgba(99,102,241,0.42)" : "var(--border-color)"}`,
                    color: storyCalls === calls ? "var(--accent)" : "var(--text-muted)",
                  }}
                >
                  x{calls}
                </button>
              ))}
            </div>
          </div>

          {/* Tabs */}
          <div className="mt-6 flex gap-1 rounded-xl p-1 overflow-x-auto" style={{ background: "var(--input-bg)" }}>
            {TABS.map((t) => {
              const Icon = t.icon;
              const active = tab === t.id;
              return (
                <button
                  key={t.id}
                  onClick={() => setTab(t.id)}
                  className="relative flex-1 flex items-center justify-center gap-1.5 sm:gap-2 rounded-lg px-2 sm:px-4 py-2.5 font-mono text-xs sm:text-sm tracking-wider transition-colors whitespace-nowrap min-w-0"
                  style={{ color: active ? "var(--text-primary)" : "var(--text-muted)" }}
                >
                  {active && (
                    <motion.div
                      layoutId="activeTab"
                      className="absolute inset-0 rounded-lg"
                      style={{ background: "var(--glass-bg)", border: "1px solid var(--glass-border)" }}
                      transition={{ type: "spring", stiffness: 400, damping: 30 }}
                    />
                  )}
                  <span className="relative z-10 flex items-center gap-2">
                    <Icon size={14} style={{ color: active ? "var(--accent)" : "var(--text-muted)" }} />
                    {t.label}
                    {/* Badge for assigned tab */}
                    {t.id === "assigned" && assignedCount > 0 && (
                      <span
                        className="min-w-[18px] h-[18px] flex items-center justify-center rounded-full text-xs font-bold text-white px-1"
                        style={{ background: overdueCount > 0 ? "var(--neon-red, #FF3333)" : "var(--accent)" }}
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
          <AnimatePresence mode="wait">
            {tab === "recommended" && (
              <motion.div key="recommended" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.2 }}>
                <RecommendedTab
                  onStart={startTraining}
                  onStartStory={startStoryTraining}
                  starting={starting}
                  storyCalls={storyCalls}
                />
              </motion.div>
            )}

            {tab === "scenarios" && (
              <motion.div key="scenarios" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.2 }}>
                <ScenariosTab
                  starting={starting}
                  storyCalls={storyCalls}
                  onStoryCallsChange={setStoryCalls}
                  onStart={startTraining}
                  onStartStory={startStoryTraining}
                />
              </motion.div>
            )}

            {tab === "assigned" && (
              <motion.div key="assigned" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.2 }}>
                <AssignedTab onStart={startTraining} onStartStory={startStoryTraining} starting={starting} storyCalls={storyCalls} />
              </motion.div>
            )}

            {tab === "builder" && (
              <motion.div key="builder" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.2 }}>
                <CharacterBuilder storyCalls={storyCalls} />
              </motion.div>
            )}

            {tab === "saved" && (
              <motion.div key="saved" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.2 }}>
                <SavedTab storyCalls={storyCalls} />
              </motion.div>
            )}
          </AnimatePresence>
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

/* ─── Recommended Tab ────────────────────────────────────────────────────── */

function RecommendedTab({
  onStart,
  onStartStory,
  starting,
  storyCalls,
}: {
  onStart: (id: string) => void;
  onStartStory: (id: string, calls?: number) => void;
  starting: string | null;
  storyCalls: number;
}) {
  const scenarios = useTrainingStore((s) => s.scenarios);
  const scenariosLoading = useTrainingStore((s) => s.scenariosLoading);

  // Build recommendations: pick archetypes from different groups/tiers
  // In production this would come from backend /training/recommended
  const recommendations = (() => {
    // Simple client-side recommendation engine
    // Groups recommendations into: main, skill-gap, challenge, new-group
    const groups: { title: string; subtitle: string; color: string; archetypes: ArchetypeInfo[] }[] = [];

    // 1. Main recommendation — moderate difficulty, varied groups
    const t1t2 = ARCHETYPES.filter((a) => a.tier <= 2 && a.difficulty <= 6);
    const mainPick = t1t2.slice(0, 3);
    if (mainPick.length) {
      groups.push({
        title: "Рекомендуемые сегодня",
        subtitle: "На основе сложности и разнообразия",
        color: "var(--accent)",
        archetypes: mainPick,
      });
    }

    // 2. New groups — COGNITIVE, SOCIAL, TEMPORAL, PROFESSIONAL, COMPOUND
    const newGroups: Array<{ key: string; archetypes: ArchetypeInfo[] }> = [
      { key: "cognitive", archetypes: ARCHETYPES.filter((a) => a.group === "cognitive" && a.tier <= 2) },
      { key: "social", archetypes: ARCHETYPES.filter((a) => a.group === "social" && a.tier <= 2) },
      { key: "temporal", archetypes: ARCHETYPES.filter((a) => a.group === "temporal" && a.tier <= 2) },
      { key: "professional", archetypes: ARCHETYPES.filter((a) => a.group === "professional" && a.tier <= 2) },
    ];
    for (const ng of newGroups) {
      const g = ARCHETYPE_GROUPS[ng.key as keyof typeof ARCHETYPE_GROUPS];
      if (g && ng.archetypes.length > 0) {
        groups.push({
          title: `${g.icon} ${g.label}`,
          subtitle: g.description,
          color: g.color,
          archetypes: ng.archetypes.slice(0, 3),
        });
      }
    }

    // 3. Challenge — high tier
    const challenges = ARCHETYPES.filter((a) => a.tier >= 3 && a.difficulty >= 7).slice(0, 3);
    if (challenges.length) {
      groups.push({
        title: "Вызов",
        subtitle: "Для опытных менеджеров",
        color: "#EF4444",
        archetypes: challenges,
      });
    }

    return groups;
  })();

  if (scenariosLoading) {
    return (
      <div className="grid grid-cols-1 gap-4 mt-6">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="glass-panel rounded-2xl h-32 animate-pulse" />
        ))}
      </div>
    );
  }

  return (
    <div className="mt-6 space-y-8">
      {recommendations.map((group, gi) => (
        <div key={gi}>
          <div className="flex items-center gap-3 mb-4">
            <div className="flex items-center gap-2">
              {gi === 0 && <Sparkles size={18} style={{ color: group.color }} />}
              {gi === recommendations.length - 1 && <TrendingUp size={18} style={{ color: group.color }} />}
              <h3 className="font-display text-base font-bold tracking-wide" style={{ color: "var(--text-primary)" }}>
                {group.title}
              </h3>
            </div>
            <span className="text-xs" style={{ color: "var(--text-muted)" }}>
              {group.subtitle}
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {group.archetypes.map((arch) => {
              const groupInfo = ARCHETYPE_GROUPS[arch.group];
              const tierColor = getTierColor(arch.tier);
              const diffColor = getDifficultyColor(arch.difficulty);
              // Find a matching scenario by difficulty
              const matchScenario = scenarios.length
                ? [...scenarios].sort((a, b) => Math.abs(a.difficulty - arch.difficulty) - Math.abs(b.difficulty - arch.difficulty))[0]
                : null;

              return (
                <motion.div
                  key={arch.code}
                  className="glass-panel p-5 rounded-2xl relative overflow-hidden"
                  whileHover={{ y: -4, boxShadow: `0 8px 24px ${diffColor}15` }}
                >
                  {/* Top gradient accent */}
                  <div
                    className="absolute top-0 left-0 right-0 h-1"
                    style={{ background: `linear-gradient(90deg, ${diffColor}, ${tierColor})` }}
                  />

                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <span className="text-xl">{arch.icon}</span>
                      <div>
                        <div className="font-display text-sm font-bold" style={{ color: diffColor }}>
                          {arch.name}
                        </div>
                        <div className="text-sm italic" style={{ color: "var(--text-muted)" }}>
                          &laquo;{arch.subtitle}&raquo;
                        </div>
                      </div>
                    </div>
                    <div className="flex gap-1.5">
                      <span className="rounded px-1.5 py-0.5 text-xs font-mono font-bold" style={{ background: tierColor + "20", color: tierColor }}>
                        T{arch.tier}
                      </span>
                      <span className="rounded px-1.5 py-0.5 text-xs font-mono" style={{ background: "var(--input-bg)", color: "var(--text-muted)" }}>
                        Сл. {arch.difficulty}
                      </span>
                    </div>
                  </div>

                  <p className="text-xs leading-relaxed mb-3" style={{ color: "var(--text-secondary)" }}>
                    {arch.description}
                  </p>

                  {/* Skill counters */}
                  <div className="flex flex-wrap gap-1 mb-3">
                    {arch.counters.map((skill) => (
                      <span
                        key={skill}
                        className="rounded-full px-2 py-0.5 text-xs font-mono"
                        style={{ background: "var(--input-bg)", color: "var(--text-muted)", border: "1px solid var(--border-color)" }}
                      >
                        {skill.replace(/_/g, " ")}
                      </span>
                    ))}
                  </div>

                  {/* Weakness hint */}
                  <div className="rounded-lg p-2 mb-3" style={{ background: "rgba(255,215,0,0.05)", border: "1px solid rgba(255,215,0,0.1)" }}>
                    <div className="text-sm font-mono mb-0.5" style={{ color: "rgba(255,215,0,0.6)" }}>
                      Слабое место
                    </div>
                    <p className="text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                      {arch.weakness}
                    </p>
                  </div>

                  {/* Actions */}
                  <div className="flex gap-2">
                    {matchScenario ? (
                      <>
                        <motion.button
                          onClick={() => onStart(matchScenario.id)}
                          disabled={starting === matchScenario.id}
                          className="flex-1 btn-neon flex items-center justify-center gap-1.5 py-2 text-xs"
                          whileTap={{ scale: 0.97 }}
                          style={{ background: `linear-gradient(135deg, ${diffColor}20, ${tierColor}10)` }}
                        >
                          {starting === matchScenario.id ? (
                            <Loader2 size={12} className="animate-spin" />
                          ) : (
                            <>
                              <Sparkles size={12} /> Начать
                            </>
                          )}
                        </motion.button>
                        <motion.button
                          onClick={() => onStartStory(matchScenario.id, storyCalls)}
                          disabled={!!starting}
                          className="btn-neon flex items-center gap-1.5 px-3 py-2 text-xs"
                          whileTap={{ scale: 0.97 }}
                          style={{ borderColor: diffColor + "30", color: diffColor }}
                        >
                          AI x{storyCalls}
                        </motion.button>
                      </>
                    ) : (
                      <div className="flex items-center gap-1.5 text-xs" style={{ color: "var(--text-muted)" }}>
                        <Lock size={12} /> Загрузите сценарии
                      </div>
                    )}
                  </div>
                </motion.div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

/* ─── Scenarios Tab with Filters ──────────────────────────────────────────── */

function ScenariosTab({
  starting,
  storyCalls,
  onStoryCallsChange,
  onStart,
  onStartStory,
}: {
  starting: string | null;
  storyCalls: number;
  onStoryCallsChange: (calls: number) => void;
  onStart: (id: string) => void;
  onStartStory: (id: string, calls?: number) => void;
}) {
  const { scenariosLoading, typeFilter, difficultyFilter, setTypeFilter, setDifficultyFilter, filteredScenarios } = useTrainingStore();
  const filtered = filteredScenarios();

  if (scenariosLoading) {
    return (
      <div className="mt-6 grid gap-5 sm:grid-cols-2">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="glass-panel p-6 space-y-4 animate-pulse relative overflow-hidden rounded-2xl">
            <div className="absolute top-0 left-0 right-0 h-1.5 bg-[var(--input-bg)]" />
            <div className="flex items-start gap-3">
              <div className="w-14 h-14 rounded-2xl bg-[var(--input-bg)]" />
              <div className="flex-1 space-y-2">
                <div className="h-5 w-2/3 rounded bg-[var(--input-bg)]" />
                <div className="h-3 w-full rounded bg-[var(--input-bg)]" />
              </div>
              <div className="h-6 w-12 rounded-lg bg-[var(--input-bg)]" />
            </div>
            <div className="h-4 w-3/4 rounded bg-[var(--input-bg)]" />
            <div className="flex gap-1">
              {[...Array(10)].map((_, j) => <div key={j} className="h-2 flex-1 rounded-full bg-[var(--input-bg)]" />)}
            </div>
            <div className="flex gap-2">
              <div className="h-6 w-20 rounded-lg bg-[var(--input-bg)]" />
              <div className="h-6 w-20 rounded-lg bg-[var(--input-bg)]" />
              <div className="h-6 w-16 rounded-lg bg-[var(--input-bg)]" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="h-12 rounded-xl bg-[var(--input-bg)]" />
              <div className="h-12 rounded-xl bg-[var(--input-bg)]" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <>
      <div
        className="mt-6 overflow-hidden rounded-2xl"
        style={{
          background: "linear-gradient(135deg, rgba(5,5,6,0.95), rgba(18,18,22,0.94))",
          border: "1px solid rgba(99,102,241,0.18)",
          boxShadow: "0 18px 45px rgba(0,0,0,0.28)",
        }}
      >
        <div className="grid gap-6 px-5 py-5 md:grid-cols-[1.1fr_0.9fr] md:px-6">
          <div>
            <div className="font-mono text-sm tracking-[0.28em]" style={{ color: "var(--accent)" }}>
              AI Story Mode
            </div>
            <h2 className="mt-3 font-display text-2xl font-bold tracking-[0.08em]" style={{ color: "var(--text-primary)" }}>
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
            ].map((item) => (
              <button
                key={item.calls}
                onClick={() => onStoryCallsChange(item.calls)}
                className="rounded-xl px-4 py-3 text-left transition-all"
                style={{
                  background: storyCalls === item.calls ? "rgba(99,102,241,0.14)" : "rgba(255,255,255,0.03)",
                  border: storyCalls === item.calls ? "1px solid rgba(99,102,241,0.42)" : "1px solid rgba(255,255,255,0.08)",
                  boxShadow: storyCalls === item.calls ? "0 0 0 1px rgba(99,102,241,0.12) inset" : "none",
                }}
              >
                <div className="font-mono text-xs uppercase tracking-widest" style={{ color: storyCalls === item.calls ? "var(--accent)" : "var(--text-primary)" }}>
                  {item.label}
                </div>
                <div className="mt-1 text-xs leading-relaxed" style={{ color: "var(--text-muted)" }}>
                  {item.text}
                </div>
              </button>
            ))}
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

      {/* ── Scenario Grid ────────────────────────────── */}
      {filtered.length === 0 ? (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mt-16 flex flex-col items-center">
          <Inbox size={40} style={{ color: "var(--text-muted)" }} />
          <p className="mt-3 text-sm" style={{ color: "var(--text-muted)" }}>
            {typeFilter !== "all" || difficultyFilter !== "all"
              ? "Нет сценариев с такими фильтрами"
              : "Сценарии пока не добавлены"}
          </p>
        </motion.div>
      ) : (
        <div className="mt-6 grid gap-5 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
          {filtered.map((scenario, i) => (
            <ScenarioDossierCard
              key={scenario.id}
              scenario={scenario}
              index={i}
              isStarting={starting === scenario.id}
              onStart={onStart}
              onStartStory={onStartStory}
              storyCalls={storyCalls}
            />
          ))}
        </div>
      )}
    </>
  );
}

/* ─── Assigned Trainings Tab ──────────────────────────────────────────────── */

function AssignedTab({
  onStart,
  onStartStory,
  starting,
  storyCalls,
}: {
  onStart: (id: string) => void;
  onStartStory: (id: string, calls?: number) => void;
  starting: string | null;
  storyCalls: number;
}) {
  const { assigned, assignedLoading } = useTrainingStore();

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

  if (assigned.length === 0) {
    return (
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mt-16 flex flex-col items-center">
        <ClipboardList size={40} style={{ color: "var(--text-muted)" }} />
        <p className="mt-3 text-sm" style={{ color: "var(--text-muted)" }}>
          Нет назначенных тренировок
        </p>
        <p className="mt-1 font-mono text-xs" style={{ color: "var(--text-muted)" }}>
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
        const isStarting = starting === item.scenario_id;

        return (
          <motion.div
            key={item.id}
            initial={{ opacity: 0, x: -12 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.08 }}
            className="glass-panel p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4"
            style={{
              borderLeft: `3px solid ${isOverdue ? "var(--neon-red, #FF3333)" : "var(--accent)"}`,
            }}
          >
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <h3 className="font-display font-semibold truncate" style={{ color: "var(--text-primary)" }}>
                  {item.scenario_title}
                </h3>
                {isOverdue && (
                  <AlertTriangle size={16} style={{ color: "var(--neon-red, #FF3333)", flexShrink: 0 }} />
                )}
              </div>
              <div className="mt-1.5 flex items-center gap-3 font-mono text-xs" style={{ color: "var(--text-muted)" }}>
                <span className="flex items-center gap-1">
                  <Clock size={11} />
                  {isOverdue ? (
                    <span style={{ color: "var(--neon-red, #FF3333)" }}>
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
                style={{ borderColor: "rgba(99,102,241,0.24)", color: "var(--accent)" }}
                whileTap={{ scale: 0.97 }}
              >
                AI x{storyCalls}
              </motion.button>
            </div>
          </motion.div>
        );
      })}
    </div>
  );
}

/* ─── Saved Characters Tab ─────────────────────────────────────────────────── */

function SavedTab({ storyCalls }: { storyCalls: number }) {
  const { savedCharacters, savedLoading, fetchSavedCharacters } = useTrainingStore();
  const router = useRouter();
  const [starting, setStarting] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  useEffect(() => {
    fetchSavedCharacters();
  }, [fetchSavedCharacters]);

  const buildStoryUrl = (scenarioId: string, char: { archetype: string; profession: string; lead_source: string; difficulty: number }) => {
    const params = new URLSearchParams({
      mode: "story",
      calls: String(storyCalls),
      custom_archetype: char.archetype,
      custom_profession: char.profession,
      custom_lead_source: char.lead_source,
      custom_difficulty: String(char.difficulty),
    });
    return `/training/${scenarioId}?${params.toString()}`;
  };

  const handleStart = async (
    char: { id?: string; archetype: string; profession: string; lead_source: string; difficulty: number },
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
      const session = await api.post("/training/sessions", {
        ...(scenarioId ? { scenario_id: scenarioId } : {}),
        custom_archetype: char.archetype,
        custom_profession: char.profession,
        custom_lead_source: char.lead_source,
        custom_difficulty: char.difficulty,
      });
      router.push(`/training/${session.id}`);
    } catch {
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
        <p className="mt-1 font-mono text-xs" style={{ color: "var(--text-muted)" }}>
          Создайте первого в Конструкторе
        </p>
      </div>
    );
  }

  return (
    <div className="mt-8 grid gap-4 sm:grid-cols-2">
      {savedCharacters.map((char, i) => {
        return (
          <motion.div
            key={char.id}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: i * 0.05 }}
            className="glass-panel p-5 relative overflow-hidden"
          >
            <div className="absolute top-0 left-0 right-0 h-[2px]" style={{ background: "linear-gradient(90deg, transparent, var(--accent), transparent)" }} />
            <h3 className="font-display font-semibold" style={{ color: "var(--text-primary)" }}>
              {char.name}
            </h3>
            <div className="mt-2 flex items-center gap-2 flex-wrap">
              <span className="rounded-full px-2 py-0.5 text-xs font-mono" style={{ background: "var(--accent-muted)", color: "var(--accent)", border: "1px solid var(--accent)" }}>
                {char.archetype}
              </span>
              <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
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
                style={{ borderColor: "rgba(99,102,241,0.24)", color: "var(--accent)" }}
                whileTap={{ scale: 0.97 }}
              >
                AI x{storyCalls}
              </motion.button>
              <motion.button
                onClick={() => {
                  if (window.confirm(`Удалить персонажа "${char.name}"?`)) {
                    handleDelete(char.id);
                  }
                }}
                disabled={deleting === char.id}
                className="btn-neon px-3 text-xs"
                style={{ color: "var(--neon-red, #FF3333)", borderColor: "rgba(255,51,51,0.3)" }}
                whileTap={{ scale: 0.97 }}
              >
                {deleting === char.id ? <Loader2 size={12} className="animate-spin" /> : "×"}
              </motion.button>
            </div>
          </motion.div>
        );
      })}
    </div>
  );
}
