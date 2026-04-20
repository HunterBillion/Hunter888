"use client";

/**
 * /pvp/tutorial — Arena first-match tutorial.
 *
 * Phase C (2026-04-20). New user lands here before their first real match
 * to learn the loop: read the question, use a lifeline when stuck, see the
 * coaching card after answering. 3 scripted rounds, all-frontend, no LLM
 * spend. Completion is persisted via `POST /api/tutorial/arena/complete`.
 *
 * Uses the production Arena components verbatim so what the player learns
 * here matches what they'll see in real PvP: CountdownOverlay,
 * CoachingCard, CelebrationBurst, sfx, theme accent.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowRight,
  Bot,
  BookOpen,
  CheckCircle2,
  Trophy,
  Sparkles,
  Volume2,
  VolumeX,
  XCircle,
} from "lucide-react";
import AuthLayout from "@/components/layout/AuthLayout";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";
import { useSFX } from "@/components/arena/sfx/useSFX";
import { themeFor } from "@/components/arena/themes";
import { CelebrationBurst } from "@/components/arena/reveal/CelebrationBurst";
import { CountdownOverlay } from "@/components/arena/reveal/CountdownOverlay";
import { CoachingCard, type CoachingPayload } from "@/components/arena/reveal/CoachingCard";

interface TutorialQuestion {
  id: string;
  text: string;
  options: Array<{ id: string; label: string }>;
  correctOptionId: string;
  coaching: CoachingPayload;
  tipBeforeAnswer?: string;
}

// Curated 3-question walkthrough — these are the same topics that appear
// in early real matches, so the tutorial doubles as a primer.
const QUESTIONS: TutorialQuestion[] = [
  {
    id: "q1",
    text: "Какая сумма долга нужна для внесудебного банкротства через МФЦ?",
    options: [
      { id: "a", label: "от 25 000 ₽ до 1 000 000 ₽" },
      { id: "b", label: "от 500 000 ₽ до 3 000 000 ₽" },
      { id: "c", label: "любая сумма — главное отсутствие имущества" },
    ],
    correctOptionId: "a",
    tipBeforeAnswer:
      "Подсказка: МФЦ — это упрощённая процедура для небольших долгов без имущества.",
    coaching: {
      tip: "Порог внесудебного банкротства — это первое, что проверяется. Для долгов выше 1 млн ₽ только суд.",
      idealReply:
        "Внесудебное банкротство через МФЦ доступно при долге 25 000 – 1 000 000 ₽ и подтверждённом отсутствии имущества.",
      keyArticles: ["ст. 223.2 127-ФЗ", "ст. 223.3 127-ФЗ"],
      scoreNormalised: 100,
    },
  },
  {
    id: "q2",
    text: "Сколько длится процедура реализации имущества в судебном банкротстве физлица?",
    options: [
      { id: "a", label: "До 30 дней" },
      { id: "b", label: "До 6 месяцев, продлевается судом" },
      { id: "c", label: "2 года фиксированно" },
    ],
    correctOptionId: "b",
    tipBeforeAnswer:
      "Подсказка: это наиболее частый ответ клиентов «как долго я буду в статусе банкрота».",
    coaching: {
      tip: "Срок 6 мес — ориентир, но суд продлевает при наличии имущества или споров с кредиторами.",
      idealReply:
        "Процедура реализации — до 6 месяцев, с продлением судом. Всё это время управляющий работает с активами должника.",
      keyArticles: ["ст. 213.24 127-ФЗ"],
      scoreNormalised: 100,
    },
  },
  {
    id: "q3",
    text: "В какой срок руководитель ОБЯЗАН подать заявление о банкротстве юрлица после признаков неплатёжеспособности?",
    options: [
      { id: "a", label: "30 дней" },
      { id: "b", label: "90 дней" },
      { id: "c", label: "Право, а не обязанность" },
    ],
    correctOptionId: "a",
    tipBeforeAnswer:
      "Подсказка: пропуск этого срока = субсидиарка для директора.",
    coaching: {
      tip: "30 дней — жёсткий триггер. Пропуск = личная ответственность КДЛ по ст. 61.12.",
      idealReply:
        "Руководитель должен подать заявление в течение 30 дней с момента возникновения признаков — иначе наступает субсидиарная ответственность за пропуск срока.",
      keyArticles: ["ст. 9 127-ФЗ", "ст. 61.12 127-ФЗ"],
      scoreNormalised: 100,
    },
  },
];

type Phase =
  | "intro"
  | "countdown"
  | "question"
  | "locked"
  | "reveal"
  | "summary"
  | "done";

export default function ArenaTutorialPage() {
  const router = useRouter();
  const theme = themeFor("arena");
  const sfx = useSFX();

  const [round, setRound] = useState(0);
  const [phase, setPhase] = useState<Phase>("intro");
  const [pickedId, setPickedId] = useState<string | null>(null);
  const [correctCount, setCorrectCount] = useState(0);
  const [celebrate, setCelebrate] = useState(false);
  const [coachingOpen, setCoachingOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [alreadyDone, setAlreadyDone] = useState<boolean | null>(null);
  // 2026-04-20: TTS через Web Speech API (без backend).
  // Владельцу важно «во всей панели голосом общаться» — туториал теперь
  // автоматически озвучивает вопрос, а юзер может выключить/перечитать.
  const [ttsEnabled, setTtsEnabled] = useState(true);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);

  const question = QUESTIONS[round];

  const speak = useCallback((text: string) => {
    if (typeof window === "undefined") return;
    const synth = window.speechSynthesis;
    if (!synth) return; // не поддерживается → тихая деградация
    // Cancel текущую речь — чтобы вопросы не накладывались при быстрой смене
    synth.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "ru-RU";
    u.rate = 0.95;
    u.pitch = 1.0;
    u.onstart = () => setIsSpeaking(true);
    u.onend = () => setIsSpeaking(false);
    u.onerror = () => setIsSpeaking(false);
    utteranceRef.current = u;
    synth.speak(u);
  }, []);

  const stopSpeaking = useCallback(() => {
    if (typeof window === "undefined") return;
    window.speechSynthesis?.cancel();
    setIsSpeaking(false);
  }, []);

  // Автоплей озвучки при переходе в фазу question.
  useEffect(() => {
    if (phase !== "question" || !ttsEnabled || !question) return;
    speak(question.text);
    // На unmount / смену фазы — прерываем речь
    return () => stopSpeaking();
  }, [phase, round, ttsEnabled, question, speak, stopSpeaking]);

  // Жёсткий cleanup на unmount (на случай навигации во время речи)
  useEffect(() => {
    return () => {
      if (typeof window !== "undefined") window.speechSynthesis?.cancel();
    };
  }, []);

  // Pre-warm sfx + check tutorial status (so returning users can replay
  // without the "first-time" celebration).
  useEffect(() => {
    sfx.prime();
    (async () => {
      try {
        const s = await api.get<{ completed: boolean }>(
          "/tutorial/arena/status",
        );
        setAlreadyDone(s.completed);
      } catch (e) {
        logger.warn("tutorial status failed", e);
        setAlreadyDone(false);
      }
    })();
  }, [sfx]);

  const handleStart = useCallback(() => {
    setPhase("countdown");
  }, []);

  const handleCountdownDone = useCallback(() => {
    setPhase("question");
    setPickedId(null);
  }, []);

  const handleChoose = useCallback(
    (optId: string) => {
      if (phase !== "question") return;
      setPickedId(optId);
      setPhase("locked");
      const isCorrect = optId === question.correctOptionId;
      if (isCorrect) {
        setCorrectCount((n) => n + 1);
        sfx.play("correct");
        setCelebrate(true);
        setTimeout(() => setCelebrate(false), 1200);
      } else {
        sfx.play("wrong");
      }
      // Reveal coaching card after a short breath so the player sees the
      // green/red feedback on the option they picked.
      setTimeout(() => {
        setPhase("reveal");
        setCoachingOpen(true);
      }, 900);
    },
    [phase, question, sfx],
  );

  const handleDismissCoaching = useCallback(() => {
    setCoachingOpen(false);
    if (round + 1 < QUESTIONS.length) {
      setRound((r) => r + 1);
      setPhase("countdown");
    } else {
      setPhase("summary");
    }
  }, [round]);

  const handleFinish = useCallback(async () => {
    setSaving(true);
    let completed = false;
    try {
      await api.post<{ first_time: boolean }>("/tutorial/arena/complete", {});
      completed = true;
    } catch (e) {
      logger.warn("tutorial complete post failed", e);
      // 2026-04-20: НЕ ставим localStorage в catch. Раньше флаг ставился
      // в finally — если бэк упал, фронт считал туториал пройденным, а бэк
      // нет. Юзер возвращался → welcome исчезал, хотя на /pvp/rating/me
      // tutorial_completed всё ещё false → рассинхрон двух источников.
      // Теперь: флаг ставится ТОЛЬКО после успеха. Если упало — юзер
      // увидит welcome снова (корректно, повторит туториал).
    } finally {
      if (completed) {
        try { localStorage.setItem("arena_tutorial_completed", "1"); } catch { /* ignore */ }
      }
      setSaving(false);
      router.push("/pvp");
    }
  }, [router]);

  const progress = useMemo(
    () => `${Math.min(round + 1, QUESTIONS.length)}/${QUESTIONS.length}`,
    [round],
  );

  return (
    <AuthLayout>
      <div
        className="min-h-[calc(100vh-100px)] flex flex-col"
        style={{
          background: `radial-gradient(circle at 30% 20%, ${theme.accent}18 0%, transparent 55%), var(--bg-primary)`,
        }}
      >
        {/* ── Header ── */}
        <div
          className="flex items-center justify-between px-4 md:px-8 py-3"
          style={{ borderBottom: `1px solid ${theme.accent}22` }}
        >
          <div className="flex items-center gap-3">
            <div
              className="flex items-center justify-center h-9 w-9 rounded-xl"
              style={{
                background: `${theme.accent}22`,
                color: theme.accent,
                border: `1px solid ${theme.accent}55`,
              }}
            >
              <Bot size={18} />
            </div>
            <div>
              <div
                className="text-[10px] uppercase tracking-wider font-semibold"
                style={{ color: theme.accent }}
              >
                Первая Арена
              </div>
              <div className="font-semibold" style={{ color: "var(--text-primary)" }}>
                Тренировка с наставником
              </div>
            </div>
          </div>
          {phase !== "intro" && phase !== "summary" && (
            <div
              className="rounded-full px-3 py-1 font-mono text-sm"
              style={{
                background: `${theme.accent}14`,
                border: `1px solid ${theme.accent}33`,
                color: theme.accent,
              }}
            >
              раунд {progress}
            </div>
          )}
          <button
            type="button"
            onClick={() => router.push("/pvp")}
            className="text-xs uppercase tracking-widest"
            style={{ color: "var(--text-muted)" }}
          >
            Пропустить
          </button>
        </div>

        {/* ── Body ── */}
        <div className="flex-1 flex items-center justify-center px-4 py-8">
          <AnimatePresence mode="wait">
            {phase === "intro" && (
              <motion.div
                key="intro"
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="max-w-xl w-full text-center"
              >
                <motion.div
                  animate={{ rotate: [0, -5, 5, 0], scale: [1, 1.03, 1] }}
                  transition={{ duration: 2.2, repeat: Infinity }}
                  className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl mb-4"
                  style={{
                    background: `${theme.accent}22`,
                    color: theme.accent,
                    border: `2px solid ${theme.accent}55`,
                  }}
                >
                  <Sparkles size={26} />
                </motion.div>
                <h1
                  className="text-3xl md:text-4xl font-bold mb-3"
                  style={{ color: "var(--text-primary)" }}
                >
                  Как работает Арена
                </h1>
                <p
                  className="text-base md:text-lg mb-6 leading-relaxed"
                  style={{ color: "var(--text-muted)" }}
                >
                  3 коротких раунда против AI-наставника. Ответишь — получишь
                  идеальную реплику и статьи 127-ФЗ. После тренировки откроется
                  настоящий рейтинговый матч.
                </p>
                <div
                  className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-8 text-left"
                  style={{ color: "var(--text-secondary)" }}
                >
                  {[
                    {
                      icon: BookOpen,
                      title: "3 вопроса",
                      sub: "порог МФЦ, срок реализации, срок подачи",
                    },
                    {
                      icon: Trophy,
                      title: "Разбор каждой ошибки",
                      sub: "что было бы лучше сказать",
                    },
                    {
                      icon: CheckCircle2,
                      title: "Без рейтинга",
                      sub: "реальный матч стартует после",
                    },
                  ].map((it, i) => {
                    const Icon = it.icon;
                    return (
                      <div
                        key={i}
                        className="rounded-xl p-3"
                        style={{
                          background: "rgba(255,255,255,0.03)",
                          border: "1px solid rgba(255,255,255,0.08)",
                        }}
                      >
                        <Icon size={16} style={{ color: theme.accent }} />
                        <div
                          className="text-sm font-semibold mt-1"
                          style={{ color: "var(--text-primary)" }}
                        >
                          {it.title}
                        </div>
                        <div className="text-xs mt-0.5">{it.sub}</div>
                      </div>
                    );
                  })}
                </div>
                <motion.button
                  type="button"
                  onClick={handleStart}
                  whileTap={{ scale: 0.97 }}
                  className="inline-flex items-center gap-2 rounded-xl px-6 py-3 text-sm font-semibold"
                  style={{
                    background: theme.accent,
                    color: "#0b0b14",
                    boxShadow: `0 20px 40px -12px ${theme.glow}`,
                  }}
                >
                  Поехали
                  <ArrowRight size={14} />
                </motion.button>
                {alreadyDone && (
                  <div
                    className="mt-4 text-xs"
                    style={{ color: "var(--text-muted)" }}
                  >
                    Ты уже проходил(а) тренировку — но можешь повторить.
                  </div>
                )}
              </motion.div>
            )}

            {(phase === "question" || phase === "locked" || phase === "reveal") &&
              question && (
                <motion.div
                  key={`q-${round}`}
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  className="max-w-2xl w-full"
                >
                  <div
                    className="rounded-2xl p-5 md:p-6 mb-4"
                    style={{
                      background: "var(--bg-panel)",
                      border: `1px solid ${theme.accent}33`,
                    }}
                  >
                    <div className="flex items-center justify-between gap-3 mb-2">
                      <div
                        className="text-[10px] uppercase tracking-wider font-semibold"
                        style={{ color: theme.accent }}
                      >
                        Вопрос {round + 1}
                        {isSpeaking && (
                          <span
                            className="ml-2 inline-flex items-center gap-1 animate-pulse"
                            style={{ color: theme.accent }}
                          >
                            <span
                              className="inline-block w-1 h-1 rounded-full"
                              style={{ background: theme.accent }}
                            />
                            озвучиваю…
                          </span>
                        )}
                      </div>
                      {/* 2026-04-20: переключатель TTS + replay. Web Speech API,
                          без backend. Toggle off выключает автоплей на все
                          следующие вопросы. Replay (Volume2 click when enabled)
                          перечитывает текущий вопрос. */}
                      <div className="flex items-center gap-1">
                        <button
                          type="button"
                          onClick={() => {
                            if (ttsEnabled) {
                              // Replay текущий вопрос если уже включено
                              speak(question.text);
                            } else {
                              setTtsEnabled(true);
                              speak(question.text);
                            }
                          }}
                          className="p-1.5 rounded-md transition hover:bg-[var(--input-bg)]"
                          style={{ color: ttsEnabled ? theme.accent : "var(--text-muted)" }}
                          title={ttsEnabled ? "Повторить озвучку" : "Включить голос"}
                          aria-label={ttsEnabled ? "Повторить озвучку" : "Включить голос"}
                        >
                          <Volume2 size={16} />
                        </button>
                        {ttsEnabled && (
                          <button
                            type="button"
                            onClick={() => { setTtsEnabled(false); stopSpeaking(); }}
                            className="p-1.5 rounded-md transition hover:bg-[var(--input-bg)]"
                            style={{ color: "var(--text-muted)" }}
                            title="Выключить голос"
                            aria-label="Выключить голос"
                          >
                            <VolumeX size={16} />
                          </button>
                        )}
                      </div>
                    </div>
                    <div
                      className="text-lg md:text-xl font-semibold leading-snug"
                      style={{ color: "var(--text-primary)" }}
                    >
                      {question.text}
                    </div>
                    {question.tipBeforeAnswer && phase === "question" && (
                      <div
                        className="mt-3 inline-flex items-center gap-1.5 text-xs"
                        style={{ color: "var(--text-muted)" }}
                      >
                        💡 {question.tipBeforeAnswer}
                      </div>
                    )}
                  </div>

                  <div className="grid gap-2">
                    {question.options.map((o) => {
                      const isPicked = pickedId === o.id;
                      const isCorrect = o.id === question.correctOptionId;
                      const reveal = phase === "locked" || phase === "reveal";
                      const showAsCorrect = reveal && isCorrect;
                      const showAsWrongPick = reveal && isPicked && !isCorrect;
                      const color = showAsCorrect
                        ? "#4ade80"
                        : showAsWrongPick
                          ? "#f87171"
                          : theme.accent;
                      const bg = showAsCorrect
                        ? "rgba(74,222,128,0.12)"
                        : showAsWrongPick
                          ? "rgba(248,113,113,0.12)"
                          : isPicked
                            ? `${theme.accent}18`
                            : "rgba(255,255,255,0.03)";
                      const Icon = showAsCorrect
                        ? CheckCircle2
                        : showAsWrongPick
                          ? XCircle
                          : null;
                      return (
                        <motion.button
                          key={o.id}
                          type="button"
                          disabled={phase !== "question"}
                          onClick={() => handleChoose(o.id)}
                          whileTap={phase === "question" ? { scale: 0.98 } : undefined}
                          className="text-left rounded-xl px-4 py-3 flex items-center gap-3 transition-all disabled:cursor-default"
                          style={{
                            background: bg,
                            border: `1px solid ${color}${showAsCorrect || showAsWrongPick ? "66" : "22"}`,
                            color: "var(--text-primary)",
                          }}
                        >
                          <span
                            className="flex items-center justify-center h-6 w-6 rounded-md font-mono text-xs font-bold"
                            style={{
                              background: `${color}22`,
                              color,
                              border: `1px solid ${color}44`,
                            }}
                          >
                            {o.id.toUpperCase()}
                          </span>
                          <span className="flex-1 text-sm">{o.label}</span>
                          {Icon && <Icon size={16} style={{ color }} />}
                        </motion.button>
                      );
                    })}
                  </div>
                </motion.div>
              )}

            {phase === "summary" && (
              <motion.div
                key="summary"
                initial={{ opacity: 0, scale: 0.96 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0 }}
                className="max-w-xl w-full text-center"
              >
                <div
                  className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl mb-4"
                  style={{
                    background: "rgba(74,222,128,0.15)",
                    color: "#4ade80",
                    border: "2px solid rgba(74,222,128,0.5)",
                  }}
                >
                  <Trophy size={26} />
                </div>
                <h2
                  className="text-3xl font-bold mb-1"
                  style={{ color: "var(--text-primary)" }}
                >
                  Арена открыта
                </h2>
                <div
                  className="text-sm mb-5"
                  style={{ color: "var(--text-muted)" }}
                >
                  Ты ответил(а) правильно на{" "}
                  <span
                    className="font-mono font-bold"
                    style={{ color: theme.accent }}
                  >
                    {correctCount}/{QUESTIONS.length}
                  </span>{" "}
                  · базовые опоры 127-ФЗ знаешь.
                </div>
                <div
                  className="rounded-xl p-4 mb-6 text-left text-sm"
                  style={{
                    background: "rgba(255,255,255,0.03)",
                    border: "1px solid rgba(255,255,255,0.08)",
                    color: "var(--text-secondary)",
                  }}
                >
                  Что теперь работает на реальной Арене:
                  <ul className="mt-2 space-y-1 list-disc list-inside text-[13px]">
                    <li>кнопка «Подсказка» — 2 за матч, использует RAG по 127-ФЗ</li>
                    <li>кнопка «Пропустить» — 1 за матч, без штрафа</li>
                    <li>микрофон — отвечай голосом</li>
                    <li>разбор после каждого раунда с идеальной репликой</li>
                  </ul>
                </div>
                <motion.button
                  type="button"
                  onClick={handleFinish}
                  disabled={saving}
                  whileTap={{ scale: 0.97 }}
                  className="inline-flex items-center gap-2 rounded-xl px-6 py-3 text-sm font-semibold disabled:opacity-40"
                  style={{
                    background: theme.accent,
                    color: "#0b0b14",
                    boxShadow: `0 20px 40px -12px ${theme.glow}`,
                  }}
                >
                  {saving ? "Сохраняю…" : "На Арену"}
                  <ArrowRight size={14} />
                </motion.button>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* ── Overlays ── */}
        <CountdownOverlay
          open={phase === "countdown"}
          accentColor={theme.accent}
          label={`РАУНД ${round + 1}`}
          onDone={handleCountdownDone}
        />
        <CoachingCard
          open={coachingOpen}
          accentColor={theme.accent}
          payload={question?.coaching ?? null}
          onDismiss={handleDismissCoaching}
        />
        <CelebrationBurst trigger={celebrate} />
      </div>
    </AuthLayout>
  );
}
