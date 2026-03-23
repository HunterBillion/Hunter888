"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { logger } from "@/lib/logger";
import {
  Crosshair,
  Clock,
  Zap,
  Loader2,
  ArrowRight,
  Inbox,
  Users,
  Puzzle,
  BookOpen,
  ClipboardList,
  Filter,
  AlertTriangle,
} from "lucide-react";
import { api } from "@/lib/api";
import AuthLayout from "@/components/layout/AuthLayout";
import CharacterBuilder from "@/components/training/CharacterBuilder";
import { useTrainingStore } from "@/stores/useTrainingStore";
import type { Scenario } from "@/types";

type Tab = "scenarios" | "assigned" | "builder" | "saved";

const TABS: { id: Tab; label: string; icon: React.ComponentType<{ size: number; style?: React.CSSProperties }> }[] = [
  { id: "scenarios", label: "Сценарии", icon: BookOpen },
  { id: "assigned", label: "Назначенные", icon: ClipboardList },
  { id: "builder", label: "Конструктор", icon: Puzzle },
  { id: "saved", label: "Мои персонажи", icon: Users },
];

const TYPE_FILTERS = [
  { key: "all", label: "Все" },
  { key: "cold", label: "Холодные" },
  { key: "warm", label: "Тёплые" },
  { key: "in", label: "Входящие" },
  { key: "objection", label: "Возражения" },
] as const;

const DIFF_FILTERS = [
  { key: "all", label: "Любая" },
  { key: "easy", label: "1-3" },
  { key: "medium", label: "4-6" },
  { key: "hard", label: "7-10" },
] as const;

function getDifficultyConfig(d: number) {
  if (d <= 3) return { label: "Легко", color: "#00FF66", bg: "rgba(0,255,102,0.08)", border: "rgba(0,255,102,0.2)" };
  if (d <= 6) return { label: "Средне", color: "var(--warning)", bg: "rgba(245,158,11,0.08)", border: "rgba(245,158,11,0.2)" };
  return { label: "Сложно", color: "#FF3333", bg: "rgba(255,51,51,0.08)", border: "rgba(255,51,51,0.2)" };
}

function TrainingPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [tab, setTab] = useState<Tab>("scenarios");
  const [starting, setStarting] = useState<string | null>(null);
  const [startError, setStartError] = useState<string | null>(null);
  const [storyCalls, setStoryCalls] = useState<number>(3);

  const store = useTrainingStore();

  useEffect(() => {
    store.fetchScenarios();
    store.fetchAssigned();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const nextTab = searchParams.get("tab");
    if (nextTab === "assigned" || nextTab === "builder" || nextTab === "saved" || nextTab === "scenarios") {
      setTab(nextTab);
    }
  }, [searchParams]);

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

  const overdueCount = store.assigned.filter((a) => new Date(a.deadline) < new Date()).length;
  const assignedCount = store.assigned.length;

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
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
            <div className="flex items-center gap-2">
              <Crosshair size={20} style={{ color: "var(--accent)" }} />
              <h1 className="font-display text-2xl font-bold tracking-[0.15em]" style={{ color: "var(--text-primary)" }}>
                ТРЕНИРОВКА
              </h1>
            </div>
            <p className="mt-2 font-mono text-xs tracking-wider" style={{ color: "var(--text-muted)" }}>
              ВЫБЕРИТЕ ФОРМАТ ТРЕНИРОВКИ
            </p>
          </motion.div>

          <div className="mt-5 flex flex-wrap items-center justify-between gap-3 rounded-2xl px-4 py-3" style={{ background: "rgba(255,255,255,0.03)", border: "1px solid var(--border-color)" }}>
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.22em]" style={{ color: "var(--accent)" }}>
                STORY PRESET
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
                    background: storyCalls === calls ? "rgba(139,92,246,0.14)" : "var(--input-bg)",
                    border: `1px solid ${storyCalls === calls ? "rgba(139,92,246,0.42)" : "var(--border-color)"}`,
                    color: storyCalls === calls ? "var(--accent)" : "var(--text-muted)",
                  }}
                >
                  x{calls}
                </button>
              ))}
            </div>
          </div>

          {/* Tabs */}
          <div className="mt-6 flex gap-1 rounded-xl p-1" style={{ background: "var(--input-bg)" }}>
            {TABS.map((t) => {
              const Icon = t.icon;
              const active = tab === t.id;
              return (
                <button
                  key={t.id}
                  onClick={() => setTab(t.id)}
                  className="relative flex-1 flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 font-mono text-xs tracking-wider transition-colors"
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
                        className="min-w-[18px] h-[18px] flex items-center justify-center rounded-full text-[9px] font-bold text-white px-1"
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
      <div className="mt-8 grid gap-5 sm:grid-cols-2">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="glass-panel p-6 space-y-4 animate-pulse relative overflow-hidden">
            <div className="absolute top-0 left-0 right-0 h-[2px] bg-[var(--input-bg)]" />
            <div className="h-5 w-3/4 rounded bg-[var(--input-bg)]" />
            <div className="space-y-1.5">
              <div className="h-3 w-full rounded bg-[var(--input-bg)]" />
              <div className="h-3 w-2/3 rounded bg-[var(--input-bg)]" />
            </div>
            <div className="flex gap-3">
              <div className="h-5 w-24 rounded-full bg-[var(--input-bg)]" />
              <div className="h-5 w-16 rounded bg-[var(--input-bg)]" />
            </div>
            <div className="h-10 w-full rounded-xl bg-[var(--input-bg)]" />
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
          border: "1px solid rgba(139,92,246,0.18)",
          boxShadow: "0 18px 45px rgba(0,0,0,0.28)",
        }}
      >
        <div className="grid gap-5 px-5 py-5 md:grid-cols-[1.15fr_0.85fr] md:px-6">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.28em]" style={{ color: "var(--accent)" }}>
              AI STORY MODE
            </div>
            <h2 className="mt-3 font-display text-2xl font-bold tracking-[0.08em]" style={{ color: "var(--text-primary)" }}>
              ИСТОРИЯ КЛИЕНТА НА НЕСКОЛЬКО ЗВОНКОВ
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
                  background: storyCalls === item.calls ? "rgba(139,92,246,0.14)" : "rgba(255,255,255,0.03)",
                  border: storyCalls === item.calls ? "1px solid rgba(139,92,246,0.42)" : "1px solid rgba(255,255,255,0.08)",
                  boxShadow: storyCalls === item.calls ? "0 0 0 1px rgba(139,92,246,0.12) inset" : "none",
                }}
              >
                <div className="font-mono text-[11px] uppercase tracking-widest" style={{ color: storyCalls === item.calls ? "var(--accent)" : "var(--text-primary)" }}>
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
      <div className="mt-6 flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-2">
          <Filter size={13} style={{ color: "var(--text-muted)" }} />
          <span className="font-mono text-[10px] tracking-widest uppercase" style={{ color: "var(--text-muted)" }}>Тип:</span>
          <div className="flex gap-1">
            {TYPE_FILTERS.map((f) => (
              <button
                key={f.key}
                onClick={() => setTypeFilter(f.key as typeof typeFilter)}
                className="rounded-lg px-2.5 py-1 font-mono text-[11px] transition-all"
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

        <div className="flex items-center gap-2">
          <span className="font-mono text-[10px] tracking-widest uppercase" style={{ color: "var(--text-muted)" }}>Сложность:</span>
          <div className="flex gap-1">
            {DIFF_FILTERS.map((f) => (
              <button
                key={f.key}
                onClick={() => setDifficultyFilter(f.key as typeof difficultyFilter)}
                className="rounded-lg px-2.5 py-1 font-mono text-[11px] transition-all"
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
        <div className="mt-6 grid gap-5 sm:grid-cols-2">
          {filtered.map((scenario, i) => {
            const diff = getDifficultyConfig(scenario.difficulty);
            const isStarting = starting === scenario.id;
            return (
              <motion.div
                key={scenario.id}
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.05 }}
                className="glass-panel p-6 transition-all relative overflow-hidden"
                whileHover={{
                  y: -3,
                  boxShadow: "0 8px 30px rgba(139, 92, 246, 0.15)",
                  borderColor: "rgba(139, 92, 246, 0.3)",
                }}
              >
                <div className="absolute top-0 left-0 right-0 h-[2px]" style={{ background: `linear-gradient(90deg, transparent, ${diff.color}, transparent)` }} />
                <h3 className="font-display text-lg font-semibold" style={{ color: "var(--text-primary)" }}>
                  {scenario.title}
                </h3>
                {scenario.character_name && (
                  <div className="mt-1.5 flex items-center gap-1.5 font-mono text-[10px] tracking-wider" style={{ color: "var(--text-muted)" }}>
                    <Users size={10} />
                    <span>{scenario.character_name}</span>
                  </div>
                )}
                <p className="mt-2 text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                  {scenario.description}
                </p>
                <div className="mt-4 flex items-center gap-3">
                  <span
                    className="rounded-full px-2.5 py-0.5 text-xs font-medium font-mono"
                    style={{ background: diff.bg, color: diff.color, border: `1px solid ${diff.border}` }}
                  >
                    <Zap size={10} className="mr-1 inline" />
                    {diff.label} ({scenario.difficulty}/10)
                  </span>
                  <span className="flex items-center gap-1 text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                    <Clock size={12} />
                    {scenario.estimated_duration_minutes} мин
                  </span>
                </div>
                <motion.button
                  onClick={() => onStart(scenario.id)}
                  disabled={isStarting}
                  className="vh-btn-primary mt-5 flex w-full items-center justify-center gap-2"
                  whileTap={{ scale: 0.98 }}
                >
                  {isStarting ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : (
                    <>
                      Начать тренировку
                      <ArrowRight size={16} />
                    </>
                  )}
                </motion.button>
                <motion.button
                  onClick={() => onStartStory(scenario.id, storyCalls)}
                  className="mt-2 flex w-full items-center justify-center gap-2 rounded-xl border px-4 py-3 font-mono text-xs tracking-[0.12em] transition-all"
                  style={{
                    borderColor: "rgba(139,92,246,0.24)",
                    background: "rgba(139,92,246,0.08)",
                    color: "var(--text-primary)",
                  }}
                  whileTap={{ scale: 0.98 }}
                >
                  <Puzzle size={14} style={{ color: "var(--accent)" }} />
                  Запустить AI-story x{storyCalls}
                </motion.button>
              </motion.div>
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
            className="glass-panel p-5 flex items-center justify-between gap-4"
            style={{
              borderLeft: `3px solid ${isOverdue ? "var(--neon-red, #FF3333)" : "var(--accent)"}`,
            }}
          >
            <div className="flex-1 min-w-0">
              <h3 className="font-display font-semibold truncate" style={{ color: "var(--text-primary)" }}>
                {item.scenario_title}
              </h3>
              <div className="mt-1.5 flex items-center gap-3 font-mono text-[11px]" style={{ color: "var(--text-muted)" }}>
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

            {isOverdue && (
              <AlertTriangle size={18} style={{ color: "var(--neon-red, #FF3333)", flexShrink: 0 }} />
            )}

            <div className="flex shrink-0 gap-2">
              <motion.button
                onClick={() => onStart(item.scenario_id)}
                disabled={isStarting}
                className="vh-btn-primary flex items-center gap-2"
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
                className="vh-btn-outline flex items-center gap-2"
                style={{ borderColor: "rgba(139,92,246,0.24)", color: "var(--accent)" }}
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
    char: { archetype: string; profession: string; lead_source: string; difficulty: number },
    storyMode = false,
  ) => {
    setStarting(char.archetype);
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
        const diff = getDifficultyConfig(char.difficulty);
        return (
          <motion.div
            key={char.id}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
            className="glass-panel p-5 relative overflow-hidden"
          >
            <div className="absolute top-0 left-0 right-0 h-[2px]" style={{ background: `linear-gradient(90deg, transparent, ${diff.color}, transparent)` }} />
            <h3 className="font-display font-semibold" style={{ color: "var(--text-primary)" }}>
              {char.name}
            </h3>
            <div className="mt-2 flex items-center gap-2 flex-wrap">
              <span className="rounded-full px-2 py-0.5 text-[10px] font-mono" style={{ background: diff.bg, color: diff.color, border: `1px solid ${diff.border}` }}>
                {diff.label} ({char.difficulty}/10)
              </span>
              <span className="text-[10px] font-mono" style={{ color: "var(--text-muted)" }}>
                {char.lead_source}
              </span>
            </div>
            <div className="mt-4 flex gap-2">
              <motion.button
                onClick={() => handleStart(char, false)}
                disabled={starting === char.archetype}
                className="vh-btn-primary flex-1 flex items-center justify-center gap-2 text-xs"
                whileTap={{ scale: 0.97 }}
              >
                {starting === char.archetype ? <Loader2 size={14} className="animate-spin" /> : <><ArrowRight size={14} /> Тренироваться</>}
              </motion.button>
              <motion.button
                onClick={() => handleStart(char, true)}
                disabled={starting === char.archetype}
                className="vh-btn-outline flex items-center justify-center gap-2 px-3 text-xs"
                style={{ borderColor: "rgba(139,92,246,0.24)", color: "var(--accent)" }}
                whileTap={{ scale: 0.97 }}
              >
                AI x{storyCalls}
              </motion.button>
              <motion.button
                onClick={() => handleDelete(char.id)}
                disabled={deleting === char.id}
                className="vh-btn-outline px-3 text-xs"
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
