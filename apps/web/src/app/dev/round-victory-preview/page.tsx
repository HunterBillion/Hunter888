"use client";

/**
 * /dev/round-victory-preview — превью Фаз 4 + 5.
 *
 * 2026-04-30: создана для визуального ревью без backend / WS / auth.
 * Тестим RoundIndicator (Фаза 4) и PvPVictoryScreen (Фаза 5).
 */

import * as React from "react";
import { motion } from "framer-motion";
import { ArenaBackground } from "@/components/pvp/ArenaBackground";
import { RoundIndicator } from "@/components/pvp/RoundIndicator";
import { PvPVictoryScreen } from "@/components/pvp/PvPVictoryScreen";
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

export default function RoundVictoryPreviewPage() {
  /* ── Round indicator state ───────────────────────────── */
  const [tier, setTier] = React.useState<PvPRankTier>("gold");
  const [time, setTime] = React.useState(120);
  const [round, setRound] = React.useState(1);
  const [role, setRole] = React.useState<"seller" | "client">("seller");
  const [running, setRunning] = React.useState(false);

  React.useEffect(() => {
    if (!running) return;
    const id = window.setInterval(() => {
      setTime((t) => Math.max(0, t - 1));
    }, 1000);
    return () => window.clearInterval(id);
  }, [running]);

  /* ── Victory screen state ────────────────────────────── */
  const [vsOpen, setVsOpen] = React.useState(false);
  const [vsConfig, setVsConfig] = React.useState<{
    isWinner: boolean;
    isDraw: boolean;
    delta: number;
    promotion: boolean;
  }>({ isWinner: true, isDraw: false, delta: 37, promotion: false });

  const launchVs = (
    isWinner: boolean,
    isDraw: boolean,
    delta: number,
    promotion = false,
  ) => {
    setVsConfig({ isWinner, isDraw, delta, promotion });
    setVsOpen(true);
  };

  return (
    <ArenaBackground tier={tier} className="min-h-screen px-4 py-6 sm:px-8 sm:py-10">
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
            Фазы 4 + 5
          </h1>
          <p
            className="mt-2 font-pixel"
            style={{ color: "var(--text-muted)", fontSize: 14, letterSpacing: "0.1em" }}
          >
            RoundIndicator (пиксельный таймер с тиканьем) + PvPVictoryScreen (4-фазный reveal)
          </p>
        </header>

        {/* ═══ Round Indicator демо ═══ */}
        <section
          className="space-y-4 p-5"
          style={{
            background: "var(--bg-panel)",
            outline: "2px solid var(--accent)",
            outlineOffset: -2,
            boxShadow: "4px 4px 0 0 var(--accent)",
          }}
        >
          <h2
            className="font-pixel"
            style={{
              color: "var(--text-primary)",
              fontSize: 18,
              letterSpacing: "0.18em",
              textTransform: "uppercase",
            }}
          >
            ▸ Round Indicator
          </h2>
          <ChipGroup
            label="Тир (цвет ring)"
            value={tier}
            options={TIERS}
            renderLabel={(t) => PVP_RANK_LABELS[normalizeRankTier(t)] ?? t}
            onChange={(v) => setTier(v as PvPRankTier)}
          />
          <ChipGroup
            label="Раунд"
            value={String(round)}
            options={["0", "1", "2"]}
            renderLabel={(r) => (r === "0" ? "Смена ролей" : `Раунд ${r}`)}
            onChange={(v) => setRound(Number(v))}
          />
          <ChipGroup
            label="Твоя роль"
            value={role}
            options={["seller", "client"]}
            renderLabel={(r) => (r === "seller" ? "Менеджер" : "Клиент")}
            onChange={(v) => setRole(v as "seller" | "client")}
          />

          <div>
            <div
              className="font-pixel mb-2"
              style={{ color: "var(--text-muted)", fontSize: 12, letterSpacing: "0.18em", textTransform: "uppercase" }}
            >
              Времени осталось: {time}с
            </div>
            <input
              type="range"
              min={0}
              max={180}
              value={time}
              onChange={(e) => setTime(Number(e.target.value))}
              className="w-full"
            />
          </div>

          <div className="flex flex-wrap gap-3 pt-3" style={{ borderTop: "2px dashed var(--accent-muted)" }}>
            <PixelBtn onClick={() => setRunning((r) => !r)}>
              {running ? "❚❚ Пауза тикера" : "▶ Запустить тикер"}
            </PixelBtn>
            <PixelBtn onClick={() => setTime(180)}>↻ 3:00</PixelBtn>
            <PixelBtn onClick={() => setTime(30)}>⚠ 0:30 (warning)</PixelBtn>
            <PixelBtn onClick={() => setTime(8)}>🔥 0:08 (danger pulse)</PixelBtn>
          </div>

          <div className="pt-3">
            <RoundIndicator
              roundNumber={round}
              myRole={role}
              timeRemaining={time}
              totalSeconds={180}
              tierColor={tierAccent(tier)}
            />
          </div>
        </section>

        {/* ═══ Victory Screen демо ═══ */}
        <section
          className="space-y-4 p-5"
          style={{
            background: "var(--bg-panel)",
            outline: "2px solid var(--accent)",
            outlineOffset: -2,
            boxShadow: "4px 4px 0 0 var(--accent)",
          }}
        >
          <h2
            className="font-pixel"
            style={{
              color: "var(--text-primary)",
              fontSize: 18,
              letterSpacing: "0.18em",
              textTransform: "uppercase",
            }}
          >
            ▸ Victory Screen
          </h2>
          <p
            style={{ color: "var(--text-muted)", fontSize: 13 }}
          >
            4-фазный reveal: KO!-flash → count-up очков → ELO-дельта → details. Skip
            ▶▶ в правом верхнем углу пропускает к деталям. Если уже нажимал Skip —
            следующий бой стартует с Phase 4 (флаг в localStorage).
          </p>

          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <PixelBtn onClick={() => launchVs(true, false, 37)}>VICTORY +37</PixelBtn>
            <PixelBtn onClick={() => launchVs(true, false, 52, true)}>FLAWLESS + Promo</PixelBtn>
            <PixelBtn onClick={() => launchVs(false, true, 0)}>DRAW</PixelBtn>
            <PixelBtn onClick={() => launchVs(false, false, -28)}>DEFEAT -28</PixelBtn>
            <PixelBtn
              onClick={() => {
                try { localStorage.removeItem("pvp_victory_skip_intro"); } catch {}
                alert("Skip-флаг сброшен — следующий VS пройдёт через все 4 фазы");
              }}
            >
              ↻ Сбросить skip
            </PixelBtn>
          </div>
        </section>

        {vsOpen && (
          <PvPVictoryScreen
            key={`vs-${vsConfig.delta}-${vsConfig.isWinner}-${vsConfig.promotion}`}
            isWinner={vsConfig.isWinner}
            isDraw={vsConfig.isDraw}
            myScore={vsConfig.isWinner ? 247 : vsConfig.isDraw ? 130 : 92}
            opponentScore={vsConfig.isWinner ? 168 : vsConfig.isDraw ? 130 : 198}
            ratingDelta={vsConfig.delta}
            prevRating={1450}
            myTier={tier}
            newTier={vsConfig.promotion ? "platinum" : tier}
            prevTier={tier}
            onContinue={() => setVsOpen(false)}
          />
        )}
      </div>
    </ArenaBackground>
  );
}

function tierAccent(tier: PvPRankTier): string {
  const map: Record<PvPRankTier, string> = {
    unranked: "var(--text-muted)",
    iron: "var(--text-muted)",
    bronze: "#B45309",
    silver: "var(--text-muted)",
    gold: "var(--warning)",
    platinum: "#22D3EE",
    diamond: "var(--info)",
    master: "var(--danger)",
    grandmaster: "#FF6B35",
  };
  return map[tier] ?? "var(--accent)";
}

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
              className="font-pixel"
              style={{
                padding: "6px 12px",
                background: active ? "var(--accent)" : "var(--bg-secondary)",
                color: active ? "#fff" : "var(--text-primary)",
                border: `2px solid ${active ? "var(--accent)" : "var(--border-color)"}`,
                borderRadius: 0,
                fontSize: 12,
                letterSpacing: "0.12em",
                textTransform: "uppercase",
                boxShadow: active
                  ? "3px 3px 0 0 #000, 0 0 12px var(--accent-glow)"
                  : "2px 2px 0 0 var(--border-color)",
                cursor: "pointer",
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

function PixelBtn({
  onClick,
  children,
}: {
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <motion.button
      type="button"
      onClick={onClick}
      whileHover={{ x: -1, y: -1 }}
      whileTap={{ x: 2, y: 2 }}
      className="font-pixel"
      style={{
        padding: "7px 14px",
        background: "var(--bg-secondary)",
        color: "var(--accent)",
        border: "2px solid var(--accent)",
        borderRadius: 0,
        fontSize: 12,
        letterSpacing: "0.12em",
        textTransform: "uppercase",
        boxShadow: "3px 3px 0 0 var(--accent)",
        cursor: "pointer",
      }}
    >
      {children}
    </motion.button>
  );
}
