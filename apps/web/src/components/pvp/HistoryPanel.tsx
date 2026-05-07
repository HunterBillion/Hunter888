"use client";

/**
 * HistoryPanel — right-sidebar widget «Моя история» (компакт-5).
 *
 * PR-16 (2026-05-07). Использует `usePvPStore.myDuels` (уже фетчится в
 * /pvp/page.tsx с `?exclude_cancelled=true`). Показывает последние 5
 * завершённых дуэлей в плотном вертикальном списке. Клик — переход
 * на страницу дуэли.
 */

import { useMemo } from "react";
import { motion } from "framer-motion";
import { ArrowRight, Loader2, Sword } from "lucide-react";
import { useRouter } from "next/navigation";
import { usePvPStore } from "@/stores/usePvPStore";

const VERDICT_COLORS = {
  victory: "var(--success)",
  defeat: "var(--danger)",
  draw: "var(--warning)",
} as const;

export function HistoryPanel() {
  const router = useRouter();
  const myDuels = usePvPStore((s) => s.myDuels);
  const loading = usePvPStore((s) => s.duelsLoading);
  const myUserId = usePvPStore((s) => s.rating?.user_id);

  const top5 = useMemo(() => myDuels.slice(0, 5), [myDuels]);

  return (
    <section
      className="p-3"
      style={{
        background: "var(--bg-panel)",
        outline: "2px solid var(--accent)",
        outlineOffset: -2,
        boxShadow: "3px 3px 0 0 var(--accent)",
        borderRadius: 0,
      }}
      aria-label="История дуэлей"
    >
      <div
        className="font-pixel uppercase tracking-widest mb-3 flex items-center gap-2"
        style={{ color: "var(--accent)", fontSize: 11, letterSpacing: "0.16em" }}
      >
        <Sword size={13} />
        МОЯ ИСТОРИЯ
      </div>

      {loading && top5.length === 0 ? (
        <div className="flex items-center justify-center py-6">
          <Loader2 size={14} className="animate-spin" style={{ color: "var(--text-muted)" }} />
        </div>
      ) : top5.length === 0 ? (
        <div
          className="font-pixel text-[10px] uppercase tracking-wider py-4 text-center"
          style={{ color: "var(--text-muted)", letterSpacing: "0.14em" }}
        >
          Ещё нет дуэлей
        </div>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {top5.map((duel, i) => {
            const isP1 = myUserId === duel.player1_id;
            const myScore = isP1 ? duel.player1_total : duel.player2_total;
            const oppScore = isP1 ? duel.player2_total : duel.player1_total;
            const myDelta = isP1 ? duel.player1_rating_delta : duel.player2_rating_delta;
            const isWinner = duel.winner_id === myUserId;
            const ratingApplied = duel.rating_change_applied && !duel.is_pve;
            const verdict = duel.is_draw ? "draw" : isWinner ? "victory" : "defeat";
            const accent = VERDICT_COLORS[verdict];

            return (
              <motion.button
                key={duel.id}
                type="button"
                initial={{ opacity: 0, x: 4 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.04 }}
                onClick={() => router.push(`/pvp/duel/${duel.id}`)}
                whileHover={{ x: -1 }}
                className="w-full text-left flex items-center gap-2 px-2 py-1.5 transition-colors"
                style={{
                  background: "var(--bg-secondary, rgba(0,0,0,0.2))",
                  border: `1px solid ${accent}40`,
                  borderLeft: `3px solid ${accent}`,
                  borderRadius: 0,
                  cursor: "pointer",
                }}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span
                      className="font-pixel uppercase text-[10px]"
                      style={{ color: accent, letterSpacing: "0.12em" }}
                    >
                      {verdict === "victory" ? "Поб." : verdict === "draw" ? "Нич." : "Пор."}
                    </span>
                    {duel.is_pve && (
                      <span
                        className="font-pixel uppercase text-[8px] px-1"
                        style={{ color: "var(--warning)", border: "1px solid var(--warning)", letterSpacing: "0.1em" }}
                      >
                        PvE
                      </span>
                    )}
                  </div>
                  <div
                    className="font-pixel tabular-nums text-[10px] tracking-wider"
                    style={{ color: "var(--text-muted)" }}
                  >
                    {Math.round(myScore)}–{Math.round(oppScore)}
                  </div>
                </div>
                <div
                  className="font-pixel text-[11px] tabular-nums"
                  style={{
                    color: ratingApplied ? (myDelta >= 0 ? "var(--success)" : "var(--danger)") : "var(--text-muted)",
                  }}
                >
                  {ratingApplied ? `${myDelta >= 0 ? "+" : ""}${Math.round(myDelta)}` : "—"}
                </div>
                <ArrowRight size={10} style={{ color: "var(--text-muted)", flexShrink: 0 }} />
              </motion.button>
            );
          })}
        </ul>
      )}

      {myDuels.length > 5 && (
        <button
          type="button"
          onClick={() => router.push("/pvp/leaderboard?tab=history")}
          className="mt-3 block w-full text-center font-pixel uppercase text-[10px] tracking-widest py-1.5"
          style={{
            color: "var(--text-muted)",
            border: "1px dashed var(--border-color)",
            background: "transparent",
            letterSpacing: "0.18em",
            cursor: "pointer",
          }}
        >
          Все {myDuels.length} →
        </button>
      )}
    </section>
  );
}
