"use client";

import { motion } from "framer-motion";
import { AlertTriangle } from "lucide-react";
import Link from "next/link";

interface DuplicateWarningProps {
  message: string;
  duplicateIds: string[];
  onDismiss: () => void;
}

export function DuplicateWarning({ message, duplicateIds, onDismiss }: DuplicateWarningProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-xl p-4 mb-4"
      style={{
        background: "rgba(212,168,75,0.08)",
        border: "1px solid rgba(212,168,75,0.25)",
      }}
    >
      <div className="flex items-start gap-3">
        <AlertTriangle size={18} className="shrink-0 mt-0.5" style={{ color: "var(--warning)" }} />
        <div className="flex-1">
          <div className="text-sm font-medium" style={{ color: "var(--warning)" }}>
            Возможный дубликат
          </div>
          <p className="text-xs mt-1" style={{ color: "var(--text-secondary)" }}>
            {message}
          </p>
          {duplicateIds.length > 0 && (
            <div className="flex flex-wrap gap-2 mt-2">
              {duplicateIds.map((id) => (
                <Link
                  key={id}
                  href={`/clients/${id}`}
                  className="text-xs font-mono px-2 py-1 rounded-lg transition-colors"
                  style={{
                    background: "rgba(212,168,75,0.1)",
                    color: "var(--warning)",
                    border: "1px solid rgba(212,168,75,0.2)",
                  }}
                >
                  Карточка #{id.slice(0, 8)}
                </Link>
              ))}
            </div>
          )}
          <motion.button
            onClick={onDismiss}
            className="text-xs font-mono mt-2"
            style={{ color: "var(--text-muted)" }}
            whileTap={{ scale: 0.97 }}
          >
            Скрыть предупреждение
          </motion.button>
        </div>
      </div>
    </motion.div>
  );
}
