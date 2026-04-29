"use client";

/**
 * /dev/duel-chat-preview — demo-страница нового пиксельного DuelChat.
 *
 * 2026-04-29 polish:
 *  - <select> заменены на единые pixel-chip groups (4 панели одного формата).
 *  - Убран «Tip:» и подсказка про Enter (по запросу).
 *  - Добавлен arena-grid фон + parallax-туман.
 *  - autoFocus в инпут чата при заходе.
 *
 * НЕ ИСПОЛЬЗУЕТСЯ В ПРОДЕ — middleware закрывает /dev/* в production
 * после Фазы 7. Сейчас открыто для визуального ревью.
 */

import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { DuelChat } from "@/components/pvp/DuelChat";
import { type PvPRankTier, PVP_RANK_LABELS, normalizeRankTier } from "@/types";

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
const STATUS_LABELS: Record<ConnectionStatus, string> = {
  online: "Онлайн",
  typing: "Печатает",
  offline: "Офлайн",
  reconnecting: "Реконнект",
};

const ROLES: Array<"seller" | "client"> = ["seller", "client"];
const ROLE_LABELS: Record<"seller" | "client", string> = {
  seller: "Менеджер",
  client: "Клиент",
};

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

const AI_REPLIES = [
  "Понятно. Давайте уточним детали — сколько кредиторов и есть ли исполнительные производства?",
  "А приставы уже что-то взыскали? И вы официально работаете сейчас?",
  "По единственному жилью — оно за вами без обременений? Ипотеки нет?",
  "Хорошо. Тогда следующий шаг — собрать документы. Готовы их предоставить в течение недели?",
];

export default function DuelChatPreviewPage() {
  const [messages, setMessages] = useState<Message[]>(SAMPLE_MESSAGES);
  const [input, setInput] = useState("");
  const [opponentStatus, setOpponentStatus] = useState<ConnectionStatus>("typing");
  const [selfTier, setSelfTier] = useState<PvPRankTier>("gold");
  const [opponentTier, setOpponentTier] = useState<PvPRankTier>("platinum");
  const [showScores, setShowScores] = useState(true);
  const [myRole, setMyRole] = useState<"seller" | "client">("seller");
  const [deliveredIds, setDeliveredIds] = useState<string[]>([]);
  const replyIdxRef = useRef(0);

  const handleSend = () => {
    if (!input.trim()) return;
    const myMsg: Message = {
      id: `m${Date.now()}`,
      sender_role: myRole,
      text: input.trim(),
      round: messages[messages.length - 1]?.round ?? 1,
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, myMsg]);
    setInput("");
    // delivered ack через 350мс — для демо ✓
    window.setTimeout(() => {
      setDeliveredIds((prev) => [...prev, myMsg.id]);
    }, 350);

    setOpponentStatus("typing");
    window.setTimeout(() => {
      const reply = AI_REPLIES[replyIdxRef.current % AI_REPLIES.length];
      replyIdxRef.current += 1;
      setMessages((prev) => [
        ...prev,
        {
          id: `m${Date.now()}-ai`,
          sender_role: myRole === "seller" ? "client" : "seller",
          text: reply,
          round: prev[prev.length - 1]?.round ?? 1,
          timestamp: new Date().toISOString(),
        },
      ]);
      setOpponentStatus("online");
    }, 1400);
  };

  return (
    <div
      className="relative min-h-screen px-4 py-6 sm:px-8 sm:py-10"
      style={{
        background: "var(--bg-primary)",
        backgroundImage: [
          // верхний свет «арены»
          "radial-gradient(ellipse 80% 50% at 50% 0%, color-mix(in srgb, var(--accent) 12%, transparent), transparent 65%)",
          // pixel-grid сетка
          "repeating-linear-gradient(0deg, transparent 0, transparent 23px, color-mix(in srgb, var(--accent) 10%, transparent) 23px, color-mix(in srgb, var(--accent) 10%, transparent) 24px)",
          "repeating-linear-gradient(90deg, transparent 0, transparent 23px, color-mix(in srgb, var(--accent) 10%, transparent) 23px, color-mix(in srgb, var(--accent) 10%, transparent) 24px)",
        ].join(", "),
      }}
    >
      {/* Декоративный parallax-fog поверх grid */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          backgroundImage:
            "radial-gradient(ellipse 60% 40% at 30% 20%, var(--accent-glow), transparent 70%), radial-gradient(ellipse 50% 35% at 75% 75%, color-mix(in srgb, var(--magenta) 25%, transparent), transparent 70%)",
          opacity: 0.6,
          mixBlendMode: "screen",
        }}
      />

      <div className="relative mx-auto max-w-5xl space-y-6">
        <header>
          <h1
            className="font-pixel"
            style={{
              color: "var(--text-primary)",
              fontSize: 32,
              letterSpacing: "0.18em",
              textTransform: "uppercase",
              lineHeight: 1.05,
            }}
          >
            DuelChat — Превью
          </h1>
          <p
            className="mt-2 font-pixel"
            style={{
              color: "var(--text-muted)",
              fontSize: 14,
              letterSpacing: "0.1em",
            }}
          >
            Демо Фазы 2 редизайна арены. Меняй тиры/статус — увидишь все состояния.
          </p>
        </header>

        {/* ═══ Унифицированная панель управления — 4 chip-group + checkbox ═══ */}
        <div
          className="space-y-4 p-5"
          style={{
            background: "var(--bg-panel)",
            outline: "2px solid var(--accent)",
            outlineOffset: -2,
            boxShadow: "4px 4px 0 0 var(--accent)",
          }}
        >
          <ChipGroup
            label="Твой тир"
            value={selfTier}
            options={TIERS}
            renderLabel={(t) => PVP_RANK_LABELS[normalizeRankTier(t)] ?? t}
            onChange={(v) => setSelfTier(v as PvPRankTier)}
          />
          <ChipGroup
            label="Тир соперника"
            value={opponentTier}
            options={TIERS}
            renderLabel={(t) => PVP_RANK_LABELS[normalizeRankTier(t)] ?? t}
            onChange={(v) => setOpponentTier(v as PvPRankTier)}
          />
          <ChipGroup
            label="Статус соперника"
            value={opponentStatus}
            options={STATUSES}
            renderLabel={(s) => STATUS_LABELS[s as ConnectionStatus]}
            onChange={(v) => setOpponentStatus(v as ConnectionStatus)}
          />
          <ChipGroup
            label="Твоя роль"
            value={myRole}
            options={ROLES}
            renderLabel={(r) => ROLE_LABELS[r as "seller" | "client"]}
            onChange={(v) => setMyRole(v as "seller" | "client")}
          />

          <div className="flex items-center gap-3 pt-2" style={{ borderTop: "2px dashed var(--accent-muted)" }}>
            <CheckboxToggle
              checked={showScores}
              onChange={setShowScores}
              label="Score header"
            />
            <CheckboxToggle
              checked={messages.length > 5}
              onChange={(v) => {
                if (v) {
                  // dummy не нужен — оставляю кнопку «сбросить» вместо этого
                }
                if (!v) {
                  setMessages(SAMPLE_MESSAGES);
                  setDeliveredIds([]);
                  replyIdxRef.current = 0;
                }
              }}
              label="Сбросить чат"
              invertedSemantic
            />
          </div>
        </div>

        {/* DuelChat */}
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
            deliveredIds={deliveredIds}
            autoFocus
          />
        </div>
      </div>
    </div>
  );
}

/* ── Pixel chip group ───────────────────────────────────── */
function ChipGroup({
  label,
  value,
  options,
  renderLabel,
  onChange,
}: {
  label: string;
  value: string;
  options: readonly string[];
  renderLabel: (v: string) => string;
  onChange: (v: string) => void;
}) {
  return (
    <div>
      <div
        className="font-pixel mb-2"
        style={{
          color: "var(--text-muted)",
          fontSize: 12,
          letterSpacing: "0.18em",
          textTransform: "uppercase",
        }}
      >
        {label}
      </div>
      <div className="flex flex-wrap gap-2">
        {options.map((opt) => {
          const active = opt === value;
          return (
            <motion.button
              key={opt}
              type="button"
              onClick={() => onChange(opt)}
              whileHover={active ? {} : { x: -1, y: -1 }}
              whileTap={{ x: 2, y: 2 }}
              transition={{ type: "spring", stiffness: 600, damping: 30 }}
              className="font-pixel"
              style={{
                padding: "7px 14px",
                background: active ? "var(--accent)" : "var(--bg-secondary)",
                color: active ? "#fff" : "var(--text-primary)",
                border: `2px solid ${active ? "var(--accent)" : "var(--border-color)"}`,
                borderRadius: 0,
                fontSize: 13,
                letterSpacing: "0.12em",
                textTransform: "uppercase",
                boxShadow: active
                  ? "3px 3px 0 0 #000, 0 0 12px var(--accent-glow)"
                  : "2px 2px 0 0 var(--border-color)",
                cursor: "pointer",
                transition: "background 120ms, color 120ms",
              }}
            >
              {renderLabel(opt)}
            </motion.button>
          );
        })}
      </div>
    </div>
  );
}

/* ── Pixel checkbox-toggle (для score header / reset) ───── */
function CheckboxToggle({
  checked,
  onChange,
  label,
  invertedSemantic = false,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  /** Если true — кнопка работает «one-shot»: клик выключает (для «сбросить»). */
  invertedSemantic?: boolean;
}) {
  // For checkboxes we keep stable visual; for invertedSemantic — простая кнопка.
  if (invertedSemantic) {
    return (
      <motion.button
        type="button"
        onClick={() => onChange(false)}
        whileHover={{ x: -1, y: -1 }}
        whileTap={{ x: 2, y: 2 }}
        className="font-pixel"
        style={{
          padding: "6px 14px",
          background: "transparent",
          color: "var(--text-muted)",
          border: "2px solid var(--border-color)",
          borderRadius: 0,
          fontSize: 12,
          letterSpacing: "0.14em",
          textTransform: "uppercase",
          boxShadow: "2px 2px 0 0 var(--border-color)",
          cursor: "pointer",
        }}
      >
        ↻ {label}
      </motion.button>
    );
  }

  return (
    <motion.button
      type="button"
      onClick={() => onChange(!checked)}
      whileHover={{ x: -1, y: -1 }}
      whileTap={{ x: 2, y: 2 }}
      className="font-pixel inline-flex items-center gap-2"
      aria-pressed={checked}
      style={{
        padding: "6px 14px",
        background: checked ? "var(--accent-muted)" : "transparent",
        color: checked ? "var(--accent)" : "var(--text-muted)",
        border: `2px solid ${checked ? "var(--accent)" : "var(--border-color)"}`,
        borderRadius: 0,
        fontSize: 12,
        letterSpacing: "0.14em",
        textTransform: "uppercase",
        boxShadow: checked
          ? "2px 2px 0 0 var(--accent)"
          : "2px 2px 0 0 var(--border-color)",
        cursor: "pointer",
      }}
    >
      <span
        aria-hidden
        style={{
          display: "inline-block",
          width: 10,
          height: 10,
          background: checked ? "var(--accent)" : "transparent",
          border: `2px solid ${checked ? "var(--accent)" : "var(--border-color)"}`,
        }}
      />
      {label}
    </motion.button>
  );
}
