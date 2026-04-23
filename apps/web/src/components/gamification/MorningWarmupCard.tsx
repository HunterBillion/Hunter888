"use client";

/**
 * MorningWarmupCard — 2026-04-17 replacement for the chat-style DailyDrillCard
 * on /home. Instead of a back-and-forth AI dialogue, it shows 3-5 short
 * standalone questions one after another:
 *
 *   1. Read question → type short answer → press Enter (or click "Проверить")
 *   2. Instant heuristic feedback (keywords matched / hint / why-it-matters)
 *   3. After the last question → "Разминка завершена" → "Перейти к тренировке"
 *
 * 2026-04-20 UX fixes:
 *   * Enter submits, Shift+Enter adds a newline (was: Ctrl/Cmd+Enter only).
 *   * Feedback now has a collapsible "Почему так" section with law article
 *     + reasoning + verbatim source excerpt (was: one-line эталон).
 *   * On completion the client POSTs /morning-drill/complete so the
 *     `daily_warmup` goal ticks up. Repeat of the same session is a no-op.
 *   * "Повторить" replaced with "Перейти к тренировке" — finishing warm-up
 *     is a ONE-time daily action, retakes devalue it.
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useRouter } from "next/navigation";
import { Flame, Snowflake, Coffee, CheckCircle } from "lucide-react";
import { api } from "@/lib/api";
import WarmupEndingAnimation, { pickAnimationVariant } from "./WarmupEndingAnimation";

type StreakInfo = {
  current_streak: number;
  longest_streak: number;
  completed_today: boolean;
  last_completed_on: string | null;
  unused_freezes: number;
  can_purchase: boolean;
  cost_ap: number;
  max_per_month: number;
  purchased_this_month: number;
};

type Question = {
  id: string;
  kind: "legal" | "sales";
  prompt: string;
  context?: string | null;
  hint?: string | null;
  law_article?: string | null;
  category?: string | null;
  // 2026-04-20: multiple-choice. When present (2-4 options), UI renders
  // radio buttons instead of a textarea. See seed_mc_choices.py.
  choices?: string[] | null;
};

type DrillResp = {
  session_id: string;
  total_questions: number;
  questions: Question[];
};

type Feedback = {
  question_id: string;
  ok: boolean;
  hint?: string | null;
  matched_keywords: string[];
  law_article?: string | null;
  why_it_matters?: string | null;
  source_excerpt?: string | null;
  // LLM grader (gpt-5.4 via navy.api). Nullable — falls back to hint+keywords.
  ai_score?: number | null;
  ai_feedback?: string | null;
  ai_covered?: string[];
  ai_missed?: string[];
  ai_model?: string | null;
};

type AnswerRecord = {
  question_id: string;
  kind: "legal" | "sales";
  answer: string;
  ok: boolean;
  matched_keywords: string[];
};

type State =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; msg: string }
  | {
      status: "running";
      drill: DrillResp;
      index: number;
      userAnswer: string;
      // For multiple-choice: index of the option picked (null until picked).
      choiceIndex: number | null;
      feedback: Feedback | null;
      submitting: boolean;
      answers: AnswerRecord[];
      whyOpen: boolean;
    }
  | { status: "done"; total: number; correct: number; saved: boolean };

export default function MorningWarmupCard() {
  const [state, setState] = useState<State>({ status: "idle" });
  const [score, setScore] = useState(0);
  const [streak, setStreak] = useState<StreakInfo | null>(null);
  const [freezeBusy, setFreezeBusy] = useState(false);
  const router = useRouter();

  const loadStreak = useCallback(() => {
    api
      .get<StreakInfo>("/morning-drill/streak")
      .then(setStreak)
      .catch(() => {
        /* streak badge is optional — silently skip on error */
      });
  }, []);

  useEffect(() => {
    loadStreak();
  }, [loadStreak]);

  const purchaseFreeze = useCallback(async () => {
    if (freezeBusy) return;
    setFreezeBusy(true);
    try {
      await api.post("/gamification/streak-freeze/purchase", {});
      loadStreak();
    } catch {
      // ignore — button shows AP cost up-front, user will see balance error
    } finally {
      setFreezeBusy(false);
    }
  }, [freezeBusy, loadStreak]);

  // Track whether we already fired /complete for the current session so a
  // double-click on "Завершить" doesn't double-save. Resets on new drill.
  const completedForRef = useRef<string | null>(null);

  const startDrill = useCallback(async () => {
    setState({ status: "loading" });
    try {
      const drill = await api.get<DrillResp>("/morning-drill");
      if (!drill.questions?.length) {
        setState({ status: "error", msg: "Нет вопросов на сегодня" });
        return;
      }
      setScore(0);
      completedForRef.current = null;
      setState({
        status: "running",
        drill,
        index: 0,
        userAnswer: "",
        choiceIndex: null,
        feedback: null,
        submitting: false,
        answers: [],
        whyOpen: false,
      });
    } catch (e) {
      setState({ status: "error", msg: e instanceof Error ? e.message : "Не удалось загрузить" });
    }
  }, []);

  const submitAnswer = useCallback(async () => {
    if (state.status !== "running" || state.submitting) return;
    const currentQ = state.drill.questions[state.index];
    const isMC = Array.isArray(currentQ.choices) && currentQ.choices.length >= 2;
    // For MC: require a selected option. For textarea: require non-empty text.
    if (isMC) {
      if (state.choiceIndex === null) return;
    } else if (!state.userAnswer.trim()) {
      return;
    }
    setState({ ...state, submitting: true });
    try {
      const answerText = isMC
        ? (currentQ.choices?.[state.choiceIndex ?? 0] ?? "")
        : state.userAnswer;
      const fb = await api.post<Feedback>("/morning-drill/submit", {
        session_id: state.drill.session_id,
        question_id: currentQ.id,
        answer: answerText,
        choice_index: isMC ? state.choiceIndex : null,
      });
      if (fb.ok) setScore((s) => s + 1);
      setState((prev) => {
        if (prev.status !== "running") return prev;
        const q = prev.drill.questions[prev.index];
        const rec: AnswerRecord = {
          question_id: q.id,
          kind: q.kind,
          answer: answerText,
          ok: fb.ok,
          matched_keywords: fb.matched_keywords,
        };
        return {
          ...prev,
          feedback: fb,
          submitting: false,
          answers: [...prev.answers, rec],
          whyOpen: false,
        };
      });
    } catch (e) {
      setState({ status: "error", msg: e instanceof Error ? e.message : "Ошибка отправки" });
    }
  }, [state]);

  const finalizeDrill = useCallback(
    async (drill: DrillResp, answers: AnswerRecord[], correct: number) => {
      // Guard against double-firing on second click of "Завершить".
      if (completedForRef.current === drill.session_id) return;
      completedForRef.current = drill.session_id;
      try {
        await api.post("/morning-drill/complete", {
          session_id: drill.session_id,
          total_questions: drill.total_questions,
          answers,
        });
        setState({ status: "done", total: drill.total_questions, correct, saved: true });
        // Refresh the streak badge (current_streak + completed_today) so
        // the idle card shows the new numbers when the user returns.
        loadStreak();
        // Nudge parent page to refetch daily goals so `daily_warmup` tick
        // shows without a full reload. /home listens via CustomEvent.
        if (typeof window !== "undefined") {
          window.dispatchEvent(new CustomEvent("goals:refresh"));
        }
      } catch {
        // Even if /complete failed, show the done screen — user finished.
        setState({ status: "done", total: drill.total_questions, correct, saved: false });
      }
    },
    [loadStreak],
  );

  const nextQuestion = useCallback(() => {
    if (state.status !== "running") return;
    const nextIdx = state.index + 1;
    if (nextIdx >= state.drill.questions.length) {
      void finalizeDrill(state.drill, state.answers, score);
      return;
    }
    setState({
      ...state,
      index: nextIdx,
      userAnswer: "",
      choiceIndex: null,
      feedback: null,
      whyOpen: false,
    });
  }, [state, score, finalizeDrill]);

  // Preload on mount is not automatic — user clicks the button
  useEffect(() => {
    // no-op placeholder in case we want to prefetch later
  }, []);

  // ── Render ──

  // Bug fix 2026-04-21: idle state used to ALWAYS show "Start drill" even
  // if user already completed today's warmup. That caused the confusing
  // behavior where successful completion animation → page refresh → the
  // card again invited the user to "start a drill" (already-done check
  // was missing). Now we branch on streak.completed_today.
  const alreadyDoneToday = Boolean(streak?.completed_today);

  if (state.status === "idle" || state.status === "error") {
    // ── Completed-today state ─────────────────────────────────────
    if (alreadyDoneToday && state.status === "idle") {
      return (
        <div
          className="rounded-xl border p-5 flex flex-col gap-3 relative overflow-hidden"
          style={{
            background: "linear-gradient(135deg, color-mix(in srgb, var(--success, #10b981) 8%, var(--bg-panel)) 0%, var(--bg-panel) 100%)",
            borderColor: "color-mix(in srgb, var(--success, #10b981) 35%, var(--border-color))",
            minHeight: "220px",
          }}
        >
          <div className="flex items-start justify-between">
            <div>
              <div className="text-xs font-pixel uppercase tracking-wider" style={{ color: "var(--success, #10b981)" }}>
                Разминка сегодня
              </div>
              <div className="text-lg font-semibold mt-1 flex items-center gap-2" style={{ color: "var(--text-primary)" }}>
                <CheckCircle size={20} style={{ color: "var(--success, #10b981)" }} />
                Уже прошёл
              </div>
              <p className="text-sm mt-1" style={{ color: "var(--text-secondary)" }}>
                Возвращайся завтра утром за следующим набором вопросов.
              </p>
            </div>
            <Coffee
              aria-hidden
              size={28}
              strokeWidth={1.75}
              style={{ color: "var(--success, #10b981)", opacity: 0.6 }}
            />
          </div>
          {streak && (streak.current_streak > 0 || streak.unused_freezes > 0) && (
            <div className="flex items-center flex-wrap gap-2 text-[11px]" style={{ color: "var(--text-muted)" }}>
              {streak.current_streak > 0 && (
                <span
                  className="inline-flex items-center gap-1 rounded px-1.5 py-0.5"
                  style={{ background: "color-mix(in srgb, var(--warning) 12%, transparent)", color: "var(--warning)" }}
                  title={`Лучшая серия: ${streak.longest_streak}`}
                >
                  <Flame size={12} /> {streak.current_streak}d streak
                </span>
              )}
              {streak.unused_freezes > 0 && (
                <span
                  className="inline-flex items-center gap-1 rounded px-1.5 py-0.5"
                  style={{ background: "color-mix(in srgb, var(--accent) 10%, transparent)", color: "var(--accent)" }}
                >
                  <Snowflake size={12} /> {streak.unused_freezes} freeze
                </span>
              )}
              {streak.last_completed_on && (
                <span className="inline-flex items-center gap-1 opacity-75">
                  Последняя: {new Date(streak.last_completed_on).toLocaleDateString("ru-RU", { day: "numeric", month: "short" })}
                </span>
              )}
            </div>
          )}
          <div className="mt-auto text-xs text-center" style={{ color: "var(--text-muted)" }}>
            Разминка обновляется в 00:00 по локальному времени
          </div>
        </div>
      );
    }

    // ── Idle (not yet done today) or Error state ─────────────────
    return (
      <div
        className="rounded-xl border p-5 flex flex-col gap-3"
        style={{ background: "var(--bg-panel)", borderColor: "var(--border-color)", minHeight: "220px" }}
      >
        <div className="flex items-start justify-between">
          <div>
            <div className="text-xs font-pixel uppercase tracking-wider" style={{ color: "var(--accent)" }}>
              Утренняя разминка
            </div>
            <div
              className="text-lg font-semibold mt-1"
              style={{ color: "var(--text-primary)" }}
            >
              5 коротких вопросов · 1 минута
            </div>
            <p className="text-sm mt-1" style={{ color: "var(--text-secondary)" }}>
              Разогрев — без давления. Ошибки не влияют на рейтинг.
            </p>
          </div>
          <Coffee
            aria-hidden
            size={28}
            strokeWidth={1.75}
            style={{ color: "var(--accent)" }}
          />
        </div>
        {streak && (streak.current_streak > 0 || streak.unused_freezes > 0) && (
          <div
            className="flex items-center flex-wrap gap-2 text-[11px]"
            style={{ color: "var(--text-muted)" }}
          >
            {streak.current_streak > 0 && (
              <span
                className="inline-flex items-center gap-1 rounded px-1.5 py-0.5"
                style={{
                  background: "color-mix(in srgb, var(--warning) 12%, transparent)",
                  color: "var(--warning)",
                }}
                title={`Лучшая серия: ${streak.longest_streak}`}
              >
                <Flame size={12} /> {streak.current_streak}d streak
              </span>
            )}
            {streak.unused_freezes > 0 && (
              <span
                className="inline-flex items-center gap-1 rounded px-1.5 py-0.5"
                style={{
                  background: "color-mix(in srgb, var(--accent) 10%, transparent)",
                  color: "var(--accent)",
                }}
                title="Автоматически спасёт streak при пропуске 1 дня"
              >
                <Snowflake size={12} /> {streak.unused_freezes} freeze
              </span>
            )}
            {streak.can_purchase && streak.unused_freezes === 0 && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  void purchaseFreeze();
                }}
                disabled={freezeBusy}
                className="underline disabled:opacity-40"
                style={{ color: "var(--text-secondary)" }}
              >
                Купить заморозку · {streak.cost_ap} AP
              </button>
            )}
          </div>
        )}
        {state.status === "error" && (
          <p className="text-sm" style={{ color: "var(--danger, #ff5f57)" }}>
            {state.msg}
          </p>
        )}
        <div className="flex-1" />
        <button
          onClick={startDrill}
          className="rounded-md py-2.5 text-sm font-bold uppercase tracking-wider"
          style={{ background: "var(--accent)", color: "white", letterSpacing: "0.06em" }}
        >
          Начать разминку →
        </button>
      </div>
    );
  }

  if (state.status === "loading") {
    return (
      <div
        className="rounded-xl border p-5 flex items-center justify-center"
        style={{ background: "var(--bg-panel)", borderColor: "var(--border-color)", minHeight: "220px" }}
      >
        <span style={{ color: "var(--text-muted)" }}>Подгружаю вопросы…</span>
      </div>
    );
  }

  if (state.status === "done") {
    const allRight = state.correct === state.total;
    const halfRight = state.correct >= Math.ceil(state.total / 2);
    const tone = allRight ? "success" : halfRight ? "warning" : "muted";
    const headline = allRight
      ? "Отлично, ты в форме."
      : halfRight
      ? "Хорошее начало дня."
      : "Ты не выспался? Завтра продолжим.";
    const sub = allRight
      ? "Переходи к тренировкам."
      : halfRight
      ? "Нормальный старт — тренировки закрепят."
      : "Вопросы, где ошибся, вернутся в завтрашней разминке.";

    const failedCount = state.total - state.correct;
    const currentStreak = streak?.current_streak ?? 0;
    const animVariant = pickAnimationVariant(state.correct, state.total, currentStreak, failedCount);

    return (
      <div
        className="rounded-xl border p-5 flex flex-col gap-3"
        style={{ background: "var(--bg-panel)", borderColor: "var(--border-color)", minHeight: "220px" }}
      >
        <div className="text-xs font-pixel uppercase tracking-wider" style={{ color: "var(--accent)" }}>
          Разминка завершена
        </div>

        {/* Pixel-art animation — driven by real data */}
        <WarmupEndingAnimation
          variant={animVariant}
          streakCount={currentStreak}
          questionsReturning={failedCount}
          size={200}
          className="my-2"
        />

        <div className="text-xl font-semibold" style={{ color: "var(--text-primary)" }}>
          {state.correct} из {state.total} раскрыты по ключам
        </div>
        <p className="text-sm" style={{ color: `var(--${tone === "muted" ? "text-secondary" : tone})` }}>
          <span className="font-semibold">{headline}</span>{" "}
          <span style={{ color: "var(--text-secondary)" }}>{sub}</span>
        </p>
        {state.saved && (
          <div
            className="text-xs flex items-center gap-1.5"
            style={{ color: "var(--success)" }}
          >
            <span>✓</span>
            <span>Засчитано в «Задания на сегодня» (+20 XP)</span>
          </div>
        )}
        <div className="flex-1" />
        <button
          onClick={() => router.push("/training")}
          className="rounded-md py-2.5 text-sm font-bold uppercase tracking-wider"
          style={{ background: "var(--accent)", color: "white", letterSpacing: "0.06em" }}
        >
          Перейти к тренировке →
        </button>
      </div>
    );
  }

  // state.status === "running"
  const q = state.drill.questions[state.index];
  const progress = ((state.index + 1) / state.drill.questions.length) * 100;
  const fb = state.feedback;

  return (
    <div
      className="rounded-xl border p-5 flex flex-col gap-3"
      style={{ background: "var(--bg-panel)", borderColor: "var(--border-color)", minHeight: "260px" }}
    >
      {/* Progress header */}
      <div className="flex items-center justify-between">
        <div 
          className="font-pixel tracking-wider" 
          style={{ 
            color: "var(--accent)",
            fontSize: "28px",
            lineHeight: "1.2"
          }}
        >
          Вопрос {state.index + 1} / {state.drill.questions.length}
        </div>
        {q.law_article && (
          <span
            className="text-[11px] font-medium rounded px-1.5 py-0.5"
            style={{
              background: "color-mix(in srgb, var(--accent) 12%, transparent)",
              color: "var(--accent)",
            }}
          >
            {q.law_article}
          </span>
        )}
      </div>
      <div className="h-1 rounded-full overflow-hidden" style={{ background: "var(--input-bg)" }}>
        <div
          className="h-full transition-all"
          style={{ width: `${progress}%`, background: "var(--accent)" }}
        />
      </div>

      {/* Question */}
      <div
        className="text-base font-semibold leading-snug"
        style={{ color: "var(--text-primary)" }}
      >
        {q.prompt}
      </div>
      {q.context && (
        <p className="text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
          {q.context}
        </p>
      )}

      {/* Answer input OR feedback */}
      <AnimatePresence mode="wait">
        {!fb ? (
          <motion.div
            key="input"
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="space-y-2"
          >
            {Array.isArray(q.choices) && q.choices.length >= 2 ? (
              // ── Multiple choice ───────────────────────────────────────
              <div
                role="radiogroup"
                aria-label="Варианты ответа"
                className="space-y-1.5"
              >
                {q.choices.map((opt, idx) => {
                  const picked = state.choiceIndex === idx;
                  return (
                    <button
                      key={idx}
                      type="button"
                      role="radio"
                      aria-checked={picked}
                      disabled={state.submitting}
                      onClick={() => setState({ ...state, choiceIndex: idx })}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && state.choiceIndex !== null) {
                          e.preventDefault();
                          submitAnswer();
                        }
                      }}
                      className="w-full text-left rounded-md border px-3 py-2.5 text-sm transition disabled:opacity-40 flex items-center gap-3"
                      style={{
                        background: picked
                          ? "color-mix(in srgb, var(--accent) 12%, var(--input-bg))"
                          : "var(--input-bg)",
                        borderColor: picked ? "var(--accent)" : "var(--border-color)",
                        color: "var(--text-primary)",
                      }}
                    >
                      <span
                        aria-hidden
                        className="w-4 h-4 rounded-full border-2 flex-shrink-0 flex items-center justify-center"
                        style={{
                          borderColor: picked ? "var(--accent)" : "var(--border-color)",
                          background: picked ? "var(--accent)" : "transparent",
                        }}
                      >
                        {picked && (
                          <span
                            className="w-1.5 h-1.5 rounded-full"
                            style={{ background: "white" }}
                          />
                        )}
                      </span>
                      <span className="flex-1">{opt}</span>
                    </button>
                  );
                })}
              </div>
            ) : (
              // ── Free-form textarea ────────────────────────────────────
              <>
                <textarea
                  value={state.userAnswer}
                  onChange={(e) =>
                    setState({ ...state, userAnswer: e.target.value })
                  }
                  onKeyDown={(e) => {
                    // 2026-04-20: plain Enter submits. Shift+Enter = newline.
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      submitAnswer();
                    }
                  }}
                  placeholder="Короткий ответ в 1-2 строки…"
                  className="vh-input w-full resize-none"
                  rows={3}
                  disabled={state.submitting}
                  autoFocus
                />
              </>
            )}
            <button
              onClick={submitAnswer}
              disabled={
                state.submitting ||
                (Array.isArray(q.choices) && q.choices.length >= 2
                  ? state.choiceIndex === null
                  : !state.userAnswer.trim())
              }
              className="w-full rounded-md py-2.5 text-sm font-bold uppercase tracking-wider disabled:opacity-40"
              style={{ background: "var(--accent)", color: "white", letterSpacing: "0.06em" }}
            >
              {state.submitting ? "Проверяю…" : "Проверить"}
            </button>
          </motion.div>
        ) : (
          <motion.div
            key="feedback"
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            className="space-y-2"
          >
            <div
              className="rounded-md p-3 text-sm"
              style={{
                background: fb.ok
                  ? "color-mix(in srgb, var(--success) 10%, var(--input-bg))"
                  : "color-mix(in srgb, var(--warning) 10%, var(--input-bg))",
                border: `1px solid ${fb.ok ? "var(--success)" : "var(--warning)"}`,
                color: "var(--text-primary)",
              }}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold">
                  {fb.ok ? "✓ Ключевые идеи раскрыты" : "⚠ Разверни ответ"}
                </span>
                {typeof fb.ai_score === "number" && (
                  <span
                    className="text-[11px] font-pixel uppercase tracking-wider tabular-nums"
                    style={{
                      color: fb.ai_score >= 80
                        ? "var(--success)"
                        : fb.ai_score >= 60
                        ? "var(--warning)"
                        : "var(--text-muted)",
                      letterSpacing: "0.12em",
                    }}
                    title={fb.ai_model ? `Оценка ${fb.ai_model}` : undefined}
                  >
                    AI {fb.ai_score}/100
                  </span>
                )}
              </div>

              {/* LLM feedback — replaces the 1-line hint when available. */}
              {fb.ai_feedback ? (
                <div className="text-xs leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                  {fb.ai_feedback}
                </div>
              ) : (
                fb.hint && (
                  <div className="text-xs leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                    <span className="font-medium">Эталон:</span> {fb.hint}
                  </div>
                )
              )}

              {/* Covered / missed lists from the LLM grader. */}
              {(fb.ai_covered?.length || fb.ai_missed?.length) ? (
                <div className="mt-1.5 space-y-1 text-[11px]">
                  {fb.ai_covered && fb.ai_covered.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {fb.ai_covered.map((p) => (
                        <span
                          key={`c-${p}`}
                          className="rounded px-1.5 py-0.5"
                          style={{
                            background: "color-mix(in srgb, var(--success) 15%, transparent)",
                            color: "var(--success)",
                          }}
                        >
                          ✓ {p}
                        </span>
                      ))}
                    </div>
                  )}
                  {fb.ai_missed && fb.ai_missed.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {fb.ai_missed.map((p) => (
                        <span
                          key={`m-${p}`}
                          className="rounded px-1.5 py-0.5"
                          style={{
                            background: "color-mix(in srgb, var(--warning) 15%, transparent)",
                            color: "var(--warning)",
                          }}
                        >
                          · {p}
                        </span>
                      ))}
                    </div>
                  )}
                  {fb.hint && (
                    <div
                      className="pt-1"
                      style={{ color: "var(--text-muted)" }}
                    >
                      <span className="font-medium">Эталон:</span> {fb.hint}
                    </div>
                  )}
                </div>
              ) : null}

              {fb.matched_keywords.length > 0 && (
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {fb.matched_keywords.map((kw) => (
                    <span
                      key={kw}
                      className="text-[11px] rounded px-1.5 py-0.5"
                      style={{
                        background: "color-mix(in srgb, var(--success) 15%, transparent)",
                        color: "var(--success)",
                      }}
                    >
                      {kw}
                    </span>
                  ))}
                </div>
              )}

              {/* 2026-04-20: collapsible "Почему так" — answers the #1 user
                  complaint ("эталон есть, обоснования нет"). Only shown if
                  the backend returned at least one of the why fields. */}
              {(fb.why_it_matters || fb.source_excerpt || fb.law_article) && (
                <div className="mt-2 pt-2 border-t" style={{ borderColor: "var(--border-color)" }}>
                  <button
                    type="button"
                    onClick={() =>
                      setState((prev) =>
                        prev.status === "running" ? { ...prev, whyOpen: !prev.whyOpen } : prev,
                      )
                    }
                    className="w-full flex items-center justify-between text-xs font-medium"
                    style={{ color: "var(--accent)" }}
                    aria-expanded={state.whyOpen}
                  >
                    <span>{state.whyOpen ? "▾" : "▸"} Почему так</span>
                    {fb.law_article && (
                      <span
                        className="text-[10px] rounded px-1.5 py-0.5"
                        style={{
                          background: "color-mix(in srgb, var(--accent) 12%, transparent)",
                          color: "var(--accent)",
                        }}
                      >
                        {fb.law_article}
                      </span>
                    )}
                  </button>
                  <AnimatePresence>
                    {state.whyOpen && (
                      <motion.div
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: "auto" }}
                        exit={{ opacity: 0, height: 0 }}
                        className="overflow-hidden"
                      >
                        <div
                          className="mt-1.5 text-xs leading-relaxed space-y-1.5"
                          style={{ color: "var(--text-secondary)" }}
                        >
                          {fb.why_it_matters && <p>{fb.why_it_matters}</p>}
                          {fb.source_excerpt && (
                            <blockquote
                              className="pl-2 italic"
                              style={{
                                borderLeft: "2px solid var(--accent)",
                                color: "var(--text-muted)",
                              }}
                            >
                              {fb.source_excerpt}
                            </blockquote>
                          )}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              )}
            </div>
            <button
              onClick={nextQuestion}
              className="w-full rounded-md py-2.5 text-sm font-bold uppercase tracking-wider"
              style={{ background: "var(--accent)", color: "white", letterSpacing: "0.06em" }}
            >
              {state.index + 1 < state.drill.questions.length ? "Далее →" : "Завершить"}
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
