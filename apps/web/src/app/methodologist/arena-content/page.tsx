"use client";

import { useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";
import { Database, Plus, Search, Edit, Trash2, Loader2, Save, ShieldAlert } from "lucide-react";
import AuthLayout from "@/components/layout/AuthLayout";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";
import { useAuth } from "@/hooks/useAuth";
import { hasRole } from "@/lib/guards";

interface Chunk {
  id: string;
  title: string;
  content: string;
  category: string;
  article_reference: string | null;
  difficulty_level: number;
  is_court_practice: boolean;
  tags: string[];
  created_at: string | null;
}

const CATEGORIES = [
  "eligibility", "procedure", "property", "consequences", "costs",
  "creditors", "documents", "timeline", "court", "rights",
];

export default function ArenaContentPage() {
  const { user, loading: authLoading } = useAuth();
  const accessDenied = !authLoading && user != null && !hasRole(user, ["admin", "rop", "methodologist"]);

  const [chunks, setChunks] = useState<Chunk[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [categoryFilter, setCategoryFilter] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  // Create form state
  const [form, setForm] = useState({
    title: "", content: "", category: "eligibility",
    article_reference: "", difficulty_level: 3,
    is_court_practice: false, tags: "",
  });

  const fetchChunks = useCallback(() => {
    setLoading(true);
    const params = new URLSearchParams({ page_size: "50" });
    if (categoryFilter) params.set("category", categoryFilter);
    if (searchQuery) params.set("search", searchQuery);

    api.get(`/methodologist/arena/chunks?${params}`)
      .then((res) => { setChunks(res.data.items); setTotal(res.data.total); })
      .catch((err) => logger.error("[ArenaContent] Failed to load chunks:", err))
      .finally(() => setLoading(false));
  }, [categoryFilter, searchQuery]);

  useEffect(() => { fetchChunks(); }, [fetchChunks]);

  const handleCreate = async () => {
    try {
      await api.post("/methodologist/arena/chunks", {
        ...form,
        tags: form.tags.split(",").map((t) => t.trim()).filter(Boolean),
      });
      setShowCreate(false);
      setForm({ title: "", content: "", category: "eligibility", article_reference: "", difficulty_level: 3, is_court_practice: false, tags: "" });
      fetchChunks();
    } catch (e) { alert("Error creating chunk"); }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Удалить чанк?")) return;
    try {
      await api.delete(`/methodologist/arena/chunks/${id}`);
      fetchChunks();
    } catch (e) { alert("Error deleting chunk"); }
  };

  if (accessDenied) {
    return (
      <AuthLayout>
        <div className="flex min-h-screen items-center justify-center">
          <div className="text-center">
            <ShieldAlert size={48} style={{ color: "var(--danger)", margin: "0 auto 16px" }} />
            <h2 className="font-display text-xl font-bold" style={{ color: "var(--text-primary)" }}>Доступ запрещён</h2>
            <p className="mt-2 text-sm" style={{ color: "var(--text-muted)" }}>Эта страница доступна только методологам, РОП и администраторам.</p>
          </div>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout>
      <div className="relative panel-grid-bg min-h-screen">
        <div className="mx-auto max-w-5xl px-4 py-8">
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
            <div className="flex items-center justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <Database size={20} style={{ color: "var(--accent)" }} />
                  <h1 className="font-display text-xl font-bold tracking-widest" style={{ color: "var(--text-primary)" }}>
                    КОНТЕНТ АРЕНЫ
                  </h1>
                </div>
                <p className="mt-1 font-mono text-xs" style={{ color: "var(--text-muted)" }}>
                  {total} чанков ФЗ-127
                </p>
              </div>
              <motion.button
                onClick={() => setShowCreate(!showCreate)}
                className="btn-neon flex items-center gap-2 text-xs"
                whileTap={{ scale: 0.97 }}
              >
                <Plus size={14} /> Новый чанк
              </motion.button>
            </div>
          </motion.div>

          {/* Filters */}
          <div className="mt-4 flex gap-2 flex-wrap">
            <select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              className="rounded-lg px-3 py-1.5 text-xs"
              style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)", color: "var(--text-primary)" }}
            >
              <option value="">Все категории</option>
              {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
            <input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Поиск..."
              className="rounded-lg px-3 py-1.5 text-xs flex-1"
              style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)", color: "var(--text-primary)" }}
            />
          </div>

          {/* Create form */}
          {showCreate && (
            <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }}
              className="mt-4 rounded-xl p-4 space-y-3"
              style={{ background: "var(--glass-bg)", border: "1px solid var(--accent)" }}>
              <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })}
                placeholder="Заголовок" className="w-full rounded-lg px-3 py-2 text-sm"
                style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)", color: "var(--text-primary)" }} />
              <textarea value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })}
                placeholder="Содержание чанка..." rows={4} className="w-full rounded-lg px-3 py-2 text-sm"
                style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)", color: "var(--text-primary)" }} />
              <div className="flex gap-3">
                <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}
                  className="rounded-lg px-3 py-1.5 text-xs"
                  style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)", color: "var(--text-primary)" }}>
                  {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
                <input value={form.article_reference} onChange={(e) => setForm({ ...form, article_reference: e.target.value })}
                  placeholder="Ст. 213.X" className="rounded-lg px-3 py-1.5 text-xs"
                  style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)", color: "var(--text-primary)" }} />
                <select value={form.difficulty_level} onChange={(e) => setForm({ ...form, difficulty_level: Number(e.target.value) })}
                  className="rounded-lg px-3 py-1.5 text-xs"
                  style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)", color: "var(--text-primary)" }}>
                  {[1, 2, 3, 4, 5].map((d) => <option key={d} value={d}>Сложность {d}</option>)}
                </select>
              </div>
              <input value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })}
                placeholder="Теги (через запятую)" className="w-full rounded-lg px-3 py-1.5 text-xs"
                style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)", color: "var(--text-primary)" }} />
              <div className="flex gap-2">
                <motion.button onClick={handleCreate} className="btn-neon flex items-center gap-1 text-xs" whileTap={{ scale: 0.97 }}>
                  <Save size={12} /> Создать
                </motion.button>
                <button onClick={() => setShowCreate(false)} className="text-xs" style={{ color: "var(--text-muted)" }}>
                  Отмена
                </button>
              </div>
            </motion.div>
          )}

          {/* Chunks list */}
          {loading ? (
            <div className="mt-8 flex justify-center py-16">
              <Loader2 size={24} className="animate-spin" style={{ color: "var(--accent)" }} />
            </div>
          ) : (
            <div className="mt-4 space-y-2">
              {chunks.map((chunk, i) => (
                <motion.div
                  key={chunk.id}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: i * 0.02 }}
                  className="rounded-xl p-3"
                  style={{ background: "var(--glass-bg)", border: "1px solid var(--glass-border)" }}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium truncate" style={{ color: "var(--text-primary)" }}>
                          {chunk.title}
                        </span>
                        <span className="rounded px-1.5 py-0.5 text-xs font-mono"
                          style={{ background: "var(--accent-muted)", color: "var(--accent)" }}>
                          {chunk.category}
                        </span>
                        <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                          D{chunk.difficulty_level}
                        </span>
                        {chunk.is_court_practice && (
                          <span className="rounded px-1 py-0.5 text-xs"
                            style={{ background: "rgba(129,140,248,0.1)", color: "var(--accent-hover)" }}>
                            Суд.практика
                          </span>
                        )}
                      </div>
                      <p className="text-xs mt-1 line-clamp-2" style={{ color: "var(--text-muted)" }}>
                        {chunk.content}
                      </p>
                    </div>
                    <div className="flex gap-1 ml-2 flex-shrink-0">
                      <button onClick={() => handleDelete(chunk.id)}
                        className="p-1.5 rounded-lg hover:bg-red-500/10" title="Удалить">
                        <Trash2 size={14} style={{ color: "var(--danger)" }} />
                      </button>
                    </div>
                  </div>
                </motion.div>
              ))}
            </div>
          )}
        </div>
      </div>
    </AuthLayout>
  );
}
