"use client";

import { useEffect, useState } from "react";
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
} from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api";
import AuthLayout from "@/components/layout/AuthLayout";

type Tab = "overview" | "patterns" | "insights" | "recommendations";

interface WikiOverview {
  exists: boolean;
  sessions_ingested: number;
  patterns_discovered: number;
  pages_count: number;
  last_ingest_at: string | null;
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
}

interface PatternItem {
  id: string;
  pattern_code: string;
  category: string;
  description: string;
  sessions_in_pattern: number;
  is_confirmed: boolean;
  mitigation_technique: string | null;
}

interface TechniqueItem {
  id: string;
  technique_code: string;
  technique_name: string;
  description: string;
  success_rate: number;
  success_count: number;
  attempt_count: number;
}

const TABS: { id: Tab; label: string; icon: React.ComponentType<{ size: number }> }[] = [
  { id: "overview", label: "Обзор", icon: BookOpen },
  { id: "patterns", label: "Паттерны", icon: Brain },
  { id: "insights", label: "Инсайты", icon: Lightbulb },
  { id: "recommendations", label: "Рекомендации", icon: Target },
];

const CATEGORY_CONFIG: Record<string, { label: string; color: string; icon: React.ComponentType<{ size?: number; style?: React.CSSProperties }> }> = {
  weakness: { label: "Слабость", color: "#ef4444", icon: AlertTriangle },
  strength: { label: "Сила", color: "#22c55e", icon: TrendingUp },
  quirk: { label: "Особенность", color: "#f59e0b", icon: Zap },
  misconception: { label: "Заблуждение", color: "#8b5cf6", icon: AlertTriangle },
};

function renderMarkdown(content: string): string {
  // Simple markdown-to-HTML for wiki content
  return content
    .replace(/^### (.+)$/gm, '<h3 style="font-size:1.1rem;font-weight:600;margin:1rem 0 0.5rem;color:#e0e0e0">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 style="font-size:1.3rem;font-weight:700;margin:1.5rem 0 0.75rem;color:#fff">$1</h2>')
    .replace(/^- (.+)$/gm, '<li style="margin:0.25rem 0;padding-left:0.5rem">$1</li>')
    .replace(/\n/g, "<br/>");
}

export default function WikiPage() {
  const [tab, setTab] = useState<Tab>("overview");
  const [loading, setLoading] = useState(true);
  const [overview, setOverview] = useState<WikiOverview | null>(null);
  const [pages, setPages] = useState<WikiPageItem[]>([]);
  const [patterns, setPatterns] = useState<PatternItem[]>([]);
  const [techniques, setTechniques] = useState<TechniqueItem[]>([]);
  const [selectedPage, setSelectedPage] = useState<WikiPageContent | null>(null);
  const [pageLoading, setPageLoading] = useState(false);

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    try {
      const [overviewRes, pagesRes, patternsRes, techniquesRes] = await Promise.all([
        api.get("/wiki/me"),
        api.get("/wiki/me/pages"),
        api.get("/wiki/me/patterns"),
        api.get("/wiki/me/techniques"),
      ]);
      setOverview(overviewRes);
      setPages(pagesRes.pages || []);
      setPatterns(patternsRes.patterns || []);
      setTechniques(techniquesRes.techniques || []);
    } catch {
      // Wiki may not exist yet
      setOverview({ exists: false, sessions_ingested: 0, patterns_discovered: 0, pages_count: 0, last_ingest_at: null });
    } finally {
      setLoading(false);
    }
  }

  async function loadPage(pagePath: string) {
    setPageLoading(true);
    try {
      const res = await api.get(`/wiki/me/pages/${pagePath}`);
      setSelectedPage(res);
    } catch {
      setSelectedPage(null);
    } finally {
      setPageLoading(false);
    }
  }

  const pagesByType = (type: string) => pages.filter((p) => p.page_type === type);

  return (
    <AuthLayout>
      <div style={{ maxWidth: 1000, margin: "0 auto", padding: "2rem 1rem" }}>
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", gap: "1rem", marginBottom: "2rem" }}>
          <BookOpen size={32} style={{ color: "#f59e0b" }} />
          <div>
            <h1 style={{ fontSize: "1.8rem", fontWeight: 700, color: "#fff", margin: 0 }}>
              Моя база знаний
            </h1>
            <p style={{ color: "#9ca3af", margin: 0 }}>
              Персональная wiki на основе тренировок
            </p>
          </div>
          <Link
            href="/training"
            style={{
              marginLeft: "auto",
              padding: "0.5rem 1rem",
              background: "rgba(245,158,11,0.15)",
              border: "1px solid rgba(245,158,11,0.3)",
              borderRadius: 8,
              color: "#f59e0b",
              textDecoration: "none",
              fontSize: "0.9rem",
            }}
          >
            К тренировкам
          </Link>
        </div>

        {loading ? (
          <div style={{ textAlign: "center", padding: "4rem" }}>
            <Loader2 size={32} style={{ animation: "spin 1s linear infinite", color: "#f59e0b" }} />
            <p style={{ color: "#9ca3af", marginTop: "1rem" }}>Загрузка wiki...</p>
          </div>
        ) : !overview?.exists ? (
          <div
            style={{
              textAlign: "center",
              padding: "4rem 2rem",
              background: "rgba(255,255,255,0.03)",
              borderRadius: 12,
              border: "1px solid rgba(255,255,255,0.06)",
            }}
          >
            <Brain size={48} style={{ color: "#6b7280", marginBottom: "1rem" }} />
            <h2 style={{ color: "#e0e0e0", fontSize: "1.3rem" }}>Wiki ещё не создана</h2>
            <p style={{ color: "#9ca3af", maxWidth: 500, margin: "0.5rem auto" }}>
              Пройдите хотя бы одну тренировочную сессию. После завершения сессии
              система автоматически проанализирует транскрипт и создаст вашу персональную базу знаний.
            </p>
            <Link
              href="/training"
              style={{
                display: "inline-block",
                marginTop: "1.5rem",
                padding: "0.75rem 1.5rem",
                background: "#f59e0b",
                color: "#000",
                borderRadius: 8,
                textDecoration: "none",
                fontWeight: 600,
              }}
            >
              Начать тренировку
            </Link>
          </div>
        ) : (
          <>
            {/* Stats bar */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
                gap: "1rem",
                marginBottom: "2rem",
              }}
            >
              {[
                { label: "Сессий", value: overview.sessions_ingested, icon: FileText },
                { label: "Паттернов", value: overview.patterns_discovered, icon: Brain },
                { label: "Страниц", value: overview.pages_count, icon: BookOpen },
                {
                  label: "Обновлено",
                  value: overview.last_ingest_at
                    ? new Date(overview.last_ingest_at).toLocaleDateString("ru-RU")
                    : "—",
                  icon: Clock,
                },
              ].map((stat) => (
                <div
                  key={stat.label}
                  style={{
                    background: "rgba(255,255,255,0.03)",
                    border: "1px solid rgba(255,255,255,0.06)",
                    borderRadius: 10,
                    padding: "1rem",
                    textAlign: "center",
                  }}
                >
                  <stat.icon size={20} style={{ color: "#f59e0b", marginBottom: "0.5rem" }} />
                  <div style={{ fontSize: "1.5rem", fontWeight: 700, color: "#fff" }}>{stat.value}</div>
                  <div style={{ fontSize: "0.8rem", color: "#9ca3af" }}>{stat.label}</div>
                </div>
              ))}
            </div>

            {/* Tabs */}
            <div
              style={{
                display: "flex",
                gap: "0.5rem",
                marginBottom: "1.5rem",
                borderBottom: "1px solid rgba(255,255,255,0.08)",
                paddingBottom: "0.5rem",
              }}
            >
              {TABS.map((t) => (
                <button
                  key={t.id}
                  onClick={() => {
                    setTab(t.id);
                    setSelectedPage(null);
                  }}
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
                {tab === "overview" && (
                  <div>
                    <h2 style={{ color: "#e0e0e0", fontSize: "1.2rem", marginBottom: "1rem" }}>
                      Страницы wiki
                    </h2>
                    {pages.length === 0 ? (
                      <p style={{ color: "#6b7280" }}>Страницы появятся после первой тренировки.</p>
                    ) : (
                      <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                        {pages.map((p) => (
                          <button
                            key={p.id}
                            onClick={() => loadPage(p.page_path)}
                            style={{
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "space-between",
                              padding: "0.75rem 1rem",
                              background: "rgba(255,255,255,0.03)",
                              border: "1px solid rgba(255,255,255,0.06)",
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
                                  {p.updated_at && ` | ${new Date(p.updated_at).toLocaleDateString("ru-RU")}`}
                                </div>
                              </div>
                            </div>
                            <ChevronRight size={16} style={{ color: "#6b7280" }} />
                          </button>
                        ))}
                      </div>
                    )}
                    {/* Page content viewer */}
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
                        <div
                          style={{ color: "#d1d5db", lineHeight: 1.7 }}
                          dangerouslySetInnerHTML={{ __html: renderMarkdown(selectedPage.content) }}
                        />
                      </motion.div>
                    )}
                  </div>
                )}

                {tab === "patterns" && (
                  <div>
                    <h2 style={{ color: "#e0e0e0", fontSize: "1.2rem", marginBottom: "1rem" }}>
                      Обнаруженные паттерны
                    </h2>
                    {patterns.length === 0 ? (
                      <p style={{ color: "#6b7280" }}>Паттерны будут обнаружены после нескольких тренировок.</p>
                    ) : (
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
                              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
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
                              </div>
                              <p style={{ color: "#9ca3af", margin: "0.25rem 0", fontSize: "0.9rem" }}>
                                {p.description}
                              </p>
                              <div style={{ fontSize: "0.75rem", color: "#6b7280" }}>
                                Замечен в {p.sessions_in_pattern} сессиях
                                {p.mitigation_technique && ` | Техника: ${p.mitigation_technique}`}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                )}

                {tab === "insights" && (
                  <div>
                    <h2 style={{ color: "#e0e0e0", fontSize: "1.2rem", marginBottom: "1rem" }}>
                      Техники и инсайты
                    </h2>
                    {techniques.length === 0 ? (
                      <p style={{ color: "#6b7280" }}>Техники будут обнаружены по мере тренировок.</p>
                    ) : (
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
                              <span
                                style={{
                                  marginLeft: "auto",
                                  fontSize: "0.8rem",
                                  color: t.success_rate >= 0.7 ? "#22c55e" : "#f59e0b",
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
                            <div style={{ fontSize: "0.75rem", color: "#6b7280" }}>
                              Использовано {t.attempt_count} раз | Успешно {t.success_count}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Show insight-type pages */}
                    {pagesByType("insight").length > 0 && (
                      <div style={{ marginTop: "2rem" }}>
                        <h3 style={{ color: "#e0e0e0", fontSize: "1rem", marginBottom: "0.75rem" }}>
                          Страницы инсайтов
                        </h3>
                        {pagesByType("insight").map((p) => (
                          <button
                            key={p.id}
                            onClick={() => {
                              loadPage(p.page_path);
                              setTab("overview");
                            }}
                            style={{
                              display: "block",
                              padding: "0.5rem 1rem",
                              background: "rgba(255,255,255,0.02)",
                              border: "1px solid rgba(255,255,255,0.06)",
                              borderRadius: 8,
                              color: "#d1d5db",
                              cursor: "pointer",
                              width: "100%",
                              textAlign: "left",
                              marginBottom: "0.5rem",
                            }}
                          >
                            {p.page_path}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {tab === "recommendations" && (
                  <div>
                    <h2 style={{ color: "#e0e0e0", fontSize: "1.2rem", marginBottom: "1rem" }}>
                      Рекомендации
                    </h2>
                    {pagesByType("recommendation").length === 0 ? (
                      <p style={{ color: "#6b7280" }}>Рекомендации появятся после анализа тренировок.</p>
                    ) : (
                      <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                        {pagesByType("recommendation").map((p) => (
                          <button
                            key={p.id}
                            onClick={() => {
                              loadPage(p.page_path);
                              setTab("overview");
                            }}
                            style={{
                              display: "flex",
                              alignItems: "center",
                              gap: "0.75rem",
                              padding: "1rem",
                              background: "rgba(245,158,11,0.05)",
                              border: "1px solid rgba(245,158,11,0.15)",
                              borderRadius: 10,
                              color: "#e0e0e0",
                              cursor: "pointer",
                              width: "100%",
                              textAlign: "left",
                            }}
                          >
                            <Target size={20} style={{ color: "#f59e0b" }} />
                            <div>
                              <div style={{ fontWeight: 500 }}>{p.page_path}</div>
                              <div style={{ fontSize: "0.75rem", color: "#6b7280" }}>
                                {p.updated_at && `Обновлено: ${new Date(p.updated_at).toLocaleDateString("ru-RU")}`}
                              </div>
                            </div>
                            <ChevronRight size={16} style={{ color: "#6b7280", marginLeft: "auto" }} />
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </motion.div>
            </AnimatePresence>
          </>
        )}
      </div>
    </AuthLayout>
  );
}
