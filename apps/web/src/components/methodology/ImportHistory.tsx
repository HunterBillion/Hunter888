"use client";

/**
 * TZ-5 PR-2 — collapsible "История импортов" section embedded in each
 * panel that supports import. Filtered by `routeType` so each panel
 * shows only its own branch of imports.
 */

import { useEffect, useState } from "react";
import {
  type ImportDraft,
  type ImportRouteType,
  STATUS_LABELS_RU,
  listImports,
} from "@/lib/api/imports";

interface Props {
  routeType: ImportRouteType;
  /** Manually trigger a refetch (e.g. after the wizard approves a draft). */
  refreshKey?: number;
}

export function ImportHistory({ routeType, refreshKey = 0 }: Props) {
  const [open, setOpen] = useState(false);
  const [drafts, setDrafts] = useState<ImportDraft[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    listImports({ route_type: routeType, page_size: 20 })
      .then((res) => {
        if (!cancelled) setDrafts(res.drafts);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, routeType, refreshKey]);

  return (
    <details
      className="rounded-lg border border-white/10 bg-white/5 mt-4"
      open={open}
      onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}
    >
      <summary className="cursor-pointer px-4 py-2 text-sm select-none">
        История импортов
        {drafts.length > 0 && (
          <span className="ml-2 opacity-60">({drafts.length})</span>
        )}
      </summary>
      <div className="px-4 py-3">
        {loading && <p className="text-sm opacity-60">Загрузка…</p>}
        {error && (
          <p className="text-sm text-red-400">Не удалось загрузить: {error}</p>
        )}
        {!loading && !error && drafts.length === 0 && (
          <p className="text-sm opacity-60">
            Импортов пока нет. Нажмите «Импорт» чтобы загрузить первый файл.
          </p>
        )}
        {!loading && drafts.length > 0 && (
          <ul className="space-y-2">
            {drafts.map((d) => (
              <li
                key={d.id}
                className="flex items-start justify-between gap-3 text-sm py-2 border-b border-white/5 last:border-0"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">
                    {d.attachment_filename || "(без имени)"}
                  </p>
                  <p className="text-xs opacity-60 mt-0.5">
                    {new Date(d.created_at).toLocaleString("ru")} · уверенность{" "}
                    {(d.confidence * 100).toFixed(0)}%
                    {d.original_confidence !== null &&
                      d.original_confidence !== d.confidence && (
                        <span className="ml-1 text-amber-400">
                          (LLM: {(d.original_confidence * 100).toFixed(0)}%)
                        </span>
                      )}
                  </p>
                  {d.error_message && (
                    <p className="text-xs text-red-400 mt-1 truncate">
                      {d.error_message}
                    </p>
                  )}
                </div>
                <span
                  className="text-xs px-2 py-1 rounded shrink-0"
                  style={{
                    backgroundColor:
                      d.status === "ready" || d.status === "edited"
                        ? "rgba(34,197,94,0.2)"
                        : d.status === "converted"
                        ? "rgba(120,120,120,0.2)"
                        : d.status === "failed"
                        ? "rgba(239,68,68,0.2)"
                        : "rgba(99,102,241,0.2)",
                  }}
                >
                  {STATUS_LABELS_RU[d.status]}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </details>
  );
}
