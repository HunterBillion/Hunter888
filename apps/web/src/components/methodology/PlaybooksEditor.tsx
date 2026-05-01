"use client";

/**
 * PlaybooksEditor — TZ-8 PR-C UI for the per-team methodology layer.
 *
 * Lands on the /dashboard?tab=methodology&sub=playbooks panel and gives
 * ROPs a CRUD surface over ``methodology_chunks``: list with filters,
 * inline create/edit form, status chip with one-click governance
 * transitions (actual / disputed / outdated), and an "indexing…" pill
 * for chunks whose embedding hasn't been computed yet.
 *
 * Why a single component vs. the pattern used by WikiDashboard's
 * three sub-views (list / detail / log)? Methodology has a much
 * smaller per-row surface than wiki — title + body + tags + status
 * fit comfortably in one screen. Splitting into routes would just
 * add navigation friction for a 3-click create-edit-publish flow.
 *
 * Server contract: ``app/api/methodology.py``. Authz matrix matches
 * ``check_methodology_team_access`` — ROP authors for own team,
 * manager is read-only, admin sees every team. The UI gates the
 * action buttons accordingly so the user never sees a useless
 * "Save" that 403s.
 */

import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Plus, Pencil, Trash, Sparkle } from "@phosphor-icons/react";
import {
  type MethodologyChunk,
  type MethodologyKind,
  type KnowledgeStatus,
  type MethodologyChunkCreate,
  type MethodologyChunkPatch,
  METHODOLOGY_KINDS,
  KIND_LABEL_RU,
  KNOWLEDGE_STATUSES,
  STATUS_LABEL_RU,
  STATUS_CLASSES,
  TITLE_MAX,
  BODY_MAX,
  BODY_MIN,
  LIST_FIELD_MAX,
  listMethodology,
  createMethodology,
  updateMethodology,
  deleteMethodology,
  patchMethodologyStatus,
  validateCreate,
  isStatusTransitionAllowed,
} from "@/lib/api/methodology";

// ── StatusChip ──────────────────────────────────────────────────────────────


function StatusChip({ status }: { status: KnowledgeStatus }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_CLASSES[status]}`}
      title={`Статус: ${STATUS_LABEL_RU[status]}`}
    >
      {STATUS_LABEL_RU[status]}
    </span>
  );
}


// ── Empty state ─────────────────────────────────────────────────────────────


function EmptyState({ onAdd, canAdd }: { onAdd: () => void; canAdd: boolean }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border-2 border-dashed border-gray-300 p-12 text-center">
      <Sparkle size={32} className="text-gray-400 mb-3" />
      <h3 className="text-lg font-semibold text-gray-700">
        Методология пока пуста
      </h3>
      <p className="mt-2 max-w-md text-sm text-gray-500">
        Запиши лучшие практики команды: скрипт открытия, обработку
        возражений, тон под клиента. AI-коуч и судья будут учитывать
        их в каждой следующей сессии.
      </p>
      {canAdd && (
        <button
          onClick={onAdd}
          className="mt-6 inline-flex items-center gap-2 rounded-md bg-violet-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-violet-700"
        >
          <Plus size={16} /> Создать первый playbook
        </button>
      )}
    </div>
  );
}


// ── Editor (modal) ──────────────────────────────────────────────────────────


interface EditorProps {
  /** When provided — edit mode; when null — create mode. */
  chunk: MethodologyChunk | null;
  onClose: () => void;
  onSaved: (chunk: MethodologyChunk) => void;
}

function Editor({ chunk, onClose, onSaved }: EditorProps) {
  const [title, setTitle] = useState(chunk?.title ?? "");
  const [body, setBody] = useState(chunk?.body ?? "");
  const [kind, setKind] = useState<MethodologyKind>(
    chunk?.kind ?? "opener",
  );
  const [tagsRaw, setTagsRaw] = useState(
    chunk ? (chunk.tags ?? []).join(", ") : "",
  );
  const [keywordsRaw, setKeywordsRaw] = useState(
    chunk ? (chunk.keywords ?? []).join(", ") : "",
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const tags = useMemo(
    () =>
      tagsRaw
        .split(",")
        .map((t) => t.trim())
        .filter((t) => t.length > 0),
    [tagsRaw],
  );
  const keywords = useMemo(
    () =>
      keywordsRaw
        .split(",")
        .map((k) => k.trim())
        .filter((k) => k.length > 0),
    [keywordsRaw],
  );

  const issues = useMemo(
    () =>
      validateCreate({
        title,
        body,
        kind,
        tags,
        keywords,
      }),
    [title, body, kind, tags, keywords],
  );

  const handleSave = async () => {
    setBusy(true);
    setError(null);
    try {
      let saved: MethodologyChunk;
      if (chunk) {
        const patch: MethodologyChunkPatch = {
          title,
          body,
          kind,
          tags,
          keywords,
        };
        saved = await updateMethodology(chunk.id, patch);
      } else {
        const payload: MethodologyChunkCreate = {
          title,
          body,
          kind,
          tags,
          keywords,
        };
        saved = await createMethodology(payload);
      }
      onSaved(saved);
    } catch (e: any) {
      // ``api`` helper bubbles the server's detail string up here.
      // 409 from UNIQUE collision is the most common — show it as
      // an inline error rather than a global toast.
      const detail =
        e?.response?.data?.detail ?? e?.message ?? "Не удалось сохранить";
      setError(typeof detail === "string" ? detail : JSON.stringify(detail));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        transition={{ duration: 0.15 }}
        className="w-full max-w-2xl rounded-lg bg-white p-6 shadow-xl"
      >
        <h3 className="mb-4 text-lg font-semibold">
          {chunk ? "Редактирование playbook" : "Новый playbook"}
        </h3>

        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Заголовок
            </label>
            <input
              type="text"
              value={title}
              maxLength={TITLE_MAX}
              onChange={(e) => setTitle(e.target.value)}
              className="block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500"
              placeholder="Например: Открытие звонка после скан-кода"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Категория
            </label>
            <select
              value={kind}
              onChange={(e) => setKind(e.target.value as MethodologyKind)}
              className="block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500"
            >
              {METHODOLOGY_KINDS.map((k) => (
                <option key={k} value={k}>
                  {KIND_LABEL_RU[k]}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Содержание (markdown)
            </label>
            <textarea
              value={body}
              maxLength={BODY_MAX}
              onChange={(e) => setBody(e.target.value)}
              rows={10}
              className="block w-full rounded-md border border-gray-300 px-3 py-2 font-mono text-sm focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500"
              placeholder="1. Здороваешься, представляешься.&#10;2. ..."
            />
            <div className="mt-1 flex justify-between text-xs text-gray-500">
              <span>
                {body.length} / {BODY_MAX} символов (мин. {BODY_MIN})
              </span>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Теги (через запятую)
              </label>
              <input
                type="text"
                value={tagsRaw}
                onChange={(e) => setTagsRaw(e.target.value)}
                className="block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500"
                placeholder="скан-код, тёплый лид"
              />
              <p className="mt-1 text-xs text-gray-500">
                {tags.length} / {LIST_FIELD_MAX}
              </p>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Ключевые слова для RAG
              </label>
              <input
                type="text"
                value={keywordsRaw}
                onChange={(e) => setKeywordsRaw(e.target.value)}
                className="block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500"
                placeholder="скан, QR, лид, первый звонок"
              />
              <p className="mt-1 text-xs text-gray-500">
                {keywords.length} / {LIST_FIELD_MAX}
              </p>
            </div>
          </div>
        </div>

        {issues.length > 0 && (
          <div className="mt-3 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800">
            <p className="font-medium">Проверь форму:</p>
            <ul className="mt-1 list-disc space-y-0.5 pl-5">
              {issues.map((iss) => (
                <li key={iss}>{iss}</li>
              ))}
            </ul>
          </div>
        )}

        {error && (
          <div className="mt-3 rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-800">
            {error}
          </div>
        )}

        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onClose}
            disabled={busy}
            className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50 disabled:opacity-50"
          >
            Отмена
          </button>
          <button
            onClick={handleSave}
            disabled={busy || issues.length > 0}
            className="rounded-md border border-transparent bg-violet-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-violet-700 disabled:opacity-50"
          >
            {busy ? "Сохраняю…" : chunk ? "Сохранить" : "Создать"}
          </button>
        </div>
      </motion.div>
    </div>
  );
}


// ── Status menu — one-click governance transitions ──────────────────────────


function StatusMenu({
  chunk,
  onTransition,
}: {
  chunk: MethodologyChunk;
  onTransition: (next: KnowledgeStatus) => void;
}) {
  const [open, setOpen] = useState(false);
  const allowed = KNOWLEDGE_STATUSES.filter((s) =>
    isStatusTransitionAllowed(chunk.knowledge_status, s),
  );
  if (allowed.length === 0) return null;
  return (
    <div className="relative">
      <button
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
        }}
        className="rounded border border-gray-300 px-2 py-0.5 text-xs text-gray-600 hover:bg-gray-50"
      >
        Сменить статус
      </button>
      {open && (
        <div className="absolute right-0 z-10 mt-1 w-44 rounded-md border border-gray-200 bg-white shadow-lg">
          {allowed.map((s) => (
            <button
              key={s}
              onClick={(e) => {
                e.stopPropagation();
                setOpen(false);
                onTransition(s);
              }}
              className="block w-full px-3 py-2 text-left text-sm hover:bg-gray-50"
            >
              <span
                className={`inline-block rounded-full px-2 py-0.5 text-xs ${STATUS_CLASSES[s]}`}
              >
                {STATUS_LABEL_RU[s]}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}


// ── Main panel ──────────────────────────────────────────────────────────────


interface PlaybooksEditorProps {
  /** Whether the caller can author rows (true for ROP/admin). */
  canAuthor: boolean;
}

export function PlaybooksEditor({ canAuthor }: PlaybooksEditorProps) {
  const [items, setItems] = useState<MethodologyChunk[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<MethodologyChunk | null>(null);
  const [creating, setCreating] = useState(false);

  // Filters
  const [kindFilter, setKindFilter] = useState<MethodologyKind | "all">("all");
  const [statusFilter, setStatusFilter] =
    useState<KnowledgeStatus | "all">("all");
  const [search, setSearch] = useState("");

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      const out = await listMethodology(
        statusFilter === "all"
          ? kindFilter === "all"
            ? {}
            : { kind: kindFilter }
          : { status: statusFilter, ...(kindFilter !== "all" && { kind: kindFilter }) },
      );
      setItems(out.items);
    } catch (e: any) {
      setError(
        e?.response?.data?.detail ??
          e?.message ??
          "Не удалось загрузить список",
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kindFilter, statusFilter]);

  // Client-side search across the already-fetched items so a slow
  // typist isn't hammering the API per keystroke.
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return items;
    return items.filter(
      (c) =>
        c.title.toLowerCase().includes(q) ||
        c.body.toLowerCase().includes(q) ||
        (c.tags ?? []).some((t) => t.toLowerCase().includes(q)),
    );
  }, [items, search]);

  const handleSaved = async (saved: MethodologyChunk) => {
    setEditing(null);
    setCreating(false);
    // Refresh from server so the indexing-pending pill reflects
    // the truth (the row may already be embedded by the time
    // this returns, or may still be enqueued).
    await refresh();
  };

  const handleDelete = async (chunk: MethodologyChunk) => {
    if (
      !window.confirm(
        `Удалить «${chunk.title}»? Лучше пометить «Устарело» — это сохранит историю.`,
      )
    ) {
      return;
    }
    try {
      await deleteMethodology(chunk.id);
      setItems((prev) => prev.filter((c) => c.id !== chunk.id));
    } catch (e: any) {
      window.alert(
        e?.response?.data?.detail ??
          e?.message ??
          "Не удалось удалить",
      );
    }
  };

  const handleStatusTransition = async (
    chunk: MethodologyChunk,
    next: KnowledgeStatus,
  ) => {
    let note: string | null = null;
    if (next === "disputed" || next === "outdated") {
      note = window.prompt(
        `Объясни, почему «${STATUS_LABEL_RU[next]}». Это увидят будущие ревьюеры.`,
      );
      if (!note || !note.trim()) return; // user cancelled
    }
    try {
      const updated = await patchMethodologyStatus(chunk.id, {
        status: next,
        note,
      });
      setItems((prev) =>
        prev.map((c) => (c.id === updated.id ? updated : c)),
      );
    } catch (e: any) {
      window.alert(
        e?.response?.data?.detail ??
          e?.message ??
          "Не удалось сменить статус",
      );
    }
  };

  if (loading) {
    return (
      <div className="rounded-lg border border-gray-200 p-8 text-center text-sm text-gray-500">
        Загрузка методологии команды…
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-800">
        {error}
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <>
        <EmptyState onAdd={() => setCreating(true)} canAdd={canAuthor} />
        <AnimatePresence>
          {creating && (
            <Editor
              chunk={null}
              onClose={() => setCreating(false)}
              onSaved={handleSaved}
            />
          )}
        </AnimatePresence>
      </>
    );
  }

  return (
    <div className="space-y-4">
      {/* Filters bar */}
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Поиск по заголовку / содержанию / тегам…"
          className="min-w-[220px] flex-1 rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500"
        />
        <select
          value={kindFilter}
          onChange={(e) =>
            setKindFilter(e.target.value as MethodologyKind | "all")
          }
          className="rounded-md border border-gray-300 px-3 py-1.5 text-sm"
        >
          <option value="all">Все типы</option>
          {METHODOLOGY_KINDS.map((k) => (
            <option key={k} value={k}>
              {KIND_LABEL_RU[k]}
            </option>
          ))}
        </select>
        <select
          value={statusFilter}
          onChange={(e) =>
            setStatusFilter(e.target.value as KnowledgeStatus | "all")
          }
          className="rounded-md border border-gray-300 px-3 py-1.5 text-sm"
        >
          <option value="all">Все статусы</option>
          {KNOWLEDGE_STATUSES.map((s) => (
            <option key={s} value={s}>
              {STATUS_LABEL_RU[s]}
            </option>
          ))}
        </select>
        {canAuthor && (
          <button
            onClick={() => setCreating(true)}
            className="ml-auto inline-flex items-center gap-1 rounded-md bg-violet-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-violet-700"
          >
            <Plus size={16} /> Создать
          </button>
        )}
      </div>

      {/* List */}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        {filtered.map((chunk) => (
          <div
            key={chunk.id}
            className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm transition hover:shadow-md"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <h4 className="truncate text-base font-semibold text-gray-800">
                    {chunk.title}
                  </h4>
                  <StatusChip status={chunk.knowledge_status} />
                </div>
                <p className="mt-0.5 text-xs uppercase tracking-wide text-gray-500">
                  {KIND_LABEL_RU[chunk.kind]}
                  {chunk.embedding_pending && (
                    <span className="ml-2 inline-flex items-center gap-1 rounded-full bg-blue-50 px-2 py-0.5 text-[10px] text-blue-700">
                      Индексация…
                    </span>
                  )}
                </p>
              </div>
              {canAuthor && (
                <div className="flex shrink-0 items-center gap-1">
                  <button
                    onClick={() => setEditing(chunk)}
                    className="rounded p-1 text-gray-500 hover:bg-gray-100"
                    title="Редактировать"
                  >
                    <Pencil size={16} />
                  </button>
                  <button
                    onClick={() => handleDelete(chunk)}
                    className="rounded p-1 text-gray-500 hover:bg-red-50 hover:text-red-600"
                    title="Удалить (лучше пометить устаревшим)"
                  >
                    <Trash size={16} />
                  </button>
                </div>
              )}
            </div>

            <p className="mt-2 line-clamp-3 text-sm text-gray-600 whitespace-pre-wrap">
              {chunk.body}
            </p>

            {chunk.tags.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {chunk.tags.map((t) => (
                  <span
                    key={t}
                    className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-700"
                  >
                    #{t}
                  </span>
                ))}
              </div>
            )}

            {canAuthor && (
              <div className="mt-3 flex items-center justify-between border-t border-gray-100 pt-2 text-xs text-gray-500">
                <span>v{chunk.version}</span>
                <StatusMenu
                  chunk={chunk}
                  onTransition={(next) => handleStatusTransition(chunk, next)}
                />
              </div>
            )}
          </div>
        ))}
      </div>

      {filtered.length === 0 && (
        <p className="rounded-lg border border-dashed border-gray-300 p-8 text-center text-sm text-gray-500">
          По текущим фильтрам ничего не найдено.
        </p>
      )}

      <AnimatePresence>
        {(editing || creating) && (
          <Editor
            chunk={editing}
            onClose={() => {
              setEditing(null);
              setCreating(false);
            }}
            onSaved={handleSaved}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
