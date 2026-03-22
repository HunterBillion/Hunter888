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
        background: "rgba(255,215,0,0.08)",
        border: "1px solid rgba(255,215,0,0.25)",
      }}
    >
      <div className="flex items-start gap-3">
        <AlertTriangle size={18} className="shrink-0 mt-0.5" style={{ color: "#FFD700" }} />
        <div className="flex-1">
          <div className="text-sm font-medium" style={{ color: "#FFD700" }}>
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
                  className="text-[10px] font-mono px-2 py-1 rounded-lg transition-colors"
                  style={{
                    background: "rgba(255,215,0,0.1)",
                    color: "#FFD700",
                    border: "1px solid rgba(255,215,0,0.2)",
                  }}
                >
                  Карточка #{id.slice(0, 8)}
                </Link>
              ))}
            </div>
          )}
          <motion.button
            onClick={onDismiss}
            className="text-[10px] font-mono mt-2"
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
