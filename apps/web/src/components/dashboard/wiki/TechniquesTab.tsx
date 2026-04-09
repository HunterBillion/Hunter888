"use client";

import { Zap } from "lucide-react";
import type { TechniqueItem } from "./types";

export function TechniquesTab({ techniques }: { techniques: TechniqueItem[] }) {
  if (techniques.length === 0) {
    return <p style={{ color: "var(--text-muted)" }}>Техники ещё не обнаружены.</p>;
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
            <Zap size={16} style={{ color: "var(--warning)" }} />
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
                color: t.success_rate >= 0.7 ? "var(--success)" : t.success_rate >= 0.4 ? "var(--warning)" : "var(--danger)",
                fontWeight: 600,
              }}
            >
              {Math.round(t.success_rate * 100)}% успеха
            </span>
          </div>
          {t.description && (
            <p style={{ color: "var(--text-muted)", margin: "0.25rem 0", fontSize: "0.9rem" }}>
              {t.description}
            </p>
          )}
          {t.how_to_apply && (
            <p style={{ color: "var(--text-muted)", margin: "0.5rem 0 0.25rem", fontSize: "0.85rem", fontStyle: "italic" }}>
              Как применять: {t.how_to_apply}
            </p>
          )}
          <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
            Использовано {t.attempt_count} раз | Успешно {t.success_count}
          </div>
        </div>
      ))}
    </div>
  );
}
