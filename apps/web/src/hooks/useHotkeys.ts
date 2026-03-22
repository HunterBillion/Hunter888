"use client";

import { useEffect, useRef } from "react";

type HotkeyScope = "global" | "training" | "pvp";

interface HotkeyConfig {
  /** Key combo: "Space", "Escape", "ctrl+m", "ctrl+shift+s" */
  key: string;
  /** Action identifier for debugging */
  action: string;
  /** Scope — only fires when active scope matches */
  scope: HotkeyScope;
  /** Handler */
  handler: (e: KeyboardEvent) => void;
  /** Fire on keyup instead of keydown */
  keyup?: boolean;
  /** Allow in input/textarea (default: false) */
  allowInInput?: boolean;
}

/**
 * Config-driven keyboard shortcuts.
 * Context-aware: only fires when scope matches activeScope.
 * Prevents conflicts with input/textarea by default.
 *
 * Usage:
 * ```ts
 * useHotkeys("training", [
 *   { key: "Space", action: "toggleMic", scope: "training", handler: handleMicToggle },
 *   { key: "Escape", action: "abort", scope: "training", handler: handleAbort },
 *   { key: "ctrl+m", action: "muteTTS", scope: "training", handler: handleMute },
 * ]);
 * ```
 */
export function useHotkeys(activeScope: HotkeyScope, hotkeys: HotkeyConfig[]) {
  const hotkeysRef = useRef(hotkeys);
  hotkeysRef.current = hotkeys;

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      const isInput = target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable;

      for (const hk of hotkeysRef.current) {
        // Check scope
        if (hk.scope !== "global" && hk.scope !== activeScope) continue;

        // Check keyup vs keydown
        if (hk.keyup && e.type !== "keyup") continue;
        if (!hk.keyup && e.type !== "keydown") continue;

        // Skip inputs unless allowed
        if (isInput && !hk.allowInInput) continue;

        // Match key combo
        if (matchKey(e, hk.key)) {
          e.preventDefault();
          hk.handler(e);
          break;
        }
      }
    };

    window.addEventListener("keydown", handleKey);
    window.addEventListener("keyup", handleKey);
    return () => {
      window.removeEventListener("keydown", handleKey);
      window.removeEventListener("keyup", handleKey);
    };
  }, [activeScope]);
}

/**
 * Match a KeyboardEvent against a key combo string.
 * Supports: "Space", "Escape", "ctrl+m", "ctrl+shift+s", "alt+1"
 */
function matchKey(e: KeyboardEvent, combo: string): boolean {
  const parts = combo.toLowerCase().split("+");
  const key = parts.pop()!;

  const needCtrl = parts.includes("ctrl") || parts.includes("cmd") || parts.includes("meta");
  const needShift = parts.includes("shift");
  const needAlt = parts.includes("alt");

  if (needCtrl !== (e.ctrlKey || e.metaKey)) return false;
  if (needShift !== e.shiftKey) return false;
  if (needAlt !== e.altKey) return false;

  // Map key names
  const eventKey = e.code.toLowerCase();
  const keyMap: Record<string, string> = {
    space: "space",
    escape: "escape",
    enter: "enter",
    tab: "tab",
    backspace: "backspace",
  };

  // Direct code match
  if (eventKey === key || eventKey === `key${key}`) return true;
  // Mapped name match
  if (keyMap[key] && eventKey === keyMap[key]) return true;
  // e.key match (for letters)
  if (e.key.toLowerCase() === key) return true;

  return false;
}
