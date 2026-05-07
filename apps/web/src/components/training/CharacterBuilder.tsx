"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { logger } from "@/lib/logger";
import { AvatarPreview } from "./AvatarPreview";
import { ImportWizard } from "@/components/methodology/ImportWizard";
import { ImportHistory } from "@/components/methodology/ImportHistory";
import { useNotificationStore } from "@/stores/useNotificationStore";
import { useGamificationStore } from "@/stores/useGamificationStore";
// 2026-04-21: dropped Save/CheckCircle2/SkipForward — autosave replaced the
// standalone Save button and "Пропустить" duplicated "Далее" on optional
// steps. The icons disappearing keeps the bundle honest.
import {
  ArrowRight, ChevronLeft, Loader2, Sparkles, RotateCcw, Check,
  Lock, MessageCircle, Phone,
} from "lucide-react";
import {
  Brain, Briefcase, Broadcast, UsersThree, Heart, Gauge, Cloud, FileMagnifyingGlass,
} from "@phosphor-icons/react";
import { Button } from "@/components/ui/Button";
import { AppIcon } from "@/components/ui/AppIcon";
import { GROUP_ICONS } from "@/lib/groupIcons";
import { api, ApiError } from "@/lib/api";
import type {
  ArchetypeCode, ArchetypeGroup, ArchetypeTier, LeadSource, ProfessionCategory,
  FamilyPreset, CreditorsPreset, DebtStage, DebtRange, EmotionPreset,
  BackgroundNoise, TimeOfDay, ClientFatigue,
} from "@/types";
import { ARCHETYPES, ARCHETYPE_GROUPS, getTierColor } from "@/lib/archetypes";
import type { ArchetypeInfo } from "@/lib/archetypes";
import { ArchetypeCard } from "@/components/training/ArchetypeCard";
import { PROFESSIONS, PROFESSION_GROUPS } from "@/lib/professions";
import type { ProfessionInfo } from "@/lib/professions";
import { LEAD_SOURCES, LEAD_SOURCE_GROUPS } from "@/lib/leadSources";

// ─── Types ──────────────────────────────────────────────────────────────────

interface CharacterBuilderProps {
  storyCalls?: number;
  userLevel?: number;
}

type Step = 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7;

const STEPS: {
  icon: React.ComponentType<Record<string, unknown>>;
  label: string;
  unlockLevel: number;
  required: boolean;
}[] = [
  { icon: Brain, label: "Архетип", unlockLevel: 1, required: true },        // 0
  { icon: Briefcase, label: "Профессия", unlockLevel: 1, required: true },   // 1
  { icon: Broadcast, label: "Источник", unlockLevel: 1, required: true },    // 2
  { icon: UsersThree, label: "Контекст", unlockLevel: 3, required: false },  // 3 — FIX-4
  { icon: Heart, label: "Настроение", unlockLevel: 5, required: false },     // 4 — FIX-4
  { icon: Gauge, label: "Сложность", unlockLevel: 1, required: true },       // 5
  { icon: Cloud, label: "Среда", unlockLevel: 8, required: false },           // 6
  { icon: FileMagnifyingGlass, label: "Превью", unlockLevel: 1, required: false },     // 7 — FIX-4: level 9
];

// ─── Emotion presets data ───────────────────────────────────────────────────

const EMOTION_PRESETS: { code: EmotionPreset; name: string; icon: string; desc: string }[] = [
  { code: "neutral", name: "Нейтральный", icon: "\u{1F610}", desc: "Стандартное состояние" },
  { code: "anxious", name: "Тревожный", icon: "\u{1F630}", desc: "Нервничает, насторожен" },
  { code: "angry", name: "Злой", icon: "\u{1F620}", desc: "Раздражён ещё до звонка" },
  { code: "hopeful", name: "Надеющийся", icon: "\u{1F91E}", desc: "Верит что помогут" },
  { code: "tired", name: "Уставший", icon: "\u{1F634}", desc: "Мало энергии, апатичен" },
  { code: "rushed", name: "Спешащий", icon: "\u23F0", desc: "Нет времени, нетерпелив" },
  { code: "trusting", name: "Доверчивый", icon: "\u{1F91D}", desc: "Открыт к разговору" },
];

// ─── Tone / Vibe (2026-04-21) ────────────────────────────────────────────────
// Stylistic layer on top of archetype. Applies a soft OceanShift (±0.05..±0.10)
// to the client's personality AND swaps in a matching tone band inside the
// call-mode system prompt. See app/services/adaptive_difficulty.TONE_OCEAN_SHIFT
// and app/services/llm.build_call_mode_modifier for the server-side mapping.

type ToneCode = "harsh" | "neutral" | "lively" | "friendly";

const TONES: { code: ToneCode; name: string; desc: string }[] = [
  { code: "harsh",    name: "Жёсткий",     desc: "Холодный, лаконичный, без вежливости" },
  { code: "neutral",  name: "Нейтральный", desc: "Стандарт, без стилистического сдвига" },
  { code: "lively",   name: "Живой",       desc: "Эмоциональный, разговорчивый, шутит" },
  { code: "friendly", name: "Дружелюбный", desc: "Тёплый, открытый, готов слушать" },
];

// ─── Context data ───────────────────────────────────────────────────────────

const FAMILY_PRESETS: { code: FamilyPreset; label: string }[] = [
  { code: "random", label: "Случайно" },
  { code: "single", label: "Холост" },
  { code: "married", label: "В браке" },
  { code: "married_kids", label: "В браке + дети" },
  { code: "divorced", label: "Разведён" },
  { code: "widow", label: "Вдовец/вдова" },
];

const CREDITORS_PRESETS: { code: CreditorsPreset; label: string }[] = [
  { code: "random", label: "Случайно" },
  { code: "1", label: "1" },
  { code: "2_3", label: "2-3" },
  { code: "4_5", label: "4-5" },
  { code: "6_plus", label: "6+" },
];

const DEBT_STAGES: { code: DebtStage; label: string }[] = [
  { code: "random", label: "Случайно" },
  { code: "pre_court", label: "До суда" },
  { code: "court_started", label: "Суд начался" },
  { code: "execution", label: "Исп. производство" },
  { code: "arrest", label: "Арест имущества" },
];

const DEBT_RANGES: { code: DebtRange; label: string }[] = [
  { code: "random", label: "Случайно" },
  { code: "under_500k", label: "<500K" },
  { code: "500k_1m", label: "500K\u20131M" },
  { code: "1m_3m", label: "1M\u20133M" },
  { code: "3m_10m", label: "3M\u201310M" },
  { code: "over_10m", label: "10M+" },
];

const NOISES: { code: BackgroundNoise; label: string }[] = [
  { code: "none", label: "Тишина" }, { code: "office", label: "Офис" },
  { code: "street", label: "Улица" }, { code: "children", label: "Дети" }, { code: "tv", label: "ТВ" },
];

const TIMES: { code: TimeOfDay; label: string }[] = [
  { code: "morning", label: "Утро" }, { code: "afternoon", label: "День" },
  { code: "evening", label: "Вечер" }, { code: "night", label: "Ночь" },
];

const FATIGUES: { code: ClientFatigue; label: string }[] = [
  { code: "fresh", label: "Бодрый" }, { code: "normal", label: "Нормальный" },
  { code: "tired", label: "Уставший" }, { code: "exhausted", label: "Измотанный" },
];

// ─── Friendly autoname (PR-G) ───────────────────────────────────────────────
// Placeholder name shown in "Имя в моих клиентах". Pre-PR-G it was
// "Делегатор · Сельское хоз. · 9/10" — a machine-style label that read
// like an internal id. Now: a deterministic Russian first name picked
// from the archetype code, plus profession in lower case, plus an
// archetype-correlated age. Determinism matters: two clones of the
// same configuration must produce the same suggestion so saved
// clients still scan visually.

const _RU_NAMES_M = [
  "Иван", "Сергей", "Андрей", "Дмитрий", "Алексей",
  "Михаил", "Александр", "Николай", "Владимир", "Юрий",
  "Олег", "Виктор", "Павел", "Артём", "Кирилл",
];
const _RU_NAMES_F = [
  "Мария", "Елена", "Анна", "Ольга", "Татьяна",
  "Ирина", "Светлана", "Наталья", "Алина", "Юлия",
  "Екатерина", "Виктория", "Дарья", "Полина", "Кристина",
];

function _seedFromArchetype(code: string): number {
  let h = 2166136261;
  for (let i = 0; i < code.length; i++) h = Math.imul(h ^ code.charCodeAt(i), 16777619);
  return Math.abs(h);
}

function buildFriendlyAutoname(
  archetypeCode: string | null,
  archetypeName: string | null,
  professionName: string | null,
  difficulty: number,
): string {
  if (!archetypeCode || !archetypeName) return "Название персонажа";
  const seed = _seedFromArchetype(archetypeCode);
  // Gender bias purely deterministic — half archetypes resolve male,
  // half female. Manager perceives variety in saved list.
  const isMale = (seed & 1) === 0;
  const pool = isMale ? _RU_NAMES_M : _RU_NAMES_F;
  const first = pool[seed % pool.length];
  // Age bands: difficulty 1..3 → 28..36, 4..6 → 37..48, 7..10 → 45..58.
  const ageOffset = (seed >>> 4) % 9;
  const age = difficulty <= 3 ? 28 + ageOffset
            : difficulty <= 6 ? 37 + ageOffset
            : 45 + ageOffset;
  const profPart = professionName ? `, ${professionName.toLowerCase()}` : "";
  return `${first}${profPart}, ${age} лет (${archetypeName})`;
}

// ─── Component ──────────────────────────────────────────────────────────────

export default function CharacterBuilder({ storyCalls = 3, userLevel: userLevelProp }: CharacterBuilderProps) {
  const router = useRouter();
  // 2026-04-21: userLevel used to be hard-coded to 20 so every unlockLevel
  // check passed vacuously — the step-lock system was dead code. Now we
  // read the real level off useGamificationStore (fed by
  // GET /gamification/me/progress). Explicit prop override is preserved
  // for tests/storybook. Default 1 keeps the advanced steps locked for
  // brand-new users so the flow starts at the 3 core steps only.
  const storeLevel = useGamificationStore((s) => s.level);
  const fetchGamification = useGamificationStore((s) => s.fetchProgress);
  const userLevel = userLevelProp ?? storeLevel ?? 1;
  useEffect(() => {
    // Fire-and-forget: if progress hasn't been fetched this session, do it
    // once so the constructor sees an accurate level. Cached 60s server-side.
    fetchGamification().catch((err) => logger.error("[CharacterBuilder] gamification fetch failed:", err));
  }, [fetchGamification]);
  const [step, setStep] = useState<Step>(0);
  const [importOpen, setImportOpen] = useState(false);
  const [importRefreshKey, setImportRefreshKey] = useState(0);
  // Step 0
  const [archetype, setArchetype] = useState<ArchetypeCode | null>(null);
  const [groupFilter, setGroupFilter] = useState<ArchetypeGroup | null>(null);
  const [tierFilter, setTierFilter] = useState<ArchetypeTier | null>(null);
  // Step 1
  const [profession, setProfession] = useState<ProfessionCategory | null>(null);
  // Step 2
  const [leadSource, setLeadSource] = useState<LeadSource>("cold_base");
  // Step 3
  const [familyPreset, setFamilyPreset] = useState<FamilyPreset>("random");
  const [creditorsPreset, setCreditorsPreset] = useState<CreditorsPreset>("random");
  const [debtStage, setDebtStage] = useState<DebtStage>("random");
  const [debtRange, setDebtRange] = useState<DebtRange>("random");
  // Step 4
  const [emotionPreset, setEmotionPreset] = useState<EmotionPreset>("neutral");
  // 2026-04-21: Tone/Vibe (lives on Step 4 alongside emotion — both are
  // stylistic layers). Default "neutral" = no OceanShift, same behaviour
  // as before the constructor v2 rollout.
  const [tone, setTone] = useState<"harsh" | "neutral" | "lively" | "friendly">("neutral");
  // Step 5
  const [difficulty, setDifficulty] = useState(5);
  // Step 6
  const [bgNoise, setBgNoise] = useState<BackgroundNoise>("none");
  const [timeOfDay, setTimeOfDay] = useState<TimeOfDay>("afternoon");
  const [clientFatigue, setClientFatigue] = useState<ClientFatigue>("normal");
  // UI state
  const [starting, setStarting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  // 2026-04-21: autosave flow. Old UI had a standalone "Сохранить" button
  // right next to "Чат"/"Звонок" on the preview step — the user had to
  // click save MANUALLY before starting, and forgetting meant the carefully
  // configured client was lost forever. Now save is implicit: autoSave is
  // on by default, one click on Чат/Звонок creates the custom_character
  // row first, then starts the session with a proper custom_character_id
  // link. Unchecking gives a one-shot throwaway client.
  const [autoSave, setAutoSave] = useState(true);
  const [customName, setCustomName] = useState("");

  const selectedArchetype = ARCHETYPES.find((a) => a.code === archetype);
  const selectedProfession = PROFESSIONS.find((p) => p.code === profession);

  const isStepLocked = (s: number) => STEPS[s].unlockLevel > userLevel;

  const canNext = (): boolean => {
    if (step === 0) return archetype !== null;
    if (step === 1) return profession !== null;
    return true;
  };

  const nextStep = () => {
    let next = step + 1;
    // Skip locked steps
    while (next < 7 && isStepLocked(next)) next++;
    if (next <= 7) setStep(next as Step);
  };

  const prevStep = () => {
    let prev = step - 1;
    while (prev > 0 && isStepLocked(prev)) prev--;
    if (prev >= 0) setStep(prev as Step);
  };

  const buildStoryQuery = (scenarioId: string) => {
    // 2026-04-21: now passes all 11 builder fields. Previously only 4 were
    // sent → story-mode silently dropped family/creditors/debt/emotion/noise/
    // time/fatigue. The /training/[id] page reads these off the URL and
    // forwards them to the WS session.start handler in custom_params.
    const params = new URLSearchParams({
      mode: "story",
      calls: String(storyCalls),
      custom_archetype: archetype || "",
      custom_profession: profession || "",
      custom_lead_source: leadSource,
      custom_difficulty: String(difficulty),
      custom_family_preset: familyPreset,
      custom_creditors_preset: creditorsPreset,
      custom_debt_stage: debtStage,
      custom_debt_range: debtRange,
      custom_emotion_preset: emotionPreset,
      custom_bg_noise: bgNoise,
      custom_time_of_day: timeOfDay,
      custom_fatigue: clientFatigue,
      custom_tone: tone,
    });
    return `/training/${scenarioId}?${params.toString()}`;
  };

  // sessionMode=call routes to the phone-call UI; chat is the default text-chat.
  // Both use the same backend session — the backend receives session_mode
  // via custom_params so prompts can adapt (shorter sentences, interruptions,
  // etc.) in call mode even though the REST endpoint is the same.
  const handleStart = async (storyMode = false, sessionMode: "chat" | "call" = "chat") => {
    if (!archetype || !profession) return;
    setStarting(true);
    try {
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
      } catch { /* proceed without */ }

      if (storyMode && scenarioId) { router.push(buildStoryQuery(scenarioId)); return; }

      // 2026-04-21: autosave before starting. If the user hasn't unchecked
      // the preview-step toggle, persist the current builder state as a
      // CustomCharacter FIRST, remember its id, then link it to the new
      // TrainingSession via custom_character_id. Failure to save must NOT
      // block the session start — a saved-toast is nice-to-have, a running
      // session is the actual goal. `saved` guards against double-save on
      // repeated Start clicks.
      let savedCharId: string | undefined;
      if (autoSave && !saved) {
        try {
          const a = ARCHETYPES.find((x) => x.code === archetype);
          const p = PROFESSIONS.find((x) => x.code === profession);
          const defaultName = `${a?.name || archetype} \u00B7 ${p?.name || profession} \u00B7 ${difficulty}/10`;
          const savedChar = await api.post("/characters/custom", {
            name: (customName.trim() || defaultName),
            archetype, profession, lead_source: leadSource, difficulty,
            family_preset: familyPreset !== "random" ? familyPreset : null,
            creditors_preset: creditorsPreset !== "random" ? creditorsPreset : null,
            debt_stage: debtStage !== "random" ? debtStage : null,
            debt_range: debtRange !== "random" ? debtRange : null,
            emotion_preset: emotionPreset,
            bg_noise: bgNoise,
            time_of_day: timeOfDay,
            client_fatigue: clientFatigue,
            tone: tone !== "neutral" ? tone : null,
          });
          savedCharId = savedChar?.id;
          setSaved(true);
        } catch (saveErr) {
          logger.warn("Autosave failed — starting session anyway", saveErr);
        }
      }

      // 2026-04-21: stopped dropping "neutral"/"afternoon"/"normal"/"none" as
      // if they were unset. Those are deliberate user choices — the previous
      // `!==` guards silently erased them so the backend never saw the
      // picked value. Now all 11 fields are sent as-is; the backend filters
      // only real emptiness (None / "" / "null"). "random" IS still a
      // sentinel for the 4 context/environment presets (step 3 options
      // literally include a "Случайно" radio), so it's the only one we
      // keep filtering locally.
      const session = await api.post("/training/sessions", {
        ...(scenarioId ? { scenario_id: scenarioId } : {}),
        ...(savedCharId ? { custom_character_id: savedCharId } : {}),
        custom_archetype: archetype,
        custom_profession: profession,
        custom_lead_source: leadSource,
        custom_difficulty: difficulty,
        custom_family_preset: familyPreset !== "random" ? familyPreset : undefined,
        custom_creditors_preset: creditorsPreset !== "random" ? creditorsPreset : undefined,
        custom_debt_stage: debtStage !== "random" ? debtStage : undefined,
        custom_debt_range: debtRange !== "random" ? debtRange : undefined,
        custom_emotion_preset: emotionPreset,
        custom_bg_noise: bgNoise,
        custom_time_of_day: timeOfDay,
        custom_fatigue: clientFatigue,
        custom_tone: tone,
        custom_session_mode: sessionMode,
      });
      const targetPath = sessionMode === "call"
        ? `/training/${session.id}/call`
        : `/training/${session.id}`;
      router.push(targetPath);
    } catch (err) {
      logger.error("Failed to start:", err);
      // 2026-04-21: replaces bare alert() with the shared toast store
      // and mirrors the 409 "session_already_active" rescue that lives
      // in app/training/page.tsx:performStart — otherwise the user
      // hitting Chat/Call while a previous session is still open hit a
      // dead-end alert with no way to resume the active session.
      if (
        err instanceof ApiError &&
        err.status === 409 &&
        err.detail &&
        (err.detail as { code?: string }).code === "session_already_active"
      ) {
        const existingId = (err.detail as { existing_session_id?: string }).existing_session_id;
        if (typeof existingId === "string" && existingId.length > 0) {
          useNotificationStore.getState().addToast({
            title: "Активная тренировка",
            body: "У тебя уже идёт тренировка — открываю её.",
            type: "info",
          });
          const target = sessionMode === "call"
            ? `/training/${existingId}/call`
            : `/training/${existingId}`;
          setTimeout(() => router.push(target), 600);
          return;
        }
      }
      useNotificationStore.getState().addToast({
        title: "Ошибка",
        body: err instanceof Error ? err.message : "Не удалось создать сессию",
        type: "error",
      });
      setStarting(false);
    }
  };

  const handleSave = async () => {
    if (!archetype || !profession) return;
    setSaving(true);
    try {
      const a = ARCHETYPES.find((x) => x.code === archetype);
      const p = PROFESSIONS.find((x) => x.code === profession);
      const defaultName = `${a?.name || archetype} \u00B7 ${p?.name || profession} \u00B7 ${difficulty}/10`;
      await api.post("/characters/custom", {
        name: (customName.trim() || defaultName),
        archetype, profession, lead_source: leadSource, difficulty,
        family_preset: familyPreset !== "random" ? familyPreset : null,
        creditors_preset: creditorsPreset !== "random" ? creditorsPreset : null,
        debt_stage: debtStage !== "random" ? debtStage : null,
        debt_range: debtRange !== "random" ? debtRange : null,
        // 2026-04-21: saving "neutral"/"afternoon"/"normal"/"none" as-is too —
        // they're valid picks, not pseudo-defaults (matches the handleStart fix).
        emotion_preset: emotionPreset,
        bg_noise: bgNoise,
        time_of_day: timeOfDay,
        client_fatigue: clientFatigue,
        tone: tone !== "neutral" ? tone : null,
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      logger.error("Save error:", err);
      useNotificationStore.getState().addToast({ title: "Ошибка", body: "Не удалось сохранить", type: "error" });
    } finally { setSaving(false); }
  };

  const reset = () => {
    // 2026-04-21: confirm before nuking N steps of user input. Previously
    // one mis-click on "Сбросить" at the final step wiped everything —
    // archetype, profession, 8 other picks, name — without a safety net.
    // Only ask when there's actually something to lose.
    if ((archetype || profession || customName) &&
        !window.confirm("Сбросить всё, что собрали? Это нельзя отменить.")) {
      return;
    }
    setStep(0); setArchetype(null); setProfession(null); setLeadSource("cold_base");
    setFamilyPreset("random"); setCreditorsPreset("random"); setDebtStage("random"); setDebtRange("random");
    setEmotionPreset("neutral"); setTone("neutral"); setDifficulty(5);
    setBgNoise("none"); setTimeOfDay("afternoon"); setClientFatigue("normal");
    setGroupFilter(null); setTierFilter(null);
    setCustomName(""); setAutoSave(true); setSaved(false);
  };

  const filteredArchetypes = ARCHETYPES.filter((a) => {
    if (groupFilter && a.group !== groupFilter) return false;
    if (tierFilter && a.tier !== tierFilter) return false;
    return true;
  });

  // ── Radio button row helper ──
  // PR-C: removed the bottom margin — the parent now spaces fields via a
  // grid gap, and the leftover mb-4 was wasting vertical space inside the
  // new mini-cards. Chip styling kept identical so the change is purely
  // structural.
  const RadioRow = ({ label, options, value, onChange }: {
    label: string; options: { code: string; label: string }[]; value: string; onChange: (v: string) => void;
  }) => (
    <div>
      <div className="text-xs font-medium uppercase tracking-wide mb-2" style={{ color: "var(--text-muted)" }}>{label}</div>
      <div className="flex flex-wrap gap-1.5">
        {options.map((o) => (
          <button key={o.code} onClick={() => onChange(o.code)}
            className="rounded-lg px-3 py-1.5 text-xs transition-all"
            style={{
              background: value === o.code ? "var(--accent-muted)" : "var(--input-bg)",
              border: `1px solid ${value === o.code ? "var(--accent)" : "var(--border-color)"}`,
              color: value === o.code ? "var(--accent)" : "var(--text-secondary)",
            }}>
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );

  return (
    <div className="mt-8">
      {/* TZ-5 PR-2 — import button + history */}
      <div className="flex justify-end mb-4">
        <button
          onClick={() => setImportOpen(true)}
          className="px-3 py-1.5 rounded-md text-xs font-medium"
          style={{ background: "var(--accent-muted)", color: "var(--accent)" }}
          title="Загрузить описание клиентского типажа — платформа создаст черновик персонажа."
        >
          📤 Импорт типажа
        </button>
      </div>
      <ImportWizard
        open={importOpen}
        onClose={() => setImportOpen(false)}
        presetRouteType="character"
        onApproved={() => setImportRefreshKey((k) => k + 1)}
      />
      <ImportHistory routeType="character" refreshKey={importRefreshKey} />
      {/* Stepper — 8 steps. PR-G: Lego-style "what you picked" feedback.
          Each completed step shows a tiny one-word summary of the actual
          selection ("Скептик" under "Архетип", "Юрист" under
          "Профессия", "Хол. база" under "Источник", "9/10" under
          "Сложность", etc). Pre-PR-G the breadcrumb only said "this
          step is done" without telling the user WHAT they had picked,
          so the manager couldn't glance back at the wizard and verify
          their build. Only renders at >=lg where labels are visible. */}
      {(() => {
        // Compute a tiny summary per step. Defined inside the render so
        // the closure captures the current builder state without an
        // extra useMemo allocation. Empty strings render as zero-height
        // spans to keep the row alignment stable.
        const _stepSummaries: string[] = [
          /* 0 Архетип */    selectedArchetype?.name ?? "",
          /* 1 Профессия */  selectedProfession?.name ?? "",
          /* 2 Источник */   LEAD_SOURCES.find((l) => l.code === leadSource)?.name ?? "",
          /* 3 Контекст */   [
            familyPreset !== "random" ? FAMILY_PRESETS.find(f => f.code === familyPreset)?.label : "",
            debtRange !== "random" ? DEBT_RANGES.find(d => d.code === debtRange)?.label : "",
          ].filter(Boolean).slice(0, 1).join(" · ") || "Случайно",
          /* 4 Настроение */ EMOTION_PRESETS.find((e) => e.code === emotionPreset)?.name ?? "Нейтр.",
          /* 5 Сложность */  `${difficulty}/10`,
          /* 6 Среда */      [
            bgNoise !== "none" ? NOISES.find(n => n.code === bgNoise)?.label : "",
            timeOfDay !== "afternoon" ? TIMES.find(t => t.code === timeOfDay)?.label : "",
          ].filter(Boolean).slice(0, 1).join(" · ") || "Тишина · день",
          /* 7 Превью */     "",
        ];
        return (
          <div className="flex items-start justify-between mb-8 overflow-x-auto pb-2">
            {STEPS.map((s, i) => {
              const Icon = s.icon;
              const done = i < step;
              const active = i === step;
              const locked = isStepLocked(i);
              const summary = _stepSummaries[i];
              return (
                <div key={i} className="flex items-start flex-1 min-w-0 pt-0.5">
                  <button
                    onClick={() => !locked && i <= step && setStep(i as Step)}
                    className="flex items-start gap-1.5 flex-shrink-0"
                    disabled={locked || i > step}
                  >
                    <div className="w-7 h-7 rounded-full flex items-center justify-center transition-all flex-shrink-0"
                      style={{
                        background: locked ? "var(--input-bg)" : done ? "var(--accent)" : active ? "var(--accent-muted)" : "var(--input-bg)",
                        border: active ? "2px solid var(--accent)" : "2px solid transparent",
                        opacity: locked ? 0.4 : 1,
                      }}>
                      {locked ? <Lock size={10} style={{ color: "var(--text-muted)" }} />
                        : done ? <Check size={12} className="text-white" />
                        : <Icon size={12} style={{ color: active ? "var(--accent)" : "var(--text-muted)" }} />}
                    </div>
                    <div className="hidden lg:flex flex-col items-start min-w-0">
                      <span className="text-xs font-medium uppercase tracking-wide leading-none"
                        style={{ color: locked ? "var(--text-muted)" : active ? "var(--text-primary)" : "var(--text-muted)", opacity: locked ? 0.4 : 1 }}>
                        {s.label}
                      </span>
                      {/* PR-G Lego summary: what's actually picked at
                          this step. Truncates so the breadcrumb stays
                          single-row even with long profession names. */}
                      {(done || (active && summary)) && summary && (
                        <span
                          className="mt-0.5 text-[10px] leading-tight truncate max-w-[110px]"
                          style={{ color: done ? "var(--accent)" : "var(--text-muted)" }}
                          title={summary}
                        >
                          {summary}
                        </span>
                      )}
                    </div>
                  </button>
                  {i < STEPS.length - 1 && (
                    <div className="flex-1 h-px mx-2 min-w-2 mt-3" style={{ background: done ? "var(--accent)" : "var(--border-color)" }} />
                  )}
                </div>
              );
            })}
          </div>
        );
      })()}

      {/* Step content */}
      <AnimatePresence mode="wait">
        <motion.div key={`s${step}`} initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }} transition={{ duration: 0.2 }}>

          {/* ═══ Step 0: Archetype ═══ */}
          {step === 0 && (<>
            <div className="flex flex-wrap gap-1.5 mb-3">
              <button onClick={() => setGroupFilter(null)}
                className="rounded-full px-2.5 py-1 text-sm font-medium uppercase tracking-wide"
                style={{ background: !groupFilter ? "var(--accent)" : "var(--input-bg)", color: !groupFilter ? "white" : "var(--text-muted)" }}>
                Все ({ARCHETYPES.length})
              </button>
              {(Object.entries(ARCHETYPE_GROUPS) as [ArchetypeGroup, typeof ARCHETYPE_GROUPS[ArchetypeGroup]][]).map(([key, g]) => {
                const count = ARCHETYPES.filter((a) => a.group === key).length;
                return (
                  <button key={key} onClick={() => setGroupFilter(groupFilter === key ? null : key)}
                    className="rounded-full px-2 py-1 text-sm font-medium uppercase tracking-wide"
                    style={{ background: groupFilter === key ? g.color + "20" : "var(--input-bg)", color: groupFilter === key ? g.color : "var(--text-muted)", border: groupFilter === key ? `1px solid ${g.color}40` : "1px solid transparent" }}>
                    {(() => { const I = GROUP_ICONS[g.icon]; return I ? <I size={14} weight="duotone" /> : null; })()} {g.label} ({count})
                  </button>
                );
              })}
            </div>
            {/* PR-C: T1-T4 are tier filters, but the bare "T1/T2/T3/T4"
                labels gave the user no idea what they meant. Same chip
                shape, readable copy. Tooltip explains the unlock-level
                gate so power users still know they map to archetype
                tiers under the hood. */}
            <div className="flex flex-wrap gap-1.5 mb-4">
              {([1, 2, 3, 4] as ArchetypeTier[]).map((t) => {
                const tc = getTierColor(t);
                const labels = ["Лёгкие", "Средние", "Сложные", "Эксперт"];
                const titles = [
                  "Тир 1 — базовая сложность, доступны с 1 уровня",
                  "Тир 2 — средняя сложность",
                  "Тир 3 — высокая сложность",
                  "Тир 4 — эксперт, разблокируется на высоких уровнях",
                ];
                return (
                  <button key={t} onClick={() => setTierFilter(tierFilter === t ? null : t)}
                    title={titles[t - 1]}
                    className="rounded-full px-3 py-1 text-xs font-semibold"
                    style={{ background: tierFilter === t ? tc + "20" : "var(--input-bg)", color: tierFilter === t ? tc : "var(--text-muted)", border: tierFilter === t ? `1px solid ${tc}40` : "1px solid transparent" }}>
                    {labels[t - 1]}
                  </button>
                );
              })}
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 max-h-[55vh] overflow-y-auto pr-1">
              {filteredArchetypes.map((a) => (
                <ArchetypeCard
                  key={a.code}
                  arch={a}
                  size="compact"
                  selected={archetype === a.code}
                  onSelect={() => setArchetype(a.code)}
                />
              ))}
            </div>
          </>)}

          {/* ═══ Step 1: Profession (25) ═══ */}
          {step === 1 && (<>
            <h3 className="font-display text-sm font-bold mb-1" style={{ color: "var(--text-primary)" }}>Профессия клиента</h3>
            <p className="text-xs mb-4" style={{ color: "var(--text-muted)" }}>Определяет доход, стиль общения и манеру поведения</p>
            <div className="space-y-5 max-h-[55vh] overflow-y-auto pr-1">
              {Object.entries(PROFESSION_GROUPS).map(([key, group]) => (
                <div key={key}>
                  <div className="text-sm font-semibold uppercase tracking-wide mb-2" style={{ color: "var(--text-muted)" }}>{group.label}</div>
                  <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
                    {PROFESSIONS.filter((p) => p.group === key).map((p) => {
                      const sel = profession === p.code;
                      return (
                        <motion.button key={p.code} onClick={() => setProfession(p.code)}
                          className="glass-panel p-3 text-left rounded-xl relative"
                          style={{ borderColor: sel ? "var(--accent)60" : undefined, boxShadow: sel ? "0 0 16px var(--accent-muted)" : undefined }}
                          whileHover={{ y: -2 }} whileTap={{ scale: 0.97 }}>
                          {sel && <div className="absolute top-1.5 right-1.5 w-4 h-4 rounded-full flex items-center justify-center" style={{ background: "var(--accent)" }}><Check size={8} className="text-white" /></div>}
                          <div className="text-xl mb-1"><AppIcon emoji={p.icon} size={22} /></div>
                          <div className="text-xs font-bold" style={{ color: sel ? "var(--accent)" : "var(--text-primary)" }}>{p.name}</div>
                          <div className="text-sm font-mono mt-0.5" style={{ color: "var(--text-muted)" }}>{p.debtRange} ₽</div>
                        </motion.button>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          </>)}

          {/* ═══ Step 2: Lead Source (20) ═══ */}
          {/* PR-G: align step 2 cards with the glass-panel + Check
              indicator + motion idiom used by steps 0/1/4 so the
              wizard reads as one continuous design language. The
              group sections (Холодные / Тёплые / Входящие) keep
              their headers — they're structural, not decoration. */}
          {step === 2 && (<>
            <h3 className="font-display text-sm font-bold mb-1" style={{ color: "var(--text-primary)" }}>Источник лида</h3>
            <p className="text-xs mb-4" style={{ color: "var(--text-muted)" }}>Определяет уровень доверия, осведомлённость и ожидания клиента</p>
            <div className="space-y-5 max-h-[55vh] overflow-y-auto pr-1">
              {Object.entries(LEAD_SOURCE_GROUPS).map(([key, group]) => (
                <div key={key}>
                  <div className="text-sm font-semibold uppercase tracking-wide mb-2" style={{ color: "var(--text-muted)" }}>{group.label}</div>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                    {LEAD_SOURCES.filter((s) => s.group === key).map((s) => {
                      const sel = leadSource === s.code;
                      return (
                        <motion.button key={s.code} onClick={() => setLeadSource(s.code)}
                          className="glass-panel p-3 text-left rounded-xl relative"
                          style={{ borderColor: sel ? "var(--accent)60" : undefined, boxShadow: sel ? "0 0 16px var(--accent-muted)" : undefined }}
                          whileHover={{ y: -2 }} whileTap={{ scale: 0.97 }}>
                          {sel && <div className="absolute top-1.5 right-1.5 w-4 h-4 rounded-full flex items-center justify-center" style={{ background: "var(--accent)" }}><Check size={8} className="text-white" /></div>}
                          <div className="text-xs font-bold" style={{ color: sel ? "var(--accent)" : "var(--text-primary)" }}>{s.name}</div>
                          <div className="text-sm mt-0.5" style={{ color: "var(--text-muted)" }}>
                            {s.trust >= 2 ? "Высокое доверие" : s.trust >= 1 ? "Открытый контакт" : s.trust === 0 ? "Нейтральный" : s.trust >= -1 ? "Настороженный" : "Холодный контакт"}
                          </div>
                        </motion.button>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          </>)}

          {/* ═══ Step 3: Client Context (NEW) ═══
               PR-C: split single big glass-panel into one mini-card per
               field so the visual rhythm matches the card-grid steps
               (1/2/4) instead of looking like a flat form. */}
          {step === 3 && (<>
            <h3 className="font-display text-sm font-bold mb-1" style={{ color: "var(--text-primary)" }}>Контекст клиента</h3>
            <p className="text-xs mb-4" style={{ color: "var(--text-muted)" }}>Жизненная ситуация влияет на страхи, мотивы и бэкстори</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="glass-panel p-4 rounded-xl">
                <RadioRow label="Семейное положение" options={FAMILY_PRESETS} value={familyPreset} onChange={(v) => setFamilyPreset(v as FamilyPreset)} />
              </div>
              <div className="glass-panel p-4 rounded-xl">
                <RadioRow label="Количество кредиторов" options={CREDITORS_PRESETS} value={creditorsPreset} onChange={(v) => setCreditorsPreset(v as CreditorsPreset)} />
              </div>
              <div className="glass-panel p-4 rounded-xl">
                <RadioRow label="Стадия долга" options={DEBT_STAGES} value={debtStage} onChange={(v) => setDebtStage(v as DebtStage)} />
              </div>
              <div className="glass-panel p-4 rounded-xl">
                <RadioRow label="Общий долг" options={DEBT_RANGES} value={debtRange} onChange={(v) => setDebtRange(v as DebtRange)} />
              </div>
            </div>
          </>)}

          {/* ═══ Step 4: Emotion Preset + Tone (NEW) ═══ */}
          {step === 4 && (<>
            <h3 className="font-display text-sm font-bold mb-1" style={{ color: "var(--text-primary)" }}>Эмоциональный пресет</h3>
            <p className="text-xs mb-4" style={{ color: "var(--text-muted)" }}>Начальное настроение клиента при звонке</p>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {EMOTION_PRESETS.map((ep) => {
                const sel = emotionPreset === ep.code;
                return (
                  <motion.button key={ep.code} onClick={() => setEmotionPreset(ep.code)}
                    className="glass-panel p-4 text-center rounded-xl relative"
                    style={{ borderColor: sel ? "var(--accent)60" : undefined, boxShadow: sel ? "0 0 16px var(--accent-muted)" : undefined }}
                    whileHover={{ y: -2 }} whileTap={{ scale: 0.97 }}>
                    {sel && <div className="absolute top-1.5 right-1.5 w-4 h-4 rounded-full flex items-center justify-center" style={{ background: "var(--accent)" }}><Check size={8} className="text-white" /></div>}
                    <div className="text-2xl mb-2"><AppIcon emoji={ep.icon} size={28} /></div>
                    <div className="text-xs font-bold" style={{ color: sel ? "var(--accent)" : "var(--text-primary)" }}>{ep.name}</div>
                    <div className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>{ep.desc}</div>
                  </motion.button>
                );
              })}
            </div>

            {/* ── Tone / Vibe (2026-04-21) ──
                 Shown on the same step as emotion — both shape the client's
                 *stylistic* register without touching archetype identity or
                 difficulty. Emotion = current mood at pickup; Tone = default
                 manner of speech. OceanShift is deliberately tiny (±0.05..
                 ±0.10) so a "skeptic + friendly" is still clearly skeptical. */}
            <h3 className="font-display text-sm font-bold mt-6 mb-1" style={{ color: "var(--text-primary)" }}>Тон клиента</h3>
            <p className="text-xs mb-4" style={{ color: "var(--text-muted)" }}>
              Манера речи и общий вайб. Сдвигает стиль, не характер и не сложность.
            </p>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {TONES.map((t) => {
                const sel = tone === t.code;
                return (
                  <motion.button key={t.code} onClick={() => setTone(t.code)}
                    className="glass-panel p-4 text-center rounded-xl relative"
                    style={{ borderColor: sel ? "var(--accent)60" : undefined, boxShadow: sel ? "0 0 16px var(--accent-muted)" : undefined }}
                    whileHover={{ y: -2 }} whileTap={{ scale: 0.97 }}>
                    {sel && <div className="absolute top-1.5 right-1.5 w-4 h-4 rounded-full flex items-center justify-center" style={{ background: "var(--accent)" }}><Check size={8} className="text-white" /></div>}
                    <div className="text-xs font-bold" style={{ color: sel ? "var(--accent)" : "var(--text-primary)" }}>{t.name}</div>
                    <div className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>{t.desc}</div>
                  </motion.button>
                );
              })}
            </div>
          </>)}

          {/* ═══ Step 5: Difficulty — PR-G full redesign ═══
               Pre-PR-G: a single sparse 10-cell number row in a giant
               glass-panel. Pilot users called this "пустая трата экрана".
               Now: 4 difficulty band cards (Лёгкий 1-3, Средний 4-6,
               Сложный 7-8, Эксперт 9-10) each carrying its own colour,
               description, and an inline fine-tune slider that picks
               the exact 1-10 value within the band. The band itself
               highlights when its range is selected — Lego-style
               feedback that the choice "landed" inside that band. */}
          {step === 5 && (<>
            <h3 className="font-display text-sm font-bold mb-1" style={{ color: "var(--text-primary)" }}>Уровень сложности</h3>
            <p className="text-xs mb-4" style={{ color: "var(--text-muted)" }}>Влияет на агрессивность, ловушки и адаптивную сложность. Подберите диапазон, затем — точный балл.</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {[
                { code: "easy",   range: [1, 3]  as [number, number], label: "Лёгкий",  color: "var(--success)", bg: "var(--success-muted)", desc: "Клиент лояльный, мало возражений. Для новичков." },
                { code: "medium", range: [4, 6]  as [number, number], label: "Средний", color: "var(--warning)", bg: "var(--warning-muted)", desc: "Стандартные возражения и ловушки. Базовый рабочий уровень." },
                { code: "hard",   range: [7, 8]  as [number, number], label: "Сложный", color: "var(--danger)",  bg: "var(--danger-muted)",  desc: "Агрессивный клиент, каскад ловушек. Закалка опытных." },
                { code: "boss",   range: [9, 10] as [number, number], label: "Эксперт", color: "#ff0055",        bg: "rgba(255,0,85,0.10)",  desc: "Максимальная сложность, все ловушки сразу. Только для боссов." },
              ].map((band) => {
                const inBand = difficulty >= band.range[0] && difficulty <= band.range[1];
                return (
                  <motion.div
                    key={band.code}
                    onClick={() => setDifficulty(band.range[0])}
                    className="glass-panel p-4 rounded-xl cursor-pointer relative"
                    style={{
                      background: inBand ? band.bg : undefined,
                      borderColor: inBand ? band.color : undefined,
                      boxShadow: inBand ? `0 0 18px -4px ${band.color}` : undefined,
                    }}
                    whileHover={{ y: -2 }}
                    whileTap={{ scale: 0.98 }}
                  >
                    {inBand && (
                      <div className="absolute top-2 right-2 w-5 h-5 rounded-full flex items-center justify-center" style={{ background: band.color }}>
                        <Check size={10} className="text-white" />
                      </div>
                    )}
                    <div className="flex items-baseline gap-2 mb-1">
                      <span className="font-display text-2xl font-black tabular-nums" style={{ color: inBand ? band.color : "var(--text-muted)" }}>
                        {band.range[0]}–{band.range[1]}
                      </span>
                      <span className="text-sm font-bold uppercase tracking-wider" style={{ color: inBand ? band.color : "var(--text-secondary)" }}>
                        {band.label}
                      </span>
                    </div>
                    <p className="text-xs leading-relaxed mb-3" style={{ color: "var(--text-muted)" }}>{band.desc}</p>
                    {/* Fine-tune row — only for the active band, otherwise it's noise. */}
                    {inBand && (
                      <div className="flex gap-1.5">
                        {Array.from({ length: band.range[1] - band.range[0] + 1 }, (_, i) => band.range[0] + i).map((lvl) => {
                          const exact = difficulty === lvl;
                          return (
                            <motion.button
                              key={lvl}
                              onClick={(e) => { e.stopPropagation(); setDifficulty(lvl); }}
                              className="flex-1 rounded-md py-1.5 text-sm font-mono font-bold"
                              style={{
                                background: exact ? band.color : "var(--input-bg)",
                                color: exact ? "#fff" : "var(--text-secondary)",
                                border: `1px solid ${exact ? band.color : "var(--border-color)"}`,
                              }}
                              whileTap={{ scale: 0.95 }}
                            >
                              {lvl}
                            </motion.button>
                          );
                        })}
                      </div>
                    )}
                  </motion.div>
                );
              })}
            </div>
            <div className="mt-4 text-center text-xs" style={{ color: "var(--text-muted)" }}>
              Текущий выбор: <span className="font-bold tabular-nums" style={{ color: "var(--text-primary)" }}>{difficulty}/10</span>
            </div>
          </>)}

          {/* ═══ Step 6: Environment (NEW) ═══
               PR-C: same mini-card-per-field treatment as Step 3 so the
               wizard reads as one continuous design language. */}
          {step === 6 && (<>
            <h3 className="font-display text-sm font-bold mb-1" style={{ color: "var(--text-primary)" }}>Модификаторы среды</h3>
            <p className="text-xs mb-4" style={{ color: "var(--text-muted)" }}>Условия, в которых находится клиент во время звонка</p>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="glass-panel p-4 rounded-xl">
                <RadioRow label="Фоновый шум" options={NOISES} value={bgNoise} onChange={(v) => setBgNoise(v as BackgroundNoise)} />
              </div>
              <div className="glass-panel p-4 rounded-xl">
                <RadioRow label="Время суток" options={TIMES} value={timeOfDay} onChange={(v) => setTimeOfDay(v as TimeOfDay)} />
              </div>
              <div className="glass-panel p-4 rounded-xl">
                <RadioRow label="Усталость клиента" options={FATIGUES} value={clientFatigue} onChange={(v) => setClientFatigue(v as ClientFatigue)} />
              </div>
            </div>
          </>)}

          {/* ═══ Step 7: Preview + Summary ═══ */}
          {step === 7 && (<>
            <div className="glass-panel p-6 rounded-2xl">
              <div className="flex items-center gap-3 mb-4">
                {selectedArchetype ? (
                  <AvatarPreview
                    seed={selectedArchetype.code}
                    size={48}
                    className="shrink-0 rounded-full"
                    style={{
                      border: `2px solid color-mix(in srgb, ${ARCHETYPE_GROUPS[selectedArchetype.group]?.color ?? "var(--accent)"} 30%, transparent)`,
                    }}
                  />
                ) : (
                  <Sparkles size={16} style={{ color: "var(--accent)" }} />
                )}
                <div>
                  <h3 className="font-display text-sm font-bold" style={{ color: "var(--text-primary)" }}>Ваш персонаж</h3>
                  {selectedArchetype && <div className="text-xs" style={{ color: "var(--text-muted)" }}>{selectedArchetype.name} · {selectedArchetype.subtitle}</div>}
                </div>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
                <div className="rounded-xl p-3" style={{ background: "var(--input-bg)" }}>
                  <div className="text-xs font-medium uppercase tracking-wide mb-1" style={{ color: "var(--text-muted)" }}>Архетип</div>
                  <div className="text-sm font-bold" style={{ color: selectedArchetype ? ARCHETYPE_GROUPS[selectedArchetype.group]?.color : "var(--text-primary)" }}>
                    {selectedArchetype ? <><AppIcon emoji={selectedArchetype.icon} size={16} /> {selectedArchetype.name}</> : "\u2014"}
                  </div>
                  {selectedArchetype && <div className="text-xs font-semibold mt-0.5" style={{ color: "var(--text-muted)" }}>T{selectedArchetype.tier} · Lv{selectedArchetype.unlock_level}+</div>}
                </div>
                <div className="rounded-xl p-3" style={{ background: "var(--input-bg)" }}>
                  <div className="text-xs font-medium uppercase tracking-wide mb-1" style={{ color: "var(--text-muted)" }}>Профессия</div>
                  <div className="text-sm font-bold" style={{ color: "var(--text-primary)" }}>{selectedProfession ? <><AppIcon emoji={selectedProfession.icon} size={16} /> {selectedProfession.name}</> : "\u2014"}</div>
                </div>
                <div className="rounded-xl p-3" style={{ background: "var(--input-bg)" }}>
                  <div className="text-xs font-medium uppercase tracking-wide mb-1" style={{ color: "var(--text-muted)" }}>Источник</div>
                  <div className="text-sm font-bold" style={{ color: "var(--text-primary)" }}>{LEAD_SOURCES.find((l) => l.code === leadSource)?.name ?? "\u2014"}</div>
                </div>
                <div className="rounded-xl p-3" style={{ background: "var(--input-bg)" }}>
                  <div className="text-xs font-medium uppercase tracking-wide mb-1" style={{ color: "var(--text-muted)" }}>Сложность</div>
                  <div className="text-lg font-black font-mono" style={{ color: difficulty <= 3 ? "var(--success)" : difficulty <= 6 ? "var(--warning)" : "var(--danger)" }}>{difficulty}/10</div>
                </div>
              </div>
              {/* Extra params summary — every chip always rendered so the
                  user sees exactly what was picked across all 9 wizard
                  fields, including defaults. Previously each chip was
                  gated by `value !== "default"`, so a user who kept the
                  defaults saw an empty preview and lost confidence that
                  step 3/4/6 picks landed. `tone` had no chip at all.   */}
              <div className="flex flex-wrap gap-1.5 mb-4">
                <span className="rounded-full px-2 py-0.5 text-xs font-medium" style={{ background: "var(--input-bg)", color: "var(--text-muted)" }}>Семья: {FAMILY_PRESETS.find(f => f.code === familyPreset)?.label ?? "Случайно"}</span>
                <span className="rounded-full px-2 py-0.5 text-xs font-medium" style={{ background: "var(--input-bg)", color: "var(--text-muted)" }}>Кредиторы: {CREDITORS_PRESETS.find(c => c.code === creditorsPreset)?.label ?? "Случайно"}</span>
                <span className="rounded-full px-2 py-0.5 text-xs font-medium" style={{ background: "var(--input-bg)", color: "var(--text-muted)" }}>Стадия: {DEBT_STAGES.find(d => d.code === debtStage)?.label ?? "Случайно"}</span>
                <span className="rounded-full px-2 py-0.5 text-xs font-medium" style={{ background: "var(--input-bg)", color: "var(--text-muted)" }}>Долг: {DEBT_RANGES.find(d => d.code === debtRange)?.label ?? "Случайно"}</span>
                <span className="rounded-full px-2 py-0.5 text-xs font-medium" style={{ background: "var(--input-bg)", color: "var(--text-muted)" }}>Настроение: {EMOTION_PRESETS.find(e => e.code === emotionPreset)?.name ?? "Нейтральный"}</span>
                <span className="rounded-full px-2 py-0.5 text-xs font-medium" style={{ background: "var(--input-bg)", color: "var(--text-muted)" }}>Тон: {TONES.find(t => t.code === tone)?.name ?? "Нейтральный"}</span>
                <span className="rounded-full px-2 py-0.5 text-xs font-medium" style={{ background: "var(--input-bg)", color: "var(--text-muted)" }}>Шум: {NOISES.find(n => n.code === bgNoise)?.label ?? "Тишина"}</span>
                <span className="rounded-full px-2 py-0.5 text-xs font-medium" style={{ background: "var(--input-bg)", color: "var(--text-muted)" }}>Время: {TIMES.find(t => t.code === timeOfDay)?.label ?? "День"}</span>
                <span className="rounded-full px-2 py-0.5 text-xs font-medium" style={{ background: "var(--input-bg)", color: "var(--text-muted)" }}>Усталость: {FATIGUES.find(f => f.code === clientFatigue)?.label ?? "Нормальный"}</span>
              </div>
              <p className="text-xs leading-relaxed" style={{ color: "var(--text-muted)" }}>
                AI создаст реалистичный портрет клиента на основе всех выбранных параметров.
              </p>

              {/* ── Editable name + autosave (2026-04-21) ──
                   Previously name was auto-generated from "архетип · профессия
                   · сложность/10" with no way to override — two identical
                   builds produced two identical names, making the saved list
                   impossible to scan. Autosave replaces the old manual
                   "Сохранить" button: saving is implicit unless the user
                   opts out, so they can never lose a carefully configured
                   client by forgetting to click. */}
              <div className="mt-5 pt-5 border-t" style={{ borderColor: "var(--border-color)" }}>
                <label className="block text-xs font-medium uppercase tracking-wide mb-2" style={{ color: "var(--text-muted)" }}>
                  Имя в моих клиентах
                </label>
                <input
                  type="text"
                  value={customName}
                  onChange={(e) => setCustomName(e.target.value)}
                  placeholder={buildFriendlyAutoname(
                    selectedArchetype?.code ?? null,
                    selectedArchetype?.name ?? null,
                    selectedProfession?.name ?? null,
                    difficulty,
                  )}
                  maxLength={100}
                  className="w-full rounded-xl px-3 py-2 text-sm"
                  style={{
                    background: "var(--input-bg)",
                    border: "1px solid var(--border-color)",
                    color: "var(--text-primary)",
                  }}
                />
                <label className="mt-3 flex items-center gap-2 text-sm cursor-pointer" style={{ color: "var(--text-secondary)" }}>
                  <input
                    type="checkbox"
                    checked={autoSave}
                    onChange={(e) => setAutoSave(e.target.checked)}
                    className="w-4 h-4"
                  />
                  <span>💾 Сохранить в «Мои клиенты» при запуске</span>
                </label>
                <p className="mt-1 text-xs" style={{ color: "var(--text-muted)" }}>
                  Можно будет запустить того же клиента ещё раз и смотреть прогресс: количество запусков, лучший балл, средний балл.
                </p>
              </div>
            </div>
          </>)}

        </motion.div>
      </AnimatePresence>

      {/* Navigation */}
      <div className="mt-8 flex items-center justify-between">
        <div className="flex gap-2.5">
          {step > 0 && (
            <Button variant="ghost" onClick={prevStep} size="sm" icon={<ChevronLeft size={16} />}>Назад</Button>
          )}
          {(archetype || profession) && (
            <Button variant="ghost" onClick={reset} size="sm" icon={<RotateCcw size={14} />}>Сбросить</Button>
          )}
        </div>

        <div className="flex gap-2.5">
          {/* 2026-04-21: "Пропустить" removed for optional steps 3/4/6.
              On those steps canNext() is always true, so the dedicated
              ghost button did exactly the same thing as "Далее" — a
              duplicate control that confused first-time users about which
              path was "correct". "Далее" handles both paths now. */}

          {step < 7 ? (
            <Button onClick={nextStep} disabled={!canNext()} size="sm" iconRight={<ArrowRight size={16} />}>Далее</Button>
          ) : (
            /* 2026-04-21: preview action row. Standalone "Сохранить" is
               gone — autosave checkbox + name input above handle it
               implicitly. The three remaining buttons are the three ways
               to ACTUALLY start the training; sharing the preview screen
               no longer has a fourth button that doesn't start anything. */
            <div className="flex flex-wrap gap-2.5">
              <Button variant="primary" onClick={() => handleStart(false, "chat")} disabled={starting || !archetype || !profession} size="sm" loading={starting} icon={<MessageCircle size={16} />}>
                Чат
              </Button>
              <Button onClick={() => handleStart(false, "call")} disabled={starting || !archetype || !profession} size="sm" loading={starting} icon={<Phone size={16} />} style={{ borderColor: "var(--accent)", color: "var(--accent)", background: "var(--accent-muted)" }}>
                Звонок
              </Button>
              <Button onClick={() => handleStart(true)} disabled={starting || !archetype || !profession} size="sm" loading={starting} icon={<Sparkles size={16} />} style={{ borderColor: "var(--accent-glow)", color: "var(--accent)" }}>
                AI x{storyCalls}
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
