"use client";

/**
 * ArenaContentEditor — CRUD for ФЗ-127 knowledge chunks (Arena content).
 *
 * Migrated 2026-04-26 from `apps/web/src/app/methodologist/arena-content/page.tsx`
 * into a dashboard sub-tab. Backend route switched to `/rop/arena/chunks`.
 *
 * 2026-05-04 PR-3 audit hardening:
 *   * Inline edit form per row (was: only Create + Delete)
 *   * Pagination UI — was hardcoded page_size=50 with no controls,
 *     hiding 87% of the 375 prod chunks
 *   * Empty-state block (was: blank panel on zero results)
 *   * Search debounce 300ms + AbortController on stale fetches
 *     (was: each keystroke fired a new request, p99 94s on 10 parallel)
 *   * `embedding_ready` chip per chunk so methodologists see which
 *     edits have actually re-indexed in RAG
 *   * Optimistic locking via `If-Match: <updated_at>` on PUT — backend
 *     returns 412 stale_chunk if another editor saved in between
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import {
  Database,
  Plus,
  Trash2,
  Pencil,
  Loader2,
  Save,
  X,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { logger } from "@/lib/logger";
import { toast } from "sonner";
import { ImportWizard } from "@/components/methodology/ImportWizard";
import { ImportHistory } from "@/components/methodology/ImportHistory";

interface Chunk {
  id: string;
  // Canonical fields
  fact_text: string;
  law_article: string;
  // Legacy aliases — backend keeps emitting these for back-compat
  title: string;
  content: string;
  article_reference: string | null;
  category: string;
  difficulty_level: number;
  is_court_practice: boolean;
  tags: string[];
  created_at: string | null;
  updated_at: string | null;
  // Diagnostics — added in PR-1
  embedding_ready: boolean;
  retrieval_count: number;
}

const CATEGORIES = [
  "eligibility", "procedure", "property", "consequences", "costs",
  "creditors", "documents", "timeline", "court", "rights",
];

const DEFAULT_FORM = {
  title: "",
  content: "",
  category: "eligibility",
  article_reference: "",
  difficulty_level: 3,
  is_court_practice: false,
  tags: "",
};

const PAGE_SIZE = 50;
const SEARCH_DEBOUNCE_MS = 300;

export function ArenaContentEditor() {
  const [chunks, setChunks] = useState<Chunk[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const [page, setPage] = useState(1);
  const [categoryFilter, setCategoryFilter] = useState<string>("");
  const [searchInput, setSearchInput] = useState("");
  const [searchQuery, setSearchQuery] = useState(""); // debounced
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState(DEFAULT_FORM);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState(DEFAULT_FORM);
  const [editingUpdatedAt, setEditingUpdatedAt] = useState<string | null>(null);
  const [savingEdit, setSavingEdit] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [importRefreshKey, setImportRefreshKey] = useState(0);

  // Debounce search input → 300ms after last keystroke flushes to query.
  useEffect(() => {
    const t = setTimeout(() => setSearchQuery(searchInput), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [searchInput]);

  // Reset to page 1 when filters change so we don't paginate past the end.
  useEffect(() => {
    setPage(1);
  }, [searchQuery, categoryFilter]);

  // AbortController per fetch so a fast-typing methodologist doesn't
  // race the previous in-flight request.
  const abortRef = useRef<AbortController | null>(null);

  const fetchChunks = useCallback(() => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setLoading(true);
    setErrorMsg(null);

    const params = new URLSearchParams({
      page: String(page),
      page_size: String(PAGE_SIZE),
    });
    if (categoryFilter) params.set("category", categoryFilter);
    if (searchQuery) params.set("search", searchQuery);

    api
      .get<{ items: Chunk[]; total: number }>(
        `/rop/arena/chunks?${params}`,
        { signal: ctrl.signal },
      )
      .then((res) => {
        if (ctrl.signal.aborted) return;
        setChunks(res.items);
        setTotal(res.total);
      })
      .catch((err) => {
        if (ctrl.signal.aborted) return;
        if (err instanceof DOMException && err.name === "AbortError") return;
        const msg = err instanceof ApiError ? err.message : String(err);
        setErrorMsg(msg);
        logger.error("[ArenaContentEditor] load failed:", err);
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoading(false);
      });

    return () => ctrl.abort();
  }, [page, categoryFilter, searchQuery]);

  useEffect(() => {
    fetchChunks();
    return () => abortRef.current?.abort();
  }, [fetchChunks]);

  const totalPages = useMemo(() => Math.max(1, Math.ceil(total / PAGE_SIZE)), [total]);

  const handleCreate = async () => {
    try {
      await api.post("/rop/arena/chunks", {
        ...createForm,
        tags: createForm.tags.split(",").map((t) => t.trim()).filter(Boolean),
      });
      setShowCreate(false);
      setCreateForm(DEFAULT_FORM);
      fetchChunks();
      toast.success("Чанк создан");
    } catch (err) {
      logger.error("[ArenaContentEditor] create failed:", err);
      toast.error("Ошибка создания чанка", {
        description: err instanceof Error ? err.message : undefined,
      });
    }
  };

  const startEdit = (chunk: Chunk) => {
    setEditingId(chunk.id);
    setEditingUpdatedAt(chunk.updated_at);
    setEditForm({
      title: chunk.title || chunk.law_article || "",
      content: chunk.content || chunk.fact_text || "",
      category: chunk.category,
      article_reference: chunk.article_reference || chunk.law_article || "",
      difficulty_level: chunk.difficulty_level,
      is_court_practice: chunk.is_court_practice,
      tags: (chunk.tags || []).join(", "),
    });
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditingUpdatedAt(null);
    setEditForm(DEFAULT_FORM);
  };

  const handleSaveEdit = async () => {
    if (!editingId) return;
    setSavingEdit(true);
    try {
      const headers: Record<string, string> = {};
      if (editingUpdatedAt) headers["If-Match"] = editingUpdatedAt;

      await api.put(
        `/rop/arena/chunks/${editingId}`,
        {
          ...editForm,
          tags: editForm.tags.split(",").map((t) => t.trim()).filter(Boolean),
        },
        { headers },
      );
      toast.success("Чанк обновлён");
      cancelEdit();
      fetchChunks();
    } catch (err) {
      logger.error("[ArenaContentEditor] update failed:", err);
      // 412 stale_chunk — guide the user to refresh and retry
      if (err instanceof ApiError && err.status === 412) {
        toast.error("Чанк изменён другим редактором", {
          description: "Перезагрузите список и примените правки повторно.",
        });
      } else if (err instanceof ApiError && err.status === 410) {
        toast.error("Чанк помечен удалённым", {
          description: "Сначала восстановите его (раздел будет в PR-3 follow-up).",
        });
      } else {
        toast.error("Ошибка обновления чанка", {
          description: err instanceof Error ? err.message : undefined,
        });
      }
    } finally {
      setSavingEdit(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Удалить чанк? Это soft-delete — историю можно будет восстановить.")) return;
    try {
      await api.delete(`/rop/arena/chunks/${id}`);
      fetchChunks();
      toast.success("Чанк удалён");
    } catch (err) {
      logger.error("[ArenaContentEditor] delete failed:", err);
      toast.error("Ошибка удаления чанка", {
        description: err instanceof Error ? err.message : undefined,
      });
    }
  };

  const showEmpty = !loading && !errorMsg && chunks.length === 0;
  const showError = !loading && !!errorMsg;

  return (
    <div className="space-y-4">
      {/* ── Header ──────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Database size={16} style={{ color: "var(--accent)" }} />
          <h3
            className="font-display text-sm tracking-wider"
            style={{ color: "var(--text-secondary)" }}
          >
            КОНТЕНТ АРЕНЫ
          </h3>
          <span className="font-mono text-xs" style={{ color: "var(--text-muted)" }}>
            {total} чанков ФЗ-127
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => fetchChunks()}
            className="p-1.5 rounded-md"
            style={{ background: "var(--bg-secondary)", color: "var(--text-muted)" }}
            title="Обновить"
            aria-label="Обновить список"
          >
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
          </button>
          <button
            type="button"
            onClick={() => setImportOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium"
            style={{ background: "var(--accent-muted)", color: "var(--accent)" }}
            title="Загрузить статью или подборку фактов — платформа добавит в очередь review."
          >
            📤 Импорт
          </button>
          <motion.button
            type="button"
            onClick={() => setShowCreate(!showCreate)}
            className="btn-neon flex items-center gap-2 text-xs"
            whileTap={{ scale: 0.97 }}
          >
            <Plus size={14} /> Новый чанк
          </motion.button>
        </div>
      </div>

      <ImportWizard
        open={importOpen}
        onClose={() => setImportOpen(false)}
        presetRouteType="arena_knowledge"
        onApproved={() => setImportRefreshKey((k) => k + 1)}
      />
      <ImportHistory routeType="arena_knowledge" refreshKey={importRefreshKey} />

      {/* ── Filters ─────────────────────────────────────────────────── */}
      <div className="flex gap-2 flex-wrap">
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="rounded-lg px-3 py-1.5 text-xs"
          style={{
            background: "var(--input-bg)",
            border: "1px solid var(--border-color)",
            color: "var(--text-primary)",
          }}
        >
          <option value="">Все категории</option>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <input
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          placeholder="Поиск по тексту, ст., тегам, делу..."
          className="rounded-lg px-3 py-1.5 text-xs flex-1"
          style={{
            background: "var(--input-bg)",
            border: "1px solid var(--border-color)",
            color: "var(--text-primary)",
          }}
        />
      </div>

      {/* ── Create form ─────────────────────────────────────────────── */}
      {showCreate && (
        <motion.div
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: "auto", opacity: 1 }}
          className="rounded-xl p-4 space-y-3"
          style={{ background: "var(--glass-bg)", border: "1px solid var(--accent)" }}
        >
          <input
            value={createForm.title}
            onChange={(e) => setCreateForm({ ...createForm, title: e.target.value })}
            placeholder="Заголовок"
            className="w-full rounded-lg px-3 py-2 text-sm"
            style={{
              background: "var(--input-bg)",
              border: "1px solid var(--border-color)",
              color: "var(--text-primary)",
            }}
          />
          <textarea
            value={createForm.content}
            onChange={(e) => setCreateForm({ ...createForm, content: e.target.value })}
            placeholder="Содержание чанка (мин. 10 символов)..."
            rows={4}
            className="w-full rounded-lg px-3 py-2 text-sm"
            style={{
              background: "var(--input-bg)",
              border: "1px solid var(--border-color)",
              color: "var(--text-primary)",
            }}
          />
          <div className="flex gap-3 flex-wrap">
            <select
              value={createForm.category}
              onChange={(e) => setCreateForm({ ...createForm, category: e.target.value })}
              className="rounded-lg px-3 py-1.5 text-xs"
              style={{
                background: "var(--input-bg)",
                border: "1px solid var(--border-color)",
                color: "var(--text-primary)",
              }}
            >
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
            <input
              value={createForm.article_reference}
              onChange={(e) =>
                setCreateForm({ ...createForm, article_reference: e.target.value })
              }
              placeholder="Ст. 213.X"
              className="rounded-lg px-3 py-1.5 text-xs"
              style={{
                background: "var(--input-bg)",
                border: "1px solid var(--border-color)",
                color: "var(--text-primary)",
              }}
            />
            <select
              value={createForm.difficulty_level}
              onChange={(e) =>
                setCreateForm({ ...createForm, difficulty_level: Number(e.target.value) })
              }
              className="rounded-lg px-3 py-1.5 text-xs"
              style={{
                background: "var(--input-bg)",
                border: "1px solid var(--border-color)",
                color: "var(--text-primary)",
              }}
            >
              {[1, 2, 3, 4, 5].map((d) => (
                <option key={d} value={d}>Сложность {d}</option>
              ))}
            </select>
          </div>
          <input
            value={createForm.tags}
            onChange={(e) => setCreateForm({ ...createForm, tags: e.target.value })}
            placeholder="Теги (через запятую)"
            className="w-full rounded-lg px-3 py-1.5 text-xs"
            style={{
              background: "var(--input-bg)",
              border: "1px solid var(--border-color)",
              color: "var(--text-primary)",
            }}
          />
          <div className="flex gap-2">
            <motion.button
              type="button"
              onClick={handleCreate}
              className="btn-neon flex items-center gap-1 text-xs"
              whileTap={{ scale: 0.97 }}
            >
              <Save size={12} /> Создать
            </motion.button>
            <button
              type="button"
              onClick={() => setShowCreate(false)}
              className="text-xs"
              style={{ color: "var(--text-muted)" }}
            >
              Отмена
            </button>
          </div>
        </motion.div>
      )}

      {/* ── List + states ───────────────────────────────────────────── */}
      {loading && chunks.length === 0 ? (
        <div className="flex justify-center py-16">
          <Loader2 size={24} className="animate-spin" style={{ color: "var(--accent)" }} />
        </div>
      ) : null}

      {showError && (
        <div
          className="rounded-xl p-4 text-sm"
          style={{
            background: "rgba(239,68,68,0.08)",
            border: "1px solid rgba(239,68,68,0.35)",
            color: "#ef4444",
          }}
        >
          Ошибка загрузки: {errorMsg}{" "}
          <button
            type="button"
            onClick={() => fetchChunks()}
            className="underline ml-2"
          >
            Повторить
          </button>
        </div>
      )}

      {showEmpty && (
        <div
          className="rounded-xl p-8 text-center text-sm"
          style={{
            background: "var(--glass-bg)",
            border: "1px dashed var(--border-color)",
            color: "var(--text-muted)",
          }}
        >
          <Database size={28} style={{ margin: "0 auto 10px", opacity: 0.4 }} />
          {searchQuery || categoryFilter ? (
            <>
              Ничего не найдено по фильтру.{" "}
              <button
                type="button"
                onClick={() => {
                  setSearchInput("");
                  setSearchQuery("");
                  setCategoryFilter("");
                }}
                className="underline"
              >
                Сбросить
              </button>
            </>
          ) : (
            <>
              В базе пока нет чанков — нажмите «Новый чанк» или импортируйте
              подборку фактов.
            </>
          )}
        </div>
      )}

      {!showEmpty && !showError && chunks.length > 0 && (
        <div className="space-y-2">
          {chunks.map((chunk, i) => {
            const isEditing = editingId === chunk.id;
            const animProps =
              i < 20
                ? {
                    initial: { opacity: 0 },
                    animate: { opacity: 1 },
                    transition: { delay: i * 0.02 },
                  }
                : {};
            return (
              <motion.div
                key={chunk.id}
                {...animProps}
                className="rounded-xl p-3"
                style={{
                  background: "var(--glass-bg)",
                  border: isEditing
                    ? "1px solid var(--accent)"
                    : "1px solid var(--glass-border)",
                }}
              >
                {isEditing ? (
                  <div className="space-y-2">
                    <input
                      value={editForm.title}
                      onChange={(e) =>
                        setEditForm({ ...editForm, title: e.target.value })
                      }
                      placeholder="Заголовок"
                      className="w-full rounded-lg px-3 py-2 text-sm"
                      style={{
                        background: "var(--input-bg)",
                        border: "1px solid var(--border-color)",
                        color: "var(--text-primary)",
                      }}
                    />
                    <textarea
                      value={editForm.content}
                      onChange={(e) =>
                        setEditForm({ ...editForm, content: e.target.value })
                      }
                      placeholder="Содержание чанка (мин. 10 символов)..."
                      rows={5}
                      className="w-full rounded-lg px-3 py-2 text-sm"
                      style={{
                        background: "var(--input-bg)",
                        border: "1px solid var(--border-color)",
                        color: "var(--text-primary)",
                      }}
                    />
                    <div className="flex gap-2 flex-wrap">
                      <select
                        value={editForm.category}
                        onChange={(e) =>
                          setEditForm({ ...editForm, category: e.target.value })
                        }
                        className="rounded-lg px-3 py-1.5 text-xs"
                        style={{
                          background: "var(--input-bg)",
                          border: "1px solid var(--border-color)",
                          color: "var(--text-primary)",
                        }}
                      >
                        {CATEGORIES.map((c) => (
                          <option key={c} value={c}>{c}</option>
                        ))}
                      </select>
                      <input
                        value={editForm.article_reference}
                        onChange={(e) =>
                          setEditForm({
                            ...editForm,
                            article_reference: e.target.value,
                          })
                        }
                        placeholder="Ст. 213.X"
                        className="rounded-lg px-3 py-1.5 text-xs"
                        style={{
                          background: "var(--input-bg)",
                          border: "1px solid var(--border-color)",
                          color: "var(--text-primary)",
                        }}
                      />
                      <select
                        value={editForm.difficulty_level}
                        onChange={(e) =>
                          setEditForm({
                            ...editForm,
                            difficulty_level: Number(e.target.value),
                          })
                        }
                        className="rounded-lg px-3 py-1.5 text-xs"
                        style={{
                          background: "var(--input-bg)",
                          border: "1px solid var(--border-color)",
                          color: "var(--text-primary)",
                        }}
                      >
                        {[1, 2, 3, 4, 5].map((d) => (
                          <option key={d} value={d}>Сложность {d}</option>
                        ))}
                      </select>
                    </div>
                    <input
                      value={editForm.tags}
                      onChange={(e) =>
                        setEditForm({ ...editForm, tags: e.target.value })
                      }
                      placeholder="Теги (через запятую)"
                      className="w-full rounded-lg px-3 py-1.5 text-xs"
                      style={{
                        background: "var(--input-bg)",
                        border: "1px solid var(--border-color)",
                        color: "var(--text-primary)",
                      }}
                    />
                    <div className="flex gap-2">
                      <motion.button
                        type="button"
                        onClick={handleSaveEdit}
                        disabled={savingEdit}
                        className="btn-neon flex items-center gap-1 text-xs"
                        whileTap={{ scale: 0.97 }}
                      >
                        {savingEdit ? (
                          <Loader2 size={12} className="animate-spin" />
                        ) : (
                          <Save size={12} />
                        )}{" "}
                        Сохранить
                      </motion.button>
                      <button
                        type="button"
                        onClick={cancelEdit}
                        className="flex items-center gap-1 text-xs"
                        style={{ color: "var(--text-muted)" }}
                      >
                        <X size={12} /> Отмена
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span
                          className="text-sm font-medium truncate"
                          style={{ color: "var(--text-primary)" }}
                        >
                          {chunk.title || chunk.law_article}
                        </span>
                        <span
                          className="rounded px-1.5 py-0.5 text-xs font-mono"
                          style={{
                            background: "var(--accent-muted)",
                            color: "var(--accent)",
                          }}
                        >
                          {chunk.category}
                        </span>
                        <span
                          className="text-xs font-mono"
                          style={{ color: "var(--text-muted)" }}
                        >
                          D{chunk.difficulty_level}
                        </span>
                        {chunk.is_court_practice && (
                          <span
                            className="rounded px-1 py-0.5 text-xs"
                            style={{
                              background: "rgba(129,140,248,0.1)",
                              color: "var(--accent-hover)",
                            }}
                          >
                            Суд.практика
                          </span>
                        )}
                        {!chunk.embedding_ready && (
                          <span
                            className="rounded px-1.5 py-0.5 text-xs"
                            style={{
                              background: "rgba(245,158,11,0.1)",
                              color: "#f59e0b",
                              border: "1px solid rgba(245,158,11,0.3)",
                            }}
                            title="Embedding ещё не вычислен — RAG этот чанк временно не находит."
                          >
                            ⏳ embedding pending
                          </span>
                        )}
                        {chunk.retrieval_count > 0 && (
                          <span
                            className="text-xs font-mono"
                            style={{ color: "var(--text-muted)" }}
                            title="Сколько раз чанк был выбран RAG-pipeline"
                          >
                            ↻ {chunk.retrieval_count}
                          </span>
                        )}
                      </div>
                      <p
                        className="text-xs mt-1"
                        style={{
                          color: "var(--text-muted)",
                          display: "-webkit-box",
                          WebkitLineClamp: 3,
                          WebkitBoxOrient: "vertical",
                          overflow: "hidden",
                        }}
                      >
                        {chunk.fact_text || chunk.content}
                      </p>
                    </div>
                    <div className="flex gap-1 ml-2 flex-shrink-0">
                      <button
                        type="button"
                        onClick={() => startEdit(chunk)}
                        className="p-1.5 rounded-lg hover:bg-white/5"
                        title="Изменить"
                        aria-label="Изменить чанк"
                      >
                        <Pencil size={14} style={{ color: "var(--text-muted)" }} />
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDelete(chunk.id)}
                        className="p-1.5 rounded-lg hover:bg-red-500/10"
                        title="Удалить (soft-delete)"
                        aria-label="Удалить чанк"
                      >
                        <Trash2 size={14} style={{ color: "var(--danger)" }} />
                      </button>
                    </div>
                  </div>
                )}
              </motion.div>
            );
          })}
        </div>
      )}

      {/* ── Pagination ──────────────────────────────────────────────── */}
      {total > PAGE_SIZE && (
        <div
          className="flex items-center justify-between text-xs"
          style={{ color: "var(--text-muted)" }}
        >
          <div>
            Страница {page} из {totalPages} • показано{" "}
            {chunks.length} из {total}
          </div>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1 || loading}
              className="p-1.5 rounded-md"
              style={{
                background: page === 1 ? "transparent" : "var(--bg-secondary)",
                border: "1px solid var(--border-color)",
                color: "var(--text-secondary)",
                cursor: page === 1 ? "not-allowed" : "pointer",
                opacity: page === 1 ? 0.4 : 1,
              }}
              aria-label="Предыдущая страница"
            >
              <ChevronLeft size={14} />
            </button>
            <button
              type="button"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages || loading}
              className="p-1.5 rounded-md"
              style={{
                background:
                  page >= totalPages ? "transparent" : "var(--bg-secondary)",
                border: "1px solid var(--border-color)",
                color: "var(--text-secondary)",
                cursor: page >= totalPages ? "not-allowed" : "pointer",
                opacity: page >= totalPages ? 0.4 : 1,
              }}
              aria-label="Следующая страница"
            >
              <ChevronRight size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
