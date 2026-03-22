"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { logger } from "@/lib/logger";
import {
  Brain,
  Briefcase,
  Wallet,
  Zap,
  ArrowRight,
  ArrowLeft,
  Loader2,
  Sparkles,
  RotateCcw,
  Check,
  Save,
  CheckCircle2,
} from "lucide-react";
import { api } from "@/lib/api";
import type { ArchetypeCode, LeadSource, ProfessionCategory } from "@/types";

// ─── Data maps ───────────────────────────────────────────────────────────────

interface ArchetypeInfo {
  code: ArchetypeCode;
  name: string;
  description: string;
  group: string;
  difficulty: number; // base difficulty 1-10
  color: string;
}

interface CharacterBuilderProps {
  storyCalls?: number;
}

const ARCHETYPE_GROUPS: Record<string, { label: string; color: string }> = {
  resistance: { label: "Сопротивление", color: "#FF3333" },
  emotional: { label: "Эмоциональные", color: "#E028CC" },
  control: { label: "Контроль", color: "#FFD700" },
  avoidance: { label: "Избегание", color: "#3B82F6" },
  special: { label: "Особые", color: "#00FF94" },
};

const ARCHETYPES: ArchetypeInfo[] = [
  // Resistance
  { code: "skeptic", name: "Скептик", description: "Сомневается в легальности, требует доказательств", group: "resistance", difficulty: 5, color: "#FF3333" },
  { code: "aggressive", name: "Агрессор", description: "Враждебный, обвиняет всех вокруг", group: "resistance", difficulty: 7, color: "#FF3333" },
  { code: "hostile", name: "Враждебный", description: "Открыто конфликтует, провоцирует", group: "resistance", difficulty: 8, color: "#FF3333" },
  { code: "blamer", name: "Обвинитель", description: "Перекладывает вину на всех", group: "resistance", difficulty: 6, color: "#FF3333" },
  { code: "sarcastic", name: "Саркастичный", description: "Язвительный, обесценивает усилия", group: "resistance", difficulty: 6, color: "#FF3333" },
  // Emotional
  { code: "anxious", name: "Тревожный", description: "Боится юридических последствий", group: "emotional", difficulty: 4, color: "#E028CC" },
  { code: "crying", name: "Плачущий", description: "Эмоционально подавлен, плачет", group: "emotional", difficulty: 5, color: "#E028CC" },
  { code: "desperate", name: "Отчаявшийся", description: "На грани, потерял надежду", group: "emotional", difficulty: 6, color: "#E028CC" },
  { code: "ashamed", name: "Стыдящийся", description: "Стесняется своей ситуации", group: "emotional", difficulty: 4, color: "#E028CC" },
  { code: "overwhelmed", name: "Перегруженный", description: "Запутался, не может принять решение", group: "emotional", difficulty: 5, color: "#E028CC" },
  { code: "grateful", name: "Благодарный", description: "Готов сотрудничать, ценит помощь", group: "emotional", difficulty: 2, color: "#E028CC" },
  // Control
  { code: "manipulator", name: "Манипулятор", description: "Контролирует разговор, тестирует границы", group: "control", difficulty: 8, color: "#FFD700" },
  { code: "know_it_all", name: "Всезнайка", description: "Считает себя экспертом, поучает", group: "control", difficulty: 7, color: "#FFD700" },
  { code: "negotiator", name: "Торговец", description: "Выбивает скидки и условия", group: "control", difficulty: 6, color: "#FFD700" },
  { code: "shopper", name: "Шоппер", description: "Сравнивает предложения, не торопится", group: "control", difficulty: 5, color: "#FFD700" },
  { code: "pragmatic", name: "Прагматик", description: "Фокус на цифрах и ROI", group: "control", difficulty: 5, color: "#FFD700" },
  { code: "lawyer_client", name: "Юрист-клиент", description: "Знает законы, проверяет каждое слово", group: "control", difficulty: 9, color: "#FFD700" },
  // Avoidance
  { code: "passive", name: "Пассивный", description: "Безнадёжный, хочет чтобы спасли", group: "avoidance", difficulty: 3, color: "#3B82F6" },
  { code: "delegator", name: "Делегатор", description: "Избегает решений, хочет простоты", group: "avoidance", difficulty: 4, color: "#3B82F6" },
  { code: "avoidant", name: "Уклонист", description: "Избегает разговора, уходит от темы", group: "avoidance", difficulty: 5, color: "#3B82F6" },
  { code: "paranoid", name: "Параноик", description: "Не доверяет никому, ищет подвох", group: "avoidance", difficulty: 7, color: "#3B82F6" },
  // Special
  { code: "couple", name: "Пара", description: "Два человека с разными мнениями", group: "special", difficulty: 8, color: "#00FF94" },
  { code: "returner", name: "Возвращенец", description: "Уже отказывался, звонит снова", group: "special", difficulty: 6, color: "#00FF94" },
  { code: "referred", name: "По рекомендации", description: "Пришёл по совету знакомого", group: "special", difficulty: 3, color: "#00FF94" },
  { code: "rushed", name: "Спешащий", description: "Нет времени, хочет быстро", group: "special", difficulty: 5, color: "#00FF94" },
];

interface ProfessionInfo {
  code: ProfessionCategory;
  name: string;
  icon: string;
  debtRange: string;
}

const PROFESSIONS: ProfessionInfo[] = [
  { code: "budget", name: "Бюджетник", icon: "🏛️", debtRange: "100K–1M" },
  { code: "government", name: "Госслужащий", icon: "🏢", debtRange: "200K–2M" },
  { code: "military", name: "Военный", icon: "🎖️", debtRange: "150K–1.5M" },
  { code: "pensioner", name: "Пенсионер", icon: "👴", debtRange: "50K–500K" },
  { code: "entrepreneur", name: "Предприниматель", icon: "💼", debtRange: "500K–5M" },
  { code: "worker", name: "Рабочий", icon: "🔧", debtRange: "100K–800K" },
  { code: "it_office", name: "IT / Офис", icon: "💻", debtRange: "300K–3M" },
  { code: "trade_service", name: "Торговля/Сервис", icon: "🛒", debtRange: "100K–1M" },
  { code: "homemaker", name: "Домохозяйка", icon: "🏠", debtRange: "50K–500K" },
  { code: "special", name: "Другое", icon: "✨", debtRange: "100K–2M" },
];

const LEAD_SOURCES: { code: LeadSource; name: string }[] = [
  { code: "cold_base", name: "Холодная база" },
  { code: "website_form", name: "Заявка с сайта" },
  { code: "referral", name: "Рекомендация" },
  { code: "social_media", name: "Соцсети" },
  { code: "repeat_call", name: "Повторный звонок" },
  { code: "incoming", name: "Входящий" },
  { code: "partner", name: "Партнёр" },
  { code: "chatbot", name: "Чат-бот" },
  { code: "webinar", name: "Вебинар" },
  { code: "churned", name: "Отвалившийся" },
];

// ─── Steps ───────────────────────────────────────────────────────────────────

type Step = 0 | 1 | 2 | 3;

const STEPS: { icon: React.ComponentType<{ size: number; style?: React.CSSProperties }>; label: string }[] = [
  { icon: Brain, label: "Архетип" },
  { icon: Briefcase, label: "Профессия" },
  { icon: Wallet, label: "Контекст" },
  { icon: Zap, label: "Сложность" },
];

// ─── Component ───────────────────────────────────────────────────────────────

export default function CharacterBuilder({ storyCalls = 3 }: CharacterBuilderProps) {
  const router = useRouter();
  const [step, setStep] = useState<Step>(0);
  const [archetype, setArchetype] = useState<ArchetypeCode | null>(null);
  const [profession, setProfession] = useState<ProfessionCategory | null>(null);
  const [leadSource, setLeadSource] = useState<LeadSource>("cold_base");
  const [difficulty, setDifficulty] = useState(5);
  const [starting, setStarting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [groupFilter, setGroupFilter] = useState<string | null>(null);

  const selectedArchetype = ARCHETYPES.find((a) => a.code === archetype);
  const selectedProfession = PROFESSIONS.find((p) => p.code === profession);

  const canNext = (): boolean => {
    if (step === 0) return archetype !== null;
    if (step === 1) return profession !== null;
    return true;
  };

  const buildStoryQuery = (scenarioId: string) => {
    const params = new URLSearchParams({
      mode: "story",
      calls: String(storyCalls),
      custom_archetype: archetype || "",
      custom_profession: profession || "",
      custom_lead_source: leadSource,
      custom_difficulty: String(difficulty),
    });
    return `/training/${scenarioId}?${params.toString()}`;
  };

  const handleStart = async (storyMode = false) => {
    if (!archetype || !profession) return;
    setStarting(true);
    try {
      // Try to find a matching scenario for script/checkpoints context
      let scenarioId: string | undefined;
      try {
        const scenarios = await api.get("/scenarios/");
        if (scenarios.length) {
          const sorted = [...scenarios].sort(
            (a: { difficulty: number }, b: { difficulty: number }) =>
              Math.abs(a.difficulty - difficulty) - Math.abs(b.difficulty - difficulty),
          );
          scenarioId = sorted[0].id;
        }
      } catch {
        // Scenarios endpoint might fail — proceed without
      }

      // Send custom character params to backend (scenario_id is now optional)
      if (storyMode && scenarioId) {
        router.push(buildStoryQuery(scenarioId));
        return;
      }

      const session = await api.post("/training/sessions", {
        ...(scenarioId ? { scenario_id: scenarioId } : {}),
        custom_archetype: archetype,
        custom_profession: profession,
        custom_lead_source: leadSource,
        custom_difficulty: difficulty,
      });
      router.push(`/training/${session.id}`);
    } catch (err) {
      logger.error("Failed to start:", err);
      alert("Не удалось создать сессию. Проверьте, что бэкенд запущен и сценарии загружены (seed_db).");
      setStarting(false);
    }
  };

  const handleSave = async () => {
    if (!archetype || !profession) return;
    setSaving(true);
    try {
      const selectedArch = ARCHETYPES.find((a) => a.code === archetype);
      const selectedProf = PROFESSIONS.find((p) => p.code === profession);
      await api.post("/characters/custom", {
        name: `${selectedArch?.name || archetype} · ${selectedProf?.name || profession}`,
        archetype,
        profession,
        lead_source: leadSource,
        difficulty,
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      logger.error("Failed to save character:", err);
    } finally {
      setSaving(false);
    }
  };

  const reset = () => {
    setStep(0);
    setArchetype(null);
    setProfession(null);
    setLeadSource("cold_base");
    setDifficulty(5);
    setGroupFilter(null);
  };

  const filteredArchetypes = groupFilter
    ? ARCHETYPES.filter((a) => a.group === groupFilter)
    : ARCHETYPES;

  return (
    <div className="mt-8">
      {/* Stepper */}
      <div className="flex items-center justify-between mb-8">
        {STEPS.map((s, i) => {
          const Icon = s.icon;
          const done = i < step;
          const active = i === step;
          return (
            <div key={i} className="flex items-center flex-1">
              <button
                onClick={() => i <= step && setStep(i as Step)}
                className="flex items-center gap-2"
                disabled={i > step}
              >
                <div
                  className="w-8 h-8 rounded-full flex items-center justify-center transition-all"
                  style={{
                    background: done ? "var(--accent)" : active ? "var(--accent-muted)" : "var(--input-bg)",
                    border: active ? "2px solid var(--accent)" : "2px solid transparent",
                  }}
                >
                  {done ? (
                    <Check size={14} className="text-white" />
                  ) : (
                    <Icon size={14} style={{ color: active ? "var(--accent)" : "var(--text-muted)" }} />
                  )}
                </div>
                <span
                  className="font-mono text-[10px] uppercase tracking-wider hidden sm:inline"
                  style={{ color: active ? "var(--text-primary)" : "var(--text-muted)" }}
                >
                  {s.label}
                </span>
              </button>
              {i < STEPS.length - 1 && (
                <div
                  className="flex-1 h-px mx-3"
                  style={{ background: done ? "var(--accent)" : "var(--border-color)" }}
                />
              )}
            </div>
          );
        })}
      </div>

      {/* Step content */}
      <AnimatePresence mode="wait">
        {/* Step 0: Archetype */}
        {step === 0 && (
          <motion.div key="s0" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }} transition={{ duration: 0.2 }}>
            {/* Group filters */}
            <div className="flex flex-wrap gap-2 mb-5">
              <button
                onClick={() => setGroupFilter(null)}
                className="rounded-full px-3 py-1 font-mono text-[10px] uppercase tracking-wider transition-colors"
                style={{
                  background: !groupFilter ? "var(--accent)" : "var(--input-bg)",
                  color: !groupFilter ? "white" : "var(--text-muted)",
                }}
              >
                Все ({ARCHETYPES.length})
              </button>
              {Object.entries(ARCHETYPE_GROUPS).map(([key, g]) => {
                const count = ARCHETYPES.filter((a) => a.group === key).length;
                return (
                  <button
                    key={key}
                    onClick={() => setGroupFilter(groupFilter === key ? null : key)}
                    className="rounded-full px-3 py-1 font-mono text-[10px] uppercase tracking-wider transition-colors"
                    style={{
                      background: groupFilter === key ? g.color + "20" : "var(--input-bg)",
                      color: groupFilter === key ? g.color : "var(--text-muted)",
                      border: groupFilter === key ? `1px solid ${g.color}40` : "1px solid transparent",
                    }}
                  >
                    {g.label} ({count})
                  </button>
                );
              })}
            </div>

            {/* Archetype grid */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
              {filteredArchetypes.map((a) => {
                const selected = archetype === a.code;
                return (
                  <motion.button
                    key={a.code}
                    onClick={() => setArchetype(a.code)}
                    className="glass-panel p-4 text-left transition-all relative overflow-hidden"
                    style={{
                      borderColor: selected ? a.color + "60" : undefined,
                      boxShadow: selected ? `0 0 20px ${a.color}15` : undefined,
                    }}
                    whileHover={{ y: -2 }}
                    whileTap={{ scale: 0.98 }}
                  >
                    {selected && (
                      <div className="absolute top-2 right-2">
                        <Check size={14} style={{ color: a.color }} />
                      </div>
                    )}
                    <div
                      className="font-display text-sm font-semibold"
                      style={{ color: selected ? a.color : "var(--text-primary)" }}
                    >
                      {a.name}
                    </div>
                    <p className="mt-1 text-[11px] leading-snug" style={{ color: "var(--text-muted)" }}>
                      {a.description}
                    </p>
                    <div className="mt-2 flex items-center gap-2">
                      <span
                        className="rounded-full px-1.5 py-0.5 font-mono text-[9px]"
                        style={{
                          background: a.color + "15",
                          color: a.color,
                        }}
                      >
                        {ARCHETYPE_GROUPS[a.group]?.label}
                      </span>
                      <span className="font-mono text-[9px]" style={{ color: "var(--text-muted)" }}>
                        ⚡{a.difficulty}
                      </span>
                    </div>
                  </motion.button>
                );
              })}
            </div>
          </motion.div>
        )}

        {/* Step 1: Profession */}
        {step === 1 && (
          <motion.div key="s1" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }} transition={{ duration: 0.2 }}>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
              {PROFESSIONS.map((p) => {
                const selected = profession === p.code;
                return (
                  <motion.button
                    key={p.code}
                    onClick={() => setProfession(p.code)}
                    className="glass-panel p-4 text-center transition-all"
                    style={{
                      borderColor: selected ? "var(--accent)" + "60" : undefined,
                      boxShadow: selected ? "0 0 20px rgba(139,92,246,0.15)" : undefined,
                    }}
                    whileHover={{ y: -2 }}
                    whileTap={{ scale: 0.98 }}
                  >
                    <div className="text-2xl mb-2">{p.icon}</div>
                    <div
                      className="font-display text-xs font-semibold"
                      style={{ color: selected ? "var(--accent)" : "var(--text-primary)" }}
                    >
                      {p.name}
                    </div>
                    <div className="mt-1 font-mono text-[9px]" style={{ color: "var(--text-muted)" }}>
                      {p.debtRange} ₽
                    </div>
                    {selected && (
                      <motion.div
                        initial={{ scale: 0 }}
                        animate={{ scale: 1 }}
                        className="mt-2 mx-auto w-4 h-4 rounded-full flex items-center justify-center"
                        style={{ background: "var(--accent)" }}
                      >
                        <Check size={10} className="text-white" />
                      </motion.div>
                    )}
                  </motion.button>
                );
              })}
            </div>
          </motion.div>
        )}

        {/* Step 2: Context (lead source) */}
        {step === 2 && (
          <motion.div key="s2" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }} transition={{ duration: 0.2 }}>
            <h3 className="font-display text-sm tracking-wider mb-4" style={{ color: "var(--text-primary)" }}>
              Источник лида
            </h3>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
              {LEAD_SOURCES.map((ls) => {
                const selected = leadSource === ls.code;
                return (
                  <button
                    key={ls.code}
                    onClick={() => setLeadSource(ls.code)}
                    className="rounded-xl px-3 py-2.5 font-mono text-xs text-left transition-all"
                    style={{
                      background: selected ? "var(--accent-muted)" : "var(--input-bg)",
                      border: `1px solid ${selected ? "var(--accent)" : "var(--border-color)"}`,
                      color: selected ? "var(--accent)" : "var(--text-secondary)",
                    }}
                  >
                    {ls.name}
                  </button>
                );
              })}
            </div>
          </motion.div>
        )}

        {/* Step 3: Difficulty + Summary */}
        {step === 3 && (
          <motion.div key="s3" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }} transition={{ duration: 0.2 }}>
            {/* Difficulty slider */}
            <div className="glass-panel p-6 mb-6">
              <h3 className="font-display text-sm tracking-wider mb-4" style={{ color: "var(--text-primary)" }}>
                Уровень сложности
              </h3>
              <div className="flex items-center gap-4">
                <input
                  type="range"
                  min={1}
                  max={10}
                  value={difficulty}
                  onChange={(e) => setDifficulty(Number(e.target.value))}
                  className="flex-1 accent-purple-500"
                  style={{ accentColor: "var(--accent)" }}
                />
                <span
                  className="font-display text-3xl font-bold w-12 text-center"
                  style={{
                    color:
                      difficulty <= 3 ? "#00FF66" : difficulty <= 6 ? "var(--warning)" : "#FF3333",
                  }}
                >
                  {difficulty}
                </span>
              </div>
              <div className="flex justify-between mt-1 font-mono text-[9px]" style={{ color: "var(--text-muted)" }}>
                <span>Легко</span>
                <span>Средне</span>
                <span>Хардкор</span>
              </div>
            </div>

            {/* Summary card */}
            <div className="glass-panel p-6">
              <div className="flex items-center gap-2 mb-4">
                <Sparkles size={16} style={{ color: "var(--accent)" }} />
                <h3 className="font-display text-sm tracking-wider" style={{ color: "var(--text-primary)" }}>
                  Ваш персонаж
                </h3>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                <div>
                  <div className="font-mono text-[9px] uppercase tracking-widest mb-1" style={{ color: "var(--text-muted)" }}>
                    Архетип
                  </div>
                  <div className="text-sm font-medium" style={{ color: selectedArchetype?.color ?? "var(--text-primary)" }}>
                    {selectedArchetype?.name ?? "—"}
                  </div>
                </div>
                <div>
                  <div className="font-mono text-[9px] uppercase tracking-widest mb-1" style={{ color: "var(--text-muted)" }}>
                    Профессия
                  </div>
                  <div className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                    {selectedProfession ? `${selectedProfession.icon} ${selectedProfession.name}` : "—"}
                  </div>
                </div>
                <div>
                  <div className="font-mono text-[9px] uppercase tracking-widest mb-1" style={{ color: "var(--text-muted)" }}>
                    Источник
                  </div>
                  <div className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                    {LEAD_SOURCES.find((l) => l.code === leadSource)?.name ?? "—"}
                  </div>
                </div>
                <div>
                  <div className="font-mono text-[9px] uppercase tracking-widest mb-1" style={{ color: "var(--text-muted)" }}>
                    Сложность
                  </div>
                  <div
                    className="text-sm font-bold font-mono"
                    style={{
                      color:
                        difficulty <= 3 ? "#00FF66" : difficulty <= 6 ? "var(--warning)" : "#FF3333",
                    }}
                  >
                    {difficulty}/10
                  </div>
                </div>
              </div>

              <p className="mt-4 text-xs leading-relaxed" style={{ color: "var(--text-muted)" }}>
                Психология, страхи, точка слома и ловушки будут сгенерированы автоматически на основе архетипа и сложности.
              </p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Navigation */}
      <div className="mt-8 flex items-center justify-between">
        <div className="flex gap-2">
          {step > 0 && (
            <motion.button
              onClick={() => setStep((step - 1) as Step)}
              className="vh-btn-outline flex items-center gap-2"
              whileTap={{ scale: 0.97 }}
            >
              <ArrowLeft size={14} /> Назад
            </motion.button>
          )}
          {(archetype || profession) && (
            <motion.button
              onClick={reset}
              className="vh-btn-outline flex items-center gap-2"
              style={{ color: "var(--text-muted)" }}
              whileTap={{ scale: 0.97 }}
            >
              <RotateCcw size={14} /> Сбросить
            </motion.button>
          )}
        </div>

        {step < 3 ? (
          <motion.button
            onClick={() => setStep((step + 1) as Step)}
            disabled={!canNext()}
            className="vh-btn-primary flex items-center gap-2"
            style={{ opacity: canNext() ? 1 : 0.4 }}
            whileTap={canNext() ? { scale: 0.97 } : {}}
          >
            Далее <ArrowRight size={14} />
          </motion.button>
        ) : (
          <>
            <motion.button
              onClick={handleSave}
              disabled={saving || saved || !archetype || !profession}
              className="vh-btn-outline flex items-center gap-2"
              whileTap={{ scale: 0.97 }}
            >
              {saved ? (
                <><CheckCircle2 size={14} style={{ color: "var(--neon-green, #00FF66)" }} /> Сохранён</>
              ) : saving ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <><Save size={14} /> Сохранить</>
              )}
            </motion.button>
            <motion.button
              onClick={() => handleStart(false)}
              disabled={starting || !archetype || !profession}
              className="vh-btn-primary flex items-center gap-2"
              whileTap={{ scale: 0.97 }}
            >
              {starting ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <>
                  <Sparkles size={14} /> Начать тренировку
                </>
              )}
            </motion.button>
            <motion.button
              onClick={() => handleStart(true)}
              disabled={starting || !archetype || !profession}
              className="vh-btn-outline flex items-center gap-2"
              style={{ borderColor: "rgba(139,92,246,0.28)", color: "var(--accent)" }}
              whileTap={{ scale: 0.97 }}
            >
              {starting ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <>
                  <Sparkles size={14} /> AI-story x{storyCalls}
                </>
              )}
            </motion.button>
          </>
        )}
      </div>
    </div>
  );
}
