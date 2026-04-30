"use client";

/**
 * /dev/arena-tiers-preview — превью Фазы 6 (8 биомов арены по тирам).
 *
 * Каждый из 8 рангов рендерится как отдельная мини-арена с FighterCard
 * парой внутри — чтобы был контекст «как это будет выглядеть в дуэли».
 */

import * as React from "react";
import { ArenaBackground } from "@/components/pvp/ArenaBackground";
import { FighterCard } from "@/components/pvp/FighterCard";
import { type PvPRankTier, PVP_RANK_LABELS } from "@/types";

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

export default function ArenaTiersPreviewPage() {
  return (
    <div
      className="min-h-screen px-4 py-6 sm:px-8 sm:py-10"
      style={{ background: "var(--bg-primary)" }}
    >
      <div className="mx-auto max-w-5xl space-y-8">
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
            Арены по тирам — Фаза 6
          </h1>
          <p
            className="mt-2 font-pixel"
            style={{ color: "var(--text-muted)", fontSize: 14, letterSpacing: "0.1em" }}
          >
            8 уникальных биомов через CSS-композицию (без PNG-ассетов).
          </p>
        </header>

        <div className="grid gap-6 sm:grid-cols-2">
          {TIERS.map((tier) => (
            <ArenaBackground
              key={tier}
              tier={tier}
              className="overflow-hidden"
              style={{
                outline: "2px solid var(--border-color)",
                outlineOffset: -2,
                boxShadow: "3px 3px 0 0 var(--border-color)",
                minHeight: 280,
              }}
            >
              <div className="relative p-4 sm:p-5 flex flex-col gap-4 h-full">
                {/* Tier label top-left */}
                <div
                  className="font-pixel"
                  style={{
                    color: "var(--text-primary)",
                    fontSize: 14,
                    letterSpacing: "0.18em",
                    textTransform: "uppercase",
                    textShadow: "2px 2px 0 #000",
                  }}
                >
                  {PVP_RANK_LABELS[tier]}
                </div>

                {/* Two fighters with VS in middle */}
                <div className="flex items-center gap-2 mt-auto">
                  <FighterCard
                    side="left"
                    name="Игрок"
                    tier={tier}
                    role="seller"
                    hp={75}
                    active
                  />
                  <span
                    className="font-pixel"
                    style={{
                      color: "var(--accent)",
                      fontSize: 18,
                      letterSpacing: "-0.05em",
                      textShadow: "2px 2px 0 #000, 0 0 8px var(--accent-glow)",
                    }}
                  >
                    VS
                  </span>
                  <FighterCard
                    side="right"
                    name="Бот"
                    tier={tier}
                    role="client"
                    hp={45}
                    isBot
                  />
                </div>
              </div>
            </ArenaBackground>
          ))}
        </div>
      </div>
    </div>
  );
}
