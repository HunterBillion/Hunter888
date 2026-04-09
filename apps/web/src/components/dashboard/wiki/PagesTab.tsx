"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import {
  ChevronRight,
  Edit3,
  FileText,
  Loader2,
  Save,
  X,
} from "lucide-react";
import Markdown from "react-markdown";
import type { WikiPageItem, WikiPageContent } from "./types";
import { formatDate } from "./utils";

export function PagesTab({
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
