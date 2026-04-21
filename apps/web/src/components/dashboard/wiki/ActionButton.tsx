"use client";

import { Loader2, Play } from "lucide-react";

export function ActionButton({
  icon: Icon,
  label,
  onClick,
  loading,
  color = "var(--warning)",
  disabled = false,
}: {
  icon: React.ComponentType<Record<string, unknown>>;
  label: string;
  onClick: () => void;
  loading: boolean;
  color?: string;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={loading || disabled}
      style={{
        display: "flex",
        alignItems: "center",
        gap: "0.4rem",
        padding: "0.4rem 0.75rem",
        background: `${color}15`,
        border: `1px solid ${color}33`,
        borderRadius: 8,
        color: loading || disabled ? "var(--text-muted)" : color,
        cursor: loading || disabled ? "not-allowed" : "pointer",
        fontSize: "0.875rem",
        fontWeight: 500,
        opacity: disabled ? 0.5 : 1,
      }}
    >
      {loading ? <Loader2 size={14} style={{ animation: "spin 1s linear infinite" }} /> : <Icon size={14} weight="duotone" />}
      {label}
    </button>
  );
}
