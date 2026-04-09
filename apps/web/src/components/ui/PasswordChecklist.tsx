"use client";

import { motion } from "framer-motion";
import { Check, X } from "lucide-react";

export interface PasswordRule {
  id: string;
  label: string;
  test: (v: string) => boolean;
}

export const PASSWORD_RULES: PasswordRule[] = [
  { id: "len",     label: "Минимум 8 символов",          test: (v) => v.length >= 8 },
  { id: "upper",   label: "Заглавная буква (A–Z)",        test: (v) => /[A-Z]/.test(v) },
  { id: "lower",   label: "Строчная буква (a–z)",         test: (v) => /[a-z]/.test(v) },
  { id: "digit",   label: "Цифра (0–9)",                  test: (v) => /[0-9]/.test(v) },
  { id: "special", label: "Спецсимвол (!@#$%^&*...)",     test: (v) => /[!@#$%^&*()\-_=+\[\]{}|;:'",.<>?/\\`~]/.test(v) },
];

/**
 * Checks all PASSWORD_RULES against `value` and returns
 * true only if every rule passes.
 */
export function isPasswordValid(value: string): boolean {
  return PASSWORD_RULES.every((r) => r.test(value));
}

interface Props {
  value: string;
  className?: string;
}

/**
 * Live password-requirements checklist.
 * Shows each requirement with a green check when satisfied.
 */
export function PasswordChecklist({ value, className = "" }: Props) {
  if (!value) return null;

  return (
    <motion.ul
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      className={`mt-2 space-y-1 ${className}`}
      aria-live="polite"
    >
      {PASSWORD_RULES.map(({ id, label, test }) => {
        const ok = test(value);
        return (
          <li
            key={id}
            className="flex items-center gap-2 text-xs transition-colors duration-200"
            style={{ color: ok ? "var(--success)" : "var(--text-muted)" }}
          >
            <span
              className="flex-shrink-0 w-3.5 h-3.5 rounded-full flex items-center justify-center"
              style={{
                background: ok ? "rgba(61,220,132,0.15)" : "var(--bg-tertiary)",
                border: `1px solid ${ok ? "rgba(61,220,132,0.35)" : "var(--border-color)"}`,
                transition: "background 0.2s, border-color 0.2s",
              }}
            >
              {ok ? (
                <Check size={8} strokeWidth={3} />
              ) : (
                <X size={8} strokeWidth={2.5} style={{ color: "var(--border-color)" }} />
              )}
            </span>
            {label}
          </li>
        );
      })}
    </motion.ul>
  );
}
