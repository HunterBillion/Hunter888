"use client";

/**
 * KnowledgeBasePanel — right-sidebar widget «База ФЗ-127» (compact).
 *
 * PR-16 (2026-05-07). Mini-search over `/api/knowledge/rag/browse` (limit=3
 * for compact display). Кнопка «Открыть полную базу» ведёт на полный
 * `KnowledgeBaseBrowser` через `?tab=knowledge_base` URL-параметр на
 * /pvp (таб включается, центральный layout заменяется на full-screen
 * RAG-browser).
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { BookOpen, Loader2, Search, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";
import { categoryLabel } from "@/lib/categories";

interface RagChunk {
  id: string;
  category: string;
  law_article: string | null;
  fact_text: string;
}

interface RagBrowseResponse {
  chunks: RagChunk[];
  total: number;
}

export function KnowledgeBasePanel() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [chunks, setChunks] = useState<RagChunk[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchChunks = useMemo(() => {
    return async (searchTerm: string) => {
      setLoading(true);
      try {
        const params = new URLSearchParams({ limit: "3" });
        if (searchTerm.trim().length >= 2) params.set("search", searchTerm.trim());
        const data = await api.get<RagBrowseResponse>(`/knowledge/rag/browse?${params}`);
        setChunks(data?.chunks ?? []);
        setTotal(data?.total ?? null);
      } catch (err) {
        logger.warn("[kb-panel] fetch failed:", err);
        setChunks([]);
      } finally {
        setLoading(false);
      }
    };
  }, []);

  // Initial fetch + debounced search.
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => fetchChunks(query), query ? 350 : 0);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [query, fetchChunks]);

  return (
    <section
      className="p-3"
      style={{
        background: "var(--bg-panel)",
        outline: "2px solid var(--accent)",
        outlineOffset: -2,
        boxShadow: "3px 3px 0 0 var(--accent)",
        borderRadius: 0,
      }}
      aria-label="База ФЗ-127"
    >
      <div
        className="font-pixel uppercase tracking-widest mb-3 flex items-center gap-2"
        style={{ color: "var(--accent)", fontSize: 11, letterSpacing: "0.16em" }}
      >
        <BookOpen size={13} />
        БАЗА ФЗ-127
        {total !== null && total > 0 && (
          <span
            className="ml-auto font-pixel text-[10px]"
            style={{ color: "var(--text-muted)", letterSpacing: "0.06em" }}
          >
            {total} статей
          </span>
        )}
      </div>

      <div className="relative mb-2">
        <Search
          size={12}
          className="absolute top-1/2 -translate-y-1/2 left-2"
          style={{ color: "var(--text-muted)" }}
        />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Поиск..."
          className="w-full pl-7 pr-7 py-1.5 text-xs"
          style={{
            background: "var(--bg-secondary, var(--input-bg))",
            color: "var(--text-primary)",
            border: "1px solid var(--border-color)",
            borderRadius: 0,
            outline: "none",
          }}
          onFocus={(e) => { e.currentTarget.style.borderColor = "var(--accent)"; }}
          onBlur={(e) => { e.currentTarget.style.borderColor = "var(--border-color)"; }}
        />
        {query && (
          <button
            type="button"
            onClick={() => setQuery("")}
            className="absolute top-1/2 -translate-y-1/2 right-1.5 p-1"
            style={{ color: "var(--text-muted)" }}
            aria-label="Очистить"
          >
            <X size={11} />
          </button>
        )}
      </div>

      {loading && chunks.length === 0 ? (
        <div className="flex items-center justify-center py-4">
          <Loader2 size={14} className="animate-spin" style={{ color: "var(--text-muted)" }} />
        </div>
      ) : chunks.length === 0 ? (
        <div
          className="font-pixel text-[10px] uppercase tracking-wider py-3 text-center"
          style={{ color: "var(--text-muted)", letterSpacing: "0.14em" }}
        >
          {query ? "Ничего не найдено" : "Загружается..."}
        </div>
      ) : (
        <AnimatePresence mode="popLayout">
          <ul className="flex flex-col gap-1.5">
            {chunks.map((c, i) => (
              <motion.li
                key={c.id}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ delay: i * 0.04 }}
                className="px-2 py-1.5 text-[11px] leading-snug"
                style={{
                  background: "var(--bg-secondary, rgba(0,0,0,0.2))",
                  borderLeft: "2px solid var(--accent)",
                  color: "var(--text-secondary)",
                }}
              >
                <div
                  className="font-pixel uppercase text-[9px] mb-0.5 flex items-center gap-1.5"
                  style={{ color: "var(--accent)", letterSpacing: "0.12em" }}
                >
                  <span>{categoryLabel(c.category)}</span>
                  {c.law_article && (
                    <span style={{ color: "var(--text-muted)" }}>· {c.law_article}</span>
                  )}
                </div>
                <div className="line-clamp-3" style={{ color: "var(--text-primary)" }}>
                  {c.fact_text}
                </div>
              </motion.li>
            ))}
          </ul>
        </AnimatePresence>
      )}

      <button
        type="button"
        onClick={() => router.push("/pvp?tab=knowledge_base")}
        className="mt-3 block w-full text-center font-pixel uppercase text-[10px] tracking-widest py-1.5"
        style={{
          color: "var(--text-muted)",
          border: "1px dashed var(--border-color)",
          background: "transparent",
          letterSpacing: "0.18em",
          cursor: "pointer",
        }}
      >
        Полная база →
      </button>
    </section>
  );
}
