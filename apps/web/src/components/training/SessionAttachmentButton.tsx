"use client";

import { useRef, useState } from "react";
import { AlertCircle, Loader2, Paperclip } from "lucide-react";
import { ApiError, api } from "@/lib/api";
import { sanitizeText } from "@/lib/sanitize";
import type { ClientAttachment } from "@/types";

interface SessionAttachmentButtonProps {
  sessionId: string;
  disabled?: boolean;
  variant?: "chat" | "call";
  onUploaded?: (attachment: ClientAttachment) => void;
}

const ACCEPTED_ATTACHMENT_TYPES = [
  ".pdf",
  ".png",
  ".jpg",
  ".jpeg",
  ".webp",
  ".heic",
  ".tiff",
  ".doc",
  ".docx",
  ".rtf",
  ".odt",
  ".xls",
  ".xlsx",
  ".csv",
  "image/*",
  "application/pdf",
].join(",");

export function SessionAttachmentButton({
  sessionId,
  disabled = false,
  variant = "chat",
  onUploaded,
}: SessionAttachmentButtonProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFile = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || disabled || uploading) return;

    setUploading(true);
    setError(null);
    try {
      const attachment = await api.upload<ClientAttachment>(
        `/training/sessions/${sessionId}/attachments`,
        file,
      );
      onUploaded?.(attachment);
    } catch (err) {
      const msg = err instanceof ApiError || err instanceof Error
        ? err.message
        : "Не удалось загрузить файл";
      setError(msg);
    } finally {
      setUploading(false);
    }
  };

  const isCall = variant === "call";

  return (
    <div className="relative shrink-0">
      <input
        ref={inputRef}
        type="file"
        className="hidden"
        accept={ACCEPTED_ATTACHMENT_TYPES}
        onChange={handleFile}
      />
      <button
        type="button"
        disabled={disabled || uploading}
        onClick={() => inputRef.current?.click()}
        aria-label="Прикрепить документ"
        title="Прикрепить документ к сессии и CRM"
        className={
          isCall
            ? "flex h-8 w-8 items-center justify-center rounded-full bg-white/15 text-white transition-opacity hover:bg-white/25 disabled:cursor-not-allowed disabled:opacity-30"
            : "flex h-[40px] w-[40px] items-center justify-center rounded-xl transition-opacity disabled:cursor-not-allowed disabled:opacity-40"
        }
        style={isCall ? undefined : {
          background: "var(--input-bg)",
          border: "1px solid var(--border-color)",
          color: "var(--accent)",
        }}
      >
        {uploading ? <Loader2 size={16} className="animate-spin" /> : <Paperclip size={16} />}
      </button>
      {error && (
        <div
          className={
            isCall
              ? "absolute bottom-11 left-0 z-30 w-64 rounded-lg border border-red-400/30 bg-red-950/90 p-2 text-xs text-red-100 shadow-xl"
              : "absolute bottom-12 left-0 z-30 flex w-64 items-start gap-2 rounded-lg p-2 text-xs shadow-xl"
          }
          style={isCall ? undefined : {
            background: "color-mix(in srgb, var(--danger) 14%, var(--bg-secondary))",
            border: "1px solid color-mix(in srgb, var(--danger) 30%, transparent)",
            color: "var(--danger)",
          }}
        >
          <AlertCircle size={13} className="mt-0.5 shrink-0" />
          <span>{sanitizeText(error)}</span>
        </div>
      )}
    </div>
  );
}
