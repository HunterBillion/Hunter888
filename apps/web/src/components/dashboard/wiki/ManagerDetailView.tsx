"use client";

import { useState, useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  ChevronLeft,
  Download,
  Loader2,
  PauseCircle,
  Play,
  PlayCircle,
  RotateCcw,
} from "lucide-react";
import {
  Pulse,
  Archive,
  ChartBar,
  BookOpen,
  Brain,
  Calendar,
  Clock,
  FileText,
  Lightbulb,
} from "@phosphor-icons/react";
import { api } from "@/lib/api";
import type {
  DetailTab,
  EnrichedProfile,
  ManagerWikiSummary,
  PatternItem,
  TechniqueItem,
  WikiChartData,
  WikiLogEntry,
  WikiPageContent,
  WikiPageItem,
} from "./types";
import { timeAgo } from "./utils";
import { ActionButton } from "./ActionButton";
import { EnrichedProfileTab } from "./EnrichedProfileTab";
import { PagesTab } from "./PagesTab";
import { PatternsTab } from "./PatternsTab";
import { TechniquesTab } from "./TechniquesTab";
import { WikiChartsSection } from "./WikiChartsSection";
import { LogTab } from "./LogTab";

const DETAIL_TABS: { id: DetailTab; label: string; icon: typeof BookOpen }[] = [
  { id: "profile", label: "Профиль", icon: Pulse },
  { id: "pages", label: "Страницы", icon: FileText },
  { id: "patterns", label: "Паттерны", icon: Brain },
  { id: "techniques", label: "Техники", icon: Lightbulb },
  { id: "charts", label: "Графики", icon: ChartBar },
  { id: "log", label: "Лог изменений", icon: Clock },
];

export function ManagerDetailView({
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
        <Loader2 size={32} style={{ animation: "spin 1s linear infinite", color: "var(--warning)" }} />
        <p style={{ color: "var(--text-muted)", marginTop: "1rem" }}>Загрузка wiki...</p>
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
            color: "var(--text-muted)",
            cursor: "pointer",
            fontSize: "0.85rem",
          }}
        >
          <ChevronLeft size={16} />
          Назад
        </button>
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <h1 style={{ fontSize: "1.4rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>
              {manager.manager_name}
            </h1>
            {manager.status && manager.status !== "active" && (
              <span style={{
                fontSize: "0.7rem",
                padding: "2px 8px",
                borderRadius: 8,
                background: manager.status === "paused" ? "rgba(245,158,11,0.12)" : "rgba(107,114,128,0.15)",
                color: manager.status === "paused" ? "var(--warning)" : "var(--text-muted)",
                fontWeight: 600,
              }}>
                {manager.status === "paused" ? <><PauseCircle size={12} style={{ display: "inline", verticalAlign: "middle", marginRight: 3 }} /> На паузе</> : <><Archive size={12} weight="duotone" style={{ display: "inline", verticalAlign: "middle", marginRight: 3 }} /> Архив</>}
              </span>
            )}
          </div>
          <p style={{ color: "var(--text-muted)", margin: 0, fontSize: "0.8rem" }}>
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
        <ActionButton icon={Play} label="Инжест всех сессий" onClick={onIngestAll} loading={actionLoading === "ingest-all"} color="var(--success)" />
        <ActionButton icon={Calendar} label="Дневной синтез" onClick={onDailySynthesis} loading={actionLoading === "daily"} color="var(--accent)" />
        <ActionButton icon={Calendar} label="Недельный синтез" onClick={onWeeklySynthesis} loading={actionLoading === "weekly"} color="var(--accent)" />
        <ActionButton icon={Download} label="PDF" onClick={() => onExport("pdf")} loading={actionLoading === "export-pdf"} color="var(--warning)" />
        <ActionButton icon={Download} label="CSV" onClick={() => onExport("csv")} loading={actionLoading === "export-csv"} color="var(--warning)" />
        <div style={{ flex: 1 }} />
        {/* Status management */}
        {manager.status === "active" ? (
          <ActionButton icon={PauseCircle} label="Пауза" onClick={() => onChangeStatus("paused")} loading={actionLoading === "status-paused"} color="var(--warning)" />
        ) : manager.status === "paused" ? (
          <ActionButton icon={PlayCircle} label="Возобновить" onClick={() => onChangeStatus("active")} loading={actionLoading === "status-active"} color="var(--success)" />
        ) : null}
        <ActionButton icon={Archive} label="Архив" onClick={() => onChangeStatus("archived")} loading={actionLoading === "status-archived"} color="var(--text-muted)" disabled={manager.status === "archived"} />
        <ActionButton icon={RotateCcw} label="Пересоздать" onClick={onReanalyze} loading={actionLoading === "reanalyze"} color="var(--danger)" />
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
              color: tab === t.id ? "var(--warning)" : "var(--text-muted)",
              cursor: "pointer",
              fontSize: "0.9rem",
              fontWeight: tab === t.id ? 600 : 400,
              transition: "all 0.2s",
            }}
          >
            <t.icon size={16} weight="duotone" />
            {t.label}
            {t.id === "patterns" && patterns.length > 0 && (
              <span style={{
                marginLeft: 4,
                fontSize: "0.7rem",
                padding: "1px 6px",
                borderRadius: 8,
                background: "rgba(239,68,68,0.15)",
                color: "var(--danger)",
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
