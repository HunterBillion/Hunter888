"use client";

/**
 * /leaderboard — unified leaderboard hub.
 *
 * 2026-05-04 v2: redesigned to 4 tabs (was 7). Old query params still
 * work via aliasing so existing bookmarks and the LeagueHeroCard CTA
 * keep working without redirect:
 *
 *   ?tab=hunter|week|month  →  ?tab=company  (week/month also set period)
 *   ?tab=arena|knowledge    →  ?tab=duels    (sets mode)
 *   ?tab=teams              →  ?tab=teams    (unchanged)
 *   ?tab=league             →  ?tab=league   (unchanged)
 *
 * The 4 tabs are: Лига · Компания · Команды · Дуэли. Lega is the
 * default because it's the most-engaging gamified surface.
 */

import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { Trophy, Building2, Crown, Swords } from "lucide-react";
import AuthLayout from "@/components/layout/AuthLayout";
import { LeagueTab } from "@/components/leaderboard/LeagueTab";
import { CompanyTab } from "@/components/leaderboard/CompanyTab";
import { TeamsTab } from "@/components/leaderboard/TeamsTab";
import { DuelsTab } from "@/components/leaderboard/DuelsTab";
import { PixelInfoButton } from "@/components/ui/PixelInfoButton";

type Tab = "league" | "company" | "teams" | "duels";

const TABS: { key: Tab; label: string; icon: typeof Trophy }[] = [
  { key: "league", label: "Лига", icon: Trophy },
  { key: "company", label: "Компания", icon: Crown },
  { key: "teams", label: "Команды", icon: Building2 },
  { key: "duels", label: "Дуэли", icon: Swords },
];

const VALID_TABS: Tab[] = ["league", "company", "teams", "duels"];

// Aliases from previous 7-tab structure → new 4-tab structure.
// Returns canonical Tab + optional secondary URL hint we won't store
// (handled inline by sub-tabs reading their own ?period= or ?mode=).
function aliasTab(raw: string | null): Tab {
  if (!raw) return "league";
  if ((VALID_TABS as string[]).includes(raw)) return raw as Tab;
  if (raw === "hunter" || raw === "week" || raw === "month") return "company";
  if (raw === "arena" || raw === "knowledge") return "duels";
  return "league";
}

export default function LeaderboardPageWrapper() {
  return (
    <Suspense fallback={null}>
      <LeaderboardPage />
    </Suspense>
  );
}

function LeaderboardPage() {
  const params = useSearchParams();
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<Tab>(() =>
    aliasTab(params?.get("tab") ?? null),
  );

  // Re-sync on browser back/forward.
  useEffect(() => {
    setActiveTab(aliasTab(params?.get("tab") ?? null));
  }, [params]);

  const switchTab = useCallback(
    (next: Tab) => {
      setActiveTab(next);
      const url = next === "league" ? "/leaderboard" : `/leaderboard?tab=${next}`;
      router.replace(url, { scroll: false });
    },
    [router],
  );

  return (
    <AuthLayout>
      <div className="panel-grid-bg min-h-screen">
        <div className="app-page max-w-6xl">
          {/* Header */}
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="mb-6 flex items-start justify-between gap-3"
          >
            <div>
              <h1
                className="font-display text-2xl md:text-3xl font-bold tracking-tight"
                style={{ color: "var(--text-primary)" }}
              >
                Лидерборд
              </h1>
              <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
                Лига недели, рейтинг компании, команды и дуэли — всё в одном
                месте.
              </p>
            </div>
            <PixelInfoButton
              title="Лидерборд"
              sections={[
                {
                  icon: Trophy,
                  label: "Лига",
                  text: "Твоя недельная когорта (~15 игроков). Топ-3 повышаются, низ-3 вылетают. Сброс — воскресенье 23:59 МСК.",
                },
                {
                  icon: Crown,
                  label: "Компания",
                  text: "Рейтинг по всем игрокам. Переключай период: Неделя (TP), Месяц (турнир), Всё время (Hunter Score).",
                },
                {
                  icon: Building2,
                  label: "Команды",
                  text: "Офисы продаж по среднему баллу (Bayesian). Видны все командам — внутренняя прозрачность.",
                },
                {
                  icon: Swords,
                  label: "Дуэли",
                  text: "ELO двух режимов: голос (1×1 продажа) и знания (квиз по 127-ФЗ).",
                },
              ]}
              footer="Подсказка: каждый таб помнится в URL — можно поделиться ссылкой"
            />
          </motion.div>

          {/* Tabs */}
          <div
            className="flex gap-1 mb-6 p-1 rounded-xl overflow-x-auto"
            style={{
              background: "var(--input-bg)",
              border: "1px solid var(--border-color)",
            }}
          >
            {TABS.map((t) => {
              const Icon = t.icon;
              const active = activeTab === t.key;
              return (
                <button
                  key={t.key}
                  onClick={() => switchTab(t.key)}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-all shrink-0"
                  style={{
                    background: active ? "var(--accent)" : "transparent",
                    color: active ? "#fff" : "var(--text-secondary)",
                    boxShadow: active ? "0 2px 10px var(--accent-glow)" : "none",
                  }}
                >
                  <Icon size={14} />
                  {t.label}
                </button>
              );
            })}
          </div>

          <AnimatePresence mode="wait">
            <motion.div
              key={activeTab}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.18 }}
            >
              {activeTab === "league" && <LeagueTab />}
              {activeTab === "company" && <CompanyTab />}
              {activeTab === "teams" && <TeamsTab />}
              {activeTab === "duels" && <DuelsTab />}
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </AuthLayout>
  );
}
