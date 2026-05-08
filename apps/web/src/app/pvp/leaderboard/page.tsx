"use client";

/**
 * /pvp/leaderboard — DEPRECATED.
 *
 * 2026-05-08: страница удалена и заменена редиректом. Раньше это была
 * отдельная панель с топом сезона + историей дуэлей, которая визуально
 * дублировала раздел «Дуэли» в `/leaderboard`. После аркадного
 * редизайна `/leaderboard` («Зал Славы») — все 4 таба свёрнуты в одну
 * скроллящуюся страницу с якорной навигацией. PvP-leaderboard теперь
 * живёт там как `АРЕНА IV · ДУЭЛИ`.
 *
 * Любая ссылка / закладка на `/pvp/leaderboard` (а также со старыми
 * query-параметрами вроде `?tab=history`) ведёт на якорь
 * `/leaderboard#stage-duels`. Используем client-side router.replace —
 * Next.js серверный `redirect()` не умеет добавлять hash fragment к
 * таргету, а нам нужен именно якорь, чтобы StageSelect сразу
 * подсветил Дуэли и страница проскроллила к секции.
 *
 * Замечу: 365-строчная старая реализация удалена целиком — её
 * функциональность полностью покрыта `LeagueTab`/`DuelsTab` внутри
 * нового `/leaderboard`. Если когда-то понадобится отдельный экран
 * сезонных наград — его надо строить заново на новых хелперах из
 * `apps/api/app/services/hunter_leaderboard.py`, а не откатываться к
 * этому файлу.
 */

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function PvPLeaderboardRedirect() {
  const router = useRouter();

  useEffect(() => {
    // router.replace сохраняет историю чище push() — пользователь,
    // нажав «назад», не вернётся на эту пустую страницу.
    router.replace("/leaderboard#stage-duels");
  }, [router]);

  // Минимальный fallback — на случай если JS отключён или редирект
  // занимает > 1 кадра. Текст уважает требование ≥ 14px шрифта.
  return (
    <div
      className="min-h-screen flex items-center justify-center"
      style={{ background: "var(--bg-primary)" }}
    >
      <div
        className="font-pixel uppercase tracking-widest text-center"
        style={{ color: "var(--text-muted)", fontSize: 16 }}
      >
        ▰ Перенаправление в Зал Славы… ▰
        <div style={{ fontSize: 14, marginTop: 8 }}>
          <a
            href="/leaderboard#stage-duels"
            style={{ color: "var(--accent)", textDecoration: "underline" }}
          >
            Открыть АРЕНА IV · ДУЭЛИ →
          </a>
        </div>
      </div>
    </div>
  );
}
