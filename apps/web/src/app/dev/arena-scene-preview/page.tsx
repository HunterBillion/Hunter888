"use client";

/**
 * /dev/arena-scene-preview — превью Фазы 3: ArenaBackground + FighterCard
 * + HPBar + VsBanner.
 *
 * 2026-04-29: создана для визуального ревью без backend / WS / auth.
 * Закроется в production после Фазы 7 (см. middleware.ts).
 */

import * as React from "react";
import { motion } from "framer-motion";
import { ArenaBackground } from "@/components/pvp/ArenaBackground";
import { FighterCard } from "@/components/pvp/FighterCard";
import { VsBanner } from "@/components/pvp/VsBanner";
import { HPBar } from "@/components/pvp/HPBar";
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

export default function ArenaScenePreviewPage() {
  const [bgTier, setBgTier] = React.useState<PvPRankTier>("gold");
  const [leftTier, setLeftTier] = React.useState<PvPRankTier>("gold");
  const [rightTier, setRightTier] = React.useState<PvPRankTier>("platinum");
  const [leftHp, setLeftHp] = React.useState(78);
  const [rightHp, setRightHp] = React.useState(54);
  const [activeSide, setActiveSide] = React.useState<"left" | "right">("left");
  const [vsOpen, setVsOpen] = React.useState(false);

  return (
    <ArenaBackground tier={bgTier} className="min-h-screen px-4 py-6 sm:px-8 sm:py-10">
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
            Arena Scene — Фаза 3
          </h1>
          <p
            className="mt-2 font-pixel"
            style={{ color: "var(--text-muted)", fontSize: 14, letterSpacing: "0.1em" }}
          >
            ArenaBackground · FighterCard · HPBar · VsBanner. Демо без backend.
          </p>
        </header>

        {/* Controls */}
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
            label="Тир арены (фон)"
            value={bgTier}
            options={TIERS}
            renderLabel={(t) => PVP_RANK_LABELS[normalizeRankTier(t)] ?? t}
            onChange={(v) => setBgTier(v as PvPRankTier)}
          />
          <ChipGroup
            label="Левый боец — тир"
            value={leftTier}
            options={TIERS}
            renderLabel={(t) => PVP_RANK_LABELS[normalizeRankTier(t)] ?? t}
            onChange={(v) => setLeftTier(v as PvPRankTier)}
          />
          <ChipGroup
            label="Правый боец — тир"
            value={rightTier}
            options={TIERS}
            renderLabel={(t) => PVP_RANK_LABELS[normalizeRankTier(t)] ?? t}
            onChange={(v) => setRightTier(v as PvPRankTier)}
          />
          <ChipGroup
            label="Активный боец"
            value={activeSide}
            options={["left", "right"]}
            renderLabel={(s) => (s === "left" ? "Левый" : "Правый")}
            onChange={(v) => setActiveSide(v as "left" | "right")}
          />

          <div className="grid sm:grid-cols-2 gap-4">
            <div>
              <div className="font-pixel mb-2" style={{ color: "var(--text-muted)", fontSize: 12, letterSpacing: "0.18em", textTransform: "uppercase" }}>
                Левый HP: {leftHp}
              </div>
              <input
                type="range"
                min={0}
                max={100}
                value={leftHp}
                onChange={(e) => setLeftHp(Number(e.target.value))}
                className="w-full"
                aria-label="Левый HP"
              />
            </div>
            <div>
              <div className="font-pixel mb-2" style={{ color: "var(--text-muted)", fontSize: 12, letterSpacing: "0.18em", textTransform: "uppercase" }}>
                Правый HP: {rightHp}
              </div>
              <input
                type="range"
                min={0}
                max={100}
                value={rightHp}
                onChange={(e) => setRightHp(Number(e.target.value))}
                className="w-full"
                aria-label="Правый HP"
              />
            </div>
          </div>

          <div className="flex flex-wrap gap-3 pt-2" style={{ borderTop: "2px dashed var(--accent-muted)" }}>
            <PixelActionBtn onClick={() => setVsOpen(true)}>▶ Запустить VS-баннер</PixelActionBtn>
            <PixelActionBtn onClick={() => { setLeftHp(100); setRightHp(100); }}>↻ Сбросить HP</PixelActionBtn>
            <PixelActionBtn onClick={() => { setLeftHp(20); setRightHp(15); }}>⚠ Низкий HP (тест pulse)</PixelActionBtn>
          </div>
        </div>

        {/* Сцена */}
        <div className="flex flex-col sm:flex-row items-stretch justify-between gap-3">
          <FighterCard
            side="left"
            name="Дмитрий"
            tier={leftTier}
            role="seller"
            hp={leftHp}
            active={activeSide === "left"}
          />
          <div className="flex items-center justify-center px-4">
            <span
              className="font-pixel"
              style={{
                color: "var(--accent)",
                fontSize: 28,
                letterSpacing: "-0.05em",
                textShadow: "3px 3px 0 #000, 0 0 12px var(--accent-glow)",
              }}
            >
              VS
            </span>
          </div>
          <FighterCard
            side="right"
            name="AI-БОРИС"
            tier={rightTier}
            role="client"
            hp={rightHp}
            isBot
            active={activeSide === "right"}
          />
        </div>

        {/* HPBar showcase */}
        <div
          className="p-5 space-y-3"
          style={{
            background: "var(--bg-panel)",
            outline: "2px solid var(--border-color)",
            outlineOffset: -2,
            boxShadow: "3px 3px 0 0 var(--border-color)",
          }}
        >
          <div
            className="font-pixel"
            style={{ color: "var(--text-muted)", fontSize: 12, letterSpacing: "0.18em", textTransform: "uppercase" }}
          >
            HPBar — все состояния
          </div>
          {[100, 80, 50, 25, 5].map((v) => (
            <div key={v} className="flex items-center gap-3">
              <span className="font-pixel" style={{ color: "var(--text-muted)", fontSize: 12, width: 50 }}>
                {v}%
              </span>
              <HPBar value={v} tierColor="var(--accent)" width={300} />
            </div>
          ))}
        </div>

        <VsBanner
          open={vsOpen}
          leftName="Дмитрий"
          rightName="AI-Борис"
          leftTier={leftTier}
          rightTier={rightTier}
          onDone={() => setVsOpen(false)}
        />
      </div>
    </ArenaBackground>
  );
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

function PixelActionBtn({
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
        fontSize: 13,
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
