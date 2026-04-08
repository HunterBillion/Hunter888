"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  BookOpen,
  Brain,
  Lightbulb,
  Target,
  Clock,
  ChevronRight,
  Loader2,
  FileText,
  TrendingUp,
  AlertTriangle,
  Zap,
  Users,
  Activity,
  RefreshCw,
  ShieldCheck,
  ArrowLeft,
  Search,
  Info,
} from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { isAdmin } from "@/lib/guards";
import AuthLayout from "@/components/layout/AuthLayout";
import { BackButton } from "@/components/ui/BackButton";
import Markdown from "react-markdown";

/* ─── Types ─── */

interface ManagerWikiSummary {
  wiki_id: string;
  manager_id: string;
  manager_name: string;
  manager_role: string;
  status: string;
  sessions_ingested: number;
  patterns_discovered: number;
  pages_count: number;
  total_tokens_used: number;
  last_ingest_at: string | null;
  created_at: string | null;
}

interface WikiPageItem {
  id: string;
  page_path: string;
  page_type: string;
  version: number;
  tags: string[];
  updated_at: string | null;
}

interface WikiPageContent {
  id: string;
  page_path: string;
  content: string;
  page_type: string;
  version: number;
  tags: string[];
  source_sessions: string[];
}

interface PatternItem {
  id: string;
  pattern_code: string;
  category: string;
  description: string;
  sessions_in_pattern: number;
  is_confirmed: boolean;
  mitigation_technique: string | null;
  impact_on_score_delta: number | null;
}

interface TechniqueItem {
  id: string;
  technique_code: string;
  technique_name: string;
  description: string;
  success_rate: number;
  success_count: number;
  attempt_count: number;
  applicable_to_archetype: string | null;
  how_to_apply: string | null;
}

interface WikiLogEntry {
  id: string;
  action: string;
  description: string | null;
  pages_modified: number;
  pages_created: number;
  patterns_discovered: string[];
  tokens_used: number;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  error_msg: string | null;
}

interface GlobalStats {
  total_wikis: number;
  total_sessions_ingested: number;
  total_patterns_discovered: number;
  total_pages: number;
  total_tokens_used: number;
}

type View = "list" | "detail";
type DetailTab = "pages" | "patterns" | "techniques" | "log";

/* ─── Category config ─── */

const CATEGORY_CONFIG: Record<string, { label: string; color: string; icon: typeof AlertTriangle }> = {
  weakness: { label: "Слабость", color: "#ef4444", icon: AlertTriangle },
  strength: { label: "Сила", color: "#22c55e", icon: TrendingUp },
  quirk: { label: "Особенность", color: "#f59e0b", icon: Zap },
  misconception: { label: "Заблуждение", color: "#8b5cf6", icon: AlertTriangle },
};

const ACTION_LABELS: Record<string, string> = {
  ingest_session: "Анализ сессии",
  rebuild_page: "Перестроение страницы",
  pattern_discovered: "Новый паттерн",
  technique_discovered: "Новая техника",
  manual_edit: "Ручная правка",
};

/* ─── Helpers ─── */

/* renderMarkdown removed — replaced with react-markdown to prevent XSS */

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function timeAgo(iso: string | null): string {
  if (!iso) return "никогда";
  const diff = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "только что";
  if (minutes < 60) return `${minutes} мин. назад`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} ч. назад`;
  const days = Math.floor(hours / 24);
  return `${days} дн. назад`;
}

/* ═══════════════════════════════════════════════════════════════════════════
   MAIN COMPONENT
   ═══════════════════════════════════════════════════════════════════════════ */

export default function AdminWikiPage() {
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();

  // ── Access control ──
  // Only deny access once we KNOW the user is loaded and is NOT admin
  const accessDenied = !authLoading && user != null && !isAdmin(user);

  // ── State ──
  const [view, setView] = useState<View>("list");
  const [loading, setLoading] = useState(true);
  const [globalStats, setGlobalStats] = useState<GlobalStats | null>(null);
  const [wikis, setWikis] = useState<ManagerWikiSummary[]>([]);
  const [searchQuery, setSearchQuery] = useState("");

  // Detail state
  const [selectedManager, setSelectedManager] = useState<ManagerWikiSummary | null>(null);
  const [detailTab, setDetailTab] = useState<DetailTab>("pages");
  const [pages, setPages] = useState<WikiPageItem[]>([]);
  const [patterns, setPatterns] = useState<PatternItem[]>([]);
  const [techniques, setTechniques] = useState<TechniqueItem[]>([]);
  const [logEntries, setLogEntries] = useState<WikiLogEntry[]>([]);
  const [selectedPage, setSelectedPage] = useState<WikiPageContent | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [pageLoading, setPageLoading] = useState(false);
  const [showHelp, setShowHelp] = useState(false);

  // ── Data loading ──

  const loadList = useCallback(async () => {
    setLoading(true);
    try {
      const [statsRes, wikisRes] = await Promise.all([
        api.get("/wiki/global/stats"),
        api.get("/wiki/managers"),
      ]);
      setGlobalStats(statsRes);
      setWikis(wikisRes.wikis || []);
    } catch (err) {
      console.error("Wiki load error:", err);
      // Data simply won't show — access denied is handled by role check above
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!authLoading && user && isAdmin(user)) {
      loadList();
    }
  }, [user, authLoading, loadList]);

  const openManager = useCallback(async (mgr: ManagerWikiSummary) => {
    setSelectedManager(mgr);
    setView("detail");
    setDetailTab("pages");
    setSelectedPage(null);
    setDetailLoading(true);
    try {
      const [pagesRes, patternsRes, techniquesRes, logRes] = await Promise.all([
        api.get(`/wiki/${mgr.manager_id}/pages`),
        api.get(`/wiki/${mgr.manager_id}/patterns`),
        api.get(`/wiki/${mgr.manager_id}/techniques`),
        api.get(`/wiki/${mgr.manager_id}/log`),
      ]);
      setPages(pagesRes.pages || []);
      setPatterns(patternsRes.patterns || []);
      setTechniques(techniquesRes.techniques || []);
      setLogEntries(logRes.log || []);
    } catch {
      setPages([]);
      setPatterns([]);
      setTechniques([]);
      setLogEntries([]);
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const loadPageContent = useCallback(async (managerId: string, pagePath: string) => {
    setPageLoading(true);
    try {
      const res = await api.get(`/wiki/${managerId}/pages/${pagePath}`);
      setSelectedPage(res);
    } catch {
      setSelectedPage(null);
    } finally {
      setPageLoading(false);
    }
  }, []);

  // ── Filtering ──
  const filteredWikis = wikis.filter((w) =>
    w.manager_name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // ── Access denied screen ──
  if (accessDenied) {
    return (
      <AuthLayout>
        <div style={{ maxWidth: 600, margin: "4rem auto", textAlign: "center", padding: "2rem" }}>
          <ShieldCheck size={48} style={{ color: "#ef4444", margin: "0 auto 1rem" }} />
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "#fff" }}>
            Доступ запрещён
          </h1>
          <p style={{ color: "#9ca3af", marginTop: "0.5rem" }}>
            Wiki менеджеров доступна только администраторам.
            Если вы считаете это ошибкой, обратитесь к администратору системы.
          </p>
          <button
            onClick={() => router.push("/home")}
            style={{
              marginTop: "1.5rem",
              padding: "0.75rem 2rem",
              background: "rgba(255,255,255,0.06)",
              border: "1px solid rgba(255,255,255,0.1)",
              borderRadius: 8,
              color: "#e0e0e0",
              cursor: "pointer",
              fontSize: "0.9rem",
            }}
          >
            На главную
          </button>
        </div>
      </AuthLayout>
    );
  }

  // ── Loading ──
  if (authLoading || loading) {
    return (
      <AuthLayout>
        <div style={{ textAlign: "center", padding: "6rem 2rem" }}>
          <Loader2 size={36} style={{ animation: "spin 1s linear infinite", color: "#f59e0b" }} />
          <p style={{ color: "#9ca3af", marginTop: "1rem" }}>Загрузка...</p>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout>
      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "2rem 1rem" }}>
        {view === "list" ? (
          <ManagerListView
            globalStats={globalStats}
            wikis={filteredWikis}
            searchQuery={searchQuery}
            onSearch={setSearchQuery}
            onSelectManager={openManager}
            onRefresh={loadList}
            showHelp={showHelp}
            onToggleHelp={() => setShowHelp(!showHelp)}
          />
        ) : (
          <ManagerDetailView
            manager={selectedManager!}
            tab={detailTab}
            onTabChange={setDetailTab}
            pages={pages}
            patterns={patterns}
            techniques={techniques}
            logEntries={logEntries}
            selectedPage={selectedPage}
            loading={detailLoading}
            pageLoading={pageLoading}
            onBack={() => { setView("list"); setSelectedManager(null); }}
            onLoadPage={(path) => loadPageContent(selectedManager!.manager_id, path)}
          />
        )}
      </div>
    </AuthLayout>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   LIST VIEW — all managers' wikis
   ═══════════════════════════════════════════════════════════════════════════ */

function ManagerListView({
  globalStats,
  wikis,
  searchQuery,
  onSearch,
  onSelectManager,
  onRefresh,
  showHelp,
  onToggleHelp,
}: {
  globalStats: GlobalStats | null;
  wikis: ManagerWikiSummary[];
  searchQuery: string;
  onSearch: (q: string) => void;
  onSelectManager: (w: ManagerWikiSummary) => void;
  onRefresh: () => void;
  showHelp: boolean;
  onToggleHelp: () => void;
}) {
  return (
    <>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: "1rem", marginBottom: "1.5rem", flexWrap: "wrap" }}>
        <ShieldCheck size={28} style={{ color: "#f59e0b" }} />
        <div style={{ flex: 1 }}>
          <h1 style={{ fontSize: "1.6rem", fontWeight: 700, color: "#fff", margin: 0 }}>
            Wiki менеджеров
          </h1>
          <p style={{ color: "#9ca3af", margin: 0, fontSize: "0.85rem" }}>
            Панель администратора — персональные базы знаний всех менеджеров
          </p>
        </div>
        <button
          onClick={onToggleHelp}
          style={{
            padding: "0.5rem",
            background: showHelp ? "rgba(245,158,11,0.15)" : "rgba(255,255,255,0.04)",
            border: `1px solid ${showHelp ? "rgba(245,158,11,0.3)" : "rgba(255,255,255,0.08)"}`,
            borderRadius: 8,
            color: showHelp ? "#f59e0b" : "#9ca3af",
            cursor: "pointer",
          }}
          title="Справка"
        >
          <Info size={18} />
        </button>
        <button
          onClick={onRefresh}
          style={{
            padding: "0.5rem",
            background: "rgba(255,255,255,0.04)",
            border: "1px solid rgba(255,255,255,0.08)",
            borderRadius: 8,
            color: "#9ca3af",
            cursor: "pointer",
          }}
          title="Обновить"
        >
          <RefreshCw size={18} />
        </button>
      </div>

      {/* Help panel */}
      <AnimatePresence>
        {showHelp && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            style={{
              marginBottom: "1.5rem",
              padding: "1.25rem",
              background: "rgba(245,158,11,0.06)",
              border: "1px solid rgba(245,158,11,0.15)",
              borderRadius: 12,
              overflow: "hidden",
            }}
          >
            <h3 style={{ color: "#f59e0b", fontSize: "1rem", fontWeight: 600, margin: "0 0 0.75rem" }}>
              Как работает Wiki менеджеров
            </h3>
            <div style={{ color: "#d1d5db", fontSize: "0.85rem", lineHeight: 1.7 }}>
              <p style={{ margin: "0 0 0.5rem" }}>
                <strong style={{ color: "#fff" }}>Wiki</strong> — это персональная база знаний каждого менеджера,
                которая автоматически строится из тренировочных сессий по паттерну Karpathy (raw &rarr; wiki &rarr; outputs).
              </p>
              <p style={{ margin: "0 0 0.5rem" }}>
                <strong style={{ color: "#fff" }}>Как создаётся:</strong> После завершения каждой тренировочной сессии
                Gemini LLM автоматически анализирует транскрипт и:
              </p>
              <ul style={{ margin: "0 0 0.5rem", paddingLeft: "1.5rem" }}>
                <li>Обнаруживает <strong style={{ color: "#ef4444" }}>слабости</strong> (паттерны ошибок, повторяющиеся проблемы)</li>
                <li>Фиксирует <strong style={{ color: "#22c55e" }}>сильные техники</strong> (успешные приёмы с % успеха)</li>
                <li>Генерирует <strong style={{ color: "#f59e0b" }}>страницы wiki</strong> (обзор, инсайты, рекомендации)</li>
              </ul>
              <p style={{ margin: "0 0 0.5rem" }}>
                <strong style={{ color: "#fff" }}>Что видите вы:</strong>
              </p>
              <ul style={{ margin: "0 0 0.5rem", paddingLeft: "1.5rem" }}>
                <li><strong>Список менеджеров</strong> — у кого уже есть wiki, сколько сессий проанализировано</li>
                <li><strong>Паттерны</strong> — слабости и особенности конкретного менеджера</li>
                <li><strong>Техники</strong> — какие приёмы работают у этого менеджера</li>
                <li><strong>Лог изменений</strong> — когда и что было обновлено в wiki</li>
              </ul>
              <p style={{ margin: "0 0 0.5rem" }}>
                <strong style={{ color: "#fff" }}>Обновления в реальном времени:</strong> Нажмите кнопку{" "}
                <RefreshCw size={14} style={{ display: "inline", verticalAlign: "middle", color: "#f59e0b" }} />{" "}
                чтобы загрузить актуальные данные. Wiki обновляется автоматически после каждой сессии менеджера.
              </p>
              <p style={{ margin: 0, fontSize: "0.8rem", color: "#9ca3af" }}>
                Эта панель доступна только администраторам. Менеджеры НЕ видят свою wiki.
              </p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Global stats */}
      {globalStats && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
            gap: "0.75rem",
            marginBottom: "1.5rem",
          }}
        >
          {[
            { label: "Wiki создано", value: globalStats.total_wikis, icon: Users, color: "#6366f1" },
            { label: "Сессий", value: globalStats.total_sessions_ingested, icon: Activity, color: "#f59e0b" },
            { label: "Паттернов", value: globalStats.total_patterns_discovered, icon: Brain, color: "#ef4444" },
            { label: "Страниц", value: globalStats.total_pages, icon: FileText, color: "#22c55e" },
            { label: "Токенов LLM", value: globalStats.total_tokens_used.toLocaleString("ru-RU"), icon: Zap, color: "#8b5cf6" },
          ].map((s) => (
            <div
              key={s.label}
              style={{
                background: "rgba(255,255,255,0.03)",
                border: "1px solid rgba(255,255,255,0.06)",
                borderRadius: 10,
                padding: "0.75rem",
                textAlign: "center",
              }}
            >
              <s.icon size={18} style={{ color: s.color, marginBottom: "0.25rem" }} />
              <div style={{ fontSize: "1.3rem", fontWeight: 700, color: "#fff" }}>{s.value}</div>
              <div style={{ fontSize: "0.75rem", color: "#9ca3af" }}>{s.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Search */}
      <div style={{ position: "relative", marginBottom: "1rem" }}>
        <Search
          size={16}
          style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: "#6b7280" }}
        />
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => onSearch(e.target.value)}
          placeholder="Поиск по имени менеджера..."
          style={{
            width: "100%",
            padding: "0.6rem 0.75rem 0.6rem 2.25rem",
            background: "rgba(255,255,255,0.03)",
            border: "1px solid rgba(255,255,255,0.08)",
            borderRadius: 8,
            color: "#e0e0e0",
            fontSize: "0.9rem",
            outline: "none",
          }}
        />
      </div>

      {/* Manager list */}
      {wikis.length === 0 ? (
        <div style={{ textAlign: "center", padding: "3rem", color: "#6b7280" }}>
          <Brain size={40} style={{ margin: "0 auto 1rem", opacity: 0.4 }} />
          <p>Wiki ещё не созданы.</p>
          <p style={{ fontSize: "0.85rem" }}>
            Менеджеры должны пройти хотя бы одну тренировочную сессию.
          </p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          {wikis.map((w) => (
            <motion.button
              key={w.wiki_id}
              onClick={() => onSelectManager(w)}
              whileHover={{ scale: 1.005 }}
              whileTap={{ scale: 0.995 }}
              style={{
                display: "grid",
                gridTemplateColumns: "1fr auto auto auto auto",
                alignItems: "center",
                gap: "1rem",
                padding: "0.85rem 1.25rem",
                background: "rgba(255,255,255,0.03)",
                border: "1px solid rgba(255,255,255,0.06)",
                borderRadius: 10,
                cursor: "pointer",
                color: "#e0e0e0",
                textAlign: "left",
                width: "100%",
              }}
            >
              <div>
                <div style={{ fontWeight: 600, fontSize: "0.95rem" }}>{w.manager_name}</div>
                <div style={{ fontSize: "0.75rem", color: "#6b7280" }}>
                  {w.manager_role === "admin" ? "Админ" : w.manager_role === "rop" ? "РОП" : "Менеджер"}
                </div>
              </div>
              <div style={{ textAlign: "center" }}>
                <div style={{ fontSize: "1.1rem", fontWeight: 700, color: "#f59e0b" }}>{w.sessions_ingested}</div>
                <div style={{ fontSize: "0.7rem", color: "#6b7280" }}>сессий</div>
              </div>
              <div style={{ textAlign: "center" }}>
                <div style={{ fontSize: "1.1rem", fontWeight: 700, color: "#ef4444" }}>{w.patterns_discovered}</div>
                <div style={{ fontSize: "0.7rem", color: "#6b7280" }}>паттернов</div>
              </div>
              <div style={{ textAlign: "center" }}>
                <div style={{ fontSize: "0.75rem", color: "#9ca3af" }}>{timeAgo(w.last_ingest_at)}</div>
              </div>
              <ChevronRight size={16} style={{ color: "#6b7280" }} />
            </motion.button>
          ))}
        </div>
      )}
    </>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   DETAIL VIEW — single manager's wiki
   ═══════════════════════════════════════════════════════════════════════════ */

const DETAIL_TABS: { id: DetailTab; label: string; icon: typeof BookOpen }[] = [
  { id: "pages", label: "Страницы", icon: FileText },
  { id: "patterns", label: "Паттерны", icon: Brain },
  { id: "techniques", label: "Техники", icon: Lightbulb },
  { id: "log", label: "Лог изменений", icon: Clock },
];

function ManagerDetailView({
  manager,
  tab,
  onTabChange,
  pages,
  patterns,
  techniques,
  logEntries,
  selectedPage,
  loading,
  pageLoading,
  onBack,
  onLoadPage,
}: {
  manager: ManagerWikiSummary;
  tab: DetailTab;
  onTabChange: (t: DetailTab) => void;
  pages: WikiPageItem[];
  patterns: PatternItem[];
  techniques: TechniqueItem[];
  logEntries: WikiLogEntry[];
  selectedPage: WikiPageContent | null;
  loading: boolean;
  pageLoading: boolean;
  onBack: () => void;
  onLoadPage: (path: string) => void;
}) {
  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: "4rem" }}>
        <Loader2 size={32} style={{ animation: "spin 1s linear infinite", color: "#f59e0b" }} />
        <p style={{ color: "#9ca3af", marginTop: "1rem" }}>Загрузка wiki...</p>
      </div>
    );
  }

  return (
    <>
      {/* Back + Header */}
      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "1.5rem" }}>
        <button
          onClick={onBack}
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.4rem",
            padding: "0.5rem 0.75rem",
            background: "rgba(255,255,255,0.04)",
            border: "1px solid rgba(255,255,255,0.08)",
            borderRadius: 8,
            color: "#9ca3af",
            cursor: "pointer",
            fontSize: "0.85rem",
          }}
        >
          <ArrowLeft size={16} />
          Назад
        </button>
        <div style={{ flex: 1 }}>
          <h1 style={{ fontSize: "1.4rem", fontWeight: 700, color: "#fff", margin: 0 }}>
            {manager.manager_name}
          </h1>
          <p style={{ color: "#9ca3af", margin: 0, fontSize: "0.8rem" }}>
            Wiki | {manager.sessions_ingested} сессий | {manager.patterns_discovered} паттернов | {manager.pages_count} страниц
            {manager.last_ingest_at && ` | Обновлено: ${timeAgo(manager.last_ingest_at)}`}
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div
        style={{
          display: "flex",
          gap: "0.5rem",
          marginBottom: "1.5rem",
          borderBottom: "1px solid rgba(255,255,255,0.08)",
          paddingBottom: "0.5rem",
          flexWrap: "wrap",
        }}
      >
        {DETAIL_TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => onTabChange(t.id)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.4rem",
              padding: "0.5rem 1rem",
              borderRadius: 8,
              border: "none",
              background: tab === t.id ? "rgba(245,158,11,0.15)" : "transparent",
              color: tab === t.id ? "#f59e0b" : "#9ca3af",
              cursor: "pointer",
              fontSize: "0.9rem",
              fontWeight: tab === t.id ? 600 : 400,
              transition: "all 0.2s",
            }}
          >
            <t.icon size={16} />
            {t.label}
            {t.id === "patterns" && patterns.length > 0 && (
              <span style={{
                marginLeft: 4,
                fontSize: "0.7rem",
                padding: "1px 6px",
                borderRadius: 8,
                background: "rgba(239,68,68,0.15)",
                color: "#ef4444",
              }}>
                {patterns.length}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Content */}
      <AnimatePresence mode="wait">
        <motion.div
          key={tab}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          transition={{ duration: 0.2 }}
        >
          {tab === "pages" && (
            <PagesTab
              pages={pages}
              selectedPage={selectedPage}
              pageLoading={pageLoading}
              onLoadPage={onLoadPage}
            />
          )}
          {tab === "patterns" && <PatternsTab patterns={patterns} />}
          {tab === "techniques" && <TechniquesTab techniques={techniques} />}
          {tab === "log" && <LogTab logEntries={logEntries} />}
        </motion.div>
      </AnimatePresence>
    </>
  );
}

/* ─── Pages Tab ─── */

function PagesTab({
  pages,
  selectedPage,
  pageLoading,
  onLoadPage,
}: {
  pages: WikiPageItem[];
  selectedPage: WikiPageContent | null;
  pageLoading: boolean;
  onLoadPage: (path: string) => void;
}) {
  if (pages.length === 0) {
    return <p style={{ color: "#6b7280" }}>Страницы ещё не созданы. Менеджер должен пройти тренировку.</p>;
  }
  return (
    <div>
      <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        {pages.map((p) => (
          <button
            key={p.id}
            onClick={() => onLoadPage(p.page_path)}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "0.75rem 1rem",
              background: selectedPage?.page_path === p.page_path
                ? "rgba(245,158,11,0.08)"
                : "rgba(255,255,255,0.03)",
              border: `1px solid ${selectedPage?.page_path === p.page_path ? "rgba(245,158,11,0.2)" : "rgba(255,255,255,0.06)"}`,
              borderRadius: 8,
              cursor: "pointer",
              color: "#e0e0e0",
              textAlign: "left",
              width: "100%",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
              <FileText size={16} style={{ color: "#f59e0b" }} />
              <div>
                <div style={{ fontWeight: 500 }}>{p.page_path}</div>
                <div style={{ fontSize: "0.75rem", color: "#6b7280" }}>
                  {p.page_type} | v{p.version}
                  {p.updated_at && ` | ${formatDate(p.updated_at)}`}
                </div>
              </div>
            </div>
            <ChevronRight size={16} style={{ color: "#6b7280" }} />
          </button>
        ))}
      </div>

      {pageLoading && (
        <div style={{ textAlign: "center", padding: "2rem" }}>
          <Loader2 size={24} style={{ animation: "spin 1s linear infinite", color: "#f59e0b" }} />
        </div>
      )}

      {selectedPage && !pageLoading && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          style={{
            marginTop: "1.5rem",
            padding: "1.5rem",
            background: "rgba(255,255,255,0.03)",
            border: "1px solid rgba(255,255,255,0.08)",
            borderRadius: 12,
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "1rem" }}>
            <h3 style={{ color: "#f59e0b", margin: 0 }}>{selectedPage.page_path}</h3>
            <span style={{ fontSize: "0.75rem", color: "#6b7280" }}>v{selectedPage.version}</span>
          </div>
          {selectedPage.tags && selectedPage.tags.length > 0 && (
            <div style={{ display: "flex", gap: "0.3rem", flexWrap: "wrap", marginBottom: "1rem" }}>
              {selectedPage.tags.map((tag) => (
                <span
                  key={tag}
                  style={{
                    padding: "2px 8px",
                    borderRadius: 6,
                    background: "rgba(99,102,241,0.1)",
                    color: "#818cf8",
                    fontSize: "0.7rem",
                  }}
                >
                  {tag}
                </span>
              ))}
            </div>
          )}
          <div
            className="wiki-content"
            style={{ color: "#d1d5db", lineHeight: 1.7, fontSize: "0.9rem" }}
          >
            <Markdown
              skipHtml
              allowedElements={["h1", "h2", "h3", "h4", "p", "ul", "ol", "li", "strong", "em", "a", "br", "code", "pre", "blockquote"]}
              components={{
                h2: ({ children }) => <h2 style={{ fontSize: "1.3rem", fontWeight: 700, margin: "1.5rem 0 0.75rem", color: "#fff" }}>{children}</h2>,
                h3: ({ children }) => <h3 style={{ fontSize: "1.1rem", fontWeight: 600, margin: "1rem 0 0.5rem", color: "#e0e0e0" }}>{children}</h3>,
                strong: ({ children }) => <strong style={{ color: "#fff" }}>{children}</strong>,
                li: ({ children }) => <li style={{ margin: "0.25rem 0", paddingLeft: "0.5rem" }}>{children}</li>,
              }}
            >
              {selectedPage.content}
            </Markdown>
          </div>
        </motion.div>
      )}
    </div>
  );
}

/* ─── Patterns Tab ─── */

function PatternsTab({ patterns }: { patterns: PatternItem[] }) {
  if (patterns.length === 0) {
    return <p style={{ color: "#6b7280" }}>Паттерны ещё не обнаружены.</p>;
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {patterns.map((p) => {
        const config = CATEGORY_CONFIG[p.category] || CATEGORY_CONFIG.weakness;
        return (
          <div
            key={p.id}
            style={{
              padding: "1rem",
              background: "rgba(255,255,255,0.03)",
              border: `1px solid ${config.color}33`,
              borderRadius: 10,
              borderLeft: `3px solid ${config.color}`,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem", flexWrap: "wrap" }}>
              <config.icon size={16} style={{ color: config.color }} />
              <span style={{ fontWeight: 600, color: "#e0e0e0" }}>{p.pattern_code}</span>
              <span
                style={{
                  fontSize: "0.7rem",
                  padding: "2px 8px",
                  borderRadius: 10,
                  background: `${config.color}22`,
                  color: config.color,
                }}
              >
                {config.label}
              </span>
              {p.is_confirmed && (
                <span
                  style={{
                    fontSize: "0.7rem",
                    padding: "2px 8px",
                    borderRadius: 10,
                    background: "rgba(34,197,94,0.15)",
                    color: "#22c55e",
                  }}
                >
                  Подтверждён
                </span>
              )}
              {p.impact_on_score_delta != null && (
                <span
                  style={{
                    marginLeft: "auto",
                    fontSize: "0.75rem",
                    color: p.impact_on_score_delta < 0 ? "#ef4444" : "#22c55e",
                    fontWeight: 600,
                  }}
                >
                  {p.impact_on_score_delta > 0 ? "+" : ""}{p.impact_on_score_delta.toFixed(1)} score
                </span>
              )}
            </div>
            <p style={{ color: "#9ca3af", margin: "0.25rem 0", fontSize: "0.9rem" }}>
              {p.description}
            </p>
            <div style={{ fontSize: "0.75rem", color: "#6b7280" }}>
              Замечен в {p.sessions_in_pattern} сессиях
              {p.mitigation_technique && ` | Рекомендация: ${p.mitigation_technique}`}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ─── Techniques Tab ─── */

function TechniquesTab({ techniques }: { techniques: TechniqueItem[] }) {
  if (techniques.length === 0) {
    return <p style={{ color: "#6b7280" }}>Техники ещё не обнаружены.</p>;
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {techniques.map((t) => (
        <div
          key={t.id}
          style={{
            padding: "1rem",
            background: "rgba(255,255,255,0.03)",
            border: "1px solid rgba(255,255,255,0.06)",
            borderRadius: 10,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
            <Zap size={16} style={{ color: "#f59e0b" }} />
            <span style={{ fontWeight: 600, color: "#e0e0e0" }}>{t.technique_name}</span>
            {t.applicable_to_archetype && (
              <span
                style={{
                  fontSize: "0.7rem",
                  padding: "2px 8px",
                  borderRadius: 10,
                  background: "rgba(99,102,241,0.1)",
                  color: "#818cf8",
                }}
              >
                {t.applicable_to_archetype}
              </span>
            )}
            <span
              style={{
                marginLeft: "auto",
                fontSize: "0.8rem",
                color: t.success_rate >= 0.7 ? "#22c55e" : t.success_rate >= 0.4 ? "#f59e0b" : "#ef4444",
                fontWeight: 600,
              }}
            >
              {Math.round(t.success_rate * 100)}% успеха
            </span>
          </div>
          {t.description && (
            <p style={{ color: "#9ca3af", margin: "0.25rem 0", fontSize: "0.9rem" }}>
              {t.description}
            </p>
          )}
          {t.how_to_apply && (
            <p style={{ color: "#d1d5db", margin: "0.5rem 0 0.25rem", fontSize: "0.85rem", fontStyle: "italic" }}>
              Как применять: {t.how_to_apply}
            </p>
          )}
          <div style={{ fontSize: "0.75rem", color: "#6b7280" }}>
            Использовано {t.attempt_count} раз | Успешно {t.success_count}
          </div>
        </div>
      ))}
    </div>
  );
}

/* ─── Log Tab ─── */

function LogTab({ logEntries }: { logEntries: WikiLogEntry[] }) {
  if (logEntries.length === 0) {
    return <p style={{ color: "#6b7280" }}>Лог пуст — нет записей об изменениях.</p>;
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
      {logEntries.map((entry) => (
        <div
          key={entry.id}
          style={{
            padding: "0.75rem 1rem",
            background: entry.error_msg ? "rgba(239,68,68,0.04)" : "rgba(255,255,255,0.03)",
            border: `1px solid ${entry.error_msg ? "rgba(239,68,68,0.15)" : "rgba(255,255,255,0.06)"}`,
            borderRadius: 8,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.3rem" }}>
            <span style={{
              fontSize: "0.75rem",
              padding: "2px 8px",
              borderRadius: 6,
              background: entry.status === "completed" ? "rgba(34,197,94,0.12)" : entry.status === "failed" ? "rgba(239,68,68,0.12)" : "rgba(245,158,11,0.12)",
              color: entry.status === "completed" ? "#22c55e" : entry.status === "failed" ? "#ef4444" : "#f59e0b",
              fontWeight: 600,
            }}>
              {entry.status === "completed" ? "Готово" : entry.status === "failed" ? "Ошибка" : "В процессе"}
            </span>
            <span style={{ fontWeight: 500, color: "#e0e0e0", fontSize: "0.9rem" }}>
              {ACTION_LABELS[entry.action] || entry.action}
            </span>
            <span style={{ marginLeft: "auto", fontSize: "0.75rem", color: "#6b7280" }}>
              {formatDate(entry.started_at)}
            </span>
          </div>
          {entry.description && (
            <p style={{ color: "#9ca3af", margin: "0.25rem 0 0", fontSize: "0.8rem" }}>
              {entry.description}
            </p>
          )}
          <div style={{ display: "flex", gap: "1rem", marginTop: "0.3rem", fontSize: "0.75rem", color: "#6b7280" }}>
            {entry.pages_created > 0 && <span>+{entry.pages_created} страниц</span>}
            {entry.pages_modified > 0 && <span>{entry.pages_modified} обновлено</span>}
            {entry.patterns_discovered.length > 0 && (
              <span style={{ color: "#ef4444" }}>+{entry.patterns_discovered.length} паттернов</span>
            )}
            {entry.tokens_used > 0 && <span>{entry.tokens_used} токенов</span>}
          </div>
          {entry.error_msg && (
            <p style={{ color: "#ef4444", margin: "0.3rem 0 0", fontSize: "0.75rem" }}>
              {entry.error_msg}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}
