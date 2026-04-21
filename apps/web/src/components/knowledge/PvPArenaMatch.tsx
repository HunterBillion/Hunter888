"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { CheckCircle, XCircle, Clock, Pencil, Medal, Bot, User, Star, LogOut } from "lucide-react";
import { useKnowledgeStore } from "@/stores/useKnowledgeStore";
import type { ArenaRoundResult, ArenaFinalResults } from "@/types";
import { ArenaAudioPlayer } from "@/components/pvp/ArenaAudioPlayer";

// Sprint 1-3 Arena upgrade (2026-04-20):
//  - Post-answer reveal with right-answer highlight + article + explanation
//  - Confetti / wrong-shake animations
//  - SFX pack (correct / wrong / round_start / round_end)
//  - Voice-enabled input (ArenaAnswerInput)
import { CorrectAnswerReveal } from "@/components/arena/reveal/CorrectAnswerReveal";
import { CelebrationBurst } from "@/components/arena/reveal/CelebrationBurst";
import { WrongShake } from "@/components/arena/reveal/WrongShake";
import { ArenaAnswerInput } from "@/components/arena/input/ArenaAnswerInput";
import { useSFX } from "@/components/arena/sfx/useSFX";
import type { CorrectAnswerPayload } from "@/components/arena/reveal/CorrectAnswerReveal";
// Sprint 4 (2026-04-20): lifelines (hint / skip / 50-50) wired to REST endpoints
import { useLifelines } from "@/components/arena/hooks/useLifelines";
import { HintBubble } from "@/components/arena/reveal/HintBubble";
// Phase C (2026-04-20): power-ups (×2 XP) — active modifier, one-shot per arm
import { usePowerUps } from "@/components/arena/hooks/usePowerUps";
import { Zap } from "lucide-react";

const CATEGORY_LABELS: Record<string, string> = {
  eligibility: "Условия банкротства",
  procedure: "Порядок процедуры",
  property: "Имущество",
  consequences: "Последствия",
  costs: "Стоимость",
  creditors: "Кредиторы",
  documents: "Документы",
  timeline: "Сроки",
  court: "Суд",
  rights: "Права должника",
};

function DifficultyStars({ level }: { level: number }) {
  return (
    <span className="inline-flex gap-0.5" style={{ color: "var(--warning)" }}>
      {Array.from({ length: 5 }, (_, i) => (
        <Star key={i} size={14} fill={i < level ? "currentColor" : "none"} />
      ))}
    </span>
  );
}

interface PvPArenaMatchProps {
  userId: string;
  sendMessage: (data: unknown) => void;
}

export default function PvPArenaMatch({ userId, sendMessage }: PvPArenaMatchProps) {
  const router = useRouter();
  const [showExitConfirm, setShowExitConfirm] = useState(false);
  const {
    pvpRound,
    pvpTotalRounds,
    pvpArenaPlayers,
    pvpRoundResults,
    pvpMyAnswer,
    pvpMyAnswerSubmitted,
    pvpOpponentsAnswered,
    pvpTimeLeft,
    pvpFinalResults,
    pvpCurrentQuestion,
    pvpCurrentCategory,
    pvpCurrentDifficulty,
    pvpDisconnectedPlayers,
    pvpArenaAudioUrl,
    pvpMatchId,
    submitPvPAnswer,
    tickPvPTimer,
  } = useKnowledgeStore();

  // Sprint 4 — lifelines (hint / skip / 50-50) persisted on the backend
  const lifelines = useLifelines({
    sessionId: pvpMatchId,
    mode: "arena",
    enabled: !!pvpMatchId,
  });
  // Phase C — active power-up modifiers (×2 XP)
  const powerups = usePowerUps({
    sessionId: pvpMatchId,
    mode: "arena",
    enabled: !!pvpMatchId,
  });

  const [inputText, setInputText] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Sprint 1-3 Arena upgrade state
  const sfx = useSFX();
  const [revealPayload, setRevealPayload] = useState<CorrectAnswerPayload | null>(null);
  const [revealOpen, setRevealOpen] = useState(false);
  const [celebrate, setCelebrate] = useState(false);
  const [shake, setShake] = useState(false);
  const lastSeenRoundRef = useRef<number>(0);

  // Prime sound pack on mount so first correct/wrong fires instantly
  useEffect(() => {
    sfx.prime();
  }, [sfx]);

  // Watch round results — when a new one arrives for US, show reveal + play SFX
  useEffect(() => {
    if (!pvpRoundResults.length) return;
    const latest = pvpRoundResults[pvpRoundResults.length - 1];
    const round = latest.round_number ?? pvpRoundResults.length;
    if (round <= lastSeenRoundRef.current) return;
    lastSeenRoundRef.current = round;

    const mine = latest.players?.find((p) => p.user_id === userId);
    if (!mine) return;

    // Fire SFX + burst/shake
    if (mine.is_correct) {
      sfx.play("correct");
      setCelebrate(true);
      setTimeout(() => setCelebrate(false), 1200);
    } else {
      sfx.play("wrong");
      setShake(true);
      setTimeout(() => setShake(false), 600);
    }

    // Phase C — sync power-up state after the round (it may have been
    // consumed by backend scoring). A no-op when nothing was armed.
    powerups.refresh();

    setRevealPayload({
      isCorrect: !!mine.is_correct,
      scoreDelta: (mine.score ?? 0) + (mine.speed_bonus ?? 0),
      correctAnswer: latest.correct_answer ?? null,
      articleReference: (latest as unknown as { article_reference?: string }).article_reference ?? null,
      explanation: (latest as unknown as { explanation?: string }).explanation ?? null,
      userAnswer: mine.answer ?? null,
    });
    setRevealOpen(true);
  }, [pvpRoundResults, userId, sfx]);

  // Round start ping
  useEffect(() => {
    if (pvpCurrentQuestion) sfx.play("round_start");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pvpCurrentQuestion]);

  // Timer countdown
  useEffect(() => {
    if (pvpTimeLeft > 0 && !pvpMyAnswerSubmitted) {
      timerRef.current = setInterval(() => {
        tickPvPTimer();
      }, 1000);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [pvpTimeLeft, pvpMyAnswerSubmitted, tickPvPTimer]);

  const handleSubmitAnswer = useCallback(() => {
    const text = inputText.trim();
    if (!text || pvpMyAnswerSubmitted) return;

    submitPvPAnswer(text);
    sendMessage({
      type: "pvp.answer",
      data: { text, round_number: pvpRound },
    });
    setInputText("");
  }, [inputText, pvpMyAnswerSubmitted, pvpRound, submitPvPAnswer, sendMessage]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSubmitAnswer();
      }
    },
    [handleSubmitAnswer],
  );

  // Focus input when new question arrives
  useEffect(() => {
    if (pvpCurrentQuestion && !pvpMyAnswerSubmitted) {
      inputRef.current?.focus();
    }
  }, [pvpCurrentQuestion, pvpMyAnswerSubmitted]);

  // Final results screen
  if (pvpFinalResults) {
    return <ArenaResultsView results={pvpFinalResults} userId={userId} />;
  }

  const lastResult = pvpRoundResults.length > 0 ? pvpRoundResults[pvpRoundResults.length - 1] : null;

  return (
    <div className="flex flex-col h-full" style={{ background: "var(--bg-primary)", color: "var(--text-primary)" }}>
      {/* Exit confirmation overlay */}
      {showExitConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: "var(--overlay-bg)", backdropFilter: "blur(4px)" }}>
          <div className="rounded-xl p-6 max-w-sm w-full mx-4" style={{ background: "var(--bg-secondary)", border: "1px solid var(--border-color)" }}>
            <h3 className="text-lg font-bold mb-2" style={{ color: "var(--text-primary)" }}>Выйти из матча?</h3>
            <p className="text-sm mb-5" style={{ color: "var(--text-muted)" }}>Прогресс текущего матча будет потерян.</p>
            <div className="flex gap-3">
              <button
                onClick={() => setShowExitConfirm(false)}
                className="flex-1 py-2.5 rounded-lg text-sm font-medium"
                style={{ background: "var(--input-bg)", color: "var(--text-primary)", border: "1px solid var(--border-color)" }}
              >
                Остаться
              </button>
              <button
                onClick={() => {
                  sendMessage({ type: "leave_match" });
                  router.push("/pvp");
                }}
                className="flex-1 py-2.5 rounded-lg text-sm font-medium"
                style={{ background: "var(--danger)", color: "#fff" }}
              >
                Выйти
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 glass-panel border-b" style={{ borderColor: "var(--border-color)" }}>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowExitConfirm(true)}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors"
            style={{ background: "var(--danger-muted)", color: "var(--danger)", border: "1px solid var(--danger-muted)" }}
            title="Выйти из матча"
          >
            <LogOut size={14} />
            Выйти
          </button>
          <span className="text-lg font-bold">ДУЭЛЬ ЗНАНИЙ</span>
        </div>
        <div className="text-sm text-[var(--text-secondary)]">
          Раунд {pvpRound}/{pvpTotalRounds}
        </div>
        <div className={`text-lg font-mono font-bold ${pvpTimeLeft <= 10 ? "animate-pulse" : ""}`} style={{ color: pvpTimeLeft <= 10 ? "var(--danger)" : "var(--success)" }}>
          {Math.floor(pvpTimeLeft / 60)}:{String(pvpTimeLeft % 60).padStart(2, "0")}
        </div>
      </div>

      {/* Question */}
      {pvpCurrentQuestion && (
        <div className="mx-4 mt-4 p-4 glass-panel rounded-lg">
          <p className="text-base leading-relaxed">{pvpCurrentQuestion}</p>
          <div className="mt-2 flex items-center gap-3 text-sm text-[var(--text-muted)]">
            {pvpCurrentCategory && (
              <span>{CATEGORY_LABELS[pvpCurrentCategory] || pvpCurrentCategory}</span>
            )}
            <DifficultyStars level={pvpCurrentDifficulty} />
          </div>
          {/* 2026-04-19 Phase 2.8: arcade-themed narration for the round. */}
          {pvpArenaAudioUrl && (
            <div className="mt-3 flex justify-end">
              <ArenaAudioPlayer
                audioUrl={pvpArenaAudioUrl}
                label={`РАУНД ${pvpRound}`}
                autoplay={true}
              />
            </div>
          )}
        </div>
      )}

      {/* Scoreboard */}
      <div className="mx-4 mt-3 p-3 glass-panel opacity-80 rounded-lg">
        <div className="space-y-2">
          {pvpArenaPlayers.map((player) => {
            const isMe = player.user_id === userId;
            const isDisconnected = pvpDisconnectedPlayers.includes(player.user_id);
            const hasAnswered = pvpOpponentsAnswered[player.user_id];

            return (
              <div
                key={player.user_id}
                className="flex items-center justify-between px-3 py-2 rounded"
                style={{
                  background: isMe ? "var(--accent-muted)" : "var(--glass-bg)",
                  border: isMe ? "1px solid var(--accent)" : "none",
                }}
              >
                <div className="flex items-center gap-2">
                  <span>{player.is_bot ? <Bot size={16} /> : <User size={16} />}</span>
                  <span className="font-medium" style={{ color: isMe ? "var(--accent)" : "var(--text-primary)" }}>
                    {isMe ? "Вы" : player.name}
                  </span>
                  {isDisconnected && <span className="text-xs" style={{ color: "var(--danger)" }}>(отключен)</span>}
                </div>
                <div className="flex items-center gap-4">
                  <span className="text-sm text-[var(--text-muted)]">
                    {player.score} очков
                  </span>
                  {/* Round history indicators */}
                  <div className="flex gap-1">
                    {pvpRoundResults.map((rr, rrIdx) => {
                      const pr = rr.players.find((p) => p.user_id === player.user_id);
                      return (
                        <span key={`${rr.round_number ?? rrIdx}-${player.user_id}`} className={`w-4 h-4 rounded-full text-xs flex items-center justify-center ${pr?.is_correct ? "bg-green-600" : "bg-red-600"}`}>
                          {pr?.is_correct ? <CheckCircle size={10} /> : <XCircle size={10} />}
                        </span>
                      );
                    })}
                  </div>
                  {/* Answer status for current round */}
                  {pvpCurrentQuestion && (
                    <span className="text-xs inline-flex items-center">
                      {isMe && pvpMyAnswerSubmitted
                        ? <CheckCircle size={14} />
                        : hasAnswered
                          ? <Clock size={14} />
                          : <Pencil size={14} />}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Answer input — Sprint 2: voice + lifelines + accent theme */}
      {pvpCurrentQuestion && (
        <div className="mx-4 mt-3">
          {pvpMyAnswerSubmitted ? (
            <div
              className="rounded-xl px-4 py-3 text-center text-sm"
              style={{
                background: "var(--input-bg)",
                border: "1px solid var(--border-color)",
                color: "var(--text-muted)",
              }}
            >
              ✓ Ответ отправлен. Ожидаем соперников…
            </div>
          ) : (
            <>
              {/* Phase C — Power-up chip row (above lifelines bar).
                  Armed state shows a pulsing glow; click debits a charge
                  and arms the ×2 multiplier for the next answer. */}
              {(powerups.counts.doublexp > 0 || powerups.activeKind) && (
                <div className="flex items-center gap-2 mb-2 flex-wrap">
                  <button
                    type="button"
                    disabled={
                      !!powerups.activeKind || powerups.counts.doublexp <= 0 || pvpTimeLeft <= 0
                    }
                    onClick={async () => {
                      const ok = await powerups.activate("doublexp");
                      if (ok) sfx.play("hint");
                    }}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-semibold uppercase tracking-wider transition-all disabled:opacity-45"
                    style={{
                      background: powerups.activeKind === "doublexp" ? "#facc15" : "#facc1518",
                      color: powerups.activeKind === "doublexp" ? "#0b0b14" : "#facc15",
                      border: "1px solid #facc1555",
                      boxShadow: powerups.activeKind === "doublexp"
                        ? "0 0 18px #facc15aa"
                        : undefined,
                    }}
                    title={
                      powerups.activeKind === "doublexp"
                        ? "Активно — следующий верный ответ даст ×2"
                        : "Активировать ×2 на следующий ответ"
                    }
                  >
                    <Zap size={12} />
                    {powerups.activeKind === "doublexp" ? "×2 АКТИВНО" : "×2 очков"}
                    {powerups.activeKind !== "doublexp" && (
                      <span className="font-mono opacity-80">×{powerups.counts.doublexp}</span>
                    )}
                  </button>
                  {powerups.error && (
                    <span
                      className="text-[10px] uppercase tracking-widest"
                      style={{ color: "var(--danger)" }}
                    >
                      {powerups.error}
                    </span>
                  )}
                </div>
              )}
              <ArenaAnswerInput
              accentColor="#a78bfa"
              placeholder="Введи ответ или нажми микрофон…"
              disabled={pvpTimeLeft <= 0}
              onSubmit={(text) => {
                submitPvPAnswer(text);
                sendMessage({
                  type: "pvp.answer",
                  data: { text, round_number: pvpRound },
                });
                setInputText("");
              }}
              lifelines={{
                hintsLeft: lifelines.counts.hints,
                skipsLeft: lifelines.counts.skips,
                fiftyFiftysLeft: lifelines.counts.fiftys,
              }}
              onHint={async () => {
                if (!pvpCurrentQuestion) return;
                const r = await lifelines.useHint(pvpCurrentQuestion);
                if (r) sfx.play("hint");
              }}
              onSkip={async () => {
                const ok = await lifelines.useSkip();
                if (!ok) return;
                // Still debit the round clock on the server via an empty
                // answer (convention: "__skip__" sentinel).
                submitPvPAnswer("__skip__");
                sendMessage({
                  type: "pvp.answer",
                  data: { text: "__skip__", round_number: pvpRound },
                });
              }}
              onFiftyFifty={async () => {
                const ok = await lifelines.useFifty();
                if (ok) sfx.play("hint");
              }}
            />
            </>
          )}
        </div>
      )}

      {/* Last round result */}
      {lastResult && !pvpCurrentQuestion && (
        <div className="mx-4 mt-3 p-4 glass-panel rounded-lg">
          <h3 className="text-sm font-semibold text-[var(--text-muted)] mb-2">
            Результат раунда {lastResult.round_number}
          </h3>
          <p className="text-sm text-[var(--text-secondary)] mb-3">
            {lastResult.question}
          </p>
          <div className="space-y-2">
            {lastResult.players.map((p) => (
              <div key={p.user_id} className="flex items-center justify-between text-sm">
                <div className="flex items-center gap-2">
                  <span>{p.is_correct ? <CheckCircle size={14} /> : <XCircle size={14} />}</span>
                  <span className={p.user_id === userId ? "font-medium" : ""} style={{ color: p.user_id === userId ? "var(--accent)" : "var(--text-primary)" }}>
                    {p.user_id === userId ? "Вы" : p.name}
                  </span>
                </div>
                <div className="flex items-center gap-2 text-[var(--text-muted)]">
                  <span className="text-xs max-w-[200px] truncate">&laquo;{p.answer}&raquo;</span>
                  <span style={{ color: p.is_correct ? "var(--success)" : "var(--danger)" }}>
                    {p.score}{p.speed_bonus > 0 ? ` (+${p.speed_bonus})` : ""}
                  </span>
                </div>
              </div>
            ))}
          </div>
          {lastResult.correct_answer && (
            <div className="mt-3 pt-3 border-t border-[var(--border-color)] text-sm">
              <p style={{ color: "var(--success)" }}>Правильный ответ: {lastResult.correct_answer}</p>
              {lastResult.article_ref && (
                <p className="text-[var(--text-muted)] mt-1">{lastResult.article_ref}</p>
              )}
            </div>
          )}
        </div>
      )}

      {/* Spacer */}
      <div className="flex-1" />

      {/* Sprint 1 overlays: reveal + celebration + wrong-shake */}
      <CorrectAnswerReveal
        open={revealOpen}
        payload={revealPayload}
        accentColor="#a78bfa"
        onDismiss={() => setRevealOpen(false)}
      />
      <CelebrationBurst trigger={celebrate} />
      <WrongShake trigger={shake} />
      {lifelines.lastHint && (
        <HintBubble
          open={!!lifelines.lastHint}
          text={lifelines.lastHint.text}
          article={lifelines.lastHint.article}
          confidence={lifelines.lastHint.confidence}
          onDismiss={lifelines.dismissHint}
        />
      )}
    </div>
  );
}

function ArenaResultsView({
  results,
  userId,
}: {
  results: ArenaFinalResults;
  userId: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] p-6">
      <h1 className="text-2xl font-bold mb-6">РЕЗУЛЬТАТЫ ДУЭЛИ</h1>

      <div className="w-full max-w-md space-y-3">
        {results.rankings.map((player) => {
          const isMe = player.user_id === userId;
          return (
            <div
              key={player.user_id}
              className={`flex items-center justify-between p-4 rounded-lg ${isMe ? "" : "glass-panel"}`}
              style={isMe ? { background: "var(--accent-muted)", border: "1px solid var(--accent)" } : undefined}
            >
              <div className="flex items-center gap-3">
                <span className="text-2xl">{player.rank <= 3 ? <Medal size={24} /> : `#${player.rank}`}</span>
                <div>
                  <p className="font-medium" style={{ color: isMe ? "var(--accent)" : "var(--text-primary)" }}>
                    {isMe ? "Вы" : player.name}
                    {player.is_bot && <> <Bot size={14} className="inline" /></>}
                  </p>
                  <p className="text-sm text-[var(--text-muted)]">
                    {player.score} очков | {player.correct} верных
                  </p>
                </div>
              </div>
              <div className="text-right">
                {player.rating_delta !== undefined && player.rating_delta !== 0 && (
                  <span className="text-sm font-medium" style={{ color: player.rating_delta > 0 ? "var(--success)" : "var(--danger)" }}>
                    {player.rating_delta > 0 ? "+" : ""}
                    {Math.round(player.rating_delta)} ELO
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {results.contains_bot && (
        <p className="mt-4 text-sm text-[var(--text-muted)]">
          Матч с ботом — рейтинг не изменился
        </p>
      )}

      <div className="mt-6 flex gap-3">
        <a
          href="/pvp"
          className="px-4 py-2 btn-neon rounded-lg transition-colors"
        >
          К Арене
        </a>
      </div>
    </div>
  );
}
