"use client";

/**
 * /dev/matchmaking-preview — превью Фазы 7 (MatchmakingOverlay).
 *
 * 2026-04-30: пиксельный поиск соперника + VS reveal без backend.
 */

import * as React from "react";
import { motion } from "framer-motion";
import { ArenaBackground } from "@/components/pvp/ArenaBackground";
import { MatchmakingOverlay } from "@/components/pvp/MatchmakingOverlay";

export default function MatchmakingPreviewPage() {
  const [open, setOpen] = React.useState(false);
  const [status, setStatus] = React.useState<"searching" | "matched">("searching");
  const [opponentRating, setOpponentRating] = React.useState<number | undefined>(1547);
  const [estimatedWait, setEstimatedWait] = React.useState(60);

  const launchSearch = (rating?: number) => {
    setOpponentRating(rating);
    setEstimatedWait(60);
    setStatus("searching");
    setOpen(true);
    // Auto-transition to matched после 4s для демо
    window.setTimeout(() => setStatus("matched"), 4000);
  };

  return (
    <ArenaBackground tier="gold" className="min-h-screen px-4 py-6 sm:px-8 sm:py-10">
      <div className="relative mx-auto max-w-4xl space-y-6">
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
            Фаза 7 — Matchmaking
          </h1>
          <p
            className="mt-2 font-pixel"
            style={{ color: "var(--text-muted)", fontSize: 14, letterSpacing: "0.1em" }}
          >
            MatchmakingOverlay в пиксельном стиле. Searching → Matched через 4s (demo timing).
          </p>
        </header>

        <section
          className="space-y-3 p-5"
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
            ▸ Сценарии
          </h2>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <PixelBtn onClick={() => launchSearch(1547)}>PvP HUNTER 1547</PixelBtn>
            <PixelBtn onClick={() => launchSearch(undefined)}>PvE BOT</PixelBtn>
            <PixelBtn
              onClick={() => {
                setOpen(true);
                setStatus("searching");
                setEstimatedWait(15);
                // Останется в searching state до отмены
              }}
            >
              ↻ Searching only
            </PixelBtn>
          </div>
        </section>

        {open && (
          <MatchmakingOverlay
            status={status}
            position={3}
            estimatedWait={estimatedWait}
            opponentRating={opponentRating}
            onCancel={() => setOpen(false)}
          />
        )}
      </div>
    </ArenaBackground>
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
        padding: "8px 16px",
        background: "var(--bg-secondary)",
        color: "var(--accent)",
        border: "2px solid var(--accent)",
        borderRadius: 0,
        fontSize: 13,
        letterSpacing: "0.14em",
        textTransform: "uppercase",
        boxShadow: "3px 3px 0 0 var(--accent)",
        cursor: "pointer",
      }}
    >
      {children}
    </motion.button>
  );
}
