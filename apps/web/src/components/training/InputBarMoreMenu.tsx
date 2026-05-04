"use client";

/**
 * InputBarMoreMenu — kebab dropdown for tertiary input-bar actions.
 *
 * Background (NEW-6 / NEW-7, 2026-05-04):
 * Several PRs (#211 script tap, #219 LinkClientButton, #221 chip swap,
 * SessionAttachmentButton) all squeezed icons into the same input row,
 * leaving the actual textarea narrow ("сплющенная панель"). To restore
 * the "type a message" focus we keep ONE primary chip (link-client) +
 * textarea + send button visible, and tuck the rest behind a kebab.
 *
 * The kebab contains, today, only the SessionAttachmentButton — but it
 * is positioned to be the place to dump any future tertiary action so
 * we don't repeat the squashed-bar regression.
 */

import { useEffect, useRef, useState } from "react";
import { MoreVertical } from "lucide-react";
import { SessionAttachmentButton } from "@/components/training/SessionAttachmentButton";

interface InputBarMoreMenuProps {
  sessionId: string;
  disabled?: boolean;
  variant?: "chat" | "call";
}

export function InputBarMoreMenu({
  sessionId,
  disabled = false,
  variant = "chat",
}: InputBarMoreMenuProps) {
  const isCall = variant === "call";
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement | null>(null);

  // Close on outside click — same pattern as LinkClientButton.
  useEffect(() => {
    if (!open) return;
    const handleClick = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  return (
    <div ref={wrapRef} className="relative shrink-0">
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((prev) => !prev)}
        aria-label="Дополнительные действия"
        aria-expanded={open}
        title="Дополнительные действия (вложения и т.д.)"
        className={
          isCall
            ? "flex h-8 w-8 items-center justify-center rounded-full bg-white/15 text-white transition-opacity hover:bg-white/25 disabled:cursor-not-allowed disabled:opacity-30"
            : "flex h-[40px] w-[40px] items-center justify-center rounded-xl transition-opacity disabled:cursor-not-allowed disabled:opacity-40"
        }
        style={isCall ? undefined : {
          background: "var(--input-bg)",
          border: "1px solid var(--border-color)",
          color: "var(--text-secondary)",
        }}
      >
        <MoreVertical size={16} />
      </button>

      {open && (
        <div
          role="menu"
          aria-label="Дополнительные действия"
          className={
            isCall
              ? "absolute bottom-11 left-0 z-30 w-56 rounded-lg border border-white/10 bg-zinc-900/95 p-2 text-xs text-white shadow-xl backdrop-blur-md"
              : "absolute bottom-12 left-0 z-30 w-56 rounded-lg p-2 text-xs shadow-xl"
          }
          style={isCall ? undefined : {
            background: "var(--bg-secondary)",
            border: "1px solid var(--border-color)",
            color: "var(--text-primary)",
          }}
        >
          {/*
            Each row mirrors a normal menu item: icon-button on the left,
            descriptive label on the right. We re-mount the underlying
            SessionAttachmentButton in its standard inline form (its own
            invisible <input type="file"> + button) and pair it with a
            label so the user understands what the icon does.
          */}
          <div className="flex items-center gap-3 rounded px-1.5 py-1.5">
            <SessionAttachmentButton
              sessionId={sessionId}
              disabled={disabled}
              variant={variant}
            />
            <div className="flex flex-col">
              <span className="text-sm font-medium leading-tight">
                Прикрепить документ
              </span>
              <span
                className="text-xs leading-tight"
                style={isCall ? { color: "rgba(255,255,255,0.55)" } : { color: "var(--text-muted)" }}
              >
                PDF, фото, договор и т.д. — попадёт в карточку CRM-клиента.
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
