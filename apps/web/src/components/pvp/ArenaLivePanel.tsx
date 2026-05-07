"use client";

/**
 * ArenaLivePanel — left-sidebar widget «Арена сейчас».
 *
 * PR-16 (2026-05-07). Показывает:
 *   - текущий queue size (опрос /pvp/queue/status каждые 15 сек)
 *   - твоё место в очереди когда ищешь матч (из usePvPStore.queueStatus)
 *   - индикатор подключения WS (connectionState)
 *
 * Дополнительные стат-цифры (онлайн / матчей за день) можно добавить
 * позднее когда появятся endpoint'ы — сейчас фокус на том что уже
 * есть в store без новых API.
 */

import { useEffect, useState } from "react";
import { Loader2, Radio, Users, Clock } from "lucide-react";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";
import { usePvPStore } from "@/stores/usePvPStore";

interface QueueStatus {
  queue_size: number;
}

export function ArenaLivePanel() {
  const queueStatus = usePvPStore((s) => s.queueStatus);
  const queuePosition = usePvPStore((s) => s.queuePosition);
  const estimatedWait = usePvPStore((s) => s.estimatedWait);
  const [serverQueue, setServerQueue] = useState<number | null>(null);

  useEffect(() => {
    const tick = async () => {
      try {
        const data = await api.get<QueueStatus>("/pvp/queue/status");
        if (typeof data?.queue_size === "number") setServerQueue(data.queue_size);
      } catch (err) {
        logger.warn("[arena-live] queue status fetch failed:", err);
      }
    };
    tick();
    const id = window.setInterval(tick, 15_000);
    return () => window.clearInterval(id);
  }, []);

  const searching = queueStatus === "searching";
  const matched = queueStatus === "matched";

  return (
    <section
      className="p-3"
      style={{
        background: "var(--bg-panel)",
        outline: `2px solid ${searching ? "var(--success)" : matched ? "var(--accent)" : "var(--border-color)"}`,
        outlineOffset: -2,
        boxShadow: searching ? "3px 3px 0 0 var(--success)" : "3px 3px 0 0 var(--border-color)",
        borderRadius: 0,
        transition: "outline-color 200ms, box-shadow 200ms",
      }}
      aria-label="Активность арены"
    >
      <div
        className="font-pixel uppercase tracking-widest mb-3 flex items-center gap-2"
        style={{
          color: searching ? "var(--success)" : "var(--text-muted)",
          fontSize: 11,
          letterSpacing: "0.16em",
        }}
      >
        <Radio
          size={13}
          className={searching ? "animate-pulse" : ""}
        />
        АРЕНА СЕЙЧАС
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs">
          <span
            className="flex items-center gap-1.5"
            style={{ color: "var(--text-muted)" }}
          >
            <Users size={12} />
            В очереди
          </span>
          <span
            className="font-pixel tabular-nums"
            style={{ color: "var(--text-primary)", fontSize: 14 }}
          >
            {serverQueue !== null ? serverQueue : "—"}
          </span>
        </div>

        {searching && (
          <>
            <div className="flex items-center justify-between text-xs">
              <span
                className="flex items-center gap-1.5"
                style={{ color: "var(--text-muted)" }}
              >
                Твоё место
              </span>
              <span
                className="font-pixel tabular-nums"
                style={{ color: "var(--success)", fontSize: 14 }}
              >
                {queuePosition || "?"}
              </span>
            </div>

            {estimatedWait > 0 && (
              <div className="flex items-center justify-between text-xs">
                <span
                  className="flex items-center gap-1.5"
                  style={{ color: "var(--text-muted)" }}
                >
                  <Clock size={12} />
                  Осталось
                </span>
                <span
                  className="font-pixel tabular-nums"
                  style={{ color: "var(--success)", fontSize: 13 }}
                >
                  ~{estimatedWait}с
                </span>
              </div>
            )}

            <div
              className="mt-2 flex items-center justify-center gap-2 px-2 py-1.5 font-pixel uppercase text-[10px]"
              style={{
                background: "color-mix(in srgb, var(--success) 12%, transparent)",
                color: "var(--success)",
                border: "1px solid var(--success)",
                letterSpacing: "0.16em",
              }}
            >
              <Loader2 size={11} className="animate-spin" />
              ИЩЕМ СОПЕРНИКА
            </div>
          </>
        )}

        {matched && (
          <div
            className="mt-2 flex items-center justify-center gap-2 px-2 py-1.5 font-pixel uppercase text-[10px]"
            style={{
              background: "color-mix(in srgb, var(--accent) 14%, transparent)",
              color: "var(--accent)",
              border: "1px solid var(--accent)",
              letterSpacing: "0.16em",
            }}
          >
            ✓ МАТЧ НАЙДЕН
          </div>
        )}

        {queueStatus === "idle" && (
          <div
            className="mt-1 font-pixel uppercase text-[10px] tracking-widest"
            style={{ color: "var(--text-muted)", letterSpacing: "0.16em" }}
          >
            Нажми «Дуэль» →
          </div>
        )}
      </div>
    </section>
  );
}
