"use client";

import { useState, useRef, useCallback, useEffect } from "react";

/**
 * Custom Kanban drag-and-drop hook — works on desktop (HTML5 DnD) + mobile (touch events).
 *
 * Architecture:
 * - Desktop: HTML5 drag events → dataTransfer
 * - Mobile:  Touch events with 200ms long-press activation → manual hit-testing
 * - Both:    Produce the same callbacks (onDragStart, onDragEnd, isDragging, activeId, overColumn)
 *
 * Touch UX details:
 * - Long-press (200ms) to start drag — prevents scroll hijacking
 * - Visual clone follows finger
 * - Column hit-testing via getBoundingClientRect
 * - Haptic feedback on activation (navigator.vibrate)
 * - Auto-scroll near edges
 */

export interface DragState {
  /** Currently dragged item ID. */
  activeId: string | null;
  /** Column (status) the dragged item is currently over. */
  overColumn: string | null;
  /** Touch-drag clone position for overlay rendering. */
  clonePos: { x: number; y: number } | null;
  /** Whether touch drag mode is active (vs HTML5). */
  isTouchDrag: boolean;
}

interface UseKanbanDragOptions {
  /** Called when a drag operation successfully completes over a valid column. */
  onDrop: (itemId: string, targetColumn: string) => void;
  /** Column element refs for hit-testing. Map of status → element. */
  columnRefs: React.MutableRefObject<Map<string, HTMLElement>>;
}

export function useKanbanDrag({ onDrop, columnRefs }: UseKanbanDragOptions) {
  const [state, setState] = useState<DragState>({
    activeId: null,
    overColumn: null,
    clonePos: null,
    isTouchDrag: false,
  });

  const longPressTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const touchStartPos = useRef<{ x: number; y: number } | null>(null);
  const scrollContainerRef = useRef<HTMLElement | null>(null);
  const autoScrollRAF = useRef<number | null>(null);

  // ── HTML5 Drag (Desktop) ──

  const handleDragStart = useCallback((itemId: string, e: React.DragEvent) => {
    e.dataTransfer.setData("text/plain", itemId);
    e.dataTransfer.effectAllowed = "move";
    setState({ activeId: itemId, overColumn: null, clonePos: null, isTouchDrag: false });
  }, []);

  const handleDragOver = useCallback((column: string, e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    setState((prev) => (prev.overColumn === column ? prev : { ...prev, overColumn: column }));
  }, []);

  const handleDragLeave = useCallback((_column: string) => {
    setState((prev) => ({ ...prev, overColumn: null }));
  }, []);

  const handleDrop = useCallback(
    (column: string, e: React.DragEvent) => {
      e.preventDefault();
      const itemId = e.dataTransfer.getData("text/plain");
      if (itemId) onDrop(itemId, column);
      setState({ activeId: null, overColumn: null, clonePos: null, isTouchDrag: false });
    },
    [onDrop],
  );

  const handleDragEnd = useCallback(() => {
    setState({ activeId: null, overColumn: null, clonePos: null, isTouchDrag: false });
  }, []);

  // ── Touch Drag (Mobile) ──

  const hitTestColumn = useCallback(
    (x: number, y: number): string | null => {
      for (const [status, el] of columnRefs.current.entries()) {
        const rect = el.getBoundingClientRect();
        if (x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom) {
          return status;
        }
      }
      return null;
    },
    [columnRefs],
  );

  // Auto-scroll when dragging near edges of scroll container
  const startAutoScroll = useCallback((clientX: number) => {
    const container = scrollContainerRef.current;
    if (!container) return;

    const cancelAutoScroll = () => {
      if (autoScrollRAF.current) {
        cancelAnimationFrame(autoScrollRAF.current);
        autoScrollRAF.current = null;
      }
    };

    cancelAutoScroll();

    const rect = container.getBoundingClientRect();
    const edgeZone = 60;
    const leftDist = clientX - rect.left;
    const rightDist = rect.right - clientX;

    let speed = 0;
    if (leftDist < edgeZone) speed = -Math.max(2, (edgeZone - leftDist) / 4);
    else if (rightDist < edgeZone) speed = Math.max(2, (edgeZone - rightDist) / 4);

    if (speed !== 0) {
      const scroll = () => {
        container.scrollLeft += speed;
        autoScrollRAF.current = requestAnimationFrame(scroll);
      };
      autoScrollRAF.current = requestAnimationFrame(scroll);
    }
  }, []);

  const handleTouchStart = useCallback(
    (itemId: string, e: React.TouchEvent) => {
      const touch = e.touches[0];
      touchStartPos.current = { x: touch.clientX, y: touch.clientY };

      longPressTimer.current = setTimeout(() => {
        // Haptic feedback
        if (navigator.vibrate) navigator.vibrate(30);

        setState({
          activeId: itemId,
          overColumn: null,
          clonePos: { x: touch.clientX, y: touch.clientY },
          isTouchDrag: true,
        });
      }, 200);
    },
    [],
  );

  const handleTouchMove = useCallback(
    (e: React.TouchEvent) => {
      const touch = e.touches[0];

      // Cancel long-press if moved too far before activation
      if (longPressTimer.current && touchStartPos.current) {
        const dx = touch.clientX - touchStartPos.current.x;
        const dy = touch.clientY - touchStartPos.current.y;
        if (Math.sqrt(dx * dx + dy * dy) > 10) {
          clearTimeout(longPressTimer.current);
          longPressTimer.current = null;
        }
      }

      if (!state.isTouchDrag) return;

      e.preventDefault(); // Prevent scroll during drag

      const column = hitTestColumn(touch.clientX, touch.clientY);
      startAutoScroll(touch.clientX);

      setState((prev) => ({
        ...prev,
        clonePos: { x: touch.clientX, y: touch.clientY },
        overColumn: column,
      }));
    },
    [state.isTouchDrag, hitTestColumn, startAutoScroll],
  );

  const handleTouchEnd = useCallback(() => {
    if (longPressTimer.current) {
      clearTimeout(longPressTimer.current);
      longPressTimer.current = null;
    }
    if (autoScrollRAF.current) {
      cancelAnimationFrame(autoScrollRAF.current);
      autoScrollRAF.current = null;
    }

    if (state.isTouchDrag && state.activeId && state.overColumn) {
      onDrop(state.activeId, state.overColumn);
    }

    setState({ activeId: null, overColumn: null, clonePos: null, isTouchDrag: false });
  }, [state, onDrop]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (longPressTimer.current) clearTimeout(longPressTimer.current);
      if (autoScrollRAF.current) cancelAnimationFrame(autoScrollRAF.current);
    };
  }, []);

  return {
    state,
    scrollContainerRef,
    // Desktop HTML5 DnD
    handleDragStart,
    handleDragOver,
    handleDragLeave,
    handleDrop,
    handleDragEnd,
    // Touch DnD
    handleTouchStart,
    handleTouchMove,
    handleTouchEnd,
  };
}
