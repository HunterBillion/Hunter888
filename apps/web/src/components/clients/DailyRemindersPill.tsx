"use client";

/**
 * DailyRemindersPill — compact "today's reminders" badge for the /home hero.
 *
 * Rendering rules:
 *   * Fetches GET /reminders on mount, filters to items whose remind_at
 *     falls on today's local calendar day.
 *   * If 0 reminders → renders nothing (stays out of the way).
 *   * If ≥1 reminders → renders a small pill showing the next due one
 *     (time + +N suffix when there are more). Click / Enter / Space opens
 *     a popover listing up to 5 items with overdue highlighting.
 *
 * Replaces the full-width `ReminderWidget` block that used to sit below
 * all the home-page panels. 80 %+ of users never scrolled far enough to
 * see it — so moving it into the hero as an affordance is both more
 * visible and less visually heavy.
 */

import { useState, useEffect, useRef, useMemo, useLayoutEffect } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import Link from "next/link";
import { Clock, ChevronRight, ChevronDown, Phone, X } from "lucide-react";
import { api } from "@/lib/api";
import { sanitizeText } from "@/lib/sanitize";
import { logger } from "@/lib/logger";
import type { ReminderItem } from "@/types";

/** Pure helper — is `iso` today's local day? */
function isToday(iso: string): boolean {
  const d = new Date(iso);
  const now = new Date();
  return (
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  );
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function DailyRemindersPill() {
  const [reminders, setReminders] = useState<ReminderItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const pillRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);

  // Fetch once on mount. Could be revalidated on `goals:refresh` later if
  // we wire reminders into that event bus — not doing it yet because
  // reminders change rarely during a session.
  useEffect(() => {
    let cancelled = false;
    api
      .get<ReminderItem[]>("/reminders")
      .then((data) => {
        if (cancelled) return;
        setReminders(data.filter((r) => isToday(r.remind_at)));
      })
      .catch((err) => {
        if (!cancelled) logger.error("DailyRemindersPill load failed:", err);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Close on outside click + Esc. The popover now lives in a portal, so
  // we have to check BOTH the trigger pill and the popover element —
  // `wrapperRef` only covers the pill.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      const target = e.target as Node;
      const insidePill = wrapperRef.current?.contains(target);
      const insidePopover = popoverRef.current?.contains(target);
      if (!insidePill && !insidePopover) {
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  // Position the portal-rendered popover under the pill. useLayoutEffect
  // runs BEFORE paint so there's no flash of un-positioned popover.
  // Width stays bounded to min(320, viewport - 24) and the popover is
  // right-aligned with the pill (like before), but clamped inside the
  // viewport when the pill is close to the right edge.
  useLayoutEffect(() => {
    if (!open || !pillRef.current) return;
    const rect = pillRef.current.getBoundingClientRect();
    const popoverWidth = Math.min(320, window.innerWidth - 24);
    // Prefer right-align to pill (same visual behaviour as before). If
    // that would put the popover off-screen on the left, clamp to 12 px
    // from the left edge.
    let left = rect.right - popoverWidth;
    if (left < 12) left = 12;
    const top = rect.bottom + 8;
    setPos({ top, left });
  }, [open]);

  // Reposition on scroll/resize while open, so the popover follows the
  // pill if the page is short-scrolled.
  useEffect(() => {
    if (!open) return;
    const reposition = () => {
      if (!pillRef.current) return;
      const rect = pillRef.current.getBoundingClientRect();
      const popoverWidth = Math.min(320, window.innerWidth - 24);
      let left = rect.right - popoverWidth;
      if (left < 12) left = 12;
      setPos({ top: rect.bottom + 8, left });
    };
    window.addEventListener("scroll", reposition, { passive: true });
    window.addEventListener("resize", reposition);
    return () => {
      window.removeEventListener("scroll", reposition);
      window.removeEventListener("resize", reposition);
    };
  }, [open]);

  // Sort by time asc — "next up" wins the pill label. Memoised so the
  // sort doesn't run every re-render.
  const sorted = useMemo(
    () =>
      [...reminders].sort(
        (a, b) =>
          new Date(a.remind_at).getTime() - new Date(b.remind_at).getTime(),
      ),
    [reminders],
  );

  const now = Date.now();
  const overdueCount = sorted.filter(
    (r) => new Date(r.remind_at).getTime() < now,
  ).length;

  // Don't render while loading OR when there's nothing to show — the hero
  // badge row should stay clean for users with no pending calls.
  if (loading || sorted.length === 0) return null;

  const first = sorted[0];
  const firstOverdue = new Date(first.remind_at).getTime() < now;
  const more = sorted.length - 1;

  const pillBg = firstOverdue
    ? "color-mix(in srgb, var(--danger) 12%, transparent)"
    : "color-mix(in srgb, var(--accent) 10%, transparent)";
  const pillBorder = firstOverdue
    ? "color-mix(in srgb, var(--danger) 35%, transparent)"
    : "color-mix(in srgb, var(--accent) 30%, transparent)";
  const pillColor = firstOverdue ? "var(--danger)" : "var(--accent)";

  return (
    <div ref={wrapperRef} className="relative inline-flex">
      <button
        ref={pillRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setOpen((v) => !v);
          }
        }}
        aria-label={`Напоминания на сегодня: ${sorted.length}${overdueCount > 0 ? `, просрочено ${overdueCount}` : ""}`}
        aria-expanded={open}
        className="inline-flex items-center gap-1.5 font-mono text-xs px-2.5 py-1 rounded-full uppercase tracking-wider cursor-pointer transition-all hover:brightness-110 hover:shadow-md active:scale-95"
        style={{
          background: pillBg,
          border: `1px solid ${pillBorder}`,
          color: pillColor,
        }}
        title={
          firstOverdue
            ? `Просрочено: ${first.client_name ?? "клиент"} — ${formatTime(first.remind_at)}`
            : `Ближайшее: ${first.client_name ?? "клиент"} — ${formatTime(first.remind_at)}`
        }
      >
        <Clock size={10} />
        {formatTime(first.remind_at)}
        {more > 0 && (
          <span
            className="rounded px-1"
            style={{
              background: "color-mix(in srgb, currentColor 25%, transparent)",
              color: "inherit",
            }}
          >
            +{more}
          </span>
        )}
        {/* overdue red dot — visible even when the pill isn't red (edge case:
            only later items overdue, earliest still in future) */}
        {!firstOverdue && overdueCount > 0 && (
          <span
            aria-hidden
            className="w-1.5 h-1.5 rounded-full"
            style={{ background: "var(--danger)" }}
          />
        )}
        {/* 2026-04-20: chevron — явный сигнал "это кликабельный dropdown".
            Поворот на 180° при open для visual feedback. */}
        <ChevronDown
          size={10}
          className="transition-transform"
          style={{ transform: open ? "rotate(180deg)" : "rotate(0)" }}
        />
      </button>

      {/* Popover rendered via portal into <body> so parent `overflow:hidden`
          on the hero glass-panel (and z-index stacks) cannot clip it.
          Position is computed against the pill's bounding rect. */}
      {typeof document !== "undefined" &&
        createPortal(
          <AnimatePresence>
            {open && pos && (
              <motion.div
                key="popover"
                ref={popoverRef}
                initial={{ opacity: 0, y: -4, scale: 0.97 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -4, scale: 0.97 }}
                transition={{ duration: 0.15 }}
                role="dialog"
                aria-label="Напоминания на сегодня"
                className="fixed z-[1000] rounded-lg p-3"
                style={{
                  top: pos.top,
                  left: pos.left,
                  width: "min(320px, calc(100vw - 24px))",
                  // 2026-04-20: ИСПРАВЛЕНО — прозрачный var(--bg-panel) на
                  // glass-подложке делал текст в popover нечитаемым. Теперь
                  // сплошной var(--bg-primary) + заметный border и boxShadow
                  // → popover "стоит над" hero-панелью, а не "сквозь" неё.
                  background: "var(--bg-primary)",
                  border: "1px solid var(--border-color)",
                  boxShadow:
                    "0 20px 50px rgba(0,0,0,0.55), 0 0 0 1px color-mix(in srgb, var(--accent) 15%, transparent)",
                  backdropFilter: "blur(0)",
                }}
              >
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <Clock size={12} style={{ color: "var(--accent)" }} />
                <span
                  className="text-[11px] font-mono uppercase tracking-wider"
                  style={{ color: "var(--accent)", letterSpacing: "0.14em" }}
                >
                  Напоминания сегодня
                </span>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Закрыть"
                className="p-1 rounded hover:bg-[var(--bg-secondary)] transition"
                style={{ color: "var(--text-muted)" }}
              >
                <X size={12} />
              </button>
            </div>

            <div className="space-y-1.5">
              {sorted.slice(0, 5).map((r, i) => {
                const isOverdue = new Date(r.remind_at).getTime() < now;
                return (
                  <motion.div
                    key={r.id}
                    initial={{ opacity: 0, x: -6 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.03 }}
                  >
                    <Link
                      href={`/clients/${r.client_id}`}
                      onClick={() => setOpen(false)}
                      className="flex items-center gap-2.5 rounded-md p-2 transition-colors hover:bg-[var(--bg-secondary)]"
                      style={{ background: "var(--input-bg)" }}
                    >
                      <Phone
                        size={11}
                        style={{
                          color: isOverdue
                            ? "var(--danger)"
                            : "var(--text-muted)",
                        }}
                      />
                      <div className="flex-1 min-w-0">
                        <span
                          className="text-xs font-medium truncate block"
                          style={{ color: "var(--text-primary)" }}
                        >
                          {sanitizeText(r.client_name || "Клиент")}
                        </span>
                        {r.message && (
                          <span
                            className="text-[10px] truncate block"
                            style={{ color: "var(--text-muted)" }}
                          >
                            {sanitizeText(r.message)}
                          </span>
                        )}
                      </div>
                      <span
                        className="text-[11px] font-mono tabular-nums shrink-0"
                        style={{
                          color: isOverdue
                            ? "var(--danger)"
                            : "var(--text-muted)",
                        }}
                      >
                        {formatTime(r.remind_at)}
                      </span>
                    </Link>
                  </motion.div>
                );
              })}
            </div>

            {sorted.length > 5 && (
              <div
                className="text-center mt-2 text-[10px]"
                style={{ color: "var(--text-muted)" }}
              >
                +{sorted.length - 5} ещё
              </div>
            )}

            <Link
              href="/clients"
              onClick={() => setOpen(false)}
              className="mt-2 flex items-center justify-center gap-1 py-1.5 rounded-md text-[11px] font-medium uppercase tracking-wider transition"
              style={{
                background: "var(--accent-muted)",
                color: "var(--accent)",
              }}
            >
              Все напоминания <ChevronRight size={10} />
            </Link>
              </motion.div>
            )}
          </AnimatePresence>,
          document.body,
        )}
    </div>
  );
}
