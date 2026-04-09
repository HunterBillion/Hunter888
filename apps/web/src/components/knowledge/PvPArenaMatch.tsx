"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useKnowledgeStore } from "@/stores/useKnowledgeStore";
import type { ArenaRoundResult, ArenaFinalResults } from "@/types";

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
    <span style={{ color: "var(--warning)" }}>
      {"★".repeat(Math.min(level, 5))}
      {"☆".repeat(Math.max(0, 5 - level))}
    </span>
  );
}

interface PvPArenaMatchProps {
  userId: string;
  sendMessage: (data: unknown) => void;
}

export default function PvPArenaMatch({ userId, sendMessage }: PvPArenaMatchProps) {
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
    submitPvPAnswer,
    tickPvPTimer,
  } = useKnowledgeStore();

  const [inputText, setInputText] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

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
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 glass-panel border-b" style={{ borderColor: "var(--border-color)" }}>
        <div className="flex items-center gap-2">
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
                  <span>{player.is_bot ? "🤖" : isMe ? "👤" : "👤"}</span>
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
                          {pr?.is_correct ? "✓" : "✗"}
                        </span>
                      );
                    })}
                  </div>
                  {/* Answer status for current round */}
                  {pvpCurrentQuestion && (
                    <span className="text-xs">
                      {isMe && pvpMyAnswerSubmitted
                        ? "✅"
                        : hasAnswered
                          ? "⌛"
                          : "✏️"}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Answer input */}
      {pvpCurrentQuestion && (
        <div className="mx-4 mt-3 p-3 glass-panel rounded-lg">
          {pvpMyAnswerSubmitted ? (
            <div className="text-center py-3 text-[var(--text-muted)]">
              <p>Ответ отправлен. Ожидаем соперников...</p>
            </div>
          ) : (
            <div className="flex gap-2">
              <input
                ref={inputRef}
                type="text"
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Введите ваш ответ..."
                className="flex-1 px-3 py-2 rounded-lg focus:outline-none bg-[var(--input-bg)] text-[var(--text-primary)] border border-[var(--border-color)] focus:border-[var(--accent)]"
                maxLength={1000}
                disabled={pvpTimeLeft <= 0}
              />
              <button
                onClick={handleSubmitAnswer}
                disabled={!inputText.trim() || pvpTimeLeft <= 0}
                className="px-4 py-2 btn-neon disabled:opacity-40 disabled:cursor-not-allowed rounded-lg font-medium transition-colors"
              >
                Отправить
              </button>
            </div>
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
                  <span>{p.is_correct ? "✅" : "❌"}</span>
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
          const medals = ["🥇", "🥈", "🥉", "4️⃣"];

          return (
            <div
              key={player.user_id}
              className={`flex items-center justify-between p-4 rounded-lg ${isMe ? "" : "glass-panel"}`}
              style={isMe ? { background: "var(--accent-muted)", border: "1px solid var(--accent)" } : undefined}
            >
              <div className="flex items-center gap-3">
                <span className="text-2xl">{medals[player.rank - 1] || `#${player.rank}`}</span>
                <div>
                  <p className="font-medium" style={{ color: isMe ? "var(--accent)" : "var(--text-primary)" }}>
                    {isMe ? "Вы" : player.name}
                    {player.is_bot && " 🤖"}
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
