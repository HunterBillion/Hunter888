"use client";

/**
 * ContentPanel — sub-tabs for /dashboard "Контент" (formerly "Методология"
 * — renamed 2026-05-05 because non-engineers read "Methodology" as something
 * they don't own; in production this is "everything that fills training":
 * scenarios, knowledge, plays, AI-quality oversight, wiki).
 *
 *   РОПы            — users with role=rop scoped to caller's team.
 *   Сессии          — every training session in scope.
 *   База ФЗ-127     — global knowledge chunks (was "Контент арены").
 *   Сценарии        — scenario constructor (draft → publish lifecycle).
 *   Ревью знаний    — TTL queue for legal_knowledge chunks.
 *   AI-собеседник   — aggregate AI quality oversight (was "Качество AI").
 *   Wiki            — corporate knowledge base, reuses <WikiDashboard>.
 *   Отзывы          — admin-only moderation queue.
 *
 * URL deep-link via `?sub=...`. Server-side redirects in next.config.ts
 * map retired `/methodologist/*` paths to the canonical sub-tabs; in-app
 * `?tab=methodology` legacy URLs are normalised to `?tab=content` by the
 * dashboard page itself.
 */

import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Mail } from "lucide-react";
import { BookOpen, Brain, Star, FileText, Database, Stack, Shield, Sparkle } from "@phosphor-icons/react";
import dynamic from "next/dynamic";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { roleName } from "@/lib/guards";
import { DashboardSkeleton } from "@/components/ui/Skeleton";
import { PixelInfoButton } from "@/components/ui/PixelInfoButton";
import { TeamKpiPanel } from "@/components/methodology/TeamKpiPanel";
// TeamAnalyticsWidget removed from this sub-tab 2026-05-05 — it duplicated
// the team-wide charts already on `?tab=team` (the merged Команда tab).
// The widget itself still lives at apps/web/src/components/methodology/
// TeamAnalyticsWidget.tsx in case it's needed somewhere else later.
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

// PlaybooksEditor — UI retired 2026-05-05; backend remains. The editor
// component file at apps/web/src/components/methodology/PlaybooksEditor.tsx
// is intentionally kept on disk for if we re-add the surface elsewhere.

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
  | "wiki"
  | "reviews";

// Legacy ?sub=playbooks deep-links land on `arena` — both surfaces are
// "team knowledge that the AI uses". The playbooks UI was retired
// 2026-05-05 because team-private playbooks duplicated the value of
// Сценарии (which already encode "how we run a call") + Wiki (which
// captures live best-practice). Backend /methodology/chunks endpoint
// is preserved for future use; only the UI tab is removed.
const PLAYBOOKS_LEGACY_TARGET: SubTab = "arena";

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
    let cancelled = false;
    setLoading(true);
    setError(null);
    api.get<UserListItem[]>("/users/?role=rop&limit=200")
      .then((data) => {
        if (cancelled) return;
        setItems(Array.isArray(data) ? data : []);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Ошибка загрузки");
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });
    return () => { cancelled = true; };
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

const SUB_TABS: { id: SubTab; label: string; icon: typeof BookOpen; adminOnly?: boolean }[] = [
  { id: "rops", label: "РОПы", icon: Brain },
  { id: "sessions", label: "Сессии", icon: FileText },
  // Was "Контент арены" — non-engineers couldn't tell whether "arena"
  // was the training mode, the rating system, or a separate product.
  // The chunks themselves are scoped to ФЗ-127, so the label says so.
  { id: "arena", label: "База ФЗ-127", icon: Database },
  { id: "scenarios", label: "Сценарии", icon: Stack },
  // TTL review queue for legal_knowledge chunks. Visible to ROP+admin —
  // the POST /admin/knowledge/{id}/review endpoint gates on those roles
  // anyway, so the tab is hidden from managers preemptively to keep
  // the nav uncluttered.
  { id: "knowledge_review", label: "Ревью знаний", icon: Shield },
  // Aggregate AI quality oversight: persona conflicts, policy
  // violations of the AI client. Was "Качество AI" — too abstract;
  // "AI-собеседник" makes the subject explicit (the client persona,
  // not the judge / coach). Backend gate: rop|admin.
  { id: "ai_quality", label: "AI-собеседник", icon: Sparkle },
  { id: "wiki", label: "Wiki", icon: BookOpen },
  { id: "reviews", label: "Отзывы", icon: Star, adminOnly: true },
];

export function MethodologyPanel({ isAdminCaller }: Props) {
  const searchParams = useSearchParams();

  // Deep-link: /dashboard?tab=content&sub=arena lands on the right
  // sub-tab. Used by the Next.js redirects from the retired
  // /methodologist/* paths (next.config.ts) and by the ROP nav menu.
  // Reading the raw string (not searchParams ref) keeps re-sync below
  // immune to unrelated query-param churn (e.g. `?modal=...`) that would
  // otherwise yank the user back to whatever `?sub=` is in the URL.
  //
  // Retired ids:
  //   - `scoring` (2026-05-05) — placeholder, never had real UI.
  //   - `playbooks` (2026-05-05) — duplicated value of Сценарии + Wiki;
  //     legacy bookmarks land on PLAYBOOKS_LEGACY_TARGET (= arena, the
  //     closest "team knowledge surface" still in the UI).
  const subParam = searchParams.get("sub");
  const initialSub = useMemo<SubTab>(() => {
    const allowed: SubTab[] = [
      "rops",
      "sessions",
      "arena",
      "scenarios",
      "knowledge_review",
      "ai_quality",
      "wiki",
      "reviews",
    ];
    if (subParam === "playbooks") return PLAYBOOKS_LEGACY_TARGET;
    if (!allowed.includes(subParam as SubTab)) return "rops";
    // Non-admin landing on adminOnly sub via deep-link → graceful fallback
    // instead of the empty AnimatePresence (which renders a blank panel).
    if (subParam === "reviews" && !isAdminCaller) return "rops";
    return subParam as SubTab;
  }, [subParam, isAdminCaller]);

  const [active, setActive] = useState<SubTab>(initialSub);

  // Re-sync when ?sub= changes (e.g. browser back/forward) and rewrite
  // the URL bar in place when we resolved a legacy id (`playbooks` →
  // `arena`) — keeps bookmarks self-healing without a 3xx hop.
  useEffect(() => {
    setActive(initialSub);
    if (subParam && subParam !== initialSub && typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.set("sub", initialSub);
      window.history.replaceState(null, "", url.toString());
    }
  }, [initialSub, subParam]);

  const visibleTabs = SUB_TABS.filter((t) => !t.adminOnly || isAdminCaller);

  return (
    <div className="space-y-4">
      {/* Tab title with i-tooltip */}
      <div className="flex items-center justify-between">
        <h2 className="font-display text-base tracking-wider" style={{ color: "var(--text-secondary)" }}>
          КОНТЕНТ
        </h2>
        <PixelInfoButton
          title="Контент"
          sections={[
            { label: "Сценарии", text: "Шаблоны разговоров для тренировок. Правки попадают к менеджерам только после кнопки «Опубликовать»." },
            { label: "База ФЗ-127", text: "Вопросы и цитаты из 127-ФЗ — то, что менеджер видит в режиме «Арена знаний»." },
            { label: "Сессии", text: "Просмотр любой сессии любого менеджера команды. Можно ревьюить, оставлять комментарии, отмечать как кейс." },
            { label: "Ревью знаний", text: "Очередь чанков на проверку. Помеченные «спорно» / «устарело» автоматически исключаются из ответов AI." },
            { label: "AI-собеседник", text: "Агрегаты ошибок AI-клиента по команде: персона-конфликты, нарушения политики разговора. Помогает ловить regression в работе AI после деплоя." },
            { label: "Wiki", text: "Корпоративная база: лучшие практики, регламенты. Автосинтез из успешных диалогов." },
          ]}
          footer="Всё, что наполняет тренировки. Раньше это была отдельная роль методолога — с апреля 2026 инструменты у РОПа."
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
          {active === "wiki" && <WikiDashboard />}
          {active === "reviews" && isAdminCaller && <ReviewsAdmin />}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
