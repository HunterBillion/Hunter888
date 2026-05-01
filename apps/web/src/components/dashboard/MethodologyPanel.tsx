"use client";

/**
 * MethodologyPanel — sub-tabs for /dashboard "Методология":
 *   1. РОПы          — list of users with role=rop scoped to the caller's
 *                      team (ROP sees own team, admin sees all teams).
 *                      Server enforces scope via apps/api/app/api/users.py.
 *   2. Сессии        — paginated browse of every training session in scope.
 *                      Migrated 2026-04-26 from /methodologist/sessions
 *                      standalone page.
 *   3. Контент арены — CRUD for ФЗ-127 knowledge chunks. Migrated from
 *                      /methodologist/arena-content standalone page.
 *   4. Сценарии      — placeholder for the constructor (TZ-3 will fill it
 *                      with draft-publish lifecycle UI).
 *   5. Скоринг       — placeholder for scoring weights config.
 *   6. Wiki          — corporate knowledge base, reuses <WikiDashboard>.
 *   7. Отзывы        — admin-only moderation queue.
 *
 * URL deep-link via `?sub=...` query param so a permanent redirect from
 * the retired /methodologist/* pages can land on the right sub-tab.
 */

import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Mail } from "lucide-react";
import { BookOpen, Brain, Star, FileText, Database, Sliders, Stack, Shield, Sparkle } from "@phosphor-icons/react";
import dynamic from "next/dynamic";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { roleName } from "@/lib/guards";
import { DashboardSkeleton } from "@/components/ui/Skeleton";
import { PixelInfoButton } from "@/components/ui/PixelInfoButton";
import { TeamKpiPanel } from "@/components/methodology/TeamKpiPanel";
import { TeamAnalyticsWidget } from "@/components/methodology/TeamAnalyticsWidget";
import { BulkAssignModal } from "@/components/methodology/BulkAssignModal";
import { CsvImportModal } from "@/components/methodology/CsvImportModal";

const WikiDashboard = dynamic(
  () => import("@/components/dashboard/WikiDashboard").then((m) => m.WikiDashboard),
  { loading: () => <DashboardSkeleton />, ssr: false }
);

const ReviewsAdmin = dynamic(
  () => import("@/components/dashboard/ReviewsAdmin").then((m) => m.ReviewsAdmin),
  { loading: () => <DashboardSkeleton />, ssr: false }
);

const SessionsBrowser = dynamic(
  () => import("@/components/dashboard/methodology/SessionsBrowser").then((m) => m.SessionsBrowser),
  { loading: () => <DashboardSkeleton />, ssr: false }
);

const ArenaContentEditor = dynamic(
  () => import("@/components/dashboard/methodology/ArenaContentEditor").then((m) => m.ArenaContentEditor),
  { loading: () => <DashboardSkeleton />, ssr: false }
);

const ScenariosEditor = dynamic(
  () => import("@/components/dashboard/methodology/ScenariosEditor").then((m) => m.ScenariosEditor),
  { loading: () => <DashboardSkeleton />, ssr: false }
);

const KnowledgeReviewQueue = dynamic(
  () => import("@/components/dashboard/methodology/KnowledgeReviewQueue").then((m) => m.KnowledgeReviewQueue),
  { loading: () => <DashboardSkeleton />, ssr: false }
);

const AiQualityPanel = dynamic(
  () => import("@/components/dashboard/methodology/AiQualityPanel").then((m) => m.AiQualityPanel),
  { loading: () => <DashboardSkeleton />, ssr: false }
);

interface UserListItem {
  id: string;
  email: string;
  full_name: string;
  role: string;
  team_name: string | null;
  is_active: boolean;
  avatar_url: string | null;
  created_at: string;
}

type SubTab =
  | "rops"
  | "sessions"
  | "arena"
  | "scenarios"
  | "knowledge_review"
  | "ai_quality"
  | "scoring"
  | "wiki"
  | "reviews";

interface Props {
  isAdminCaller: boolean;
}

function RopList({ isAdminCaller }: { isAdminCaller: boolean }) {
  const [items, setItems] = useState<UserListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [csvOpen, setCsvOpen] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    // Methodologist role retired 2026-04-26 — ROPs inherited the methodology
    // surface. We list rop role here (server scopes to caller's team for rop
    // viewers, returns all teams for admin viewers).
    api.get<UserListItem[]>("/users/?role=rop&limit=200")
      .then((data) => setItems(Array.isArray(data) ? data : []))
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Ошибка загрузки"))
      .finally(() => setLoading(false));
  }, [refreshKey]);

  if (loading) return <DashboardSkeleton />;
  if (error) {
    return (
      <div className="glass-panel rounded-xl p-6 text-center" style={{ color: "var(--danger)" }}>
        {error}
      </div>
    );
  }

  const toolbar = (
    <div className="flex flex-wrap gap-2 mb-3 justify-end">
      <button
        type="button"
        onClick={() => setBulkOpen(true)}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium"
        style={{ background: "var(--accent-muted)", color: "var(--accent)" }}
        title="Назначить один сценарий нескольким менеджерам сразу"
      >
        🎯 Массовое назначение
      </button>
      {isAdminCaller && (
        <button
          type="button"
          onClick={() => setCsvOpen(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium"
          style={{ background: "var(--accent-muted)", color: "var(--accent)" }}
          title="Загрузить список менеджеров/РОПов из .csv"
        >
          📥 Импорт CSV
        </button>
      )}
    </div>
  );

  const bulkModal = (
    <BulkAssignModal
      open={bulkOpen}
      onClose={() => setBulkOpen(false)}
      onAssigned={() => setRefreshKey((k) => k + 1)}
    />
  );
  const csvModal = (
    <CsvImportModal
      open={csvOpen}
      onClose={() => setCsvOpen(false)}
      onImported={() => setRefreshKey((k) => k + 1)}
    />
  );

  if (items.length === 0) {
    return (
      <>
        <TeamAnalyticsWidget refreshKey={refreshKey} />
        {toolbar}
        <TeamKpiPanel refreshKey={refreshKey} />
        <div className="glass-panel rounded-xl p-8 text-center">
          <Brain size={32} weight="duotone" style={{ color: "var(--text-muted)", margin: "0 auto 12px", opacity: 0.5 }} />
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            В вашей команде пока нет РОПов. Назначить может администратор.
          </p>
        </div>
        {bulkModal}
        {csvModal}
      </>
    );
  }

  return (
    <>
      <TeamAnalyticsWidget refreshKey={refreshKey} />
      {toolbar}
      <TeamKpiPanel refreshKey={refreshKey} />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {items.map((u) => (
          <div
            key={u.id}
            className="glass-panel rounded-xl p-4 flex items-center gap-3"
            style={{ border: u.is_active ? "1px solid var(--border-color)" : "1px dashed var(--danger)" }}
          >
            <div
              className="flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center font-bold text-sm"
              style={{ background: "var(--accent-muted)", color: "var(--accent)" }}
            >
              {u.full_name.split(" ").map((p) => p[0]).slice(0, 2).join("").toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-semibold truncate" style={{ color: "var(--text-primary)" }}>
                {u.full_name}
              </div>
              <div className="flex items-center gap-2 text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
                <Mail size={12} />
                <span className="truncate">{u.email}</span>
              </div>
              <div className="flex items-center gap-2 text-xs mt-1" style={{ color: "var(--text-muted)" }}>
                <span>{roleName(u.role)}</span>
                {u.team_name && <span>· {u.team_name}</span>}
                {!u.is_active && <span style={{ color: "var(--danger)" }}>· неактивен</span>}
              </div>
            </div>
          </div>
        ))}
      </div>
      {bulkModal}
      {csvModal}
    </>
  );
}

function PlaceholderTab({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="glass-panel rounded-xl p-8 text-center">
      <Stack size={32} weight="duotone" style={{ color: "var(--text-muted)", margin: "0 auto 12px", opacity: 0.5 }} />
      <h3 className="text-base font-semibold" style={{ color: "var(--text-primary)" }}>
        {title}
      </h3>
      <p className="mt-2 text-sm max-w-md mx-auto" style={{ color: "var(--text-muted)" }}>
        {subtitle}
      </p>
    </div>
  );
}

const SUB_TABS: { id: SubTab; label: string; icon: typeof BookOpen; adminOnly?: boolean }[] = [
  { id: "rops", label: "РОПы", icon: Brain },
  { id: "sessions", label: "Сессии", icon: FileText },
  { id: "arena", label: "Контент арены", icon: Database },
  { id: "scenarios", label: "Сценарии", icon: Stack },
  // TZ-4 §8 — TTL review queue. Visible to ROP+admin (the
  // POST /admin/knowledge/{id}/review endpoint also gates on those
  // roles, so a pilot manager seeing the tab gets a 403 anyway —
  // hiding it preemptively keeps the nav uncluttered).
  { id: "knowledge_review", label: "Ревью знаний", icon: Shield },
  // TZ-4 §13.4.1 — aggregate AI quality oversight. Lives here
  // because the failure modes are about AI craft (policy violations,
  // persona drift), not people-management (Команда tab keeps that
  // focus). Backend gate: rop|admin.
  { id: "ai_quality", label: "Качество AI", icon: Sparkle },
  { id: "scoring", label: "Скоринг", icon: Sliders },
  { id: "wiki", label: "Wiki", icon: BookOpen },
  { id: "reviews", label: "Отзывы", icon: Star, adminOnly: true },
];

export function MethodologyPanel({ isAdminCaller }: Props) {
  const searchParams = useSearchParams();

  // Deep-link: /dashboard?tab=methodology&sub=arena lands on the right
  // sub-tab. Used by the Next.js redirects from the retired
  // /methodologist/* paths (next.config.ts) and by the ROP nav menu.
  const initialSub = useMemo<SubTab>(() => {
    const raw = searchParams.get("sub");
    const allowed: SubTab[] = [
      "rops",
      "sessions",
      "arena",
      "scenarios",
      "knowledge_review",
      "ai_quality",
      "scoring",
      "wiki",
      "reviews",
    ];
    return (allowed.includes(raw as SubTab) ? (raw as SubTab) : "rops") as SubTab;
  }, [searchParams]);

  const [active, setActive] = useState<SubTab>(initialSub);

  // Re-sync when ?sub= changes (e.g. browser back/forward)
  useEffect(() => {
    setActive(initialSub);
  }, [initialSub]);

  const visibleTabs = SUB_TABS.filter((t) => !t.adminOnly || isAdminCaller);

  return (
    <div className="space-y-4">
      {/* Tab title with i-tooltip */}
      <div className="flex items-center justify-between">
        <h2 className="font-display text-base tracking-wider" style={{ color: "var(--text-secondary)" }}>
          МЕТОДОЛОГИЯ
        </h2>
        <PixelInfoButton
          title="Методология"
          sections={[
            { label: "Сценарии", text: "Шаблоны разговоров для тренировок. Версионирование (TZ-3): правки попадают к менеджерам только после кнопки «Опубликовать»." },
            { label: "Контент Арены", text: "База знаний для квизов: вопросы, варианты ответов, цитаты из 127-ФЗ. Что менеджер видит в режиме «Арена знаний»." },
            { label: "Скоринг", text: "Веса L1-L10 для оценки сессии. Изменения вступают в силу для НОВЫХ сессий — старые остаются на старых весах." },
            { label: "Сессии", text: "Просмотр любой сессии любого менеджера команды. Можно ревьюить, оставлять комментарии, отмечать как кейс." },
            { label: "Ревью знаний", text: "Очередь legal_knowledge чанков на проверку (TZ-4 §8). Помеченные disputed/needs_review автоматически исключаются из ответов AI." },
            { label: "Качество AI", text: "Агрегаты по всей команде: персона-конфликты, нарушения политики разговора (TZ-4 §10). Помогает ловить regression в работе AI после деплоя." },
            { label: "Wiki", text: "Корпоративная база: лучшие практики, регламенты. Автосинтез из успешных диалогов." },
          ]}
          footer="Раньше методолог был отдельной ролью. С апреля 2026 эти инструменты — часть Дашборда ROP."
        />
      </div>

      {/* Sub-tab bar */}
      <div className="flex items-center gap-2 rounded-xl p-1.5 overflow-x-auto" style={{ background: "var(--glass-bg)", border: "1px solid var(--glass-border)" }}>
        {visibleTabs.map((t) => {
          const Icon = t.icon;
          const isActive = active === t.id;
          return (
            <button
              key={t.id}
              onClick={() => {
                setActive(t.id);
                // Reflect sub-tab in URL so links/refresh stay deterministic
                if (typeof window !== "undefined") {
                  const url = new URL(window.location.href);
                  url.searchParams.set("sub", t.id);
                  window.history.replaceState(null, "", url.toString());
                }
              }}
              className="relative flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors"
              style={{
                color: isActive ? "var(--text-primary)" : "var(--text-muted)",
                fontWeight: isActive ? 600 : 500,
              }}
            >
              <Icon size={14} weight="duotone" style={{ color: isActive ? "var(--accent)" : undefined }} />
              <span>{t.label}</span>
              {isActive && (
                <motion.div
                  layoutId="methodology-subtab-indicator"
                  className="absolute inset-0 rounded-lg -z-10"
                  style={{ background: "var(--accent-muted)", border: "1px solid var(--accent)" }}
                  transition={{ type: "spring", stiffness: 400, damping: 30 }}
                />
              )}
            </button>
          );
        })}
      </div>

      <AnimatePresence mode="wait">
        <motion.div
          key={active}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
        >
          {active === "rops" && <RopList isAdminCaller={isAdminCaller} />}
          {active === "sessions" && <SessionsBrowser />}
          {active === "arena" && <ArenaContentEditor />}
          {active === "scenarios" && <ScenariosEditor />}
          {active === "knowledge_review" && <KnowledgeReviewQueue />}
          {active === "ai_quality" && <AiQualityPanel />}
          {active === "scoring" && <PlaceholderTab title="Скоринг" subtitle="Управление весами скоринговых слоёв (L1–L10) — в дорожной карте." />}
          {active === "wiki" && <WikiDashboard />}
          {active === "reviews" && isAdminCaller && <ReviewsAdmin />}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
