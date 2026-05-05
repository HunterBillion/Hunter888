"use client";

import { useEffect, useState, useCallback } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import type {
  View,
  DetailTab,
  ManagerWikiSummary,
  GlobalStats,
  SchedulerStatus,
  WikiChartData,
  WikiPageItem,
  WikiPageContent,
  PatternItem,
  TechniqueItem,
  WikiLogEntry,
  EnrichedProfile,
  CompareManager,
} from "./types";
import { ManagerListView } from "./ManagerListView";
import { ManagerDetailView } from "./ManagerDetailView";

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
  const [pendingReanalyze, setPendingReanalyze] = useState<string | null>(null);

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

  // Bridges legacy `showMessage(text, type)` call sites onto sonner so
  // the project has a single toast system. Kept as a thin shim instead
  // of a full search-and-replace because the call-site shape (string +
  // "success"/"error") is identical to sonner's `toast.success/error`.
  const showMessage = (text: string, type: "success" | "error") => {
    if (type === "success") toast.success(text);
    else toast.error(text);
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
      const { getApiBaseUrl } = await import("@/lib/public-origin");
      const baseUrl = getApiBaseUrl();
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

  const requestReanalyze = useCallback((managerId: string) => {
    // Re-analysis runs an LLM pipeline over the manager's full session
    // history — it's billable and slow. Surface a confirmation so the
    // user doesn't trigger it by accident.
    setPendingReanalyze(managerId);
  }, []);

  const confirmReanalyze = useCallback(async () => {
    if (!pendingReanalyze) return;
    const managerId = pendingReanalyze;
    setActionLoading("reanalyze");
    try {
      const res = await api.post(`/wiki/manager/${managerId}/reanalyze`, {});
      showMessage(res.message || "Re-analysis started", "success");
      if (selectedManager) openManager(selectedManager);
      setPendingReanalyze(null);
    } catch (err: any) {
      showMessage(err.message || "Re-analysis failed", "error");
      // Keep the modal open on failure so the user can retry.
    } finally {
      setActionLoading(null);
    }
  }, [pendingReanalyze, selectedManager, openManager]);

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
        <Loader2 size={36} style={{ animation: "spin 1s linear infinite", color: "var(--warning)" }} />
        <p style={{ color: "var(--text-muted)", marginTop: "1rem" }}>Загрузка Wiki...</p>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto" }}>
        {/* Notifications go through sonner (mounted globally in root layout) — no local toast container needed. */}

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
            onReanalyze={() => requestReanalyze(selectedManager!.manager_id)}
            actionLoading={actionLoading}
          />
        )}

      <ConfirmDialog
        open={pendingReanalyze !== null}
        onOpenChange={(open) => { if (!open && actionLoading !== "reanalyze") setPendingReanalyze(null); }}
        title="Запустить переанализ?"
        description={
          <div className="space-y-2">
            <p>
              Переанализ прогоняет LLM по всей истории сессий менеджера и
              перезаписывает страницы wiki. Операция платная и небыстрая
              (1–3 минуты в зависимости от объёма истории).
            </p>
            <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
              Запускайте, если изменилась модель / промпт-шаблон или
              wiki заметно расходится с тем, что показывают сессии.
            </p>
          </div>
        }
        confirmLabel="Запустить"
        busy={actionLoading === "reanalyze"}
        onConfirm={confirmReanalyze}
      />
    </div>
  );
}
