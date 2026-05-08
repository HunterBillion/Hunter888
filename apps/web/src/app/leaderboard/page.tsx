"use client";

/**
 * /leaderboard — «ЗАЛ СЛАВЫ», аркадный редизайн (2026-05-08).
 *
 * Что изменилось vs прошлой версии:
 *   - убран блок <h1>Лидерборд</h1> + описание (пользователь явно
 *     попросил снести как «мусор»)
 *   - убраны 4 pill-таба — теперь это единая страница со скроллом и
 *     якорной навигацией StageSelect (sticky сверху)
 *   - добавлена HeroPanel («карточка персонажа» в стиле файтинга)
 *   - между секциями — пиксельные разделители StageDivider
 *   - все 4 раздела (Лига / Компания / Команды / Дуэли) рисуются
 *     одновременно, по очереди, как «STAGE 1 → 4»
 *   - бэкенд НЕ трогался — каждая секция использует те же endpoints
 *
 * Старые ?tab=... query-параметры игнорируются — пользователь хотел
 * единое полотно, и шеринг конкретного раздела теперь делается через
 * якорь /leaderboard#stage-duels (отрабатывается StageSelect-ом).
 *
 * Шрифты ≥ 14px везде (требование пользователя).
 */

import { Suspense, type ReactNode } from "react";
import { Trophy } from "lucide-react";
import AuthLayout from "@/components/layout/AuthLayout";
import { HeroPanel } from "@/components/leaderboard/HeroPanel";
import { StageSelect } from "@/components/leaderboard/StageSelect";
import { StageDivider } from "@/components/leaderboard/StageDivider";
import { LeagueTab } from "@/components/leaderboard/LeagueTab";
import { CompanyTab } from "@/components/leaderboard/CompanyTab";
import { TeamsTab } from "@/components/leaderboard/TeamsTab";
import { DuelsTab } from "@/components/leaderboard/DuelsTab";

export default function LeaderboardPageWrapper() {
  return (
    <Suspense fallback={null}>
      <LeaderboardPage />
    </Suspense>
  );
}

function LeaderboardPage() {
  return (
    <AuthLayout>
      <div className="panel-grid-bg min-h-screen">
        <div className="app-page max-w-6xl">
          {/* ═══ ЗАЛ СЛАВЫ — главный логотип ═══ */}
          <div className="text-center pt-2 pb-6 select-none">
            <div
              className="font-pixel"
              style={{
                fontSize: "clamp(36px, 6vw, 64px)",
                lineHeight: 1.0,
                letterSpacing: "0.06em",
                background:
                  "linear-gradient(180deg, #ffd650 0%, #facc15 35%, var(--accent) 100%)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
                backgroundClip: "text",
                textShadow:
                  "0 0 18px rgba(167,139,250,0.45), 0 0 28px rgba(255,210,80,0.35)",
                filter: "drop-shadow(0 4px 0 rgba(0,0,0,0.45))",
              }}
            >
              <span aria-hidden style={{ marginRight: 12 }}>★</span>
              ЗАЛ СЛАВЫ
              <span aria-hidden style={{ marginLeft: 12 }}>★</span>
            </div>
            <div
              className="font-pixel uppercase tracking-widest mt-2"
              style={{ color: "var(--text-muted)", fontSize: 16 }}
            >
              Сезон I · Май 2026
            </div>
          </div>

          {/* ═══ HERO ═══ */}
          <HeroPanel />

          {/* ═══ ВЫБОР АРЕНЫ (sticky) ═══ */}
          <StageSelect />

          {/*
            2026-05-08 (полировка): каждая секция теперь обёрнута в
            <StageSection accent={...}>. Это даёт единую иерархию:
              - StageDivider — пиксельная плашка с заголовком
              - StageSection — рамка-«кабинет» для внутренностей
                (border 2px solid accent×alpha, padding 5×4)
            Без этой обёртки секции «плыли» — period-switcher слева,
            podium центрирован, table снова слева — пользователь видел
            ступенчатую кашу. Теперь весь контент секции живёт внутри
            одной рамки с одинаковым left padding.
          */}
          <StageDivider
            id="league"
            numeral="I"
            title="ЛИГА"
            subtitle="Недельная когорта · топ-3 повышаются · низ-3 вылетают"
            accent="var(--accent)"
          />
          <StageSection accent="var(--accent)">
            <LeagueTab />
          </StageSection>

          <StageDivider
            id="company"
            numeral="II"
            title="КОМПАНИЯ"
            subtitle="Рейтинг по всем игрокам · неделя · месяц · всё время"
            accent="#facc15"
          />
          <StageSection accent="#facc15">
            <CompanyTab />
          </StageSection>

          <StageDivider
            id="teams"
            numeral="III"
            title="КОМАНДЫ"
            subtitle="Офисы продаж · ранг по skill-adjusted (Bayesian)"
            accent="#fb923c"
          />
          <StageSection accent="#fb923c">
            <TeamsTab />
          </StageSection>

          <StageDivider
            id="duels"
            numeral="IV"
            title="ДУЭЛИ"
            subtitle="ELO голосовых дуэлей · ELO квиза по 127-ФЗ"
            accent="#ff3ec8"
          />
          <StageSection accent="#ff3ec8">
            <DuelsTab />
          </StageSection>

          {/*
            Конец секций. Footer ниже — пиксельная подпись через всю ширину.
          */}
          {/* Footer space — пиксельная подпись */}
          <div className="text-center mt-16 mb-8">
            <div
              className="font-pixel uppercase tracking-widest inline-flex items-center gap-2"
              style={{ color: "var(--text-muted)", fontSize: 14 }}
            >
              <Trophy size={14} />
              ★ КОНЕЦ ТАБЛИЦЫ ★
              <Trophy size={14} />
            </div>
          </div>
        </div>
      </div>
    </AuthLayout>
  );
}

/**
 * StageSection — единая рамка под каждой пиксельной плашкой StageDivider.
 *
 * 2026-05-08 (полировка): без этой обёртки контент секций «плыл» —
 * period-switcher жил на одном left X, podium центрировался, table
 * снова шёл от левого края, общая иерархия рассыпалась. Теперь:
 *   - 2px пунктирная рамка цвета арены (accent с low alpha)
 *   - единый padding p-5 (md:p-6)
 *   - радиус 0 — пиксель-стиль, без скруглений
 *   - mb-12 между секциями для дыхания
 *
 * Все таб-компоненты внутри получают одинаковый отступ от левого края,
 * так что period-switcher / mode-toggle / table / podium выровнены по
 * одной вертикальной оси.
 */
function StageSection({
  children,
  accent,
}: {
  children: ReactNode;
  accent: string;
}) {
  return (
    <section
      className="relative mb-12"
      style={{
        // Пиксельная рамка с низкой непрозрачностью акцента — секцию
        // видно, но она не «кричит» сильнее самой плашки-заголовка.
        border: `2px solid ${accent}33`,
        background: "rgba(8,5,18,0.35)",
        boxShadow: `inset 0 0 24px rgba(0,0,0,0.35)`,
      }}
    >
      {/* Внутренний padding одинаковый для всех 4 секций — устраняет
          «ступеньку» между period-switcher (раньше прижатый к рамке)
          и podium (раньше центрированный). */}
      <div className="p-4 md:p-5">{children}</div>
    </section>
  );
}
