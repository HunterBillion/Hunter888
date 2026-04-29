"use client";

/**
 * ScenariosEditor — TZ-3 §14.4 frontend constructor MVP.
 *
 * Replaces the placeholder that lived in MethodologyPanel since PR #47
 * (B2). What ships in this MVP (PR C4):
 *
 *   • Template list with status badge + draft_revision + "current
 *     published version" indicator. Operator sees at a glance which
 *     templates have unpublished drafts vs published vs no-version.
 *   • Per-row Publish action. Click → confirm modal → POST
 *     /rop/scenarios/{id}/publish with `expected_draft_revision`
 *     (the value rendered in the row). Translates the publisher's
 *     409/422 responses into a user-readable toast + (for 409) a
 *     refresh-and-republish prompt that re-fetches the list.
 *   • Per-row "View versions" disclosure: lists the last N published
 *     versions with their content_hash short prefix, status badge,
 *     and published_at timestamp. Read-only — historical sessions
 *     resolve through them via PR #52's runtime resolver.
 *
 * What's NOT in this MVP — explicit follow-up scope:
 *
 *   • In-place template editing (name / description / stages /
 *     archetype weights). The existing PUT /rop/scenarios/{id} now
 *     bumps draft_revision but doesn't have a UI here yet — methodologists
 *     today edit via the API directly. PR C4.1 will add the form.
 *   • Stages drag-and-drop reorder, traps picker, scoring modifier
 *     editor — TZ-3 §14.4 calls these out as part of "polish", not
 *     MVP. Same with the validation_report inline rendering.
 *   • Create-new-template wizard — covered by POST /rop/scenarios
 *     today; FE wizard lands in C4.2 after C4 is in prod for a week
 *     and the publish flow is proven.
 *
 * Why this scope: the load-bearing fix of TZ-3 (§7.3.1, removal of
 * auto-publish) needs an explicit Publish button in the UI BEFORE the
 * old in-place editor can be revived — otherwise methodologists will
 * "save" via the API thinking that publishes (it no longer does).
 * This MVP gives them a Publish action; the editor follows once the
 * UX of explicit publish is proven.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleDot,
  Loader2,
  RefreshCw,
  Send,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";

import { api, ApiError } from "@/lib/api";
import { logger } from "@/lib/logger";
import { DashboardSkeleton } from "@/components/ui/Skeleton";

// ── Types matching the rop.py response shape ───────────────────────────────

interface ScenarioListItem {
  id: string;
  title: string;
  description: string | null;
  scenario_code: string;
  group: string;
  who_calls: string;
  is_active: boolean;
  created_at: string | null;
  // C1 + C2 added these fields — list endpoint will expose them
  // post-deploy. Until then they're undefined and the UI degrades
  // gracefully (no badge / "—" display).
  status?: "draft" | "published" | "archived";
  draft_revision?: number;
  current_published_version_id?: string | null;
}

interface ScenarioVersion {
  id: string;
  version_number: number;
  status: "published" | "superseded" | "archived";
  content_hash: string;
  published_at: string | null;
}

interface PublishConflictDetail {
  code: "scenario_publish_conflict";
  message: string;
  expected: number;
  actual: number;
}

interface PublishValidationDetail {
  code: "scenario_publish_invalid";
  message: string;
  validation_report: {
    schema_version: number;
    has_errors: boolean;
    issues: Array<{
      code: string;
      severity: "error" | "warning";
      message: string;
      field: string | null;
    }>;
  };
}

// ── Component ──────────────────────────────────────────────────────────────

export function ScenariosEditor() {
  const [items, setItems] = useState<ScenarioListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [publishingId, setPublishingId] = useState<string | null>(null);

  const fetchList = useCallback(async () => {
    setLoading(true);
    try {
      const res: { items: ScenarioListItem[]; total: number } = await api.get(
        "/rop/scenarios?page_size=200",
      );
      setItems(res.items ?? []);
      setError(null);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Не удалось загрузить сценарии";
      logger.error("[ScenariosEditor] list failed:", err);
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchList();
  }, [fetchList]);

  const handlePublish = useCallback(
    async (item: ScenarioListItem) => {
      const expected = item.draft_revision ?? 0;
      const ok = window.confirm(
        `Опубликовать «${item.title}»?\n\n` +
          `Текущая ревизия черновика: ${expected}.\n` +
          `Будет создана новая опубликованная версия. Историческая ` +
          `неприкосновенность гарантирована: предыдущая версия будет ` +
          `помечена как superseded, но данные сохранятся.`,
      );
      if (!ok) return;

      setPublishingId(item.id);
      try {
        const res = await api.post<{
          version_id: string;
          version_number: number;
          content_hash: string;
          superseded_version_id: string | null;
        }>(`/rop/scenarios/${item.id}/publish`, {
          expected_draft_revision: expected,
        });
        toast.success(
          `Сценарий опубликован — версия №${res.version_number}` +
            (res.superseded_version_id ? " (предыдущая → superseded)" : ""),
        );
        await fetchList();
      } catch (err) {
        if (err instanceof ApiError) {
          if (err.status === 409) {
            const det = err.detail as unknown as PublishConflictDetail | undefined;
            toast.error(
              `Конфликт публикации: ожидалась ревизия ${det?.expected ?? "?"}, ` +
                `актуальная ${det?.actual ?? "?"}. Шаблон отредактирован ` +
                `другим пользователем — обновляем список.`,
              { duration: 8000 },
            );
            await fetchList();
            return;
          }
          if (err.status === 422) {
            const det = err.detail as unknown as PublishValidationDetail | undefined;
            const issues = det?.validation_report?.issues ?? [];
            const errorCount = issues.filter((i) => i.severity === "error").length;
            toast.error(
              `Сценарий не прошёл валидацию (${errorCount} ошибок). ` +
                `Первая: ${issues[0]?.message ?? "—"}`,
              { duration: 12000 },
            );
            return;
          }
        }
        const msg = err instanceof Error ? err.message : "Ошибка публикации";
        toast.error(msg);
      } finally {
        setPublishingId(null);
      }
    },
    [fetchList],
  );

  const counts = useMemo(() => {
    const c = { total: items.length, published: 0, draft: 0, archived: 0, no_version: 0 };
    for (const i of items) {
      if (i.status === "draft") c.draft++;
      else if (i.status === "archived") c.archived++;
      else c.published++;
      if (!i.current_published_version_id) c.no_version++;
    }
    return c;
  }, [items]);

  if (loading && items.length === 0) return <DashboardSkeleton />;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="font-display text-sm tracking-wider" style={{ color: "var(--text-secondary)" }}>
            СЦЕНАРИИ
          </h3>
          <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
            Всего {counts.total} · опубликовано {counts.published} · черновиков {counts.draft}
            {counts.no_version > 0 && (
              <>
                {" · "}
                <span style={{ color: "var(--warning)" }}>
                  {counts.no_version} без published версии
                </span>
              </>
            )}
          </p>
        </div>
        <button
          onClick={fetchList}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium disabled:opacity-50"
          style={{ background: "var(--accent-muted)", color: "var(--accent)" }}
        >
          <RefreshCw size={11} className={loading ? "animate-spin" : ""} />
          Обновить
        </button>
      </div>

      {error && (
        <div
          className="rounded-lg p-3 flex items-center gap-2 text-sm"
          style={{ background: "var(--danger-muted)", color: "var(--danger)" }}
        >
          <XCircle size={14} />
          {error}
        </div>
      )}

      <div className="space-y-2">
        {items.map((item) => (
          <ScenarioRow
            key={item.id}
            item={item}
            expanded={expandedId === item.id}
            publishing={publishingId === item.id}
            onToggle={() => setExpandedId(expandedId === item.id ? null : item.id)}
            onPublish={() => handlePublish(item)}
          />
        ))}
        {!items.length && !loading && (
          <div
            className="glass-panel rounded-xl p-8 text-center text-sm italic"
            style={{ color: "var(--text-muted)" }}
          >
            Сценариев пока нет. Создайте через API или дождитесь конструктора (C4.1).
          </div>
        )}
      </div>

      <p className="text-xs italic" style={{ color: "var(--text-muted)" }}>
        Эта вкладка — MVP конструктора (TZ-3 §14.4). Сейчас доступны: список,
        Publish, история версий. Inline-редактор полей (название/описание/этапы)
        придёт в C4.1 после того, как explicit Publish flow проявит себя на пилоте.
      </p>
    </div>
  );
}

// ── Row ─────────────────────────────────────────────────────────────────────

function ScenarioRow({
  item,
  expanded,
  publishing,
  onToggle,
  onPublish,
}: {
  item: ScenarioListItem;
  expanded: boolean;
  publishing: boolean;
  onToggle: () => void;
  onPublish: () => void;
}) {
  const status = item.status ?? "published";
  const hasVersion = Boolean(item.current_published_version_id);
  return (
    <div
      className="rounded-xl overflow-hidden"
      style={{
        background: "var(--glass-bg)",
        border: "1px solid var(--glass-border)",
      }}
    >
      <div className="flex items-center gap-3 p-3">
        <button
          onClick={onToggle}
          className="p-1 rounded hover:bg-white/5"
          aria-label="Показать или скрыть версии"
        >
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-medium text-sm truncate" style={{ color: "var(--text-primary)" }}>
              {item.title}
            </span>
            <code className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
              {item.scenario_code}
            </code>
            <StatusBadge status={status} />
            {!hasVersion && (
              <span
                className="rounded px-1.5 py-0.5 text-xs font-medium inline-flex items-center gap-1"
                style={{ background: "var(--warning-muted, rgba(234,179,8,0.15))", color: "var(--warning)" }}
                title="У шаблона ещё нет опубликованной версии — runtime использует legacy fallback"
              >
                <AlertTriangle size={10} />
                no v1
              </span>
            )}
          </div>
          {item.description && (
            <p className="text-xs mt-0.5 line-clamp-1" style={{ color: "var(--text-muted)" }}>
              {item.description}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2 text-xs" style={{ color: "var(--text-muted)" }}>
          <span title="Optimistic-concurrency cursor">
            rev {item.draft_revision ?? "—"}
          </span>
        </div>
        <button
          onClick={onPublish}
          disabled={publishing}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold disabled:opacity-50"
          style={{
            background: "var(--accent-muted)",
            color: "var(--accent)",
            border: "1px solid var(--accent)",
          }}
        >
          {publishing ? <Loader2 size={11} className="animate-spin" /> : <Send size={11} />}
          Publish
        </button>
      </div>

      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            style={{ overflow: "hidden" }}
          >
            <ScenarioVersions templateId={item.id} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ── Version disclosure ─────────────────────────────────────────────────────

function ScenarioVersions({ templateId }: { templateId: string }) {
  const [versions, setVersions] = useState<ScenarioVersion[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        // Endpoint TBD by C4.1; for now we surface a friendly note.
        // The version list is exposed in admin Client Domain panel today;
        // this preview avoids guessing at an endpoint that doesn't exist.
        const res: { versions: ScenarioVersion[] } = await api.get(
          `/rop/scenarios/${templateId}/versions?limit=10`,
        );
        if (!cancelled) setVersions(res.versions ?? []);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          // Endpoint not built yet — degrade gracefully
          setVersions([]);
          setError(
            "Список версий по этому шаблону доступен в админ-панели Client Domain. " +
              "Inline-список появится в C4.1.",
          );
        } else {
          const msg = err instanceof Error ? err.message : "Ошибка загрузки версий";
          setError(msg);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [templateId]);

  if (loading)
    return (
      <div className="px-12 py-3 flex items-center gap-2 text-xs" style={{ color: "var(--text-muted)" }}>
        <Loader2 size={11} className="animate-spin" />
        Загружаю версии...
      </div>
    );

  if (error || !versions || versions.length === 0)
    return (
      <div className="px-12 pb-3 text-xs italic" style={{ color: "var(--text-muted)" }}>
        {error ?? "Версий ещё нет. Нажмите Publish, чтобы создать v1."}
      </div>
    );

  return (
    <div className="px-12 pb-3 space-y-1.5">
      {versions.map((v) => (
        <div
          key={v.id}
          className="flex items-center gap-3 text-xs"
          style={{ color: "var(--text-secondary)" }}
        >
          <span className="font-mono w-12">v{v.version_number}</span>
          <StatusBadge status={v.status} small />
          <code className="font-mono" style={{ color: "var(--text-muted)" }}>
            {v.content_hash.slice(0, 8)}
          </code>
          <span style={{ color: "var(--text-muted)" }}>
            {v.published_at ? new Date(v.published_at).toLocaleString("ru-RU") : "—"}
          </span>
        </div>
      ))}
    </div>
  );
}

// ── Status badge ───────────────────────────────────────────────────────────

function StatusBadge({
  status,
  small = false,
}: {
  status: "draft" | "published" | "archived" | "superseded";
  small?: boolean;
}) {
  const cfg = {
    draft: { color: "var(--warning)", label: "draft", icon: CircleDot },
    published: { color: "var(--success)", label: "published", icon: CheckCircle2 },
    superseded: { color: "var(--text-muted)", label: "superseded", icon: CircleDot },
    archived: { color: "var(--text-muted)", label: "archived", icon: CircleDot },
  }[status];
  const Icon = cfg.icon;
  return (
    <span
      className={`rounded px-1.5 py-0.5 font-medium inline-flex items-center gap-1 ${small ? "text-[10px]" : "text-xs"}`}
      style={{
        background: `color-mix(in srgb, ${cfg.color} 12%, transparent)`,
        color: cfg.color,
      }}
    >
      <Icon size={small ? 9 : 10} />
      {cfg.label}
    </span>
  );
}
