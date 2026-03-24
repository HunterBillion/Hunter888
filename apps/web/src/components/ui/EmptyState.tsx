"use client";

import { motion } from "framer-motion";
import type { LucideIcon } from "lucide-react";
import { Inbox } from "lucide-react";

interface EmptyStateProps {
  icon?: LucideIcon;
  title: string;
  description?: string;
  actionLabel?: string;
  onAction?: () => void;
  className?: string;
}

/**
 * Reusable empty-state placeholder with optional CTA.
 *
 * Usage:
 *   <EmptyState
 *     icon={Users}
 *     title="Пока нет клиентов"
 *     description="Добавьте первого клиента для начала работы"
 *     actionLabel="Добавить клиента"
 *     onAction={() => setShowModal(true)}
 *   />
 */
export function EmptyState({
  icon: Icon = Inbox,
  title,
  description,
  actionLabel,
  onAction,
  className = "",
}: EmptyStateProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className={`flex flex-col items-center text-center py-16 ${className}`}
    >
      <div
        className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl"
        style={{ background: "var(--accent-muted)" }}
      >
        <Icon size={28} style={{ color: "var(--accent)", opacity: 0.7 }} />
      </div>
      <h3
        className="font-display text-sm font-bold tracking-wider uppercase"
        style={{ color: "var(--text-primary)" }}
      >
        {title}
      </h3>
      {description && (
        <p className="mt-1.5 text-xs max-w-xs" style={{ color: "var(--text-muted)" }}>
          {description}
        </p>
      )}
      {actionLabel && onAction && (
        <motion.button
          onClick={onAction}
          className="vh-btn-primary mt-5 flex items-center gap-2 text-xs"
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.97 }}
        >
          {actionLabel}
        </motion.button>
      )}
    </motion.div>
  );
}
