"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Keyboard, X } from "lucide-react";
import { useFocusTrap } from "@/hooks/useFocusTrap";

interface ShortcutGroup {
  title: string;
  shortcuts: { keys: string[]; description: string }[];
}

const SHORTCUT_GROUPS: ShortcutGroup[] = [
  {
    title: "Навигация",
    shortcuts: [
      { keys: ["?"], description: "Показать горячие клавиши" },
      { keys: ["G", "H"], description: "Главная" },
      { keys: ["G", "T"], description: "Тренировки" },
      { keys: ["G", "S"], description: "Настройки" },
    ],
  },
  {
    title: "Тренировка",
    shortcuts: [
      { keys: ["Space"], description: "Удерживать — запись голоса" },
      { keys: ["Esc"], description: "Завершить сессию" },
      { keys: ["Ctrl", "M"], description: "Вкл/выкл озвучку" },
    ],
  },
  {
    title: "PvP Арена",
    shortcuts: [
      { keys: ["Space"], description: "Удерживать — запись голоса" },
      { keys: ["Esc"], description: "Выйти из арены" },
    ],
  },
  {
    title: "Общее",
    shortcuts: [
      { keys: ["Esc"], description: "Закрыть модальное окно" },
      { keys: ["Tab"], description: "Навигация по элементам" },
    ],
  },
];

export function KeyboardShortcutsOverlay() {
  const [open, setOpen] = useState(false);
  const trapRef = useFocusTrap(open, () => setOpen(false));

  // Toggle on "?" key
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Don't trigger in inputs
      const target = e.target as HTMLElement;
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable) return;

      if (e.key === "?") {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[300] flex items-center justify-center"
          style={{ background: "rgba(0,0,0,0.7)", backdropFilter: "blur(4px)" }}
          onClick={() => setOpen(false)}
        >
          <motion.div
            ref={trapRef}
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.95, opacity: 0 }}
            transition={{ type: "spring", stiffness: 400, damping: 30 }}
            className="glass-panel w-full max-w-lg mx-4 p-6 max-h-[80vh] overflow-y-auto"
            role="dialog"
            aria-modal="true"
            aria-label="Горячие клавиши"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-5">
              <div className="flex items-center gap-2">
                <Keyboard size={18} style={{ color: "var(--accent)" }} />
                <h2 className="font-display text-lg font-bold tracking-wider" style={{ color: "var(--text-primary)" }}>
                  ГОРЯЧИЕ КЛАВИШИ
                </h2>
              </div>
              <button onClick={() => setOpen(false)} aria-label="Закрыть" style={{ color: "var(--text-muted)" }}>
                <X size={18} />
              </button>
            </div>

            <div className="space-y-5">
              {SHORTCUT_GROUPS.map((group) => (
                <div key={group.title}>
                  <h3 className="font-mono text-xs tracking-widest uppercase mb-2" style={{ color: "var(--text-muted)" }}>
                    {group.title}
                  </h3>
                  <div className="space-y-1.5">
                    {group.shortcuts.map((sc, i) => (
                      <div
                        key={i}
                        className="flex items-center justify-between py-1.5 px-2 rounded-lg"
                        style={{ background: "var(--input-bg)" }}
                      >
                        <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
                          {sc.description}
                        </span>
                        <div className="flex gap-1">
                          {sc.keys.map((k, j) => (
                            <kbd
                              key={j}
                              className="inline-flex items-center justify-center min-w-[24px] h-6 px-1.5 rounded font-mono text-xs font-bold"
                              style={{
                                background: "var(--bg-tertiary)",
                                border: "1px solid var(--border-color)",
                                color: "var(--text-primary)",
                                boxShadow: "0 1px 2px rgba(0,0,0,0.2)",
                              }}
                            >
                              {k}
                            </kbd>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            <p className="mt-5 text-center text-xs font-mono" style={{ color: "var(--text-muted)" }}>
              Нажмите <kbd className="inline-flex items-center justify-center w-5 h-5 rounded font-mono text-xs font-bold mx-0.5" style={{ background: "var(--bg-tertiary)", border: "1px solid var(--border-color)", color: "var(--text-primary)" }}>?</kbd> чтобы закрыть
            </p>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
