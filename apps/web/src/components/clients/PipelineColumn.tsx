"use client";

import { useCallback, forwardRef } from "react";
import { ClipboardList, Plus, GripVertical } from "lucide-react";
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
  onInlineEdit?: (clientId: string, patch: Partial<CRMClient>) => Promise<void>;
  onAddClient?: (status: ClientStatus) => void;
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
      onInlineEdit,
      onAddClient,
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
          boxShadow: isOver
            ? `0 0 20px color-mix(in srgb, ${color} 15%, transparent)`
            : "none",
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
                boxShadow: `0 0 6px color-mix(in srgb, ${color} 50%, transparent)`,
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
                  background: `color-mix(in srgb, ${color} 10%, transparent)`,
                  color: color,
                  border: `1px solid color-mix(in srgb, ${color} 20%, transparent)`,
                }}
              >
                {debtLabel} &#8381;
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

        {/* Drop indicator when dragging over */}
        <AnimatePresence>
          {isOver && activeId && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="mx-2 mt-2 rounded-lg border-2 border-dashed py-4 text-center"
              style={{
                borderColor: color,
                background: `color-mix(in srgb, ${color} 5%, transparent)`,
              }}
            >
              <span className="text-xs font-mono" style={{ color }}>
                Отпустите здесь
              </span>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Cards */}
        <div className="flex-1 p-2 space-y-1.5 overflow-y-auto scrollbar-thin">
          <AnimatePresence mode="popLayout">
            {clients.map((client) => (
              <motion.div
                key={client.id}
                layout
                initial={{ opacity: 0, scale: 0.92, y: 12 }}
                animate={{
                  opacity: activeId === client.id ? 0.3 : 1,
                  scale: activeId === client.id ? 0.95 : 1,
                  y: 0,
                }}
                exit={{ opacity: 0, scale: 0.9, y: -8 }}
                transition={{
                  layout: { type: "spring", stiffness: 350, damping: 30 },
                  opacity: { duration: 0.2 },
                  scale: { duration: 0.2 },
                }}
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
                {/* Drag handle hint */}
                {!readOnly && (
                  <div
                    className="flex items-center justify-center h-0 overflow-visible relative"
                    style={{ zIndex: 1 }}
                  >
                    <div className="absolute -top-0 opacity-0 group-hover:opacity-30 transition-opacity">
                      <GripVertical size={10} style={{ color: "var(--text-muted)" }} />
                    </div>
                  </div>
                )}
                <PipelineCard
                  client={client}
                  userRole={userRole}
                  readOnly={readOnly}
                  visibleFields={visibleFields}
                  onQuickNote={onQuickNote}
                  onReminder={onReminder}
                  onInlineNoteSubmit={onInlineNoteSubmit}
                  onInlineEdit={onInlineEdit}
                />
              </motion.div>
            ))}
          </AnimatePresence>

          {/* Empty state */}
          {!clients.length && !isOver && (
            <div className="text-center py-6 px-3">
              <div
                className="mx-auto mb-2 flex h-10 w-10 items-center justify-center rounded-lg"
                style={{
                  background: `color-mix(in srgb, ${color} 8%, transparent)`,
                  border: `1px solid color-mix(in srgb, ${color} 15%, transparent)`,
                }}
              >
                <ClipboardList size={16} style={{ color, opacity: 0.6 }} />
              </div>
              <span
                className="text-xs font-mono block"
                style={{ color: "var(--text-muted)", opacity: 0.6 }}
              >
                Нет клиентов
              </span>
              {!readOnly && onAddClient && (
                <motion.button
                  type="button"
                  onClick={() => onAddClient(status)}
                  className="mt-3 inline-flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors"
                  style={{
                    background: `color-mix(in srgb, ${color} 10%, transparent)`,
                    color: color,
                    border: `1px solid color-mix(in srgb, ${color} 20%, transparent)`,
                  }}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.97 }}
                >
                  <Plus size={12} />
                  Добавить клиента
                </motion.button>
              )}
            </div>
          )}

          {/* Add client button at bottom of non-empty columns */}
          {!readOnly && onAddClient && clients.length > 0 && (
            <motion.button
              type="button"
              onClick={() => onAddClient(status)}
              className="w-full mt-1 flex items-center justify-center gap-1 rounded-lg py-2 text-xs font-medium transition-colors border border-dashed"
              style={{
                borderColor: "var(--border-color)",
                color: "var(--text-muted)",
                opacity: 0.5,
              }}
              whileHover={{
                opacity: 0.9,
                borderColor: color,
              }}
              whileTap={{ scale: 0.98 }}
            >
              <Plus size={10} />
              Добавить
            </motion.button>
          )}
        </div>
      </div>
    );
  },
);
