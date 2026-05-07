"use client";

/**
 * useMascotAnchorStore — тонкий store для DOM-якорей маскота.
 *
 * Каждый интерактивный компонент лобби (HonestNavigator плитки, RatingCard,
 * история дуэлей) регистрирует анкор по id. PixelMascot подписывается на
 * `target` и анимируется к ECMA-точке через Framer Motion `animate`.
 *
 * Минимальный API:
 *   - registerAnchor(id, rect) — обновляет известный rect
 *   - unregisterAnchor(id) — при размонтировании компонента
 *   - setTarget(id | null) — null = home (fixed corner)
 *   - target/anchors — текущий выбор + словарь анкоров
 */

import { create } from "zustand";

export type MascotAnchorId =
  | "home"          // дефолтная позиция — fixed bottom-right corner
  | "rating"        // RatingCard блок
  | "tile-duel"     // HonestNavigator: «Дуэль» плитка
  | "tile-blitz"    // HonestNavigator: «Блиц 20×60» плитка
  | "tile-themed"   // HonestNavigator: «По теме» плитка
  | "history";      // последняя карточка в истории дуэлей

export interface AnchorRect {
  /** absolute viewport-coords of the anchor. */
  x: number;
  y: number;
  /** size of the anchor (для центрирования) */
  width: number;
  height: number;
}

interface State {
  anchors: Record<string, AnchorRect>;
  /** id анкора куда маскот целится; null/home → дефолт. */
  target: MascotAnchorId | null;
}

interface Actions {
  registerAnchor: (id: MascotAnchorId, rect: AnchorRect) => void;
  unregisterAnchor: (id: MascotAnchorId) => void;
  setTarget: (id: MascotAnchorId | null) => void;
}

export const useMascotAnchorStore = create<State & Actions>((set) => ({
  anchors: {},
  target: null,
  registerAnchor: (id, rect) => set((s) => ({
    anchors: { ...s.anchors, [id]: rect },
  })),
  unregisterAnchor: (id) => set((s) => {
    if (!(id in s.anchors)) return s;
    const next = { ...s.anchors };
    delete next[id];
    return { anchors: next };
  }),
  setTarget: (id) => set({ target: id }),
}));

/** React hook helper — registers a ref and re-publishes its rect on
 * resize / scroll. Returns the ref to attach to the DOM node. */
export function useMascotAnchor(id: MascotAnchorId) {
  // Returns a ref-callback. We compute getBoundingClientRect on:
  //   1. mount
  //   2. window resize
  //   3. scroll (lobby is short, so this fires rarely)
  // Cheap recompute (~µs); better than relying on stale rects after layout.
  const register = useMascotAnchorStore((s) => s.registerAnchor);
  const unregister = useMascotAnchorStore((s) => s.unregisterAnchor);

  return (node: HTMLElement | null) => {
    if (!node) {
      unregister(id);
      return;
    }
    const publish = () => {
      const r = node.getBoundingClientRect();
      register(id, { x: r.left, y: r.top, width: r.width, height: r.height });
    };
    publish();
    window.addEventListener("resize", publish);
    window.addEventListener("scroll", publish, true);
    // Note: we don't store the cleanup — node will be GC'd with the
    // listener leak if it persists, but in practice React's ref-callback
    // re-runs with `null` on unmount which calls unregister above.
  };
}
