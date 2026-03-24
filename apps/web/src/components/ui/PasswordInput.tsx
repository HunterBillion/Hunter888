"use client";

import { useState } from "react";
import { Lock, Eye, EyeOff } from "lucide-react";

interface PasswordInputProps {
  id: string;
  value: string;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  placeholder?: string;
  required?: boolean;
  minLength?: number;
  autoComplete?: string;
  ariaLabel?: string;
  ariaDescribedBy?: string;
}

/**
 * Password input with visibility toggle.
 * Includes Lock icon on the left and Eye/EyeOff toggle on the right.
 */
export function PasswordInput({
  id,
  value,
  onChange,
  placeholder,
  required = true,
  minLength,
  autoComplete,
  ariaLabel,
  ariaDescribedBy,
}: PasswordInputProps) {
  const [visible, setVisible] = useState(false);

  return (
    <div className="relative">
      <Lock
        size={16}
        className="absolute left-3.5 top-1/2 -translate-y-1/2"
        style={{ color: "var(--text-muted)" }}
      />
      <input
        id={id}
        type={visible ? "text" : "password"}
        value={value}
        onChange={onChange}
        required={required}
        minLength={minLength}
        className="vh-input pl-10 pr-10"
        placeholder={placeholder}
        autoComplete={autoComplete}
        aria-label={ariaLabel}
        aria-describedby={ariaDescribedBy}
      />
      <button
        type="button"
        onClick={() => setVisible((v) => !v)}
        className="absolute right-3 top-1/2 -translate-y-1/2 p-0.5 rounded-md transition-colors"
        style={{ color: "var(--text-muted)" }}
        aria-label={visible ? "Скрыть пароль" : "Показать пароль"}
        tabIndex={-1}
      >
        {visible ? <EyeOff size={16} /> : <Eye size={16} />}
      </button>
    </div>
  );
}
