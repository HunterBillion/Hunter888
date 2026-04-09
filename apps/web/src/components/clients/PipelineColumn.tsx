"use client";

import { useCallback, forwardRef } from "react";
import { ClipboardList } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import type { CRMClient, ClientStatus, UserRole } from "@/types";
import { CLIENT_STATUS_LABELS, CLIENT_STATUS_COLORS } from "@/types";
import { PipelineCard, type PipelineCardField } from "./PipelineCard";

interface PipelineColumnProps {
  status: ClientStatus;
  clients: CRMClient[];
  isOver: boolean;
  activeId: string | null;
  userRole?: UserRole;
  readOnly?: boolean;
  layoutMode?: "grid" | "board";
  visibleFields?: PipelineCardField[];
  onQuickNote?: (client: CRMClient) => void;
  onReminder?: (client: CRMClient) => void;
  onInlineNoteSubmit?: (client: CRMClient, text: string) => Promise<void>;
  // HTML5 DnD handlers (desktop)
  onDragOver: (status: string, e: React.DragEvent) => void;
  onDragLeave: (status: string) => void;
  onDrop: (status: string, e: React.DragEvent) => void;
  onDragStart: (id: string, e: React.DragEvent) => void;
  onDragEnd: () => void;
  // Touch DnD handlers (mobile)
  onTouchStart: (id: string, e: React.TouchEvent) => void;
  onTouchMove: (e: React.TouchEvent) => void;
  onTouchEnd: () => void;
}

export const PipelineColumn = forwardRef<HTMLDivElement, PipelineColumnProps>(
  function PipelineColumn(
    {
      status,
      clients,
      isOver,
      activeId,
      userRole,
      readOnly = false,
      layoutMode = "grid",
      visibleFields,
      onQuickNote,
      onReminder,
      onInlineNoteSubmit,
      onDragOver,
      onDragLeave,
      onDrop,
      onDragStart,
      onDragEnd,
      onTouchStart,
      onTouchMove,
      onTouchEnd,
    },
    ref,
  ) {
    const color = CLIENT_STATUS_COLORS[status];
    const label = CLIENT_STATUS_LABELS[status];

    const handleDragOver = useCallback(
      (e: React.DragEvent) => onDragOver(status, e),
      [onDragOver, status],
    );
    const handleDragLeave = useCallback(
      () => onDragLeave(status),
      [onDragLeave, status],
    );
    const handleDrop = useCallback(
      (e: React.DragEvent) => onDrop(status, e),
      [onDrop, status],
    );

    const totalDebt = clients.reduce((sum, c) => sum + (c.debt_amount ?? 0), 0);
    const debtLabel =
      totalDebt >= 1_000_000
        ? `${(totalDebt / 1_000_000).toFixed(1)}M`
        : totalDebt >= 1_000
          ? `${(totalDebt / 1_000).toFixed(0)}K`
          : String(totalDebt);

    return (
      <div
        ref={ref}
        className="flex flex-col rounded-xl transition-all duration-200"
        style={{
          width: layoutMode === "board" ? "300px" : "100%",
          minWidth: layoutMode === "board" ? "300px" : 0,
          maxHeight: "min(70vh, calc(100vh - 220px))",
          background: isOver
            ? `color-mix(in srgb, ${color} 6%, var(--bg-secondary))`
            : "var(--bg-secondary)",
          border: `1px solid ${isOver ? color : "var(--border-color)"}`,
          boxShadow: isOver ? `0 0 20px ${color}15` : "none",
        }}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {/* Column header */}
        <div
          className="flex items-center justify-between px-3 py-3 border-b shrink-0"
          style={{ borderColor: "var(--border-color)" }}
        >
          <div className="flex items-center gap-2">
            <div
              className="w-2.5 h-2.5 rounded-full shrink-0"
              style={{
                background: color,
                boxShadow: `0 0 6px ${color}80`,
              }}
            />
            <span
              className="text-xs font-mono font-semibold uppercase tracking-wider"
              style={{ color: "var(--text-primary)" }}
            >
              {label}
            </span>
          </div>
          <div className="flex items-center gap-2">
            {totalDebt > 0 && (
              <span
                className="text-xs font-mono px-1.5 py-0.5 rounded"
                style={{
                  background: `${color}10`,
                  color: `${color}`,
                  border: `1px solid ${color}20`,
                }}
              >
                {debtLabel} ₽
              </span>
            )}
            <span
              className="text-xs font-mono font-bold min-w-[20px] text-center px-1.5 py-0.5 rounded-full"
              style={{
                background: "var(--input-bg)",
                color: clients.length > 0 ? color : "var(--text-muted)",
              }}
            >
              {clients.length}
            </span>
          </div>
        </div>

        {/* Drop indicator when empty + dragging over */}
        {isOver && clients.length === 0 && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="mx-2 mt-2 rounded-lg border-2 border-dashed py-6 text-center"
            style={{ borderColor: color, background: `${color}08` }}
          >
            <span className="text-xs font-mono" style={{ color }}>
              Отпустите здесь
            </span>
          </motion.div>
        )}

        {/* Cards */}
        <div className="flex-1 p-2 space-y-1.5 overflow-y-auto scrollbar-thin">
          <AnimatePresence mode="popLayout">
            {clients.map((client) => (
              <motion.div
                key={client.id}
                layout
                initial={{ opacity: 0, scale: 0.95, y: 8 }}
                animate={{
                  opacity: activeId === client.id ? 0.4 : 1,
                  scale: 1,
                  y: 0,
                }}
                exit={{ opacity: 0, scale: 0.95 }}
                transition={{ duration: 0.15 }}
                draggable={!readOnly}
                onDragStart={readOnly ? undefined : (e) =>
                  onDragStart(
                    client.id,
                    e as unknown as React.DragEvent,
                  )
                }
                onDragEnd={readOnly ? undefined : onDragEnd}
                onTouchStart={readOnly ? undefined : (e) =>
                  onTouchStart(
                    client.id,
                    e as unknown as React.TouchEvent,
                  )
                }
                onTouchMove={readOnly ? undefined : (e) =>
                  onTouchMove(e as unknown as React.TouchEvent)
                }
                onTouchEnd={readOnly ? undefined : onTouchEnd}
                className={readOnly ? "" : "cursor-grab active:cursor-grabbing touch-none"}
              >
                <PipelineCard
                  client={client}
                  userRole={userRole}
                  readOnly={readOnly}
                  visibleFields={visibleFields}
                  onQuickNote={onQuickNote}
                  onReminder={onReminder}
                  onInlineNoteSubmit={onInlineNoteSubmit}
                />
              </motion.div>
            ))}
          </AnimatePresence>

          {!clients.length && !isOver && (
            <div className="text-center py-6 px-3">
              <div className="text-base opacity-30 mb-1.5"><ClipboardList size={18} /></div>
              <span className="text-xs font-mono" style={{ color: "var(--text-muted)", opacity: 0.6 }}>
                Нет клиентов
              </span>
            </div>
          )}
        </div>
      </div>
    );
  },
);
