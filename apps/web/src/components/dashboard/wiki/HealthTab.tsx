"use client";

import { useState } from "react";
import {
  Heartbeat,
  Warning,
  CheckCircle,
  ArrowRight,
  Lightning,
  Info,
  CaretDown,
  CaretUp,
} from "@phosphor-icons/react";
import { Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import type { LintReport } from "./types";
import { timeAgo } from "./utils";

const SEVERITY_STYLES: Record<string, { bg: string; border: string; icon: string; label: string }> = {
  high: { bg: "rgba(239,68,68,0.08)", border: "rgba(239,68,68,0.3)", icon: "var(--danger)", label: "Критично" },
  medium: { bg: "rgba(245,158,11,0.08)", border: "rgba(245,158,11,0.3)", icon: "var(--warning)", label: "Важно" },
  low: { bg: "rgba(99,102,241,0.06)", border: "rgba(99,102,241,0.2)", icon: "var(--accent)", label: "Мелочь" },
  info: { bg: "rgba(59,130,246,0.06)", border: "rgba(59,130,246,0.2)", icon: "var(--text-muted)", label: "Инфо" },
};

export function HealthTab({ managerId }: { managerId: string }) {
  const [report, setReport] = useState<LintReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [runLoading, setRunLoading] = useState(false);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [loaded, setLoaded] = useState(false);

  const loadReport = async () => {
    setLoading(true);
    try {
      const data = await api.get<LintReport>(`/wiki/${managerId}/lint`);
      setReport(data);
    } catch {
      setReport(null);
    } finally {
      setLoading(false);
      setLoaded(true);
    }
  };

  const runLint = async () => {
    setRunLoading(true);
    try {
      const data = await api.post<LintReport>(`/wiki/${managerId}/lint`, {});
      setReport(data);
    } catch {
      // ignore
    } finally {
      setRunLoading(false);
      setLoaded(true);
    }
  };

  // Auto-load on first render
  if (!loaded && !loading) {
    loadReport();
  }

  const toggleExpand = (idx: number) => {
    const next = new Set(expanded);
    if (next.has(idx)) next.delete(idx);
    else next.add(idx);
    setExpanded(next);
  };

  const healthScore = report?.health_score ?? null;
  const scoreColor = healthScore !== null
    ? healthScore >= 80 ? "var(--success)" : healthScore >= 50 ? "var(--warning)" : "var(--danger)"
    : "var(--text-muted)";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <Heartbeat size={24} weight="fill" style={{ color: "var(--accent)" }} />
          <h3 style={{ margin: 0, fontSize: "1.1rem" }}>Здоровье Wiki</h3>
          {report?.last_run && (
            <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
              Последний запуск: {timeAgo(report.last_run)}
            </span>
          )}
        </div>
        <button
          onClick={runLint}
          disabled={runLoading}
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.5rem",
            padding: "0.5rem 1rem",
            background: "var(--accent)",
            border: "none",
            borderRadius: 8,
            color: "white",
            cursor: runLoading ? "wait" : "pointer",
            fontSize: "0.85rem",
            fontWeight: 600,
            opacity: runLoading ? 0.7 : 1,
          }}
        >
          {runLoading ? <Loader2 size={16} style={{ animation: "spin 1s linear infinite" }} /> : <Lightning size={16} weight="fill" />}
          {runLoading ? "Анализирую..." : "Запустить Lint"}
        </button>
      </div>

      {loading && (
        <div style={{ textAlign: "center", padding: "2rem" }}>
          <Loader2 size={24} style={{ animation: "spin 1s linear infinite", color: "var(--warning)" }} />
        </div>
      )}

      {!loading && report?.status === "no_lint_report" && (
        <div style={{
          padding: "2rem",
          textAlign: "center",
          background: "rgba(255,255,255,0.02)",
          borderRadius: 12,
          border: "1px dashed rgba(255,255,255,0.1)",
        }}>
          <Info size={40} style={{ color: "var(--text-muted)", marginBottom: "0.75rem" }} />
          <p style={{ color: "var(--text-muted)", margin: 0 }}>
            Lint ещё не запускался. Нажмите &quot;Запустить Lint&quot; для первой проверки.
          </p>
        </div>
      )}

      {!loading && report && report.status !== "no_lint_report" && (
        <>
          {/* Health Score Card */}
          <div style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr 1fr 1fr",
            gap: "1rem",
          }}>
            {/* Score */}
            <div style={{
              padding: "1.25rem",
              background: "rgba(255,255,255,0.03)",
              border: "1px solid rgba(255,255,255,0.08)",
              borderRadius: 12,
              textAlign: "center",
            }}>
              <div style={{ fontSize: "2rem", fontWeight: 700, color: scoreColor }}>
                {healthScore ?? "—"}%
              </div>
              <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
                Health Score
              </div>
            </div>

            {/* Issues */}
            <div style={{
              padding: "1.25rem",
              background: "rgba(239,68,68,0.04)",
              border: "1px solid rgba(239,68,68,0.15)",
              borderRadius: 12,
              textAlign: "center",
            }}>
              <div style={{ fontSize: "2rem", fontWeight: 700, color: "var(--danger)" }}>
                {report.summary?.total_issues ?? 0}
              </div>
              <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
                Проблем
              </div>
            </div>

            {/* Suggestions */}
            <div style={{
              padding: "1.25rem",
              background: "rgba(59,130,246,0.04)",
              border: "1px solid rgba(59,130,246,0.15)",
              borderRadius: 12,
              textAlign: "center",
            }}>
              <div style={{ fontSize: "2rem", fontWeight: 700, color: "var(--accent)" }}>
                {report.summary?.total_suggestions ?? 0}
              </div>
              <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
                Предложений
              </div>
            </div>

            {/* Cross-refs */}
            <div style={{
              padding: "1.25rem",
              background: "rgba(16,185,129,0.04)",
              border: "1px solid rgba(16,185,129,0.15)",
              borderRadius: 12,
              textAlign: "center",
            }}>
              <div style={{ fontSize: "2rem", fontWeight: 700, color: "var(--success)" }}>
                {report.summary?.cross_references ?? 0}
              </div>
              <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
                Перекрёстных ссылок
              </div>
            </div>
          </div>

          {/* Summary breakdown */}
          <div style={{
            display: "flex",
            gap: "0.75rem",
            flexWrap: "wrap",
          }}>
            {[
              { label: "Противоречия", count: report.summary?.contradictions ?? 0, color: "var(--danger)" },
              { label: "Устаревшие", count: report.summary?.stale_pages ?? 0, color: "var(--warning)" },
              { label: "Осиротевшие", count: report.summary?.orphan_pages ?? 0, color: "var(--accent)" },
              { label: "Низкая уверенность", count: report.summary?.low_confidence ?? 0, color: "var(--text-muted)" },
              { label: "Недостающие концепции", count: report.summary?.missing_concepts ?? 0, color: "var(--warning)" },
            ].map((item) => (
              <div key={item.label} style={{
                padding: "0.4rem 0.75rem",
                background: "rgba(255,255,255,0.03)",
                borderRadius: 6,
                fontSize: "0.8rem",
                display: "flex",
                alignItems: "center",
                gap: "0.4rem",
              }}>
                <span style={{
                  width: 8, height: 8, borderRadius: "50%",
                  background: item.count > 0 ? item.color : "rgba(255,255,255,0.1)",
                  display: "inline-block",
                }} />
                <span style={{ color: "var(--text-secondary)" }}>{item.label}:</span>
                <span style={{ fontWeight: 600, color: item.count > 0 ? item.color : "var(--text-muted)" }}>
                  {item.count}
                </span>
              </div>
            ))}
          </div>

          {/* Issues list */}
          {report.issues && report.issues.length > 0 && (
            <div>
              <h4 style={{ margin: "0 0 0.75rem 0", fontSize: "0.95rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <Warning size={18} weight="fill" style={{ color: "var(--danger)" }} />
                Проблемы ({report.issues.length})
              </h4>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                {report.issues.map((issue, idx) => {
                  const style = SEVERITY_STYLES[issue.severity] || SEVERITY_STYLES.low;
                  const isExpanded = expanded.has(idx);
                  return (
                    <div
                      key={idx}
                      style={{
                        background: style.bg,
                        border: `1px solid ${style.border}`,
                        borderRadius: 10,
                        overflow: "hidden",
                      }}
                    >
                      <button
                        onClick={() => toggleExpand(idx)}
                        style={{
                          width: "100%",
                          display: "flex",
                          alignItems: "center",
                          gap: "0.75rem",
                          padding: "0.75rem 1rem",
                          background: "none",
                          border: "none",
                          cursor: "pointer",
                          textAlign: "left",
                        }}
                      >
                        <span style={{
                          padding: "0.15rem 0.5rem",
                          borderRadius: 4,
                          fontSize: "0.7rem",
                          fontWeight: 700,
                          background: style.border,
                          color: "white",
                          textTransform: "uppercase",
                        }}>
                          {style.label}
                        </span>
                        <span style={{ flex: 1, fontSize: "0.85rem", color: "var(--text-primary)" }}>
                          {issue.title}
                        </span>
                        {isExpanded ? <CaretUp size={16} /> : <CaretDown size={16} />}
                      </button>
                      {isExpanded && (
                        <div style={{ padding: "0 1rem 0.75rem 1rem", fontSize: "0.82rem" }}>
                          <p style={{ color: "var(--text-secondary)", margin: "0 0 0.5rem 0" }}>{issue.detail}</p>
                          <div style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "0.4rem",
                            color: "var(--success)",
                            fontSize: "0.8rem",
                          }}>
                            <ArrowRight size={14} />
                            <span>{issue.recommendation}</span>
                          </div>
                          {issue.affected_pages && issue.affected_pages.length > 0 && (
                            <div style={{ marginTop: "0.4rem", fontSize: "0.75rem", color: "var(--text-muted)" }}>
                              Страницы: {issue.affected_pages.join(", ")}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Suggestions list */}
          {report.suggestions && report.suggestions.length > 0 && (
            <div>
              <h4 style={{ margin: "0 0 0.75rem 0", fontSize: "0.95rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <CheckCircle size={18} weight="fill" style={{ color: "var(--accent)" }} />
                Предложения ({report.suggestions.length})
              </h4>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                {report.suggestions.map((sug, idx) => {
                  const sIdx = idx + (report.issues?.length ?? 0) + 100;
                  const style = SEVERITY_STYLES[sug.severity] || SEVERITY_STYLES.info;
                  const isExpanded = expanded.has(sIdx);
                  return (
                    <div
                      key={sIdx}
                      style={{
                        background: style.bg,
                        border: `1px solid ${style.border}`,
                        borderRadius: 10,
                        overflow: "hidden",
                      }}
                    >
                      <button
                        onClick={() => toggleExpand(sIdx)}
                        style={{
                          width: "100%",
                          display: "flex",
                          alignItems: "center",
                          gap: "0.75rem",
                          padding: "0.75rem 1rem",
                          background: "none",
                          border: "none",
                          cursor: "pointer",
                          textAlign: "left",
                        }}
                      >
                        <span style={{
                          padding: "0.15rem 0.5rem",
                          borderRadius: 4,
                          fontSize: "0.7rem",
                          fontWeight: 600,
                          background: style.border,
                          color: "white",
                        }}>
                          {sug.type === "cross_reference" ? "СВЯЗЬ" :
                           sug.type === "missing_concept" ? "КОНЦЕПЦИЯ" :
                           sug.type === "low_confidence" ? "ДАННЫЕ" :
                           sug.type === "pending_confirmation" ? "ПАТТЕРН" : "ИНФО"}
                        </span>
                        <span style={{ flex: 1, fontSize: "0.85rem", color: "var(--text-primary)" }}>
                          {sug.title}
                        </span>
                        {isExpanded ? <CaretUp size={16} /> : <CaretDown size={16} />}
                      </button>
                      {isExpanded && (
                        <div style={{ padding: "0 1rem 0.75rem 1rem", fontSize: "0.82rem" }}>
                          <p style={{ color: "var(--text-secondary)", margin: "0 0 0.5rem 0" }}>{sug.detail}</p>
                          <div style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "0.4rem",
                            color: "var(--success)",
                            fontSize: "0.8rem",
                          }}>
                            <ArrowRight size={14} />
                            <span>{sug.recommendation}</span>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* No issues state */}
          {(!report.issues || report.issues.length === 0) && (!report.suggestions || report.suggestions.length === 0) && (
            <div style={{
              padding: "2rem",
              textAlign: "center",
              background: "rgba(16,185,129,0.04)",
              borderRadius: 12,
              border: "1px solid rgba(16,185,129,0.15)",
            }}>
              <CheckCircle size={40} weight="fill" style={{ color: "var(--success)", marginBottom: "0.75rem" }} />
              <p style={{ color: "var(--success)", margin: 0, fontWeight: 600 }}>
                Wiki в отличном состоянии! Проблем и предложений нет.
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
