"use client";

/**
 * /dev/duel-chat-preview — demo-страница нового пиксельного DuelChat.
 *
 * 2026-04-29: создана для визуальной верификации Фазы 2 редизайна арены
 * без необходимости поднимать backend / WS / auth. Маршруты `/dev/*`
 * отпущены из auth guard в development (см. middleware.ts).
 *
 * Тут моки: 3 раунда, разные тиры, typing-state, scores. Можно тыкать
 * input, отправлять сообщения, переключать состояния (online/typing/offline)
 * через переключатели в шапке.
 *
 * НЕ ИСПОЛЬЗУЕТСЯ В ПРОДЕ — middleware закрывает /dev/* в production.
 */

import { useState } from "react";
import { DuelChat } from "@/components/pvp/DuelChat";
import { type PvPRankTier } from "@/types";

const TIERS: PvPRankTier[] = [
  "iron",
  "bronze",
  "silver",
  "gold",
  "platinum",
  "diamond",
  "master",
  "grandmaster",
];

type ConnectionStatus = "online" | "typing" | "offline" | "reconnecting";

const STATUSES: ConnectionStatus[] = ["online", "typing", "offline", "reconnecting"];

interface Message {
  id: string;
  sender_role: "seller" | "client";
  text: string;
  round: number;
  timestamp: string;
}

const SAMPLE_MESSAGES: Message[] = [
  {
    id: "m1",
    sender_role: "client",
    text: "Здравствуйте. Мне нужны деньги срочно — банк отказал. Я слышал, вы помогаете с ФЗ-127?",
    round: 1,
    timestamp: new Date(Date.now() - 1000 * 60 * 7).toISOString(),
  },
  {
    id: "m2",
    sender_role: "seller",
    text: "Добрый день! Да, мы работаем именно по 127-ФЗ — банкротство физ.лиц. Расскажите вашу ситуацию: какие долги, на какую сумму?",
    round: 1,
    timestamp: new Date(Date.now() - 1000 * 60 * 6).toISOString(),
  },
  {
    id: "m3",
    sender_role: "client",
    text: "У меня три кредитки и один потребкредит, итого около 1.8 млн. Уже 4 месяца не плачу — приставы пишут.",
    round: 1,
    timestamp: new Date(Date.now() - 1000 * 60 * 5).toISOString(),
  },
  {
    id: "m4",
    sender_role: "seller",
    text: "Понял. По вашему долгу подходит судебное банкротство. Есть имущество — авто, недвижка кроме единственного жилья?",
    round: 2,
    timestamp: new Date(Date.now() - 1000 * 60 * 3).toISOString(),
  },
  {
    id: "m5",
    sender_role: "client",
    text: "Авто Лада 2018 года, единственная квартира — больше ничего нет. И что, всё списать получится?",
    round: 2,
    timestamp: new Date(Date.now() - 1000 * 60 * 1).toISOString(),
  },
];

export default function DuelChatPreviewPage() {
  const [messages, setMessages] = useState<Message[]>(SAMPLE_MESSAGES);
  const [input, setInput] = useState("");
  const [opponentStatus, setOpponentStatus] =
    useState<ConnectionStatus>("typing");
  const [selfTier, setSelfTier] = useState<PvPRankTier>("gold");
  const [opponentTier, setOpponentTier] = useState<PvPRankTier>("platinum");
  const [showScores, setShowScores] = useState(true);
  const [myRole, setMyRole] = useState<"seller" | "client">("seller");

  const handleSend = () => {
    if (!input.trim()) return;
    const next: Message = {
      id: `m${Date.now()}`,
      sender_role: myRole,
      text: input.trim(),
      round: messages[messages.length - 1]?.round ?? 1,
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, next]);
    setInput("");

    // Через 1.4 секунды fake-AI печатает ответ — для демо typewriter-эффекта
    setOpponentStatus("typing");
    window.setTimeout(() => {
      setMessages((prev) => [
        ...prev,
        {
          id: `m${Date.now()}-ai`,
          sender_role: myRole === "seller" ? "client" : "seller",
          text: "Понятно. Давайте уточним детали — сколько кредиторов и есть ли исполнительные производства?",
          round: prev[prev.length - 1]?.round ?? 1,
          timestamp: new Date().toISOString(),
        },
      ]);
      setOpponentStatus("online");
    }, 1400);
  };

  return (
    <div
      className="min-h-screen px-4 py-6 sm:px-8 sm:py-10"
      style={{ background: "var(--bg-primary)" }}
    >
      <div className="mx-auto max-w-5xl space-y-6">
        {/* Заголовок demo */}
        <header>
          <h1
            className="font-pixel"
            style={{
              color: "var(--text-primary)",
              fontSize: 28,
              letterSpacing: "0.18em",
              textTransform: "uppercase",
            }}
          >
            DuelChat — Превью
          </h1>
          <p
            className="mt-1"
            style={{ color: "var(--text-muted)", fontSize: 14 }}
          >
            Demo Фазы 2 редизайна PvP-арены. Не trip к боевой логике / WS /
            backend. Меняй переключатели — увидишь все состояния.
          </p>
        </header>

        {/* Панель управления */}
        <div
          className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-4"
          style={{
            background: "var(--bg-panel)",
            outline: "2px solid var(--accent)",
            outlineOffset: -2,
            boxShadow: "3px 3px 0 0 var(--accent)",
          }}
        >
          <ControlSelect
            label="Твой тир"
            value={selfTier}
            options={TIERS}
            onChange={(v) => setSelfTier(v as PvPRankTier)}
          />
          <ControlSelect
            label="Тир соперника"
            value={opponentTier}
            options={TIERS}
            onChange={(v) => setOpponentTier(v as PvPRankTier)}
          />
          <ControlSelect
            label="Статус соперника"
            value={opponentStatus}
            options={STATUSES}
            onChange={(v) => setOpponentStatus(v as ConnectionStatus)}
          />
          <ControlSelect
            label="Твоя роль"
            value={myRole}
            options={["seller", "client"]}
            onChange={(v) => setMyRole(v as "seller" | "client")}
          />
          <label className="flex items-center gap-2 col-span-full">
            <input
              type="checkbox"
              checked={showScores}
              onChange={(e) => setShowScores(e.target.checked)}
            />
            <span
              className="font-pixel"
              style={{
                color: "var(--text-primary)",
                fontSize: 12,
                letterSpacing: "0.14em",
                textTransform: "uppercase",
              }}
            >
              Показывать score header
            </span>
          </label>
        </div>

        {/* Сам DuelChat — фикс. высота для удобства просмотра */}
        <div style={{ height: 720 }}>
          <DuelChat
            messages={messages}
            myRole={myRole}
            input={input}
            onInputChange={setInput}
            onSend={handleSend}
            opponentStatus={opponentStatus}
            scores={
              showScores
                ? { selling_score: 73, acting_score: 68, legal_accuracy: 91 }
                : null
            }
            selfTier={selfTier}
            opponentTier={opponentTier}
          />
        </div>

        {/* Hint */}
        <footer
          className="font-pixel"
          style={{
            color: "var(--text-muted)",
            fontSize: 11,
            letterSpacing: "0.12em",
            textTransform: "uppercase",
          }}
        >
          Tip: отправь сообщение — увидишь typewriter-печать AI-ответа через 1.4s.
        </footer>
      </div>
    </div>
  );
}

function ControlSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: readonly string[];
  onChange: (v: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span
        className="font-pixel"
        style={{
          color: "var(--text-muted)",
          fontSize: 10,
          letterSpacing: "0.18em",
          textTransform: "uppercase",
        }}
      >
        {label}
      </span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="font-pixel"
        style={{
          background: "var(--bg-secondary)",
          color: "var(--text-primary)",
          border: "2px solid var(--accent)",
          borderRadius: 0,
          padding: "6px 8px",
          fontSize: 13,
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          boxShadow: "2px 2px 0 0 var(--accent)",
        }}
      >
        {options.map((opt) => (
          <option key={opt} value={opt}>
            {opt}
          </option>
        ))}
      </select>
    </label>
  );
}
