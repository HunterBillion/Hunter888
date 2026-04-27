"use client";

import { useRef, useState } from "react";
import { motion } from "framer-motion";
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  Copy,
  ExternalLink,
  FileText,
  Loader2,
  Paperclip,
  ScanSearch,
  ShieldCheck,
  ShieldAlert,
  ShieldX,
  Upload,
  XCircle,
} from "lucide-react";
import { ApiError, api } from "@/lib/api";
import { sanitizeText } from "@/lib/sanitize";
import type { ClientAttachment } from "@/types";

interface ClientAttachmentsProps {
  clientId: string;
  attachments: ClientAttachment[];
  readOnly?: boolean;
  onUploaded?: () => void;
}

/**
 * TZ-4 §6.1.1 four state machines. Each column has its own enum + RU
 * label + colour. We render up to four chips per attachment, omitting
 * columns that are at their default ("nothing happened yet") value to
 * keep the row readable.
 *
 * Naming reflects the production data shape (legacy ``pending`` /
 * ``not_required`` strings) — the §6.1.1 spec wording (``ocr_pending``
 * / ``ocr_done``) is not yet enforced in the backend write path.
 * Mapping both forms here so a future rename lands without breaking
 * already-deployed FE.
 */

type StateMachine = "lifecycle" | "ocr" | "classification" | "verification";

interface BadgeMeta {
  label: string;
  /** Tailwind-friendly state colour key. */
  tone: "muted" | "info" | "success" | "warning" | "danger";
  /** Optional tooltip text shown on hover. */
  hint?: string;
}

const LIFECYCLE_LABELS: Record<string, BadgeMeta> = {
  uploaded: { label: "Загружается", tone: "info", hint: "FE начал PUT/POST" },
  received: { label: "Получен", tone: "muted", hint: "Backend принял файл" },
  rejected: { label: "Отклонён", tone: "danger", hint: "AV блок / превышение лимита" },
  // Pre-D1 historical values still possible on old rows.
  processing: { label: "Обработка", tone: "info" },
  ready: { label: "Готов", tone: "success" },
  failed: { label: "Ошибка", tone: "danger" },
};

const OCR_LABELS: Record<string, BadgeMeta> = {
  not_required: { label: "OCR не нужен", tone: "muted" },
  pending: { label: "OCR ожидает", tone: "warning" },
  ocr_pending: { label: "OCR ожидает", tone: "warning" },
  in_progress: { label: "OCR идёт", tone: "info" },
  completed: { label: "OCR готов", tone: "success" },
  ocr_done: { label: "OCR готов", tone: "success" },
  failed: { label: "OCR упал", tone: "danger" },
  ocr_failed: { label: "OCR упал", tone: "danger" },
};

const CLASSIFICATION_LABELS: Record<string, BadgeMeta> = {
  pending: { label: "Классификация ожидает", tone: "warning" },
  classification_pending: { label: "Классификация ожидает", tone: "warning" },
  in_progress: { label: "Классификация идёт", tone: "info" },
  completed: { label: "Классифицирован", tone: "success" },
  classified: { label: "Классифицирован", tone: "success" },
  failed: { label: "Классиф. упала", tone: "danger" },
  classification_failed: { label: "Классиф. упала", tone: "danger" },
  not_required: { label: "Без классификации", tone: "muted" },
};

const VERIFICATION_LABELS: Record<string, BadgeMeta> = {
  unverified: { label: "Не проверен", tone: "muted" },
  pending_review: { label: "На ревью", tone: "warning" },
  verified: { label: "Проверен", tone: "success" },
  rejected_review: { label: "Отклонён ревью", tone: "danger" },
};

const TONE_STYLES: Record<BadgeMeta["tone"], { background: string; color: string }> = {
  muted: { background: "var(--bg-secondary)", color: "var(--text-muted)" },
  info: {
    background: "color-mix(in srgb, var(--info) 14%, transparent)",
    color: "var(--info)",
  },
  success: {
    background: "color-mix(in srgb, var(--success) 16%, transparent)",
    color: "var(--success)",
  },
  warning: {
    background: "color-mix(in srgb, var(--warning) 16%, transparent)",
    color: "var(--warning)",
  },
  danger: {
    background: "color-mix(in srgb, var(--danger) 16%, transparent)",
    color: "var(--danger)",
  },
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} Б`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} КБ`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`;
}

function badgeFor(machine: StateMachine, value: string | null | undefined): BadgeMeta | null {
  if (!value) return null;
  const dict =
    machine === "lifecycle"
      ? LIFECYCLE_LABELS
      : machine === "ocr"
        ? OCR_LABELS
        : machine === "classification"
          ? CLASSIFICATION_LABELS
          : VERIFICATION_LABELS;
  return (
    dict[value] ?? {
      label: value,
      tone: "muted",
      hint: "Неизвестное значение state-machine — обновите FE labels",
    }
  );
}

/** Should the badge be hidden because the column sits at its
 * "nothing happened yet" default? Keeps the chip strip lean — only
 * shows what's actually informative for the manager. */
function isDefaultState(machine: StateMachine, value: string | null | undefined): boolean {
  if (!value) return true;
  if (machine === "ocr" && value === "not_required") return true;
  if (machine === "classification" && value === "not_required") return true;
  if (machine === "verification" && value === "unverified") return true;
  return false;
}

function VerificationIcon({ status }: { status: string | null | undefined }) {
  switch (status) {
    case "verified":
      return <ShieldCheck size={11} />;
    case "pending_review":
      return <ShieldAlert size={11} />;
    case "rejected_review":
      return <ShieldX size={11} />;
    default:
      return null;
  }
}

function StatusChip({
  machine,
  value,
  icon,
}: {
  machine: StateMachine;
  value: string | null | undefined;
  icon?: React.ReactNode;
}) {
  if (isDefaultState(machine, value)) return null;
  const meta = badgeFor(machine, value);
  if (!meta) return null;
  const style = TONE_STYLES[meta.tone];
  return (
    <span
      className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px]"
      style={style}
      title={meta.hint}
    >
      {icon}
      {meta.label}
    </span>
  );
}

export function ClientAttachments({
  clientId,
  attachments,
  readOnly = false,
  onUploaded,
}: ClientAttachmentsProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFile = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || uploading) return;

    setUploading(true);
    setError(null);
    try {
      await api.upload<ClientAttachment>(`/clients/${clientId}/attachments`, file);
      onUploaded?.();
    } catch (err) {
      const msg =
        err instanceof ApiError || err instanceof Error
          ? err.message
          : "Не удалось загрузить файл";
      setError(msg);
    } finally {
      setUploading(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.22 }}
      className="glass-panel p-4"
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Paperclip size={14} style={{ color: "var(--accent)" }} />
          <span
            className="text-xs font-semibold uppercase tracking-wide"
            style={{ color: "var(--accent)" }}
          >
            ДОКУМЕНТЫ
          </span>
        </div>
        {!readOnly && (
          <>
            <input
              ref={inputRef}
              type="file"
              className="hidden"
              onChange={handleFile}
              accept=".pdf,.png,.jpg,.jpeg,.webp,.heic,.tiff,.doc,.docx,.rtf,.odt,.xls,.xlsx,.csv,image/*,application/pdf"
            />
            <motion.button
              type="button"
              disabled={uploading}
              onClick={() => inputRef.current?.click()}
              className="text-xs flex items-center gap-1 disabled:opacity-50"
              style={{ color: "var(--accent)" }}
              whileTap={{ scale: 0.95 }}
            >
              {uploading ? (
                <Loader2 size={12} className="animate-spin" />
              ) : (
                <Upload size={12} />
              )}
              Загрузить
            </motion.button>
          </>
        )}
      </div>

      {error && (
        <div
          className="mb-3 flex items-start gap-2 rounded-lg px-2.5 py-2 text-xs"
          style={{
            background: "color-mix(in srgb, var(--danger) 12%, transparent)",
            color: "var(--danger)",
          }}
        >
          <AlertCircle size={13} className="mt-0.5 shrink-0" />
          <span>{sanitizeText(error)}</span>
        </div>
      )}

      {attachments.length === 0 ? (
        <p className="text-xs leading-relaxed" style={{ color: "var(--text-muted)" }}>
          Документы ещё не прикреплены. Загрузите паспорт, документы приставов, список
          кредитов или сканы, чтобы они сохранились в карточке и timeline.
        </p>
      ) : (
        <div className="space-y-2">
          {attachments.map((item) => {
            const isDuplicate = !!item.duplicate_of;
            const verified = item.verification_status === "verified";
            return (
              <div
                key={item.id}
                className="rounded-lg p-2.5"
                style={{
                  background: "var(--input-bg)",
                  border: `1px solid ${
                    verified
                      ? "color-mix(in srgb, var(--success) 35%, var(--border-color))"
                      : "var(--border-color)"
                  }`,
                }}
              >
                <div className="flex items-start gap-2">
                  <FileText
                    size={15}
                    className="mt-0.5 shrink-0"
                    style={{ color: "var(--accent)" }}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span
                        className="truncate text-sm font-medium"
                        style={{ color: "var(--text-primary)" }}
                      >
                        {sanitizeText(item.filename)}
                      </span>
                      {item.public_url && (
                        <a
                          href={item.public_url}
                          target="_blank"
                          rel="noreferrer"
                          className="shrink-0 opacity-70 hover:opacity-100"
                          style={{ color: "var(--accent)" }}
                          title="Открыть файл"
                        >
                          <ExternalLink size={12} />
                        </a>
                      )}
                    </div>

                    {/* Chip strip — TZ-4 §6.1.1 four state machines.
                        Default-state values are filtered out by
                        isDefaultState() so we don't render a wall of
                        "Не проверен / OCR не нужен / Без классификации"
                        for every freshly-uploaded row. */}
                    <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[10px]">
                      <span
                        className="rounded px-1.5 py-0.5"
                        style={{
                          background: "var(--bg-secondary)",
                          color: "var(--text-muted)",
                        }}
                      >
                        {sanitizeText(item.document_type ?? "unknown")}
                      </span>
                      <span
                        className="rounded px-1.5 py-0.5"
                        style={{
                          background: "var(--bg-secondary)",
                          color: "var(--text-muted)",
                        }}
                      >
                        {formatBytes(item.file_size)}
                      </span>
                      {/* Lifecycle never hides — even ``received`` is the
                          baseline status and tells the manager the row
                          is real. */}
                      <StatusChip
                        machine="lifecycle"
                        value={item.status}
                        icon={
                          item.status === "rejected" ? (
                            <XCircle size={10} />
                          ) : item.status === "received" ? (
                            <CheckCircle2 size={10} />
                          ) : (
                            <Clock size={10} />
                          )
                        }
                      />
                      <StatusChip
                        machine="ocr"
                        value={item.ocr_status}
                        icon={<ScanSearch size={10} />}
                      />
                      <StatusChip
                        machine="classification"
                        value={item.classification_status}
                      />
                      <StatusChip
                        machine="verification"
                        value={item.verification_status}
                        icon={<VerificationIcon status={item.verification_status} />}
                      />
                      {isDuplicate && (
                        <span
                          className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px]"
                          style={TONE_STYLES.warning}
                          title={`Дубликат файла ${item.duplicate_of}`}
                        >
                          <Copy size={10} />
                          Дубликат
                        </span>
                      )}
                    </div>

                    <div
                      className="mt-1 text-[10px] font-mono"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {item.sha256.slice(0, 12)}
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </motion.div>
  );
}
