"use client";

import { useEffect, useState } from "react";
import { useSound } from "@/hooks/useSound";
import type { ArenaChallenge } from "@/types";

interface PvPChallengeToastProps {
  challenge: ArenaChallenge;
  onAccept: (challengeId: string) => void;
  onDecline: (challengeId: string) => void;
  expiresInSeconds?: number;
}

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

export default function PvPChallengeToast({
  challenge,
  onAccept,
  onDecline,
  expiresInSeconds = 60,
}: PvPChallengeToastProps) {
  const [timeLeft, setTimeLeft] = useState(expiresInSeconds);
  const { playSound } = useSound();

  // SFX: play challenge sound on mount
  useEffect(() => {
    playSound("challenge", 0.6);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps -- mount-only SFX; playSound is intentionally excluded

  useEffect(() => {
    const timer = setInterval(() => {
      setTimeLeft((prev) => {
        if (prev <= 1) {
          clearInterval(timer);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  // Auto-dismiss when expired
  if (timeLeft <= 0) return null;

  return (
    <div className="fixed top-4 right-4 z-50 w-80 cyber-card border border-[var(--neon-amber)] rounded-xl shadow-2xl overflow-hidden animate-in slide-in-from-right">
      {/* Timer bar */}
      <div className="h-1" style={{ background: "var(--glass-border)" }}>
        <div
          className="h-full transition-all duration-1000 ease-linear"
          style={{ background: "var(--warning)", width: `${(timeLeft / expiresInSeconds) * 100}%` }}
        />
      </div>

      <div className="p-4">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-xl">⚔️</span>
          <h3 className="font-bold" style={{ color: "var(--text-primary)" }}>Вызов на дуэль!</h3>
        </div>

        <p className="text-sm mb-1" style={{ color: "var(--text-secondary)" }}>
          <span className="font-medium" style={{ color: "var(--text-primary)" }}>{challenge.challenger_name}</span>
          {" "}приглашает на дуэль знаний
        </p>

        {challenge.category && (
          <p className="text-xs mb-2" style={{ color: "var(--text-muted)" }}>
            Категория: {CATEGORY_LABELS[challenge.category] || challenge.category}
          </p>
        )}

        <p className="text-xs mb-3" style={{ color: "var(--text-muted)" }}>
          {challenge.max_players === 4 ? "Командный бой (4 игрока)" : "Дуэль 1 на 1"}
          {" "} | {timeLeft} сек
        </p>

        <div className="flex gap-2">
          <button
            onClick={() => onAccept(challenge.challenge_id)}
            className="flex-1 px-3 py-2 btn-neon btn-neon--green text-white text-sm font-medium rounded-lg transition-colors"
          >
            Принять
          </button>
          <button
            onClick={() => onDecline(challenge.challenge_id)}
            className="flex-1 px-3 py-2 btn-neon text-white text-sm font-medium rounded-lg transition-colors"
          >
            Отклонить
          </button>
        </div>
      </div>
    </div>
  );
}
