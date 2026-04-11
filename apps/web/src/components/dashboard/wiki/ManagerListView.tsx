"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  CheckCircle,
  ChevronRight,
  Info,
  Loader2,
  PauseCircle,
  RefreshCw,
  Search,
  Settings,
} from "lucide-react";
import {
  Pulse,
  Archive,
  ChartBar,
  Brain,
  Calendar,
  FileText,
  ShieldCheck,
  UsersThree,
  Lightning,
} from "@phosphor-icons/react";
import type {
  CompareManager,
  GlobalStats,
  ManagerWikiSummary,
  SchedulerStatus,
  WikiChartData,
} from "./types";
import { timeAgo } from "./utils";
import { ActionButton } from "./ActionButton";
import { WikiChartsSection } from "./WikiChartsSection";
import { CompareResultsPanel } from "./CompareResultsPanel";

export function ManagerListView({
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
        <ShieldCheck size={28} weight="duotone" style={{ color: "var(--warning)" }} />
        <div style={{ flex: 1 }}>
          <h1 style={{ fontSize: "1.6rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>
            Wiki менеджеров
          </h1>
          <p style={{ color: "var(--text-muted)", margin: 0, fontSize: "0.85rem" }}>
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
            color: showHelp ? "var(--warning)" : "var(--text-muted)",
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
            background: compareMode ? "rgba(124,106,232,0.15)" : "rgba(255,255,255,0.04)",
            border: `1px solid ${compareMode ? "rgba(124,106,232,0.3)" : "rgba(255,255,255,0.08)"}`,
            borderRadius: 8,
            color: compareMode ? "var(--accent)" : "var(--text-muted)",
            cursor: "pointer",
            fontSize: "0.8rem",
            display: "flex",
            alignItems: "center",
            gap: "0.3rem",
          }}
          title="Сравнить менеджеров"
        >
          <UsersThree size={16} weight="duotone" />
          Сравнить
        </button>
        <button
          onClick={onRefresh}
          style={{
            padding: "0.5rem",
            background: "rgba(255,255,255,0.04)",
            border: "1px solid rgba(255,255,255,0.08)",
            borderRadius: 8,
            color: "var(--text-muted)",
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
          background: "rgba(124,106,232,0.08)",
          border: "1px solid rgba(124,106,232,0.2)",
          borderRadius: 10,
          flexWrap: "wrap",
        }}>
          <UsersThree size={18} weight="duotone" style={{ color: "var(--accent)" }} />
          <span style={{ color: "var(--accent-hover)", fontSize: "0.85rem" }}>
            Выберите 2–5 менеджеров для сравнения ({compareSelected.length} выбрано)
          </span>
          <div style={{ flex: 1 }} />
          <button
            onClick={onCompare}
            disabled={compareSelected.length < 2 || compareLoading}
            style={{
              padding: "0.4rem 1rem",
              background: compareSelected.length >= 2 ? "rgba(124,106,232,0.2)" : "rgba(255,255,255,0.04)",
              border: "1px solid rgba(124,106,232,0.3)",
              borderRadius: 8,
              color: compareSelected.length >= 2 ? "var(--accent-hover)" : "var(--text-muted)",
              cursor: compareSelected.length >= 2 ? "pointer" : "not-allowed",
              fontSize: "0.85rem",
              fontWeight: 600,
              display: "flex",
              alignItems: "center",
              gap: "0.3rem",
            }}
          >
            {compareLoading ? <Loader2 size={14} style={{ animation: "spin 1s linear infinite" }} /> : <ChartBar size={14} weight="duotone" />}
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
            <h3 style={{ color: "var(--warning)", fontSize: "1rem", fontWeight: 600, margin: "0 0 0.75rem" }}>
              Как работает Wiki менеджеров
            </h3>
            <div style={{ color: "var(--text-muted)", fontSize: "0.85rem", lineHeight: 1.7 }}>
              <p style={{ margin: "0 0 0.5rem" }}>
                <strong style={{ color: "var(--text-primary)" }}>Wiki</strong> — это персональная база знаний каждого менеджера,
                которая автоматически строится из тренировочных сессий.
              </p>
              <p style={{ margin: "0 0 0.5rem" }}>
                <strong style={{ color: "var(--text-primary)" }}>Автоматика:</strong> Каждые 12 часов система автоматически анализирует новые сессии.
                Ежедневно в 03:00 UTC формируется дневной синтез, еженедельно по понедельникам — недельный.
              </p>
              <ul style={{ margin: "0 0 0.5rem", paddingLeft: "1.5rem" }}>
                <li><strong style={{ color: "var(--danger)" }}>Слабости</strong> — паттерны ошибок</li>
                <li><strong style={{ color: "var(--success)" }}>Техники</strong> — успешные приёмы с % успеха</li>
                <li><strong style={{ color: "var(--warning)" }}>Страницы</strong> — обзоры, инсайты, рекомендации</li>
                <li><strong style={{ color: "var(--accent)" }}>Синтез</strong> — дневные и недельные AI-резюме</li>
              </ul>
              <p style={{ margin: "0 0 0.5rem" }}>
                <strong style={{ color: "var(--text-primary)" }}>Действия:</strong> Вы можете редактировать страницы, экспортировать данные в PDF/CSV,
                запускать синтез вручную и инжестить пропущенные сессии.
              </p>
              <p style={{ margin: 0, fontSize: "0.8rem", color: "var(--text-muted)" }}>
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
            { label: "Wiki создано", value: globalStats.total_wikis, icon: UsersThree, color: "var(--accent)" },
            { label: "Сессий", value: globalStats.total_sessions_ingested, icon: Pulse, color: "var(--warning)" },
            { label: "Паттернов", value: globalStats.total_patterns_discovered, icon: Brain, color: "var(--danger)" },
            { label: "Страниц", value: globalStats.total_pages, icon: FileText, color: "var(--success)" },
            { label: "Токенов LLM", value: globalStats.total_tokens_used.toLocaleString("ru-RU"), icon: Lightning, color: "var(--accent)" },
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
              <s.icon size={18} weight="duotone" style={{ color: s.color, marginBottom: "0.25rem" }} />
              <div style={{ fontSize: "1.3rem", fontWeight: 700, color: "var(--text-primary)" }}>{s.value}</div>
              <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{s.label}</div>
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
              color: schedulerStatus.running ? "var(--success)" : "var(--danger)",
            }}
          >
            <Settings size={14} />
            Планировщик: {schedulerStatus.running ? "работает" : "остановлен"}
            {schedulerStatus.last_ingest_run && (
              <span style={{ color: "var(--text-muted)", marginLeft: 4 }}>
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
          color="var(--accent)"
        />
        <ActionButton
          icon={Calendar}
          label="Недельный синтез"
          onClick={onWeeklySynthesis}
          loading={actionLoading === "weekly"}
          color="var(--accent)"
        />
        <ActionButton
          icon={ChartBar}
          label={showCharts ? "Скрыть графики" : "Графики"}
          onClick={() => setShowCharts(!showCharts)}
          loading={false}
          color={showCharts ? "var(--warning)" : "var(--text-muted)"}
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
          style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }}
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
            color: "var(--text-secondary)",
            fontSize: "0.9rem",
            outline: "none",
          }}
        />
      </div>

      {/* Manager list */}
      {wikis.length === 0 ? (
        <div style={{ textAlign: "center", padding: "3rem", color: "var(--text-muted)" }}>
          <Brain size={40} weight="duotone" style={{ margin: "0 auto 1rem", opacity: 0.4 }} />
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
                  ? "rgba(124,106,232,0.08)"
                  : "rgba(255,255,255,0.03)",
                border: compareMode && compareSelected.includes(w.manager_id)
                  ? "1px solid rgba(124,106,232,0.3)"
                  : "1px solid rgba(255,255,255,0.06)",
                borderRadius: 10,
                cursor: "pointer",
                color: "var(--text-secondary)",
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
                    ? "rgba(124,106,232,0.3)"
                    : "transparent",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}>
                  {compareSelected.includes(w.manager_id) && <CheckCircle size={14} style={{ color: "var(--accent)" }} />}
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
                      color: w.status === "paused" ? "var(--warning)" : "var(--text-muted)",
                      fontWeight: 600,
                    }}>
                      {w.status === "paused" ? <><PauseCircle size={10} style={{ display: "inline", verticalAlign: "middle", marginRight: 2 }} /> Пауза</> : <><Archive size={10} weight="duotone" style={{ display: "inline", verticalAlign: "middle", marginRight: 2 }} /> Архив</>}
                    </span>
                  )}
                </div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                  {w.manager_role === "admin" ? "Админ" : w.manager_role === "rop" ? "РОП" : "Менеджер"}
                </div>
              </div>
              <div style={{ textAlign: "center" }}>
                <div style={{ fontSize: "1.1rem", fontWeight: 700, color: "var(--warning)" }}>{w.sessions_ingested}</div>
                <div style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>сессий</div>
              </div>
              <div style={{ textAlign: "center" }}>
                <div style={{ fontSize: "1.1rem", fontWeight: 700, color: "var(--danger)" }}>{w.patterns_discovered}</div>
                <div style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>паттернов</div>
              </div>
              <div style={{ textAlign: "center" }}>
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{timeAgo(w.last_ingest_at)}</div>
              </div>
              <ChevronRight size={16} style={{ color: "var(--text-muted)" }} />
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
