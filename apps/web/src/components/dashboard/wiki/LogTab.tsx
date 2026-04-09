"use client";

import type { WikiLogEntry } from "./types";
import { ACTION_LABELS } from "./types";
import { formatDate } from "./utils";

export function LogTab({ logEntries }: { logEntries: WikiLogEntry[] }) {
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
