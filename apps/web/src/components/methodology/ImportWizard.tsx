"use client";

/**
 * TZ-5 PR #101 — universal import wizard with inline edit + bulk + re-extract.
 *
 * Embedded as a modal inside ScenariosEditor / ArenaContentEditor /
 * CharacterBuilder. Flow per file:
 *   select → uploading → review (editable, route-aware) → approve | discard
 *
 * Bulk upload accepts multiple files and processes them sequentially —
 * each one goes through the same review step so ROP doesn't have to
 * re-open the wizard for every file.
 *
 * Re-extract: from the review step, ROP can re-run extraction on the
 * same uploaded bytes (new classifier guess or forced route).
 */

import { useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api";
import {
  type ArenaKnowledgePayload,
  type CharacterPayload,
  type ImportDraft,
  type ImportRouteType,
  type ScenarioPayload,
  type ScenarioStepDraft,
  ROUTE_LABELS_RU,
  approveArenaKnowledgeDraft,
  approveCharacterDraft,
  convertScenarioDraft,
  discardImportDraft,
  reExtractDraft,
  updateImportDraft,
  uploadImportMaterial,
} from "@/lib/api/imports";
import { ARCHETYPES } from "@/lib/archetypes";

const ALLOWED_EXTENSIONS = [".pdf", ".docx", ".txt", ".md", ".pptx"];
const MAX_BYTES = 50 * 1024 * 1024;
const ROUTE_OPTIONS: ImportRouteType[] = ["scenario", "character", "arena_knowledge"];
const ARENA_CATEGORIES = [
  "eligibility",
  "process",
  "rights",
  "deadlines",
  "cost",
  "consequences",
  "general",
];

type Step = "select" | "uploading" | "review" | "approving" | "done" | "error";

interface Props {
  open: boolean;
  onClose: () => void;
  presetRouteType?: ImportRouteType;
  onApproved?: (draft: ImportDraft, target: { kind: ImportRouteType; id: string }) => void;
}

interface QueueItem {
  file: File;
  status: "pending" | "active" | "done" | "skipped" | "error";
  draftId?: string;
  errorMsg?: string;
}

export function ImportWizard({ open, onClose, presetRouteType, onApproved }: Props) {
  const [step, setStep] = useState<Step>("select");
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [activeIdx, setActiveIdx] = useState<number>(-1);
  const [consent, setConsent] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [draft, setDraft] = useState<ImportDraft | null>(null);
  const [editedPayload, setEditedPayload] = useState<ScenarioPayload | CharacterPayload | ArenaKnowledgePayload | null>(null);
  const [chosenRoute, setChosenRoute] = useState<ImportRouteType>("scenario");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [resultMsg, setResultMsg] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [reExtracting, setReExtracting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!open) {
      setStep("select");
      setQueue([]);
      setActiveIdx(-1);
      setConsent(false);
      setDraft(null);
      setEditedPayload(null);
      setErrorMsg(null);
      setResultMsg(null);
    }
  }, [open]);

  // ── helpers ──────────────────────────────────────────────────────────

  const validateFile = (f: File): string | null => {
    const lower = f.name.toLowerCase();
    if (!ALLOWED_EXTENSIONS.some((ext) => lower.endsWith(ext))) {
      return `«${f.name}»: формат не поддерживается. Принимаем: ${ALLOWED_EXTENSIONS.join(", ")}`;
    }
    if (f.size > MAX_BYTES) {
      return `«${f.name}»: больше ${MAX_BYTES / (1024 * 1024)} МБ.`;
    }
    return null;
  };

  const addFiles = (files: FileList | File[] | null) => {
    if (!files) return;
    const arr = Array.from(files);
    const errs: string[] = [];
    const accepted: File[] = [];
    for (const f of arr) {
      const e = validateFile(f);
      if (e) errs.push(e);
      else accepted.push(f);
    }
    setErrorMsg(errs.length ? errs.join("\n") : null);
    if (accepted.length) {
      setQueue((q) => [
        ...q,
        ...accepted.map((file) => ({ file, status: "pending" as const })),
      ]);
    }
  };

  const removeQueueItem = (idx: number) => {
    setQueue((q) => q.filter((_, i) => i !== idx));
  };

  const startProcessing = async () => {
    if (!queue.length || !consent) return;
    setStep("uploading");
    setActiveIdx(0);
    await processFile(0);
  };

  const processFile = async (idx: number) => {
    setActiveIdx(idx);
    setQueue((q) => q.map((it, i) => (i === idx ? { ...it, status: "active" } : it)));
    try {
      const result = await uploadImportMaterial(
        queue[idx].file,
        consent,
        presetRouteType,
      );
      setDraft(result);
      setEditedPayload(result.extracted_raw || result.extracted || null);
      setChosenRoute(result.route_type);
      setQueue((q) =>
        q.map((it, i) => (i === idx ? { ...it, status: "active", draftId: result.id } : it)),
      );
      setStep("review");
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e);
      setQueue((q) =>
        q.map((it, i) => (i === idx ? { ...it, status: "error", errorMsg: msg } : it)),
      );
      // skip to next file in bulk mode, otherwise show error
      if (queue.length > 1 && idx + 1 < queue.length) {
        await processFile(idx + 1);
      } else {
        setErrorMsg(msg);
        setStep("error");
      }
    }
  };

  const goToNextOrFinish = () => {
    const next = activeIdx + 1;
    if (next < queue.length) {
      setDraft(null);
      setEditedPayload(null);
      processFile(next);
    } else {
      setStep("done");
    }
  };

  // ── editor actions ───────────────────────────────────────────────────

  const saveEdits = async () => {
    if (!draft || !editedPayload) return;
    setSaving(true);
    try {
      // Inject confidence ≥ 0.6 only when the user actually edited (we
      // forward the edited payload; backend gate will raise 409 if confidence
      // bumps without `extracted` change — so we always send `extracted`).
      const updated = await updateImportDraft(draft.id, {
        extracted: editedPayload,
      });
      setDraft(updated);
      setResultMsg("Изменения сохранены.");
    } catch (e) {
      setErrorMsg(e instanceof ApiError ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const onApprove = async () => {
    if (!draft) return;
    setStep("approving");
    setErrorMsg(null);
    try {
      // If ROP edited, save first; the approve endpoints use draft.extracted.
      if (editedPayload && draft.status !== "edited") {
        await updateImportDraft(draft.id, { extracted: editedPayload });
      }
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
      setQueue((q) =>
        q.map((it, i) => (i === activeIdx ? { ...it, status: "done" } : it)),
      );
      goToNextOrFinish();
    } catch (e) {
      setErrorMsg(e instanceof ApiError ? e.message : String(e));
      setStep("error");
    }
  };

  const onDiscard = async () => {
    if (!draft) return;
    try {
      await discardImportDraft(draft.id);
      setQueue((q) =>
        q.map((it, i) => (i === activeIdx ? { ...it, status: "skipped" } : it)),
      );
      goToNextOrFinish();
    } catch (e) {
      setErrorMsg(e instanceof ApiError ? e.message : String(e));
      setStep("error");
    }
  };

  const onReExtract = async (forced?: ImportRouteType) => {
    if (!draft) return;
    setReExtracting(true);
    setErrorMsg(null);
    try {
      const updated = await reExtractDraft(draft.id, forced);
      setDraft(updated);
      setEditedPayload(updated.extracted_raw || updated.extracted || null);
      setChosenRoute(updated.route_type);
    } catch (e) {
      setErrorMsg(e instanceof ApiError ? e.message : String(e));
    } finally {
      setReExtracting(false);
    }
  };

  // ── render ───────────────────────────────────────────────────────────

  if (!open) return null;

  const isBulk = queue.length > 1;
  const progressLabel = isBulk
    ? `Файл ${activeIdx + 1} из ${queue.length}`
    : null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="glass-panel max-w-2xl w-full max-h-[90vh] overflow-y-auto rounded-2xl p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-start justify-between mb-4">
          <div>
            <h2 className="text-xl font-semibold">Импорт материала</h2>
            <p className="text-sm opacity-70 mt-1">
              {presetRouteType
                ? `Целевая ветка: ${ROUTE_LABELS_RU[presetRouteType]}`
                : "Платформа определит куда положить файл — вы сможете переключить ветку до сохранения."}
            </p>
            {progressLabel && (
              <p className="text-xs mt-1 opacity-60">{progressLabel}</p>
            )}
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
          <SelectStep
            queue={queue}
            consent={consent}
            dragActive={dragActive}
            errorMsg={errorMsg}
            fileInputRef={fileInputRef}
            onAddFiles={addFiles}
            onRemove={removeQueueItem}
            onConsent={setConsent}
            onDragActive={setDragActive}
            onSubmit={startProcessing}
            onCancel={onClose}
          />
        )}

        {step === "uploading" && (
          <div className="py-8 text-center">
            <p>Загружаем и анализируем «{queue[activeIdx]?.file.name}»…</p>
            <div className="mt-4 w-full bg-white/10 rounded-full h-2 overflow-hidden">
              <div
                className="h-full bg-[var(--accent)] animate-pulse"
                style={{ width: "60%" }}
              />
            </div>
            {isBulk && <BulkProgress queue={queue} activeIdx={activeIdx} />}
          </div>
        )}

        {step === "review" && draft && (
          <ReviewStep
            draft={draft}
            editedPayload={editedPayload}
            chosenRoute={chosenRoute}
            presetRouteType={presetRouteType}
            saving={saving}
            reExtracting={reExtracting}
            errorMsg={errorMsg}
            resultMsg={resultMsg}
            isBulk={isBulk}
            queue={queue}
            activeIdx={activeIdx}
            onChosenRoute={setChosenRoute}
            onPayloadChange={setEditedPayload}
            onSave={saveEdits}
            onApprove={onApprove}
            onDiscard={onDiscard}
            onReExtract={onReExtract}
          />
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
              {isBulk && (
                <p className="text-xs mt-2 opacity-80">
                  Обработано: {queue.filter((q) => q.status === "done").length} ·
                  пропущено: {queue.filter((q) => q.status === "skipped").length} ·
                  ошибок: {queue.filter((q) => q.status === "error").length}
                </p>
              )}
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
            <div className="rounded-lg p-4 bg-red-900/20 border border-red-700/40 text-sm whitespace-pre-wrap">
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
                onClick={() => {
                  setErrorMsg(null);
                  setStep("select");
                }}
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

// ── Sub-components ─────────────────────────────────────────────────────

function SelectStep({
  queue,
  consent,
  dragActive,
  errorMsg,
  fileInputRef,
  onAddFiles,
  onRemove,
  onConsent,
  onDragActive,
  onSubmit,
  onCancel,
}: {
  queue: QueueItem[];
  consent: boolean;
  dragActive: boolean;
  errorMsg: string | null;
  fileInputRef: React.MutableRefObject<HTMLInputElement | null>;
  onAddFiles: (files: FileList | null) => void;
  onRemove: (idx: number) => void;
  onConsent: (b: boolean) => void;
  onDragActive: (b: boolean) => void;
  onSubmit: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="space-y-4">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          onDragActive(true);
        }}
        onDragLeave={() => onDragActive(false)}
        onDrop={(e) => {
          e.preventDefault();
          onDragActive(false);
          onAddFiles(e.dataTransfer.files);
        }}
        onClick={() => fileInputRef.current?.click()}
        className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition ${
          dragActive ? "border-[var(--accent)]" : "border-white/20"
        }`}
        role="button"
        tabIndex={0}
      >
        <p className="text-base">
          Перетащите файлы сюда или нажмите, чтобы выбрать
        </p>
        <p className="text-xs opacity-60 mt-2">
          {ALLOWED_EXTENSIONS.join(", ")} · до 50 МБ · можно несколько
        </p>
        <input
          ref={fileInputRef}
          type="file"
          accept={ALLOWED_EXTENSIONS.join(",")}
          multiple
          hidden
          onChange={(e) => onAddFiles(e.target.files)}
        />
      </div>

      {queue.length > 0 && (
        <ul className="space-y-1 max-h-40 overflow-y-auto">
          {queue.map((q, i) => (
            <li
              key={i}
              className="flex items-center justify-between text-sm bg-white/5 rounded px-3 py-1.5"
            >
              <span className="truncate flex-1">
                {q.file.name}
                <span className="opacity-50 ml-2">
                  ({(q.file.size / 1024).toFixed(0)} КБ)
                </span>
              </span>
              <button
                type="button"
                onClick={() => onRemove(i)}
                className="opacity-60 hover:opacity-100 ml-2"
                aria-label={`Удалить ${q.file.name}`}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}

      <label className="flex items-start gap-2 text-sm cursor-pointer">
        <input
          type="checkbox"
          checked={consent}
          onChange={(e) => onConsent(e.target.checked)}
          className="mt-1"
        />
        <span>
          Согласен на обработку обучающего материала по 152-ФЗ. Загружаемые
          данные не должны содержать несогласованной персональной информации
          клиентов.
        </span>
      </label>

      {errorMsg && (
        <div className="text-sm text-red-400 bg-red-900/20 rounded p-3 border border-red-700/40 whitespace-pre-wrap">
          {errorMsg}
        </div>
      )}

      <div className="flex gap-2 justify-end">
        <button
          type="button"
          className="px-4 py-2 rounded-lg opacity-70 hover:opacity-100"
          onClick={onCancel}
        >
          Отмена
        </button>
        <button
          type="button"
          disabled={!queue.length || !consent}
          onClick={onSubmit}
          className="px-4 py-2 rounded-lg bg-[var(--accent)] disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Загрузить {queue.length > 1 ? `(${queue.length} файлов)` : ""}
        </button>
      </div>
    </div>
  );
}

function BulkProgress({ queue, activeIdx }: { queue: QueueItem[]; activeIdx: number }) {
  return (
    <div className="mt-4 text-left text-xs space-y-1">
      {queue.map((q, i) => (
        <div key={i} className="flex justify-between">
          <span className="truncate flex-1">
            {i === activeIdx && "▶ "}
            {q.file.name}
          </span>
          <span className="ml-2 opacity-70">
            {q.status === "done"
              ? "✓"
              : q.status === "error"
              ? "✗"
              : q.status === "skipped"
              ? "—"
              : q.status === "active"
              ? "…"
              : ""}
          </span>
        </div>
      ))}
    </div>
  );
}

function ReviewStep({
  draft,
  editedPayload,
  chosenRoute,
  presetRouteType,
  saving,
  reExtracting,
  errorMsg,
  resultMsg,
  isBulk,
  queue,
  activeIdx,
  onChosenRoute,
  onPayloadChange,
  onSave,
  onApprove,
  onDiscard,
  onReExtract,
}: {
  draft: ImportDraft;
  editedPayload: ScenarioPayload | CharacterPayload | ArenaKnowledgePayload | null;
  chosenRoute: ImportRouteType;
  presetRouteType?: ImportRouteType;
  saving: boolean;
  reExtracting: boolean;
  errorMsg: string | null;
  resultMsg: string | null;
  isBulk: boolean;
  queue: QueueItem[];
  activeIdx: number;
  onChosenRoute: (r: ImportRouteType) => void;
  onPayloadChange: (p: ScenarioPayload | CharacterPayload | ArenaKnowledgePayload) => void;
  onSave: () => void;
  onApprove: () => void;
  onDiscard: () => void;
  onReExtract: (forced?: ImportRouteType) => void;
}) {
  return (
    <div className="space-y-4">
      <div className="rounded-lg p-3 bg-white/5">
        <p className="text-sm opacity-70">Платформа определила:</p>
        <p className="font-medium mt-1">{ROUTE_LABELS_RU[draft.route_type]}</p>
        <p className="text-xs opacity-60 mt-1">
          Уверенность: {(draft.confidence * 100).toFixed(0)}%
          {draft.original_confidence !== null &&
            draft.original_confidence !== draft.confidence && (
              <span className="ml-2">
                (LLM был: {(draft.original_confidence * 100).toFixed(0)}%)
              </span>
            )}
        </p>
        {draft.confidence < 0.6 && (
          <p className="text-xs text-amber-400 mt-2">
            ⚠ Уверенность низкая — отредактируйте поля или нажмите «Re-extract».
          </p>
        )}
      </div>

      {!presetRouteType && (
        <div className="rounded-lg p-3 bg-white/5">
          <p className="text-sm mb-2">Куда сохранить?</p>
          <div className="flex gap-3 flex-wrap">
            {ROUTE_OPTIONS.map((r) => (
              <label key={r} className="flex items-center gap-1.5 cursor-pointer text-sm">
                <input
                  type="radio"
                  name="route"
                  checked={chosenRoute === r}
                  onChange={() => onChosenRoute(r)}
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

      {!draft.error_message && editedPayload && (
        <RouteEditor
          routeType={chosenRoute}
          payload={editedPayload}
          onChange={onPayloadChange}
        />
      )}

      <details className="text-sm">
        <summary className="cursor-pointer opacity-70 hover:opacity-100">
          Показать извлечённый текст (PII вырезан)
        </summary>
        <pre className="mt-2 p-3 bg-black/30 rounded text-xs whitespace-pre-wrap max-h-48 overflow-auto">
          {draft.source_text || "(пусто)"}
        </pre>
      </details>

      {resultMsg && (
        <div className="text-xs text-green-400 bg-green-900/20 rounded p-2 border border-green-700/40">
          {resultMsg}
        </div>
      )}

      {errorMsg && (
        <div className="text-sm text-red-400 bg-red-900/20 rounded p-3 border border-red-700/40">
          {errorMsg}
        </div>
      )}

      <div className="flex gap-2 justify-between flex-wrap">
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => onReExtract()}
            disabled={reExtracting}
            className="px-3 py-2 rounded-lg text-sm opacity-70 hover:opacity-100 disabled:opacity-40"
            title="Заново прогнать классификатор и экстрактор"
          >
            ↻ Re-extract
          </button>
          <button
            type="button"
            onClick={onSave}
            disabled={saving || !editedPayload}
            className="px-3 py-2 rounded-lg text-sm opacity-70 hover:opacity-100 disabled:opacity-40"
          >
            {saving ? "Сохраняем…" : "Сохранить правки"}
          </button>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            className="px-4 py-2 rounded-lg text-sm opacity-70 hover:opacity-100"
            onClick={onDiscard}
          >
            {isBulk ? "Пропустить" : "Отклонить"}
          </button>
          <button
            type="button"
            onClick={onApprove}
            disabled={!!draft.error_message}
            className="px-4 py-2 rounded-lg bg-[var(--accent)] disabled:opacity-40"
          >
            {isBulk && activeIdx + 1 < queue.length
              ? "Сохранить и далее →"
              : "Сохранить как черновик"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Route-aware payload editor ─────────────────────────────────────────

function RouteEditor({
  routeType,
  payload,
  onChange,
}: {
  routeType: ImportRouteType;
  payload: ScenarioPayload | CharacterPayload | ArenaKnowledgePayload;
  onChange: (p: ScenarioPayload | CharacterPayload | ArenaKnowledgePayload) => void;
}) {
  if (routeType === "scenario") {
    return <ScenarioEditor payload={payload as ScenarioPayload} onChange={onChange} />;
  }
  if (routeType === "character") {
    return <CharacterEditor payload={payload as CharacterPayload} onChange={onChange} />;
  }
  return <ArenaEditor payload={payload as ArenaKnowledgePayload} onChange={onChange} />;
}

function FieldLabel({ children }: { children: React.ReactNode }) {
  return <label className="block text-xs uppercase tracking-wider opacity-60 mb-1">{children}</label>;
}

function ScenarioEditor({
  payload,
  onChange,
}: {
  payload: ScenarioPayload;
  onChange: (p: ScenarioPayload) => void;
}) {
  const update = <K extends keyof ScenarioPayload>(k: K, v: ScenarioPayload[K]) =>
    onChange({ ...payload, [k]: v });

  const updateStep = (idx: number, patch: Partial<ScenarioStepDraft>) => {
    const next = [...payload.steps];
    next[idx] = { ...next[idx], ...patch };
    update("steps", next);
  };
  const addStep = () => {
    update("steps", [
      ...payload.steps,
      {
        order: payload.steps.length + 1,
        name: `Шаг ${payload.steps.length + 1}`,
        description: "",
        manager_goals: [],
        expected_client_reaction: null,
      },
    ]);
  };
  const removeStep = (idx: number) =>
    update(
      "steps",
      payload.steps.filter((_, i) => i !== idx).map((s, i) => ({ ...s, order: i + 1 })),
    );

  return (
    <div className="space-y-3">
      <div>
        <FieldLabel>Название</FieldLabel>
        <input
          type="text"
          value={payload.title_suggested}
          onChange={(e) => update("title_suggested", e.target.value)}
          className="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-sm"
        />
      </div>
      <div>
        <FieldLabel>Краткое описание</FieldLabel>
        <textarea
          value={payload.summary}
          onChange={(e) => update("summary", e.target.value)}
          rows={2}
          className="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-sm"
        />
      </div>
      <div>
        <FieldLabel>Этапы</FieldLabel>
        <div className="space-y-2">
          {payload.steps.map((s, i) => (
            <div key={i} className="bg-white/5 rounded p-2 space-y-1">
              <div className="flex items-center gap-2">
                <span className="text-xs opacity-60 w-5">#{s.order}</span>
                <input
                  type="text"
                  value={s.name}
                  onChange={(e) => updateStep(i, { name: e.target.value })}
                  className="flex-1 bg-white/5 border border-white/10 rounded px-2 py-1 text-sm"
                  placeholder="Название шага"
                />
                <button
                  type="button"
                  onClick={() => removeStep(i)}
                  className="opacity-60 hover:opacity-100 px-2"
                  aria-label="Удалить шаг"
                >
                  ×
                </button>
              </div>
              <textarea
                value={s.description}
                onChange={(e) => updateStep(i, { description: e.target.value })}
                rows={2}
                className="w-full bg-white/5 border border-white/10 rounded px-2 py-1 text-xs"
                placeholder="Что делает менеджер на этом шаге"
              />
            </div>
          ))}
          <button
            type="button"
            onClick={addStep}
            className="text-xs opacity-70 hover:opacity-100 px-3 py-1.5 rounded border border-dashed border-white/20"
          >
            + Добавить шаг
          </button>
        </div>
      </div>
      <StringListEditor
        label="Возражения клиента"
        items={payload.expected_objections}
        onChange={(v) => update("expected_objections", v)}
        placeholder="Например: дорого"
      />
      <StringListEditor
        label="Критерии успеха"
        items={payload.success_criteria}
        onChange={(v) => update("success_criteria", v)}
        placeholder="Например: встреча в календаре"
      />
      <StringListEditor
        label="Цитаты из исходника (audit-trail)"
        items={payload.quotes_from_source}
        onChange={(v) => update("quotes_from_source", v)}
        placeholder="Должна совпадать с текстом источника"
      />
    </div>
  );
}

function CharacterEditor({
  payload,
  onChange,
}: {
  payload: CharacterPayload;
  onChange: (p: CharacterPayload) => void;
}) {
  const update = <K extends keyof CharacterPayload>(k: K, v: CharacterPayload[K]) =>
    onChange({ ...payload, [k]: v });

  return (
    <div className="space-y-3">
      <div>
        <FieldLabel>Имя / тип персонажа</FieldLabel>
        <input
          type="text"
          value={payload.name}
          onChange={(e) => update("name", e.target.value)}
          className="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-sm"
          placeholder="Иван П., директор стройки"
        />
      </div>
      <div>
        <FieldLabel>Архетип (выбор из 100)</FieldLabel>
        <select
          value={payload.archetype_hint || ""}
          onChange={(e) => update("archetype_hint", e.target.value || null)}
          className="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-sm"
        >
          <option value="">— не выбран —</option>
          {ARCHETYPES.map((a) => (
            <option key={a.code} value={a.code}>
              {a.name} — {a.subtitle}
            </option>
          ))}
        </select>
      </div>
      <div>
        <FieldLabel>Описание</FieldLabel>
        <textarea
          value={payload.description}
          onChange={(e) => update("description", e.target.value)}
          rows={3}
          className="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-sm"
        />
      </div>
      <StringListEditor
        label="Черты характера"
        items={payload.personality_traits}
        onChange={(v) => update("personality_traits", v)}
        placeholder="Например: агрессивный"
      />
      <StringListEditor
        label="Типичные возражения"
        items={payload.typical_objections}
        onChange={(v) => update("typical_objections", v)}
      />
      <StringListEditor
        label="Речевые паттерны"
        items={payload.speech_patterns}
        onChange={(v) => update("speech_patterns", v)}
        placeholder="Любимая фраза или тик"
      />
      <StringListEditor
        label="Цитаты из исходника"
        items={payload.quotes_from_source}
        onChange={(v) => update("quotes_from_source", v)}
      />
    </div>
  );
}

function ArenaEditor({
  payload,
  onChange,
}: {
  payload: ArenaKnowledgePayload;
  onChange: (p: ArenaKnowledgePayload) => void;
}) {
  const update = <K extends keyof ArenaKnowledgePayload>(k: K, v: ArenaKnowledgePayload[K]) =>
    onChange({ ...payload, [k]: v });

  return (
    <div className="space-y-3">
      <div>
        <FieldLabel>Факт</FieldLabel>
        <textarea
          value={payload.fact_text}
          onChange={(e) => update("fact_text", e.target.value)}
          rows={3}
          className="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-sm"
          placeholder="Минимальный долг для банкротства — 500 000 руб."
        />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <FieldLabel>Статья закона</FieldLabel>
          <input
            type="text"
            value={payload.law_article || ""}
            onChange={(e) => update("law_article", e.target.value || null)}
            className="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-sm"
            placeholder="127-ФЗ ст. 213.3"
          />
        </div>
        <div>
          <FieldLabel>Категория</FieldLabel>
          <select
            value={payload.category}
            onChange={(e) => update("category", e.target.value)}
            className="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-sm"
          >
            {ARENA_CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div>
        <FieldLabel>Сложность (1-5)</FieldLabel>
        <input
          type="range"
          min={1}
          max={5}
          step={1}
          value={payload.difficulty_level}
          onChange={(e) => update("difficulty_level", Number(e.target.value))}
          className="w-full"
        />
        <p className="text-xs opacity-60 mt-1">Текущая: {payload.difficulty_level}</p>
      </div>
      <StringListEditor
        label="Ключевые слова для матчинга"
        items={payload.match_keywords}
        onChange={(v) => update("match_keywords", v)}
      />
      <StringListEditor
        label="Типичные ошибки"
        items={payload.common_errors}
        onChange={(v) => update("common_errors", v)}
        placeholder="Например: 100 000 рублей"
      />
      <div>
        <FieldLabel>Подсказка-ответ</FieldLabel>
        <input
          type="text"
          value={payload.correct_response_hint}
          onChange={(e) => update("correct_response_hint", e.target.value)}
          className="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-sm"
        />
      </div>
      <StringListEditor
        label="Цитаты из исходника"
        items={payload.quotes_from_source}
        onChange={(v) => update("quotes_from_source", v)}
      />
    </div>
  );
}

function StringListEditor({
  label,
  items,
  onChange,
  placeholder,
}: {
  label: string;
  items: string[];
  onChange: (v: string[]) => void;
  placeholder?: string;
}) {
  const [input, setInput] = useState("");
  const add = () => {
    const v = input.trim();
    if (!v) return;
    onChange([...items, v]);
    setInput("");
  };
  const remove = (i: number) => onChange(items.filter((_, j) => j !== i));
  return (
    <div>
      <FieldLabel>{label}</FieldLabel>
      <div className="flex flex-wrap gap-1.5 mb-2">
        {items.map((it, i) => (
          <span
            key={i}
            className="text-xs bg-white/10 rounded px-2 py-1 flex items-center gap-1"
          >
            {it}
            <button
              type="button"
              onClick={() => remove(i)}
              className="opacity-60 hover:opacity-100"
              aria-label={`Удалить ${it}`}
            >
              ×
            </button>
          </span>
        ))}
        {!items.length && (
          <span className="text-xs opacity-40 italic">пока ничего</span>
        )}
      </div>
      <div className="flex gap-1.5">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
          placeholder={placeholder}
          className="flex-1 bg-white/5 border border-white/10 rounded px-3 py-1.5 text-sm"
        />
        <button
          type="button"
          onClick={add}
          className="px-3 py-1.5 rounded bg-white/5 hover:bg-white/10 text-sm"
        >
          +
        </button>
      </div>
    </div>
  );
}
