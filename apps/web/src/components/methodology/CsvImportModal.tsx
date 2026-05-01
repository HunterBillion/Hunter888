"use client";

/**
 * Admin-only — bulk-create users from a CSV.
 *
 * Surfaced as "📥 Импорт CSV" button in the Команда sub-tab when the
 * caller is an admin. Server expects columns: email, full_name (required)
 * + role, team_id (optional). BOM-tolerant.
 */

import { useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api";
import { type CsvImportResponse, importUsersCsv } from "@/lib/api/team";

const MAX_BYTES = 1 * 1024 * 1024;

interface Props {
  open: boolean;
  onClose: () => void;
  onImported?: (resp: CsvImportResponse) => void;
}

export function CsvImportModal({ open, onClose, onImported }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CsvImportResponse | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!open) {
      setFile(null);
      setError(null);
      setResult(null);
    }
  }, [open]);

  const onPick = (f: File | null) => {
    if (!f) return;
    if (f.size > MAX_BYTES) {
      setError(`CSV больше ${MAX_BYTES / 1024} КБ — разделите файл.`);
      return;
    }
    if (!f.name.toLowerCase().endsWith(".csv")) {
      setError("Принимаем только .csv");
      return;
    }
    setFile(f);
    setError(null);
  };

  const onSubmit = async () => {
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      const resp = await importUsersCsv(file);
      setResult(resp);
      onImported?.(resp);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="glass-panel max-w-xl w-full max-h-[90vh] overflow-y-auto rounded-2xl p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-start justify-between mb-4">
          <div>
            <h2 className="text-xl font-semibold">Импорт пользователей из CSV</h2>
            <p className="text-sm opacity-70 mt-1">
              Колонки: <code>email, full_name</code> (обязательные) +{" "}
              <code>role, team_id</code> (опциональные). До 1 МБ.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="opacity-70 hover:opacity-100 px-2 py-1 text-lg leading-none"
            aria-label="Закрыть"
          >
            ×
          </button>
        </header>

        {!result && (
          <div className="space-y-4">
            <div
              onClick={() => inputRef.current?.click()}
              className="border-2 border-dashed border-white/20 rounded-xl p-6 text-center cursor-pointer"
              role="button"
              tabIndex={0}
            >
              <p className="text-base">
                {file
                  ? `Выбран: ${file.name} (${(file.size / 1024).toFixed(0)} КБ)`
                  : "Нажмите чтобы выбрать .csv"}
              </p>
              <input
                ref={inputRef}
                type="file"
                accept=".csv,text/csv"
                hidden
                onChange={(e) => onPick(e.target.files?.[0] || null)}
              />
            </div>

            <details className="text-sm">
              <summary className="cursor-pointer opacity-70 hover:opacity-100">
                Показать пример CSV
              </summary>
              <pre className="mt-2 p-3 bg-black/30 rounded text-xs whitespace-pre-wrap">
{`email,full_name,role,team_id
ivan@x.ru,Иван Петров,manager,
maria@x.ru,Мария Иванова,rop,
admin@x.ru,Админ Главный,admin,`}
              </pre>
              <p className="text-xs opacity-60 mt-2">
                Пользователи создаются с временным паролем; запросите сброс через
                «Забыли пароль?» или отправьте инвайт.
              </p>
            </details>

            {error && (
              <div
                className="text-sm rounded p-3 border"
                style={{
                  color: "var(--danger)",
                  background: "rgba(239,68,68,0.1)",
                  borderColor: "rgba(239,68,68,0.4)",
                }}
              >
                {error}
              </div>
            )}

            <div className="flex justify-end gap-2">
              <button
                type="button"
                className="px-4 py-2 rounded-lg opacity-70 hover:opacity-100"
                onClick={onClose}
              >
                Отмена
              </button>
              <button
                type="button"
                onClick={onSubmit}
                disabled={!file || loading}
                className="px-4 py-2 rounded-lg bg-[var(--accent)] disabled:opacity-40"
              >
                {loading ? "Импортируем…" : "Импортировать"}
              </button>
            </div>
          </div>
        )}

        {result && (
          <div className="space-y-4">
            <div className="rounded-lg p-3 bg-green-900/20 border border-green-700/40 text-sm">
              Создано: {result.created} · пропущено: {result.skipped} · ошибок: {result.errors}
            </div>
            <table className="w-full text-xs">
              <thead className="opacity-60">
                <tr>
                  <th className="text-left py-1">Стр.</th>
                  <th className="text-left py-1">Email</th>
                  <th className="text-left py-1">Статус</th>
                  <th className="text-left py-1">Ошибка</th>
                </tr>
              </thead>
              <tbody>
                {result.rows.map((r, i) => (
                  <tr key={i} className="border-t border-white/5">
                    <td className="py-1">{r.line}</td>
                    <td className="py-1 truncate max-w-[180px]">{r.email}</td>
                    <td className="py-1">
                      <span
                        className="px-2 py-0.5 rounded text-xs"
                        style={{
                          background:
                            r.status === "created"
                              ? "rgba(34,197,94,0.2)"
                              : r.status === "error"
                              ? "rgba(239,68,68,0.2)"
                              : "rgba(120,120,120,0.2)",
                        }}
                      >
                        {r.status}
                      </span>
                    </td>
                    <td className="py-1 opacity-70 text-xs truncate max-w-[180px]">
                      {r.error || ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="flex justify-end">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 rounded-lg bg-[var(--accent)]"
              >
                Закрыть
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
