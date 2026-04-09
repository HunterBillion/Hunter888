"use client";

import type { PatternItem } from "./types";
import { CATEGORY_CONFIG } from "./types";

export function PatternsTab({ patterns }: { patterns: PatternItem[] }) {
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
