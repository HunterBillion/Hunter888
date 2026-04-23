"use client";

import { useRef, useState } from "react";
import { motion } from "framer-motion";
import { FileText, Loader2, Paperclip, Upload, ExternalLink, AlertCircle } from "lucide-react";
import { ApiError, api } from "@/lib/api";
import { sanitizeText } from "@/lib/sanitize";
import type { ClientAttachment } from "@/types";

interface ClientAttachmentsProps {
  clientId: string;
  attachments: ClientAttachment[];
  readOnly?: boolean;
  onUploaded?: () => void;
}

const STATUS_LABELS: Record<string, string> = {
  received: "Получен",
  processing: "Обработка",
  ready: "Готов",
  failed: "Ошибка",
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} Б`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} КБ`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`;
}

function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
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
      const msg = err instanceof ApiError || err instanceof Error
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
          <span className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--accent)" }}>
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
              {uploading ? <Loader2 size={12} className="animate-spin" /> : <Upload size={12} />}
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
          Документы ещё не прикреплены. Загрузите паспорт, документы приставов, список кредитов или сканы,
          чтобы они сохранились в карточке и timeline.
        </p>
      ) : (
        <div className="space-y-2">
          {attachments.map((item) => (
            <div
              key={item.id}
              className="rounded-lg p-2.5"
              style={{
                background: "var(--input-bg)",
                border: "1px solid var(--border-color)",
              }}
            >
              <div className="flex items-start gap-2">
                <FileText size={15} className="mt-0.5 shrink-0" style={{ color: "var(--accent)" }} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-medium" style={{ color: "var(--text-primary)" }}>
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
                  <div className="mt-1 flex flex-wrap gap-1.5 text-[10px]">
                    <span className="rounded px-1.5 py-0.5" style={{ background: "var(--bg-secondary)", color: "var(--text-muted)" }}>
                      {sanitizeText(item.document_type ?? "unknown")}
                    </span>
                    <span className="rounded px-1.5 py-0.5" style={{ background: "var(--bg-secondary)", color: "var(--text-muted)" }}>
                      {formatBytes(item.file_size)}
                    </span>
                    <span className="rounded px-1.5 py-0.5" style={{ background: "var(--bg-secondary)", color: "var(--text-muted)" }}>
                      {statusLabel(item.status)}
                    </span>
                    {item.ocr_status === "pending" && (
                      <span className="rounded px-1.5 py-0.5" style={{ background: "color-mix(in srgb, var(--warning) 14%, transparent)", color: "var(--warning)" }}>
                        OCR ожидает
                      </span>
                    )}
                  </div>
                  <div className="mt-1 text-[10px] font-mono" style={{ color: "var(--text-muted)" }}>
                    {item.sha256.slice(0, 12)}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </motion.div>
  );
}
