"use client";

import { useEffect, useState, useCallback } from "react";
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
  Edit3,
  Save,
  X,
  Download,
  Play,
  Calendar,
  Settings,
  CheckCircle,
  PauseCircle,
  PlayCircle,
  Archive,
  BarChart3,
  PieChart,
  RotateCcw,
} from "lucide-react";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  PointElement,
  LineElement,
  ArcElement,
  RadialLinearScale,
  Tooltip,
  Legend,
  Filler,
} from "chart.js";
import { Bar, Line, Doughnut, Radar } from "react-chartjs-2";
import { api } from "@/lib/api";
import Markdown from "react-markdown";

ChartJS.register(CategoryScale, LinearScale, BarElement, PointElement, LineElement, ArcElement, RadialLinearScale, Tooltip, Legend, Filler);

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

interface SchedulerStatus {
  running: boolean;
  last_ingest_run: string | null;
  last_daily_run: string | null;
  last_weekly_run: string | null;
  stats: {
    total_ingests: number;
    total_daily_syntheses: number;
    total_weekly_syntheses: number;
    errors: number;
  };
  config: {
    ingest_interval_hours: number;
    daily_synthesis_hour_utc: number;
    weekly_synthesis_day: string;
    weekly_synthesis_hour_utc: number;
  };
}

interface WikiChartData {
  period_days: number;
  daily_sessions: { date: string; sessions: number; avg_score: number }[];
  pattern_distribution: { category: string; count: number }[];
  wiki_activity: { date: string; ingests: number; pages_created: number; pages_modified: number }[];
  top_managers: { manager_id: string; name: string; sessions: number; patterns: number; pages: number }[];
}

interface EnrichedProfile {
  manager_id: string;
  name: string;
  training: {
    total_sessions: number;
    avg_score: number;
    best_score: number;
    total_hours: number;
    recent_14d_sessions: number;
    recent_14d_avg_score: number;
    score_trend: { score: number; date: string }[];
  };
  skills: Record<string, number>;
  pipeline: Record<string, any>;
  wiki: { exists: boolean; pages_count: number; sessions_ingested: number; patterns_discovered: number };
  patterns_summary: {
    total: number;
    weaknesses: number;
    strengths: number;
    top_weaknesses: { code: string; description: string; sessions: number }[];
    top_strengths: { code: string; description: string; sessions: number }[];
  };
  techniques_summary: {
    total: number;
    best: { code: string; name: string; success_rate: number; attempts: number }[];
  };
}

interface CompareManager {
  manager_id: string;
  name: string;
  sessions_total: number;
  avg_score: number;
  best_score: number;
  worst_score: number;
  score_layers: Record<string, number>;
  skills: Record<string, number>;
  patterns_total: number;
  patterns_by_category: Record<string, number>;
  patterns: { code: string; category: string; description: string; sessions_count: number; confirmed: boolean }[];
  techniques_total: number;
  techniques: { code: string; name: string; success_rate: number; attempts: number }[];
  wiki_pages: number;
  wiki_sessions_ingested: number;
}

type View = "list" | "detail";
type DetailTab = "pages" | "patterns" | "techniques" | "log" | "charts" | "profile";

/* ─── Category config ─── */

const CATEGORY_CONFIG: Record<string, { label: string; color: string; icon: typeof AlertTriangle }> = {
  weakness: { label: "Слабость", color: "#ef4444", icon: AlertTriangle },
  strength: { label: "Сила", color: "#22c55e", icon: TrendingUp },
  quirk: { label: "Особенность", color: "#f59e0b", icon: Zap },
  misconception: { label: "Заблуждение", color: "#8b5cf6", icon: AlertTriangle },
};

const ACTION_LABELS: Record<string, string> = {
  ingest_session: "Анализ сессии",
  daily_synthesis: "Дневной синтез",
  weekly_synthesis: "Недельный синтез",
  monthly_review: "Месячный обзор",
  lint_pass: "Lint pass",
  manual_edit: "Ручная правка",
  rebuild_page: "Перестроение страницы",
  pattern_discovered: "Новый паттерн",
  technique_discovered: "Новая техника",
};

/* ─── Helpers ─── */

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

export function WikiDashboard() {

  // ── State ──
  const [view, setView] = useState<View>("list");
  const [loading, setLoading] = useState(true);
  const [globalStats, setGlobalStats] = useState<GlobalStats | null>(null);
  const [wikis, setWikis] = useState<ManagerWikiSummary[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [schedulerStatus, setSchedulerStatus] = useState<SchedulerStatus | null>(null);

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

  // Chart data
  const [chartData, setChartData] = useState<WikiChartData | null>(null);
  const [chartLoading, setChartLoading] = useState(false);

  // Enriched profile
  const [enrichedProfile, setEnrichedProfile] = useState<EnrichedProfile | null>(null);

  // Comparison mode
  const [compareMode, setCompareMode] = useState(false);
  const [compareSelected, setCompareSelected] = useState<string[]>([]);
  const [compareData, setCompareData] = useState<CompareManager[] | null>(null);
  const [compareLoading, setCompareLoading] = useState(false);

  // Action state
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<{ text: string; type: "success" | "error" } | null>(null);

  // ── Data loading ──

  const loadList = useCallback(async () => {
    setLoading(true);
    try {
      const [statsRes, wikisRes, schedRes, chartsRes] = await Promise.all([
        api.get("/wiki/global/stats"),
        api.get("/wiki/managers"),
        api.get("/wiki/scheduler/status").catch(() => null),
        api.get("/wiki/dashboard/charts?days=30").catch(() => null),
      ]);
      setGlobalStats(statsRes);
      setWikis(wikisRes.wikis || []);
      if (schedRes) setSchedulerStatus(schedRes);
      if (chartsRes) setChartData(chartsRes);
    } catch (err) {
      console.error("Wiki load error:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadList();
  }, [loadList]);

  const openManager = useCallback(async (mgr: ManagerWikiSummary) => {
    setSelectedManager(mgr);
    setView("detail");
    setDetailTab("profile");
    setSelectedPage(null);
    setEnrichedProfile(null);
    setDetailLoading(true);
    try {
      const [pagesRes, patternsRes, techniquesRes, logRes, enrichedRes] = await Promise.all([
        api.get(`/wiki/${mgr.manager_id}/pages`),
        api.get(`/wiki/${mgr.manager_id}/patterns`),
        api.get(`/wiki/${mgr.manager_id}/techniques`),
        api.get(`/wiki/${mgr.manager_id}/log`),
        api.get(`/wiki/manager/${mgr.manager_id}/enriched`).catch(() => null),
      ]);
      setPages(pagesRes.pages || []);
      setPatterns(patternsRes.patterns || []);
      setTechniques(techniquesRes.techniques || []);
      setLogEntries(logRes.log || []);
      if (enrichedRes) setEnrichedProfile(enrichedRes);
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

  // ── Action handlers ──

  const showMessage = (text: string, type: "success" | "error") => {
    setActionMessage({ text, type });
    setTimeout(() => setActionMessage(null), 4000);
  };

  const handleIngestAll = useCallback(async (managerId: string) => {
    setActionLoading("ingest-all");
    try {
      const res = await api.post(`/wiki/${managerId}/ingest-all`, {});
      showMessage(`Ingested ${res.ingested} sessions`, "success");
      // Reload detail
      if (selectedManager) openManager(selectedManager);
    } catch (err: any) {
      showMessage(err.message || "Ingest failed", "error");
    } finally {
      setActionLoading(null);
    }
  }, [selectedManager, openManager]);

  const handleExport = useCallback(async (managerId: string, format: "pdf" | "csv") => {
    setActionLoading(`export-${format}`);
    try {
      const baseUrl = window.location.origin.replace(":3000", ":8000");
      const token = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/)?.[1];
      const res = await fetch(`${baseUrl}/api/wiki/${managerId}/export?format=${format}`, {
        credentials: "include",
        headers: token ? { "X-CSRF-Token": decodeURIComponent(token) } : {},
      });
      if (!res.ok) throw new Error(`Export failed: ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `wiki_export.${format}`;
      a.click();
      URL.revokeObjectURL(url);
      showMessage(`Export ${format.toUpperCase()} downloaded`, "success");
    } catch (err: any) {
      showMessage(err.message || "Export failed", "error");
    } finally {
      setActionLoading(null);
    }
  }, []);

  const handleDailySynthesis = useCallback(async (managerId?: string) => {
    setActionLoading("daily");
    try {
      const url = managerId ? `/wiki/synthesis/daily?manager_id=${managerId}` : "/wiki/synthesis/daily";
      const res = await api.post(url, {});
      const completed = (res.results || []).filter((r: any) => r.status === "completed").length;
      showMessage(`Daily synthesis: ${completed} wiki(s) updated`, "success");
      if (selectedManager) openManager(selectedManager);
    } catch (err: any) {
      showMessage(err.message || "Synthesis failed", "error");
    } finally {
      setActionLoading(null);
    }
  }, [selectedManager, openManager]);

  const handleWeeklySynthesis = useCallback(async (managerId?: string) => {
    setActionLoading("weekly");
    try {
      const url = managerId ? `/wiki/synthesis/weekly?manager_id=${managerId}` : "/wiki/synthesis/weekly";
      const res = await api.post(url, {});
      const completed = (res.results || []).filter((r: any) => r.status === "completed").length;
      showMessage(`Weekly synthesis: ${completed} wiki(s) updated`, "success");
      if (selectedManager) openManager(selectedManager);
    } catch (err: any) {
      showMessage(err.message || "Synthesis failed", "error");
    } finally {
      setActionLoading(null);
    }
  }, [selectedManager, openManager]);

  const handleSavePage = useCallback(async (managerId: string, pagePath: string, content: string) => {
    setActionLoading("save-page");
    try {
      await api.put(`/wiki/${managerId}/pages/${pagePath}`, { content });
      showMessage("Page saved", "success");
      // Reload page content
      await loadPageContent(managerId, pagePath);
    } catch (err: any) {
      showMessage(err.message || "Save failed", "error");
    } finally {
      setActionLoading(null);
    }
  }, [loadPageContent]);

  const handleChangeStatus = useCallback(async (managerId: string, newStatus: string) => {
    setActionLoading(`status-${newStatus}`);
    try {
      const res = await api.put(`/wiki/manager/${managerId}/status`, { status: newStatus });
      showMessage(res.message || `Status → ${newStatus}`, "success");
      // Update local state
      setWikis((prev) => prev.map((w) => w.manager_id === managerId ? { ...w, status: newStatus } : w));
      if (selectedManager?.manager_id === managerId) {
        setSelectedManager((prev) => prev ? { ...prev, status: newStatus } : prev);
      }
    } catch (err: any) {
      showMessage(err.message || "Status change failed", "error");
    } finally {
      setActionLoading(null);
    }
  }, [selectedManager]);

  const handleReanalyze = useCallback(async (managerId: string) => {
    setActionLoading("reanalyze");
    try {
      const res = await api.post(`/wiki/manager/${managerId}/reanalyze`, {});
      showMessage(res.message || "Re-analysis started", "success");
      if (selectedManager) openManager(selectedManager);
    } catch (err: any) {
      showMessage(err.message || "Re-analysis failed", "error");
    } finally {
      setActionLoading(null);
    }
  }, [selectedManager, openManager]);

  // ── Compare handler ──
  const handleCompare = useCallback(async () => {
    if (compareSelected.length < 2) return;
    setCompareLoading(true);
    try {
      const res = await api.get(`/wiki/compare?ids=${compareSelected.join(",")}`);
      setCompareData(res.managers || []);
    } catch (err: any) {
      showMessage(err.message || "Comparison failed", "error");
    } finally {
      setCompareLoading(false);
    }
  }, [compareSelected]);

  const toggleCompareSelect = useCallback((managerId: string) => {
    setCompareSelected((prev) => {
      if (prev.includes(managerId)) return prev.filter((id) => id !== managerId);
      if (prev.length >= 5) return prev;
      return [...prev, managerId];
    });
  }, []);

  // ── Filtering ──
  const filteredWikis = wikis.filter((w) =>
    w.manager_name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // ── Loading ──
  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: "4rem 2rem" }}>
        <Loader2 size={36} style={{ animation: "spin 1s linear infinite", color: "#f59e0b" }} />
        <p style={{ color: "#9ca3af", marginTop: "1rem" }}>Загрузка Wiki...</p>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto" }}>
        {/* Action message toast */}
        <AnimatePresence>
          {actionMessage && (
            <motion.div
              initial={{ opacity: 0, y: -20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              style={{
                position: "fixed",
                top: 20,
                right: 20,
                zIndex: 1000,
                padding: "0.75rem 1.25rem",
                borderRadius: 10,
                background: actionMessage.type === "success" ? "rgba(34,197,94,0.15)" : "rgba(239,68,68,0.15)",
                border: `1px solid ${actionMessage.type === "success" ? "rgba(34,197,94,0.3)" : "rgba(239,68,68,0.3)"}`,
                color: actionMessage.type === "success" ? "#22c55e" : "#ef4444",
                fontSize: "0.85rem",
                fontWeight: 500,
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
              }}
            >
              {actionMessage.type === "success" ? <CheckCircle size={16} /> : <AlertTriangle size={16} />}
              {actionMessage.text}
            </motion.div>
          )}
        </AnimatePresence>

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
            schedulerStatus={schedulerStatus}
            onDailySynthesis={() => handleDailySynthesis()}
            onWeeklySynthesis={() => handleWeeklySynthesis()}
            actionLoading={actionLoading}
            chartData={chartData}
            compareMode={compareMode}
            onToggleCompareMode={() => { setCompareMode(!compareMode); setCompareSelected([]); setCompareData(null); }}
            compareSelected={compareSelected}
            onToggleCompareSelect={toggleCompareSelect}
            onCompare={handleCompare}
            compareData={compareData}
            compareLoading={compareLoading}
            onCloseCompare={() => setCompareData(null)}
          />
        ) : (
          <ManagerDetailView
            manager={selectedManager!}
            tab={detailTab}
            onTabChange={setDetailTab}
            enrichedProfile={enrichedProfile}
            pages={pages}
            patterns={patterns}
            techniques={techniques}
            logEntries={logEntries}
            selectedPage={selectedPage}
            loading={detailLoading}
            pageLoading={pageLoading}
            onBack={() => { setView("list"); setSelectedManager(null); }}
            onLoadPage={(path) => loadPageContent(selectedManager!.manager_id, path)}
            onSavePage={(path, content) => handleSavePage(selectedManager!.manager_id, path, content)}
            onIngestAll={() => handleIngestAll(selectedManager!.manager_id)}
            onExport={(fmt) => handleExport(selectedManager!.manager_id, fmt)}
            onDailySynthesis={() => handleDailySynthesis(selectedManager!.manager_id)}
            onWeeklySynthesis={() => handleWeeklySynthesis(selectedManager!.manager_id)}
            onChangeStatus={(status) => handleChangeStatus(selectedManager!.manager_id, status)}
            onReanalyze={() => handleReanalyze(selectedManager!.manager_id)}
            actionLoading={actionLoading}
          />
        )}
    </div>
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
  schedulerStatus,
  onDailySynthesis,
  onWeeklySynthesis,
  actionLoading,
  chartData,
  compareMode,
  onToggleCompareMode,
  compareSelected,
  onToggleCompareSelect,
  onCompare,
  compareData,
  compareLoading,
  onCloseCompare,
}: {
  globalStats: GlobalStats | null;
  wikis: ManagerWikiSummary[];
  searchQuery: string;
  onSearch: (q: string) => void;
  onSelectManager: (w: ManagerWikiSummary) => void;
  onRefresh: () => void;
  showHelp: boolean;
  onToggleHelp: () => void;
  schedulerStatus: SchedulerStatus | null;
  onDailySynthesis: () => void;
  onWeeklySynthesis: () => void;
  actionLoading: string | null;
  chartData: WikiChartData | null;
  compareMode: boolean;
  onToggleCompareMode: () => void;
  compareSelected: string[];
  onToggleCompareSelect: (id: string) => void;
  onCompare: () => void;
  compareData: CompareManager[] | null;
  compareLoading: boolean;
  onCloseCompare: () => void;
}) {
  const [showCharts, setShowCharts] = useState(false);
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
          onClick={onToggleCompareMode}
          style={{
            padding: "0.5rem 0.75rem",
            background: compareMode ? "rgba(99,102,241,0.15)" : "rgba(255,255,255,0.04)",
            border: `1px solid ${compareMode ? "rgba(99,102,241,0.3)" : "rgba(255,255,255,0.08)"}`,
            borderRadius: 8,
            color: compareMode ? "#6366f1" : "#9ca3af",
            cursor: "pointer",
            fontSize: "0.8rem",
            display: "flex",
            alignItems: "center",
            gap: "0.3rem",
          }}
          title="Сравнить менеджеров"
        >
          <Users size={16} />
          Сравнить
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

      {/* Compare bar */}
      {compareMode && (
        <div style={{
          display: "flex",
          alignItems: "center",
          gap: "0.75rem",
          padding: "0.75rem 1rem",
          marginBottom: "1rem",
          background: "rgba(99,102,241,0.08)",
          border: "1px solid rgba(99,102,241,0.2)",
          borderRadius: 10,
          flexWrap: "wrap",
        }}>
          <Users size={18} style={{ color: "#6366f1" }} />
          <span style={{ color: "#a5b4fc", fontSize: "0.85rem" }}>
            Выберите 2–5 менеджеров для сравнения ({compareSelected.length} выбрано)
          </span>
          <div style={{ flex: 1 }} />
          <button
            onClick={onCompare}
            disabled={compareSelected.length < 2 || compareLoading}
            style={{
              padding: "0.4rem 1rem",
              background: compareSelected.length >= 2 ? "rgba(99,102,241,0.2)" : "rgba(255,255,255,0.04)",
              border: "1px solid rgba(99,102,241,0.3)",
              borderRadius: 8,
              color: compareSelected.length >= 2 ? "#a5b4fc" : "#6b7280",
              cursor: compareSelected.length >= 2 ? "pointer" : "not-allowed",
              fontSize: "0.85rem",
              fontWeight: 600,
              display: "flex",
              alignItems: "center",
              gap: "0.3rem",
            }}
          >
            {compareLoading ? <Loader2 size={14} style={{ animation: "spin 1s linear infinite" }} /> : <BarChart3 size={14} />}
            Сравнить
          </button>
        </div>
      )}

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
                которая автоматически строится из тренировочных сессий.
              </p>
              <p style={{ margin: "0 0 0.5rem" }}>
                <strong style={{ color: "#fff" }}>Автоматика:</strong> Каждые 12 часов система автоматически анализирует новые сессии.
                Ежедневно в 03:00 UTC формируется дневной синтез, еженедельно по понедельникам — недельный.
              </p>
              <ul style={{ margin: "0 0 0.5rem", paddingLeft: "1.5rem" }}>
                <li><strong style={{ color: "#ef4444" }}>Слабости</strong> — паттерны ошибок</li>
                <li><strong style={{ color: "#22c55e" }}>Техники</strong> — успешные приёмы с % успеха</li>
                <li><strong style={{ color: "#f59e0b" }}>Страницы</strong> — обзоры, инсайты, рекомендации</li>
                <li><strong style={{ color: "#8b5cf6" }}>Синтез</strong> — дневные и недельные AI-резюме</li>
              </ul>
              <p style={{ margin: "0 0 0.5rem" }}>
                <strong style={{ color: "#fff" }}>Действия:</strong> Вы можете редактировать страницы, экспортировать данные в PDF/CSV,
                запускать синтез вручную и инжестить пропущенные сессии.
              </p>
              <p style={{ margin: 0, fontSize: "0.8rem", color: "#9ca3af" }}>
                Эта панель доступна только администраторам.
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

      {/* Scheduler status + global actions */}
      <div
        style={{
          display: "flex",
          gap: "0.5rem",
          marginBottom: "1.5rem",
          flexWrap: "wrap",
          alignItems: "center",
        }}
      >
        {schedulerStatus && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              padding: "0.4rem 0.75rem",
              background: schedulerStatus.running ? "rgba(34,197,94,0.08)" : "rgba(239,68,68,0.08)",
              border: `1px solid ${schedulerStatus.running ? "rgba(34,197,94,0.2)" : "rgba(239,68,68,0.2)"}`,
              borderRadius: 8,
              fontSize: "0.8rem",
              color: schedulerStatus.running ? "#22c55e" : "#ef4444",
            }}
          >
            <Settings size={14} />
            Планировщик: {schedulerStatus.running ? "работает" : "остановлен"}
            {schedulerStatus.last_ingest_run && (
              <span style={{ color: "#6b7280", marginLeft: 4 }}>
                | Последний инжест: {timeAgo(schedulerStatus.last_ingest_run)}
              </span>
            )}
          </div>
        )}
        <div style={{ flex: 1 }} />
        <ActionButton
          icon={Calendar}
          label="Дневной синтез"
          onClick={onDailySynthesis}
          loading={actionLoading === "daily"}
          color="#6366f1"
        />
        <ActionButton
          icon={Calendar}
          label="Недельный синтез"
          onClick={onWeeklySynthesis}
          loading={actionLoading === "weekly"}
          color="#8b5cf6"
        />
        <ActionButton
          icon={BarChart3}
          label={showCharts ? "Скрыть графики" : "Графики"}
          onClick={() => setShowCharts(!showCharts)}
          loading={false}
          color={showCharts ? "#f59e0b" : "#6b7280"}
        />
      </div>

      {/* Charts section */}
      <AnimatePresence>
        {showCharts && chartData && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            style={{ overflow: "hidden", marginBottom: "1.5rem" }}
          >
            <WikiChartsSection data={chartData} />
          </motion.div>
        )}
      </AnimatePresence>

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
              onClick={() => compareMode ? onToggleCompareSelect(w.manager_id) : onSelectManager(w)}
              whileHover={{ scale: 1.005 }}
              whileTap={{ scale: 0.995 }}
              style={{
                display: "grid",
                gridTemplateColumns: compareMode ? "auto 1fr auto auto auto auto" : "1fr auto auto auto auto",
                alignItems: "center",
                gap: "1rem",
                padding: "0.85rem 1.25rem",
                background: compareMode && compareSelected.includes(w.manager_id)
                  ? "rgba(99,102,241,0.08)"
                  : "rgba(255,255,255,0.03)",
                border: compareMode && compareSelected.includes(w.manager_id)
                  ? "1px solid rgba(99,102,241,0.3)"
                  : "1px solid rgba(255,255,255,0.06)",
                borderRadius: 10,
                cursor: "pointer",
                color: "#e0e0e0",
                textAlign: "left",
                width: "100%",
              }}
            >
              {compareMode && (
                <div style={{
                  width: 20,
                  height: 20,
                  borderRadius: 4,
                  border: compareSelected.includes(w.manager_id)
                    ? "2px solid #6366f1"
                    : "2px solid rgba(255,255,255,0.15)",
                  background: compareSelected.includes(w.manager_id)
                    ? "rgba(99,102,241,0.3)"
                    : "transparent",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}>
                  {compareSelected.includes(w.manager_id) && <CheckCircle size={14} style={{ color: "#6366f1" }} />}
                </div>
              )}
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                  <span style={{ fontWeight: 600, fontSize: "0.95rem" }}>{w.manager_name}</span>
                  {w.status && w.status !== "active" && (
                    <span style={{
                      fontSize: "0.65rem",
                      padding: "1px 6px",
                      borderRadius: 6,
                      background: w.status === "paused" ? "rgba(245,158,11,0.12)" : "rgba(107,114,128,0.15)",
                      color: w.status === "paused" ? "#f59e0b" : "#6b7280",
                      fontWeight: 600,
                    }}>
                      {w.status === "paused" ? "⏸ Пауза" : "📦 Архив"}
                    </span>
                  )}
                </div>
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

      {/* ── Compare Results Panel ── */}
      {compareData && compareData.length >= 2 && (
        <CompareResultsPanel data={compareData} onClose={onCloseCompare} />
      )}
    </>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   COMPARE RESULTS PANEL — side-by-side manager comparison (Feature 9)
   ═══════════════════════════════════════════════════════════════════════════ */

const COMPARE_COLORS = ["#f59e0b", "#6366f1", "#22c55e", "#ef4444", "#ec4899"];

function CompareResultsPanel({ data, onClose }: { data: CompareManager[]; onClose: () => void }) {
  const LAYER_LABELS: Record<string, string> = {
    script_adherence: "Скрипт",
    objection_handling: "Возражения",
    communication: "Коммуникация",
    anti_patterns: "Анти-паттерны",
    result: "Результат",
  };

  const SKILL_LABELS: Record<string, string> = {
    empathy: "Эмпатия",
    knowledge: "Знания",
    objection_handling: "Возражения",
    stress_resistance: "Стресс",
    closing: "Закрытие",
    qualification: "Квалификация",
  };

  const glassCard: React.CSSProperties = {
    background: "rgba(255,255,255,0.03)",
    border: "1px solid rgba(255,255,255,0.06)",
    borderRadius: 12,
    padding: "1rem",
  };

  // Radar chart for score layers
  const radarData = {
    labels: Object.values(LAYER_LABELS),
    datasets: data.map((m, i) => ({
      label: m.name,
      data: Object.keys(LAYER_LABELS).map((k) => m.score_layers[k] || 0),
      borderColor: COMPARE_COLORS[i],
      backgroundColor: COMPARE_COLORS[i] + "20",
      pointBackgroundColor: COMPARE_COLORS[i],
      borderWidth: 2,
    })),
  };

  // Radar for skills
  const skillKeys = Object.keys(SKILL_LABELS);
  const skillRadar = {
    labels: Object.values(SKILL_LABELS),
    datasets: data.map((m, i) => ({
      label: m.name,
      data: skillKeys.map((k) => m.skills[k] || 0),
      borderColor: COMPARE_COLORS[i],
      backgroundColor: COMPARE_COLORS[i] + "20",
      pointBackgroundColor: COMPARE_COLORS[i],
      borderWidth: 2,
    })),
  };

  const radarOpts: any = {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      r: {
        beginAtZero: true,
        ticks: { color: "#6b7280", backdropColor: "transparent", font: { size: 10 } },
        grid: { color: "rgba(255,255,255,0.06)" },
        pointLabels: { color: "#9ca3af", font: { size: 11 } },
      },
    },
    plugins: { legend: { labels: { color: "#9ca3af", font: { size: 11 } } } },
  };

  // Bar chart for avg scores
  const barData = {
    labels: data.map((m) => m.name),
    datasets: [
      {
        label: "Средний балл",
        data: data.map((m) => m.avg_score),
        backgroundColor: data.map((_, i) => COMPARE_COLORS[i] + "80"),
        borderColor: data.map((_, i) => COMPARE_COLORS[i]),
        borderWidth: 1,
        borderRadius: 6,
      },
      {
        label: "Лучший балл",
        data: data.map((m) => m.best_score),
        backgroundColor: data.map((_, i) => COMPARE_COLORS[i] + "30"),
        borderColor: data.map((_, i) => COMPARE_COLORS[i]),
        borderWidth: 1,
        borderRadius: 6,
        borderDash: [3, 3],
      },
    ],
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      style={{ marginTop: "1.5rem" }}
    >
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "1rem" }}>
        <Users size={22} style={{ color: "#6366f1" }} />
        <h2 style={{ fontSize: "1.3rem", fontWeight: 700, color: "#fff", margin: 0 }}>
          Сравнение менеджеров
        </h2>
        <div style={{ flex: 1 }} />
        <button
          onClick={onClose}
          style={{
            padding: "0.4rem",
            background: "rgba(255,255,255,0.04)",
            border: "1px solid rgba(255,255,255,0.08)",
            borderRadius: 8,
            color: "#9ca3af",
            cursor: "pointer",
          }}
        >
          <X size={18} />
        </button>
      </div>

      {/* Summary cards */}
      <div style={{ display: "grid", gridTemplateColumns: `repeat(${data.length}, 1fr)`, gap: "0.75rem", marginBottom: "1rem" }}>
        {data.map((m, i) => (
          <div key={m.manager_id + i} style={{
            ...glassCard,
            borderTop: `3px solid ${COMPARE_COLORS[i]}`,
          }}>
            <div style={{ fontWeight: 700, color: "#fff", fontSize: "1rem", marginBottom: "0.5rem" }}>{m.name}</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.3rem", fontSize: "0.8rem" }}>
              <div><span style={{ color: "#6b7280" }}>Сессий: </span><span style={{ color: "#f59e0b", fontWeight: 600 }}>{m.sessions_total}</span></div>
              <div><span style={{ color: "#6b7280" }}>Ср. балл: </span><span style={{ color: "#22c55e", fontWeight: 600 }}>{m.avg_score}</span></div>
              <div><span style={{ color: "#6b7280" }}>Лучший: </span><span style={{ color: "#a5b4fc", fontWeight: 600 }}>{m.best_score}</span></div>
              <div><span style={{ color: "#6b7280" }}>Худший: </span><span style={{ color: "#ef4444", fontWeight: 600 }}>{m.worst_score}</span></div>
              <div><span style={{ color: "#6b7280" }}>Паттернов: </span><span style={{ color: "#f59e0b", fontWeight: 600 }}>{m.patterns_total}</span></div>
              <div><span style={{ color: "#6b7280" }}>Техник: </span><span style={{ color: "#22c55e", fontWeight: 600 }}>{m.techniques_total}</span></div>
            </div>
          </div>
        ))}
      </div>

      {/* Charts row */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0.75rem", marginBottom: "1rem" }}>
        {/* Score comparison bar */}
        <div style={glassCard}>
          <div style={{ color: "#9ca3af", fontSize: "0.8rem", fontWeight: 600, marginBottom: "0.5rem" }}>Баллы</div>
          <div style={{ height: 220 }}>
            <Bar data={barData} options={{
              responsive: true,
              maintainAspectRatio: false,
              scales: {
                x: { ticks: { color: "#6b7280", font: { size: 10 } }, grid: { display: false } },
                y: { beginAtZero: true, ticks: { color: "#6b7280" }, grid: { color: "rgba(255,255,255,0.04)" } },
              },
              plugins: { legend: { labels: { color: "#9ca3af", font: { size: 10 } } } },
            }} />
          </div>
        </div>

        {/* Score layers radar */}
        <div style={glassCard}>
          <div style={{ color: "#9ca3af", fontSize: "0.8rem", fontWeight: 600, marginBottom: "0.5rem" }}>Слои оценки</div>
          <div style={{ height: 220 }}>
            <Radar data={radarData} options={radarOpts} />
          </div>
        </div>

        {/* Skills radar */}
        <div style={glassCard}>
          <div style={{ color: "#9ca3af", fontSize: "0.8rem", fontWeight: 600, marginBottom: "0.5rem" }}>Навыки</div>
          <div style={{ height: 220 }}>
            <Radar data={skillRadar} options={radarOpts} />
          </div>
        </div>
      </div>

      {/* Patterns & Techniques tables */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
        {/* Patterns */}
        <div style={glassCard}>
          <div style={{ color: "#9ca3af", fontSize: "0.8rem", fontWeight: 600, marginBottom: "0.75rem" }}>
            <Brain size={14} style={{ display: "inline", verticalAlign: "middle", marginRight: 4 }} />
            Паттерны по категориям
          </div>
          <table style={{ width: "100%", fontSize: "0.8rem", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid rgba(255,255,255,0.08)" }}>
                <th style={{ textAlign: "left", padding: "4px 8px", color: "#6b7280", fontWeight: 500 }}>Категория</th>
                {data.map((m, i) => (
                  <th key={m.manager_id + i} style={{ textAlign: "center", padding: "4px 8px", color: COMPARE_COLORS[i], fontWeight: 600 }}>
                    {m.name.split(" ")[0]}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {["weakness", "strength", "quirk", "misconception"].map((cat) => (
                <tr key={cat} style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                  <td style={{ padding: "4px 8px", color: CATEGORY_CONFIG[cat]?.color || "#9ca3af" }}>
                    {CATEGORY_CONFIG[cat]?.label || cat}
                  </td>
                  {data.map((m, i) => (
                    <td key={m.manager_id + i} style={{ textAlign: "center", padding: "4px 8px", color: "#e0e0e0" }}>
                      {m.patterns_by_category[cat] || 0}
                    </td>
                  ))}
                </tr>
              ))}
              <tr style={{ fontWeight: 600 }}>
                <td style={{ padding: "4px 8px", color: "#9ca3af" }}>Всего</td>
                {data.map((m, i) => (
                  <td key={m.manager_id + i} style={{ textAlign: "center", padding: "4px 8px", color: COMPARE_COLORS[i] }}>
                    {m.patterns_total}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>

        {/* Techniques */}
        <div style={glassCard}>
          <div style={{ color: "#9ca3af", fontSize: "0.8rem", fontWeight: 600, marginBottom: "0.75rem" }}>
            <Lightbulb size={14} style={{ display: "inline", verticalAlign: "middle", marginRight: 4 }} />
            Лучшие техники
          </div>
          {data.map((m, i) => (
            <div key={m.manager_id + i} style={{ marginBottom: "0.5rem" }}>
              <div style={{ fontSize: "0.75rem", fontWeight: 600, color: COMPARE_COLORS[i], marginBottom: "0.25rem" }}>{m.name}</div>
              {m.techniques.length === 0 ? (
                <div style={{ fontSize: "0.75rem", color: "#6b7280", fontStyle: "italic" }}>Нет техник</div>
              ) : (
                m.techniques.slice(0, 3).map((t) => (
                  <div key={t.code} style={{ display: "flex", justifyContent: "space-between", fontSize: "0.75rem", color: "#9ca3af", padding: "2px 0" }}>
                    <span>{t.name}</span>
                    <span style={{ color: t.success_rate >= 0.7 ? "#22c55e" : t.success_rate >= 0.4 ? "#f59e0b" : "#ef4444" }}>
                      {Math.round(t.success_rate * 100)}%
                    </span>
                  </div>
                ))
              )}
            </div>
          ))}
        </div>
      </div>
    </motion.div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   ACTION BUTTON — reusable styled button
   ═══════════════════════════════════════════════════════════════════════════ */

function ActionButton({
  icon: Icon,
  label,
  onClick,
  loading,
  color = "#f59e0b",
  disabled = false,
}: {
  icon: typeof Play;
  label: string;
  onClick: () => void;
  loading: boolean;
  color?: string;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={loading || disabled}
      style={{
        display: "flex",
        alignItems: "center",
        gap: "0.4rem",
        padding: "0.4rem 0.75rem",
        background: `${color}15`,
        border: `1px solid ${color}33`,
        borderRadius: 8,
        color: loading || disabled ? "#6b7280" : color,
        cursor: loading || disabled ? "not-allowed" : "pointer",
        fontSize: "0.8rem",
        fontWeight: 500,
        opacity: disabled ? 0.5 : 1,
      }}
    >
      {loading ? <Loader2 size={14} style={{ animation: "spin 1s linear infinite" }} /> : <Icon size={14} />}
      {label}
    </button>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   DETAIL VIEW — single manager's wiki
   ═══════════════════════════════════════════════════════════════════════════ */

const DETAIL_TABS: { id: DetailTab; label: string; icon: typeof BookOpen }[] = [
  { id: "profile", label: "Профиль", icon: Activity },
  { id: "pages", label: "Страницы", icon: FileText },
  { id: "patterns", label: "Паттерны", icon: Brain },
  { id: "techniques", label: "Техники", icon: Lightbulb },
  { id: "charts", label: "Графики", icon: BarChart3 },
  { id: "log", label: "Лог изменений", icon: Clock },
];

function ManagerDetailView({
  manager,
  tab,
  onTabChange,
  enrichedProfile,
  pages,
  patterns,
  techniques,
  logEntries,
  selectedPage,
  loading,
  pageLoading,
  onBack,
  onLoadPage,
  onSavePage,
  onIngestAll,
  onExport,
  onDailySynthesis,
  onWeeklySynthesis,
  onChangeStatus,
  onReanalyze,
  actionLoading,
}: {
  manager: ManagerWikiSummary;
  tab: DetailTab;
  onTabChange: (t: DetailTab) => void;
  enrichedProfile: EnrichedProfile | null;
  pages: WikiPageItem[];
  patterns: PatternItem[];
  techniques: TechniqueItem[];
  logEntries: WikiLogEntry[];
  selectedPage: WikiPageContent | null;
  loading: boolean;
  pageLoading: boolean;
  onBack: () => void;
  onLoadPage: (path: string) => void;
  onSavePage: (path: string, content: string) => void;
  onIngestAll: () => void;
  onExport: (format: "pdf" | "csv") => void;
  onDailySynthesis: () => void;
  onWeeklySynthesis: () => void;
  onChangeStatus: (status: string) => void;
  onReanalyze: () => void;
  actionLoading: string | null;
}) {
  const [detailChartData, setDetailChartData] = useState<WikiChartData | null>(null);

  // Load chart data when charts tab is selected — must be before early returns
  useEffect(() => {
    if (tab === "charts" && !detailChartData && !loading) {
      api.get("/wiki/dashboard/charts?days=30")
        .then((res: WikiChartData) => setDetailChartData(res))
        .catch(() => {});
    }
  }, [tab, detailChartData, loading]);

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
      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "1rem" }}>
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
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <h1 style={{ fontSize: "1.4rem", fontWeight: 700, color: "#fff", margin: 0 }}>
              {manager.manager_name}
            </h1>
            {manager.status && manager.status !== "active" && (
              <span style={{
                fontSize: "0.7rem",
                padding: "2px 8px",
                borderRadius: 8,
                background: manager.status === "paused" ? "rgba(245,158,11,0.12)" : "rgba(107,114,128,0.15)",
                color: manager.status === "paused" ? "#f59e0b" : "#6b7280",
                fontWeight: 600,
              }}>
                {manager.status === "paused" ? "⏸ На паузе" : "📦 Архив"}
              </span>
            )}
          </div>
          <p style={{ color: "#9ca3af", margin: 0, fontSize: "0.8rem" }}>
            Wiki | {manager.sessions_ingested} сессий | {manager.patterns_discovered} паттернов | {manager.pages_count} страниц
            {manager.last_ingest_at && ` | Обновлено: ${timeAgo(manager.last_ingest_at)}`}
          </p>
        </div>
      </div>

      {/* Action bar */}
      <div
        style={{
          display: "flex",
          gap: "0.5rem",
          marginBottom: "1.5rem",
          flexWrap: "wrap",
        }}
      >
        <ActionButton icon={Play} label="Инжест всех сессий" onClick={onIngestAll} loading={actionLoading === "ingest-all"} color="#22c55e" />
        <ActionButton icon={Calendar} label="Дневной синтез" onClick={onDailySynthesis} loading={actionLoading === "daily"} color="#6366f1" />
        <ActionButton icon={Calendar} label="Недельный синтез" onClick={onWeeklySynthesis} loading={actionLoading === "weekly"} color="#8b5cf6" />
        <ActionButton icon={Download} label="PDF" onClick={() => onExport("pdf")} loading={actionLoading === "export-pdf"} color="#f59e0b" />
        <ActionButton icon={Download} label="CSV" onClick={() => onExport("csv")} loading={actionLoading === "export-csv"} color="#f59e0b" />
        <div style={{ flex: 1 }} />
        {/* Status management */}
        {manager.status === "active" ? (
          <ActionButton icon={PauseCircle} label="Пауза" onClick={() => onChangeStatus("paused")} loading={actionLoading === "status-paused"} color="#f59e0b" />
        ) : manager.status === "paused" ? (
          <ActionButton icon={PlayCircle} label="Возобновить" onClick={() => onChangeStatus("active")} loading={actionLoading === "status-active"} color="#22c55e" />
        ) : null}
        <ActionButton icon={Archive} label="Архив" onClick={() => onChangeStatus("archived")} loading={actionLoading === "status-archived"} color="#6b7280" disabled={manager.status === "archived"} />
        <ActionButton icon={RotateCcw} label="Пересоздать" onClick={onReanalyze} loading={actionLoading === "reanalyze"} color="#ef4444" />
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
          {tab === "profile" && <EnrichedProfileTab profile={enrichedProfile} />}
          {tab === "pages" && (
            <PagesTab
              pages={pages}
              selectedPage={selectedPage}
              pageLoading={pageLoading}
              onLoadPage={onLoadPage}
              onSavePage={onSavePage}
              actionLoading={actionLoading}
            />
          )}
          {tab === "patterns" && <PatternsTab patterns={patterns} />}
          {tab === "techniques" && <TechniquesTab techniques={techniques} />}
          {tab === "charts" && <WikiChartsSection data={detailChartData} />}
          {tab === "log" && <LogTab logEntries={logEntries} />}
        </motion.div>
      </AnimatePresence>
    </>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   ENRICHED PROFILE TAB — Feature 8: ROP reports as data source
   ═══════════════════════════════════════════════════════════════════════════ */

function EnrichedProfileTab({ profile }: { profile: EnrichedProfile | null }) {
  if (!profile) {
    return (
      <div style={{ textAlign: "center", padding: "3rem", color: "#6b7280" }}>
        <Activity size={36} style={{ margin: "0 auto 1rem", opacity: 0.4 }} />
        <p>Профиль загружается...</p>
      </div>
    );
  }

  const glassCard: React.CSSProperties = {
    background: "rgba(255,255,255,0.03)",
    border: "1px solid rgba(255,255,255,0.06)",
    borderRadius: 12,
    padding: "1rem",
  };

  const SKILL_LABELS: Record<string, string> = {
    empathy: "Эмпатия",
    knowledge: "Знания",
    objection_handling: "Возражения",
    stress_resistance: "Стрессоуст.",
    closing: "Закрытие",
    qualification: "Квалификация",
  };

  const skillKeys = Object.keys(SKILL_LABELS);
  const skillValues = skillKeys.map((k) => profile.skills[k] || 0);

  // Skills radar
  const skillRadarData = {
    labels: Object.values(SKILL_LABELS),
    datasets: [
      {
        label: profile.name,
        data: skillValues,
        borderColor: "#f59e0b",
        backgroundColor: "rgba(245,158,11,0.15)",
        pointBackgroundColor: "#f59e0b",
        borderWidth: 2,
      },
    ],
  };

  const radarOpts: any = {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      r: {
        beginAtZero: true,
        max: 100,
        ticks: { color: "#6b7280", backdropColor: "transparent", font: { size: 10 }, stepSize: 25 },
        grid: { color: "rgba(255,255,255,0.06)" },
        pointLabels: { color: "#9ca3af", font: { size: 11 } },
      },
    },
    plugins: { legend: { display: false } },
  };

  // Score trend line chart
  const trend = profile.training.score_trend || [];
  const trendData = {
    labels: trend.map((t) => new Date(t.date).toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" })),
    datasets: [
      {
        label: "Балл",
        data: trend.map((t) => t.score),
        borderColor: "#6366f1",
        backgroundColor: "rgba(99,102,241,0.1)",
        fill: true,
        tension: 0.3,
        pointRadius: 4,
        pointBackgroundColor: "#6366f1",
      },
    ],
  };

  const trendOpts: any = {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      x: { ticks: { color: "#6b7280", font: { size: 10 } }, grid: { display: false } },
      y: { beginAtZero: true, ticks: { color: "#6b7280" }, grid: { color: "rgba(255,255,255,0.04)" } },
    },
    plugins: { legend: { display: false } },
  };

  const t = profile.training;
  const scoreDelta = t.recent_14d_sessions > 0 && t.total_sessions > t.recent_14d_sessions
    ? t.recent_14d_avg_score - t.avg_score
    : null;

  return (
    <div>
      {/* KPI Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "0.75rem", marginBottom: "1rem" }}>
        {[
          { label: "Всего сессий", value: t.total_sessions, color: "#f59e0b", icon: Target },
          { label: "Средний балл", value: t.avg_score.toFixed(1), color: "#22c55e", icon: TrendingUp },
          { label: "Лучший балл", value: t.best_score.toFixed(1), color: "#6366f1", icon: Zap },
          { label: "Часов практики", value: t.total_hours.toFixed(1), color: "#ec4899", icon: Clock },
        ].map((kpi) => (
          <div key={kpi.label} style={glassCard}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginBottom: "0.3rem" }}>
              <kpi.icon size={14} style={{ color: kpi.color }} />
              <span style={{ fontSize: "0.75rem", color: "#6b7280" }}>{kpi.label}</span>
            </div>
            <div style={{ fontSize: "1.4rem", fontWeight: 700, color: kpi.color }}>{kpi.value}</div>
          </div>
        ))}
      </div>

      {/* 14-day trend badge */}
      <div style={{
        display: "flex",
        gap: "0.75rem",
        marginBottom: "1rem",
        padding: "0.75rem 1rem",
        ...glassCard,
        flexWrap: "wrap",
        alignItems: "center",
      }}>
        <Calendar size={16} style={{ color: "#6366f1" }} />
        <span style={{ color: "#9ca3af", fontSize: "0.85rem" }}>Последние 14 дней:</span>
        <span style={{ color: "#f59e0b", fontWeight: 600 }}>{t.recent_14d_sessions} сессий</span>
        <span style={{ color: "#9ca3af" }}>|</span>
        <span style={{ color: "#22c55e", fontWeight: 600 }}>Ср. балл: {t.recent_14d_avg_score.toFixed(1)}</span>
        {scoreDelta !== null && (
          <span style={{
            padding: "2px 8px",
            borderRadius: 8,
            fontSize: "0.75rem",
            fontWeight: 600,
            background: scoreDelta >= 0 ? "rgba(34,197,94,0.12)" : "rgba(239,68,68,0.12)",
            color: scoreDelta >= 0 ? "#22c55e" : "#ef4444",
          }}>
            {scoreDelta >= 0 ? "↑" : "↓"} {Math.abs(scoreDelta).toFixed(1)} vs всё время
          </span>
        )}
      </div>

      {/* Charts row */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem", marginBottom: "1rem" }}>
        {/* Score trend */}
        <div style={glassCard}>
          <div style={{ color: "#9ca3af", fontSize: "0.8rem", fontWeight: 600, marginBottom: "0.5rem" }}>
            <TrendingUp size={14} style={{ display: "inline", verticalAlign: "middle", marginRight: 4 }} />
            Динамика баллов
          </div>
          <div style={{ height: 200 }}>
            {trend.length > 0 ? (
              <Line data={trendData} options={trendOpts} />
            ) : (
              <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "#6b7280", fontSize: "0.85rem" }}>
                Нет данных
              </div>
            )}
          </div>
        </div>

        {/* Skills radar */}
        <div style={glassCard}>
          <div style={{ color: "#9ca3af", fontSize: "0.8rem", fontWeight: 600, marginBottom: "0.5rem" }}>
            <Activity size={14} style={{ display: "inline", verticalAlign: "middle", marginRight: 4 }} />
            Навыки
            {profile.skills.level !== undefined && (
              <span style={{ marginLeft: 8, color: "#f59e0b", fontSize: "0.75rem" }}>
                Ур. {profile.skills.level} | XP: {profile.skills.total_xp} | Hunter: {profile.skills.hunter_score}
              </span>
            )}
          </div>
          <div style={{ height: 200 }}>
            <Radar data={skillRadarData} options={radarOpts} />
          </div>
        </div>
      </div>

      {/* Patterns & Techniques summary */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem", marginBottom: "1rem" }}>
        {/* Patterns summary */}
        <div style={glassCard}>
          <div style={{ color: "#9ca3af", fontSize: "0.8rem", fontWeight: 600, marginBottom: "0.75rem" }}>
            <Brain size={14} style={{ display: "inline", verticalAlign: "middle", marginRight: 4 }} />
            Паттерны ({profile.patterns_summary.total})
            <span style={{ marginLeft: 8 }}>
              <span style={{ color: "#ef4444" }}>⚠ {profile.patterns_summary.weaknesses}</span>
              {" / "}
              <span style={{ color: "#22c55e" }}>✓ {profile.patterns_summary.strengths}</span>
            </span>
          </div>
          {profile.patterns_summary.top_weaknesses.length > 0 && (
            <div style={{ marginBottom: "0.5rem" }}>
              <div style={{ fontSize: "0.7rem", color: "#ef4444", fontWeight: 600, marginBottom: "0.25rem" }}>Основные слабости:</div>
              {profile.patterns_summary.top_weaknesses.map((p) => (
                <div key={p.code} style={{ fontSize: "0.75rem", color: "#d1d5db", padding: "2px 0", display: "flex", justifyContent: "space-between" }}>
                  <span>{p.description || p.code}</span>
                  <span style={{ color: "#6b7280" }}>{p.sessions} сес.</span>
                </div>
              ))}
            </div>
          )}
          {profile.patterns_summary.top_strengths.length > 0 && (
            <div>
              <div style={{ fontSize: "0.7rem", color: "#22c55e", fontWeight: 600, marginBottom: "0.25rem" }}>Сильные стороны:</div>
              {profile.patterns_summary.top_strengths.map((p) => (
                <div key={p.code} style={{ fontSize: "0.75rem", color: "#d1d5db", padding: "2px 0", display: "flex", justifyContent: "space-between" }}>
                  <span>{p.description || p.code}</span>
                  <span style={{ color: "#6b7280" }}>{p.sessions} сес.</span>
                </div>
              ))}
            </div>
          )}
          {profile.patterns_summary.total === 0 && (
            <div style={{ fontSize: "0.8rem", color: "#6b7280", fontStyle: "italic" }}>Паттерны ещё не обнаружены</div>
          )}
        </div>

        {/* Techniques summary */}
        <div style={glassCard}>
          <div style={{ color: "#9ca3af", fontSize: "0.8rem", fontWeight: 600, marginBottom: "0.75rem" }}>
            <Lightbulb size={14} style={{ display: "inline", verticalAlign: "middle", marginRight: 4 }} />
            Техники ({profile.techniques_summary.total})
          </div>
          {profile.techniques_summary.best.length > 0 ? (
            profile.techniques_summary.best.map((t) => (
              <div key={t.code} style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                fontSize: "0.8rem",
                padding: "0.3rem 0",
                borderBottom: "1px solid rgba(255,255,255,0.04)",
              }}>
                <span style={{ color: "#d1d5db" }}>{t.name}</span>
                <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                  <span style={{ color: "#6b7280", fontSize: "0.7rem" }}>{t.attempts} попыток</span>
                  <span style={{
                    padding: "1px 8px",
                    borderRadius: 8,
                    fontSize: "0.7rem",
                    fontWeight: 600,
                    background: t.success_rate >= 0.7 ? "rgba(34,197,94,0.12)" : t.success_rate >= 0.4 ? "rgba(245,158,11,0.12)" : "rgba(239,68,68,0.12)",
                    color: t.success_rate >= 0.7 ? "#22c55e" : t.success_rate >= 0.4 ? "#f59e0b" : "#ef4444",
                  }}>
                    {Math.round(t.success_rate * 100)}%
                  </span>
                </div>
              </div>
            ))
          ) : (
            <div style={{ fontSize: "0.8rem", color: "#6b7280", fontStyle: "italic" }}>Техники ещё не обнаружены</div>
          )}
        </div>
      </div>

      {/* Wiki summary */}
      <div style={glassCard}>
        <div style={{ color: "#9ca3af", fontSize: "0.8rem", fontWeight: 600, marginBottom: "0.5rem" }}>
          <BookOpen size={14} style={{ display: "inline", verticalAlign: "middle", marginRight: 4 }} />
          Wiki статус
        </div>
        <div style={{ display: "flex", gap: "2rem", fontSize: "0.85rem", flexWrap: "wrap" }}>
          <div>
            <span style={{ color: "#6b7280" }}>Статус: </span>
            <span style={{ color: profile.wiki.exists ? "#22c55e" : "#ef4444", fontWeight: 600 }}>
              {profile.wiki.exists ? "Активна" : "Не создана"}
            </span>
          </div>
          <div>
            <span style={{ color: "#6b7280" }}>Страниц: </span>
            <span style={{ color: "#f59e0b", fontWeight: 600 }}>{profile.wiki.pages_count}</span>
          </div>
          <div>
            <span style={{ color: "#6b7280" }}>Проанализировано сессий: </span>
            <span style={{ color: "#6366f1", fontWeight: 600 }}>{profile.wiki.sessions_ingested}</span>
          </div>
          <div>
            <span style={{ color: "#6b7280" }}>Обнаружено паттернов: </span>
            <span style={{ color: "#ef4444", fontWeight: 600 }}>{profile.wiki.patterns_discovered}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ─── Pages Tab (with editing) ─── */

function PagesTab({
  pages,
  selectedPage,
  pageLoading,
  onLoadPage,
  onSavePage,
  actionLoading,
}: {
  pages: WikiPageItem[];
  selectedPage: WikiPageContent | null;
  pageLoading: boolean;
  onLoadPage: (path: string) => void;
  onSavePage: (path: string, content: string) => void;
  actionLoading: string | null;
}) {
  const [editing, setEditing] = useState(false);
  const [editContent, setEditContent] = useState("");

  const startEdit = () => {
    if (selectedPage) {
      setEditContent(selectedPage.content);
      setEditing(true);
    }
  };

  const cancelEdit = () => {
    setEditing(false);
    setEditContent("");
  };

  const saveEdit = () => {
    if (selectedPage && editContent.trim()) {
      onSavePage(selectedPage.page_path, editContent);
      setEditing(false);
    }
  };

  // Reset edit state when page changes
  const currentPagePath = selectedPage?.page_path;
  useEffect(() => {
    setEditing(false);
    setEditContent("");
  }, [currentPagePath]);

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
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
            <h3 style={{ color: "#f59e0b", margin: 0 }}>{selectedPage.page_path}</h3>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <span style={{ fontSize: "0.75rem", color: "#6b7280" }}>v{selectedPage.version}</span>
              {!editing ? (
                <button
                  onClick={startEdit}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "0.3rem",
                    padding: "0.3rem 0.6rem",
                    background: "rgba(99,102,241,0.1)",
                    border: "1px solid rgba(99,102,241,0.25)",
                    borderRadius: 6,
                    color: "#818cf8",
                    cursor: "pointer",
                    fontSize: "0.8rem",
                  }}
                >
                  <Edit3 size={13} />
                  Редактировать
                </button>
              ) : (
                <>
                  <button
                    onClick={saveEdit}
                    disabled={actionLoading === "save-page"}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.3rem",
                      padding: "0.3rem 0.6rem",
                      background: "rgba(34,197,94,0.1)",
                      border: "1px solid rgba(34,197,94,0.25)",
                      borderRadius: 6,
                      color: "#22c55e",
                      cursor: actionLoading === "save-page" ? "not-allowed" : "pointer",
                      fontSize: "0.8rem",
                    }}
                  >
                    {actionLoading === "save-page" ? (
                      <Loader2 size={13} style={{ animation: "spin 1s linear infinite" }} />
                    ) : (
                      <Save size={13} />
                    )}
                    Сохранить
                  </button>
                  <button
                    onClick={cancelEdit}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.3rem",
                      padding: "0.3rem 0.6rem",
                      background: "rgba(239,68,68,0.1)",
                      border: "1px solid rgba(239,68,68,0.25)",
                      borderRadius: 6,
                      color: "#ef4444",
                      cursor: "pointer",
                      fontSize: "0.8rem",
                    }}
                  >
                    <X size={13} />
                    Отмена
                  </button>
                </>
              )}
            </div>
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

          {editing ? (
            <textarea
              value={editContent}
              onChange={(e) => setEditContent(e.target.value)}
              style={{
                width: "100%",
                minHeight: 300,
                padding: "1rem",
                background: "rgba(0,0,0,0.3)",
                border: "1px solid rgba(99,102,241,0.3)",
                borderRadius: 8,
                color: "#e0e0e0",
                fontSize: "0.9rem",
                fontFamily: "monospace",
                lineHeight: 1.6,
                resize: "vertical",
                outline: "none",
              }}
            />
          ) : (
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
          )}
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

/* ─── Charts Section ─── */

const CHART_COMMON_OPTIONS = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { display: false },
    tooltip: {
      backgroundColor: "rgba(17,24,39,0.95)",
      titleColor: "#f3f4f6",
      bodyColor: "#d1d5db",
      borderColor: "rgba(255,255,255,0.1)",
      borderWidth: 1,
      cornerRadius: 8,
      padding: 10,
    },
  },
  scales: {
    x: {
      grid: { color: "rgba(255,255,255,0.04)" },
      ticks: { color: "#6b7280", font: { size: 10 } },
    },
    y: {
      grid: { color: "rgba(255,255,255,0.04)" },
      ticks: { color: "#6b7280", font: { size: 10 } },
      beginAtZero: true,
    },
  },
};

const CATEGORY_COLORS: Record<string, string> = {
  weakness: "#ef4444",
  strength: "#22c55e",
  quirk: "#f59e0b",
  misconception: "#8b5cf6",
  unknown: "#6b7280",
};

const CATEGORY_LABELS_RU: Record<string, string> = {
  weakness: "Слабости",
  strength: "Сильные стороны",
  quirk: "Особенности",
  misconception: "Заблуждения",
  unknown: "Другое",
};

function WikiChartsSection({ data }: { data: WikiChartData | null }) {
  if (!data) {
    return (
      <div style={{ textAlign: "center", padding: "2rem", color: "#6b7280" }}>
        <Loader2 size={24} style={{ animation: "spin 1s linear infinite", color: "#f59e0b", margin: "0 auto" }} />
        <p style={{ marginTop: "0.5rem", fontSize: "0.85rem" }}>Загрузка графиков...</p>
      </div>
    );
  }

  const dailySessions = data.daily_sessions;
  const patternDist = data.pattern_distribution;
  const wikiActivity = data.wiki_activity;

  // Sessions activity bar chart
  const sessionsBarData = {
    labels: dailySessions.map((d) => {
      const dt = new Date(d.date);
      return `${dt.getDate()}.${dt.getMonth() + 1}`;
    }),
    datasets: [
      {
        label: "Сессии",
        data: dailySessions.map((d) => d.sessions),
        backgroundColor: "rgba(99, 102, 241, 0.5)",
        borderColor: "rgba(99, 102, 241, 0.8)",
        borderWidth: 1,
        borderRadius: 4,
      },
    ],
  };

  // Score trend line chart
  const scoreTrendData = {
    labels: dailySessions.map((d) => {
      const dt = new Date(d.date);
      return `${dt.getDate()}.${dt.getMonth() + 1}`;
    }),
    datasets: [
      {
        label: "Средний балл",
        data: dailySessions.map((d) => d.avg_score),
        borderColor: "#f59e0b",
        backgroundColor: "rgba(245, 158, 11, 0.1)",
        borderWidth: 2,
        fill: true,
        tension: 0.4,
        pointRadius: 3,
        pointBackgroundColor: "#f59e0b",
      },
    ],
  };

  // Pattern distribution doughnut
  const patternDoughnutData = {
    labels: patternDist.map((p) => CATEGORY_LABELS_RU[p.category] || p.category),
    datasets: [
      {
        data: patternDist.map((p) => p.count),
        backgroundColor: patternDist.map((p) => CATEGORY_COLORS[p.category] || "#6b7280"),
        borderColor: "rgba(0,0,0,0.3)",
        borderWidth: 2,
      },
    ],
  };

  // Wiki activity (ingests + pages)
  const wikiActivityData = {
    labels: wikiActivity.map((d) => {
      const dt = new Date(d.date);
      return `${dt.getDate()}.${dt.getMonth() + 1}`;
    }),
    datasets: [
      {
        label: "Инжесты",
        data: wikiActivity.map((d) => d.ingests),
        backgroundColor: "rgba(34, 197, 94, 0.5)",
        borderColor: "rgba(34, 197, 94, 0.8)",
        borderWidth: 1,
        borderRadius: 4,
      },
      {
        label: "Страниц создано",
        data: wikiActivity.map((d) => d.pages_created),
        backgroundColor: "rgba(245, 158, 11, 0.5)",
        borderColor: "rgba(245, 158, 11, 0.8)",
        borderWidth: 1,
        borderRadius: 4,
      },
    ],
  };

  const lineOptions = {
    ...CHART_COMMON_OPTIONS,
    plugins: {
      ...CHART_COMMON_OPTIONS.plugins,
      legend: { display: false },
    },
  };

  const barOptions = {
    ...CHART_COMMON_OPTIONS,
    plugins: {
      ...CHART_COMMON_OPTIONS.plugins,
      legend: { display: true, position: "top" as const, labels: { color: "#9ca3af", boxWidth: 12, font: { size: 11 } } },
    },
  };

  const doughnutOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: "right" as const,
        labels: { color: "#d1d5db", boxWidth: 12, font: { size: 11 }, padding: 8 },
      },
      tooltip: CHART_COMMON_OPTIONS.plugins.tooltip,
    },
  };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
      {/* Sessions per day */}
      <div style={{
        padding: "1rem",
        background: "rgba(255,255,255,0.03)",
        border: "1px solid rgba(255,255,255,0.06)",
        borderRadius: 12,
      }}>
        <h4 style={{ margin: "0 0 0.75rem", color: "#e0e0e0", fontSize: "0.9rem", fontWeight: 600 }}>
          <Activity size={15} style={{ marginRight: 6, verticalAlign: "text-bottom", color: "#6366f1" }} />
          Сессии по дням
        </h4>
        <div style={{ height: 200 }}>
          {dailySessions.length > 0 ? (
            <Bar data={sessionsBarData} options={CHART_COMMON_OPTIONS as any} />
          ) : (
            <p style={{ color: "#6b7280", fontSize: "0.8rem", textAlign: "center", paddingTop: "4rem" }}>Нет данных</p>
          )}
        </div>
      </div>

      {/* Score trend */}
      <div style={{
        padding: "1rem",
        background: "rgba(255,255,255,0.03)",
        border: "1px solid rgba(255,255,255,0.06)",
        borderRadius: 12,
      }}>
        <h4 style={{ margin: "0 0 0.75rem", color: "#e0e0e0", fontSize: "0.9rem", fontWeight: 600 }}>
          <TrendingUp size={15} style={{ marginRight: 6, verticalAlign: "text-bottom", color: "#f59e0b" }} />
          Тренд среднего балла
        </h4>
        <div style={{ height: 200 }}>
          {dailySessions.length > 0 ? (
            <Line data={scoreTrendData} options={lineOptions as any} />
          ) : (
            <p style={{ color: "#6b7280", fontSize: "0.8rem", textAlign: "center", paddingTop: "4rem" }}>Нет данных</p>
          )}
        </div>
      </div>

      {/* Pattern distribution */}
      <div style={{
        padding: "1rem",
        background: "rgba(255,255,255,0.03)",
        border: "1px solid rgba(255,255,255,0.06)",
        borderRadius: 12,
      }}>
        <h4 style={{ margin: "0 0 0.75rem", color: "#e0e0e0", fontSize: "0.9rem", fontWeight: 600 }}>
          <PieChart size={15} style={{ marginRight: 6, verticalAlign: "text-bottom", color: "#ef4444" }} />
          Распределение паттернов
        </h4>
        <div style={{ height: 200 }}>
          {patternDist.length > 0 ? (
            <Doughnut data={patternDoughnutData} options={doughnutOptions as any} />
          ) : (
            <p style={{ color: "#6b7280", fontSize: "0.8rem", textAlign: "center", paddingTop: "4rem" }}>Паттерны не обнаружены</p>
          )}
        </div>
      </div>

      {/* Wiki activity */}
      <div style={{
        padding: "1rem",
        background: "rgba(255,255,255,0.03)",
        border: "1px solid rgba(255,255,255,0.06)",
        borderRadius: 12,
      }}>
        <h4 style={{ margin: "0 0 0.75rem", color: "#e0e0e0", fontSize: "0.9rem", fontWeight: 600 }}>
          <BookOpen size={15} style={{ marginRight: 6, verticalAlign: "text-bottom", color: "#22c55e" }} />
          Активность Wiki
        </h4>
        <div style={{ height: 200 }}>
          {wikiActivity.length > 0 ? (
            <Bar data={wikiActivityData} options={barOptions as any} />
          ) : (
            <p style={{ color: "#6b7280", fontSize: "0.8rem", textAlign: "center", paddingTop: "4rem" }}>Нет данных</p>
          )}
        </div>
      </div>

      {/* Top managers table */}
      {data.top_managers.length > 0 && (
        <div style={{
          gridColumn: "1 / -1",
          padding: "1rem",
          background: "rgba(255,255,255,0.03)",
          border: "1px solid rgba(255,255,255,0.06)",
          borderRadius: 12,
        }}>
          <h4 style={{ margin: "0 0 0.75rem", color: "#e0e0e0", fontSize: "0.9rem", fontWeight: 600 }}>
            <Users size={15} style={{ marginRight: 6, verticalAlign: "text-bottom", color: "#6366f1" }} />
            Топ менеджеров по паттернам
          </h4>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid rgba(255,255,255,0.08)" }}>
                  <th style={{ textAlign: "left", padding: "0.5rem", color: "#9ca3af", fontWeight: 500 }}>Менеджер</th>
                  <th style={{ textAlign: "center", padding: "0.5rem", color: "#9ca3af", fontWeight: 500 }}>Сессии</th>
                  <th style={{ textAlign: "center", padding: "0.5rem", color: "#9ca3af", fontWeight: 500 }}>Паттерны</th>
                  <th style={{ textAlign: "center", padding: "0.5rem", color: "#9ca3af", fontWeight: 500 }}>Страницы</th>
                </tr>
              </thead>
              <tbody>
                {data.top_managers.map((m, i) => (
                  <tr key={m.manager_id} style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                    <td style={{ padding: "0.5rem", color: "#e0e0e0" }}>
                      <span style={{ color: "#6b7280", marginRight: 8 }}>#{i + 1}</span>
                      {m.name}
                    </td>
                    <td style={{ textAlign: "center", padding: "0.5rem", color: "#f59e0b" }}>{m.sessions}</td>
                    <td style={{ textAlign: "center", padding: "0.5rem", color: "#ef4444" }}>{m.patterns}</td>
                    <td style={{ textAlign: "center", padding: "0.5rem", color: "#22c55e" }}>{m.pages}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
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
