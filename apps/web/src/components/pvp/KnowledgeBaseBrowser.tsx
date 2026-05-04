"use client";

/**
 * KnowledgeBaseBrowser — full RAG transparency view.
 *
 * 2026-05-04: user requested "видеть всё что AI знает" — every chunk,
 * every question template, every common error, every blitz Q&A — so
 * they can copy any answer and verify the system end-to-end.
 *
 * Backend: GET /api/knowledge/rag/browse?category=&search=&difficulty=
 *
 * Layout: filters on top, then a scroll-list of expandable cards. Each
 * card shows the full chunk: facts, article, hint, common-errors,
 * blitz Q&A, question templates. Every text block is copy-clickable.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Loader2,
  Search,
  Copy,
  Check,
  BookOpen,
  AlertTriangle,
  Sparkles,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";

interface RagChunk {
  id: string;
  category: string;
  difficulty: number;
  law_article: string;
  fact_text: string;
  correct_response_hint: string | null;
  common_errors: string[];
  match_keywords: string[];
  question_templates: { text?: string; difficulty?: number }[];
  follow_up_questions: string[];
  blitz_question: string | null;
  blitz_answer: string | null;
  court_case_reference: string | null;
  is_court_practice: boolean;
  tags: string[];
}

interface BrowseResponse {
  chunks: RagChunk[];
  total: number;
  limit: number;
  offset: number;
  by_category: Record<string, number>;
}

const CATEGORY_LABELS: Record<string, string> = {
  eligibility: "Условия подачи",
  procedure: "Процедуры",
  property: "Имущество",
  consequences: "Последствия",
  costs: "Расходы",
  creditors: "Кредиторы",
  documents: "Документы",
  timeline: "Сроки",
  court: "Суд",
  rights: "Права",
};

const PAGE_SIZE = 50;

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={async (e) => {
        e.stopPropagation();
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1200);
        } catch {
          /* ignore */
        }
      }}
      className="inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[10px] uppercase tracking-wider transition-colors"
      style={{
        background: copied ? "rgba(34,197,94,0.18)" : "rgba(255,255,255,0.06)",
        color: copied ? "var(--success)" : "var(--text-muted)",
        border: "1px solid rgba(255,255,255,0.08)",
      }}
      title="Скопировать"
    >
      {copied ? <Check size={10} /> : <Copy size={10} />}
      {copied ? "OK" : "копировать"}
    </button>
  );
}

function ChunkCard({ chunk }: { chunk: RagChunk }) {
  const [expanded, setExpanded] = useState(false);
  const catLabel = CATEGORY_LABELS[chunk.category] ?? chunk.category;

  return (
    <div
      className="rounded-xl overflow-hidden"
      style={{
        background: "var(--bg-panel)",
        border: "1px solid var(--border-color)",
      }}
    >
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-start justify-between gap-3 p-4 text-left hover:opacity-90 transition-opacity"
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1.5 flex-wrap">
            <span
              className="font-pixel text-[10px] uppercase tracking-widest px-1.5 py-0.5"
              style={{
                color: "var(--accent)",
                background: "color-mix(in srgb, var(--accent) 12%, transparent)",
                border: "1px solid color-mix(in srgb, var(--accent) 30%, transparent)",
              }}
            >
              {catLabel}
            </span>
            <span
              className="font-mono text-[10px] uppercase tracking-widest"
              style={{ color: "var(--text-muted)" }}
            >
              сложность {chunk.difficulty}/5
            </span>
            {chunk.is_court_practice && (
              <span
                className="font-mono text-[10px] uppercase tracking-widest px-1.5 py-0.5"
                style={{
                  color: "#a78bfa",
                  background: "rgba(167,139,250,0.12)",
                  border: "1px solid rgba(167,139,250,0.3)",
                }}
              >
                судебная практика
              </span>
            )}
          </div>
          <div
            className="text-sm font-medium leading-relaxed line-clamp-2"
            style={{ color: "var(--text-primary)" }}
          >
            {chunk.fact_text}
          </div>
          <div
            className="mt-1 text-xs font-mono"
            style={{ color: "var(--text-muted)" }}
          >
            📑 {chunk.law_article}
          </div>
        </div>
        <span className="shrink-0 mt-1" style={{ color: "var(--text-muted)" }}>
          {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </span>
      </button>

      {expanded && (
        <div
          className="px-4 pb-4 space-y-3 border-t"
          style={{ borderColor: "rgba(255,255,255,0.06)" }}
        >
          {/* Full fact text */}
          <Section
            label="📖 Факт целиком"
            content={chunk.fact_text}
            copyText={chunk.fact_text}
          />

          {/* Article */}
          <Section
            label="📑 Статья"
            content={chunk.law_article}
            copyText={chunk.law_article}
          />

          {/* Correct response hint */}
          {chunk.correct_response_hint && (
            <Section
              label="✓ Эталонный ответ (correct_response_hint)"
              content={chunk.correct_response_hint}
              copyText={chunk.correct_response_hint}
              accent="var(--success)"
            />
          )}

          {/* Common errors */}
          {chunk.common_errors.length > 0 && (
            <div>
              <Header
                label="⚠ Распространённые ошибки (common_errors)"
                accent="var(--warning)"
              />
              <ul className="mt-1.5 space-y-1">
                {chunk.common_errors.map((err, i) => (
                  <li
                    key={i}
                    className="flex items-start justify-between gap-2 text-sm pl-3"
                    style={{ color: "var(--text-secondary)" }}
                  >
                    <span>
                      <span style={{ color: "var(--warning)" }}>→ </span>
                      {err}
                    </span>
                    <CopyButton text={err} />
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Blitz Q&A */}
          {(chunk.blitz_question || chunk.blitz_answer) && (
            <div
              className="rounded-lg p-3"
              style={{
                background: "color-mix(in srgb, var(--warning) 6%, transparent)",
                border: "1px solid color-mix(in srgb, var(--warning) 25%, transparent)",
              }}
            >
              <div
                className="font-pixel text-[11px] uppercase tracking-widest mb-2"
                style={{ color: "var(--warning)" }}
              >
                ⚡ БЛИЦ Q&A
              </div>
              {chunk.blitz_question && (
                <div className="mb-2">
                  <div
                    className="text-[10px] uppercase tracking-wider mb-0.5"
                    style={{ color: "var(--text-muted)" }}
                  >
                    Вопрос
                  </div>
                  <div className="flex items-start justify-between gap-2 text-sm">
                    <span style={{ color: "var(--text-primary)" }}>{chunk.blitz_question}</span>
                    <CopyButton text={chunk.blitz_question} />
                  </div>
                </div>
              )}
              {chunk.blitz_answer && (
                <div>
                  <div
                    className="text-[10px] uppercase tracking-wider mb-0.5"
                    style={{ color: "var(--text-muted)" }}
                  >
                    Эталонный ответ
                  </div>
                  <div className="flex items-start justify-between gap-2 text-sm">
                    <span style={{ color: "var(--success)" }}>{chunk.blitz_answer}</span>
                    <CopyButton text={chunk.blitz_answer} />
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Question templates */}
          {chunk.question_templates.length > 0 && (
            <div>
              <Header label="📝 Заготовленные вопросы (question_templates)" accent="var(--accent)" />
              <ul className="mt-1.5 space-y-1">
                {chunk.question_templates.map((tmpl, i) => {
                  const text = typeof tmpl === "string" ? tmpl : tmpl?.text || "";
                  if (!text) return null;
                  return (
                    <li
                      key={i}
                      className="flex items-start justify-between gap-2 text-sm pl-3"
                      style={{ color: "var(--text-secondary)" }}
                    >
                      <span>
                        <span style={{ color: "var(--accent)" }}>{i + 1}. </span>
                        {text}
                        {typeof tmpl === "object" && tmpl.difficulty && (
                          <span
                            className="ml-2 text-[10px]"
                            style={{ color: "var(--text-muted)" }}
                          >
                            (D{tmpl.difficulty})
                          </span>
                        )}
                      </span>
                      <CopyButton text={text} />
                    </li>
                  );
                })}
              </ul>
            </div>
          )}

          {/* Follow-up questions */}
          {chunk.follow_up_questions.length > 0 && (
            <div>
              <Header label="↻ Углубляющие вопросы (follow_up)" accent="#60a5fa" />
              <ul className="mt-1.5 space-y-1">
                {chunk.follow_up_questions.map((q, i) => (
                  <li
                    key={i}
                    className="flex items-start justify-between gap-2 text-sm pl-3"
                    style={{ color: "var(--text-secondary)" }}
                  >
                    <span>
                      <span style={{ color: "#60a5fa" }}>{i + 1}. </span>
                      {q}
                    </span>
                    <CopyButton text={q} />
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Match keywords */}
          {chunk.match_keywords.length > 0 && (
            <div>
              <Header label="🔑 Ключевые слова (match_keywords)" accent="var(--text-muted)" />
              <div className="mt-1.5 flex flex-wrap gap-1.5 pl-3">
                {chunk.match_keywords.map((kw, i) => (
                  <span
                    key={i}
                    className="font-mono text-[11px] px-1.5 py-0.5 rounded"
                    style={{
                      background: "rgba(255,255,255,0.05)",
                      border: "1px solid rgba(255,255,255,0.08)",
                      color: "var(--text-secondary)",
                    }}
                  >
                    {kw}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Court case reference */}
          {chunk.court_case_reference && (
            <Section
              label="⚖ Судебная практика"
              content={chunk.court_case_reference}
              copyText={chunk.court_case_reference}
              accent="#a78bfa"
            />
          )}

          {/* Tags + ID */}
          <div className="flex items-center justify-between gap-2 pt-2 text-[10px] font-mono" style={{ color: "var(--text-muted)" }}>
            <span>id: {chunk.id.slice(0, 8)}…</span>
            {chunk.tags.length > 0 && (
              <span>теги: {chunk.tags.join(", ")}</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function Header({ label, accent }: { label: string; accent: string }) {
  return (
    <div
      className="font-pixel text-[11px] uppercase tracking-widest"
      style={{ color: accent }}
    >
      {label}
    </div>
  );
}

function Section({
  label,
  content,
  copyText,
  accent = "var(--text-muted)",
}: {
  label: string;
  content: string;
  copyText: string;
  accent?: string;
}) {
  return (
    <div>
      <div className="flex items-center justify-between gap-2">
        <Header label={label} accent={accent} />
        <CopyButton text={copyText} />
      </div>
      <div
        className="mt-1 text-sm leading-relaxed pl-3"
        style={{ color: "var(--text-primary)" }}
      >
        {content}
      </div>
    </div>
  );
}

export function KnowledgeBaseBrowser() {
  const [data, setData] = useState<BrowseResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [category, setCategory] = useState<string>("");
  const [search, setSearch] = useState<string>("");
  const [difficulty, setDifficulty] = useState<number | null>(null);
  const [offset, setOffset] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (category) params.set("category", category);
      if (search.trim()) params.set("search", search.trim());
      if (difficulty) params.set("difficulty", String(difficulty));
      params.set("limit", String(PAGE_SIZE));
      params.set("offset", String(offset));
      const resp = await api.get<BrowseResponse>(`/knowledge/rag/browse?${params}`);
      setData(resp);
    } catch (err) {
      logger.error("rag browse failed", err);
      setData({ chunks: [], total: 0, limit: PAGE_SIZE, offset: 0, by_category: {} });
    } finally {
      setLoading(false);
    }
  }, [category, search, difficulty, offset]);

  useEffect(() => {
    // Debounce search to avoid hammering the endpoint on every keystroke.
    const t = setTimeout(load, 300);
    return () => clearTimeout(t);
  }, [load]);

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0;
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  const categoryStats = useMemo(() => {
    if (!data) return [];
    return Object.entries(data.by_category).sort((a, b) => b[1] - a[1]);
  }, [data]);

  return (
    <div className="space-y-4">
      <div
        className="rounded-xl p-4"
        style={{
          background: "color-mix(in srgb, var(--accent) 8%, transparent)",
          border: "1px solid color-mix(in srgb, var(--accent) 25%, transparent)",
        }}
      >
        <div className="flex items-center gap-2 mb-2">
          <BookOpen size={16} style={{ color: "var(--accent)" }} />
          <div
            className="font-pixel text-sm uppercase tracking-widest"
            style={{ color: "var(--accent)" }}
          >
            База знаний ФЗ-127 (RAG)
          </div>
        </div>
        <p className="text-xs leading-relaxed" style={{ color: "var(--text-secondary)" }}>
          Полная база фактов по которой работает AI-судья. Каждый блок —
          один чанк: текст факта, статья, эталонный ответ, частые
          ошибки, блиц Q&A, заготовленные вопросы. Любой текст можно
          скопировать. Если AI принял неправильный ответ — найди
          здесь чем должен был ответить.
        </p>
      </div>

      {/* Filters */}
      <div className="space-y-2">
        <div
          className="flex items-center gap-2 px-3 py-2"
          style={{
            background: "var(--input-bg)",
            border: "1px solid var(--border-color)",
            borderRadius: 0,
          }}
        >
          <Search size={14} style={{ color: "var(--text-muted)" }} />
          <input
            type="text"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setOffset(0);
            }}
            placeholder="Поиск по факту / статье / блиц-вопросу…"
            className="flex-1 bg-transparent text-sm outline-none"
            style={{ color: "var(--text-primary)", fontFamily: "var(--font-mono, monospace)" }}
          />
        </div>

        <div className="flex flex-wrap gap-1.5">
          <button
            type="button"
            onClick={() => {
              setCategory("");
              setOffset(0);
            }}
            className="px-2.5 py-1 text-[11px] uppercase tracking-widest font-pixel"
            style={{
              background: !category ? "var(--accent)" : "var(--bg-panel)",
              color: !category ? "#fff" : "var(--text-muted)",
              border: `1px solid ${!category ? "var(--accent)" : "var(--border-color)"}`,
              borderRadius: 0,
            }}
          >
            все ({data?.total ?? 0})
          </button>
          {categoryStats.map(([cat, n]) => {
            const active = category === cat;
            return (
              <button
                key={cat}
                type="button"
                onClick={() => {
                  setCategory(active ? "" : cat);
                  setOffset(0);
                }}
                className="px-2.5 py-1 text-[11px] uppercase tracking-widest font-pixel"
                style={{
                  background: active ? "var(--accent)" : "var(--bg-panel)",
                  color: active ? "#fff" : "var(--text-secondary)",
                  border: `1px solid ${active ? "var(--accent)" : "var(--border-color)"}`,
                  borderRadius: 0,
                }}
              >
                {CATEGORY_LABELS[cat] ?? cat} ({n})
              </button>
            );
          })}
        </div>

        <div className="flex flex-wrap gap-1.5">
          <span
            className="font-pixel text-[10px] uppercase tracking-widest self-center mr-1"
            style={{ color: "var(--text-muted)" }}
          >
            ▸ сложность:
          </span>
          {[null, 1, 2, 3, 4, 5].map((d) => {
            const active = difficulty === d;
            const label = d === null ? "все" : `${d}/5`;
            return (
              <button
                key={String(d)}
                type="button"
                onClick={() => {
                  setDifficulty(d);
                  setOffset(0);
                }}
                className="px-2 py-0.5 text-[10px] uppercase tracking-widest font-pixel"
                style={{
                  background: active ? "var(--warning)" : "var(--bg-panel)",
                  color: active ? "#0b0b14" : "var(--text-muted)",
                  border: `1px solid ${active ? "var(--warning)" : "var(--border-color)"}`,
                  borderRadius: 0,
                }}
              >
                {label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Results */}
      {loading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 size={20} className="animate-spin" style={{ color: "var(--accent)" }} />
        </div>
      ) : !data || data.chunks.length === 0 ? (
        <div
          className="rounded-xl p-8 text-center"
          style={{
            background: "var(--bg-panel)",
            border: "1px solid var(--border-color)",
          }}
        >
          <AlertTriangle size={24} style={{ color: "var(--text-muted)" }} className="mx-auto mb-2" />
          <div className="text-sm" style={{ color: "var(--text-muted)" }}>
            По текущим фильтрам ничего не найдено.
          </div>
        </div>
      ) : (
        <>
          <div className="flex items-center justify-between text-xs" style={{ color: "var(--text-muted)" }}>
            <span>
              <Sparkles size={11} className="inline mr-1" style={{ color: "var(--accent)" }} />
              {data.total} чанков · показано {data.chunks.length}
            </span>
            {totalPages > 1 && (
              <span>
                стр. {currentPage} из {totalPages}
              </span>
            )}
          </div>

          <div className="space-y-2">
            {data.chunks.map((c) => (
              <ChunkCard key={c.id} chunk={c} />
            ))}
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2 pt-2">
              <button
                type="button"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                className="px-3 py-1.5 text-xs font-pixel uppercase tracking-widest disabled:opacity-40"
                style={{
                  background: "var(--bg-panel)",
                  border: "1px solid var(--border-color)",
                  borderRadius: 0,
                  color: "var(--text-secondary)",
                }}
              >
                ← назад
              </button>
              <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                {currentPage} / {totalPages}
              </span>
              <button
                type="button"
                disabled={currentPage >= totalPages}
                onClick={() => setOffset(offset + PAGE_SIZE)}
                className="px-3 py-1.5 text-xs font-pixel uppercase tracking-widest disabled:opacity-40"
                style={{
                  background: "var(--bg-panel)",
                  border: "1px solid var(--border-color)",
                  borderRadius: 0,
                  color: "var(--text-secondary)",
                }}
              >
                вперёд →
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
