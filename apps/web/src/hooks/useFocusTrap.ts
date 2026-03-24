"use client";

import { useEffect, useRef } from "react";

/**
 * Focus trap for modal dialogs.
 * Traps Tab/Shift+Tab within the referenced element and restores focus on unmount.
 * Also closes on Escape key press if onEscape callback is provided.
 */
export function useFocusTrap(active: boolean, onEscape?: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  const previousFocus = useRef<Element | null>(null);

  useEffect(() => {
    if (!active) return;

    // Save current focus to restore later
    previousFocus.current = document.activeElement;

    // Focus the first focusable element inside the trap
    const el = ref.current;
    if (!el) return;

    const focusFirst = () => {
      const focusable = getFocusableElements(el);
      if (focusable.length > 0) {
        (focusable[0] as HTMLElement).focus();
      } else {
        // Fallback: focus the container itself
        el.setAttribute("tabindex", "-1");
        el.focus();
      }
    };

    // Small delay to allow animation to complete
    const timer = setTimeout(focusFirst, 50);

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && onEscape) {
        e.preventDefault();
        onEscape();
        return;
      }

      if (e.key !== "Tab") return;

      const focusable = getFocusableElements(el);
      if (focusable.length === 0) return;

      const first = focusable[0] as HTMLElement;
      const last = focusable[focusable.length - 1] as HTMLElement;

      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault();
          last.focus();
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };

    document.addEventListener("keydown", handleKeyDown);

    return () => {
      clearTimeout(timer);
      document.removeEventListener("keydown", handleKeyDown);
      // Restore previous focus
      if (previousFocus.current instanceof HTMLElement) {
        previousFocus.current.focus();
      }
    };
  }, [active, onEscape]);

  return ref;
}

function getFocusableElements(container: HTMLElement): NodeListOf<Element> {
  return container.querySelectorAll(
    'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
  );
}
