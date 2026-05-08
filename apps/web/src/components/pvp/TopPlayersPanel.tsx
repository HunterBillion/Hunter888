"use client";

/**
 * TopPlayersPanel — left-sidebar widget «Топ-3 сезона».
 *
 * PR-16 (2026-05-07): /pvp lobby получил 3-column layout. Эта панель
 * живёт в левом сайдбаре сверху, использует существующий
 * `usePvPStore.fetchLeaderboard()` (limit=3) и рендерит компактные
 * чипы с rank-medal + name + rating.
 *
 * Реактивно: после каждого own-finalize дуэли (queueStatus → idle
 * после matched) перетягиваем leaderboard.
 */

import { useEffect } from "react";
import { motion } from "framer-motion";
import { Crown, Trophy, Medal, Loader2 } from "lucide-react";
import { usePvPStore } from "@/stores/usePvPStore";

export function TopPlayersPanel() {
  const leaderboard = usePvPStore((s) => s.leaderboard);
  const loading = usePvPStore((s) => s.leaderboardLoading);
  const fetch = usePvPStore((s) => s.fetchLeaderboard);

  useEffect(() => {
    fetch(undefined, 3);
    // refresh once a minute — leaderboard moves slowly
    const id = window.setInterval(() => fetch(undefined, 3), 60_000);
    return () => window.clearInterval(id);
  }, [fetch]);

  const top3 = leaderboard.slice(0, 3);
  const medalIcons = [Crown, Trophy, Medal];
  const medalColors = ["#facc15", "#cbd5e1", "#cd7f32"];

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
      aria-label="Топ-3 сезона"
    >
      <div
        className="font-pixel uppercase tracking-widest mb-3 flex items-center gap-2"
        style={{ color: "var(--accent)", fontSize: 13, letterSpacing: "0.16em" }}
      >
        <Trophy size={15} />
        ТОП-3 СЕЗОНА
      </div>

      {loading && top3.length === 0 ? (
        <div className="flex items-center justify-center py-4">
          <Loader2 size={14} className="animate-spin" style={{ color: "var(--text-muted)" }} />
        </div>
      ) : top3.length === 0 ? (
        <div
          className="font-pixel text-[12px] uppercase tracking-wider py-3 text-center"
          style={{ color: "var(--text-muted)", letterSpacing: "0.14em" }}
        >
          Сезон только начался
        </div>
      ) : (
        <ul className="flex flex-col gap-2">
          {top3.map((p, i) => {
            const Icon = medalIcons[i] ?? Medal;
            const color = medalColors[i] ?? "var(--text-muted)";
            return (
              <motion.li
                key={p.user_id}
                initial={{ opacity: 0, x: -4 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.04 }}
                className="flex items-center gap-2 px-2 py-1.5"
                style={{
                  background: i === 0 ? "color-mix(in srgb, #facc15 8%, transparent)" : "transparent",
                  border: `1px solid ${i === 0 ? "color-mix(in srgb, #facc15 30%, transparent)" : "var(--border-color)"}`,
                  borderRadius: 0,
                }}
              >
                <Icon size={16} style={{ color, flexShrink: 0 }} />
                <span
                  className="text-[13px] truncate flex-1"
                  style={{ color: "var(--text-primary)" }}
                  title={p.username || ""}
                >
                  {p.username || `user-${p.user_id.slice(0, 6)}`}
                </span>
                <span
                  className="font-pixel text-[13px] tabular-nums"
                  style={{ color, letterSpacing: "0.04em" }}
                >
                  {Math.round(p.rating)}
                </span>
              </motion.li>
            );
          })}
        </ul>
      )}

      {/*
        2026-05-08: ссылка ведёт на новый «Зал Славы», конкретно на
        АРЕНА IV · ДУЭЛИ (через якорь #stage-duels). Раньше указывала
        на `/pvp/leaderboard` — отдельная страница, которая стала
        дубликатом раздела «Дуэли» в /leaderboard и теперь
        перенаправляется. Используем `<a>` (не `<Link>`), потому что
        Next.js Link не реагирует на чистые hash-якоря, если pathname
        меняется одновременно — браузерный native href справляется
        надёжнее и сразу скроллит к секции.
      */}
      <a
        href="/leaderboard#stage-duels"
        className="mt-3 block text-center font-pixel uppercase text-[12px] tracking-widest py-2 transition-colors hover:bg-[var(--input-bg)]"
        style={{
          color: "var(--text-muted)",
          border: "1px dashed var(--border-color)",
          letterSpacing: "0.18em",
          textDecoration: "none",
        }}
      >
        Полный лидерборд →
      </a>
    </section>
  );
}
