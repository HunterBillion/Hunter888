"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  BookOpen,
  Send,
  CheckCircle2,
  XCircle,
  Lightbulb,
  Loader2,
  Zap,
} from "lucide-react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { AppIcon } from "@/components/ui/AppIcon";
import { useSound } from "@/hooks/useSound";
import { QuizThinkingIndicator } from "@/components/pvp/QuizThinkingIndicator";
import { QuizCaseIntro } from "@/components/pvp/QuizCaseIntro";
import { useKnowledgeStore, type QuizMessage } from "@/stores/useKnowledgeStore";
import { ReportAnswerButton } from "@/components/pvp/ReportAnswerButton";
import { QuestionReportButton } from "@/components/pvp/QuestionReportButton";
import { QuizHUD } from "@/components/pvp/QuizHUD";
import { QuizAnswerCard } from "@/components/pvp/QuizAnswerCard";
import { QuizVerdictOverlay } from "@/components/pvp/QuizVerdictOverlay";
import { QuizHistoryStrip } from "@/components/pvp/QuizHistoryStrip";
import { QuizResultsScreen } from "@/components/pvp/QuizResultsScreen";
import { PixelMascot } from "@/components/pvp/PixelMascot";
import type { MascotState } from "@/components/pvp/PixelMascotSprites";
import { categoryLabel } from "@/lib/categories";
import { ErrorBoundary } from "@/components/errors/ErrorBoundary";
import { PageAuthGate } from "@/components/layout/PageAuthGate";
import { logger } from "@/lib/logger";
import type { WSMessage } from "@/types";

/* ─── Quiz Session Page ──────────────────────────────────────────────────── */

export default function KnowledgeSessionPageWrapper() {
  return (
    <PageAuthGate>
      <ErrorBoundary>
        <KnowledgeSessionPage />
      </ErrorBoundary>
    </PageAuthGate>
  );
}

function KnowledgeSessionPage() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const sessionId = params.sessionId as string;

  // 2026-05-04: read mode from URL synchronously so the hint button (and
  // any other mode-gated UI) renders correctly on first paint, before
  // the WS `quiz.session_started` event arrives. Without this the store
  // defaults to "free_dialog" and a blitz user briefly sees the hint
  // button — clicking it produced a "Подсказки недоступны в блиц-режиме"
  // toast, which was the user-visible bug.
  const urlMode = useMemo(() => {
    const m = searchParams?.get("mode");
    return (m && typeof m === "string") ? m : null;
  }, [searchParams]);

  // PR-12 (2026-05-07): синхронно из URL понимаем что сессия запущена
  // в MC-формате (choices_format=1 в URL или blitz/rapid_blitz по mode).
  // Без этого на первом paint'е до первого WS-сообщения юзер видел
  // textarea для free-text — баг «просто поле вместо вариантов».
  const isMcByUrl = useMemo(() => {
    if (!searchParams) return false;
    if (searchParams.get("choices_format") === "1") return true;
    const m = searchParams.get("mode");
    return m === "blitz" || m === "rapid_blitz";
  }, [searchParams]);

  const store = useKnowledgeStore();
  const { playSound } = useSound();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const userExitedRef = useRef(false);

  // PR-12 (2026-05-07): pull the most-recent answerId from the store so
  // the panel-level «Сообщить о проблеме» button knows which row to flag.
  // Falls through every render — cheap, store.messages is a small array.
  const lastAnswerId = useMemo<string | undefined>(() => {
    const msgs = store.messages;
    for (let i = msgs.length - 1; i >= 0; i--) {
      if (msgs[i]?.answerId) return msgs[i].answerId;
    }
    return undefined;
  }, [store.messages]);

  // PR-12 + PR-13: mascot mood from recent feedback. PR-13 fix: `partial`
  // (yellow «почти») теперь даёт cheer (мягкий) — раньше падал в idle
  // и лев молчал когда юзер был «близко».
  const quizMascotState = useMemo<MascotState>(() => {
    const last = store.messages.filter(m => m.type === "feedback").slice(-1)[0];
    if (!last) return "idle";
    if (last.verdictLevel === "correct" || last.verdictLevel === "partial") return "cheer";
    if (last.verdictLevel === "wrong" || last.verdictLevel === "off_topic") return "sad";
    return "idle";
  }, [store.messages]);

  // PR-22 (Phase 2): latest verdict + dismiss tracking для VerdictOverlay.
  // Overlay показывается когда есть feedback с id'ом которого нет в
  // dismissedVerdicts. Auto-advance в блице через 2s clears + ставит next.
  const [dismissedVerdicts, setDismissedVerdicts] = useState<Set<string>>(new Set());
  const latestVerdict = useMemo(() => {
    const fbs = store.messages.filter((m) => m.type === "feedback");
    const last = fbs[fbs.length - 1];
    if (!last) return null;
    if (dismissedVerdicts.has(last.id)) return null;
    return last;
  }, [store.messages, dismissedVerdicts]);
  // Auto-dismiss верить когда currentQuestion инкрементировался
  // (новый вопрос пришёл от backend).
  const lastQuestionIdxRef = useRef(store.currentQuestion);
  useEffect(() => {
    if (store.currentQuestion !== lastQuestionIdxRef.current) {
      lastQuestionIdxRef.current = store.currentQuestion;
      // не вызываем setDismissedVerdicts — overlay сам исчезнет когда
      // приедет новый feedback. Если новый feedback не пришёл а вопрос
      // уже сменился — закрываем principle через id.
      if (latestVerdict) {
        setDismissedVerdicts((prev) => new Set(prev).add(latestVerdict.id));
      }
    }
  }, [store.currentQuestion, latestVerdict]);
  const dismissVerdict = useCallback(() => {
    if (latestVerdict) {
      setDismissedVerdicts((prev) => new Set(prev).add(latestVerdict.id));
    }
  }, [latestVerdict]);

  const [showResults, setShowResults] = useState(false);
  const [hintLoading, setHintLoading] = useState(false);
  // Pre-validation hint shown under input when answer is rejected.
  const [validationError, setValidationError] = useState<string | null>(null);
  // Whether the current question allows hints (from quiz.question payload).
  // 2026-05-04 hotfix: default seeded from URL mode synchronously so the
  // button doesn't flicker visible-for-1s in blitz before the first
  // WS message updates it. Backend payload still overrides per question.
  const isBlitzByUrl = urlMode === "blitz" || urlMode === "rapid_blitz";
  const [hintAvailable, setHintAvailable] = useState<boolean>(!isBlitzByUrl);
  // Tiered-hint state for the current question (resets on new question).
  // tier=null means "no hint used yet"; tiersRemaining=0 disables the button.
  const [hintTier, setHintTier] = useState<number | null>(null);
  const [hintTiersRemaining, setHintTiersRemaining] = useState<number | null>(null);

  // Initialize store.mode from URL on mount so blitz UI is correct
  // before the first WS message. The WS handler still re-inits when
  // `quiz.session_started` arrives — that's idempotent.
  useEffect(() => {
    if (urlMode && urlMode !== store.mode) {
      store.init(urlMode as typeof store.mode, store.category ?? undefined);
    }
    // Run once on mount (and whenever URL mode actually changes).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlMode]);

  // quiz_v2: narrative case briefing (2026-04-18)
  const [caseIntro, setCaseIntro] = useState<{
    caseId: string;
    complexity: "simple" | "tangled" | "adversarial";
    introText: string;
    totalQuestions: number;
    personality: "professor" | "detective" | "blitz";
    audioUrl?: string | null;
  } | null>(null);

  // #7 fix: Reset store when navigating to a different session to prevent stale state leak
  useEffect(() => {
    if (store.sessionId && store.sessionId !== sessionId) {
      store.reset();
    }
    store.setSessionId(sessionId);
    store.setStatus("connecting");
  }, [sessionId]); // eslint-disable-line react-hooks/exhaustive-deps -- store setters are stable Zustand actions

  // WebSocket message handler
  const handleMessage = useCallback(
    (msg: WSMessage) => {
      const data: Record<string, unknown> = { ...msg, ...(msg.data || {}) };
      const type = msg.type;

      switch (type) {
        case "session_started": {
          store.setStatus("active");
          if (data.mode) {
            store.init(data.mode as typeof store.mode, data.category as string | undefined);
            store.setSessionId(sessionId);
            store.setStatus("active");
          }
          if (typeof data.total_questions === "number") {
            store.updateProgress({
              correct: 0,
              incorrect: 0,
              skipped: 0,
              score: 0,
              current: 0,
              total: data.total_questions as number,
            });
          }
          // 2026-05-04: schema alignment — backend sends both names
          // depending on event (`time_limit_per_question` on
          // quiz.ready, `time_limit` on quiz.session_started + per
          // question). Accept either to remove drift between handlers.
          const tl = (typeof data.time_limit === "number"
            ? data.time_limit
            : typeof data.time_limit_per_question === "number"
              ? data.time_limit_per_question
              : null) as number | null;
          if (tl !== null && tl > 0) {
            store.setTimeLeft(tl);
          }
          break;
        }

        // V2: quiz.ready with personality data
        // quiz_v2: narrative case briefing (2026-04-18)
        case "case.intro": {
          const cx = (data.complexity === "simple" || data.complexity === "tangled" || data.complexity === "adversarial")
            ? data.complexity
            : "simple";
          const p = (data.personality === "detective" || data.personality === "professor" || data.personality === "blitz")
            ? data.personality
            : "professor";
          setCaseIntro({
            caseId: String(data.case_id ?? "C-???"),
            complexity: cx as "simple" | "tangled" | "adversarial",
            introText: String(data.intro_text ?? ""),
            totalQuestions: Number(data.total_questions ?? 10),
            personality: p as "professor" | "detective" | "blitz",
            audioUrl: typeof data.audio_url === "string" ? data.audio_url : null,
          });
          break;
        }
        // quiz_v2: TTS audio arrives async AFTER case.intro (backend synth takes 1-3s)
        case "case.intro.audio": {
          const audio = typeof data.audio_url === "string" ? data.audio_url : null;
          if (audio) {
            setCaseIntro((prev) => prev ? { ...prev, audioUrl: audio } : prev);
          }
          break;
        }

        case "quiz.ready": {
          store.setStatus("active");
          store.setSessionId(sessionId);
          if (typeof data.total_questions === "number") {
            store.updateProgress({
              correct: 0, incorrect: 0, skipped: 0, score: 0, current: 0,
              total: data.total_questions as number,
            });
          }
          if (typeof data.time_limit_per_question === "number") {
            store.setTimeLeft(data.time_limit_per_question as number);
          }
          // V2: Set AI personality
          const personality = data.ai_personality as Record<string, string> | undefined;
          if (personality) {
            store.setAiPersonality({
              name: personality.name,
              displayName: personality.display_name,
              avatarEmoji: personality.avatar_emoji,
              greeting: personality.greeting,
            });
            // Show greeting as system message
            store.addMessage({
              type: "system",
              content: personality.greeting,
              avatarEmoji: personality.avatar_emoji,
            });
          }
          break;
        }

        case "question":
        case "quiz.question": {
          const content = (data.content || data.text) as string;
          const currentPersonality = useKnowledgeStore.getState().aiPersonality;
          store.addMessage({
            type: "question",
            content,
            category: data.category as string | undefined,
            avatarEmoji: currentPersonality?.avatarEmoji,
          });
          store.setIsTyping(false);
          // V2: Update difficulty from server
          if (typeof data.current_difficulty === "number") {
            store.setCurrentDifficulty(data.current_difficulty as number);
          }
          // Clear pending follow-up
          store.setPendingFollowUp(null);
          // 2026-05-04: trust backend's hint_available flag per question,
          // not a hardcoded mode check on the client.
          if (typeof data.hint_available === "boolean") {
            setHintAvailable(data.hint_available);
          }
          // Clear stale validation error when a new question lands.
          setValidationError(null);
          // Reset tiered-hint counters for the new question.
          setHintTier(null);
          setHintTiersRemaining(null);
          // 2026-05-04: reset countdown on each question. Backend now
          // sends `time_limit` per question (not just on quiz.ready).
          // Without this the client timer ran down to 0 on q1 and
          // never restarted — that's the "таймер показывает 0" bug.
          if (typeof data.time_limit === "number" && data.time_limit > 0) {
            store.setTimeLeft(data.time_limit as number);
          }
          // PR-MC (2026-05-05): MC-format payload carries `choices: string[]`
          // and `format: "mc_3"`. Stash on store so the input row renders
          // 3 buttons instead of textarea. Reset on every new question so a
          // mixed-format session works (rare, but cheap to support).
          if (Array.isArray(data.choices) && data.choices.length >= 2) {
            store.setCurrentChoices(data.choices.map((c: unknown) => String(c)));
          } else {
            store.setCurrentChoices(null);
          }
          break;
        }

        // 2026-04-18 STREAMING: verdict arrives first (< 1-2s), UI shows ✓/✖ + sets up streaming bubble.
        case "quiz.feedback.verdict": {
          const correctAns = typeof data.correct_answer === "string" ? data.correct_answer : undefined;
          const articleRef = typeof data.article_reference === "string" ? data.article_reference : undefined;
          const isCorrect = Boolean(data.is_correct);
          // 2026-05-04 FRONT-3: 4-bucket verdict from backend
          const verdictLevel =
            typeof data.verdict_level === "string"
              ? (data.verdict_level as "correct" | "partial" | "off_topic" | "wrong")
              : isCorrect ? "correct" : "wrong";
          const llmScore = typeof data.llm_score === "number" ? data.llm_score : undefined;
          // PR-12 (2026-05-07): MC mode emits answer_id on the verdict
          // event itself, before chunks arrive. Pick it up here so the
          // «Пожаловаться» button is wired immediately.
          const answerId = typeof data.answer_id === "string" ? data.answer_id : undefined;
          store.setIsTyping(false);
          store.addMessage({
            type: "feedback",
            content: "",              // will be filled by chunk events
            isCorrect,
            verdictLevel,
            llmScore,
            correctAnswer: correctAns,
            articleRef,
            explanation: "",
            answerId,
          });
          if (isCorrect) {
            playSound("correct", 0.4);
          } else {
            playSound("incorrect", 0.3);
          }
          break;
        }
        // Streaming chunks — append to the last feedback message as tokens arrive.
        case "quiz.feedback.chunk": {
          const t = typeof data.text === "string" ? data.text : "";
          if (t) {
            store.appendToLastMessage(t);
          }
          break;
        }
        case "feedback":
        case "quiz.feedback": {
          // V2: Enhanced feedback with personality, streak, speed bonus
          const personalityComment = data.personality_comment as string | undefined;
          const speedBonus = data.speed_bonus as number | undefined;
          // PR-12 (2026-05-07): personalityComment больше НЕ склеивается
          // с explanation — рендерится отдельным italic-баблом в bubble
          // (см. render-блок ниже). Без этого на blitz/MC реакции
          // showman / professor сливались с объяснением и пользователь
          // не чувствовал персонажа.
          const feedbackContent = (data.explanation as string) || "";
          const currentPersonality2 = useKnowledgeStore.getState().aiPersonality;

          // SFX: correct/incorrect + streak milestone
          if (data.is_correct) {
            playSound("correct", 0.4);
            const streakVal = data.streak as number | undefined;
            if (streakVal && [3, 5, 7, 10].includes(streakVal)) {
              setTimeout(() => playSound("streak", 0.5), 300);
            }
          } else {
            playSound("incorrect", 0.3);
          }

          // 2026-05-04: dedup the verdict+final double-bubble. If the
          // streaming verdict arrived first (normal blitz path), it
          // already created an empty feedback bubble that chunks have
          // been filling. We finalize it in place rather than appending
          // a second bubble. Fall back to addMessage for clients that
          // never received a verdict (legacy/race).
          const verdictLevel =
            (typeof data.verdict_level === "string" ? data.verdict_level : null) as
              | "correct" | "partial" | "off_topic" | "wrong" | null;
          const llmScore = typeof data.llm_score === "number" ? data.llm_score : undefined;
          const patch = {
            type: "feedback" as const,
            content: feedbackContent,
            isCorrect: data.is_correct as boolean,
            verdictLevel: verdictLevel ?? (data.is_correct ? "correct" : "wrong"),
            llmScore,
            explanation: data.explanation as string | undefined,
            articleRef: (data.article_ref || data.article_reference) as string | undefined,
            correctAnswer: (data.correct_answer || data.correct_answer_summary) as string | undefined,
            personalityComment,
            speedBonus,
            avatarEmoji: currentPersonality2?.avatarEmoji,
            // PR-6: backend includes `answer_id` so the bubble can offer "Flag".
            answerId: typeof data.answer_id === "string" ? data.answer_id : undefined,
          };
          const finalized = store.finalizeLastFeedback(patch);
          if (!finalized) {
            store.addMessage(patch);
          }
          // V2: Update streak & difficulty
          if (typeof data.streak === "number") {
            store.setStreak(data.streak as number, (data.best_streak as number) ?? store.bestStreak);
          }
          if (typeof data.current_difficulty === "number") {
            store.setCurrentDifficulty(data.current_difficulty as number);
          }
          if (data.progress) {
            const p = data.progress as Record<string, number>;
            store.updateProgress({
              correct: p.correct ?? store.correct,
              incorrect: p.incorrect ?? store.incorrect,
              skipped: p.skipped ?? store.skipped,
              score: p.score ?? store.score,
              current: p.current ?? store.currentQuestion,
              total: p.total ?? store.totalQuestions,
            });
          }
          break;
        }

        // V2: Follow-up question from AI
        case "quiz.follow_up": {
          store.setPendingFollowUp(data.text as string);
          const currentPersonality3 = useKnowledgeStore.getState().aiPersonality;
          store.addMessage({
            type: "follow_up",
            content: data.text as string,
            avatarEmoji: currentPersonality3?.avatarEmoji,
          });
          break;
        }

        // V2: Progress update
        case "quiz.progress": {
          const p = data as Record<string, number>;
          store.updateProgress({
            correct: p.correct ?? store.correct,
            incorrect: p.incorrect ?? store.incorrect,
            skipped: p.skipped ?? store.skipped,
            score: p.score ?? store.score,
            current: p.current ?? store.currentQuestion,
            total: p.total ?? store.totalQuestions,
          });
          // 2026-05-04 FRONT-2: sync client timer with server-truth on
          // every progress event. Client setInterval keeps ticking
          // between events; this just corrects drift cheaply.
          if (typeof p.time_left_now === "number" && p.time_left_now >= 0) {
            store.setTimeLeft(p.time_left_now);
          }
          break;
        }

        // V2: Soft limit warning
        case "quiz.soft_limit": {
          store.addMessage({
            type: "system",
            content: data.text as string,
          });
          break;
        }

        case "hint":
        case "quiz.hint": {
          // 2026-05-04: tiered hint payload — show tier label inline so
          // the user understands what level of reveal they got and how
          // many more they can request.
          const hintText = (data.content || data.text) as string;
          const tier = typeof data.tier === "number" ? (data.tier as number) : null;
          const tiersRemaining = typeof data.tiers_remaining === "number"
            ? (data.tiers_remaining as number)
            : null;
          const cumPenalty = typeof data.cumulative_penalty === "number"
            ? (data.cumulative_penalty as number)
            : null;
          const header = tier
            ? `▸ ПОДСКАЗКА ${tier}/3${cumPenalty !== null ? `  (${cumPenalty} pt)` : ""}`
            : "▸ ПОДСКАЗКА";
          store.addMessage({
            type: "hint",
            content: `${header}\n${hintText}`,
          });
          setHintTier(tier ?? null);
          setHintTiersRemaining(tiersRemaining ?? null);
          setHintLoading(false);
          break;
        }

        case "system":
        case "quiz.system_message": {
          store.addMessage({
            type: "system",
            content: (data.content || data.text) as string,
          });
          break;
        }

        case "typing": {
          store.setIsTyping(true);
          break;
        }

        case "timer_sync":
        case "quiz.timeout": {
          if (typeof data.time_left === "number") {
            store.setTimeLeft(data.time_left as number);
          }
          break;
        }

        case "session_completed":
        case "quiz.completed": {
          if (userExitedRef.current) break;
          store.setResults(data.results as Record<string, unknown>);
          store.setStatus("completed");
          setShowResults(true);
          if (timerRef.current) {
            clearInterval(timerRef.current);
            timerRef.current = null;
          }
          // SFX: victory or defeat based on score
          const resultScore = ((data.results as Record<string, unknown>)?.score as number) ?? 0;
          playSound(resultScore >= 50 ? "victory" : "defeat", 0.5);
          break;
        }

        case "error": {
          store.addMessage({
            type: "system",
            content: `Ошибка: ${data.message || "Неизвестная ошибка"}`,
          });
          break;
        }

        case "quiz.moderation": {
          // Server stripped the input as profanity / jailbreak. Question stays
          // active — show the coach line and let the user retype without
          // burning an attempt.
          store.addMessage({
            type: "system",
            content: (data.message as string) || "Сформулируйте ответ заново.",
          });
          store.setIsTyping(false);
          break;
        }

        default:
          logger.warn("[Knowledge WS] Unknown message type:", type);
      }
    },
    [sessionId], // eslint-disable-line react-hooks/exhaustive-deps -- store actions are stable Zustand refs
  );

  // WebSocket connection
  const { sendMessage, isConnected, connectionState } = useWebSocket({
    path: `/ws/knowledge`,
    onMessage: handleMessage,
    autoConnect: true,
  });

  // Send quiz.start when WS connects and status is still "connecting"
  useEffect(() => {
    if (isConnected && store.status === "connecting") {
      // Retrieve mode/category from URL search params or store
      const params = new URLSearchParams(window.location.search);
      const mode = params.get("mode") || store.mode || "free_dialog";
      const category = params.get("category") || store.category || undefined;
      const personality = params.get("personality") || undefined;
      // PR-MC hotfix (2026-05-06): forward `choices_format` into the WS
      // start payload. The previous PR plumbed it only through the REST
      // POST /knowledge/sessions, but the WS handler reads its config
      // from quiz.start.data (REST creates a DB row, the WS handler
      // creates the in-memory _SoloQuizState). Without this line every
      // session fell back to free-text — chunks_with_choices stayed
      // 0/383 in prod and zero MC events fired.
      const choicesFormat = params.get("choices_format") === "1"
        || params.get("format") === "mc_3";
      sendMessage({
        type: "quiz.start",
        data: {
          mode,
          category,
          ai_personality: personality,
          choices_format: choicesFormat,
        },
      });
    }
  }, [isConnected, store.status, sendMessage]); // eslint-disable-line react-hooks/exhaustive-deps

  // Timer for blitz mode
  // Extract boolean so we don't put a raw expression in the deps array
  // (which React can't track) and don't use the numeric timeLeft value
  // (which would restart the interval every second).
  const hasTimeLeft = store.timeLeft !== null;
  useEffect(() => {
    if (store.mode === "blitz" && hasTimeLeft && store.status === "active") {
      timerRef.current = setInterval(() => {
        store.tickTimer();
      }, 1000);
      return () => {
        if (timerRef.current) {
          clearInterval(timerRef.current);
          timerRef.current = null;
        }
      };
    }
    // store.tickTimer is a stable Zustand action — safe to omit.
  }, [store.mode, store.status, hasTimeLeft]); // eslint-disable-line react-hooks/exhaustive-deps -- store.tickTimer is a stable Zustand action (documented above)

  // SFX: tick sound for last 10 seconds in blitz
  useEffect(() => {
    if (store.mode === "blitz" && store.timeLeft !== null && store.timeLeft <= 10 && store.timeLeft > 0) {
      playSound("tick", 0.2);
    }
  }, [store.mode, store.timeLeft, playSound]);

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [store.messages.length, store.isTyping]);

  // 2026-05-04: textarea auto-resize. The fixed 120px maxHeight from
  // before truncated long structured answers (statute citations,
  // multi-paragraph reasoning), forcing the user to scroll inside the
  // input. Now grows up to ~10 lines, then scrolls inside the box.
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    const cap = 240; // ~10 lines @ 14px line-height
    el.style.height = `${Math.min(cap, el.scrollHeight)}px`;
  }, [store.input]);

  // #6 fix: Sanitize user input — strip control chars, cap length
  const MAX_ANSWER_LENGTH = 2000;
  const MIN_ANSWER_LENGTH = 3;
  const sanitizeInput = (raw: string): string => {
    // Remove zero-width and control characters (keep newlines/tabs)
    // eslint-disable-next-line no-control-regex
    return raw.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F\u200B-\u200F\uFEFF]/g, "").slice(0, MAX_ANSWER_LENGTH);
  };

  // 2026-05-04: client-side pre-validation. Stops mash-typed garbage like
  // "\u0440\u0430"/"\u043E\u0432"/"\u043E\u0430" from being sent to the WS where it costs an LLM
  // evaluation and gets scored as "\u0441\u043B\u0438\u0448\u043A\u043E\u043C \u043A\u043E\u0440\u043E\u0442\u043A\u0438\u0439 \u043E\u0442\u0432\u0435\u0442". Strict by
  // user request: option (\u0430) \u2014 min 3 non-whitespace chars, no semantic
  // requirement (no digit/keyword check). Returns null if valid, or a
  // user-facing message explaining the rejection.
  const validateAnswer = (text: string): string | null => {
    const stripped = text.replace(/\s+/g, "");
    if (stripped.length < MIN_ANSWER_LENGTH) {
      return `\u041E\u0442\u0432\u0435\u0442 \u0441\u043B\u0438\u0448\u043A\u043E\u043C \u043A\u043E\u0440\u043E\u0442\u043A\u0438\u0439 \u2014 \u043C\u0438\u043D\u0438\u043C\u0443\u043C ${MIN_ANSWER_LENGTH} \u0441\u0438\u043C\u0432\u043E\u043B\u0430.`;
    }
    return null;
  };

  // Send answer
  const handleSend = useCallback(() => {
    const text = sanitizeInput(store.input.trim());
    if (!text || store.status !== "active") return;

    const reason = validateAnswer(text);
    if (reason) {
      setValidationError(reason);
      // Don't clear input \u2014 let the user fix it.
      inputRef.current?.focus();
      return;
    }
    setValidationError(null);

    store.addMessage({ type: "answer", content: text });
    sendMessage({ type: "answer", content: text });
    store.setInput("");
    store.setIsTyping(true);

    // Focus back on input
    setTimeout(() => inputRef.current?.focus(), 50);
  }, [store.input, store.status, sendMessage]); // eslint-disable-line react-hooks/exhaustive-deps -- store setters are stable Zustand actions

  // PR-MC (2026-05-05): one-shot click handler for the 3-button MC layout.
  // Sends `{type:"answer", choice_index}` instead of free text and stashes
  // the picked index so the UI can highlight ✓/✗ on the chosen button
  // when the verdict comes back.
  const handleChoicePick = useCallback((idx: number) => {
    if (store.status !== "active") return;
    if (store.pickedChoiceIndex !== null) return; // already locked-in
    const choices = store.currentChoices;
    if (!choices || idx < 0 || idx >= choices.length) return;
    store.setPickedChoiceIndex(idx);
    store.addMessage({ type: "answer", content: choices[idx] });
    sendMessage({ type: "answer", choice_index: idx });
    store.setIsTyping(true);
  }, [store, sendMessage]);

  // PR-20 (2026-05-08): Arcade-Stage редизайн — extract exit handler
  // и добавляем keyboard shortcuts A-E для выбора ответа.
  const handleExit = useCallback(() => {
    userExitedRef.current = true;
    try {
      if (store.status === "active") sendMessage({ type: "quiz.end" });
    } catch { /* WS may be down */ }
    store.reset();
    router.push("/pvp");
  }, [store, sendMessage, router]);

  useEffect(() => {
    if (store.status !== "active") return;
    if (store.pickedChoiceIndex !== null) return;
    const choices = store.currentChoices;
    if (!choices || choices.length < 2) return;
    const onKey = (e: KeyboardEvent) => {
      // ignore if user is typing in an input/textarea
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      const code = e.key.toUpperCase();
      if (code.length !== 1) return;
      const idx = code.charCodeAt(0) - 65;  // A→0, B→1, ...
      if (idx >= 0 && idx < choices.length) {
        e.preventDefault();
        handleChoicePick(idx);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [store.status, store.pickedChoiceIndex, store.currentChoices, handleChoicePick]);

  // Request hint
  const handleHint = useCallback(() => {
    if (hintLoading) return;
    setHintLoading(true);
    sendMessage({ type: "hint_request" });
  }, [hintLoading, sendMessage]);

  // Keyboard submit
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // PR-20: formatTime + progressPct переехали в QuizHUD; сюда не нужны.

  // ─── Results Screen ────────────────────────────────
  if (showResults || store.status === "completed") {
    const results = store.results || {};
    const durationSeconds =
      typeof results.duration_seconds === "number"
        ? results.duration_seconds
        : 0;
    return (
      <div className="flex min-h-screen flex-col" style={{ background: "var(--bg-primary)" }}>
        <QuizResultsScreen
          mode={store.mode}
          category={store.category}
          score={store.score}
          correct={store.correct}
          incorrect={store.incorrect}
          bestStreak={store.bestStreak ?? 0}
          totalQuestions={store.totalQuestions || (store.correct + store.incorrect)}
          durationSeconds={durationSeconds}
          results={results}
          messages={store.messages}
          onPlayAgain={() => {
            const m = store.mode;
            const c = store.category ?? undefined;
            store.reset();
            store.init(m, c);
            router.push("/pvp");
          }}
          onBackToArena={() => {
            store.reset();
            router.push("/pvp");
          }}
        />
      </div>
    );
  }

  // ─── Chat Interface ────────────────────────────────
  return (
    <div
      className="flex h-screen flex-col relative"
      style={{
        background: "var(--bg-primary)",
        // PR-20 polish: smoother ambient gradient + subtle grid (вместо
        // жёсткой 23px-сетки). Sub-pixel смотрится тоньше на ретине.
        backgroundImage: `
          radial-gradient(ellipse 80% 60% at 50% 0%, var(--accent-muted) 0%, transparent 55%),
          radial-gradient(ellipse 60% 50% at 80% 100%, rgba(217,70,239,0.06) 0%, transparent 60%),
          repeating-linear-gradient(0deg, transparent 0, transparent 31px, rgba(107,77,199,0.025) 31px, rgba(107,77,199,0.025) 32px),
          repeating-linear-gradient(90deg, transparent 0, transparent 31px, rgba(107,77,199,0.025) 31px, rgba(107,77,199,0.025) 32px)
        `,
        // Анти-алиасинг шрифтов на всю страницу — глаз ловит разницу.
        WebkitFontSmoothing: "antialiased",
        MozOsxFontSmoothing: "grayscale",
        textRendering: "optimizeLegibility",
      } as React.CSSProperties}
    >
      {/* quiz_v2: case briefing overlay — pops in when backend emits case.intro */}
      {caseIntro && (
        <QuizCaseIntro
          caseId={caseIntro.caseId}
          complexity={caseIntro.complexity}
          introText={caseIntro.introText}
          totalQuestions={caseIntro.totalQuestions}
          personality={caseIntro.personality}
          audioUrl={caseIntro.audioUrl}
          onAccept={() => setCaseIntro(null)}
        />
      )}

      {/* PR-20 (2026-05-08): Arcade-Stage HUD заменил pixel-arcade top bar.
          Стиль скопирован с /pvp/leaderboard: glass-card + blur(20px) +
          soft tier-tints + 3-tier typography (font-display / font-mono /
          sans). Таймер-циферблат circular SVG с 3 фазами цвета. */}
      <QuizHUD
        mode={store.mode}
        category={store.category}
        currentQuestion={store.currentQuestion}
        totalQuestions={store.totalQuestions}
        correct={store.correct}
        incorrect={store.incorrect}
        bestStreak={store.bestStreak ?? 0}
        timeLeft={store.timeLeft}
        onExit={handleExit}
      />

      {/* ═══ Main Content: 2-column MC layout OR single-column free-text ═══
           PR-12 (2026-05-07): когда URL пометил MC-режим (?choices_format=1
           или mode=blitz), сразу рендерим 2-колоночный layout — даже до
           прихода первого quiz.question, со скелетоном вариантов. Иначе
           юзер видел вспышку textarea на первом paint'е. */}
      {(store.currentChoices && store.currentChoices.length >= 2) || isMcByUrl ? (
        <div className="flex-1 flex flex-col lg:flex-row overflow-hidden">
          {/* ── LEFT: MC Choices Panel (1/3) ── PR-20: glass-arena style. */}
          <aside
            className="order-2 lg:order-1 shrink-0 lg:w-[36%] overflow-y-auto"
            style={{
              background: "var(--bg-primary)",
              borderRight: "1px solid var(--glass-border, rgba(255,255,255,0.08))",
            }}
          >
            <div className="flex flex-col h-full p-4 lg:p-5">
              <div
                className="font-display font-bold uppercase tracking-widest mb-4 px-3 py-2 text-center rounded-xl"
                style={{
                  color: "var(--accent)",
                  fontSize: 13,
                  letterSpacing: "0.18em",
                  background: "var(--glass-bg, rgba(255,255,255,0.04))",
                  border: "1px solid color-mix(in srgb, var(--accent) 28%, transparent)",
                  backdropFilter: "blur(20px)",
                  WebkitBackdropFilter: "blur(20px)",
                  textShadow: "0 0 12px var(--accent-glow)",
                }}
              >
                ▸ ВЫБЕРИТЕ ОТВЕТ
              </div>

              <div className="flex flex-col gap-3 flex-1">
                {/* Pre-question skeleton (glass) — иначе layout схлопывается. */}
                {(!store.currentChoices || store.currentChoices.length < 2) && (
                  <>
                    {[0, 1, 2, 3, 4].map((i) => (
                      <div
                        key={`skeleton-${i}`}
                        className="animate-pulse rounded-xl"
                        style={{
                          height: 64,
                          background: "var(--glass-bg, rgba(255,255,255,0.04))",
                          border: "1px solid var(--glass-border, rgba(255,255,255,0.08))",
                          backdropFilter: "blur(20px)",
                          opacity: 0.5,
                        }}
                      />
                    ))}
                    <div
                      className="font-mono text-center text-[12px] mt-2 tracking-wider"
                      style={{ color: "var(--text-muted)", letterSpacing: "0.12em" }}
                    >
                      Загружаем варианты…
                    </div>
                  </>
                )}
                {(store.currentChoices ?? []).map((choiceText, idx) => (
                  <QuizAnswerCard
                    key={idx}
                    index={idx}
                    text={choiceText}
                    picked={store.pickedChoiceIndex === idx}
                    locked={store.pickedChoiceIndex !== null}
                    disabled={store.status !== "active"}
                    onPick={handleChoicePick}
                  />
                ))}
              </div>

              {/* Hint button at bottom of choices panel */}
              {hintAvailable && (
                <motion.button
                  onClick={handleHint}
                  disabled={
                    hintLoading ||
                    store.status !== "active" ||
                    (hintTiersRemaining !== null && hintTiersRemaining <= 0)
                  }
                  whileHover={{ y: -2 }}
                  whileTap={{ scale: 0.97 }}
                  className="mt-4 flex w-full items-center justify-center gap-2 py-3 px-3 rounded-xl disabled:opacity-40"
                  style={{
                    background: "rgba(245,158,11,0.1)",
                    border: "1px solid rgba(245,158,11,0.4)",
                    color: "var(--warning)",
                    backdropFilter: "blur(20px)",
                    boxShadow: "0 4px 16px rgba(245,158,11,0.16)",
                    transition: "border-color 160ms, box-shadow 200ms",
                  }}
                  title={
                    hintTier !== null
                      ? `Подсказка ${hintTier}/3 · ещё ${hintTiersRemaining ?? 0}`
                      : "Подсказка (3 уровня, штраф растёт)"
                  }
                  aria-label="Подсказка"
                >
                  {hintLoading ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : (
                    <>
                      <Lightbulb size={16} />
                      <span className="font-display font-bold text-[12px] uppercase tracking-widest">
                        {hintTier !== null ? `Подсказка ${hintTier}/3` : "Подсказка"}
                      </span>
                    </>
                  )}
                </motion.button>
              )}

              {/* PR-12 (2026-05-07): «Сообщить о проблеме» — продублированный
                  вход для жалобы на ответ AI прямо в панели вариантов.
                  Раньше кнопка жила только в verdict-bubble в чате (PR-6),
                  но если AI принял ответ неправильно (или сам вопрос
                  кривой), пользователю удобнее жаловаться прямо отсюда.
                  Привязывается к last answer'у с answerId. Если ответа
                  ещё не было — disabled с tooltip'ом. */}
              <QuestionReportButton lastAnswerId={lastAnswerId} />

              {/* PR-22 (Phase 2): HistoryStrip — компактные ✓/✗ за все
                  отвеченные вопросы с tooltip-preview на hover. */}
              {(store.totalQuestions > 0 || store.messages.some((m) => m.type === "feedback")) && (
                <div className="mt-4">
                  <QuizHistoryStrip
                    messages={store.messages}
                    totalQuestions={store.totalQuestions}
                    variant="compact"
                  />
                </div>
              )}

              {/* PR-22 (Phase 2): reactive scale — на cheer лев растёт до
                  1.15 spring, на sad сжимается 0.92 + shake. Лёгкий, но
                  заметный feedback для каждого вердикта. */}
              <div className="mt-4 flex justify-center">
                <motion.div
                  key={quizMascotState}
                  animate={
                    quizMascotState === "cheer" ? { scale: [1, 1.18, 1.08] }
                    : quizMascotState === "sad" ? { scale: [1, 0.92, 0.96], rotate: [-3, 3, -2, 0] }
                    : { scale: 1 }
                  }
                  transition={
                    quizMascotState === "cheer"
                      ? { duration: 0.5, type: "spring", stiffness: 280, damping: 16 }
                      : { duration: 0.6 }
                  }
                  className="rounded-2xl flex items-center justify-center"
                  style={{
                    padding: 8,
                    background: "linear-gradient(135deg, rgba(255,255,255,0.06) 0%, rgba(255,255,255,0.02) 100%)",
                    border: "1px solid var(--glass-border, rgba(255,255,255,0.08))",
                    boxShadow:
                      quizMascotState === "cheer"
                        ? "0 0 24px color-mix(in srgb, var(--success) 40%, transparent), inset 0 1px 0 rgba(255,255,255,0.06)"
                        : quizMascotState === "sad"
                          ? "0 0 24px color-mix(in srgb, var(--danger) 40%, transparent), inset 0 1px 0 rgba(255,255,255,0.06)"
                          : "0 4px 16px rgba(0,0,0,0.2), inset 0 1px 0 rgba(255,255,255,0.06)",
                    backdropFilter: "blur(20px)",
                    transition: "box-shadow 320ms",
                  }}
                >
                  <PixelMascot
                    state={quizMascotState}
                    size={72}
                    background="transparent"
                    ariaLabel="Квиз-маскот"
                  />
                </motion.div>
              </div>

            </div>
          </aside>

          {/* ── RIGHT: Chat Area (2/3) ── */}
          <div
            className="order-1 lg:order-2 flex-1 overflow-y-auto relative"
            style={{
              backgroundImage: `
                radial-gradient(ellipse at 50% 20%, rgba(107,77,199,0.12) 0%, transparent 55%),
                repeating-linear-gradient(0deg, transparent 0, transparent 31px, rgba(107,77,199,0.06) 31px, rgba(107,77,199,0.06) 32px),
                repeating-linear-gradient(90deg, transparent 0, transparent 31px, rgba(107,77,199,0.06) 31px, rgba(107,77,199,0.06) 32px)
              `,
            }}
          >
            <div className="px-4 py-6 space-y-4 relative">
              {/* PR-22 (Phase 2): VerdictOverlay sticky-top — большая
                  карточка вердикта с particle-burst, авто-адванс в блице. */}
              {latestVerdict && (
                <div className="sticky top-2 z-30">
                  <QuizVerdictOverlay
                    verdict={latestVerdict}
                    autoAdvance={store.mode === "blitz" || urlMode === "rapid_blitz"}
                    autoAdvanceMs={2200}
                    onDismiss={dismissVerdict}
                  />
                </div>
              )}

              {connectionState !== "connected" && (
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  className="rounded-2xl px-5 py-6 flex items-center justify-center gap-3"
                  style={{
                    background: connectionState === "error"
                      ? "linear-gradient(135deg, rgba(239,68,68,0.12) 0%, rgba(255,255,255,0.02) 100%)"
                      : "linear-gradient(135deg, color-mix(in srgb, var(--accent) 10%, rgba(255,255,255,0.04)) 0%, rgba(255,255,255,0.02) 100%)",
                    border: connectionState === "error"
                      ? "1px solid rgba(239,68,68,0.4)"
                      : "1px solid color-mix(in srgb, var(--accent) 32%, transparent)",
                    boxShadow: connectionState === "error"
                      ? "0 6px 20px rgba(239,68,68,0.18), inset 0 1px 0 rgba(255,255,255,0.04)"
                      : "0 6px 20px color-mix(in srgb, var(--accent) 18%, transparent), inset 0 1px 0 rgba(255,255,255,0.04)",
                    backdropFilter: "blur(20px) saturate(1.2)",
                  }}
                >
                  <motion.span
                    className="flex items-center justify-center rounded-full"
                    style={{
                      width: 28,
                      height: 28,
                      background: connectionState === "error" ? "rgba(239,68,68,0.18)" : "color-mix(in srgb, var(--accent) 22%, transparent)",
                      border: `1px solid ${connectionState === "error" ? "rgba(239,68,68,0.5)" : "color-mix(in srgb, var(--accent) 50%, transparent)"}`,
                    }}
                  >
                    <Loader2
                      size={14}
                      className="animate-spin"
                      style={{ color: connectionState === "error" ? "var(--danger)" : "var(--accent)" }}
                    />
                  </motion.span>
                  <span
                    className="font-display font-bold uppercase"
                    style={{
                      color: connectionState === "error" ? "var(--danger)" : "var(--accent)",
                      fontSize: 13,
                      letterSpacing: "0.16em",
                    }}
                  >
                    {connectionState === "connecting"
                      ? "Подключение к арене…"
                      : connectionState === "reconnecting"
                        ? "Переподключаемся…"
                        : "Ошибка соединения"}
                  </span>
                </motion.div>
              )}

              {store.messages.map((msg) => (
                <MessageBubble key={msg.id} message={msg} />
              ))}

              <AnimatePresence>
                {store.isTyping && <QuizThinkingIndicator />}
              </AnimatePresence>

              <div ref={messagesEndRef} />
            </div>
          </div>
        </div>
      ) : (
        /* ═══ Single-column free-text layout ═══ */
        <>
          <div
            className="flex-1 overflow-y-auto relative"
            style={{
              backgroundImage: `
                radial-gradient(ellipse at 50% 20%, rgba(107,77,199,0.12) 0%, transparent 55%),
                repeating-linear-gradient(0deg, transparent 0, transparent 31px, rgba(107,77,199,0.06) 31px, rgba(107,77,199,0.06) 32px),
                repeating-linear-gradient(90deg, transparent 0, transparent 31px, rgba(107,77,199,0.06) 31px, rgba(107,77,199,0.06) 32px)
              `,
            }}
          >
            <div className="mx-auto max-w-3xl px-4 py-6 space-y-4 relative">
              {connectionState !== "connected" && (
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  className="rounded-2xl px-5 py-6 flex items-center justify-center gap-3"
                  style={{
                    background: connectionState === "error"
                      ? "linear-gradient(135deg, rgba(239,68,68,0.12) 0%, rgba(255,255,255,0.02) 100%)"
                      : "linear-gradient(135deg, color-mix(in srgb, var(--accent) 10%, rgba(255,255,255,0.04)) 0%, rgba(255,255,255,0.02) 100%)",
                    border: connectionState === "error"
                      ? "1px solid rgba(239,68,68,0.4)"
                      : "1px solid color-mix(in srgb, var(--accent) 32%, transparent)",
                    boxShadow: connectionState === "error"
                      ? "0 6px 20px rgba(239,68,68,0.18), inset 0 1px 0 rgba(255,255,255,0.04)"
                      : "0 6px 20px color-mix(in srgb, var(--accent) 18%, transparent), inset 0 1px 0 rgba(255,255,255,0.04)",
                    backdropFilter: "blur(20px) saturate(1.2)",
                  }}
                >
                  <motion.span
                    className="flex items-center justify-center rounded-full"
                    style={{
                      width: 28,
                      height: 28,
                      background: connectionState === "error" ? "rgba(239,68,68,0.18)" : "color-mix(in srgb, var(--accent) 22%, transparent)",
                      border: `1px solid ${connectionState === "error" ? "rgba(239,68,68,0.5)" : "color-mix(in srgb, var(--accent) 50%, transparent)"}`,
                    }}
                  >
                    <Loader2
                      size={14}
                      className="animate-spin"
                      style={{ color: connectionState === "error" ? "var(--danger)" : "var(--accent)" }}
                    />
                  </motion.span>
                  <span
                    className="font-display font-bold uppercase"
                    style={{
                      color: connectionState === "error" ? "var(--danger)" : "var(--accent)",
                      fontSize: 13,
                      letterSpacing: "0.16em",
                    }}
                  >
                    {connectionState === "connecting"
                      ? "Подключение к арене…"
                      : connectionState === "reconnecting"
                        ? "Переподключаемся…"
                        : "Ошибка соединения"}
                  </span>
                </motion.div>
              )}

              {store.messages.map((msg) => (
                <MessageBubble key={msg.id} message={msg} />
              ))}

              <AnimatePresence>
                {store.isTyping && <QuizThinkingIndicator />}
              </AnimatePresence>

              <div ref={messagesEndRef} />
            </div>
          </div>

          {/* Follow-up bar */}
          {store.pendingFollowUp && (
            <div
              className="shrink-0 border-t px-4 py-3"
              style={{ borderColor: "var(--accent-muted)", background: "var(--accent-muted)" }}
            >
              <div className="mx-auto flex max-w-3xl items-center justify-between">
                <span className="text-sm" style={{ color: "var(--text-muted)" }}>
                  Уточняющий вопрос — ответьте или пропустите
                </span>
                <div className="flex gap-2">
                  <button
                    className="rounded-lg px-3 py-1.5 text-sm font-medium transition-colors"
                    style={{ background: "var(--accent-muted)", color: "var(--accent)" }}
                    onClick={() => store.setPendingFollowUp(null)}
                  >
                    Ответить
                  </button>
                  <button
                    className="rounded-lg px-3 py-1.5 text-sm font-medium transition-colors"
                    style={{ background: "rgba(255,255,255,0.06)", color: "var(--text-muted)" }}
                    onClick={() => {
                      store.setPendingFollowUp(null);
                      sendMessage({ type: "quiz.follow_up_response", data: { action: "skip" } });
                    }}
                  >
                    Пропустить
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* PR-13 (2026-05-07): Report button + lion ABOVE the free-text
              input bar. Раньше эти элементы жили только в MC-aside и
              free-text юзеры (themed/free_dialog) их не видели. */}
          <div
            className="shrink-0 flex items-center justify-between gap-3 px-4 py-2"
            style={{
              background: "color-mix(in srgb, var(--accent) 4%, var(--bg-primary))",
              borderTop: "1px dashed var(--border-color)",
            }}
          >
            <div className="flex-1 max-w-[280px]">
              <QuestionReportButton lastAnswerId={lastAnswerId} />
            </div>
            <div className="shrink-0">
              <PixelMascot
                state={quizMascotState}
                size={48}
                bordered
                frameColor="var(--accent)"
                background="var(--bg-panel)"
                ariaLabel="Квиз-маскот"
              />
            </div>
          </div>

          {/* Free-text input bar: hint + textarea + send */}
          <div
            className="shrink-0 relative"
            style={{
              borderTop: "2px solid var(--accent)",
              background: "var(--bg-primary)",
              boxShadow: "0 -2px 0 0 rgba(0,0,0,0.15)",
              zIndex: 10,
              padding: "14px 12px",
            }}
          >
            <div className="mx-auto flex max-w-3xl items-end gap-3">
              {hintAvailable && (
                <motion.button
                  onClick={handleHint}
                  disabled={
                    hintLoading ||
                    store.status !== "active" ||
                    (hintTiersRemaining !== null && hintTiersRemaining <= 0)
                  }
                  whileHover={{ y: -1 }}
                  whileTap={{ y: 2 }}
                  className="relative flex h-11 min-w-11 shrink-0 items-center justify-center gap-1 px-2 disabled:opacity-40"
                  style={{
                    background: "rgba(245,158,11,0.12)",
                    border: "2px solid var(--warning)",
                    borderRadius: 0,
                    color: "var(--warning)",
                    boxShadow: "2px 2px 0 0 var(--warning)",
                    transition: "box-shadow 120ms, transform 120ms",
                  }}
                  title={
                    hintTier !== null
                      ? `Подсказка ${hintTier}/3 · ещё ${hintTiersRemaining ?? 0}`
                      : "Подсказка (3 уровня, штраф растёт)"
                  }
                  aria-label="Подсказка"
                >
                  {hintLoading ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : (
                    <>
                      <Lightbulb size={16} />
                      {hintTier !== null && (
                        <span className="font-pixel text-[10px] leading-none">{hintTier}/3</span>
                      )}
                    </>
                  )}
                </motion.button>
              )}

              <div
                className="flex flex-1 items-end relative min-w-0"
                style={{
                  background: "var(--input-bg)",
                  border: "2px solid var(--accent)",
                  borderRadius: 0,
                  boxShadow: "2px 2px 0 0 var(--accent-muted)",
                  minHeight: 44,
                }}
              >
                <textarea
                  ref={inputRef}
                  value={store.input}
                  onChange={(e) => {
                    store.setInput(e.target.value);
                    if (validationError) setValidationError(null);
                  }}
                  onKeyDown={handleKeyDown}
                  placeholder="▸ ВВЕДИТЕ ОТВЕТ"
                  rows={1}
                  className="flex-1 resize-none bg-transparent px-3 py-2.5 text-sm outline-none placeholder:opacity-50"
                  style={{
                    color: "var(--text-primary)",
                    maxHeight: "240px",
                    overflowY: "auto",
                    fontFamily: "var(--font-mono, monospace)",
                  }}
                  disabled={store.status !== "active"}
                />
              </div>

              <motion.button
                onClick={handleSend}
                disabled={!store.input.trim() || store.status !== "active"}
                whileHover={{ y: -1 }}
                whileTap={{ y: 2 }}
                className="flex h-11 shrink-0 items-center justify-center gap-1.5 px-3 sm:px-4 disabled:opacity-40 font-pixel text-sm uppercase tracking-widest"
                style={{
                  background: "var(--accent)",
                  border: "2px solid var(--accent)",
                  borderRadius: 0,
                  color: "#fff",
                  boxShadow: "2px 2px 0 0 #000",
                  transition: "box-shadow 120ms, transform 120ms",
                }}
                aria-label="Отправить"
              >
                <Send size={14} />
                <span className="hidden sm:inline">SEND</span>
              </motion.button>
            </div>
            {validationError && (
              <div
                className="mx-auto mt-2 max-w-3xl px-1 text-xs"
                style={{ color: "var(--danger, #ef4444)" }}
              >
                ▸ {validationError}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

/* ─── Message Bubble Component ────────────────────────────────────────────── */

function MessageBubble({ message }: { message: QuizMessage }) {
  const isUser = message.type === "answer";
  const isSystem = message.type === "system";
  const isFeedback = message.type === "feedback";
  const isHint = message.type === "hint";
  const isQuestion = message.type === "question";
  const isFollowUp = message.type === "follow_up";

  // V2: Avatar emoji from personality
  const avatarEmoji = message.avatarEmoji;

  // System messages.
  // PR-13 (2026-05-07): personality.greeting приходит сюда с
  // `avatarEmoji = personality.avatar_emoji`. Раньше system-bubble его
  // игнорировал → персонаж терял лицо на ВАЖНЕЙШЕМ экране (старт сессии).
  // Теперь если есть emoji — рисуем его слева крупно + content справа,
  // иначе — старый минималистичный pixel-pill.
  if (isSystem) {
    if (avatarEmoji && message.content && message.content.length > 0) {
      return (
        <motion.div
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex justify-center"
        >
          <div
            className="flex items-start gap-3 px-4 py-3 max-w-[90%] rounded-2xl"
            style={{
              background: "linear-gradient(135deg, color-mix(in srgb, var(--accent) 8%, rgba(255,255,255,0.04)) 0%, rgba(255,255,255,0.02) 100%)",
              border: "1px solid color-mix(in srgb, var(--accent) 24%, transparent)",
              boxShadow: "0 6px 20px color-mix(in srgb, var(--accent) 14%, transparent), inset 0 1px 0 rgba(255,255,255,0.05)",
              backdropFilter: "blur(20px) saturate(1.2)",
              WebkitBackdropFilter: "blur(20px) saturate(1.2)",
            }}
          >
            <div style={{ fontSize: 24, lineHeight: 1, flexShrink: 0 }}>{avatarEmoji}</div>
            <div className="text-sm leading-relaxed italic" style={{ color: "var(--text-primary)" }}>
              {message.content}
            </div>
          </div>
        </motion.div>
      );
    }
    return (
      <motion.div
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex justify-center"
      >
        <div
          className="px-4 py-2 font-display font-bold uppercase tracking-widest rounded-full"
          style={{
            fontSize: 12,
            background: "var(--glass-bg, rgba(255,255,255,0.04))",
            color: "var(--text-muted)",
            border: "1px solid var(--glass-border, rgba(255,255,255,0.08))",
            backdropFilter: "blur(20px)",
            letterSpacing: "0.16em",
          }}
        >
          {message.content}
        </div>
      </motion.div>
    );
  }

  // ═══ Hint message — amber pixel card
  if (isHint) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-start gap-3"
      >
        <div
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl"
          style={{
            background: "linear-gradient(135deg, rgba(245,158,11,0.16) 0%, rgba(245,158,11,0.04) 100%)",
            border: "1px solid rgba(245,158,11,0.4)",
            boxShadow: "0 4px 12px rgba(245,158,11,0.18), inset 0 1px 0 rgba(255,255,255,0.06)",
            backdropFilter: "blur(20px)",
          }}
        >
          <Lightbulb size={16} style={{ color: "var(--warning)" }} />
        </div>
        <div
          className="max-w-[90%] sm:max-w-[80%] px-4 py-3 rounded-2xl"
          style={{
            background: "linear-gradient(135deg, rgba(245,158,11,0.08) 0%, rgba(245,158,11,0.02) 100%)",
            border: "1px solid rgba(245,158,11,0.32)",
            boxShadow: "0 6px 20px rgba(245,158,11,0.16), inset 0 1px 0 rgba(255,255,255,0.05)",
            backdropFilter: "blur(20px) saturate(1.2)",
            WebkitBackdropFilter: "blur(20px) saturate(1.2)",
          }}
        >
          <div
            className="font-display font-bold text-[12px] uppercase tracking-widest mb-1.5"
            style={{ color: "var(--warning)", letterSpacing: "0.16em" }}
          >
            💡 Подсказка
          </div>
          <p className="text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
            {message.content}
          </p>
        </div>
      </motion.div>
    );
  }

  // ═══ Feedback message — 4-bucket nuanced verdict (2026-05-04 FRONT-3)
  if (isFeedback) {
    const correct = message.isCorrect;
    // verdictLevel is the new source of truth. Falls back to
    // is_correct → correct/wrong for legacy messages.
    const level: "correct" | "partial" | "off_topic" | "wrong" =
      message.verdictLevel ?? (correct ? "correct" : "wrong");

    // Palette per bucket:
    //   correct   → green (success)
    //   partial   → amber (warning) — "почти, упустил детали"
    //   off_topic → blue  (accent-cool) — "знаешь, но не по теме"
    //   wrong     → red   (danger)
    const palette: Record<typeof level, { color: string; bg: string; label: string; icon: typeof CheckCircle2 }> = {
      correct: {
        color: "var(--success)",
        bg: "var(--success-muted)",
        label: "▸ ВЕРНО! +XP",
        icon: CheckCircle2,
      },
      partial: {
        color: "var(--warning)",
        bg: "color-mix(in srgb, var(--warning) 15%, transparent)",
        label: "🟡 Почти — упустил детали",
        icon: CheckCircle2,
      },
      off_topic: {
        color: "#60a5fa",
        bg: "rgba(96,165,250,0.15)",
        label: "📍 Знание верное, но не по теме",
        icon: CheckCircle2,
      },
      wrong: {
        color: "var(--danger)",
        bg: "var(--danger-muted)",
        label: "✖ Неверно",
        icon: XCircle,
      },
    };
    const { color, bg: bgColor, label: verdictLabel, icon: VerdictIcon } = palette[level];

    // 2026-05-04 dedup: the LLM judge usually puts the correct answer
    // INTO `explanation`, then backend ALSO sends a separate
    // `correctAnswer` field with the same text. Rendering both makes
    // the card show "✖ Неверно — За 3 года... ст. 61.2 / ▸ ПРАВИЛЬНО:
    // За 3 года... ст. 61.2" — same string twice. Strategy: pick ONE
    // canonical "right answer" string (correctAnswer wins, falls back
    // to explanation), and only show explanation as a SEPARATE
    // "📖 Объяснение" block if it adds material beyond the right answer.
    const norm = (s: string) => s.toLowerCase().replace(/\s+/g, " ").trim();
    const rightAnswer = (message.correctAnswer || "").trim();
    const explanation = (message.explanation || "").trim();
    const explanationAddsValue =
      explanation.length > 0 &&
      (!rightAnswer ||
        // explanation differs materially from rightAnswer (not a substring/superset)
        (!norm(rightAnswer).includes(norm(explanation)) &&
          !norm(explanation).includes(norm(rightAnswer))));

    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-start gap-3"
      >
        <div
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl"
          style={{
            background: `linear-gradient(135deg, color-mix(in srgb, ${color} 22%, transparent) 0%, color-mix(in srgb, ${color} 6%, transparent) 100%)`,
            border: `1px solid color-mix(in srgb, ${color} 45%, transparent)`,
            boxShadow: `0 4px 14px color-mix(in srgb, ${color} 28%, transparent), inset 0 1px 0 rgba(255,255,255,0.08)`,
            backdropFilter: "blur(20px)",
          }}
        >
          <VerdictIcon size={16} style={{ color, filter: `drop-shadow(0 0 4px ${color})` }} />
        </div>
        <div
          className="max-w-[90%] sm:max-w-[80%] px-4 py-3 rounded-2xl"
          style={{
            background: `linear-gradient(135deg, color-mix(in srgb, ${color} 10%, rgba(255,255,255,0.04)) 0%, rgba(255,255,255,0.02) 100%)`,
            border: `1px solid color-mix(in srgb, ${color} 36%, transparent)`,
            boxShadow: `0 8px 28px color-mix(in srgb, ${color} 22%, transparent), 0 0 0 1px color-mix(in srgb, ${color} 14%, transparent), inset 0 1px 0 rgba(255,255,255,0.05)`,
            backdropFilter: "blur(20px) saturate(1.2)",
            WebkitBackdropFilter: "blur(20px) saturate(1.2)",
          }}
        >
          <div
            className="font-display font-bold text-[13px] uppercase tracking-widest mb-2"
            style={{ color, letterSpacing: "0.14em", textShadow: `0 0 12px ${color}55` }}
          >
            {verdictLabel}
            {typeof message.llmScore === "number" && (
              <span
                className="ml-2 text-[10px]"
                style={{ color: "var(--text-muted)", opacity: 0.7 }}
              >
                {Math.round(message.llmScore)}/10
              </span>
            )}
          </div>
          {/* PR-12 (2026-05-07): дать «персонажу» голос. Показываем
              personality_comment отдельным italic-блоком ВПЕРЕДИ всех
              остальных деталей — иначе он терялся внутри `content` строки
              и пользователь чувствовал «безликий» AI. Showman/Professor/
              Detective стили теперь явно видны. */}
          {message.personalityComment && (
            <div
              className="mb-2 px-3 py-2 italic"
              style={{
                background: "color-mix(in srgb, var(--accent) 8%, transparent)",
                borderLeft: "3px solid var(--accent)",
                color: "var(--text-primary)",
                fontSize: 13,
                lineHeight: 1.5,
              }}
            >
              {message.avatarEmoji && <span style={{ marginRight: 6 }}>{message.avatarEmoji}</span>}
              {message.personalityComment}
            </div>
          )}
          {/* If NOT fully correct: show canonical right-answer block.
              Now appears for partial / off_topic / wrong — user always
              sees what the right answer was, even when "почти". */}
          {level !== "correct" && rightAnswer && (
            <div
              className="px-3 py-2.5 mb-2 rounded-xl"
              style={{
                background: "linear-gradient(135deg, rgba(34,197,94,0.12) 0%, rgba(34,197,94,0.04) 100%)",
                border: "1px solid rgba(34,197,94,0.4)",
                boxShadow: "0 4px 12px rgba(34,197,94,0.15), inset 0 1px 0 rgba(255,255,255,0.05)",
              }}
            >
              <div
                className="font-display font-bold text-[11px] uppercase tracking-widest mb-1"
                style={{ color: "var(--success)", letterSpacing: "0.16em" }}
              >
                ✓ Правильный ответ
              </div>
              <div className="text-sm leading-relaxed" style={{ color: "var(--text-primary)" }}>
                {rightAnswer}
              </div>
            </div>
          )}
          {/* If CORRECT: short confirmation if there's an explanation. */}
          {level === "correct" && explanation && (
            <p className="text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
              {explanation}
            </p>
          )}
          {/* "📖 Объяснение" block ONLY when it adds material beyond
              the right-answer block (substring check both ways).
              Renders for partial / off_topic / wrong. */}
          {level !== "correct" && explanationAddsValue && (
            <div className="mt-1 text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
              <span style={{ color: "var(--text-muted)" }}>📖 </span>
              {explanation}
            </div>
          )}
          {message.articleRef && (
            <div
              className="mt-2 inline-flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-wider px-2.5 py-1 rounded-lg"
              style={{
                color: "var(--text-muted)",
                background: "var(--glass-bg, rgba(255,255,255,0.04))",
                border: "1px solid var(--glass-border, rgba(255,255,255,0.08))",
                letterSpacing: "0.06em",
                fontWeight: 600,
              }}
            >
              <BookOpen size={11} />
              {message.articleRef}
            </div>
          )}
          {/* PR-6: «Пожаловаться на ответ» — flag button + modal. Disabled
              when answerId missing (legacy events without backend wiring). */}
          {message.answerId && <ReportAnswerButton answerId={message.answerId} />}
          {message.speedBonus && message.speedBonus > 0 && (
            <motion.div
              initial={{ scale: 0.6, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ type: "spring", stiffness: 320, damping: 18 }}
              className="mt-2 ml-2 inline-flex items-center gap-1 px-2.5 py-1 font-display font-bold text-[11px] uppercase tracking-wider rounded-lg"
              style={{
                background: "linear-gradient(135deg, rgba(245,158,11,0.95) 0%, rgba(245,158,11,0.75) 100%)",
                color: "#1a0f00",
                border: "1px solid rgba(245,158,11,0.6)",
                boxShadow: "0 4px 12px rgba(245,158,11,0.35), inset 0 1px 0 rgba(255,255,255,0.32)",
                letterSpacing: "0.1em",
              }}
            >
              <Zap size={12} /> +{message.speedBonus} SPEED
            </motion.div>
          )}
        </div>
      </motion.div>
    );
  }

  // ═══ Follow-up message
  if (isFollowUp) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-start gap-3"
      >
        <div
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl"
          style={{
            background: "linear-gradient(135deg, color-mix(in srgb, var(--accent) 22%, transparent) 0%, color-mix(in srgb, var(--accent) 8%, transparent) 100%)",
            border: "1px solid color-mix(in srgb, var(--accent) 40%, transparent)",
            boxShadow: "0 4px 12px color-mix(in srgb, var(--accent) 24%, transparent), inset 0 1px 0 rgba(255,255,255,0.06)",
            backdropFilter: "blur(20px)",
          }}
        >
          {avatarEmoji ? <AppIcon emoji={avatarEmoji} size={18} /> : <AppIcon emoji={"\uD83D\uDCA1"} size={18} />}
        </div>
        <div
          className="max-w-[90%] sm:max-w-[80%] px-4 py-3 rounded-2xl"
          style={{
            background: "linear-gradient(135deg, color-mix(in srgb, var(--accent) 10%, rgba(255,255,255,0.04)) 0%, rgba(255,255,255,0.02) 100%)",
            border: "1px solid color-mix(in srgb, var(--accent) 32%, transparent)",
            boxShadow: "0 6px 20px color-mix(in srgb, var(--accent) 16%, transparent), inset 0 1px 0 rgba(255,255,255,0.05)",
            backdropFilter: "blur(20px) saturate(1.2)",
            WebkitBackdropFilter: "blur(20px) saturate(1.2)",
          }}
        >
          <div className="font-display font-bold text-[12px] uppercase tracking-widest mb-1.5" style={{ color: "var(--accent)", letterSpacing: "0.16em" }}>
            Уточнение
          </div>
          <p className="text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
            {message.content}
          </p>
        </div>
      </motion.div>
    );
  }

  // ═══ Question from AI
  if (isQuestion) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-start gap-3"
      >
        <div
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl"
          style={{
            background: "linear-gradient(135deg, color-mix(in srgb, var(--accent) 22%, transparent) 0%, color-mix(in srgb, var(--accent) 8%, transparent) 100%)",
            border: "1px solid color-mix(in srgb, var(--accent) 40%, transparent)",
            boxShadow: "0 4px 12px color-mix(in srgb, var(--accent) 24%, transparent), inset 0 1px 0 rgba(255,255,255,0.06)",
            backdropFilter: "blur(20px)",
          }}
        >
          {avatarEmoji ? <AppIcon emoji={avatarEmoji} size={18} /> : <BookOpen size={16} style={{ color: "var(--accent)" }} />}
        </div>
        <div
          className="max-w-[90%] sm:max-w-[80%] px-4 py-3 rounded-2xl"
          style={{
            background: "linear-gradient(135deg, rgba(255,255,255,0.05) 0%, rgba(255,255,255,0.02) 100%)",
            border: "1px solid color-mix(in srgb, var(--accent) 28%, transparent)",
            boxShadow: "0 6px 22px color-mix(in srgb, var(--accent) 14%, transparent), inset 0 1px 0 rgba(255,255,255,0.05)",
            backdropFilter: "blur(20px) saturate(1.2)",
            WebkitBackdropFilter: "blur(20px) saturate(1.2)",
          }}
        >
          {message.category && (
            <div
              className="inline-flex items-center gap-1 font-display font-bold text-[12px] uppercase tracking-widest mb-3 px-3 py-1.5 rounded-lg"
              style={{
                color: "#fff",
                background: "linear-gradient(135deg, var(--accent) 0%, color-mix(in srgb, var(--accent) 80%, black) 100%)",
                boxShadow: "0 4px 12px color-mix(in srgb, var(--accent) 36%, transparent), inset 0 1px 0 rgba(255,255,255,0.2)",
                letterSpacing: "0.14em",
              }}
            >
              ▸ {categoryLabel(message.category)}
            </div>
          )}
          <p className="leading-relaxed" style={{ color: "var(--text-primary)", fontSize: 18, fontWeight: 500, lineHeight: 1.55 }}>
            {message.content}
          </p>
        </div>
      </motion.div>
    );
  }

  // ═══ User answer — pixel accent bubble right-aligned
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex justify-end"
    >
      <div
        className="max-w-[90%] sm:max-w-[80%] px-4 py-3 rounded-2xl"
        style={{
          background: "linear-gradient(135deg, var(--accent) 0%, color-mix(in srgb, var(--accent) 78%, black) 100%)",
          color: "#fff",
          border: "1px solid color-mix(in srgb, var(--accent) 60%, white)",
          boxShadow: "0 8px 24px color-mix(in srgb, var(--accent) 36%, transparent), inset 0 1px 0 rgba(255,255,255,0.18), inset 0 -2px 6px rgba(0,0,0,0.2)",
        }}
      >
        <div className="font-display font-bold text-[12px] uppercase tracking-widest mb-1.5 opacity-85" style={{ letterSpacing: "0.18em" }}>
          ВЫ
        </div>
        <p className="leading-relaxed" style={{ color: "#fff", fontSize: 16, fontWeight: 500, lineHeight: 1.5 }}>
          {message.content}
        </p>
      </div>
    </motion.div>
  );
}
