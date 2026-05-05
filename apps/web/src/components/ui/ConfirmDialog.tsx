"use client";

/**
 * ConfirmDialog — controlled wrapper around AlertDialog for the
 * "are you sure?" pattern. Replaces window.confirm() in destructive
 * flows so:
 *   - the dialog renders inside our theme (browser-native confirm
 *     looks broken on iOS Safari and ignores CSP);
 *   - the consumer can describe consequences with rich text instead
 *     of a single line;
 *   - long-running confirms can show a busy state without freezing
 *     the UI thread (which window.confirm does);
 *   - keyboard a11y comes from Radix (Esc, focus trap, restore).
 */

import * as React from "react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/AlertDialog";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  /** When true, the action button is rendered with the danger style. */
  destructive?: boolean;
  /** Disables both buttons; shows the confirm button as busy. */
  busy?: boolean;
  onConfirm: () => void;
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = "Подтвердить",
  cancelLabel = "Отмена",
  destructive = false,
  busy = false,
  onConfirm,
}: Props) {
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div>{description}</div>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={busy}>{cancelLabel}</AlertDialogCancel>
          <AlertDialogAction
            disabled={busy}
            onClick={(e) => {
              // Don't auto-close on click — let the caller decide so
              // an in-flight request can keep the modal open and
              // surface an error inline.
              e.preventDefault();
              onConfirm();
            }}
            style={
              destructive
                ? { background: "var(--danger)", color: "#fff" }
                : { background: "var(--accent)", color: "#000" }
            }
          >
            {busy ? "…" : confirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
