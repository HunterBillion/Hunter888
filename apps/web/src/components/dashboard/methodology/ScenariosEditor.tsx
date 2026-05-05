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
  Upload,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";

import { api, ApiError } from "@/lib/api";
import { logger } from "@/lib/logger";
import { DashboardSkeleton } from "@/components/ui/Skeleton";
import { PixelInfoButton } from "@/components/ui/PixelInfoButton";
import { ImportWizard } from "@/components/methodology/ImportWizard";
import { ImportHistory } from "@/components/methodology/ImportHistory";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { formatDateTimeFull } from "@/lib/utils";

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
  const [importOpen, setImportOpen] = useState(false);
  const [importRefreshKey, setImportRefreshKey] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [publishingId, setPublishingId] = useState<string | null>(null);
  const [pendingPublish, setPendingPublish] = useState<ScenarioListItem | null>(null);

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
      // Show the confirmation modal — actual publish runs in confirmPublish.
      setPendingPublish(item);
    },
    [],
  );

  const confirmPublish = useCallback(
    async (item: ScenarioListItem) => {
      const expected = item.draft_revision ?? 0;
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
            // Stale draft revision — close so the next click goes through
            // the (now-refreshed) confirmation flow instead of replaying
            // the failed expected_draft_revision.
            setPendingPublish(null);
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
            // Validation failure — the user has to fix the scenario
            // before re-publishing; keeping the modal open would just
            // replay the same 422.
            setPendingPublish(null);
            return;
          }
        }
        // Transient errors (5xx, network) — keep the modal open so the
        // user can hit «Опубликовать» again without re-finding the row.
        const msg = err instanceof Error ? err.message : "Ошибка публикации";
        toast.error(msg);
        return;
      } finally {
        setPublishingId(null);
      }
      // Success path — only here do we close the modal.
      setPendingPublish(null);
    },
    [fetchList],
  );

  const counts = useMemo(() => {
    // `status` is optional in older list payloads (will be filled in by
    // backend post-deploy). Until then, items without a status are
    // counted as `unknown` — folding them into `published` would lie
    // about the published count.
    const c = { total: items.length, published: 0, draft: 0, archived: 0, unknown: 0, no_version: 0 };
    for (const i of items) {
      if (i.status === "draft") c.draft++;
      else if (i.status === "archived") c.archived++;
      else if (i.status === "published") c.published++;
      else c.unknown++;
      if (!i.current_published_version_id) c.no_version++;
    }
    return c;
  }, [items]);

  if (loading && items.length === 0) return <DashboardSkeleton />;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-start gap-2">
          <div>
            <h3 className="font-display text-sm tracking-wider" style={{ color: "var(--text-secondary)" }}>
              СЦЕНАРИИ
            </h3>
            <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
              Всего {counts.total} · опубликовано {counts.published} · черновиков {counts.draft}
              {counts.unknown > 0 && (
                <>
                  {" · "}
                  <span title="Список ещё не отдаёт поле status — подсчёт неполный">
                    {counts.unknown} без статуса
                  </span>
                </>
              )}
              {counts.no_version > 0 && (
                <>
                  {" · "}
                  <span style={{ color: "var(--warning)" }}>
                    {counts.no_version} не опубликовано
                  </span>
                </>
              )}
            </p>
          </div>
          <PixelInfoButton
            title="Сценарии"
            sections={[
              { icon: CircleDot, label: "Шаблон сценария", text: "Базовая «карточка»: название, описание, этапы. Менеджеры видят только опубликованные шаблоны." },
              { icon: Send, label: "Версии (immutable)", text: "Каждое нажатие «Опубликовать» создаёт НОВУЮ версию. Старые версии остаются — открытые сейчас сессии работают на той версии, на которой стартовали." },
              { icon: ChevronDown, label: "Зачем версии", text: "Раньше правка шаблона прямо влияла на идущие звонки → менеджер посередине разговора видел изменённый шаг 4. Теперь правки сидят в draft до явной публикации." },
              { icon: AlertTriangle, label: "Без published версии", text: "Шаблон есть, но менеджеру его не дать (ничего не опубликовано). Жёлтое предупреждение в счётчике сверху." },
              { icon: CheckCircle2, label: "Что доступно", text: "Список + Публикация + просмотр истории версий. Inline-редактор полей появится позже." },
            ]}
            footer="Совет: после Publish обновите страницу у менеджеров — runtime-резолвер выберет новую версию для НОВЫХ сессий, текущие закончатся на старой."
          />
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setImportOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium"
            style={{ background: "var(--accent-muted)", color: "var(--accent)" }}
            title="Загрузить памятку или скрипт — платформа предложит черновик сценария."
          >
            📤 Импорт
          </button>
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
      </div>
      <ImportWizard
        open={importOpen}
        onClose={() => setImportOpen(false)}
        presetRouteType="scenario"
        onApproved={() => {
          setImportRefreshKey((k) => k + 1);
          fetchList();
        }}
      />
      <ImportHistory routeType="scenario" refreshKey={importRefreshKey} />

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
            className="glass-panel rounded-xl p-8 text-center text-sm"
            style={{ color: "var(--text-muted)" }}
          >
            <p className="mb-3">Сценариев пока нет.</p>
            <button
              type="button"
              onClick={() => setImportOpen(true)}
              className="inline-flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium"
              style={{ background: "var(--accent-muted)", color: "var(--accent)" }}
            >
              <Upload size={14} /> Импортировать первый сценарий
            </button>
          </div>
        )}
      </div>

      <p className="text-xs" style={{ color: "var(--text-muted)" }}>
        Редактирование полей внутри списка скоро появится. Пока используйте
        импорт для добавления новых сценариев.
      </p>

      <ConfirmDialog
        open={pendingPublish !== null}
        onOpenChange={(open) => { if (!open && publishingId === null) setPendingPublish(null); }}
        title="Опубликовать сценарий?"
        description={
          <div className="space-y-2">
            <p>
              Шаблон <strong>«{pendingPublish?.title ?? ""}»</strong> станет
              активным для всех будущих тренировок команды. Текущие сессии
              продолжат идти на старой версии и завершатся как обычно.
            </p>
            <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
              Предыдущая опубликованная версия будет помечена «superseded» —
              данные сохранятся, история не теряется.
            </p>
          </div>
        }
        confirmLabel="Опубликовать"
        busy={publishingId !== null}
        onConfirm={() => { if (pendingPublish) confirmPublish(pendingPublish); }}
      />
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
                title="Шаблон ещё ни разу не опубликован — менеджеры его не увидят"
              >
                <AlertTriangle size={10} />
                не опубликован
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
          <span title="Номер черновой ревизии. Растёт при каждой правке.">
            черновик № {item.draft_revision ?? "—"}
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
        // Versions endpoint is not yet exposed in the public API. The
        // canonical version list lives in the Client Domain admin panel;
        // this card surfaces a graceful 404-fallback hint until the
        // inline preview ships. Avoid leaking sprint codenames into UI.
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
            "История версий пока недоступна — появится в одной из ближайших итераций.",
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
            {v.published_at ? formatDateTimeFull(v.published_at) : "—"}
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
