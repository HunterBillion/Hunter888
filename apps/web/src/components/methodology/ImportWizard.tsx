"use client";

/**
 * TZ-5 PR-2 — universal import wizard.
 *
 * Embedded as a modal inside ScenariosEditor / ArenaChunksEditor /
 * CharacterBuilder. ROP picks a file → confirms 152-FZ consent →
 * uploads → classifier suggests a branch → ROP can override → approve
 * routes the draft into the right table (scenario_template /
 * custom_character / legal_knowledge_chunk).
 *
 * Stays in a single component so all three call sites get the same
 * UX without dragging-in a new module.
 */

import { useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api";
import {
  type ImportDraft,
  type ImportRouteType,
  ROUTE_LABELS_RU,
  approveArenaKnowledgeDraft,
  approveCharacterDraft,
  convertScenarioDraft,
  discardImportDraft,
  uploadImportMaterial,
} from "@/lib/api/imports";

const ALLOWED_EXTENSIONS = [".pdf", ".docx", ".txt", ".md", ".pptx"];
const MAX_BYTES = 50 * 1024 * 1024;
const ROUTE_OPTIONS: ImportRouteType[] = ["scenario", "character", "arena_knowledge"];

type Step = "select" | "uploading" | "review" | "approving" | "done" | "error";

interface Props {
  open: boolean;
  onClose: () => void;
  /**
   * If set, the wizard pre-locks the route so the user doesn't see the
   * route picker — used when the wizard is launched from a context that
   * KNOWS the desired branch (e.g. "Импорт" button inside ArenaChunksEditor).
   * If not set, the classifier picks; ROP can override before approve.
   */
  presetRouteType?: ImportRouteType;
  /** Called after a successful approve so the parent can refresh its list. */
  onApproved?: (draft: ImportDraft, target: { kind: ImportRouteType; id: string }) => void;
}

export function ImportWizard({ open, onClose, presetRouteType, onApproved }: Props) {
  const [step, setStep] = useState<Step>("select");
  const [file, setFile] = useState<File | null>(null);
  const [consent, setConsent] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [draft, setDraft] = useState<ImportDraft | null>(null);
  const [chosenRoute, setChosenRoute] = useState<ImportRouteType>("scenario");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [resultMsg, setResultMsg] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // Reset on close so reopening starts clean.
  useEffect(() => {
    if (!open) {
      setStep("select");
      setFile(null);
      setConsent(false);
      setDraft(null);
      setErrorMsg(null);
      setResultMsg(null);
    }
  }, [open]);

  const validateFile = (f: File): string | null => {
    const lower = f.name.toLowerCase();
    if (!ALLOWED_EXTENSIONS.some((ext) => lower.endsWith(ext))) {
      return `Формат не поддерживается. Принимаем: ${ALLOWED_EXTENSIONS.join(", ")}`;
    }
    if (f.size > MAX_BYTES) {
      return `Файл больше ${MAX_BYTES / (1024 * 1024)} МБ — разделите на части.`;
    }
    return null;
  };

  const onPickFile = (f: File | null) => {
    if (!f) return;
    const err = validateFile(f);
    if (err) {
      setErrorMsg(err);
      return;
    }
    setFile(f);
    setErrorMsg(null);
  };

  const onSubmitUpload = async () => {
    if (!file || !consent) return;
    setStep("uploading");
    setErrorMsg(null);
    try {
      const result = await uploadImportMaterial(file, consent, presetRouteType);
      setDraft(result);
      setChosenRoute(result.route_type);
      setStep("review");
    } catch (e) {
      setErrorMsg(e instanceof ApiError ? e.message : String(e));
      setStep("error");
    }
  };

  const onApprove = async () => {
    if (!draft) return;
    setStep("approving");
    setErrorMsg(null);
    try {
      let targetId = "";
      if (chosenRoute === "scenario") {
        const r = await convertScenarioDraft(draft.id);
        targetId = r.template_id;
        setResultMsg(r.message);
      } else if (chosenRoute === "character") {
        const r = await approveCharacterDraft(draft.id);
        targetId = r.character_id;
        setResultMsg(r.message);
      } else {
        const r = await approveArenaKnowledgeDraft(draft.id);
        targetId = r.chunk_id;
        setResultMsg(r.message);
      }
      onApproved?.(draft, { kind: chosenRoute, id: targetId });
      setStep("done");
    } catch (e) {
      setErrorMsg(e instanceof ApiError ? e.message : String(e));
      setStep("error");
    }
  };

  const onDiscard = async () => {
    if (!draft) return;
    try {
      await discardImportDraft(draft.id);
      setResultMsg("Черновик отклонён.");
      setStep("done");
    } catch (e) {
      setErrorMsg(e instanceof ApiError ? e.message : String(e));
      setStep("error");
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
            <h2 className="text-xl font-semibold">Импорт материала</h2>
            <p className="text-sm opacity-70 mt-1">
              {presetRouteType
                ? `Целевая ветка: ${ROUTE_LABELS_RU[presetRouteType]}`
                : "Платформа сама определит куда положить файл — вы сможете переключить ветку до сохранения."}
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

        {step === "select" && (
          <div className="space-y-4">
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragActive(true);
              }}
              onDragLeave={() => setDragActive(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragActive(false);
                const f = e.dataTransfer.files?.[0];
                onPickFile(f || null);
              }}
              onClick={() => fileInputRef.current?.click()}
              className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition ${
                dragActive ? "border-[var(--accent)]" : "border-white/20"
              }`}
              role="button"
              tabIndex={0}
            >
              <p className="text-base">
                {file
                  ? `Выбран файл: ${file.name} (${(file.size / 1024).toFixed(0)} КБ)`
                  : "Перетащите файл сюда или нажмите, чтобы выбрать"}
              </p>
              <p className="text-xs opacity-60 mt-2">
                {ALLOWED_EXTENSIONS.join(", ")} · до 50 МБ
              </p>
              <input
                ref={fileInputRef}
                type="file"
                accept={ALLOWED_EXTENSIONS.join(",")}
                hidden
                onChange={(e) => onPickFile(e.target.files?.[0] || null)}
              />
            </div>

            <label className="flex items-start gap-2 text-sm cursor-pointer">
              <input
                type="checkbox"
                checked={consent}
                onChange={(e) => setConsent(e.target.checked)}
                className="mt-1"
              />
              <span>
                Согласен на обработку обучающего материала по 152-ФЗ. Загружаемые
                данные не должны содержать несогласованной персональной информации
                клиентов.
              </span>
            </label>

            {errorMsg && (
              <div className="text-sm text-red-400 bg-red-900/20 rounded p-3 border border-red-700/40">
                {errorMsg}
              </div>
            )}

            <div className="flex gap-2 justify-end">
              <button
                type="button"
                className="px-4 py-2 rounded-lg opacity-70 hover:opacity-100"
                onClick={onClose}
              >
                Отмена
              </button>
              <button
                type="button"
                disabled={!file || !consent}
                onClick={onSubmitUpload}
                className="px-4 py-2 rounded-lg bg-[var(--accent)] disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Загрузить
              </button>
            </div>
          </div>
        )}

        {step === "uploading" && (
          <div className="py-8 text-center">
            <p>Загружаем и анализируем материал…</p>
            <div className="mt-4 w-full bg-white/10 rounded-full h-2 overflow-hidden">
              <div className="h-full bg-[var(--accent)] animate-pulse" style={{ width: "60%" }} />
            </div>
          </div>
        )}

        {step === "review" && draft && (
          <div className="space-y-4">
            <div className="rounded-lg p-3 bg-white/5">
              <p className="text-sm opacity-70">Платформа определила:</p>
              <p className="font-medium mt-1">{ROUTE_LABELS_RU[draft.route_type]}</p>
              <p className="text-xs opacity-60 mt-1">
                Уверенность: {(draft.confidence * 100).toFixed(0)}%
              </p>
              {draft.confidence < 0.6 && (
                <p className="text-xs text-amber-400 mt-2">
                  ⚠ Уверенность низкая — проверьте перед сохранением.
                </p>
              )}
            </div>

            {!presetRouteType && (
              <div>
                <p className="text-sm mb-2">Куда сохранить?</p>
                <div className="space-y-2">
                  {ROUTE_OPTIONS.map((r) => (
                    <label key={r} className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="radio"
                        name="route"
                        checked={chosenRoute === r}
                        onChange={() => setChosenRoute(r)}
                      />
                      <span>{ROUTE_LABELS_RU[r]}</span>
                      {draft.route_type === r && (
                        <span className="text-xs opacity-60">(рекомендовано)</span>
                      )}
                    </label>
                  ))}
                </div>
              </div>
            )}

            {draft.error_message && (
              <div className="text-sm text-red-400 bg-red-900/20 rounded p-3 border border-red-700/40">
                {draft.error_message}
              </div>
            )}

            <details className="text-sm">
              <summary className="cursor-pointer opacity-70 hover:opacity-100">
                Показать извлечённый текст
              </summary>
              <pre className="mt-2 p-3 bg-black/30 rounded text-xs whitespace-pre-wrap max-h-48 overflow-auto">
                {draft.source_text || "(пусто)"}
              </pre>
            </details>

            <div className="flex gap-2 justify-end">
              <button
                type="button"
                className="px-4 py-2 rounded-lg opacity-70 hover:opacity-100"
                onClick={onDiscard}
              >
                Отклонить
              </button>
              <button
                type="button"
                onClick={onApprove}
                disabled={!!draft.error_message}
                className="px-4 py-2 rounded-lg bg-[var(--accent)] disabled:opacity-40"
              >
                Сохранить как черновик
              </button>
            </div>
          </div>
        )}

        {step === "approving" && (
          <div className="py-8 text-center">
            <p>Сохраняем…</p>
          </div>
        )}

        {step === "done" && (
          <div className="space-y-4">
            <div className="rounded-lg p-4 bg-green-900/20 border border-green-700/40">
              <p>{resultMsg || "Готово."}</p>
            </div>
            <div className="flex justify-end">
              <button
                type="button"
                className="px-4 py-2 rounded-lg bg-[var(--accent)]"
                onClick={onClose}
              >
                Закрыть
              </button>
            </div>
          </div>
        )}

        {step === "error" && (
          <div className="space-y-4">
            <div className="rounded-lg p-4 bg-red-900/20 border border-red-700/40 text-sm">
              {errorMsg || "Неизвестная ошибка."}
            </div>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                className="px-4 py-2 rounded-lg opacity-70 hover:opacity-100"
                onClick={onClose}
              >
                Закрыть
              </button>
              <button
                type="button"
                className="px-4 py-2 rounded-lg bg-[var(--accent)]"
                onClick={() => setStep("select")}
              >
                Попробовать ещё раз
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
